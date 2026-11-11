# Fresh tenant storage schema

This source-only bundle belongs to controlplane-db and is consumed only by the
Spanopticon tenant storage process. It is included in the source archive, never
in the shared runtime wheel. Consumers select the exact qualified source archive
and record its digest when extracting this bundle. Frozen histories stay intact.

Deployment owns a private schema, a restricted migration role that owns it, and
a distinct restricted runtime role. Neither role may have superuser, BYPASSRLS,
CREATEROLE, CREATEDB or replication capabilities. The runtime must not inherit
the migration role. The checked-in runner applies only to an empty schema or an
identical recorded version with the same runtime role. It runs transactionally
under a schema-specific advisory lock and refuses unknown pre-existing tables.
It never creates database roles or grants access to another owner's schema.

`tenants` is a local registry of declared tenant UUIDs used for configuration
serialization. Deployment populates it from its declared tenant configuration,
using that tenant's RLS context. The bundle inserts no tenant IDs and creates no
accounts, network grants or authority. Current tenant administration and service
key authority remain with user-service. Tenant storage runtime gets SELECT and
UPDATE(id) for row locking, but cannot insert or delete registry rows. FORCE RLS
requires the UUID to equal the current request tenant, including for updates.

`storage_settings` contains private provider configuration with one provider row
per tenant and at most one enabled provider. Its runtime privileges are limited
to SELECT, INSERT and UPDATE, with forced tenant RLS. A missing tenant context
sees no rows. Provider credentials do not leave this private owner schema except
through the storage process's existing provider calls.

The deployment command takes a private `--database-url-file`, `--schema` and
`--runtime-role`. Application startup does not invoke it. Existing populated
schemas are never adopted through CREATE IF NOT EXISTS. A future schema change
requires an explicit new migration rather than altering this version's checksum.

The CI fixture in `qualification/storage_tests/test_storage_owner.py` creates
unique NOLOGIN owner/runtime roles and a unique schema on its disposable job
PostgreSQL server. It checks idempotency, forced RLS, provider uniqueness, runtime
privilege limits and changed-bundle refusal, then drops that schema and both
roles even on failure. It uses no deployed identities or providers. Agents run
only the offline input/package contract units locally; PostgreSQL checks run in CI.
