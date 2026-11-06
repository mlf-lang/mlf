#!/usr/bin/env bash
# Control-only caller regression: real seed verification, no native compilation.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
test "$#" -eq 1 || { echo 'Usage: test-timed-shared-seed.sh VERIFIED_RELEASE_BUNDLE' >&2; exit 2; }
bundle=$(cd -- "$1" && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/mlf-timed-seed.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
project="$work/project"
mkdir -p "$project/tools/release" "$project/scripts" "$work/bin"
cp "$root/tools/release/timed-bootstrap.sh" "$root/tools/release/bootstrap-manager.sh" "$project/tools/release/"
printf '{}\n' > "$project/mlf-package.json"
printf '{}\n' > "$project/shared-sources.json"
cat > "$work/bin/uname" <<'STUB'
#!/bin/sh
case "$1" in -s) echo Darwin ;; -m) echo arm64 ;; *) echo 'Darwin control fixture' ;; esac
STUB
for name in sw_vers sysctl clang git; do
 printf '#!/bin/sh\necho "control fixture"\n' > "$work/bin/$name"
done
cat > "$project/tools/release/time-command.sh" <<'STUB'
#!/bin/sh
set -eu
printf '%s\n' "$2" >> "$TEST_TIMED_LABELS"
shift 2
exec "$@"
STUB
cat > "$project/tools/release/summarize-bootstrap.sh" <<'STUB'
#!/bin/sh
printf 'control-only summarized\n' > "$TEST_SUMMARIZED"
STUB
cat > "$project/scripts/bootstrap-shared.sh" <<'STUB'
#!/bin/sh
set -eu
test "$MLF_COMPILER" = "$TEST_REAL_COMPILER"
"$TEST_REAL_SHARED_BOOTSTRAP" --verify-seed-only
# Deliberately stop after actual seed verification, before any native work.
exit 73
STUB
chmod +x "$work/bin/"* "$project/tools/release/"*.sh "$project/scripts/bootstrap-shared.sh"
export TEST_TIMED_LABELS="$work/timed-labels" TEST_SUMMARIZED="$work/summarized"
export TEST_REAL_COMPILER="$bundle/bin/emlf" TEST_REAL_SHARED_BOOTSTRAP="$root/scripts/bootstrap-shared.sh"
export MLF_COMPILER="$TEST_REAL_COMPILER" MLF_PACKAGE_MANAGER="$bundle/bin/mlfpkg"
export PATH="$work/bin:$PATH"
unset MLF_SHARED_BOOTSTRAP_CONTROL_ONLY
status=0
(cd "$project"; tools/release/timed-bootstrap.sh "$work/build") > "$work/run.log" 2>&1 || status=$?
test "$status" -eq 73 || { cat "$work/run.log" >&2; exit 1; }
grep -Fx manager-bootstrap "$TEST_TIMED_LABELS" >/dev/null
test -f "$TEST_SUMMARIZED"
receipt="$work/build/manager-bootstrap/shared-bootstrap"
jq -e '.complete == false and .phase == "seed-verified-only" and .control_only == false' "$receipt/bootstrap.json" >/dev/null
jq -e --arg path "$TEST_REAL_COMPILER" '.compiler.command.path == $path and .compiler.kind == "official-bundle-launcher"' "$receipt/seed-tools.json" >/dev/null
test ! -e "$receipt/compiler.path"
printf '%s\n' 'PASS exact timed-bootstrap and bootstrap-manager callers preserve real seed provenance and enclosing timing.'
printf '%s\n' 'Darwin host probes and timing driver are control fixtures; no macOS/native bootstrap or timing performance is qualified.'
