#!/usr/bin/env bash
set -euo pipefail
scripts=$(cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
mkdir -p "$scratch/bin"
cat > "$scratch/bin/uname" <<'SH'
#!/bin/sh
printf '%s\n' "$TEST_SYSTEM"
SH
cat > "$scratch/bin/awk" <<'SH'
#!/bin/sh
printf '%s\n' "$TEST_MEMORY"
SH
chmod +x "$scratch/bin/"*
export PATH="$scratch/bin:$PATH" TEST_SYSTEM=Linux TEST_MEMORY=17179869184
check() { ( . "$scripts/qualification-jobs.sh" ) > "$scratch/result.log" 2>&1; }
unset MLF_TEST_BUILD_JOBS
check
grep -Fxq 'Qualification build jobs: 1' "$scratch/result.log"
export MLF_TEST_BUILD_JOBS=2
check
export TEST_MEMORY=7516192768
if check; then exit 1; fi
export TEST_SYSTEM=Darwin TEST_MEMORY=17179869184
if check; then exit 1; fi
export MLF_TEST_BUILD_JOBS=1
check
for value in 0 3 -1 02 invalid; do
  export MLF_TEST_BUILD_JOBS=$value
  if check; then exit 1; fi
done
printf '%s\n' '10 bounded qualification parallelism policy checks passed.'
