#!/usr/bin/env bash
set -euo pipefail
cd /Volumes/src/mlf
base="$PWD/.mlf-build/bootstrap-memory-2026-10-19"
# All six groups are already running serially in this process. Do not overlap
# LLVM comparisons or the separate legacy timing measurement with any group.
while kill -0 57744 2>/dev/null; do sleep 5; done
node "$base/audit-verification.cjs"
node "$base/compare-generated-llvm.cjs"
export PATH="$PWD/.mlf-build/compile3/blocked:/opt/homebrew/opt/llvm/bin:$PATH"
export MLF_GC_PREFIX=/opt/homebrew/opt/bdw-gc
export MLF_COMPILER="$base/pairs/3-baseline/bin/emlf"
export MLF_PACKAGE_MANAGER="$base/pairs/3-baseline/bin/mlfpkg"
unset GC_FREE_SPACE_DIVISOR GC_INITIAL_HEAP_SIZE GC_MAXIMUM_HEAP_SIZE GC_ENABLE_INCREMENTAL GC_PRINT_STATS MLF_BOOTSTRAP_MAX_RSS_BYTES GITHUB_STEP_SUMMARY
export GITHUB_ENV="$base/legacy-export.env"
test ! -e "$GITHUB_ENV"
cd "$base/source"
/Volumes/src/mlf/tools/release/timed-bootstrap.sh "$base/legacy" > "$base/legacy.log" 2>&1
jq -e '.memory_budget.passed and .memory_budget.limit_bytes==5500000000' "$base/legacy/timing/summary.json" >/dev/null
jq -e '.gc_environment.GC_FREE_SPACE_DIVISOR=="4" and .gc_environment.GC_MAXIMUM_HEAP_SIZE==""' "$base/legacy/timing/context.json" >/dev/null
rg -q '^GC_FREE_SPACE_DIVISOR=4$' "$base/legacy-export.env"
cmp "$base/legacy/bin/emlf" "$base/pairs/3-baseline/bin/emlf"
cmp "$base/legacy/bin/mlfpkg" "$base/pairs/3-baseline/bin/mlfpkg"
node <<'JS'
const fs=require('fs'),crypto=require('crypto'),p=require('path');
const base='/Volumes/src/mlf/.mlf-build/bootstrap-memory-2026-10-19',dir=p.join(base,'legacy');
const r=JSON.parse(fs.readFileSync(p.join(dir,'build-report.json')));
if(!r.complete||r.builds.some(b=>b.cached))throw Error('Legacy build failed or cached');
const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');const rows={};
for(const target of ['emlf','mlfpkg']){const a=r.builds.find(b=>b.kind===`executable mlf-compiler:${target}`);rows[target]={binary_sha256:hash(p.join(dir,'bin',target)),llvm_sha256:hash(p.join(dir,'cache',a.key,'program.ll'))};}
if(rows.emlf.llvm_sha256!=='40d04cfb94852792ca9413f4bad06435b1936ccc0154bed5069c1e1f53b6270d'||rows.mlfpkg.llvm_sha256!=='4d690c2c80397b00673f2f218a3ce87cbbe052240d70f72d095540cdf6b5e015')throw Error('Legacy LLVM changed');
fs.writeFileSync(p.join(base,'legacy-audit.json'),JSON.stringify({complete:true,no_cache_hits:true,caller_gc_policy_unset:true,effective_divisor:4,no_maximum_heap:true,candidate_export_verified:true,outputs:rows},null,2)+'\n');
console.log('Legacy cold build passed default memory gate, exact output identity, and policy export.');
JS
