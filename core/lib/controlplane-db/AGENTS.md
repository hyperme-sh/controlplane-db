# controlplane-db package context

## Ownership
Platform SQLAlchemy models, the owner-chain runner, and the frozen mixed Alembic chain. Product and operator models live in their owners (see `scripts/ownership.json`). The migration-only `alembic.legacy_models` registry is frozen; never import it in runtime services.

## Public interface
The exact public Python modules are the `controlplane_db` entries in [`scripts/import_boundaries.json`](../../../scripts/import_boundaries.json).
The contract is exact-module based, not permission to import every descendant.
Declared modules: `controlplane_db.base`, `controlplane_db.models`, `controlplane_db.session`, `controlplane_db.migrations`, `controlplane_db.startup`, `controlplane_db.payment_store`.

## Source of truth
Start with [README.md](README.md) and the package's source/tests. Repository dependency policy: [../../../AGENTS.md](../../../AGENTS.md).

New revisions belong in their owner folder under `migration_chains/`, using the
registry in that directory. The old chain through `0053_onboarding_runs` and
its baseline SQL are frozen. Test reload adoption is approved as of 2026-10-04 and selected by the VM overlay. Other live environments need an adoption decision.

## Stop reading here
Start inside this package. Follow another package's context file only when the task crosses its interface; do not sweep unrelated product docs. Shared database migrations belong in `core/lib/controlplane-db`, shared API helpers in `core/lib/controlplane-core`, and event contracts in `core/events`. Cross-package edits must be justified by the requested change.
