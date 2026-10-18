#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
baseline=$1
node "$base/prepare-component-scopes.cjs"
"$base/pgo5/candidate/bin/emlf" -i bootstrap -i package -i tests -i "$base" --run "$base/ComponentScopesProbe.emlf" > "$base/component-scopes-oracle.log" 2>&1
"$base/final-manager/bin/mlfpkg" --compiler "$base/pgo5/candidate/bin/emlf" --build-dir "$base/component-scopes" --timeout 21600 build --target emlf > "$base/component-scopes-build.log" 2>&1
bash "$base/measure-emission.sh" component-scopes "$base/component-scopes/bin/emlf" "$baseline"
node "$base/summarize-emission.cjs" "$base/component-scopes-emission"
