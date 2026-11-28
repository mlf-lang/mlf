#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
output=.mlf-build/macos-dependencies

case "${1:?specify record or verify}" in
  record)
    . tools/release/test-events.sh macos-dependencies-record
    release_begin release/macos-dependencies/producer-byte-inventory
    while IFS= read -r formula; do
      prefix=$(cd "$(brew --prefix "$formula")" && pwd -P)
      # These metadata records are runner-local instead of native input bytes.
      find "$prefix" -type f ! -name INSTALL_RECEIPT.json ! -name sbom.spdx.json \
        ! -path '*/.brew/*' ! -path '*/__pycache__/*' -print0
    done < "$output/closure.txt" | xargs -0 shasum -a 256 | LC_ALL=C sort \
      > "$output/files.sha256"
    test -s "$output/files.sha256"
    release_pass
    ;;
  verify)
    . tools/release/test-events.sh macos-dependencies-verify
    producer=${2:?producer evidence directory required}
    release_begin release/macos-dependencies/formula-revision
    cmp "$output/homebrew-core-commit" "$producer/homebrew-core-commit"
    release_pass
    release_begin release/macos-dependencies/formula-closure
    cmp "$output/closure.txt" "$producer/closure.txt"
    release_pass
    release_begin release/macos-dependencies/installed-bytes
    shasum -a 256 -c "$producer/files.sha256" > "$output/verification.log"
    release_pass
    release_begin release/macos-dependencies/clang-gmp-collector
    native=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/mlf-pinned-smoke.XXXXXX")
    trap 'rm -rf -- "$native"' EXIT
    gmp=$(brew --prefix gmp)
    gc=$(brew --prefix bdw-gc)
    clang tools/release/macos-dependency-smoke.c -I"$gmp/include" -I"$gc/include" \
      "$gmp/lib/libgmp.a" "$gc/lib/libgc.a" -o "$native/pinned-smoke"
    test "$("$native/pinned-smoke")" = 42
    release_pass
    ;;
  *) exit 2 ;;
esac
