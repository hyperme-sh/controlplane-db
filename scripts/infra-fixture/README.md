# Infra-owned PostgreSQL fixture

These two files are byte-for-byte copies from FyberLabs/infra at the revision
recorded in source.json. Infra remains their owner. Changes belong there first;
update the recorded revision and hashes when importing reviewed changes.

The scoped organization-migration CI job reuses this fixture's labelled,
loopback-only disposable PostgreSQL and always runs its exact-run cleanup.
It does not run the central nightly batch or touch a deployed database.
The configured password belongs only to this isolated disposable container.
Do not invoke either script on a developer host.
