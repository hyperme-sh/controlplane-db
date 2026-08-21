# controlplane-db

Shared SQLAlchemy models and Alembic migrations for the Panopticon control plane.

## Row-level security (RLS)

Tenant-scoped tables use `tenant_id` plus PostgreSQL RLS. Policies compare rows to the session GUC **`app.current_tenant_id`** (empty string = platform scope for nullable `tenant_id` rows). See [`docs/tenancy-model.md`](../../../docs/tenancy-model.md) for product vs RLS tenant semantics.

### Coverage audit (Step 7)

All ORM models that include `tenant_id` are covered by migrations that **ENABLE FORCE ROW LEVEL SECURITY** and create the four policies `tenant_isolation_{select,insert,update,delete}`:

| Table(s) | Migration |
|----------|-----------|
| `users`, `roles`, `user_password_resets`, `user_preferences`, `storage_settings`, `chat_histories_ai`, `chat_sessions_ai`, `user_passkeys`, `user_passkey_challenges`, `user_magic_links`, `stripe_settings`, `billing_records`, `subscription_plans`, `notification_banner_settings`, `sso_settings`, `branding_configuration` | `20250330_0001_initial_schema_rls` |
| `organizations`, `groups`, `user_group_memberships` | `20250330_0003_user_groups_orgs_rls` |
| `acl_casbin_rules` | `20250330_0005_acl_casbin_rls` |
| `sociacl_share_links`, `sociacl_recovery_sessions` | `20250330_0006_sociacl_shr` |
| `crypto_agent_budgets` | `20250330_0007_crypto_bdg` |
| `marketplace_listings`, `marketplace_purchases` | `20250330_0008_marketplace_rls` |
| `ai_inference_records` | `20250330_0009_ai_inference_rls` |
| `marketplace_seller_profiles`, `ai_budget_event_audit`, `ai_agent_entitlements` | `20250330_0010_marketplace_seller_ai_entitlements_rls` |
| `api_keys` | `20250330_0011_api_keys` — **no RLS**; app enforces tenant on CRUD |

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
cd core/tests && uv run pytest tests/integration/test_rls_tenant_isolation.py -m integration -v
```
