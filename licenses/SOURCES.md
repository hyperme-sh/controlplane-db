# DB source and replacement preparation

The runtime image contains psycopg and psycopg-binary 3.3.6 (LGPL-3.0).
Certifi is a development dependency and is absent from the runtime image.
The existing GPL-3.0 supplement and original LGPL/libxcrypt notices remain.

The image carries 14 checksum-bound source/build materials under
`/usr/share/doc/controlplane-db/sources`, including the psycopg source release,
upstream build recipes, mapped native library sources and the original libcrypt
layer used for comparison, plus matching CPython source. `sources.json` binds these to the exact CPython 3.13
Linux amd64 wheel hash, installed native members and its SBOM. All 15 bundled
native libraries have source mappings. Build and final-image checks reject
changed package versions, archive bytes, native bytes, SBOM or file inventory.

The locked native wheel is byte-identical to the reviewed API 3.3.6 wheel.
Its upstream build run 35339446265/job 105581758837 names manylinux image
c163a278006f45883c117b4166b93cdc7b574b62e58292ed9e52879579841d77.
The retained manifest/config pair binds libxcrypt 4.5.2 and its source hash to
the original build layer. CI compares original and installed .text/.rodata
sections. The source fetch permits only reviewed HTTPS hosts and the exact
Quay S3 object path, and checks every download's size and SHA-256.

Recipient extraction uses `docker create IMAGE`, followed by
`docker cp CONTAINER:/usr/share/doc/controlplane-db/sources ./sources` and
`docker rm CONTAINER`. This copies sources without starting the container.
Recipients can replace installed libraries through their own derived image or
read-only mounts at `/opt/db/lib/python3.13/site-packages`. CI mounts modified
psycopg Python files, native extension files and libpq, then checks that Python
loads them with networking disabled and no service/database startup. Added
markers preserve the ABI; this proves replacement loading, not a source rebuild.

Upstream archives retain their public test vectors and example keys. Scanner
exceptions require the exact whole archive, member bytes, rule and start line
under the source-bundle image path. Runtime files and changed sources are not
exempt. RPM sources are carried unchanged; recursive RPM payload scanning,
bit-identical native rebuilds and Debian source archive bundling are not
claimed. See BASE.md for the base inventory and CPython pairing. History classification, older-image review and publication remain
separate; publication clearance remains false.
