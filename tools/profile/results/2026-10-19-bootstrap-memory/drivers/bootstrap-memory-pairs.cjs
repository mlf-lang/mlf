#!/usr/bin/env node
// Native package builds are serial. Node only records identities, samples RSS,
// and verifies reports; all compiler/build/checking work remains native MLF.
'use strict';
const fs=require('fs'),path=require('path'),cp=require('child_process'),crypto=require('crypto');
const [seedArg,baselineArg,candidateArg,outArg]=process.argv.slice(2);
if(!outArg)throw Error('Usage: bootstrap-memory-pairs.cjs SEED BASELINE_SOURCE CANDIDATE_SOURCE FRESH_OUTPUT');
const seed=fs.realpathSync(seedArg),sources={baseline:fs.realpathSync(baselineArg),candidate:fs.realpathSync(candidateArg)},out=path.resolve(outArg);
if(fs.existsSync(out))throw Error('Use a fresh output directory');
fs.mkdirSync(out,{recursive:true});
const scripts=path.resolve(__dirname,'../release'),helper=path.join(scripts,'timed-bootstrap.sh');
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const read=p=>JSON.parse(fs.readFileSync(p));
function snapshot(dir){
 const names=cp.execFileSync('git',['-C',dir,'ls-files','-z'],{encoding:'utf8'}).split('\0').filter(Boolean);
 return {directory:dir,commit:cp.execFileSync('git',['-C',dir,'rev-parse','HEAD'],{encoding:'utf8'}).trim(),patch:cp.execFileSync('git',['-C',dir,'diff'],{encoding:'utf8'}),sha256:Object.fromEntries(names.map(p=>[p,hash(path.join(dir,p))]))};
}
const sourceIdentities=Object.fromEntries(Object.entries(sources).map(([k,v])=>[k,snapshot(v)]));
for(const [p,h] of Object.entries(sourceIdentities.baseline.sha256))if(/\.(emlf|c|h)$/.test(p)&&sourceIdentities.candidate.sha256[p]!==h)throw Error('Compiler/runtime source differs: '+p);
const tools=Object.fromEntries([__filename,...['timed-bootstrap.sh','time-command.sh','summarize-bootstrap.sh'].map(p=>path.join(scripts,p)),...['emlf','mlfpkg'].map(p=>path.join(seed,'libexec',p))].map(p=>[p,hash(p)]));
for(const p of [cp.execFileSync('/usr/bin/which',['clang'],{encoding:'utf8'}).trim(),path.join(process.env.MLF_GC_PREFIX,'lib/libgc.a')])tools[fs.realpathSync(p)]=hash(p);
const context={complete:false,sources:sourceIdentities,sha256:tools,seed:read(path.join(seed,'release.json')),sample_order:[['baseline','candidate'],['candidate','baseline'],['baseline','candidate']],sampling_interval_ms:500,rss_units:'bytes',rss_accounting:'Sum of ps RSS for the helper and its live descendants, plus the sampler RSS. Shared pages can be counted more than once. Sampled peaks are complemented by per-command time high-water RSS.',candidate_budget_bytes:5500000000,compiler_flags:'unchanged native package compiler profile and Clang O2',gc_environment:{GC_FREE_SPACE_DIVISOR:'1',GC_INITIAL_HEAP_SIZE:'unset',GC_MAXIMUM_HEAP_SIZE:'unset'}};
fs.writeFileSync(path.join(out,'context.json'),JSON.stringify(context,null,2)+'\n');
async function run(variant,sample){
 const name=`${sample}-${variant}`,dir=path.join(out,name),log=fs.openSync(path.join(out,`${name}.log`),'wx');
 const env={...process.env,MLF_COMPILER:path.join(seed,'libexec/emlf'),MLF_PACKAGE_MANAGER:path.join(seed,'libexec/mlfpkg'),GC_FREE_SPACE_DIVISOR:'1',MLF_BOOTSTRAP_MAX_RSS_BYTES:variant==='candidate'?'5500000000':'0'};
 for(const key of ['GC_INITIAL_HEAP_SIZE','GC_MAXIMUM_HEAP_SIZE','GC_PRINT_STATS','GC_ENABLE_INCREMENTAL','GC_DISABLE_INCREMENTAL','GC_MARKERS','GC_NPROCS','GITHUB_ENV','GITHUB_STEP_SUMMARY'])delete env[key];
 const child=cp.spawn(helper,[dir],{cwd:sources[variant],env,stdio:['ignore',log,log]});
 const started=process.hrtime.bigint(),csv=fs.createWriteStream(path.join(out,`${name}-rss.csv`));
 csv.write('elapsed_seconds,tree_rss_bytes,sampler_rss_bytes,processes\n');
 let peak=0,peakTree=0,peakSampler=0,maxProcesses=0,count=0,pending=null,error=null;
 function sampleTree(){
  if(pending)return;
  pending=new Promise(resolve=>cp.execFile('/bin/ps',['-axo','pid=,ppid=,rss='],{encoding:'utf8'},(err,text)=>{
   if(err){error=err;pending=null;resolve();return;}
   const rows=text.trim().split('\n').map(line=>line.trim().split(/\s+/).map(Number)),pids=new Set([child.pid]);
   for(let changed=true;changed;){changed=false;for(const [pid,parent] of rows)if(pids.has(parent)&&!pids.has(pid)){pids.add(pid);changed=true;}}
   const members=rows.filter(([pid])=>pids.has(pid));
   if(members.length){const rss=members.reduce((sum,row)=>sum+row[2]*1024,0),sampler=process.memoryUsage().rss;
    peak=Math.max(peak,rss+sampler);peakTree=Math.max(peakTree,rss);peakSampler=Math.max(peakSampler,sampler);maxProcesses=Math.max(maxProcesses,members.length);count++;
    csv.write(`${Number(process.hrtime.bigint()-started)/1e9},${rss},${sampler},${members.length}\n`);
   }
   pending=null;resolve();
  }));
 }
 const interval=setInterval(sampleTree,500);sampleTree();
 const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('close',(code,signal)=>resolve({code,signal}));});
 clearInterval(interval);if(pending)await pending;await new Promise(resolve=>csv.end(resolve));fs.closeSync(log);
 const observation={variant,sample,...code,samples:count,peak_tree_rss_bytes:peakTree,peak_sampler_rss_bytes:peakSampler,peak_tree_plus_sampler_rss_bytes:peak,max_processes:maxProcesses,helper_wall_seconds:Number(process.hrtime.bigint()-started)/1e9};
 fs.writeFileSync(path.join(out,`${name}-observation.json`),JSON.stringify(observation,null,2)+'\n');
 if(code.code!==0||code.signal||error||count<2)throw Error(`Failed build or sampler: ${name}: ${error||JSON.stringify(code)}`);
 if(variant==='candidate'&&peak>5500000000)throw Error('Candidate process-tree RSS budget exceeded');
 const build=read(path.join(dir,'build-report.json')),timing=read(path.join(dir,'timing/summary.json'));
 if(!build.complete||build.builds.some(row=>row.cached)||timing.commands.some(row=>row.exit_code!==0))throw Error('Incomplete, cached, or failed build: '+name);
 const binaries={},llvm={};
 for(const target of ['emlf','mlfpkg']){const artifact=build.builds.find(row=>row.kind===`executable mlf-compiler:${target}`);if(!artifact)throw Error('Missing target');binaries[target]=hash(path.join(dir,'bin',target));llvm[target]=hash(path.join(dir,'cache',artifact.key,'program.ll'));}
 cp.execFileSync(path.join(dir,'bin/emlf'),['--emit-llvm',path.join(sources[variant],'benchmarks/n-body/mlf/main.emlf')],{env,stdio:['ignore',fs.openSync(path.join(dir,'validation.ll'),'w'),'inherit']});
 const validation=hash(path.join(dir,'validation.ll'));
 return {...observation,wall_seconds:timing.package_manager[0].wall_seconds,mlf_seconds:timing.commands.filter(c=>c.kind==='mlf').reduce((s,c)=>s+c.wall_seconds,0),clang_seconds:timing.commands.filter(c=>c.kind==='clang').reduce((s,c)=>s+c.wall_seconds,0),peak_process_rss_bytes:Math.max(...timing.commands.map(c=>c.peak_rss_bytes)),binaries,llvm,validation};
}
function median(a){return [...a].sort((a,b)=>a-b)[Math.floor(a.length/2)];}
function stats(a){const m=median(a);return {samples:a,median:m,min:Math.min(...a),max:Math.max(...a),mad:median(a.map(x=>Math.abs(x-m)))};}
(async()=>{
 const rows=[];
 for(let sample=1;sample<=3;sample++)for(const variant of context.sample_order[sample-1]){
  console.log(`Sample ${sample}: ${variant}`);const row=await run(variant,sample);rows.push(row);
  fs.writeFileSync(path.join(out,'progress.json'),JSON.stringify(rows,null,2)+'\n');
 }
 for(const variant of ['baseline','candidate']){
  const group=rows.filter(r=>r.variant===variant);
  if(new Set(group.map(r=>JSON.stringify(r.llvm))).size!==1||new Set(group.map(r=>JSON.stringify(r.binaries))).size!==1)throw Error('Repetition output mismatch: '+variant);
 }
 if(new Set(rows.map(r=>r.validation)).size!==1)throw Error('Resulting compilers disagree on validation LLVM');
 for(const source of Object.values(context.sources))for(const [p,h] of Object.entries(source.sha256))if(hash(path.join(source.directory,p))!==h)throw Error('Frozen source changed: '+p);
 for(const [p,h] of Object.entries(tools))if(hash(p)!==h)throw Error('Tool changed: '+p);
 const statistics=Object.fromEntries(['baseline','candidate'].map(variant=>[variant,Object.fromEntries(['wall_seconds','mlf_seconds','clang_seconds','peak_process_rss_bytes','peak_tree_plus_sampler_rss_bytes'].map(key=>[key,stats(rows.filter(r=>r.variant===variant).map(r=>r[key]))]))]));
 const report={complete:true,rows,statistics,source_and_tools_unchanged:true,all_validation_llvm_equal:true};
 fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify(report,null,2)+'\n');context.complete=true;fs.writeFileSync(path.join(out,'context.json'),JSON.stringify(context,null,2)+'\n');
 console.log(JSON.stringify(statistics,null,2));
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
