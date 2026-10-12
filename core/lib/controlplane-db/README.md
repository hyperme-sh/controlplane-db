# controlplane-db

Platform SQLAlchemy models and the existing mixed Alembic chain for the Panopticon control plane. Product models live in `hypermesh_service.models` and `aiuditor_service.models`; operator models live in `user_service.models`. The separate, frozen `alembic.legacy_models` registry preserves the mixed chain without runtime product imports. See [model ownership](../../../docs/inversion.md#wp-inv-02-model-ownership).

## Row-level security (RLS)

Tenant-scoped tables use `tenant_id` plus PostgreSQL RLS. Policies compare rows to the session GUC **`app.current_tenant_id`** (empty string = platform scope for nullable `tenant_id` rows). See [`docs/tenancy-model.md`](../../../docs/tenancy-model.md) for product vs RLS tenant semantics.

### Coverage audit (Step 7)

All ORM models that include `tenant_id` are covered by migrations that **ENABLE FORCE ROW LEVEL SECURITY** and create the four policies `tenant_isolation_{select,insert,update,delete}`:

| Table(s) | Migration |
|----------|-----------|
| `users`, `roles`, `user_password_resets`, `user_preferences`, `storage_settings`, `chat_histories_ai`, `chat_sessions_ai`, `user_passkeys`, `user_passkey_challenges`, `user_magic_links`, `stripe_settings`, `billing_records`, `subscription_plans`, `notification_banner_settings`, `sso_settings`, `branding_configuration` | `20250330_0001_initial_schema_rls` |
| `organizations`, `groups`, `user_group_memberships` | `20250330_0003_user_groups_orgs_rls` |
| `host_organization_bindings` | `20261001_0051_host_org_bindings` |
| `hypermesh_onboarding_runs` | `20261001_0053_onboarding_runs` |
| `hypermesh_host_registrations` | `20261001_0052_host_registrations` |
| `acl_casbin_rules` | `20250330_0005_acl_casbin_rls` |
| `sociacl_share_links`, `sociacl_recovery_sessions` | `20250330_0006_sociacl_shr` |
| `crypto_agent_budgets` | `20250330_0007_crypto_bdg` |
| `marketplace_listings`, `marketplace_purchases` | `20250330_0008_marketplace_rls` |
| `ai_inference_records` | `20250330_0009_ai_inference_rls` |
| `marketplace_seller_profiles`, `ai_budget_event_audit`, `ai_agent_entitlements` | `20250330_0010_marketplace_seller_ai_entitlements_rls` |
| `api_keys` | `20250330_0011_api_keys` — **no RLS**; app enforces tenant on CRUD |
| `aiuditor_connections`, `aiuditor_approvals`, `aiuditor_policies`, `aiuditor_contracts`, `aiuditor_violations`, `aiuditor_catalog` | `20260921_0025_aiuditor_rls` — also `hypermesh_leases.contract_id` |

The **`tenants`** registry table has no `tenant_id` column; it is not isolated with the same tenant-scoped policy pattern (admin / platform access only).

### Alembic

From this package root:

```bash
cd core/lib/controlplane-db && uv run alembic upgrade head
```

Configure `DATABASE_URL` for your sync driver (e.g. `postgresql+psycopg://...`) as expected by `alembic.ini`.

### RLS integration tests

Workspace package `core/tests` runs Testcontainers Postgres, migrates with Alembic, then asserts cross-tenant isolation under a restricted role. Requires Docker; set `SKIP_TESTCONTAINERS=1` to skip in CI without Docker.

```bash
cd core/tests && uv run pytest tests/integration/test_rls_tenant_isolation.py tests/integration/test_aiuditor_rls.py -m integration -v
```

## Owner migration chains (WP-INV-03)

The public `controlplane_db.migrations` runner creates owner schemas from frozen
0053 baselines, with independent version tables for platform, events, Hypermesh,
AIuditor and payment-service. See the [owner-chain runbook](../../../docs/inversion.md#wp-inv-03-owner-migration-chains).
The package contains portable owner folders in `src/controlplane_db/migration_chains`
during Phase A. Every baseline includes real database schema beyond the ORM.

`alembic.ini` retains the frozen mixed chain. Startup defaults to that chain;
the test VM overlay selects `controlplane_db.startup` owner adoption, approved
2026-10-04. Other deployments require their own adoption decision.
Never append new revisions to the mixed chain. CI checks its frozen files and
compares fresh owner-chain databases with the 0053 reference schema.

Owner migrations should be expand-only so an N-1 image keeps running on an N
schema. Nothing enforces that yet, and some existing ones are not (for example
`platform_0054_subject_scope` drops the global `keycloak_sub` unique index).
After a rollback retags an older image onto a database a newer deploy already
migrated, owners-mode startup reads each chain's version row. When that
revision is not in the image (Alembic "Can't locate revision" for the database's
current revision), startup only skips that chain when the revision can be a
later one: it uses the chain's `<chain>_<NNNN>_<slug>` id format and every table
the chain owns exists. It then logs a warning naming the chain, the database revision, and the image head, and
continues booting. The version row and schema stay as they are. This lets the
image boot; it does not prove the image works against the newer schema, so check
that no migration the rollback skips is contracting before rolling back. An unknown
revision that is not in the chain's id format (another chain's id, a malformed
id) or a schema missing the chain's tables fails startup. Revision numbers are
not monotonic along a chain (`0062_model_lifecycle` follows `0063_pending_jobs`),
so they are never compared. Absence from the image cannot prove lineage, so a
well-formed id for this chain is trusted. `scripts/check_migration_chains.py` enforces that every revision in
an owner chain uses that id format, so a later image cannot ship a revision the
guard would reject. A revision the image does contain still upgrades when it is behind
head. Any other Alembic error, and a database with no version table on a
non-empty schema, still fails startup.

Owner revisions after the baseline add current tables without changing the frozen
0053 inventory. A chain's `tables` lists its current owned tables; `baseline_tables`,
when present, lists only tables created by its frozen baseline SQL. Baseline
adoption checks the latter, then applies forward revisions. CI verifies that
inventory against the frozen SQL so later additions cannot weaken adoption checks.
Payment-service's `payment_service_0054_payout_addr` adds `host_payout_addresses`
with Base chain constraints, required proof evidence hashes and forced tenant RLS.
It adds storage only; authorized enrollment and persistence remain separate work.

Hypermesh's `hypermesh_0056_site_owner_org` adds `hypermesh_sites` with forced
tenant RLS and backfills each site's `owner_org` while the upgrade runs. A site
gets an owner only when its active bound devices belong to one organization;
every other site keeps a null owner and is logged by tenant and `site_id`. The
backfill lifts FORCE row security on `hypermesh_devices` and
`hypermesh_site_tokens` for its read and restores it in the same transaction.
It also revokes every live site token, since tokens minted before sites had
owners cannot be attributed to an organization; owners mint new ones.

### Tenant identity bindings

Platform revision `platform_0054_subject_scope` replaces the legacy global
Keycloak-subject unique index with separate platform and per-tenant constraints.
The same identity can retain its platform account and join a tenant, including
the configured network-operator membership. Existing rows, roles and subject
bindings are preserved; inactive and deleted memberships still reserve their
identity within that scope. Run the normal owner-chain migration before deploying
writers that create these memberships. A downgrade refuses to collapse identities
that now have multiple memberships; it never deletes or unbinds accounts.
