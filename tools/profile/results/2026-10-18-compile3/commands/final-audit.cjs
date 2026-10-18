const fs=require('fs'),path=require('path'),crypto=require('crypto'),cp=require('child_process');
const root=process.cwd(),base=root+'/.mlf-build/compile3',dir=root+'/tools/profile/results/2026-10-18-compile3';
const read=p=>JSON.parse(fs.readFileSync(p));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const initial=read(base+'/start.json'),summary=read(dir+'/summary.json'),bench=read(dir+'/bench-final.json');
if(!summary.primary_objective_met)throw Error('Performance objective incomplete');
const head=cp.execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();
if(head!==initial.head)throw Error('HEAD changed');
if(fs.existsSync(base+'/forbidden.log'))throw Error('Forbidden tool invoked');
for(const file of Object.keys(initial.files))if(!fs.existsSync(file))throw Error('Starting file missing: '+file);
for(const [file,digest] of Object.entries(initial.files))if(hash(base+'/start-source/'+file)!==digest)throw Error('Starting source snapshot changed: '+file);
for(const [file,digest] of Object.entries(initial.files))if(file.startsWith('benchmarks/')&&file!=='benchmarks/RESULTS.md'&&hash(file)!==digest)throw Error('Pinned benchmark changed: '+file);
for(const [file,digest] of Object.entries(read(dir+'/source-sha256.json')))if(hash(file)!==digest)throw Error('Tested source changed: '+file);
for(const [file,digest] of Object.entries(read(dir+'/bench-context.json').sha256))if(hash(file)!==digest)throw Error('Toolchain or benchmark context changed: '+file);
if(hash(summary.compiler.path)!==summary.compiler.sha256)throw Error('Candidate changed');
const median=values=>[...values].sort((a,b)=>a-b)[Math.floor(values.length/2)];
for(const b of bench.benchmarks)for(const language of ['c','baseline','mlf'])for(const dimension of ['compilation','runtime']){
 const record=b.languages[language][dimension],samples=record.samples;
 if(samples.length!==7||samples.some(s=>s.exit_code!==0||s.timed_out||s.interrupted))throw Error('Incomplete measurement: '+b.benchmark+'/'+language+'/'+dimension);
 if(median(samples.map(s=>s.wall_seconds))!==record.median_wall_seconds)throw Error('Median differs from raw samples');
}
for(const group of ['unit','packages','self-host','parity','backends','port']){
 const r=read(dir+'/validation/'+group+'.json');
 if(!r.complete||r.compiler_sha256!==summary.compiler.sha256)throw Error('Native validation incomplete: '+group);
}
for(const file of ['tools/profile/RESULTS.md','benchmarks/RESULTS.md'])if(!fs.readFileSync(file,'utf8').endsWith(fs.readFileSync(base+'/start-source/'+file,'utf8')))throw Error('Historical report changed: '+file);
cp.execFileSync('git',['diff','--check'],{stdio:'pipe'});
const audit={complete:true,compiler:summary.compiler,head,branch:cp.execFileSync('git',['branch','--show-current'],{encoding:'utf8'}).trim(),initial_files_present:Object.keys(initial.files).length,initial_source_snapshot_files_verified:Object.keys(initial.files).length,changed_starting_files:Object.entries(initial.files).filter(([file,digest])=>hash(file)!==digest).map(([file])=>file),source_hashes_verified:Object.keys(read(dir+'/source-sha256.json')).length,all_378_timed_samples_successful_and_medians_recomputed:true,native_groups_verified:6,forbidden_invocation_log_present:false,git_diff_check:'passed',historical_reports_preserved_verbatim:true,reports_sha256:Object.fromEntries(['tools/profile/RESULTS.md','benchmarks/RESULTS.md'].map(file=>[file,hash(file)]))};
fs.writeFileSync(dir+'/final-audit.json',JSON.stringify(audit,null,2)+'\n');
const entries=[];
function walk(parent){for(const name of fs.readdirSync(parent).sort()){const p=path.join(parent,name);if(fs.statSync(p).isDirectory())walk(p);else if(name!=='SHA256SUMS')entries.push(hash(p)+'  '+path.relative(dir,p));}}
walk(dir);fs.writeFileSync(dir+'/SHA256SUMS',entries.join('\n')+'\n');
console.log(JSON.stringify(audit,null,2));
console.log('Evidence files hashed:',entries.length);
