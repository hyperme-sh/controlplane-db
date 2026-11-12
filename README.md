# Shared database primitives

This package contains provider-neutral ORM models, sessions, and generic budget
operations. Provider credentials and payment stores belong to payment-service.
Each service image receives only its own fresh migration bundle.

The frozen mixed Alembic chain through `0053_onboarding_runs` and the frozen
owner baselines remain in this repository, unchanged:

- `src/controlplane_db/alembic/`
- `src/controlplane_db/migration_chains/` (`0053_baseline.py` and `baseline.sql` for each owner)

The checkout-only runner beside those trees (`migrations.py`, `startup.py`,
and `test_retention.py`) is how qualification applies them. Hatch excludes
the histories and that runner from the runtime wheel and the sdist, so a
shared install does not receive another owner's chain. `qualification/history_tests` preserves the historical
upgrade tests and runs them from this checkout against disposable PostgreSQL.
`scripts/verify_frozen_histories.py` checks the recorded baseline digests.
Provider credential stores stay out of this package. The tests that need those
stores remain at `qualification/preserved_provider_tests` and are not part of
the shared runtime check.

Run `bash scripts/check-package.sh` with `TEST_DATABASE_URL` selecting disposable
PostgreSQL. Source, wheel, and rebuilt-sdist checks exercise current generic
budget transaction and tenant boundaries. The same command runs the historical
upgrade tests from this checkout. Those history results do not replace the
current package qualification.

For managed PostgreSQL rehearsals, bootstrap the database and grant its migrator
USAGE and CREATE on the database's public schema. Precreate the restricted
`payment_mismatch_actor` NOLOGIN role and grant membership to the payment
migrator. Runtime logins must remain separate from migration ownership.
The platform and payment upgrade tests exercise a table-owning migrator without
CREATEROLE, superuser or BYPASSRLS. Historical backfills run under transactional
table locks and restore forced RLS before commit. Retiring the old custody
schema still requires every custody table to be empty.

## Startup table requirements and CI

`migration_chains/startup-tables.json` records the tables required by the
checkout startup runner. The historical ownership and baseline inventories are
unchanged. A newer unknown payment revision can omit the seven custody tables
retired by 0064, but must retain every current requirement. Malformed and
cross-owner revisions and unversioned tables still refuse startup.

Normal package CI uses `scripts/check-package.sh --contracts` for offline source,
wheel and rebuilt-sdist contracts and mocked startup checks. The central
`controlplane-db-installed` nightly suite retains the complete PostgreSQL command
without arguments. No migration is applied as part of this startup-guard fix.

## Explicit organization memberships

`OrganizationUserMembership` adds separate `member`, `owner` and `admin` rows
for an existing tenant user and organization. Composite foreign keys require
both references to share the row's tenant. A role has no default; duplicate
user/organization/role tuples are refused. These records grant no tenant or
platform administration and do not create or link a person.

The source-only platform revision `platform_0088_org_memberships` installs the
table with forced tenant row policies and no public grants. Its downgrade locks
the table and refuses populated data, including data hidden by row policies.
User Service still needs the authenticated transactional reconciler and owner
API adoption. Runtime models alone do not install a deployed schema.

The PR checks this migration against minimal parent-table fixtures in the
existing Infra-owned disposable PostgreSQL, including cross-tenant references,
row-policy refusal and downgrade preservation. The central scheduled database
adapter also discovers these cases and retains the full older-schema comparison.
