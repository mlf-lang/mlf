#!/bin/bash
set -euo pipefail
cd /Volumes/src/mlf
source .mlf-build/compile3/env.sh
base=$PWD/.mlf-build/compile3
candidate=$3
config=$1
out=$2
export MLF_PACKAGE_MANAGER=$4
export MLF_BENCH_STREAM_LLVM=${5:-}
export MLF_BENCH_STREAM_LINK=${6:-}
"$MLF_PACKAGE_MANAGER" --manifest tools/bench/mlf-package.json --compiler "$candidate" --build-dir "$base/final-bench-driver-v5" --timeout 21600 build --target bench > "$base/final-bench-driver-v5-build.log" 2>&1
node - "$config" "$candidate" "$out" <<'JS'
const fs=require('fs'),crypto=require('crypto'),cp=require('child_process'),path=require('path');const [config,candidate,out]=process.argv.slice(2);const files=[config+'/toolchain.json',config+'/clang-mlf',candidate,'.mlf-build/compile3/final-bench-driver-v5/bin/bench','.mlf-build/compile3/final-bench-driver-v5/fingerprint.json','.mlf-build/compile3/run-final-bench-v5.sh'];
const sha256=Object.fromEntries(files.map(p=>[fs.realpathSync(p),crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')]));
const t=JSON.parse(fs.readFileSync(config+'/toolchain.json'));
for(const [file,hash] of Object.entries(t.sha256)){if(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==hash)throw Error('Toolchain changed: '+file);sha256[file]=hash;}
function check(v){if(!v||typeof v!=='object')return;for(const [k,value] of Object.entries(v)){if(path.isAbsolute(k)&&typeof value==='string'&&/^[0-9a-f]{64}$/.test(value)){if(crypto.createHash('sha256').update(fs.readFileSync(k)).digest('hex')!==value)throw Error('Dependency changed: '+k);sha256[k]=value;}else check(value);}}
check(JSON.parse(fs.readFileSync('.mlf-build/compile3/final-bench-driver-v5/fingerprint.json')));
for(const helper of [t.machine_command[0],t.prestarted_linker].filter(Boolean)){const helperBuild=path.dirname(helper)+'/build.json';if(fs.existsSync(helperBuild))check(JSON.parse(fs.readFileSync(helperBuild)));}
const machine={os_version:cp.execFileSync('/usr/bin/sw_vers',['-productVersion'],{encoding:'utf8'}).trim(),os_build:cp.execFileSync('/usr/bin/sw_vers',['-buildVersion'],{encoding:'utf8'}).trim(),cpu:cp.execFileSync('/usr/sbin/sysctl',['-n','machdep.cpu.brand_string'],{encoding:'utf8'}).trim(),memory_bytes:cp.execFileSync('/usr/sbin/sysctl',['-n','hw.memsize'],{encoding:'utf8'}).trim()};
fs.writeFileSync(out+'-context.json',JSON.stringify({started_utc:new Date().toISOString(),machine,samples:7,limits:{compilation:3,runtime:2},build_concurrency:'one measured build at a time; stages within that build may overlap, including a fresh streaming LLVM process when enabled',environment:Object.fromEntries(['MLF_BENCH_STREAM_LINK','MLF_BENCH_STREAM_LLVM','PATH','MLF_GC_PREFIX','GC_INITIAL_HEAP_SIZE','GC_FREE_SPACE_DIVISOR','GC_MAXIMUM_HEAP_SIZE','SDKROOT','MACOSX_DEPLOYMENT_TARGET','CPATH','C_INCLUDE_PATH','LIBRARY_PATH','DYLD_LIBRARY_PATH','DYLD_INSERT_LIBRARIES','CFLAGS','CPPFLAGS','LDFLAGS'].map(k=>[k,process.env[k]||''])),sha256},null,2)+'\n');
JS
status=0
MLF_BENCH_MLF_CLANG="$config/clang-mlf" "$base/final-bench-driver-v5/bin/bench" "$candidate" "$PWD/.mlf-build/self-profile/candidate-v3/bin/emlf" "$out" 7 /opt/homebrew/Cellar/llvm/23.1.3/bin/clang-23 3 2 > "$out.log" 2>&1 || status=$?
printf '%s\n' "$status" > "$out/exit-status"
node - "$out" <<'JS'
const fs=require('fs'),crypto=require('crypto'),out=process.argv[2],r=JSON.parse(fs.readFileSync(out+'/results.json'));const p=out+'-context.json',context=JSON.parse(fs.readFileSync(p));
for(const [file,hash] of Object.entries(context.sha256))if(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==hash)throw Error('Input changed: '+file);
context.inputs_unchanged=true;context.finished_utc=new Date().toISOString();fs.writeFileSync(p,JSON.stringify(context,null,2)+'\n');
if(!['passed','failed'].includes(r.status)||r.benchmarks.length!==9||r.runs!==7||r.performance_checks.length!==18)throw Error('Incomplete benchmark run');
for(const b of r.benchmarks){const l=b.languages;console.log(b.benchmark,l.mlf.compilation.median_wall_seconds/l.c.compilation.median_wall_seconds,l.mlf.runtime.median_wall_seconds/l.c.runtime.median_wall_seconds);}
JS
