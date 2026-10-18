#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
name=$1
candidate=$2
baseline=${3:-$PWD/.mlf-build/self-profile/candidate-v3/bin/emlf}
base=$PWD/.mlf-build/compile3
output=$base/$name-emission
mkdir "$output"
node - "$candidate" "$baseline" "$base/baseline-bench/host-support" "$output" "${BASH_SOURCE[0]}" <<'META'
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const [candidate,baseline,host,out,script]=process.argv.slice(2);const sha256={};
function add(p){p=fs.realpathSync(p);sha256[p]=crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');}
[candidate,baseline,host,script,'benchmarks/manifest.json'].forEach(add);
for(const w of JSON.parse(fs.readFileSync('benchmarks/manifest.json')).workloads)add(w.sources.mlf);
fs.copyFileSync(script,path.join(out,'measurement-script.sh'));
fs.writeFileSync(path.join(out,'provenance.json'),JSON.stringify({candidate:fs.realpathSync(candidate),baseline:fs.realpathSync(baseline),boundary:'fresh process: standard LLVM emission',order:[['baseline','candidate'],['candidate','baseline'],['baseline','candidate']],sha256},null,2)+'\n');
META
"$candidate" --type --expr 0 > "$output/candidate-launch.txt"
"$baseline" --type --expr 0 > "$output/baseline-launch.txt"
for workload in n-body fasta binary-trees pidigits fannkuch-redux spectral-norm mandelbrot reverse-complement k-nucleotide; do
  for run in 1 2 3; do
    order='baseline candidate'
    if [[ $run == 2 ]]; then order='candidate baseline'; fi
    for variant in $order; do
      compiler=$candidate
      if [[ $variant == baseline ]]; then compiler=$baseline; fi
      prefix=$output/$workload-$run-$variant
      "$base/baseline-bench/host-support" measure 60 '' "$prefix.ll" "$prefix.err" "$compiler" --emit-llvm "$PWD/benchmarks/$workload/mlf/main.emlf" > "$prefix.json"
      cmp "$prefix.ll" "$base/baseline-bench/$workload/sample-1/mlf/build/program.ll"
    done
  done
done
node - "$output/provenance.json" <<'VERIFY'
const fs=require('fs'),crypto=require('crypto');const p=process.argv[2],r=JSON.parse(fs.readFileSync(p));for(const [f,h] of Object.entries(r.sha256))if(crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex')!==h)throw Error('Emission input changed: '+f);r.inputs_unchanged=true;fs.writeFileSync(p,JSON.stringify(r,null,2)+'\n');
VERIFY
