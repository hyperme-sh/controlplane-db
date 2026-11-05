"""Private TEST financial erasure. No provider I/O, commits, or public routing.

Call only on the coordinator's privileged connection, after native discovery.
Database-bound TEST policy is mandatory; environment variables grant no authority.
All deletion capabilities bind actual locked row images in this transaction.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from sqlalchemy import text


class TestRetentionUnavailable(RuntimeError):
    __test__ = False


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _table(name):
    return "public." + _quote(name)


def _sql(connection, statement, **params):
    return connection.execute(text(statement), params)


def _mentions(value, identities):
    if isinstance(value, str):
        return value in identities
    if isinstance(value, list):
        return any(_mentions(item, identities) for item in value)
    if isinstance(value, dict):
        return any(_mentions(item, identities) for item in value.values())
    return False


def purge_test_finances(connection, subject, closed_at, *, limit=100):
    """Erase one account's financial rows and FK children; caller commits receipt.

    Real production retention and holds remain in force unless this database was
    explicitly configured by its administrator as TEST. A rollback removes both
    deleted rows and capabilities. Another customer's roots are never selected.
    """
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Bounded TEST erasure batch required")
    if (
        _sql(connection, "SELECT public.account_test_data_enabled()").scalar_one()
        is not True
    ):
        raise TestRetentionUnavailable("Database is not configured for TEST erasure")
    _sql(
        connection,
        "SELECT public.account_require_financial_inventory(:s,:at)",
        s=subject,
        at=closed_at,
    )
    _sql(
        connection,
        "SELECT public.account_lock_financial_inventory(:s,:at,NULL)",
        s=subject,
        at=closed_at,
    )
    if (
        _sql(connection, "SELECT public.account_lock_test_data_policy()").scalar_one()
        is not True
    ):
        raise TestRetentionUnavailable("Database TEST policy changed")
    life = _sql(
        connection,
        "SELECT effects FROM public.account_lifecycles WHERE subject=:s",
        s=subject,
    ).scalar_one()
    scopes = _sql(
        connection,
        "SELECT user_ids,effects FROM public.account_lifecycle_scopes WHERE subject=:s",
        s=subject,
    ).all()
    user_ids = set(life["platform_profile"]["user_ids"])
    aliases = {subject}
    for ids, effects in scopes:
        user_ids.update(ids)
        aliases.update(
            "apikey:" + key["id"] for key in effects.get("api_keys", {}).get("keys", [])
        )
    identities = user_ids | aliases
    # Source relations are owned by these schemas; catalog FKs supply dependent
    # rows. Internal FK triggers remain enabled and may refuse unsafe deletion.
    registry = json.loads(
        Path(__file__)
        .with_name("migration_chains")
        .joinpath("manifest.json")
        .read_text()
    )
    root_names = set(registry["chains"]["payment_service"]["tables"]) | {
        "billing_records",
        "hypermesh_leases",
        "hypermesh_orders",
        "hypermesh_payouts",
        "hypermesh_fills",
        "connect_reversal_exposure_observations",
    }
    relations = dict(
        _sql(
            connection,
            "SELECT c.oid,c.relname FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r'",
        ).all()
    )
    by_name = {name: oid for oid, name in relations.items()}
    fks = _sql(
        connection,
        """SELECT f.conrelid,f.confrelid,
      ARRAY(SELECT a.attname FROM unnest(f.conkey) WITH ORDINALITY k(attnum,ord)
        JOIN pg_catalog.pg_attribute a ON a.attrelid=f.conrelid AND a.attnum=k.attnum ORDER BY k.ord),
      ARRAY(SELECT a.attname FROM unnest(f.confkey) WITH ORDINALITY k(attnum,ord)
        JOIN pg_catalog.pg_attribute a ON a.attrelid=f.confrelid AND a.attnum=k.attnum ORDER BY k.ord)
      FROM pg_catalog.pg_constraint f WHERE f.contype='f' ORDER BY f.oid""",
    ).all()
    # Cross-owner source references intentionally use native guards instead of
    # foreign keys. Follow these exact, tenant-bound relationships as well.
    for child, parent, child_cols, parent_cols in (
        (
            "billing_tax_orders",
            "billing_records",
            ("billing_record_id", "tenant_id"),
            ("id", "tenant_id"),
        ),
        (
            "hypermesh_leases",
            "billing_records",
            ("billing_record_id", "tenant_id"),
            ("id", "tenant_id"),
        ),
        (
            "hypermesh_payouts",
            "hypermesh_leases",
            ("lease_id", "tenant_id"),
            ("id", "tenant_id"),
        ),
        (
            "hypermesh_jobs",
            "hypermesh_leases",
            ("lease_id", "tenant_id"),
            ("id", "tenant_id"),
        ),
        (
            "hypermesh_tunnels",
            "hypermesh_leases",
            ("lease_id", "tenant_id"),
            ("id", "tenant_id"),
        ),
        (
            "hypermesh_tickets",
            "hypermesh_leases",
            ("lease_id", "tenant_id"),
            ("id", "tenant_id"),
        ),
        (
            "hypermesh_fills",
            "hypermesh_orders",
            ("order_id", "tenant_id"),
            ("order_id", "tenant_id"),
        ),
    ):
        if child in by_name and parent in by_name:
            fks.append((by_name[child], by_name[parent], child_cols, parent_cols))
    reachable = {by_name[name] for name in root_names if name in by_name}
    while True:
        expanded = reachable | {
            child
            for child, parent, _, _ in fks
            if parent in reachable and child in relations
        }
        if expanded == reachable:
            break
        reachable = expanded
    # Block source mutation while collecting the complete FK graph. Bound the
    # lock/statement waits in the coordinator before entering this helper.
    _sql(
        connection,
        "LOCK TABLE "
        + ",".join(_table(relations[oid]) for oid in sorted(reachable))
        + " IN SHARE ROW EXCLUSIVE MODE",
    )
    targets = {}
    more_roots = False
    pending = []
    dependencies = defaultdict(set)
    for name in sorted(root_names):
        if name not in by_name:
            continue
        # Query owner fields, not arbitrary audit/recipient text. Native billing
        # has two identity forms; their agreement is checked below.
        predicate = """to_jsonb(t)->>'user_id'=ANY(CAST(:users AS text[]))
          OR to_jsonb(t)->>'owner_sub'=ANY(CAST(:ids AS text[]))
          OR to_jsonb(t)->>'payer_sub'=ANY(CAST(:ids AS text[]))
          OR to_jsonb(t)->>'renter_user_id'=ANY(CAST(:people AS text[]))"""
        if name == "billing_records":
            predicate += (
                " OR to_jsonb(t)->'metadata'->>'actor_sub'=ANY(CAST(:ids AS text[]))"
            )
        if name == "hypermesh_orders":
            predicate += " OR to_jsonb(t)->>'org_id'=ANY(CAST(:ids AS text[]))"
        if name == "billing_records":
            predicate = "(" + predicate + ") AND t.actor <> 'tenant'"
        rows = _sql(
            connection,
            f"SELECT ctid::text,to_jsonb(t) FROM {_table(name)} t WHERE {predicate} LIMIT :lim",
            ids=sorted(aliases),
            users=sorted(user_ids),
            people=sorted(identities),
            lim=limit + 1,
        ).all()
        for locator, data in rows:
            if len(pending) >= limit:
                more_roots = True
                break
            if name == "billing_records":
                metadata = data.get("metadata")
                if not isinstance(metadata, dict):
                    raise TestRetentionUnavailable("Malformed native payer ownership")
                user, actor = data.get("user_id"), metadata.get("actor_sub")
                if (user is not None and user not in user_ids) or (
                    actor is not None and actor not in aliases
                ):
                    raise TestRetentionUnavailable("Conflicting native payer ownership")
            key = (by_name[name], locator)
            if key not in targets:
                targets[key] = (data, 0)
                pending.append(key)
    # Select risk entries only from their original canonical, non-shared binding.
    risk = _sql(
        connection,
        """SELECT r.ctid::text,to_jsonb(r) FROM public.payer_mismatch_accounts r
      WHERE EXISTS(SELECT 1 FROM public.account_financial_source_bindings b WHERE b.subject=:s
        AND b.kind='payer_mismatch_accounts' AND b.resource=r.account_key)
        AND NOT EXISTS(SELECT 1 FROM public.account_financial_source_bindings b WHERE b.subject<>:s
          AND b.kind='payer_mismatch_accounts' AND b.resource=r.account_key) LIMIT :lim""",
        s=subject,
        lim=limit,
    ).all()
    for locator, data in risk:
        key = (by_name["payer_mismatch_accounts"], locator)
        if key not in targets and len(pending) < limit:
            targets[key] = (data, 0)
            pending.append(key)
    allowed_names = root_names | {
        "hypermesh_jobs",
        "hypermesh_tunnels",
        "hypermesh_tickets",
        "host_organization_bindings",
        "ai_agent_entitlements",
        "marketplace_purchases",
    }
    # Follow all declared foreign keys, including RESTRICT relationships; never
    # disable internal constraints or leave another table pointing at a deletion.
    index = 0
    while index < len(pending):
        parent, locator = pending[index]
        index += 1
        data, depth = targets[(parent, locator)]
        for child, referenced, child_cols, parent_cols in fks:
            if referenced != parent or child not in reachable:
                continue
            predicate = " AND ".join(
                "c." + _quote(a) + " = p." + _quote(b)
                for a, b in zip(child_cols, parent_cols, strict=True)
            )
            rows = _sql(
                connection,
                f"SELECT c.ctid::text,to_jsonb(c) FROM {_table(relations[child])} c JOIN {_table(relations[parent])} p ON {predicate} WHERE p.ctid=CAST(CAST(:tid AS text) AS tid) LIMIT 1001",
                tid=locator,
            ).all()
            for child_tid, child_data in rows:
                if relations[child] not in allowed_names:
                    raise TestRetentionUnavailable(
                        "Unrecognized financial dependency owner"
                    )
                if (
                    "tenant_id" in data
                    and "tenant_id" in child_data
                    and data["tenant_id"] != child_data["tenant_id"]
                ):
                    raise TestRetentionUnavailable("Cross-tenant financial dependency")
                key = (child, child_tid)
                if key != (parent, locator):
                    dependencies[(parent, locator)].add(key)
                if key not in targets:
                    if len(targets) >= 1000:
                        raise TestRetentionUnavailable(
                            "TEST financial dependency batch exceeds limit"
                        )
                    targets[key] = (child_data, depth + 1)
                    pending.append(key)
    # Row locks and exact-image capabilities precede every delete. All original
    # native AFTER triggers continue invalidating inventories/epochs normally.
    for (oid, locator), (data, _) in targets.items():
        if data.get("livemode") is True:
            raise TestRetentionUnavailable("Live provider rows are not TEST data")
        current = _sql(
            connection,
            f"SELECT to_jsonb(t) FROM {_table(relations[oid])} t WHERE ctid=CAST(CAST(:tid AS text) AS tid) FOR UPDATE",
            tid=locator,
        ).scalar_one()
        if current != data:
            raise TestRetentionUnavailable("TEST financial source changed")
        _sql(
            connection,
            f"""INSERT INTO public.account_test_delete_capabilities
          SELECT pg_current_xact_id()::text,:oid,sha256(convert_to(to_jsonb(t)::text,'UTF8'))
          FROM {_table(relations[oid])} t WHERE ctid=CAST(CAST(:tid AS text) AS tid)
          ON CONFLICT DO NOTHING""",
            oid=oid,
            tid=locator,
        )
    counts = defaultdict(int)
    remaining = set(targets)
    while remaining:
        leaves = [key for key in remaining if not (dependencies[key] & remaining)]
        if not leaves:
            raise TestRetentionUnavailable(
                "Cyclic financial dependency requires native owner reconciliation"
            )
        for oid, locator in sorted(leaves):
            result = _sql(
                connection,
                f"DELETE FROM {_table(relations[oid])} WHERE ctid=CAST(CAST(:tid AS text) AS tid)",
                tid=locator,
            )
            counts[relations[oid]] += result.rowcount
            remaining.remove((oid, locator))
    _sql(
        connection,
        "DELETE FROM public.account_test_delete_capabilities WHERE transaction_id=pg_current_xact_id()::text",
    )
    # Original source bindings must be reconciled against live rows before any
    # completion claim. A failed/incomplete owner is never treated as empty.
    bindings = _sql(
        connection,
        "SELECT tenant_id,owner,kind,resource FROM public.account_financial_source_bindings WHERE subject=:s ORDER BY owner,kind,resource LIMIT 1000",
        s=subject,
    ).all()
    for tenant, owner, kind, resource in bindings:
        name = "billing_records" if owner == "billing" and kind == "payment" else kind
        if name not in allowed_names or name not in by_name:
            raise TestRetentionUnavailable("Unrecognized native financial source")
        identity = (
            "(to_jsonb(t)->>'host_org_id')||':'||(to_jsonb(t)->>'chain_id')"
            if name == "host_payout_addresses"
            else "coalesce(to_jsonb(t)->>'id',to_jsonb(t)->>'grant_id',to_jsonb(t)->>'revision_id',to_jsonb(t)->>'account_key',to_jsonb(t)->>'host_org_id',to_jsonb(t)->>'order_id',to_jsonb(t)->>'lease_id',to_jsonb(t)->>'organization_id')"
        )
        rows = (
            _sql(
                connection,
                f"SELECT to_jsonb(t) FROM {_table(name)} t WHERE {identity}=:r AND to_jsonb(t)->>'tenant_id' IS NOT DISTINCT FROM CAST(:tenant AS text)",
                r=resource,
                tenant=str(tenant) if tenant else None,
            )
            .scalars()
            .all()
        )
        if any(_mentions(row, identities) for row in rows):
            continue
        # Do not erase company records through an indirect former membership.
        # Once no native customer reference remains, unlink only this closure's
        # obsolete association; other parties' bindings and rows remain intact.
        subject_clause = "subject=:s AND " if rows else ""
        _sql(
            connection,
            "DELETE FROM public.account_financial_source_bindings WHERE "
            + subject_clause
            + "tenant_id IS NOT DISTINCT FROM CAST(:t AS uuid) AND owner=:o AND kind=:k AND resource=:r",
            s=subject,
            t=str(tenant) if tenant else None,
            o=owner,
            k=kind,
            r=resource,
        )
    remaining_bindings = _sql(
        connection,
        "SELECT count(*) FROM public.account_financial_source_bindings WHERE subject=:s",
        s=subject,
    ).scalar_one()
    return {
        "complete": remaining_bindings == 0 and not more_roots,
        "roots_complete": not more_roots,
        "deleted": sum(counts.values()),
        "remaining": remaining_bindings + int(more_roots),
        "tables": dict(counts),
    }
