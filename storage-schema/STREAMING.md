# Private stream reservations

`stream_migrate.py` adds stream metadata to the existing private storage owner
schema. It is an explicit migration command, never a startup hook. It provisions
no tenants, policies, identities, keys, networks or media process. Runtime can
read policy and insert/update sessions; only the owner can enable a policy or
change its generation/budget. Importing the Core adapter does not install schema.

Admission serializes on the tenant row at read committed isolation. Publishers
are limited to one per room and two per tenant; readers require an active exact
publisher path and are limited to ten per room. There are at most 22 outstanding
sessions per tenant and 11 per source IP. Expiration alone does not release a slot:
the controller must confirm termination before closing the reservation.

Every session reserves 391,000 bytes per second (3 Mbit/s video plus 128 kbit/s
audio) until its finite deadline, at most one hour and never across UTC midnight.
Reservations remain charged for their day after release or restart. This
conservative ledger does not itself police packets: the media controller and
network limiter must enforce the reserved rate and account for their bounded
overshoot before activation. Row removal/retention is owner maintenance, never
runtime permission; do not remove current-day rows or active sessions.

RLS binds both tables to the tenant GUC. Session scope/token/path/generation and
byte reservation are immutable. A callback consumes the pending row once into a
unique MediaMTX session. Closing is idempotent and cannot reopen the row. A new
generation requires the old media process to be terminated before the controller
reconciles rows; policy updates alone do not kill established streams.

This supports controlplane-core#77 and Infra#1311. Both remain inactive until the
owner authority, controller and scheduled scenario are composed.
