# controlplane-db package context

## Ownership
Shared SQLAlchemy models and Alembic migrations. Database schema ownership lives here; service behavior remains with its service.

## Public interface
The exact public Python modules are the `controlplane_db` entries in [`scripts/import_boundaries.json`](../../../scripts/import_boundaries.json).
The contract is exact-module based, not permission to import every descendant.

## Source of truth
Start with [README.md](README.md) and the package's source/tests. Repository dependency policy: [../../../AGENTS.md](../../../AGENTS.md).

## Stop reading here
Start inside this package. Follow another package's context file only when the task crosses its interface; do not sweep unrelated product docs. Shared database migrations belong in `core/lib/controlplane-db`, shared API helpers in `core/lib/controlplane-core`, and event contracts in `core/events`. Cross-package edits must be justified by the requested change.
