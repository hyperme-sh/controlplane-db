"""Native nondestructive source priming precedes personal owner cleanup."""

import json
import uuid
from datetime import timedelta

import pytest
from controlplane_db import migrations
from migration_test_support import isolated_postgres
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


@pytest.fixture(scope="module")
def inventory_engine():
    with isolated_postgres() as url:
        engine = create_engine(url)
        migrations.upgrade(engine.url.render_as_string(hide_password=False))
        yield engine
        engine.dispose()


def source(cx, subject, tenant):
    identifier = uuid.uuid4()
    cx.execute(
        text("""INSERT INTO billing_records
      (id,tenant_id,scope,actor,payment_type,currency,amount,status,metadata)
      VALUES(:id,:t,'invoice','tenant','stripe_invoice','usd',100,'succeeded',CAST(:meta AS jsonb))"""),
        {"id": identifier, "t": tenant, "meta": json.dumps({"actor_sub": subject})},
    )
    return identifier


def closed_scope(cx, subject, tenant):
    at = cx.scalar(text("SELECT transaction_timestamp()"))
    effects = {
        "identity": {"disabled": True},
        "scope_discovery": True,
        "scope_tenants": [str(tenant)] if tenant else [],
        "platform_profile": {"user_ids": []},
    }
    cx.execute(
        text("""INSERT INTO account_lifecycles
      (subject,requested_at,requested_by,source,state,retry_at,closed_at,financial_hold,effects)
      VALUES(:s,:at,:s,'self_service','closed',:at,:at,false,CAST(:effects AS jsonb))"""),
        {"s": subject, "at": at, "effects": json.dumps(effects)},
    )
    cx.execute(
        text("INSERT INTO identity_retirements(subject,retired_at) VALUES(:s,:at)"),
        {"s": subject, "at": at},
    )
    if tenant:
        cx.execute(
            text("""INSERT INTO account_lifecycle_scopes(tenant_id,subject,user_ids,effects)
          VALUES(:t,:s,'[]','{"profile_inventory_complete": true}')"""),
            {"s": subject, "t": tenant},
        )
    return {"s": subject, "t": tenant, "at": at}


def seed(cx, count=2, *, global_scope=False):
    subject, tenant = (
        "inventory-" + uuid.uuid4().hex,
        None if global_scope else uuid.uuid4(),
    )
    if tenant:
        cx.execute(
            text("INSERT INTO tenants(id,name,is_active) VALUES(:t,:s,true)"),
            {"t": tenant, "s": subject},
        )
    identifiers = [source(cx, subject, tenant) for _ in range(count)]
    values = closed_scope(cx, subject, tenant)
    return values, identifiers


def prime(cx, values, limit=100):
    return cx.scalar(
        text("SELECT account_prime_billing_financial_sources(:s,:at,:t,:limit)"),
        {**values, "limit": limit},
    )


def marker(cx, values):
    if values["t"]:
        return cx.scalar(
            text(
                "SELECT effects->'financial_inventory' FROM account_lifecycle_scopes WHERE subject=:s AND tenant_id=:t"
            ),
            values,
        )
    return cx.scalar(
        text(
            "SELECT effects->'financial_inventory' FROM account_lifecycles WHERE subject=:s"
        ),
        values,
    )


@pytest.mark.parametrize("global_scope", [False, True])
def test_bounded_inventory_cannot_mark_unvisited_sources_complete(
    inventory_engine, global_scope
):
    with inventory_engine.begin() as cx:
        values, identifiers = seed(cx, global_scope=global_scope)
        before = cx.execute(
            text(
                "SELECT id,financial_activity_at,financial_retain_until,actor,metadata FROM billing_records WHERE id=ANY(:ids) ORDER BY id"
            ),
            {"ids": identifiers},
        ).all()
        assert prime(cx, values, 1) == {
            "complete": False,
            "processed": 1,
            "remaining": 1,
        }
        assert marker(cx, values) is None
        assert prime(cx, values, 1) == {
            "complete": True,
            "processed": 1,
            "remaining": 0,
        }
        assert marker(cx, values) == {"billing": 1}
        assert prime(cx, values, 1) == {
            "complete": True,
            "processed": 0,
            "remaining": 0,
        }
        assert (
            cx.execute(
                text(
                    "SELECT id,financial_activity_at,financial_retain_until,actor,metadata FROM billing_records WHERE id=ANY(:ids) ORDER BY id"
                ),
                {"ids": identifiers},
            ).all()
            == before
        )
        assert (
            cx.scalar(
                text(
                    "SELECT count(*) FROM account_financial_source_bindings WHERE subject=:s"
                ),
                values,
            )
            == 2
        )


def test_hold_allows_inventory_but_still_refuses_financial_destruction(
    inventory_engine,
):
    with inventory_engine.begin() as cx:
        values, _ = seed(cx)
        cx.execute(
            text(
                "UPDATE account_lifecycles SET financial_hold=true,hold_reference='preserve' WHERE subject=:s"
            ),
            values,
        )
        assert prime(cx, values)["complete"]
        with (
            pytest.raises(DBAPIError, match="Financial erasure authority unavailable"),
            cx.begin_nested(),
        ):
            cx.execute(text("SELECT account_financial_epoch(:s,:at,:t)"), values)


@pytest.mark.parametrize(
    "invalid", ["date", "scope", "state", "retirement", "coverage"]
)
def test_inventory_requires_current_native_closed_scope(inventory_engine, invalid):
    with inventory_engine.begin() as cx:
        values, _ = seed(cx)
    with pytest.raises(DBAPIError) as caught, inventory_engine.begin() as cx:
        if invalid == "date":
            values = {**values, "at": values["at"] + timedelta(seconds=1)}
        elif invalid == "scope":
            values = {**values, "t": uuid.uuid4()}
        elif invalid == "state":
            cx.execute(
                text("UPDATE account_lifecycles SET state='closing' WHERE subject=:s"),
                values,
            )
        elif invalid == "retirement":
            cx.execute(
                text("DELETE FROM identity_retirements WHERE subject=:s"), values
            )
        else:
            cx.execute(
                text(
                    "DELETE FROM account_financial_fence_versions WHERE owner='hypermesh'"
                )
            )
        prime(cx, values)
    assert caught.value.orig.sqlstate == "42501"


@pytest.mark.parametrize("limit", [None, 0, 1001])
def test_inventory_batch_limit_cannot_skip_source_discovery(inventory_engine, limit):
    with inventory_engine.begin() as cx:
        values, _ = seed(cx)
    with pytest.raises(DBAPIError) as caught, inventory_engine.begin() as cx:
        prime(cx, values, limit)
    assert caught.value.orig.sqlstate == "42501"


def test_inventory_retries_when_lifecycle_row_is_owned_by_a_hold_setter(
    inventory_engine,
):
    with inventory_engine.begin() as cx:
        values, _ = seed(cx)
    with inventory_engine.begin() as holder:
        holder.execute(
            text("SELECT subject FROM account_lifecycles WHERE subject=:s FOR UPDATE"),
            values,
        )
        with pytest.raises(DBAPIError) as caught, inventory_engine.begin() as writer:
            writer.execute(text("SET LOCAL statement_timeout='1000ms'"))
            prime(writer, values)
        assert caught.value.orig.sqlstate == "40001"


def historical_host(cx):
    values = {
        "s": "historical-host-" + uuid.uuid4().hex,
        "t": uuid.uuid4(),
        "org": uuid.uuid4(),
        "device": uuid.uuid4(),
    }
    cx.execute(
        text("INSERT INTO tenants(id,name,is_active) VALUES(:t,:s,true)"), values
    )
    cx.execute(
        text("INSERT INTO organizations(id,tenant_id,legal_name) VALUES(:org,:t,:s)"),
        values,
    )
    return values


def test_payment_inventory_primes_distinct_historical_payout_addresses(
    inventory_engine,
):
    with inventory_engine.begin() as cx:
        values = historical_host(cx)
        for chain in (8453, 84532):
            cx.execute(
                text("""INSERT INTO host_payout_addresses
              (tenant_id,host_org_id,chain_id,address,verified_by_sub,proof_audience,
               proof_message_hash,proof_signature_hash,verified_at)
              VALUES(:t,:org,:chain,:address,:s,'native-test',:digest,:digest,now())"""),
                {
                    **values,
                    "chain": chain,
                    "address": "0x" + "a" * 40,
                    "digest": "b" * 64,
                },
            )
        values.update(closed_scope(cx, values["s"], values["t"]))
        clocks = cx.execute(
            text(
                "SELECT chain_id,financial_activity_at,financial_retain_until FROM host_payout_addresses WHERE tenant_id=:t ORDER BY chain_id"
            ),
            values,
        ).all()
        call = text("SELECT payment_prime_financial_sources(:s,:at,:t,1)")
        assert cx.scalar(call, values) == {
            "complete": False,
            "processed": 1,
            "remaining": 1,
        }
        assert marker(cx, values) is None
        assert cx.scalar(call, values) == {
            "complete": True,
            "processed": 1,
            "remaining": 0,
        }
        assert marker(cx, values) == {"payment": 1}
        assert set(
            cx.scalars(
                text(
                    "SELECT resource FROM account_financial_source_bindings WHERE subject=:s AND owner='payment'"
                ),
                values,
            )
        ) == {str(values["org"]) + ":8453", str(values["org"]) + ":84532"}
        assert (
            cx.execute(
                text(
                    "SELECT chain_id,financial_activity_at,financial_retain_until FROM host_payout_addresses WHERE tenant_id=:t ORDER BY chain_id"
                ),
                values,
            ).all()
            == clocks
        )
        assert cx.scalar(call, values) == {
            "complete": True,
            "processed": 0,
            "remaining": 0,
        }


def test_hypermesh_inventory_primes_historical_device_only_host_peers(inventory_engine):
    with inventory_engine.begin() as cx:
        values = historical_host(cx)
        peer = uuid.uuid4()
        cx.execute(
            text(
                "INSERT INTO host_organization_bindings(tenant_id,keycloak_sub,organization_id) VALUES(:t,:s,:org)"
            ),
            values,
        )
        cx.execute(
            text("""INSERT INTO hypermesh_devices
          (id,tenant_id,class_id,host_org_id,serial,path_a,path_b_state,
           loaded_instance_state,enrolled,created_at,sell_state,role)
          VALUES(:device,:t,'native-class',:org,:s,'{}','never_run','none',false,now(),'n/a','host')"""),
            values,
        )
        cx.execute(
            text("""INSERT INTO hypermesh_tunnels
          (id,tenant_id,device_id,lease_id,status,endpoint,server_public_key,
           server_private_key,allowed_ips,client_address,ack_applied,created_at)
          VALUES(:id,:t,:device,NULL,'allocated','native-test','public','private-test',
                 '10.77.0.0/24','10.77.0.2/32',false,now())"""),
            {**values, "id": peer},
        )
        values.update(closed_scope(cx, values["s"], values["t"]))
        call = text("SELECT hypermesh_prime_financial_sources(:s,:at,:t,1)")
        assert cx.scalar(call, values) == {
            "complete": False,
            "processed": 1,
            "remaining": 1,
        }
        assert marker(cx, values) is None
        assert cx.scalar(call, values) == {
            "complete": True,
            "processed": 1,
            "remaining": 0,
        }
        assert marker(cx, values) == {"hypermesh": 1}
        bindings = set(
            cx.execute(
                text(
                    "SELECT kind,resource FROM account_financial_source_bindings WHERE subject=:s AND owner='hypermesh'"
                ),
                values,
            ).all()
        )
        assert bindings == {
            ("host_organization_bindings", str(values["org"])),
            ("hypermesh_tunnels", str(peer)),
        }
        before = cx.scalar(
            text("SELECT financial_epoch FROM account_lifecycles WHERE subject=:s"),
            values,
        )
        cx.execute(
            text("UPDATE hypermesh_tunnels SET ack_applied=true WHERE id=:id"),
            {"id": peer},
        )
        assert (
            cx.scalar(
                text("SELECT financial_epoch FROM account_lifecycles WHERE subject=:s"),
                values,
            )
            > before
        )
        assert cx.scalar(call, values) == {
            "complete": True,
            "processed": 0,
            "remaining": 0,
        }


@pytest.mark.parametrize("owner", ["payment", "hypermesh"])
def test_native_owner_global_scope_records_actual_empty_inventory(
    inventory_engine, owner
):
    with inventory_engine.begin() as cx:
        values, _ = seed(cx, count=0, global_scope=True)
        result = cx.scalar(
            text(f"SELECT {owner}_prime_financial_sources(:s,:at,:t,100)"), values
        )
        assert result == {"complete": True, "processed": 0, "remaining": 0}
        assert marker(cx, values) == {owner: 1}


def test_global_payer_risk_inventory_uses_native_subject_hash(inventory_engine):
    import hashlib

    subject = "global-risk-" + uuid.uuid4().hex
    account_key = hashlib.sha256(subject.encode()).hexdigest()
    with inventory_engine.begin() as cx:
        cx.execute(
            text(
                "INSERT INTO payer_mismatch_accounts(account_key,day,mismatches,reserved_count,reserved_cents) VALUES(:key,current_date,1,0,0)"
            ),
            {"key": account_key},
        )
        values = closed_scope(cx, subject, None)
        result = cx.scalar(
            text("SELECT payment_prime_financial_sources(:s,:at,:t,100)"), values
        )
        assert result == {"complete": True, "processed": 1, "remaining": 0}
        assert marker(cx, values) == {"payment": 1}
        assert (
            cx.scalar(
                text(
                    "SELECT resource FROM account_financial_source_bindings WHERE subject=:s AND kind='payer_mismatch_accounts' AND tenant_id IS NULL"
                ),
                values,
            )
            == account_key
        )
        assert (
            cx.scalar(
                text(
                    "SELECT mismatches FROM payer_mismatch_accounts WHERE account_key=:key"
                ),
                {"key": account_key},
            )
            == 1
        )


@pytest.mark.parametrize(
    "query",
    [
        "SELECT account_prime_billing_financial_sources(:s,:at,:t,100)",
        "SELECT payment_prime_financial_sources(:s,:at,:t,100)",
        "SELECT hypermesh_prime_financial_sources(:s,:at,:t,100)",
        "SELECT account_record_financial_inventory(:s,:at,:t,'hypermesh')",
        "SELECT account_financial_source_bound(:s,:t,'billing','payment','unknown')",
    ],
)
def test_inventory_functions_are_not_public_capabilities(inventory_engine, query):
    role = "inventory_reader_" + uuid.uuid4().hex
    with inventory_engine.begin() as cx:
        values, _ = seed(cx, count=0)
        cx.execute(text(f"CREATE ROLE {role} NOLOGIN"))
        cx.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
    try:
        with pytest.raises(DBAPIError) as caught, inventory_engine.begin() as cx:
            cx.execute(text(f"SET LOCAL ROLE {role}"))
            cx.execute(text(query), values)
        assert caught.value.orig.sqlstate == "42501"
        assert "permission denied for function" in str(caught.value)
    finally:
        with inventory_engine.begin() as cx:
            cx.execute(text(f"DROP OWNED BY {role}"))
            cx.execute(text(f"DROP ROLE {role}"))


FINISH = text('SELECT account_finish_source_free_closure(:s,:at,:epoch)')


@pytest.fixture
def source_free_account(inventory_engine):
    with inventory_engine.connect() as cx:
        transaction = cx.begin()
        try:
            values = closed_scope(cx, str(uuid.uuid4()), None)
            cx.execute(text("""UPDATE account_lifecycles SET state='deleting',
                profile_deleted_at=transaction_timestamp(), effects=effects ||
                '{"personal_owners_erased":true,"identity_erasure":{"complete":true},
                   "discarded_progress":{"source":"private"}}'::jsonb WHERE subject=:s"""), values)
            for function in ('account_prime_billing_financial_sources',
                             'payment_prime_financial_sources', 'hypermesh_prime_financial_sources'):
                assert cx.scalar(text(f'SELECT {function}(:s,:at,NULL,1000)'), values)['complete']
            values['epoch'] = cx.scalar(text('SELECT account_financial_epoch(:s,:at,NULL,NULL)'), values)
            yield cx, values
        finally:
            transaction.rollback()


def test_source_free_completion_uses_native_proofs_and_keeps_minimal_retirement(source_free_account):
    cx, values = source_free_account
    assert cx.scalar(FINISH, values) == {'complete': True, 'epoch': values['epoch'], 'remaining': 0}
    row = cx.execute(text('SELECT state,financial_deleted_at,effects FROM account_lifecycles WHERE subject=:s'), values).one()
    assert row.state == 'deleted' and row.financial_deleted_at is not None
    assert 'discarded_progress' not in row.effects
    assert row.effects['identity_erasure'] == {'complete': True}
    assert cx.scalar(text('SELECT count(*) FROM identity_retirements WHERE subject=:s'), values) == 1
    assert cx.scalar(text('SELECT count(*) FROM account_financial_source_bindings WHERE subject=:s'), values) == 0


@pytest.mark.parametrize('change', [
    "financial_hold=true,hold_reference='preserve'",
    "profile_deleted_at=NULL",
    "effects=effects-'personal_owners_erased'",
    "effects=effects-'identity_erasure'",
    "effects=effects-'financial_inventory'",
])
def test_source_free_completion_refuses_missing_authority(source_free_account, change):
    cx, values = source_free_account
    cx.execute(text(f'UPDATE account_lifecycles SET {change} WHERE subject=:s'), values)
    with pytest.raises(DBAPIError) as error, cx.begin_nested():
        cx.scalar(FINISH, values)
    assert error.value.orig.sqlstate == '42501'
    assert cx.scalar(text('SELECT financial_deleted_at FROM account_lifecycles WHERE subject=:s'), values) is None


def test_source_free_completion_refuses_stale_epoch(source_free_account):
    cx, values = source_free_account
    with pytest.raises(DBAPIError) as error, cx.begin_nested():
        cx.scalar(FINISH, {**values, 'epoch': values['epoch'] + 1})
    assert error.value.orig.sqlstate == '40001'


def test_source_free_completion_does_not_treat_unknown_bound_source_as_empty(source_free_account):
    cx, values = source_free_account
    cx.execute(text("SELECT account_bind_financial_source(:parties,NULL,'payment','payer_mismatch_accounts','unknown-risk')"),
               {'parties': [values['s']]})
    values['epoch'] = cx.scalar(text('SELECT account_financial_epoch(:s,:at,NULL,NULL)'), values)
    result = cx.scalar(FINISH, values)
    assert result == {'complete': False, 'epoch': values['epoch'], 'remaining': 1}
    assert cx.scalar(text('SELECT state FROM account_lifecycles WHERE subject=:s'), values) == 'deleting'
