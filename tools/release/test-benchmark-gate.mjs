import assert from 'node:assert/strict';
import {verify, workloads} from './verify-benchmarks.mjs';
const digest = 'a'.repeat(64);
const metric = {wall_seconds:1,cpu_seconds:1,peak_rss_bytes:1024,exit_code:0,timed_out:false,interrupted:false,termination_signal:0};
const summary = {median_wall_seconds:1,min_wall_seconds:1,max_wall_seconds:1,median_absolute_deviation_seconds:0,samples:Array.from({length:7},()=>({...metric}))};
const manifest = {workloads:workloads.map(name=>({name,default_input:100}))};
const fixture = {
 status:'passed',implementation:'MLF',runs:7,limits:{compilation:3,runtime:2},workload_selection:workloads,
 benchmarks:workloads.map(benchmark=>({benchmark,input:100,stdin_sha256:digest,
   languages:Object.fromEntries(['c','baseline','mlf'].map(language=>[language,{compilation:summary,runtime:summary}])),
   binary_samples:Array.from({length:7},()=>Object.fromEntries(['c','baseline','mlf'].map(language=>[language,{binary_sha256:digest,artifacts_sha256:{'program.ll':digest,'runtime.o':digest,'program.o':digest}}])))})),
 performance_checks:workloads.flatMap(benchmark=>['compilation','runtime'].map(dimension=>({benchmark,dimension,maximum_ratio:dimension==='compilation'?3:2,passed:true,mlf_over_c:1})))
};
verify(fixture,manifest);
let count=1;
function reject(label, mutate) {
 const report=structuredClone(fixture), inputs=structuredClone(manifest); mutate(report,inputs);
 assert.throws(()=>verify(report,inputs),undefined,label); count++;
}
for (const state of ['running','failed','preparing',undefined]) reject(`reject ${state}`,r=>r.status=state);
reject('nine selected workloads',r=>r.workload_selection.pop());
reject('nine report rows',r=>r.benchmarks.pop());
reject('duplicate workload',r=>r.benchmarks[0].benchmark=r.benchmarks[1].benchmark);
reject('unknown manifest workload',(r,m)=>m.workloads[0].name='unknown');
reject('changed default input',r=>r.benchmarks[0].input=99);
reject('historical 5x limit',r=>r.limits.compilation=5);
reject('relaxed runtime',r=>r.limits.runtime=3);
reject('three instead of seven samples',r=>r.runs=3);
reject('missing baseline',r=>delete r.benchmarks[0].languages.baseline);
reject('missing timed sample',r=>r.benchmarks[0].languages.mlf.runtime.samples.pop());
reject('missing binary identity',r=>r.benchmarks[0].binary_samples[0].mlf.binary_sha256='');
reject('missing LLVM identity',r=>delete r.benchmarks[0].binary_samples[0].mlf.artifacts_sha256['program.ll']);
reject('missing RSS',r=>delete r.benchmarks[0].languages.c.runtime.samples[0].peak_rss_bytes);
reject('timeout',r=>r.benchmarks[0].languages.c.runtime.samples[0].timed_out=true);
reject('failed process',r=>r.benchmarks[0].languages.c.runtime.samples[0].exit_code=1);
reject('wrong median',r=>r.benchmarks[0].languages.c.runtime.median_wall_seconds=0.5);
reject('missing check',r=>r.performance_checks.pop());
reject('duplicate check',r=>r.performance_checks[0]=r.performance_checks[1]);
reject('native failed check',r=>r.performance_checks[0].passed=false);
reject('native relaxed check',r=>r.performance_checks[0].maximum_ratio=5);
reject('native ratio exceeds limit',r=>r.performance_checks[0].mlf_over_c=3.01);
reject('ratio inconsistent with samples',r=>r.performance_checks[0].mlf_over_c=2);
console.log(`${count} benchmark gate checks passed.`);
