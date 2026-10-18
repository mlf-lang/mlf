#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
out=$base/link-threads
mkdir "$out"
node - "$base/backend-global-cli/toolchain.json" "$base/global-cli-bench/n-body/sample-1/mlf/build" "$out" <<'JS'
const fs=require('fs'),crypto=require('crypto'),path=require('path');const [config,input,out]=process.argv.slice(2);
const r=JSON.parse(fs.readFileSync(config));const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
fs.copyFileSync(config,out+'/toolchain.json');
fs.writeFileSync(out+'/context.json',JSON.stringify({boundary:'link-only microbenchmark; not an acceptance measurement',input,order:'default/single, single/default, alternating; seven pairs',sha256:Object.fromEntries([config,__filename,input+'/program.o',input+'/runtime.o'].filter(fs.existsSync).map(p=>[p,hash(p)]))},null,2)+'\n');
const quote=s=>"'"+s.replaceAll("'","'\\''")+"'";
const template=r.link_template;
for(const name of ['default','single']){
 const args=template.flatMap(x=>x==='<object/link arguments>'?[input+'/program.o',input+'/runtime.o','-L/opt/homebrew/Cellar/gmp/6.3.0/lib','-lgmp','-lm']: [x]);
 if(name==='single')args.push('--threads=1');
 fs.writeFileSync(out+'/'+name,'#!/bin/bash\nexec '+args.map(quote).join(' ')+' -o "$1"\n',{mode:0o755});
}
JS
for run in 1 2 3 4 5 6 7; do
 order='default single'
 if (( run % 2 == 0 )); then order='single default'; fi
 for variant in $order; do
  "$base/baseline-bench/host-support" measure 60 '' "$out/$run-$variant.stdout" "$out/$run-$variant.stderr" "$out/$variant" "$out/$run-$variant.bin" > "$out/$run-$variant.json"
  node - "$out/$run-$variant.json" <<'JS'
const fs=require('fs'),r=JSON.parse(fs.readFileSync(process.argv[2]));if(r.exit_code!==0)throw Error('link failed');
JS
 done
done
node - "$out" <<'JS'
const fs=require('fs'),crypto=require('crypto'),out=process.argv[2];const result={};
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const context=JSON.parse(fs.readFileSync(out+'/context.json'));
for(const [p,h] of Object.entries(context.sha256))if(hash(p)!==h)throw Error('Link input changed');
for(const v of ['default','single'])context.sha256[out+'/'+v]=hash(out+'/'+v);
context.inputs_unchanged=true;
context.output_sha256=Object.fromEntries(['default','single'].flatMap(v=>[1,2,3,4,5,6,7].map(i=>[`${i}-${v}.bin`,hash(`${out}/${i}-${v}.bin`)])));
context.all_outputs_identical=new Set(Object.values(context.output_sha256)).size===1;
if(!context.all_outputs_identical)throw Error('Investigate linker output differences');
fs.writeFileSync(out+'/context.json',JSON.stringify(context,null,2)+'\n');
for(const v of ['default','single']){const samples=Array.from({length:7},(_,i)=>JSON.parse(fs.readFileSync(`${out}/${i+1}-${v}.json`)));const vals=samples.map(x=>x.wall_seconds).sort((a,b)=>a-b);result[v]={samples,median:vals[3],min:vals[0],max:vals[6]};}
fs.writeFileSync(out+'/summary.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
JS
