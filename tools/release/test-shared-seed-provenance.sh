#!/usr/bin/env bash
# Provenance-only checks. Does not bootstrap or qualify the seed compiler.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
test "$#" -eq 1 || { echo 'Usage: test-shared-seed-provenance.sh VERIFIED_RELEASE_BUNDLE' >&2; exit 2; }
original=$(cd -- "$1" && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/mlf-seed-provenance.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
bundle="$work/release bundle"
cp -a "$original" "$bundle"
export MLF_COMPILER="$bundle/bin/emlf" MLF_PACKAGE_MANAGER="$bundle/bin/mlfpkg"
export MLF_SHARED_BOOTSTRAP_DIR="$work/receipt"
unset MLF_SHARED_BOOTSTRAP_CONTROL_ONLY
run="$root/scripts/bootstrap-shared.sh"
reject() {
 local label=$1 expected=$2 status=0
 "$run" --verify-seed-only > "$work/$label.log" 2>&1 || status=$?
 test "$status" -eq 2
 grep -F "$expected" "$work/$label.log" >/dev/null
 jq -e '.complete == false and .phase == "verify-seed"' "$MLF_SHARED_BOOTSTRAP_DIR/bootstrap.json" >/dev/null
 printf 'PASS seed provenance rejects %s\n' "$label"
}
"$run" --verify-seed-only > "$work/valid.log" 2>&1
jq -e '.control_only == false and .compiler.kind == "official-bundle-launcher" and .manager.kind == "official-bundle-launcher"' "$MLF_SHARED_BOOTSTRAP_DIR/seed-tools.json" >/dev/null
jq -e '.complete == false and .phase == "seed-verified-only"' "$MLF_SHARED_BOOTSTRAP_DIR/bootstrap.json" >/dev/null
printf 'PASS exact official launcher binds native executable and bundle inventory\n'
MLF_COMPILER="$bundle/libexec/emlf" MLF_PACKAGE_MANAGER="$bundle/libexec/mlfpkg" "$run" --verify-seed-only > "$work/direct.log" 2>&1
jq -e '.compiler.kind == "native-executable" and .compiler.bundle != null and .manager.bundle != null' "$MLF_SHARED_BOOTSTRAP_DIR/seed-tools.json" >/dev/null
printf 'PASS direct libexec inputs bind bundle inventory\n'
# Native file format alone must not qualify an arbitrary/mixed standalone tool.
cp "$bundle/libexec/mlfpkg" "$work/standalone-manager"
MLF_PACKAGE_MANAGER="$work/standalone-manager" reject standalone-manager 'has no release-bundle provenance'
cp -a "$bundle" "$work/other bundle"
MLF_PACKAGE_MANAGER="$work/other bundle/libexec/mlfpkg" reject mixed-bundles 'same verified release bundle'

printf 'undeclared\n' > "$bundle/hidden"
reject undeclared-file 'file inventory differs'
rm "$bundle/hidden"
printf '\nmutation\n' >> "$bundle/README.md"
reject changed-bytes 'checksum mismatch'
cp "$original/README.md" "$bundle/README.md"
ln -s README.md "$bundle/hidden-link"
reject symlink 'contains symlinks'
rm "$bundle/hidden-link"
printf '%064d  ./../outside\n' 0 >> "$bundle/CHECKSUMS"
reject parent-traversal 'invalid release checksum manifest'
cp "$original/CHECKSUMS" "$bundle/CHECKSUMS"
jq '.compiler_sha256 = "incorrect"' "$bundle/release.json" > "$work/metadata"
mv "$work/metadata" "$bundle/release.json"
(cd "$bundle"; find . -type f ! -path ./CHECKSUMS | LC_ALL=C sort | while IFS= read -r path; do shasum -a 256 "$path"; done) > "$work/checksums"
mv "$work/checksums" "$bundle/CHECKSUMS"
reject inconsistent-metadata 'metadata disagrees'
cp "$original/release.json" "$bundle/release.json"
cp "$original/CHECKSUMS" "$bundle/CHECKSUMS"
printf '#!/bin/sh\ntouch "%s"\n' "$work/wrapper-executed" > "$work/untrusted-wrapper"
chmod +x "$work/untrusted-wrapper"
MLF_COMPILER="$work/untrusted-wrapper" reject unknown-wrapper 'unsupported wrapper'
test ! -e "$work/wrapper-executed"
printf 'PASS unknown wrapper was not executed\n'
printf 'No bootstrap, native compiler correctness or fixed point is qualified by these checks.\n'
