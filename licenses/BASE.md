# DB Python base source/legal review

DB already builds both stages from the exact Python 3.13 slim Bookworm image
recorded in `base-image.json`. It is the same immutable base reviewed for API;
DB CI independently checks the four original layer identities, dpkg status bytes,
97 installed binary/source-version pairs and 115 legal-file hashes. The source
inventory is parsed from installed package records, including separate source
versions where Debian records them. Inherited legal files remain in place.

The image now carries CPython 3.13.18 source, verified by its original source hash.
CI verifies its LICENSE against the installed Python LICENSE. A single exact
upstream ssl-documentation key placeholder is added to the source scan baseline;
this is not a credential. The source bundle now contains 14 materials. Existing
psycopg native pairing and offline replacement checks remain in place.

Debian source archives are the next follow-up: the 97 binaries map to 69 exact
source-version pairs with official Debian source references, but those archives
are not yet carried in this image. No bit-identical rebuild, Debian signer-chain
validation or blanket redistribution clearance is claimed. The Debian libcrypt1
package and the wheel's bundled libcrypt are separate components with separate
source mappings.

No base upgrade, runtime dependency change, visibility change, history rewrite
or registry publication is made. Image digests identify reviewed build inputs;
TEST services remain on moving channels. Historical-content classification,
older-image review and GHCR activation remain separate work under Infra #993.
