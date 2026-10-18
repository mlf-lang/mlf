'use strict';
const fs=require('fs'),p=require('path'),cp=require('child_process'),crypto=require('crypto');
const base=p.resolve('.mlf-build/bootstrap-memory-2026-10-19'),source=p.join(base,'source-separate'),out=p.join(base,'verification/llvm-equality');
if(fs.existsSync(out))throw Error('Use fresh output');fs.mkdirSync(out,{recursive:true});
const tools={baseline:p.join(base,'pairs/3-baseline/bin/emlf'),candidate:p.join(base,'pairs/3-candidate/bin/emlf')};
const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const env={...process.env};for(const k of ['GC_INITIAL_HEAP_SIZE','GC_FREE_SPACE_DIVISOR','GC_MAXIMUM_HEAP_SIZE','GC_ENABLE_INCREMENTAL','GC_PRINT_STATS','GITHUB_ENV','GITHUB_STEP_SUMMARY'])delete env[k];
const compilers=Object.fromEntries(Object.entries(tools).map(([v,file])=>[v,{file,sha256:hash(file)}]));
const rows=[];
for(const workload of ['binary-trees','pidigits','n-body','fannkuch-redux','spectral-norm','fasta','mandelbrot','reverse-complement','k-nucleotide'])for(const layout of ['standard','compact-gc']){
 const input=p.join(source,'benchmarks',workload,'mlf/main.emlf'),outputs={};
 for(const variant of ['baseline','candidate']){
  const stem=`${workload}-${layout}-${variant}`,ir=p.join(out,stem+'.ll'),err=p.join(out,stem+'.stderr');
  const argv=[layout==='standard'?'--emit-llvm':'--emit-llvm-gc',input];const fd=fs.openSync(ir,'w'),ef=fs.openSync(err,'w');
  try{cp.execFileSync(tools[variant],argv,{cwd:source,env,stdio:['ignore',fd,ef]});}finally{fs.closeSync(fd);fs.closeSync(ef);}
  outputs[variant]={compiler_sha256:compilers[variant].sha256,argv,llvm_sha256:hash(ir),bytes:fs.statSync(ir).size,stderr_sha256:hash(err)};
 }
 const equal=outputs.baseline.llvm_sha256===outputs.candidate.llvm_sha256;
 rows.push({workload,layout,source:input,source_sha256:hash(input),outputs,equal});
 fs.writeFileSync(p.join(out,'report.json'),JSON.stringify({complete:false,compilers,rows},null,2)+'\n');
 if(!equal)throw Error('Generated LLVM differs: '+workload+' '+layout);
}
for(const {file,sha256} of Object.values(compilers))if(hash(file)!==sha256)throw Error('Compiler changed');
fs.writeFileSync(p.join(out,'report.json'),JSON.stringify({complete:true,compilers,rows,all_18_pairs_equal:true},null,2)+'\n');console.log('All nine workloads emit identical LLVM in both layouts.');
