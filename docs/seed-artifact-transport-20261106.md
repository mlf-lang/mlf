# Temporary original seed artifact transport

## Reason and boundary

PR #19 CI318 failed before compiler source smoke because the pinned official
`v0.3.0` release could not be downloaded. The release and tag endpoints returned
404. The fetch script and seed pins in that candidate were identical to main;
this was not a source-test failure.

The original successful [Cross-platform release run 39712937640](https://github.com/mlf-lang/mlf/actions/runs/39712937640)
retains the exact original Linux and macOS SDK archives. They were downloaded
again on 2026-11-06 and their outer artifact ZIP hashes, inner archive hashes,
source COMMIT and compiler/manager hashes were verified against the existing
pins. No compiler is rebuilt or substituted by this transport change.

These artifacts expire on **2026-11-21 at approximately 04:41 UTC**. This is a
bounded recovery source, not a permanent bootstrap distribution. The original
archives have also been retained locally where available, but local copies are
not a CI dependency or a promise of permanent storage. A durable source must be
reviewed separately before expiry. No release or tag is created or restored.
Restoring the historical tag would make previously removed source history
reachable again; it is not part of this repair.

## Immutable identities

All sources belong to repository `mlf-lang/mlf`, repository ID `1420436874`,
run `39712937640`, source `ad299fa17296945ca0cf34d6fc4ac35dc5eb0924`.

| Platform | Artifact ID | Artifact name | Outer ZIP SHA-256 |
| --- | --- | --- | --- |
| Linux x64 | 12402192066 | release-linux-x64 | a13c1f252130ed1bd588ccdfa7b935e8009c4e19a5fd2b9017f14cbafaa829f2 |
| macOS arm64 | 12401994144 | release-macos-arm64 | 7f1846b86893ce2a984225224e265b008bd44a8674f78b63a0de673cd77848b8 |

Linux original archive SHA-256:
`ecfa16763745144c7b859354620d9fcad5bbedf4efe14972300b1ec1dacb8aeb`.
macOS original archive SHA-256:
`46d1c56d76f1c119836244318212f06fdedf59a59ccaa60c3979be1033e8965a`.
The existing compiler and manager pins remain unchanged in all five seed
configuration files. The default macOS bootstrap pin additionally records the
already verified original archive and source commit, making those checks
mandatory for the artifact path too.

## Transport requirements

The source configuration explicitly selects `github-actions-artifact`.
Ordinary release transport remains available for other pins; an unavailable or
invalid selected artifact must fail rather than silently selecting another
seed. Validate the repository, run, successful workflow and source identity,
artifact identity, name, digest and expiry. Hash the downloaded ZIP before
opening it and accept only the unique expected regular archive member. Keep the
original tarball bytes unchanged, then apply the archive, COMMIT, compiler and
manager checks before exporting tool locations.

For artifact transport, the checksum line used by the shared archive check is
derived from the independently reviewed archive pin. It is not represented as
the missing release's downloaded `SHA256SUMS`. Current Linux smoke and macOS
bootstrap, package, smoke and benchmark callers use the same original bytes.
Only Actions read access is added to the two workflows that lacked it; no
write permission, authentication grant, new publication trigger or campaign
selection change is introduced.

## Evidence and publication

The original 2026-11-05 focused native/framework results remain historical
results, not reruns after environment recovery. All 378 recorded source hashes
and 155 actually built source hashes are unchanged by this transport repair.
Their committed receipts and captured stdout remain intact; lost local build
caches are not claimed to have been recovered.

The fix is appended normally to published head
`5f77c669586e44f31d13b861d4f92130e1f55a47`. A new precursor with that sole parent
contains the reviewed repair and zero seal; a final child changes only the
anchor literal to the precursor SHA. `MAIN_BASE`, immutable historical mappings
and transported identities remain unchanged. Revalidate the new head, exact
synthetic PR merge, isolated fresh squash and a later main descendant. Prior
CI318 is retained as a failure and is not evidence for the new candidate.

GitHub CI on the newly published commit must exercise the real authenticated
artifact API and source smoke. Local exact-byte replay uses downloaded official
archives and authenticated API responses through a test adapter because this
cloud checkout has no GitHub CLI login; it does not claim to have exercised the
runner token or real CLI network access.

### Executed local controls

- All five actual seed configurations fetched and verified the downloaded
  original bytes through the API-response replay adapter.
- Eleven artifact test methods exercised 80 end-to-end scenarios, including
  78 rejections. They passed normally and with `PYTHONOPTIMIZE=1`, including
  the shell-launched production helper.
- All 11 existing release-mode checks passed with artifact transport inherited
  in the test environment; explicit fixture selection keeps the modes separate.
- The verified original Linux compiler executed all five existing suite receipt
  and focused-preparation controls successfully. This is not a full Core run.
- All 378 historical snapshot hashes and 155 actual build-source hashes match.

[Transport validation and captured controls](../tools/release/evidence/seed-artifact-20261106/validation.json)
record the actual bytes and limits. The complete sealed-history and fresh-checkout
results, followed by GitHub's new commit checks, are publication prerequisites.


## Durable transport preparation (2026-11-13)

The fetcher also supports an explicitly selected `https-mirror` of the **exact
original artifact ZIP**, not a rebuilt compiler or a repacked archive. This
prepares a migration but does not perform it: the five checked-in seed
configurations still select the original Actions artifacts. Their expiry
remains an unresolved CI/release dependency until a durable destination is
approved, populated, downloaded and verified, and the configurations are
reviewed and changed. Private backup copies are not accessible to Actions.

Mirror mode authenticates the outer ZIP using the existing reviewed
`MLF_SEED_ARTIFACT_SHA256`, then retains the unique regular member, original
tarball, source COMMIT and executable checks above. The original artifact/run
IDs remain provenance labels; mirror mode deliberately does not require their
remote metadata to survive. It does not claim to revalidate live GitHub run
metadata. Actions mode still performs every existing repository, run, source,
digest and expiry check. Neither mode automatically discovers or falls back to
another source, and a failed fetch never exports compiler/manager paths.

A mirror requires a credential-free HTTPS object URL without query parameters
or fragments. The fetcher ignores user curl configuration, requires HTTPS on
all redirects, bounds redirect count, transfer time and ZIP size, and never
opens the ZIP before checking its digest. Use a durable, repository-controlled
object location, not an expiring signed URL. An approved GitHub release asset
could be such a location, but this change creates no release, tag or public
binary and does not restore removed historical source reachability.

Activation checklist, requiring separate approval for any new public binary
publication:

1. Publish the two already verified original ZIPs unchanged to the approved
   durable destination. Do not rebuild, recompress or substitute either seed.
2. Download both objects from their actual consumer URLs and compare their
   outer ZIP and inner archive hashes with this document. Verify COMMIT and
   both executable hashes using `tools/release/fetch-seed.sh`; fetching and
   hashing need not execute either compiler.
3. In each of `.github/seed.env`, `.github/package-seed.env`,
   `.github/smoke-seed.env`, `.github/smoke-seed-linux.env` and
   `.github/benchmark-baseline-macos.env`, change only the transport selection
   to `MLF_SEED_TRANSPORT=https-mirror` and add `MLF_SEED_MIRROR_URL` with the
   reviewed platform's exact URL. Preserve all version, source and hash pins.
4. Run the fetch contracts and the repository release checks. Treat any
   further workflow dispatch or compiler qualification as a separate task;
   no expensive native campaign is required merely to preserve the bytes.

The benchmark baseline is independent of bootstrap policy. Moving bootstrap
to authenticated GHC-origin tools does **not** authorize replacing that
baseline. Mirroring its original bytes preserves the benchmark series;
selecting another compiler remains a separately reviewed series change.

Preparation validation (not activation or fresh native qualification):

- The 20 offline transport contract tests pass under normal Python and
  `PYTHONOPTIMIZE=1`; the 11 existing release-mode checks pass unchanged.
- Temporary copies of all five checked-in configurations, selecting mirror
  mode and a fixture URL, verify the retained original ZIP/tarball/COMMIT/tool
  bytes through the real shell fetcher. No compiler is executed.
- The download adapter is offline. These tests do not establish a live mirror,
  real TLS/redirect behavior, or ongoing availability of a hosting service.
