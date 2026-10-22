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
Archive and distribute this directory through the release hosting of your
choice; unpack it before use. This first version deliberately keeps transport
separate from package resolution: there is no HTTP client, registry, install
hook, version solver, or implicit network access.

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
one of `path` (source) or `release` plus `sha256` (checked release). Missing,
incompatible, or damaged releases fail explicitly; switching to a source
dependency is the explicit fallback. `plan` and `lock` inspect the bundle without
executing a compiler. `--locked` pins the bundle inventory as well as source
dependencies. Native tests and `run` retain their existing behavior.

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
must continue to pass. No performance percentage is claimed without measurement.
