# Private media retirement metadata

`media_migrate.py` explicitly applies an additive storage-owner schema after
validating the unchanged `001_storage.sql` baseline and restricted roles. It is
not run by service startup. No tenant, identity, key, object or grant is seeded.
Package versions and frozen migration histories are unchanged.

`storage_media_objects` permanently binds an object ID to its tenant, owner,
source and allocation. Its phase moves only from active (0), to retiring (1),
to retired (2). The deletion command becomes immutable on retirement. Runtime
cannot delete these rows or restore an earlier phase. Retired rows do not
permit object ID reuse.

`storage_media_refs` records ciphertext and wrap digests separately. References
are immutable, tenant-scoped and may be inserted only for an active object.
They may be removed only while retiring; final retirement requires no remaining
references. Insertion locks the parent object until transaction completion,
so a competing retirement waits for the reference transaction. Cross-object
references to the same digest remain visible for cleanup decisions.

The storage consumer must authenticate the source's command, lock the tenant
row before quota/reference changes, and hold the object/reference transaction
through the provider write. Cleanup must use the same serialization, preserve
shared digests, confirm provider deletion before removing references, and then
commit phase 2 exactly once. Count/byte quota is reclaimed from that committed
state, never from a timeout or a cancellation. This schema alone does not prove
provider cleanup or enforce application quota limits.

A dedicated media API/credential boundary must prevent writes through the
older generic object path from bypassing these transactions. Existing generic
storage clients are unchanged. Migration, admission/import of existing media,
service wiring and credential activation remain explicit later steps. No live
schema changes or provider calls are made by this PR. Disposable PostgreSQL
role, transition, shared-reference and contention contracts run only in CI.
