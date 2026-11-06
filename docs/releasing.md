# Releasing controlplane-db

This page is the release process for this repository. The package version
you build from a checkout is the `version` field in `pyproject.toml`. The
release line checked on pull requests is `release-policy.json`. The
immutable stable GitHub release, when one is recorded, is
`releases/accepted/release.json`.

Today those three say:

| Record | Value |
| --- | --- |
| `pyproject.toml` | `0.1.0` |
| `release-policy.json` `line` | `0.1` |
| `releases/accepted/release.json` | line `0.24`, version `0.24.0` |
| GitHub release | [`v0.24.0`](https://github.com/hyperme-sh/controlplane-db/releases/tag/v0.24.0) |

The accepted record binds that GitHub release to its source revision and
published asset digests. The wheel digest recorded for `v0.24.0` is
`sha256:f9944d506da43dbc0da1d0142226096c37c1073d97b726ae05a770ab8d64f4c8`.
The `0.1.0` sources in this tree are the development package. Publishing
them does not replace the `v0.24.0` assets.

The shared admission checklist is [release compatibility](release-policy.md).
The version numbers in the table above are the ones this repository
records. Spanopticon describes the manifest format in
[its release docs](https://github.com/hyperme-sh/spanopticon/blob/main/docs/releases.md).

Installing a wheel or an sdist does not connect to PostgreSQL and does not
apply migrations. Schema changes stay a deployment step: `python -m
controlplane_db.startup` or `python -m controlplane_db.migrations`.

## What main validation keeps

`.github/workflows/package.yml` (Standalone package) runs on pull requests
and on pushes to `main`. It executes `scripts/check-package.sh` and retains
the exact tested wheel and sdist as Actions artifacts. That workflow does
not create a GitHub release or a tag. Pull-request runs do not publish.

## Development snapshots

Two prerelease forms show up on the GitHub releases page.

`test-<commit>` prereleases are historical qualification snapshots. The
version embedded in the built distribution does not reserve a stable
version number. Evidence for those snapshots lives under
`releases/qualification`, with an explicit non-stable classification.
`releases/qualification/current` tracks the wheel binding the package check
last compared. A `test-<commit>` release is not the accepted stable
release.

## Coordinated test bundles

`.github/test-channel.json` sets the next test train to `0.24.0` and names
`.github/workflows/package.yml` as the workflow that produces the bytes.
When that workflow succeeds for a push to `main`,
`.github/workflows/test-bundles.yml` publishes the retained `tested-dist`
files as an immutable `0.24.0-test.N` prerelease. The publisher checks the
run, the source revision, the channel configuration, and the original
Actions artifact digest. It does not execute this repository's code and it
does not receive dependency or deployment credentials.

`0.24.0-test.N` bundles are development snapshots on the `0.24.0` train.
They leave `pyproject.toml`, dependency pins, and `releases/accepted`
unchanged. A consumer that wants a specific bundle selects that bundle's
commit and artifact digest. A later test number does not move the stable
release.

## Stable publication

A stable release is a `vMAJOR.MINOR.PATCH` tag. Pushing a `v*` tag runs
`.github/workflows/release.yml`:

1. Admission calls the pinned Spanopticon workflow
   `hyperme-sh/spanopticon/.github/workflows/component-release.yml` at
   `32c064be9fe47e230e0d48d353ada8b38a7c1644`. The workflow receives release
   line `0.1`, the tag name, and the repository variable
   `SPANOPTICON_RELEASE_BASELINE_SHA` (the full commit SHA of the accepted
   baseline).
2. When admission succeeds, the pinned publisher
   `hyperme-sh/.github/actions/release-channel` at
   `c16044a6d987d7d912d70bcd09ea731ab2b91b9e` publishes the exact artifacts
   produced by `.github/workflows/package.yml` for that commit.

Admission checks the triggering commit and the requested version. A
pull-request result that only validates configuration is not tag admission.
A failed or skipped admission job prevents the publish job from running.
The publisher checks the live release, the stable tag, and asset digests.
A `test-<commit>` snapshot or an `0.24.0-test.N` bundle does not become
the accepted release by relabeling its provenance file.

`releases/accepted` and `SPANOPTICON_RELEASE_BASELINE_SHA` refer to an
immutable stable GitHub release. The baseline commit is selected
independently of the candidate manifest. A candidate submitted as
`releases/candidate/release.json` has to match the declared package version
and the requested tag. Replacing the bytes of an already published version
is rejected. Missing baseline evidence fails admission.

Package qualification, consumer integration, and deploying the schema to a
running control plane are separate steps. A green package workflow does not
apply migrations anywhere.
