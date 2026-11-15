# Independent group ciphertext capacity

`group_migrate.py` adds the version-4 group tables to the storage baseline.
It does not alter the frozen baseline or the media tables. Migration ownership
and runtime roles remain separate; runtime grants cannot install or reset tables.

A tenant has at most 64 active or retiring group allocations. Each permanent
scope binds a canonical `set_p_` identifier, predicate, owner, source, issuer,
policy digest, creation digest and original signed allocation interval. A retired
marker cannot be reused or moved to another scope. No implicit membership exists.

A group has at most 4096 immutable encrypted wrap references, each at most 64 KiB:
64 native epochs times at most 64 recipients. References are reserved before
provider writes; uncertain writes retain their reservation. Tenant and group
row locks serialize quota changes under READ COMMITTED. All group mutations
reject other transaction isolation levels so stale snapshots cannot bypass quotas. Retirement must remove provider bytes and
references before the permanent marker can become retired. Runtime deletion of
allocation markers is forbidden. Forced RLS applies to both tables.

The CI storage contracts cover tenant isolation, scope immutability, quota,
retirement ordering, concurrent transaction locks and temporary-table shadowing.
This bundle alone does not configure a provider, install deployed schema, issue
credentials or activate group key delivery.


`group_location_migrate.py` adds version-5 provider bindings. Each group binds an
opaque provider-location digest before its first wrap reference. Bindings cannot
be changed or deleted, even after retirement. Groups already holding references
without a binding require explicit reconciliation; the runtime must not guess a
location from current configuration. Provider binding mutations also require
READ COMMITTED. No connection strings or credentials are stored in these rows.
