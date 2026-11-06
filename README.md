# controlplane-db

`controlplane-db` is the PostgreSQL library for the Hypermesh control plane.
Version 0.1.0 ships SQLAlchemy 2 models for platform tables, async session
helpers, small store interfaces for billing, agent budgets, and Stripe
settings, and the Alembic resources that create and upgrade the shared
schema. Product services keep their own runtime models. The frozen module
`controlplane_db.alembic.legacy_models` exists so the historical migration
environment can load the old registry.

## Why

Hosts, renters, billing, and lab measurement all write one PostgreSQL
database, with a tenant column and row-level security on nearly every table.
Putting the schema and the platform models in one library keeps those
services on the same tables, foreign keys, and migration history. A service
can upgrade the chain it owns without importing another service's ORM.

## How it works

The importable surface is small:

| Module | Role |
| --- | --- |
| `controlplane_db.base` | Shared `Base` for platform and product models |
| `controlplane_db.models` | Platform tables: tenants, users, organizations, roles, API keys, billing, marketplace, and related rows |
| `controlplane_db.session` | Async engine and session factory. `postgresql://` and `postgres://` URLs are rewritten to `postgresql+asyncpg://` |
| `controlplane_db.billing_store` | Billing rows inside the caller's transaction |
| `controlplane_db.budget_store` | Per-tenant agent budget commands |
| `controlplane_db.payment_store` | Tenant-scoped payer identity and Stripe settings |
| `controlplane_db.migrations` | Service-chain runner |
| `controlplane_db.startup` | Process entry point that applies migrations |
| `controlplane_db.alembic` | Frozen mixed chain through revision `0053_onboarding_runs` |

PostgreSQL policies read `app.current_tenant_id`. The store helpers set that
configuration for the statements they run. Set the same value on any session
you open yourself before reading or writing tenant rows.

Migrations are two histories over one database.

The frozen mixed chain lives in `controlplane_db.alembic` and stops at
`0053_onboarding_runs`. `CONTROLPLANE_MIGRATION_MODE=legacy` (the default)
upgrades that chain with the packaged `alembic.ini`, then applies the
share-lookup hardening below. Use this mode for a database that is already
on the mixed history.

`CONTROLPLANE_MIGRATION_MODE=owners` applies five chains, in order, each
with its own version table: `platform`
(`alembic_version_platform`), `events`, `hypermesh`, `aiuditor`, and
`payment_service`. The manifest is
`src/controlplane_db/migration_chains/manifest.json`. Each chain's baseline
revision is the schema that revision `0053_onboarding_runs` produced.
The migrations CLI upgrades `hypermesh`, `aiuditor`, or `payment_service`
when the same invocation also upgrades `platform`, or when `platform` is
already at the head shipped in this package. `startup` in `owners` mode
upgrades `platform` first, then the other four. Installing the package
leaves the database unchanged. Schema changes run only when a process
invokes `startup` or `python -m controlplane_db.migrations`.

An empty database is created only when `owners` mode is selected and
`CONTROLPLANE_DB_BOOTSTRAP` is `1`, `true`, or `yes`. A database that
already has chain tables and no version rows stops. A database with only
some of the five version tables stops. When a version table names a
revision this package does not contain, startup continues only if that
revision id matches the chain's `<chain>_<NNNN>_<slug>` form and the tables
that chain expects are already present. The newer schema stays in place so
the older image can boot. Whether its queries match the newer columns is a
separate check.

Platform history joins the share-lookup branch and the account-closure
branch at `platform_0079_closure_merge`. Hypermesh history joins the lab
branch and the closure branch at `hypermesh_0087_closure_lab_merge`.
Databases already on either parent upgrade to the single head through the
same runner.

`platform_0057_share_lookup` replaces share-token lookup with a
schema-qualified query, a trusted `search_path` that ends in `pg_temp`, and
no `PUBLIC` execute grant. When the roles `controlplane` and
`controlplane_app` already exist, they receive `EXECUTE`. Provision those
roles before applying the revision, or grant `EXECUTE` yourself afterward. In `owners` mode the revision runs with the
platform chain. In `legacy` mode, `python -m controlplane_db.startup`
applies the same function after the frozen upgrade. `alembic upgrade head`
on the frozen chain alone leaves the function unchanged. Rolling the
revision back keeps the hardened function.

Before an events upgrade from `events_0053_baseline`, `owners` startup
builds the event source index with `CREATE INDEX CONCURRENTLY` when
`controlplane_events` already exists. The explicit command is
`python -m controlplane_db.migrations prepare-event-source-index`.

## Practical use

Python 3.13. Runtime dependencies are SQLAlchemy 2.0.36 or newer (asyncio
extra), asyncpg 0.30 or newer, psycopg 3.2 or newer, Alembic 1.14 or newer,
and greenlet 3.1 or newer. This tree is version `0.1.0`. Install a git
revision, or work from a checkout with [uv](https://docs.astral.sh/uv/) 0.11.26:

```sh
uv venv --python 3.13
uv pip install "controlplane-db @ git+https://github.com/hyperme-sh/controlplane-db.git"
```

```sh
git clone https://github.com/hyperme-sh/controlplane-db.git
cd controlplane-db
uv sync --frozen --python 3.13
```

Open an async session. `postgresql://` is accepted. The default URL, when
`DATABASE_URL` is unset, is
`postgresql+asyncpg://controlplane_app:controlplane_app@localhost:5432/controlplane`.

```python
import asyncio
from sqlalchemy import select

from controlplane_db import async_session_maker_from_url
from controlplane_db.models import Tenant

async def list_tenants() -> None:
    maker = async_session_maker_from_url(
        "postgresql://controlplane_app:controlplane_app@localhost:5432/controlplane"
    )
    async with maker() as session:
        rows = (await session.scalars(select(Tenant))).all()
        print([row.name for row in rows])

asyncio.run(list_tenants())
```

A sync store takes a SQLAlchemy engine. The budget helper sets
`app.current_tenant_id` for the tenant you pass.

```python
import uuid
from sqlalchemy import create_engine

from controlplane_db.budget_store import list_budgets_for_tenant

engine = create_engine(
    "postgresql+psycopg://controlplane_app:controlplane_app@localhost:5432/controlplane"
)
budgets, total = list_budgets_for_tenant(engine, uuid.UUID("00000000-0000-0000-0000-000000000000"))
```

Inspect migration heads with no database connection:

```sh
uv run python -m controlplane_db.migrations heads
uv run alembic -c alembic.ini heads
```

`heads` prints JSON, one head per chain, in apply order. From an installed
copy, `python -m controlplane_db.migrations heads` uses the packaged chain
directory.

Read versions already stamped in a database:

```sh
export DATABASE_URL=postgresql://controlplane_app:controlplane_app@localhost:5432/controlplane
python -m controlplane_db.migrations current
```

Create a new database and apply every chain. Point this at a database you
intend to build. Bootstrap is the explicit permission to create schema where
none exists.

```sh
export DATABASE_URL=postgresql://controlplane_app:controlplane_app@localhost:5432/controlplane
export CONTROLPLANE_MIGRATION_MODE=owners
export CONTROLPLANE_DB_BOOTSTRAP=1
python -m controlplane_db.startup
```

Upgrade one chain on a database that already has baselines. Platform must
be at this package's platform head before `hypermesh`, `aiuditor`, or
`payment_service` will upgrade:

```sh
python -m controlplane_db.migrations upgrade --chain platform
python -m controlplane_db.migrations upgrade --chain hypermesh
```

Stamp baselines only on a mixed-chain database whose single legacy revision
is `0053_onboarding_runs` and whose baseline tables are present:

```sh
python -m controlplane_db.migrations stamp
```

A database still on the frozen history uses legacy startup. The default
legacy URL inside startup, when `DATABASE_URL` is unset, is
`postgresql+psycopg://controlplane:controlplane123@localhost:5432/controlplane`.

```sh
export DATABASE_URL=postgresql://controlplane:controlplane123@localhost:5432/controlplane
export CONTROLPLANE_MIGRATION_MODE=legacy
python -m controlplane_db.startup
```

## How Hypermesh uses it

The Hypermesh control-plane service,
[`hypermesh-service`](https://github.com/hyperme-sh/hypermesh-plane) in
`hyperme-sh/hypermesh-plane`, depends on this package. The edge forwards
`/api/v1/hypermesh`, `/api/v1/auditor`, and `/api/v1/grants` to that
service. Its container entrypoint runs `python -m hypermesh_service.schema_startup`
before it listens.

That startup takes `DATABASE_URL`, locks `controlplane-owner-migrations`,
and upgrades only the `hypermesh` chain. It runs when
`alembic_version_hypermesh` already contains exactly one revision. Platform,
events, AIuditor, and payment-service schemas stay on whatever revision
they already have. After the upgrade it ensures the marketplace tenant
through `controlplane-tenancy`.

Lease, host, and renter rows are written by `hypermesh_service`, using
models that subclass `controlplane_db.base.Base` and import
`controlplane_db.models` so foreign keys to `tenants` and `organizations`
resolve. The service sets `app.current_tenant_id` on each session.
`hypermesh_leases` stores the renter (`renter_user_id`), the host
organization (`host_org_id`), the enrolled device (`device_id`), and the
platform billing row (`billing_record_id`). Enrolled machines live in
`hypermesh_devices`, with host identity in `host_organization_bindings` and
`hypermesh_host_registrations`. A WireGuard peer per host is a row in
`hypermesh_tunnels`. Payment acceptance claims
`hypermesh_payment_callback_claims`, then moves an offered lease to `paid`
when the billing row matches. Active leases accumulate `token_count` and
`loaded_hours`. Host settlement is `hypermesh_payouts` (gross cents and net
USDC atoms). A refund sets the lease to `refunded` and removes that payout
row. Provider calls stay in the payment service. This package supplies the
tables and the platform billing identity those calls point at.

AIuditor measurement tables are the `aiuditor` chain, including
`aiuditor_0057_lab_reports` and `aiuditor_0058_enforcement`. Hypermesh
revisions `hypermesh_0069_lab_binding` and `hypermesh_0070_violation_ops`
extend the `hypermesh_0068_environment_cert` lineage. The services that
read and write those rows are
[`hyperme-sh/aiuditor`](https://github.com/hyperme-sh/aiuditor) and
[`hyperme-sh/hypermesh-plane`](https://github.com/hyperme-sh/hypermesh-plane).

`controlplane_db.billing_store`, `budget_store`, and `payment_store` are
the platform interfaces for billing rows, agent budgets, and tenant-scoped
Stripe settings. Hypermesh links a lease to `billing_records.id` and keeps
delivery and payout rows in the Hypermesh tables above.

## Develop and test

From a checkout, with uv 0.11.26 and Python 3.13:

```sh
export TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres
bash scripts/check-package.sh
```

`TEST_DATABASE_URL` must name a disposable PostgreSQL server and an
administrative role. The script refuses to run without it. Checks lock the
dependency set, run the test suite from the source tree, build a wheel,
install that wheel outside the checkout, rebuild a wheel from the sdist,
and run the same suite again. Tests create and drop databases on that
server. CI uses PostgreSQL 17 and the same script
(`.github/workflows/package.yml`).

Most migration tests resolve the graph without applying it to a shared
database. The disposable-server cases cover tenant row-level security, the
share-lookup function, chain adoption, and upgrade from the published
heads. They do not talk to a deployed control-plane database or a payment
provider.

## Release and versioning

This checkout's package version is `0.1.0`. The recorded stable GitHub
release is [`v0.24.0`](https://github.com/hyperme-sh/controlplane-db/releases/tag/v0.24.0),
bound in `releases/accepted`. Successful validation on `main` can publish
immutable `0.24.0-test.N` prerelease bundles. Those bundles, and the older
`test-<commit>` prereleases, are development snapshots. The mechanics,
admission inputs, and the difference between qualification records and the
accepted release are in [docs/releasing.md](docs/releasing.md).

## License

This package is licensed under [Apache-2.0](LICENSE). Dependencies retain
their own licenses. This declaration does not relicense bundled third-party
material.

## TEST financial retention

Platform revision `platform_0081_test_authority` installs private erasure
authority for both fresh databases and databases already on
`platform_0080_test_retention`. The original consumed migration stays unchanged.
Upgrade removes legacy non-owner capability table and column grants; reapply a
reviewed worker role plan and remove old direct financial writes before startup.


Platform `platform_0080_test_retention` and payment
`payment_service_0081_test_gc` add a private, database-bound TEST policy. They
leave production retention clocks and preservation/settlement rules in place.
No database becomes TEST merely by applying the migrations or setting an HTTP
field, tenant GUC, or process environment variable.

The database administrator registers the **selected TEST database** explicitly:

```sql
INSERT INTO public.account_test_data_policy
  (singleton, database_oid, database_name, enabled)
SELECT true, oid, datname, true
FROM pg_catalog.pg_database WHERE datname = current_database();
```

The private user-service worker also requires `FASTAPI_ENV=test` and
`ACCOUNT_CLOSURE_RETENTION=none`. Startup refuses a disagreement with the
protected database policy. A copied policy does not enable another database:
its database OID, name and PostgreSQL cluster identifier must match. The mode table is private; the
worker locks the selected policy through a definer function rather than receiving
permission to enable it. Disabling the policy waits for an in-flight erasure
transaction's shared row lock.

`controlplane_db.test_retention.purge_test_finances` runs only within the private
coordinator's existing transaction and native original-closure/inventory proof.
It deletes recent, unsettled TEST payer records despite accepted financial holds.
The worker runs this stage before personal anonymization removes payer aliases.
Exact tenant-bound billing/order/tax/lease/payout relationships and actual foreign
keys determine dependent rows; arbitrary audit text does not establish ownership.
Tenant/company billing records are preserved through retired creators. Unknown
owners, cross-tenant dependencies, cycles and oversized batches remain pending.
Live-provider rows are outside TEST erasure.

No trigger or foreign-key constraint is disabled. Exact locked row images receive
private, transaction-bound delete capabilities. Only existing financial deletion
guards recognize them; ordinary production guards and AFTER-trigger inventory
invalidation remain active. A deferred constraint forbids capabilities surviving
commit. The caller records committed counts and rechecks fresh native owner
proofs before marking the account complete. No provider calls, refunds, transfers
or settlements occur in this helper. Physical model/storage cleanup still needs
its own owner acknowledgments.

PUBLIC receives no access to mode, capabilities or original guard definitions,
and no execution of the private functions. The private TEST coordinator receives
SELECT on financial sources and native bindings, plus execution of
`account_lock_test_financial_sources`, `account_stage_test_delete`,
`account_delete_test_financial_row`, `account_clear_test_delete_capabilities`
and `account_reconcile_test_financial_bindings`. It has no financial source or
binding writes and no capability-table access. Production workers need only the
read-only mode check in addition to their existing authority.

Database-owned routines read actual rows under native locks, repeat original
payer/tenant and sandbox ancestry checks, and bind each capability to its
subject, closure time, row image and current transaction. Dependent rows need an
authorized native parent and an actual FK or explicit tenant-bound relationship.
Even a compromised coordinator cannot insert capabilities or delete financial
rows directly. The definer refuses remaining children before deletion, including
CASCADE relationships to unknown physical owners. Source bindings are reconciled
against live rows inside the same native authority. All new routines pin catalog
lookup and put temporary schemas last. The public service rejects access to the
private support state. Non-superuser worker startup rejects stale direct financial
or capability privileges.

Downgrade restores the exact saved native guard definitions. Disable TEST mode
first, restore the payment-owner guards, then remove platform TEST support;
removing the platform helper while owner guards still reference it is refused.
No deployed database or provider is changed by package qualification.

Stripe-backed billing requires independently recorded provider mode. Additive
`platform_0082_stripe_mode` stores nullable `stripe_livemode` without expanding the
legacy ORM mapping. Trusted payment adapters record only actual validated provider
responses or original billing provenance; NULL remains unknown. Once recorded,
the native trigger forbids changing or clearing the mode. TEST erasure rejects
live or unproven Stripe IDs/metadata regardless of the TEST database marker.
No provider IDs, process settings or caller metadata are guessed as sandbox.
Legacy databases without the native column retain their existing payment writes.

Existing Stripe-bearing rows without independently verified provider mode remain
ineligible for TEST erasure. The payment owner may record actual validated
provider observations; no migration guesses or backfills their sandbox status.

Forward `platform_0083_stripe_scope` also requires original same-tenant billing
provenance for Stripe-bearing leases, including exact saved session matching.
Missing, live, unproven or mismatched links cannot authorize a lease root.
Stripe classification traverses canonical metadata values and nested object/array
keys. TEST workers require this current native provenance installation before
claiming work; an older installed backend cannot silently keep a weaker guard.
