# Checked package releases

## Goal and boundary

A package author builds a library once. Consumers import its checked interface
and implementation without needing its source or repeating inference. The same
release works after moving the producer, bundle, consumer, or cache directory.
An unchanged imported crate is reused from a verified local store.

This is a package-manager extension to the existing `.mlfci` / `.mlfco`
boundary. It preserves independent xMLF checking and does not change inference,
the compiler's artifact wire formats, or the whole-program LLVM optimizer.
Native compilation still consumes the complete linked target. A later native
library format would need explicit exported symbols, closure/constructor and
runtime ABI contracts, target compatibility, and an optimization policy.

## User interface

Build and export a package library and its complete checked dependency closure:

```sh
mlfpkg --manifest greeting/mlf-package.json --compiler /tools/emlf \
  release ./greeting-release
```

The output directory must not already exist. The release includes `release.json`
and checked artifact pairs, including the shared Prelude when needed. It
contains no dependency source, build scripts, native code, or producer receipts.
Use the directory directly, or pack it into one deterministic `.mlfr` asset and
distribute it through GitHub Releases. The transport preserves the same checked
package boundary; there is no install hook or version solver.

Pin the SHA-256 of the exact `release.json` bytes in the consumer:

```json
{
  "dependencies": {
    "greeting": {
      "release": "../greeting-release",
      "sha256": "<64 lowercase hexadecimal digits>"
    }
  }
}
```

Paths are relative to the declaring manifest. Each dependency selects exactly
one of `path` (source), `release` plus `sha256` (local checked release), or
`github` with both digest pins (downloaded checked release). Missing,
incompatible, or damaged releases fail explicitly; switching to a source
dependency is the explicit fallback. `plan` and `lock` inspect the bundle without
executing a compiler. `--locked` pins the bundle inventory as well as source
dependencies. Native tests and `run` retain their existing behavior.

## GitHub distribution

Pack an exported directory without loading a source manifest or invoking a compiler:

```sh
mlfpkg pack ./greeting-release ./greeting.mlfr
```

The command refuses an existing asset and prints its `asset_sha256` and the
manifest's `sha256` as JSON. A `.mlfr` is a format-1 JSON envelope containing the
exact `release.json` text and checked metadata/object text for each crate. There
are no arbitrary filenames, executable permissions, links, or extraction hooks.
The importer only writes `release.json` and fixed `crates/<128-hex-key>/unit.*`
paths after validating the entire inventory. The first version is uncompressed;
large libraries therefore trade download size for a small native implementation.

After uploading that asset to an exact version tag, a consumer can declare:

```json
{
  "dependencies": {
    "greeting": {
      "github": {
        "repository": "owner/greeting",
        "tag": "v1.2.3",
        "asset": "greeting.mlfr"
      },
      "sha256": "<release.json SHA-256>",
      "asset_sha256": "<.mlfr SHA-256>"
    }
  }
}
```

Both pins are mandatory lowercase 64-digit hex values. Repository, tag, and
asset are validated literal selectors; no wildcard or `latest` lookup is used.
The GitHub CLI (`gh`) handles downloads and authentication, including private
repositories. Authenticate it with `gh auth login` or `GH_TOKEN`; credentials
never appear in the manifest or lockfile. Fetches explicitly target github.com,
independently of `GH_HOST`.

`plan`, `lock`, and builds may download an explicitly declared GitHub dependency
when its pinned asset is absent. `--offline` prohibits that access. The download
store is `<cache-dir>/.downloads/<asset_sha256>`, separate from the checked crate
store. Without `--cache-dir`, it lives in the selected build directory's `cache`.
Use a shared explicit cache for reuse across projects:

```sh
mlfpkg --cache-dir /shared/mlf-cache lock
mlfpkg --cache-dir /shared/mlf-cache --offline --locked build
```

Cache publication uses private staging and a per-asset lock. The asset digest is
checked before parsing, followed by the embedded manifest pin and artifact
digests. A failed or partial download cannot become a usable cache entry. Warm
loads recheck cached bytes; an intact asset can restore damaged extracted files
without network access. A missing or corrupt asset requires a new download and
fails in offline mode. `gh` is needed only when a download is actually required.
GitHub dependency lock rows record the locator and pins rather than a physical
cache path, so relocating the cache does not invalidate a lock. `--locked`
still rejects changed declarations and never chooses another version.

## Publishing a library

The [Checked package release workflow](../.github/workflows/package-release.yml)
is manually dispatched with an existing source tag and a library manifest path.
Use a distinct package tag such as `packages/greeting/0.1.0-macos-arm64`; an
existing compiler release or any other existing release is never modified.
The tagged checkout must contain the updated tools from this change.

The workflow fetches the published macOS ARM64 MLF 0.3.0 tool pair using the
archive and executable pins in [package-seed.env](../.github/package-seed.env).
It builds the updated manager while keeping the downloaded compiler unchanged,
exports the selected library with a locked input snapshot, and packs the result.
Declared package tests run before export.
If the library already has a lockfile it must match; otherwise the workflow
generates one before export. This first publishing workflow creates one compiler
variant per release. The package manager's transport is usable on any supported
host with `gh`, but consumers must select the exact compiler identified by the
bundle. Additional compiler variants need separate package tags or a workflow
that assembles all variants before publishing an immutable release.

Preparation and remote publication are separate scripts:

```sh
MLF_PACKAGE_MANAGER=/tools/mlfpkg tools/release/prepare-package-release.sh \
  ./greeting-release owner/greeting packages/greeting/0.1.0-macos-arm64 ./upload
tools/release/publish-package-release.sh ./upload owner/greeting \
  packages/greeting/0.1.0-macos-arm64 <source-commit-sha>
```

Preparation makes a compiler-qualified `.mlfr`, `dependency.json`, `SHA256SUMS`,
and release notes. Publication verifies these pins, confirms that the remote tag
still resolves to the expected source commit, and refuses an existing release.
It creates a draft with all assets before publishing. Only the publication job
has `contents: write`. Enable [GitHub release immutability](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)
to protect published tags and assets; consumer digest verification is always
required. Failed uploads leave the draft unpublished for inspection.

## Compiler compatibility

Release format 1 requires the exact producing compiler SHA-256 and the same
implicit-Prelude mode. Export currently uses the ordinary implicit-Prelude mode.
The compiler path and package-manager path do not affect release compatibility.
Exact compiler identity is intentionally conservative; cross-version or
cross-platform compatibility is not inferred from a version string.

## Portable representation and identities

`release.json` records format, package name/version, producing compiler digest,
Prelude mode, root crate, public module inventory, and the complete artifact
inventory with SHA-256 digests. Dependency references in the bundled interfaces
use a reserved virtual absolute prefix instead of producer filesystem locations.
These references are data, never paths to open on the importing machine.

Crates are addressed by their canonical portable metadata and object digests.
The metadata includes the exact content identities of dependencies, so an
implementation change changes all enclosing closure identities without claiming
that every downstream inference query must change. Identical transitive crates
in different bundles obtain the same local location. Distinct implementations
of the same crate identity cannot coexist silently in one linked program.

Import maps virtual references into a content-addressed local store under the
selected cache. It rewrites both interface and object headers consistently and
preserves semantic contracts and implementation fragments. The Prelude uses the
compiler's existing canonical shared location and must match the builtin
definition. Source libraries and multiple releases can therefore share it.

Only the root library's declared modules become a direct package dependency's
visible modules. Bundling transitive implementation dependencies does not grant
the consumer permission to import those dependencies directly. Existing
reexports preserve their defining identities.

## Validation, publication, and reuse

1. Verify the pinned manifest and every declared artifact digest. Reject invalid
   fields, path shapes, duplicate identities, inconsistent inventories, missing
   dependencies, cycles, and unreachable extra crates.
2. Check the compiler and Prelude compatibility contract. Copy cold imports into
   private staging and verify the pinned snapshot before decoding and independently
   checking implementation objects and their semantic boundaries. Producer cache
   receipts are never accepted as proof of local validation.
3. Materialize relocated artifacts under cache locks and publish complete results
   atomically. Locally generated receipts bind exact installed bytes and the
   validating package-manager binary; later reuse rehashes them. Corrupt local
   entries are repaired from the verified bundle.
4. Compile only local source crates, using imported metadata for inference. The
   final linker retains its independent linked-program check.

Build reports list imported releases separately from source crate queries, with
their pinned manifest digests and installed metadata locations. This makes zero
dependency inference observable without pretending imported work was performed
locally. Source and release inputs are verified again before build completion.

## Acceptance criteria

Permanent package integration cases exercise producer/cache deletion, relocation,
deterministic export, source-free downstream builds, both execution backends,
multiple releases sharing transitive crates, explicit direct-import visibility,
repeated cache reuse, local cache repair, manifest/artifact corruption, incompatible
compiler or Prelude mode, and lock invalidation. Existing source package tests
must continue to pass. Distribution cases additionally cover exact GitHub argv,
download failures, both digest pins, deterministic packing, warm/offline reuse,
extraction repair, malformed envelopes, and cache-independent lock snapshots.
Publisher checks exercise local preparation, existing releases, moved tags,
failed uploads, and damaged assets without publishing test releases.
The CI package job builds the candidate manager with the pinned published
compiler and runs the complete package suite, including the distribution cases.
No performance percentage is claimed without measurement.
