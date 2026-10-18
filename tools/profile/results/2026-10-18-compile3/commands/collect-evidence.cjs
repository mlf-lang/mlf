const fs=require('fs'),path=require('path'),crypto=require('crypto'),cp=require('child_process'),zlib=require('zlib');
const root=process.cwd(),base=path.join(root,'.mlf-build/compile3');
const [benchArg,configArg,candidateArg,checksArg,phaseArg,ordinaryArg]=process.argv.slice(2);
if(!ordinaryArg)throw Error('collect-evidence BENCH CONFIG CANDIDATE CHECKS PHASE_PROFILE ORDINARY');
const bench=path.resolve(benchArg),config=path.resolve(configArg),candidate=path.resolve(candidateArg),checks=path.resolve(checksArg),phase=path.resolve(phaseArg),ordinary=path.resolve(ordinaryArg);
const destination=path.join(root,'tools/profile/results/2026-10-18-compile3');
if(fs.existsSync(destination))throw Error('Evidence destination must be new');
const out=destination+'.incomplete';
if(fs.existsSync(out))throw Error('Evidence destination must be new');
fs.mkdirSync(out,{recursive:true});
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const read=p=>JSON.parse(fs.readFileSync(p));
const artifacts=[];
function save(from,to,gzip=false){
 if(!fs.existsSync(from))return false;
 const input=fs.readFileSync(from),dest=path.join(out,to);
 fs.mkdirSync(path.dirname(dest),{recursive:true});
 fs.writeFileSync(dest,gzip?zlib.gzipSync(input):input);
 artifacts.push({source:path.resolve(from),stored:to,source_sha256:crypto.createHash('sha256').update(input).digest('hex'),stored_sha256:hash(dest),gzip});return true;
}
const pgo=path.dirname(path.dirname(path.dirname(candidate)));
const digest=hash(candidate),r=read(bench+'/results.json');
if(!['passed','failed'].includes(r.status)||r.runs!==7||r.benchmarks.length!==9||r.performance_checks.length!==18||r.limits.compilation!==3||r.limits.runtime!==2)throw Error('Incomplete final gate');
const benchContext=read(bench+'-context.json');if(!benchContext.inputs_unchanged)throw Error('Final benchmark context incomplete');
for(const [file,expected] of Object.entries(benchContext.sha256))if(hash(file)!==expected)throw Error('Final benchmark context changed: '+file);
if(r.fingerprints[candidate]!==digest)throw Error('Benchmark compiler mismatch');
save(bench+'/results.json','bench-final.json');save(bench+'/exit-status','bench-exit-status.txt');save(bench+'.log','bench.log.gz',true);save(bench+'-context.json','bench-context.json');
const outputHashes={};
function retainBenchRaw(dir){
 for(const item of fs.readdirSync(dir)){
  const file=dir+'/'+item,relative=path.relative(bench,file),stat=fs.statSync(file);
  if(stat.isDirectory())retainBenchRaw(file);
  else if(stat.isFile()){
   if(/\.(json|jsonl|argv|spec)$/.test(item)&&file!==bench+'/results.json')save(file,'bench-raw/'+relative);
   if(item==='stdout'||item==='stdin')outputHashes[relative]={sha256:hash(file),bytes:stat.size};
  }
 }
}
retainBenchRaw(bench);
fs.writeFileSync(out+'/bench-output-sha256.json',JSON.stringify(outputHashes,null,2)+'\n');
for(const [file,expected] of Object.entries(r.fingerprints))if(hash(path.resolve(file))!==expected)throw Error('Final benchmark input changed: '+file);
function stats(values){const sorted=[...values].sort((a,b)=>a-b),m=sorted[Math.floor(sorted.length/2)];return {samples:values,median:m,min:sorted[0],max:sorted.at(-1),mad:[...values].map(v=>Math.abs(v-m)).sort((a,b)=>a-b)[Math.floor(values.length/2)]};}
const workloadRows=r.benchmarks.map(b=>{
 const l=b.languages,compile=l.mlf.compilation.median_wall_seconds/l.c.compilation.median_wall_seconds,runtime=l.mlf.runtime.median_wall_seconds/l.c.runtime.median_wall_seconds;
 const reference=hash(base+'/baseline-bench/'+b.benchmark+'/sample-1/mlf/build/program.ll');
 if(b.binary_samples.length!==7||b.binary_samples.some(s=>s.mlf.artifacts_sha256['program.ll']!==reference||s.baseline.artifacts_sha256['program.ll']!==reference))throw Error('LLVM mismatch: '+b.benchmark);
 const intervals=l.mlf.compilation.samples.map(s=>{
  const p=Object.fromEntries(s.stages.map(p=>[p.phase,p]));
  const ordered=[...s.stages].sort((a,b)=>a.started_seconds-b.started_seconds);
  let union=0,end=0;
  for(const stage of ordered){union+=Math.max(0,stage.finished_seconds-Math.max(end,stage.started_seconds));end=Math.max(end,stage.finished_seconds);}
  const parallel=s.stages.reduce((sum,stage)=>sum+stage.wall_seconds,0)-union;
  const tail=p.llvm.finished_seconds-Math.max(p.llvm.started_seconds,p.frontend.finished_seconds);
  return {total:s.wall_seconds,frontend:p.frontend.wall_seconds,runtime_c:p.runtime.wall_seconds,llvm:p.llvm.wall_seconds,llvm_after_frontend:tail,link:p.link.wall_seconds,link_after_objects:p.link.finished_seconds-Math.max(p.llvm.finished_seconds,p.runtime.finished_seconds),link_process_started_before_objects_finished:p.link.started_seconds<Math.max(p.llvm.finished_seconds,p.runtime.finished_seconds),overlap:parallel,other_overhead:s.wall_seconds-union,critical_branch:p.runtime.finished_seconds>p.llvm.finished_seconds?'runtime C':'frontend + LLVM',llvm_process_started_before_frontend_finished:p.llvm.started_seconds<p.frontend.finished_seconds};
 });
 return {workload:b.benchmark,compile_over_c:compile,runtime_over_c:runtime,compile_pass:compile<=3,runtime_pass:runtime<=2,worst_compile_over_c:l.mlf.compilation.max_wall_seconds/l.c.compilation.min_wall_seconds,worst_runtime_over_c:l.mlf.runtime.max_wall_seconds/l.c.runtime.min_wall_seconds,compilation_margin_seconds:3*l.c.compilation.median_wall_seconds-l.mlf.compilation.median_wall_seconds,mlf_compile:l.mlf.compilation,c_compile:l.c.compilation,mlf_runtime:l.mlf.runtime,c_runtime:l.c.runtime,intervals,median_stages:Object.fromEntries(['total','frontend','runtime_c','llvm','llvm_after_frontend','link','link_after_objects','overlap','other_overhead'].map(k=>[k,stats(intervals.map(s=>s[k]))])),standard_llvm_sha256:reference};
});
const validation=[];
const groups=['unit','packages','self-host','parity','backends','port'];
if(fs.readFileSync(checks+'/completed.txt','utf8').trim().split('\n').join(',')!==groups.join(','))throw Error('Six native groups did not finish in order');
const manager=base+'/final-manager-v2/bin/mlfpkg';
const managerBuild=read(base+'/final-manager-v2/build-report.json');
if(!managerBuild.complete||!managerBuild.commands.some(c=>c.argv[0]===candidate))throw Error('Final native package manager was not built with the candidate');
const validationTools={package_manager:{path:manager,sha256:hash(manager)},build_report_sha256:hash(base+'/final-manager-v2/build-report.json'),fingerprint_sha256:hash(base+'/final-manager-v2/fingerprint.json')};
save(base+'/final-manager-v2/build-report.json','validation/package-manager-build.json');
save(base+'/final-manager-v2/fingerprint.json','validation/package-manager-fingerprint.json');
save(base+'/final-manager-v2-build.log','validation/package-manager-build.log.gz',true);
save(checks+'/completed.txt','validation/completed.txt');
// Keep the first failed coverage-guard attempt separate from the successful rerun.
for(const file of ['verification.json','core.log','core.log.stderr'])save(checks+'/compiler-tests/unit-before-coverage-fix/'+file,'validation/earlier-unit-coverage-guard/'+file);
save(checks+'/unit-before-coverage-fix.log','validation/earlier-unit-coverage-guard/runner.log.gz',true);
for(const name of ['run-final-verification-v2.log','resume-final-verification-v2.log','final-stage-profile-build.log','final-ordinary.log'])save(base+'/'+name,'validation/commands/'+name+'.gz',true);
const expectedSources=read(checks+'/compiler-tests/unit/verification.json').sources;
for(const group of groups){
 const dir=checks+'/compiler-tests/'+group,j=read(dir+'/verification.json');
 if(j.complete!==true||j.compiler_sha256!==digest)throw Error('Native validation incomplete or compiler changed: '+group);
 if(Object.keys(j.sources).length!==Object.keys(expectedSources).length||Object.entries(expectedSources).some(([file,digest])=>j.sources[file]!==digest))throw Error('Native groups tested different source snapshots: '+group);
 for(const [suite,record] of Object.entries({...j.suites,...j.matrices}))if(record.log_sha256&&hash(dir+'/'+suite+'.log')!==record.log_sha256)throw Error('Native validation log changed: '+group+'/'+suite);
 save(dir+'/verification.json','validation/'+group+'.json');save(checks+'/'+group+'.log','validation/'+group+'.log.gz',true);
 for(const f of fs.readdirSync(dir))if(f.endsWith('.log')||f.endsWith('.log.stderr'))save(dir+'/'+f,'validation/'+group+'/'+f+'.gz',true);
 validation.push({...j,sources:undefined});
}
const ordinaryContext=read(ordinary+'/context.json');if(!ordinaryContext.inputs_unchanged||ordinaryContext.candidate!==fs.realpathSync(candidate))throw Error('Ordinary measurements incomplete');
save(ordinary+'/context.json','ordinary/context.json');
const ordinaryRows=[];
for(const variant of ['original','candidate']){
 const samples=[];for(const run of [1,2,3]){
  const stem=ordinary+'/'+run+'-'+variant,s=read(stem+'.json');if(s.exit_code!==0||s.timed_out||s.interrupted)throw Error('Ordinary compilation failed');
  for(const ext of ['json','stderr','argv'])save(stem+'.'+ext,'ordinary/'+run+'-'+variant+'.'+ext);
  samples.push({...s,llvm_sha256:hash(stem+'.ll'),llvm_bytes:fs.statSync(stem+'.ll').size});
 }
 if(new Set(samples.map(s=>s.llvm_sha256)).size!==1)throw Error('Ordinary LLVM differs within variant');
 save(ordinary+'/1-'+variant+'.ll','ordinary/'+variant+'.ll.gz',true);
 const ir=fs.readFileSync(ordinary+'/1-'+variant+'.ll','utf8');
 const llvmFeatures={private_static_string_headers:(ir.match(/\.value = private global/g)||[]).length,inline_thunk_allocator:ir.includes('define private ptr @mlf.allocate.thunk('),shared_constructor_allocator:ir.includes('define private ptr @mlf.allocate.constructor('),inline_single_thunk_force:ir.includes('%isthunk = icmp eq i32 %tag, 3')};
 ordinaryRows.push({variant,samples,llvm_features:llvmFeatures,wall:stats(samples.map(s=>s.wall_seconds)),cpu:stats(samples.map(s=>s.cpu_seconds)),peak_rss:stats(samples.map(s=>s.peak_rss_bytes))});
}
const phaseContext=read(phase+'/measurements/context.json');if(!phaseContext.inputs_unchanged||!phaseContext.all_27_llvm_outputs_equal_baseline)throw Error('Diagnostic checks incomplete');
for(const [file,expected] of Object.entries(phaseContext.sha256))if(hash(file)!==expected)throw Error('Diagnostic source changed: '+file);
for(const [file,expected] of Object.entries(ordinaryContext.sha256))if(hash(file)!==expected)throw Error('Ordinary input changed: '+file);
save(phase+'/measurements/context.json','phases/context.json');save(phase+'/build/build-report.json','phases/build-report.json');save(phase+'/build/fingerprint.json','phases/build-fingerprint.json');
const phaseRows=[];
for(const b of r.benchmarks){
 const samples=[];for(const run of [1,2,3]){const file=phase+'/measurements/'+b.benchmark+'-'+run+'.jsonl';save(file,'phases/'+b.benchmark+'-'+run+'.jsonl');samples.push(fs.readFileSync(file,'utf8').trim().split('\n').map(s=>JSON.parse(s)));}
 const names=samples[0].map(s=>s.phase);
 phaseRows.push({workload:b.benchmark,phases:Object.fromEntries(names.map(n=>[n,stats(samples.map(s=>s.find(p=>p.phase===n).delta_seconds))]))});
}
for(const f of ['toolchain.json','clang-mlf','clang-link-job.txt','clang-machine-job.txt','configure-backend.cjs'])save(config+'/'+f,'backend/'+f);
const tools=read(config+'/toolchain.json');for(const [file,expected] of Object.entries(tools.sha256))if(hash(file)!==expected)throw Error('Backend toolchain changed: '+file);
const helper=tools.machine_command[0];if(fs.existsSync(path.dirname(helper)+'/build.json'))save(path.dirname(helper)+'/build.json','backend/build.json');
if(tools.prestarted_linker)save(path.dirname(tools.prestarted_linker)+'/build.json','backend/link-helper-build.json');
save(root+'/tools/bench/link-backend.cpp','backend/link-backend.cpp');
save(root+'/tools/bench/llvm-backend.c','backend/llvm-backend.c');save(root+'/tools/bench/configure-backend.cjs','backend/configure-source.cjs');
save(pgo+'/provenance.json','pgo/provenance.json');save(pgo+'/training/compiler.profdata','pgo/compiler.profdata');
for(const name of ['training-inputs.json','clang-generate','clang-use','training/type.profraw','training/emit.profraw','training/type.txt','training/type.stderr','training/compiler.stderr'])save(pgo+'/'+name,'pgo/'+name);
for(const name of ['generate-build.log','use-build.log'])save(pgo+'/'+name,'pgo/'+name+'.gz',true);
for(const name of ['instrumented','candidate'])for(const f of ['build-report.json','fingerprint.json'])save(pgo+'/'+name+'/'+f,'pgo/'+name+'-'+f);
save(base+'/start.json','initial-worktree.json');save(base+'/start.patch','initial-worktree.patch');
const experiments=[],rawMeasurementIndex=[];
for(const dir of fs.readdirSync(base)){
 const p=base+'/'+dir;if(!fs.statSync(p).isDirectory())continue;
 const reports=fs.readdirSync(p).filter(n=>/\.(json|jsonl)$/.test(n)&&fs.statSync(p+'/'+n).isFile());
 if(reports.length)rawMeasurementIndex.push({directory:p,reports:reports.map(n=>({file:n,sha256:hash(p+'/'+n)}))});
 if(fs.existsSync(p+'/results.json')&&path.resolve(p)!==bench){save(p+'/results.json','experiments/'+dir+'.json');save(p+'/experiment-note.txt','experiments/'+dir+'-note.txt');save(p+'/exploratory-summary.json','experiments/'+dir+'-exploratory-summary.json');experiments.push({name:dir,kind:'benchmark',source:p});}
 if(fs.existsSync(p+'/summary.json')){save(p+'/summary.json','experiments/'+dir+'/summary.json');for(const name of ['provenance.json','context.json','measurement-script.sh','decision.txt'])save(p+'/'+name,'experiments/'+dir+'/'+name);experiments.push({name:dir,kind:'microbenchmark',source:p});}
 if(fs.existsSync(p+'/build-report.json'))for(const f of ['build-report.json','fingerprint.json'])save(p+'/'+f,'builds/'+dir+'/'+f);
}
for(const name of ['run-pgo7.sh','run-single-index.sh','run-restore-stream.sh','SingleIndexProbe.emlf','SingleIndexDirect.part','RestoreStreamProbe.emlf','run-investigate-stages-v1.sh','run-investigate-stages-v2.sh','run-final-bench-v4.sh','run-final-bench-v5.sh','ReadyLinkPairs.emlf','ReadyLinkStress.emlf','ReadyLinkSmoke.emlf','prepare-ready-link.cjs','run-ready-link.sh','run-ready-link-checks.sh','run-coverage5.sh','run-final-bench-v3.sh','LinkStreamProbe.emlf','ProgressProbe.emlf','host-progress.c','prepare-link-stream.cjs','link-stream-test.part','run-coverage4.sh','run-final-bench-v2.sh','BackendSmoke.emlf','run-final-backend-smoke.sh','run-pgo6.sh','run-coverage3.sh','apply-final-coverage3.cjs','run-inline-force.sh','prepare-inline-force.cjs','BuildForceProbe.emlf','runtime_inline_force.c','run-pgo5.sh','run-streaming-probe.sh','run-streaming-retry.sh','prepare-streaming.cjs','StreamSmoke.emlf','run-o0-greedy.sh','run-map-update.sh','run-map-update-retry.sh','prepare-map-update.cjs','MapUpdateProbe.emlf','run-component-scopes.sh','run-component-scopes-retry.sh','prepare-component-scopes.cjs','ComponentScopesProbe.emlf','ComponentReference.emlf','ComponentFixtures.emlf','run-project-enumeration.sh','prepare-project-enumeration.cjs','ProjectEnumerationProbe.emlf','run-live-node.sh','prepare-live-node.cjs','LiveNodeProbe.emlf','run-projection-map.sh','prepare-projection-map.cjs','ProjectionMap.part','ProjectionMapProbe.emlf','run-final-checks.sh','run-final-bench.sh','run-final-diagnostics.sh','run-global-all.sh','run-pgo4-o3.sh','measure-link-threads.sh','measure-current-heaps.sh','measure-emission.sh','summarize-emission.cjs','collect-evidence.cjs','write-final-reports.cjs'])save(base+'/'+name,'commands/'+name);
for(const name of ['single-index-oracle.log','single-index-oracle-attempt1.log','restore-stream-oracle.log','investigate-stages-v1-build.log','investigate-stages-v2-build.log','coverage5-harness.log','coverage5-harness-build.log','ready-link-pairs.log','ready-link-stress.log','link-fifo-hang.sample.txt','coverage4-harness.log','coverage4-harness-build.log','link-stream-probe.log','link-stream-probe2.log','progress-probe.log','backend-final-v1-smoke.log','stream-final-v1-smoke.log','coverage3-harness.log','coverage3-harness-build.log','inline-force-abi-2.log','component-scopes-oracle.log','project-enumeration-oracle.log'])save(base+'/'+name,'focused-checks/'+name+'.gz',true);
for(const name of ['run-final-verification-v2.sh','resume-final-verification-v2.sh','final-audit.cjs'])save(base+'/'+name,'commands/'+name);
for(const name of fs.readdirSync(base).filter(n=>n.startsWith('before-link-stream-')||n.startsWith('fifo-experiment-')||n.startsWith('before-single-index-')||n.startsWith('before-restore-stream-')||n.startsWith('before-coverage6-')||n.startsWith('before-profile-headers-')))save(base+'/'+name,'earlier-sources/'+name);
// Interrupted runs have no aggregate rows; preserve their individual clocks and DAG specifications.
for(const name of ['final-bench-v2','final-bench-v3']){
 const start=base+'/'+name;
 if(!fs.existsSync(start))continue;
 function retain(dir){for(const item of fs.readdirSync(dir)){const file=dir+'/'+item;if(fs.statSync(file).isDirectory())retain(file);else if(/\.(json|jsonl|argv|spec)$/.test(item))save(file,'incomplete-runs/'+name+'/'+path.relative(start,file));}}
 retain(start);save(start+'-context.json','incomplete-runs/'+name+'/context.json');save(start+'-interruption.json','incomplete-runs/'+name+'/interruption.json');save(start+'.log','incomplete-runs/'+name+'/runner.log.gz',true);
}
for(const name of ['n-body','fasta','k-nucleotide'])for(const run of [1,2,3])save(base+'/investigate-stages-v2/measurements/'+name+'-'+run+'.jsonl','experiments/instantiation-profile/'+name+'-'+run+'.jsonl');
save(base+'/investigate-stages-v2/build/fingerprint.json','experiments/instantiation-profile/build-fingerprint.json');
const initial=read(base+'/start.json'),missing=[],changed=[];for(const [file,expected] of Object.entries(initial.files)){if(!fs.existsSync(file))missing.push(file);else if(hash(file)!==expected)changed.push(file);}
for(const [file,expected] of Object.entries(initial.files))if(hash(base+'/start-source/'+file)!==expected)throw Error('Initial worktree snapshot changed: '+file);
if(missing.length)throw Error('Starting worktree files missing: '+missing.join(', '));
if(fs.existsSync(base+'/forbidden.log'))throw Error('Forbidden-tool invocation recorded');
for(const file of ['bootstrap/Bootstrap/Compiler.emlf','bootstrap/Bootstrap/X/Checked.emlf','bootstrap/Bootstrap/Separate.emlf','bootstrap/Main.emlf'])if(hash(file)!==initial.files[file])throw Error('Existing checked boundary changed: '+file);
for(const file of changed)if(file.startsWith('benchmarks/')&&file!=='benchmarks/RESULTS.md')throw Error('Pinned workload or input changed: '+file);
const head=cp.execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();if(head!==initial.head)throw Error('HEAD changed');
const sources=read(checks+'/compiler-tests/unit/verification.json').sources;
for(const [file,expected] of Object.entries(sources))if(hash(file)!==expected)throw Error('Validated source changed: '+file);
const sourceFiles=new Set(Object.keys(sources).map(p=>path.resolve(p)));
for(const file of ['mlfpkg','mlf-package.json','mlf.lock','bootstrap/mlf-package.json','package/mlf-package.json','tests/mlf-package.json','tools/bench/README.md','tools/profile/README.md'])sourceFiles.add(path.join(root,file));
function walk(dir){for(const name of fs.readdirSync(dir)){if(name==='results')continue;const p=path.join(dir,name);if(fs.statSync(p).isDirectory())walk(p);else if(/\.(emlf|c|cpp|h|sh|cjs|json)$/.test(name))sourceFiles.add(p);}}
walk(root+'/tools/bench');walk(root+'/tools/profile');
const sourceHashes=Object.fromEntries([...sourceFiles].sort().map(file=>{if(!file.startsWith(root+'/'))throw Error('Source outside workspace');return [path.relative(root,file),hash(file)];}));
fs.writeFileSync(out+'/source-sha256.json',JSON.stringify(sourceHashes,null,2)+'\n');
fs.writeFileSync(out+'/source-files.txt',Object.keys(sourceHashes).join('\n')+'\n');
cp.execFileSync('/usr/bin/tar',['-czf',out+'/tested-source.tar.gz','-T',out+'/source-files.txt'],{cwd:root});
cp.execFileSync('/usr/bin/tar',['-czf',out+'/frozen-self-source.tar.gz','-C',root+'/.mlf-build/self-profile/baseline-source','bootstrap']);
cp.execFileSync('/usr/bin/tar',['-czf',out+'/initial-worktree-source.tar.gz','-C',base+'/start-source','.']);
const summary={compiler:{path:candidate,sha256:digest},median_gate_passed:workloadRows.every(b=>b.compile_pass&&b.runtime_pass),primary_objective_met:workloadRows.every(b=>b.compile_pass&&b.runtime_pass&&b.mlf_compile.max_wall_seconds/b.c_compile.min_wall_seconds<3&&b.mlf_runtime.max_wall_seconds/b.c_runtime.min_wall_seconds<2),observed_variation_margin:'Every candidate maximum divided by the C minimum must also remain below the limit for an objective-met claim',limits:r.limits,all_63_candidate_standard_llvm_outputs_equal_starting:true,benchmarks:workloadRows,native_validation:validation,native_validated_source_count:Object.keys(sources).length,ordinary_self_compilation:ordinaryRows,diagnostic_phases:phaseRows,experiments,worktree:{head,branch:cp.execFileSync('git',['branch','--show-current'],{encoding:'utf8'}).trim(),initial_file_count:Object.keys(initial.files).length,missing_starting_files:missing,changed_starting_files:changed},archives:{initial_worktree_source_sha256:hash(out+'/initial-worktree-source.tar.gz'),tested_source_sha256:hash(out+'/tested-source.tar.gz'),frozen_self_source_sha256:hash(out+'/frozen-self-source.tar.gz')}};
fs.writeFileSync(out+'/summary.json',JSON.stringify(summary,null,2)+'\n');
fs.writeFileSync(out+'/validation/toolchain.json',JSON.stringify(validationTools,null,2)+'\n');
fs.writeFileSync(out+'/artifact-index.json',JSON.stringify(artifacts,null,2)+'\n');
fs.writeFileSync(out+'/raw-measurement-index.json',JSON.stringify(rawMeasurementIndex,null,2)+'\n');
fs.renameSync(out,destination);
console.log(destination);console.log('Objective met:',summary.primary_objective_met);console.log('Ordinary seconds:',ordinaryRows.map(r=>[r.variant,r.wall.median]));
