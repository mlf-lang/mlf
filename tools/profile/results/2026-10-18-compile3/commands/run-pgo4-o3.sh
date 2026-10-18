#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
node - "$base" <<'JS'
const fs=require('fs'),base=process.argv[2];const source=fs.readFileSync(base+'/pgo4/clang-use','utf8');
const needle="'-Werror=profile-instr-out-of-date'";
if(!source.includes(needle))throw Error('Missing profile wrapper');
fs.writeFileSync(base+'/clang-pgo4-o3',source.replace(needle,needle+" '-O3'"),{mode:0o755});
JS
"$base/final-manager/bin/mlfpkg" --compiler "$base/pgo4/candidate/bin/emlf" --clang "$base/clang-pgo4-o3" --build-dir "$base/pgo4-o3" --timeout 21600 build --target emlf > "$base/pgo4-o3-build.log" 2>&1
bash "$base/measure-emission.sh" pgo4-o3 "$base/pgo4-o3/bin/emlf" "$base/pgo4/candidate/bin/emlf"
node "$base/summarize-emission.cjs" "$base/pgo4-o3-emission"
