# Frozen native seed bridge

This directory is a source-complete bootstrap input, not a normal source search
root. `source.tar.gz` contains legacy `.emlf` source the released 0.3.0 seed can
parse, plus the shared-profile compatibility changes and the existing narrow
async ProcessHost transition. It is never generated from `.hs` during a build.

`manifest.json` records the pinned base, exact pre-cutover checkpoint, all raw
file hashes and archive/patch digests. `compatibility.patch` is the reviewable
change from that base. The archive itself is sufficient for a shallow clone or
release source bundle; no old Git objects or mutable remote branch are needed.

`scripts/bootstrap-shared.sh` verifies and extracts these immutable bytes into
an isolated directory, builds the bridge compiler and matching manager, then
builds the final committed shared sources with them. Inputs and outputs have
disjoint paths. The ProcessHost shim is used only by the released-seed step,
never by a normal shared compiler or release runtime.

The current archive contains 171 raw source files. Its patch was applied to the
pinned base in an isolated temporary directory and every resulting file hash
matched the archive manifest. Existing-native-producer checks caught and fixed
legacy annotation spelling and missing closed recursive signatures, then hit a
strict 1 GiB resource limit during typing. This is an incomplete type check.

The bridge has not yet completed qualification. An archive's presence and
checksums do not establish a successful build, process/completion capability,
full guest tests or native fixed point. Those outcomes require source-bound
receipts from actual execution.
