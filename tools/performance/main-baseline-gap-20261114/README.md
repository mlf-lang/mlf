# Authentic main ordinary baseline

This experimental archive records the ordinary build and five completed CLI
controls for public `mlf-lang/mlf` commit
`fc300bc9fdc389b585cbef0630fc8915d53e89c5`, tree
`386f0b41ab5f9b39fca273f3040f51d73df924a1`. This was the authentic main head
checked for this run. The compiler source is unchanged; the intended independent
experimental branch adds only this evidence directory.

**Status:** the main ordinary BUILD plus five focused CLI CONTROLS passed
independent actual-evidence review. All five commands completed with their exact
expected bytes and exit codes. This qualification is limited to the fixed source,
ordinary producer and five cases, not the full test suite or performance.

## What actually completed

- One GHC 9.14.1 ordinary `-O2` build: 18 producer commands, 141 fresh compiled
  modules (137 shared plus four host modules), 137 inferred schemes, 13 linked
  executables and 284 object/interface inputs independently checked.
- The original maintained builder performed its authentication and fresh
  canonical verification. The complete fresh literal equals the repository's
  canonical source. Independent review checked 6,235 unique file pins, 78
  toolchain files and 1,868 installed dependency files across 23 packages.
- The five CLI controls exercise version, implementation identity, arithmetic,
  Unicode output and rejection of an explicitly invalid type annotation.
  `controls/oracles.json` records all exact commands, expected statuses and byte
  oracles. The ten `controls/raw/` files are unchanged actual stdout/stderr bytes.

Cleanup-inclusive monotonic envelopes are 215,536,183,747 ns for BUILD and
7,019,030,611 ns for CONTROLS, totaling 222,555,214,358 ns against a
900,000,000,000 ns chain cap. Per-stage caps were 600 and 120 seconds. These
are setup completion durations, **not benchmark samples or a speed comparison**.
Inner elapsed fields exclude some cleanup and are retained separately.

## Reproduce the source and build recipe

Use a fresh checkout of the exact public commit above, not a moving `main` ref.
The independent source review binds all 3,876 tracked paths and 93,595,321
source bytes to the recorded tree. No earlier F25 experiment's qualification is
transferred to this baseline.

`source-provenance.json` records source-relative module/configuration pins,
inferred-scheme hashes and the canonical identity. `source-tools.json` records
the complete top-level public `tools/shared/*.py` inventory, including the
maintained builder, resource watchdog and verification helpers. Nested fixture
directories are not part of that top-level tool inventory. The tools are
already in the fixed public source tree, so they are not copied into the archive.

The 2,220,407-byte canonical file is likewise not duplicated. Use
[`bootstrap/MLF/BuiltinPreludeData.hs` at the fixed commit](https://github.com/mlf-lang/mlf/blob/fc300bc9fdc389b585cbef0630fc8915d53e89c5/bootstrap/MLF/BuiltinPreludeData.hs),
SHA256 `4b9d52fa6fa2108cc3dc1a6d04e06f18486abff4f2e682f633bddeb674c03692`.
No regenerated identity token or compiler semantic modification is introduced.

`build-recipe.json` preserves the original producer invocation, guarded command,
environment, all 18 command argument arrays in order, flags and host tool
identities. Replace logical `${SOURCE}`, `${BUILD}`, `${BUILD_GUARD}`,
`${TOOLCHAIN}`, `${TMPDIR}` and `${HOME}` placeholders with separate suitable
local paths. The unguarded maintained builder entry point is:

```sh
"$PYTHON" -B "$SOURCE/tools/shared/build.py" --bootstrap-only --optimization 2 \
  --ghc "$GHC" --cc "$CC" --build-dir "$BUILD"
```

The actual toolchain was GHC 9.14.1, Python 3.13.5 and GCC 14. Recorded flags
include `-O2`, `-fpedantic-bottoms`, `-fno-state-hack` and explicit package-database
selection. Exact versions, package identities, environment and resource limits
are in the recipe. Command arguments were changed only by local-path substitution.

`producer-pins.json` gives relative paths and exact hashes for the 13 executable
outputs, 284 object/interfaces and two same-build C objects. These are evidence
identities, not uploaded binaries. No installed packages, toolchain image or
compiled outputs are bundled, and rebuilding was not attempted for publication.

## Evidence and limits

`evidence/build-review.json` and `evidence/controls-review.json` are allowlisted
summaries of the completed reviews with original report and manifest hashes.
The final review freshly rehashed all 6,235 prior BUILD pins and verified 6,265
unique pins in total, including unchanged producer outputs, exact raw CLI bytes,
source, tools, static runtime bindings and cleanup. No inherited F25 runtime
qualification or newly executed reviewer loader probe is claimed.
`evidence/stages.json` retains actual guard completion, exit, bounds, budget and
cleanup facts. Omitted private evidence cannot be reconstructed from hashes alone.

No compiler, test, loader, target helper or benchmark was run to prepare this
archive. Unrun follow-on setup packages are not included. This baseline does
not demonstrate a performance improvement, whole-CI success, universal semantic
equivalence, GHC/native parity or native fixed-point completion. The earlier
experimental compiler branch remains separate; no candidate is promoted to main.
