#!/usr/bin/env bash
set -euo pipefail
. "$(dirname -- "$0")/test-events.sh" release-qualification-jobs
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
release_begin release/qualification-jobs/default
check
grep -Fxq 'Qualification build jobs: 1' "$scratch/result.log"
release_pass
release_begin release/qualification-jobs/linux-parallel
export MLF_TEST_BUILD_JOBS=2
check
release_pass
release_begin release/qualification-jobs/low-memory
export TEST_MEMORY=7516192768
if check; then false; fi
release_pass
release_begin release/qualification-jobs/darwin-parallel
export TEST_SYSTEM=Darwin TEST_MEMORY=17179869184
if check; then false; fi
release_pass
release_begin release/qualification-jobs/darwin-serial
export MLF_TEST_BUILD_JOBS=1
check
release_pass
for value in 0 3 -1 02 invalid; do
  release_begin "release/qualification-jobs/invalid/$value"
  export MLF_TEST_BUILD_JOBS=$value
  if check; then false; fi
  release_pass
done
printf '%s\n' '10 bounded qualification parallelism policy checks passed.'
