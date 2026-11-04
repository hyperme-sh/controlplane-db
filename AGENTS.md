# Database package development

This package owns platform ORM models, database sessions, store interfaces and
migration runners/resources. Never import the frozen migration-only legacy model
registry in runtime services. Keep the mixed chain through 0053 and frozen owner
baselines unchanged; new revisions require owner review and database validation.

Run `bash scripts/check-package.sh` for source and installed artifact checks.
These offline tests do not establish PostgreSQL schema, RLS or upgrade acceptance.
Do not run startup or apply migrations against a deployed database as a package test.

## Package publication permission boundary

Source/package validation keeps its existing runner policy and read-only contents.
The separate `.github/workflows/release.yml` publication job is the narrow exception:
it may use `contents: write` and `actions: read` on disposable `ubuntu-24.04` workers
solely through the exact-pinned shared package publisher. It must not check out or
execute this repository's code, install its packages, or receive private dependency
or deployment credentials. This hosted publication exception does not authorize
moving secret-bearing validation to another runner group. Stable publication must
retain any configured release-admission prerequisite for the exact tag/commit.
