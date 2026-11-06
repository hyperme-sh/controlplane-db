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
