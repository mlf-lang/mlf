#!/bin/bash
set -euo pipefail
# ORIGINAL CANDIDATE FROZEN_BOOTSTRAP HOST_SUPPORT FRESH_OUTPUT_DIRECTORY
if [[ $# != 5 ]]; then echo 'ordinary-pairs.sh ORIGINAL CANDIDATE FROZEN_BOOTSTRAP HOST_SUPPORT FRESH_OUTPUT_DIRECTORY' >&2; exit 64; fi
original=$1
candidate=$2
frozen=$3
host=$4
out=$5
if [[ -e $out ]]; then echo 'Use a fresh output directory.' >&2; exit 64; fi
mkdir -p "$out"
node - "$original" "$candidate" "$frozen" "$host" "$out" "${BASH_SOURCE[0]}" <<'META'
const fs=require('fs'),path=require('path'),crypto=require('crypto'),cp=require('child_process');
const [original,candidate,frozen,host,out,script]=process.argv.slice(2);
const hashes={};
function add(file){const actual=fs.realpathSync(file);hashes[actual]=crypto.createHash('sha256').update(fs.readFileSync(actual)).digest('hex');}
function walk(dir){for(const name of fs.readdirSync(dir)){const p=path.join(dir,name);if(fs.statSync(p).isDirectory())walk(p);else add(p);}}
[original,candidate,host,script].forEach(add);walk(frozen);
const dynamic_libraries={};
if(process.platform==='darwin')for(const binary of [original,candidate,host]){
 const libraries=cp.execFileSync('/usr/bin/otool',['-L',binary],{encoding:'utf8'}).split('\n').slice(1).map(s=>s.trim().split(' (')[0]).filter(s=>path.isAbsolute(s));
 dynamic_libraries[fs.realpathSync(binary)]=libraries;
 libraries.filter(fs.existsSync).forEach(add);
}
const os_version=process.platform==='darwin'?cp.execFileSync('/usr/bin/sw_vers',['-productVersion'],{encoding:'utf8'}).trim():process.platform;
fs.writeFileSync(path.join(out,'context.json'),JSON.stringify({original:fs.realpathSync(original),candidate:fs.realpathSync(candidate),frozen:fs.realpathSync(frozen),boundary:'fresh process: complete source loading through LLVM emission',order:[['original','candidate'],['candidate','original'],['original','candidate']],os_version,dynamic_libraries,environment:Object.fromEntries(['GC_INITIAL_HEAP_SIZE','GC_FREE_SPACE_DIVISOR','GC_MAXIMUM_HEAP_SIZE','DYLD_LIBRARY_PATH','DYLD_INSERT_LIBRARIES'].map(k=>[k,process.env[k]||''])),sha256:hashes},null,2)+'\n');
META
# Warm only executable launch, never the frozen source or emitted output.
"$original" --type --expr 0 > "$out/original-launch.txt"
"$candidate" --type --expr 0 > "$out/candidate-launch.txt"
for run in 1 2 3; do
 order='original candidate'
 if [[ $run == 2 ]]; then order='candidate original'; fi
 for variant in $order; do
  compiler=$candidate
  if [[ $variant == original ]]; then compiler=$original; fi
  stem=$out/$run-$variant
  printf '%s\0' "$compiler" -i "$frozen" --emit-llvm-gc "$frozen/Main.emlf" > "$stem.argv"
  "$host" measure 1800 '' "$stem.ll" "$stem.stderr" "$compiler" -i "$frozen" --emit-llvm-gc "$frozen/Main.emlf" > "$stem.json"
  # A measurement transport returns a JSON status even when its child fails.
  node -e 'const fs=require("fs");const p=process.argv[1];const r=JSON.parse(fs.readFileSync(p));if(r.exit_code!==0||r.timed_out||r.interrupted)throw Error("ordinary compilation failed: "+p)' "$stem.json"
  if [[ $run != 1 ]]; then cmp "$stem.ll" "$out/1-$variant.ll"; fi
 done
done
node - "$out/context.json" <<'VERIFY'
const fs=require('fs'),crypto=require('crypto');const p=process.argv[2],r=JSON.parse(fs.readFileSync(p));
for(const [file,expected] of Object.entries(r.sha256))if(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==expected)throw Error('Ordinary measurement input changed: '+file);
r.inputs_unchanged=true;fs.writeFileSync(p,JSON.stringify(r,null,2)+'\n');
VERIFY
