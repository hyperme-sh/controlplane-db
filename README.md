# controlplane-db

## Current version authority

Current development version: `0.1.0`. The services remain before the unreleased
0.24.0 milestone. Earlier 0.24/1.0 preparation and publication notes below are
historical and do not authorize those versions. Existing tags and historical
artifacts remain untouched. Development uses exact source pins and rebuilt
artifacts; no prior release is required. Version changes, tags and publication
require the owner's explicit authorization to the agent.

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
The active 62-case suite also includes tenant RLS, membership subject uniqueness,
AIuditor table RLS and event-index startup recovery transferred from Panopticon
`d6d9541b72db2eb3f86cb8aedc071794eba116e3`. Test fixtures create and drop separate
databases; historical migration imports resolve installed package resources.
The AIuditor table inventory explicitly includes the four newer owner tables.
Every case must pass against source, wheel and rebuilt sdist with matching JUnit
identities; CI retains these identities. Full legacy migration equivalence and
cross-service consumer integration remain separate acceptance requirements. Package version is 0.1.0.

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

Main validation retains its exact qualified files in Actions artifacts. It does
not create GitHub releases or tags. Historical `test-<commit>` prereleases remain
qualification evidence and do not establish an accepted stable release.

Stable publication requires an explicit `vMAJOR.MINOR.PATCH` tag, the exact
successful main validation artifact, compatible declared contracts and an actual
immutable stable baseline. The publisher independently verifies that evidence;
successful caller jobs alone cannot establish acceptance. Missing evidence and
first-stable bootstrap remain closed. Package qualification, coordinated consumer
acceptance and runtime deployment remain separate.

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

## Closure migration lineage

Owner mode includes account retirement, native financial fences and private
worker preflight resources. The platform history joins the existing share-lookup
hardening branch and the closure branch at `platform_0079_closure_merge` without
rewriting either parent or any frozen baseline/registry. Existing databases on
either branch upgrade through the same runner to one head. Producer-chain
upgrades require the current platform head first, including payment-service.

With TEST_DATABASE_URL set only to a disposable PostgreSQL server, package checks
also exercise fresh creation, both prior platform histories, retained application
data, repeat upgrades and the share-lookup ACL repair from source, installed wheel
and rebuilt sdist. Installing this package never applies migrations; runtime
migration mode and deployment activation remain explicit.

The separately merged lab/enforcement branch is retained unchanged. Hypermesh
joins that branch and the closure tail at `hypermesh_0087_closure_lab_merge`.
Native checks upgrade from either previous Hypermesh head, retain lab replay
receipts and RLS, and rerun private closure preflight over the combined schema.

Closure adoption is rebased onto the published 0.24 owner history. The candidate
contract binds the newly built development snapshot; accepted baseline files
remain unchanged. This is code/package qualification, not permission to replace
the accepted 0.24.0 artifact or bypass version/compatibility admission. This candidate restores 0.1.0 for development qualification. Closure remains default-off.
Five additional historical migration suites now run against this installed
owner: role uniqueness, gateway rename, pricing schema, AIuditor size/lab and
idle tunnel leases. Their fixture driver was transferred from controlplane-tests
943df6f and resolves the packaged frozen Alembic resources; no sibling checkout
or private fixture dependency is needed. Per-case databases are dropped and
reusable templates remain only for the disposable PostgreSQL server lifetime.

Development artifacts remain qualified under releases/qualification; test
prereleases do not establish an accepted stable baseline or reserve a version.
Stable publication retains independent live provenance validation.

Platform budget, payment-store and billing-owner regression tests also run in
the three artifact modes. These cases retain the Panopticon assertions against
real disposable PostgreSQL, including billing access through a restricted
non-superuser role. They do not contact payment providers or deployed databases.

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


### Published stable distribution

The accepted record binds the existing immutable `v0.24.0` release to its actual
GitHub release ID, source revision and published asset digests. Test snapshots
remain under `releases/qualification` and do not establish stable acceptance.
Runtime deployment and coordinated consumer acceptance remain separate.

## Closure release candidate

The closure runtime is qualified at the restored development version 0.1.0.
Packaged-byte differences do not authorize version advancement. Historical
baseline artifacts remain unchanged.
Package and disposable database checks do not establish deployed acceptance.

### Actions qualification and stable publication

Main merges and workflow completion do not publish GitHub test releases. Exact
qualification files remain in Actions artifacts with finite retention. The pinned
publisher independently verifies a real immutable stable baseline and refuses
qualification snapshots, even if a caller job reports success. Existing valid
stable records are retained; no release, version change, deployment or human
approval prerequisite is introduced by this correction.

The retained owner-chain integration suite comes from Panopticon
`d6d9541b72db2eb3f86cb8aedc071794eba116e3`. Its 18 database test functions
(20 parametrized cases) now run here from source, installed wheel and rebuilt
sdist. They compare frozen-baseline schema objects, adoption, rollback, owner
isolation, RLS, grants, and irreversible retirement behavior on disposable
PostgreSQL 17. The remaining marketplace-startup function (three cases) runs
in controlplane-tenancy #21, preserving all 19 original test functions.

Migration paths resolve from the installed package. Expected forward changes
explicitly include the reconciled lab/certification column order and hardened
share-lookup body and grants; historical baselines are unchanged. The full
schema comparison remains in place.

## License

This package is licensed under [Apache-2.0](LICENSE). Dependencies retain their
own licenses; this declaration does not relicense bundled third-party material.
