# controlplane-db

Platform SQLAlchemy models, database sessions, store interfaces and Alembic
migration resources. Product runtime models remain with their service owners;
`controlplane_db.alembic.legacy_models` is a migration-only frozen registry.

## Migration resources

The package includes the frozen mixed chain through `0053_onboarding_runs`, owner
migration chains and their manifest, baseline SQL and Alembic environments. The
owner runner applies platform, events, Hypermesh, AIuditor and payment-service
chains in that order. These bundled historical resources do not transfer runtime
ownership of product tables to this library.

Inspect heads without contacting a database:

```sh
uv run python -m controlplane_db.migrations heads
uv run alembic -c alembic.ini heads
```

`controlplane_db.startup` defaults to legacy migrations. Its legacy configuration
is included inside the installed package. `CONTROLPLANE_MIGRATION_MODE=owners`
selects owner adoption and requires `DATABASE_URL`. An empty owner database also
requires explicit `CONTROLPLANE_DB_BOOTSTRAP` permission. Existing unversioned or
partially adopted databases require review. Running startup applies migrations;
deployment owners must authorize database targets and adoption separately.

Owner startup can skip an unknown revision only when its ID belongs to that
chain and required tables are present. That preserves the database version and
schema; it does not prove an older application works with a newer schema.
Tenant authorization and PostgreSQL RLS must be validated in consuming services.

## Development

Use Python 3.13 and uv 0.11.26:

```sh
bash scripts/check-package.sh
```

The frozen lock supplies dependencies. Checks run the startup guards and resource
checks from source, a fresh wheel outside the checkout and a wheel rebuilt from
the source archive. Every wheel payload file must match the source tree. Hosted
CI uses read-only contents and no database or deployment credentials.

Most checks resolve migration graphs without applying SQL. Security regression tests
use a disposable PostgreSQL 17 service in CI; locally, set `TEST_DATABASE_URL` only
to a disposable database with an administrative test role. They roll back test
objects and demonstrate the historical temporary-view attack before verifying the
repair and application/untrusted-role permissions. The package check requires
that variable and rejects skipped tests.
The active 36-case suite also includes tenant RLS, membership subject uniqueness,
AIuditor table RLS and event-index startup recovery transferred from Panopticon
`d6d9541b72db2eb3f86cb8aedc071794eba116e3`. Test fixtures create and drop separate
databases; historical migration imports resolve installed package resources.
The AIuditor table inventory explicitly includes the four newer owner tables.
Every case must pass against source, wheel and rebuilt sdist with matching JUnit
identities; CI retains these identities. Full legacy migration equivalence and
cross-service consumer integration remain separate acceptance requirements. Package version is 0.24.0.

## Share lookup security repair

Platform revision `platform_0057_share_lookup` replaces the share-token lookup
with a schema-qualified table and operator, trusted search path ending in
`pg_temp`, and no PUBLIC execution. Existing `controlplane` and `controlplane_app`
roles receive execution; no roles are created. Provision application roles before
applying this revision, or have the database owner grant execution explicitly.

The frozen mixed chain and owner baseline files remain unchanged. Legacy-mode
`controlplane_db.startup` applies the same idempotent repair after its frozen
upgrade. Direct `alembic upgrade head` on the frozen legacy chain alone does not
perform this repair; use the startup entry point for legacy deployments. Owner
mode applies the new platform revision normally. Rolling back this revision keeps
the hardened function. This package change does not repair an already deployed
monorepo database until its deployment owner adopts and applies the fix.

## Release channels

Successful main-push validation retains the validated Python wheel and source distribution and publishes
an immutable `test-<commit>` GitHub prerelease. Push a `vMAJOR.MINOR.PATCH`
tag at that tested commit to promote the exact files to a stable release,
without rebuilding. Repository visibility applies to all package assets.
Package metadata versions are preserved; these are GitHub distribution snapshots,
not automatic PyPI publication or service deployment.

Promotion requires the original Actions artifact (90-day requested retention;
organization policy may shorten it). Expired evidence fails closed: validate a
new main revision. The publisher verifies the run, source, workflow and artifact
digest independently of release metadata. Repository immutable releases must be
enabled. See the [shared release contract](https://github.com/hyperme-sh/.github/blob/7749591fccd30d46ba9b0adabe82114001c9d0de/actions/release-channel/README.md).

## AIuditor measurement and enforcement resources

The packaged owner runner includes AIuditor `0057_lab_reports` / `0058_enforcement`
and Hypermesh `0069_lab_binding` / `0070_violation_ops`. Their runtime models,
authentication and callers belong to `hyperme-sh/aiuditor` and
`hyperme-sh/hypermesh-plane`; this library supplies reviewed migration resources.
The Hypermesh tail extends the standalone `0068_environment_cert` lineage, not
the retiring monorepo's later, divergent chain. Never stamp an existing monorepo
database onto this lineage to suppress an unknown revision: reconcile and qualify
that separate database cutover first. Historical envelopes retain null provenance;
no backfill manufactures lab measurement authority.

## Test qualification and stable acceptance

GitHub `test-<commit>` prereleases are development snapshots. Their embedded
package version does not reserve a stable version. Artifact and consumer evidence
lives under `releases/qualification`; the current wheel binding is still checked
by package CI, alongside any future explicit stable candidate. Earlier test
snapshot receipts are preserved there with an explicit non-stable classification.

`releases/accepted` and `SPANOPTICON_RELEASE_BASELINE_SHA` are reserved for an
actual immutable stable GitHub release. The pinned shared guard verifies the live
release channel, stable tag source and asset digests; a test snapshot cannot
become accepted through a provenance label. No stable baseline is recorded until
that release exists. Stable publication remains closed without a valid baseline;
first stable bootstrap and coordinated release qualification remain separate.
No stable version, approval prerequisite or deployment is introduced here.
