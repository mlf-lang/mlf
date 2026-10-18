#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
compiler=$base/pgo4/candidate/bin/emlf
out=$base/current-heaps
mkdir "$out"
node - "$compiler" "$out" <<'JS'
const fs=require('fs'),crypto=require('crypto'),[compiler,out]=process.argv.slice(2);
const files=[compiler,'.mlf-build/compile3/baseline-bench/host-support','.mlf-build/compile3/measure-current-heaps.sh'];
for(const n of ['binary-trees','pidigits','n-body','fannkuch-redux','spectral-norm','fasta','mandelbrot','reverse-complement','k-nucleotide'])files.push(`benchmarks/${n}/mlf/main.emlf`);
fs.writeFileSync(out+'/context.json',JSON.stringify({boundary:'ordinary source-to-LLVM microbenchmark',order:'default/256MiB/384MiB then reversed, three repetitions',sha256:Object.fromEntries(files.map(p=>[fs.realpathSync(p),crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')]))},null,2)+'\n');
JS
for name in binary-trees pidigits n-body fannkuch-redux spectral-norm fasta mandelbrot reverse-complement k-nucleotide; do
 for run in 1 2 3; do
  order='default 268435456 402653184'
  if [[ $run == 2 ]]; then order='402653184 268435456 default'; fi
  for heap in $order; do
   stem=$out/$name-$run-$heap
   args=(/usr/bin/env -u GC_INITIAL_HEAP_SIZE)
   if [[ $heap != default ]]; then args=(/usr/bin/env "GC_INITIAL_HEAP_SIZE=$heap"); fi
   "$base/baseline-bench/host-support" measure 60 '' "$stem.ll" "$stem.stderr" "${args[@]}" "$compiler" --emit-llvm "$PWD/benchmarks/$name/mlf/main.emlf" > "$stem.json"
   cmp "$stem.ll" "$base/baseline-bench/$name/sample-1/mlf/build/program.ll"
  done
 done
done
node - "$out" <<'JS'
const fs=require('fs'),crypto=require('crypto'),out=process.argv[2],context=JSON.parse(fs.readFileSync(out+'/context.json'));
for(const [file,expected] of Object.entries(context.sha256))if(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==expected)throw Error('Changed input: '+file);
const rows=[];
for(const n of ['binary-trees','pidigits','n-body','fannkuch-redux','spectral-norm','fasta','mandelbrot','reverse-complement','k-nucleotide']){
 const variants={};for(const v of ['default','268435456','402653184']){const samples=[1,2,3].map(i=>JSON.parse(fs.readFileSync(`${out}/${n}-${i}-${v}.json`)));if(samples.some(s=>s.exit_code!==0||s.timed_out||s.interrupted))throw Error('Failed measurement');const a=samples.map(s=>s.wall_seconds).sort((a,b)=>a-b);variants[v]={samples,median:a[1],min:a[0],max:a[2],mad:a.map(x=>Math.abs(x-a[1])).sort((a,b)=>a-b)[1]};}
 rows.push({workload:n,variants});console.log(n,...Object.entries(variants).map(([k,v])=>k+': '+v.median));
}
context.inputs_unchanged=true;context.all_81_llvm_outputs_equal_baseline=true;fs.writeFileSync(out+'/context.json',JSON.stringify(context,null,2)+'\n');fs.writeFileSync(out+'/summary.json',JSON.stringify({rows},null,2)+'\n');
JS
