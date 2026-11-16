# Database publication preparation

The owner remains Apache-2.0, version 0.1.0. LICENSE and NOTICE are checked byte
for byte in the original wheel and rebuilt source package. The prepared consumer
image carries the same texts plus an index of legal files from every installed
runtime distribution. Exact-version upstream psycopg supplements preserve its
complete terms. Dependency versions and frozen migration files are unchanged.

CI builds a non-root Linux amd64 image named under
`ghcr.io/hyperme-sh/controlplane-db/runtime` from the qualified wheel and hashed
public runtime requirements. The context contains neither the checkout nor
migration history. Static checks reject checkout-only histories, hosted modules,
unsafe layer paths and unexpected secret matches. Offline installed-file checks
compare the shipped runtime to its declared source surface and verify notice
hashes. This is a consumer library image, not a standalone database server.

Successful main CI publishes the qualified image to `runtime:test`, pulls it back
and verifies its identity. Publication is serialized and skips stale main builds.
Exact hashes record checked bytes; consumers use the moving channel.
No Actions package or report uploads are used.

The initial history inventory covers 1,064 commit/tag/blob objects reachable from
HEAD and fetched origin branches/tags, with 231 content matches. Checkout-only
migration paths are deliberately flagged, including neutral migration files;
this is a review queue, not a claim that each match contains hosted code.
`initial-history-review.json` records coordinates only. CI produces a fresh report
and scans exported bytes and bounded wheel/ZIP members without running old code.
It does not cover deleted/unreachable or hidden refs, remote LFS bytes or external
archives. No history is rewritten or cleared for redistribution.

The retained-content ledger is in `docs/historical-distributions`. The older-image
workflow inventories tagged and untagged retained GHCR versions and scans every
Linux amd64 layer without executing old code. Missing access is reported as
unavailable, never proof of an empty registry. After publication, inventory and
layer review must succeed. Other registries, deleted versions and omitted
platforms are outside this review. Scans do not grant publication clearance.
Access, Portal and Infra #946 remain separate work.

The 236 initial secret-scanner matches are SHA-256 entries in retained migration
inventories, each verified against reachable source bytes. Exceptions bind the
whole exported blob hash, rule and start/end lines; new coordinates fail CI.
The NOTICE addition changes only legal package metadata: CI confirmed the runtime
contract digest is unchanged. Prior candidate files are retained under
`releases/qualification/snapshots/pre-notice-*`; current candidate records name
the newly built wheel bytes without changing version 0.1.0.

The [source and replacement record](../../licenses/SOURCES.md) covers the locked
psycopg runtime and its native dependencies. It does not grant publication clearance.

[Base-image review](../../licenses/BASE.md) records the installed Debian/legal
inventory. Historical source records are superseded: no source bundles are
downloaded or included in runtime images.
