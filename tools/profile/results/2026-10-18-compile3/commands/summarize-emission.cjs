const fs=require('fs'),crypto=require('crypto'),path=require('path');
const dir=process.argv[2];
const median=a=>a.toSorted((a,b)=>a-b)[Math.floor(a.length/2)];
const rows=[];
for (const workload of ['binary-trees','pidigits','n-body','fannkuch-redux','spectral-norm','fasta','mandelbrot','reverse-complement','k-nucleotide']){
 const row={workload};
 for(const variant of ['baseline','candidate']){
  const samples=[1,2,3].map(n=>{
   const prefix=path.join(dir,`${workload}-${n}-${variant}`),s=JSON.parse(fs.readFileSync(prefix+'.json'));
   return {...s,llvm_sha256:crypto.createHash('sha256').update(fs.readFileSync(prefix+'.ll')).digest('hex')};
  });
  const times=samples.map(x=>x.wall_seconds),m=median(times);
  row[variant]={samples,median:m,min:Math.min(...times),max:Math.max(...times),mad:median(times.map(x=>Math.abs(x-m))),cpu_median:median(samples.map(x=>x.cpu_seconds))};
 }
 row.ratio=row.candidate.median/row.baseline.median;
 rows.push(row);
 console.log(workload, row.baseline.median.toFixed(6), row.candidate.median.toFixed(6),row.ratio.toFixed(4));
}
fs.writeFileSync(path.join(dir,'summary.json'),JSON.stringify({rows},null,2)+'\n');
