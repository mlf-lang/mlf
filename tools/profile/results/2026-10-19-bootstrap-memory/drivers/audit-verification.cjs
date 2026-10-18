'use strict';
const fs=require('fs'),p=require('path'),cp=require('child_process'),crypto=require('crypto');
const base=p.resolve('.mlf-build/bootstrap-memory-2026-10-19'),source=p.join(base,'source-separate'),root=p.join(base,'verification/compiler-tests');
const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');const read=f=>JSON.parse(fs.readFileSync(f));
const compiler=p.join(base,'pairs/3-candidate/bin/emlf'),expected=hash(compiler),rows=[];let snapshot=null;
function requireTrue(t,s){if(!t)throw Error(s);}
for(const group of ['unit','packages','self-host','parity','backends','port']){
 const file=p.join(root,group,'verification.json'),r=read(file);
 requireTrue(r.complete===true&&r.implementation==='MLF'&&r.group===group&&r.compiler_sha256===expected,'Incomplete or wrong compiler/group: '+group);
 const sorted=JSON.stringify(Object.fromEntries(Object.entries(r.sources).sort()));
 if(snapshot===null)snapshot=sorted;else requireTrue(sorted===snapshot,'Snapshot mismatch: '+group);
 const logs={};for(const [name,suite]of Object.entries({...r.suites,...r.matrices})){
  const file=p.join(root,group,name+'.log');requireTrue(hash(file)===suite.log_sha256,'Primary log changed: '+file);logs[name]=suite.log_sha256;
 }
 rows.push({group,complete:r.complete,report_sha256:hash(file),source_files:Object.keys(r.sources).length,logs,...(r.suites?{suites:r.suites}:{}),...(r.parity?{parity:r.parity}:{}),...(r.matrices?{matrices:r.matrices}:{}),...(r.fixed_point?{fixed_point:r.fixed_point}:{})});
}
const sources=JSON.parse(snapshot);for(const [file,sha]of Object.entries(sources)){requireTrue(hash(p.join(source,file))===sha,'Frozen test source changed: '+file);requireTrue(hash(p.resolve(file))===sha,'Current checkout test source differs: '+file);}
const inventory=cp.execFileSync('/bin/sh',['-c',"find src app test scripts runtime bootstrap package examples benchmarks tests -type d \\( -name .mlf-build -o -name .git -o -name dist-newstyle -o -name __pycache__ \\) -prune -o -type f \\( -name '*.hs' -o -name '*.emlf' -o -name '*.c' -o -name '*.h' -o -name '*.py' -o -name '*.sh' -o -name '*.expected' -o -name '*.json' -o -name '*.gz' \\) -print"],{cwd:source,encoding:'utf8'}).trim().split('\n').concat(['mlfpkg','mlf-package.json']).sort();
requireTrue(JSON.stringify(inventory)===JSON.stringify(Object.keys(sources).sort()),'Input inventory changed');
const find=g=>rows.find(r=>r.group===g);
requireTrue(find('unit').suites.core.coverage.includes('654 checks; 0 failures')&&find('unit').suites.core.coverage.includes('Oracle: 6712 closed terms')&&find('unit').suites.figure12.coverage.includes('43/43 expressions match regression expectations; 0 failures')&&find('unit').suites.figure12.coverage.includes('36 supplementary checks; 0 failures')&&find('unit').suites.harness.coverage.includes('57 native benchmark/bootstrap/release harness tests passed'),'Unit coverage changed');
requireTrue(find('packages').suites.packages.coverage.includes('18 package resolver tests passed')&&find('packages').suites.packages.coverage.includes('19 package integration cases passed'),'Package coverage changed');
const fixed=find('self-host').fixed_point;requireTrue(fixed.reused_candidate_build===false&&fixed.next_compiler_sha256===expected&&fixed.llvm_sha256==='6681b744a867617156f6e8caf4a91c3a1c6f28ecd0d51a3f36f98051f9e701dd','Fresh self-host fixed point failed');
const next=read(p.join(root,'self-host/next-stage/build-report.json'));requireTrue(next.complete===true&&!next.builds.some(b=>b.cached),'Self-host reused any build cache');
const parity=find('parity').parity;requireTrue(parity.cases===7086&&parity.accepted===3202&&parity.rejected===3884&&parity.runtime_executions===160,'Parity coverage changed');
for(const group of ['backends','port']){
 const m=find(group).matrices;requireTrue(JSON.stringify(Object.keys(m).sort())===JSON.stringify(['compact-gc','standard']),'Missing layout: '+group);
 let labels=null;
 for(const [layout,row]of Object.entries(m)){
  requireTrue(row.backends===2&&row.rows===(group==='port'?26:552),'Missing backend executions: '+group);
  const file=p.join(root,group,'matrix-'+layout,'rows.jsonl');
  const ledger=fs.readFileSync(file,'utf8').trim().split('\n').map(JSON.parse);
  requireTrue(ledger.length===row.rows&&ledger.every((r,i)=>r.index===i&&JSON.stringify(r.backends)===JSON.stringify(['interpreter','llvm'])),'Incomplete row ledger: '+group+' '+layout);
  const names=JSON.stringify(ledger.map(r=>r.label));if(labels===null)labels=names;else requireTrue(names===labels,'Layout fixture inventory differs: '+group);
  row.verified_rows_sha256=hash(file);
 }

}
const report={complete:true,compiler_sha256:expected,manager_sha256:hash(p.join(base,'pairs/3-candidate/bin/mlfpkg')),source_files:Object.keys(sources).length,all_primary_log_hashes_verified:true,sources_unchanged:true,current_checkout_test_sources_match:true,all_matrix_row_ledgers_verified:true,fresh_self_host_all_cache_misses:true,rows};
fs.writeFileSync(p.join(base,'verification/audit.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({complete:true,source_files:report.source_files,groups:rows.map(r=>r.group)}));
