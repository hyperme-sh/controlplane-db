# Aggregate company egress reservations

Infra #1703 uses `wire_migrate.py` for explicit, additive installation by the DB
owner. There is no runtime DDL or deployed database change. Policies default off;
no seed purpose is accepted. The migration grants only scoped reads, reservation
inserts and the single `claimed` transition to the restricted runtime role.

All TURN and MediaMTX consumers for a tenant use one database/schema and the same
32,000,000,000-byte maximum per UTC day. The tenant row serializes insertions at
read committed isolation. Consumer, service and generation changes do not reset
the total. Reservations last at most 60 seconds and never cross a UTC boundary.
No refund, deletion or counter decrement is exposed. An ambiguous reserve or claim
burns its full amount, even when the consumer never installs its packet limit.

A packet-limit controller must claim a grant once before installing it and must
never reset or reinstall that grant's kernel quota. It must stop on expiry,
policy loss, controller loss or exhausted bytes. This SQL alone cannot police
packets. The same central ledger must be used by every region; a separately
populated regional database is not an allowed fallback. Existing stream metadata
reservations remain a separate conservative admission check, not a second wire
allowance. Direct peer traffic never enters this ledger.

CI covers two competing connections, cross-purpose totals, retained charges,
generation changes, one-use claims, role/RLS boundaries and UTC interval refusal.
No live capacity, provider activation or physical-device result is implied.
