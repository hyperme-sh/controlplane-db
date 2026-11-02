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

These checks resolve migration graphs and inspect resources without applying SQL.
PostgreSQL upgrade/adoption, schema equivalence, RLS and consumer integration are
separate acceptance requirements. Package version remains 0.1.0.
