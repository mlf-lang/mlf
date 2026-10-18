#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
base=$PWD/.mlf-build/compile3
candidate=$base/pgo7/candidate/bin/emlf
bash "$base/run-final-checks.sh" "$candidate" "$base/final-manager-v2" "$base/final-validation-v2"
bash "$base/run-final-diagnostics.sh" "$candidate" "$base/final-manager-v2/bin/mlfpkg"
printf '%s\n' 'All six native groups and final diagnostics/ordinary pairs completed.'
