#!/usr/bin/env bash
# Older seed managers publish MLF programs but do not know the native runner.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
directory=${1:?candidate binary directory required}
cc=${2:-${CC:-clang}}
mkdir -p "$directory"
runner="$directory/mlf-build-runner"
if [ ! -e "$runner" ]; then
  temporary=$(mktemp "$directory/.mlf-build-runner.XXXXXXXX")
  trap 'rm -f "$temporary"' EXIT
  "$cc" -O2 -std=c11 -Wall -Wextra -Werror runtime/mlf_build_runner.c -o "$temporary"
  test "$("$temporary" --protocol-version)" = 1
  mv "$temporary" "$runner"
  trap - EXIT
fi
test -x "$runner"
test "$("$runner" --protocol-version)" = 1
