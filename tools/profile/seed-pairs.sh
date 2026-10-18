#!/usr/bin/env bash
# Compare published native seed packages on identical, clean compiler sources.
set -euo pipefail
test "$#" -eq 4 || { echo 'Usage: seed-pairs.sh OLD_PACKAGE NEW_PACKAGE SOURCE FRESH_OUTPUT' >&2; exit 64; }
scripts=$(cd -- "$(dirname -- "$0")/../release" && pwd)
old=$(cd "$1" && pwd)
new=$(cd "$2" && pwd)
source_tree=$(cd "$3" && pwd)
test ! -e "$4" || { echo 'Use a fresh output directory.' >&2; exit 1; }
mkdir -p "$4"
out=$(cd "$4" && pwd)
test -z "$(git -C "$source_tree" status --porcelain)"
for seed in "$old" "$new"; do
  test -x "$seed/libexec/emlf"
  test -x "$seed/libexec/mlfpkg"
done
export MLF_SEED_PAIR_OLD="$old" MLF_SEED_PAIR_NEW="$new"
export MLF_SEED_PAIR_SOURCE="$source_tree" MLF_SEED_PAIR_OUTPUT="$out"
export MLF_SEED_PAIR_TOOLS="$scripts" MLF_SEED_PAIR_SCRIPT="$scripts/../profile/seed-pairs.sh"
# Preserve the historical seed comparison policy even when the CI helper uses
# a more frequent collection policy for immutable, monolithic source targets.
# This diagnostic comparison intentionally retains over-budget baseline runs.
export GC_FREE_SPACE_DIVISOR=${GC_FREE_SPACE_DIVISOR:-1}
export MLF_BOOTSTRAP_MAX_RSS_BYTES=${MLF_BOOTSTRAP_MAX_RSS_BYTES:-0}
node <<'JS'
const fs=require('fs'),cp=require('child_process'),path=require('path'),crypto=require('crypto');
const e=process.env,src=e.MLF_SEED_PAIR_SOURCE,out=e.MLF_SEED_PAIR_OUTPUT;
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const files=cp.execFileSync('git',['-C',src,'ls-files','-z'],{encoding:'utf8'}).split('\0').filter(Boolean);
const source_sha256=Object.fromEntries(files.map(p=>[p,hash(path.join(src,p))]));
const tools={};
for(const p of [e.MLF_SEED_PAIR_SCRIPT,...['timed-bootstrap.sh','time-command.sh','summarize-bootstrap.sh'].map(p=>path.join(e.MLF_SEED_PAIR_TOOLS,p))])if(fs.existsSync(p))tools[p]=hash(p);
const seeds={};
for(const variant of ['old','new']){
  const dir=e['MLF_SEED_PAIR_'+variant.toUpperCase()];
  seeds[variant]={directory:dir,version:fs.readFileSync(path.join(dir,'VERSION'),'utf8').trim(),sha256:Object.fromEntries(['libexec/emlf','libexec/mlfpkg','CHECKSUMS'].map(p=>[p,hash(path.join(dir,p))]))};
}
const toolchain={};
const gmp=cp.execFileSync('pkg-config',['--variable=libdir','gmp'],{encoding:'utf8'}).trim();
const gmpLibrary=path.join(gmp,'libgmp.10.dylib');
if(fs.existsSync(gmpLibrary))toolchain[fs.realpathSync(gmpLibrary)]=hash(gmpLibrary);
for(const p of [cp.execFileSync('/usr/bin/which',['clang'],{encoding:'utf8'}).trim(),cp.execFileSync('/usr/bin/which',['pkg-config'],{encoding:'utf8'}).trim(),path.join(e.MLF_GC_PREFIX,'lib/libgc.a')]){const real=fs.realpathSync(p);toolchain[real]=hash(real);}
const context={complete:false,source_commit:cp.execFileSync('git',['-C',src,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),source_sha256,seeds,tools,toolchain,order:[['old','new'],['new','old'],['old','new']],boundary:'cold native package build of emlf and mlfpkg, including MLF emission, fresh runtime C, Clang O2 LLVM compilation and linking',environment:Object.fromEntries(['MLF_GC_PREFIX','GC_INITIAL_HEAP_SIZE','GC_FREE_SPACE_DIVISOR','GC_MAXIMUM_HEAP_SIZE','DYLD_LIBRARY_PATH','DYLD_INSERT_LIBRARIES'].map(k=>[k,e[k]||'']))};
fs.writeFileSync(path.join(out,'context.json'),JSON.stringify(context,null,2)+'\n');
JS
for seed in "$old" "$new"; do "$seed/libexec/emlf" --type --expr 0; done > "$out/launch-smoke.txt"
cd "$source_tree"
for sample in 1 2 3; do
  order='old new'
  if [ "$sample" -eq 2 ]; then order='new old'; fi
  for variant in $order; do
    seed=$old
    if [ "$variant" = new ]; then seed=$new; fi
    build="$out/$sample-$variant"
    printf 'Sample %s: %s\n' "$sample" "$variant"
    MLF_COMPILER="$seed/libexec/emlf" MLF_PACKAGE_MANAGER="$seed/libexec/mlfpkg" \
      "$scripts/timed-bootstrap.sh" "$build" > "$out/$sample-$variant.log" 2>&1
    "$build/bin/emlf" --type --expr '\x -> x' > "$build/type-smoke.txt"
    "$build/bin/emlf" --emit-llvm "$source_tree/benchmarks/n-body/mlf/main.emlf" > "$build/validation.ll"
    if [ "$sample-$variant" != 1-old ]; then cmp "$out/1-old/validation.ll" "$build/validation.ll"; fi
  done
done
node <<'JS'
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const e=process.env,out=e.MLF_SEED_PAIR_OUTPUT,src=e.MLF_SEED_PAIR_SOURCE;
const read=p=>JSON.parse(fs.readFileSync(p)),hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const context=read(path.join(out,'context.json')),rows=[];
for(const [p,expected] of Object.entries(context.source_sha256))if(hash(path.join(src,p))!==expected)throw Error('Source changed: '+p);
for(const [p,expected] of Object.entries({...context.tools,...context.toolchain}))if(hash(p)!==expected)throw Error('Tool changed: '+p);
for(const seed of Object.values(context.seeds))for(const [p,expected] of Object.entries(seed.sha256))if(hash(path.join(seed.directory,p))!==expected)throw Error('Seed changed: '+p);
for(const variant of ['old','new'])for(let sample=1;sample<=3;sample++){
  const dir=path.join(out,`${sample}-${variant}`),timing=read(path.join(dir,'timing/summary.json')),build=read(path.join(dir,'build-report.json'));
  if(!build.complete||build.builds.some(b=>b.cached)||timing.commands.some(c=>c.exit_code!==0))throw Error('Incomplete, cached or failed build: '+dir);
  const sums=phase=>timing.commands.filter(c=>c.phase===phase).reduce((sum,c)=>sum+c.wall_seconds,0);
  const llvm_sha256={};
  for(const target of ['emlf','mlfpkg']){
    const artifact=build.builds.find(b=>b.kind===`executable mlf-compiler:${target}`);
    if(!artifact)throw Error('Missing executable: '+target);
    llvm_sha256[target]=hash(path.join(dir,'cache',artifact.key,'program.ll'));
  }
  const row={variant,sample,wall_seconds:timing.package_manager[0].wall_seconds,mlf_seconds:sums('mlf'),runtime_c_seconds:sums('runtime-c'),llvm_and_link_seconds:sums('llvm-and-link'),llvm_sha256,compiler_sha256:hash(path.join(dir,'bin/emlf')),manager_sha256:hash(path.join(dir,'bin/mlfpkg'))};
  if(sample>1&&JSON.stringify(llvm_sha256)!==JSON.stringify(rows.find(r=>r.variant===variant).llvm_sha256))throw Error('LLVM differs between repetitions: '+variant);
  rows.push(row);
}
const median=a=>[...a].sort((x,y)=>x-y)[Math.floor(a.length/2)];
const stats=a=>{const m=median(a);return {samples:a,median:m,min:Math.min(...a),max:Math.max(...a),mad:median(a.map(x=>Math.abs(x-m)))}};
const statistics={};
for(const variant of ['old','new'])statistics[variant]=Object.fromEntries(['wall_seconds','mlf_seconds','runtime_c_seconds','llvm_and_link_seconds'].map(k=>[k,stats(rows.filter(r=>r.variant===variant).map(r=>r[k]))]));
const report={complete:true,rows,statistics,new_over_old:statistics.new.wall_seconds.median/statistics.old.wall_seconds.median,all_built_compilers_emit_equal_validation_llvm:true,source_inputs_unchanged:true};
fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify(report,null,2)+'\n');
context.complete=true;fs.writeFileSync(path.join(out,'context.json'),JSON.stringify(context,null,2)+'\n');
console.log(JSON.stringify({statistics,new_over_old:report.new_over_old},null,2));
JS
