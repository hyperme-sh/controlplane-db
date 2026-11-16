# Retained database history

The content ledger records 231 flagged coordinates from the reachable history
inventory at fd6403dc8b94e3d81c21dc3cad57c914f76f319b. Each entry binds the Git
blob, historical path and SHA-256 of its contents to a conservative disposition.

Payment-owner migrations are retained payment schema. Other migration chains,
the frozen mixed Alembic chain and its configuration are retained mixed schema.
Checkout-only migration/startup helpers are recorded separately from the old
payment store. These classifications describe retained code, not permission to
publish hosted implementation. None grants publication clearance.

CI compares the fresh reachable findings with this exact inventory, verifies
blob and archive-member hashes, and rejects additions, removals, duplicates or
changed bytes. The secret scan remains a separate check. History and frozen
migrations are unchanged; runtime wheel/image exclusions remain enforced.

Scope is fetched origin branches, tags and HEAD. Deleted/unreachable refs,
hidden server refs, external archives and remote LFS data are outside this
inventory. Older registry-image review and GHCR activation remain separate.
No source archives are fetched or added to runtime images by this check.
