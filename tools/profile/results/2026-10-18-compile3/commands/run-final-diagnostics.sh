#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
candidate=$1
export MLF_PACKAGE_MANAGER=$2
bash tools/profile/build-stages.sh "$candidate" "$base/final-stage-profile" > "$base/final-stage-profile-build.log" 2>&1
out=$base/final-stage-profile/measurements
mkdir "$out"
node - "$base/final-stage-profile/build/fingerprint.json" "$out" <<'JS'
const fs=require('fs'),crypto=require('crypto');const [build,out]=process.argv.slice(2);
const files=[build,'.mlf-build/compile3/final-stage-profile/build/bin/stages','tools/profile/Stages.emlf','tools/profile/Force.emlf','tools/profile/runtime.c','tools/profile/build-stages.sh','.mlf-build/compile3/run-final-diagnostics.sh'];
for(const name of ['n-body','fasta','binary-trees','pidigits','fannkuch-redux','spectral-norm','mandelbrot','reverse-complement','k-nucleotide'])files.push(`benchmarks/${name}/mlf/main.emlf`);
const sha256=Object.fromEntries(files.map(p=>[fs.realpathSync(p),crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')]));
fs.writeFileSync(out+'/context.json',JSON.stringify({boundary:'forced diagnostic phases; not ordinary timings',layout:'standard',runs:3,sha256},null,2)+'\n');
JS
for run in 1 2 3; do
 for name in n-body fasta binary-trees pidigits fannkuch-redux spectral-norm mandelbrot reverse-complement k-nucleotide; do
  "$base/final-stage-profile/build/bin/stages" "$PWD/benchmarks/$name/mlf/main.emlf" "$PWD/bootstrap" standard > "$out/$name-$run.ll" 2> "$out/$name-$run.jsonl"
  cmp "$out/$name-$run.ll" "$base/baseline-bench/$name/sample-1/mlf/build/program.ll"
 done
done
node - "$out" <<'JS'
const fs=require('fs'),crypto=require('crypto'),out=process.argv[2];const p=out+'/context.json',r=JSON.parse(fs.readFileSync(p));
for(const [file,expected] of Object.entries(r.sha256))if(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==expected)throw Error('Diagnostic input changed: '+file);
r.inputs_unchanged=true;r.all_27_llvm_outputs_equal_baseline=true;fs.writeFileSync(p,JSON.stringify(r,null,2)+'\n');
JS
bash tools/profile/ordinary-pairs.sh "$PWD/.mlf-build/self-profile/baseline-emlf" "$candidate" "$PWD/.mlf-build/self-profile/baseline-source/bootstrap" "$base/baseline-bench/host-support" "$base/final-ordinary" > "$base/final-ordinary.log" 2>&1
