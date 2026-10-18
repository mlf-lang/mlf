#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
candidate=$1
managerDir=$2
checks=$3
./mlfpkg lock > "$checks-lock.log" 2>&1
./mlfpkg --compiler "$candidate" --build-dir "$managerDir" --timeout 21600 build --target mlfpkg > "$managerDir-build.log" 2>&1
manager=$managerDir/bin/mlfpkg
mkdir "$checks"
for group in unit packages self-host parity backends port; do
 "$manager" compiler-test "$group" --compiler "$candidate" --build-dir "$checks/compiler-tests/$group" > "$checks/$group.log" 2>&1
 printf '%s\n' "$group" >> "$checks/completed.txt"
done
