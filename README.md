# Shared database primitives

This package contains provider-neutral ORM models, sessions, and generic budget
operations. Provider credentials and payment stores belong to payment-service.
Each service image receives only its own fresh migration bundle.

Frozen mixed and owner migration histories are private qualification resources,
not runtime or source-distribution contents. The exact pre-cutover snapshot is
preserved in the private infra owner-compose historical archive at commit
`e2ee88b60c8d9ebd412c9626a2b0dd6955af6c10`; its 180 native historical tests pass.
The private payment history fixture additionally checks the new provider model
against those unchanged database histories. No deployed ledger was changed.

Run `bash scripts/check-package.sh` with `TEST_DATABASE_URL` selecting disposable
PostgreSQL. Source, wheel, and rebuilt-sdist checks exercise current generic
budget transaction and tenant boundaries. Historical reconciliation is a
separate private run and never substitutes for current package qualification.
