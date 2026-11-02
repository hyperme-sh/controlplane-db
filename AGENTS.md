# Database package development

This package owns platform ORM models, database sessions, store interfaces and
migration runners/resources. Never import the frozen migration-only legacy model
registry in runtime services. Keep the mixed chain through 0053 and frozen owner
baselines unchanged; new revisions require owner review and database validation.

Run `bash scripts/check-package.sh` for source and installed artifact checks.
These offline tests do not establish PostgreSQL schema, RLS or upgrade acceptance.
Do not run startup or apply migrations against a deployed database as a package test.
