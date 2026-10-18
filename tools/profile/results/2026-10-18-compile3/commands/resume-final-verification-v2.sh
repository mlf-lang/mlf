#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
candidate=$base/pgo7/candidate/bin/emlf
manager=$base/final-manager-v2/bin/mlfpkg
checks=$base/final-validation-v2
# The failed core launch is archived separately. Native package fingerprints
# reuse only unchanged modules compiled by this same candidate; CoreMain rebuilds.
for group in unit packages self-host parity backends port; do
 "$manager" compiler-test "$group" --compiler "$candidate" --build-dir "$checks/compiler-tests/$group" > "$checks/$group.log" 2>&1
 printf '%s\n' "$group" >> "$checks/completed.txt"
done
bash "$base/run-final-diagnostics.sh" "$candidate" "$manager"
printf '%s\n' 'All six native groups and final diagnostics/ordinary pairs completed.'
