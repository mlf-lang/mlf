const fs=require('fs'),b='.mlf-build/compile3',p='bootstrap/Bootstrap/LLVM/Codegen.emlf';let s=fs.readFileSync(p,'utf8');
fs.writeFileSync(b+'/before-inline-force-Codegen.emlf',s,{flag:'wx'});
const start=s.indexOf('forceDefinition :'),end=s.indexOf('\naliasMetadata :',start);
if(start<0||end<0)throw Error('Missing compact force helper');
let block=s.slice(start,end);let lines=[...block.matchAll(/  Cons ("(?:[^"\\]|\\.)*")/g)].map(m=>JSON.parse(m[1]));
if(lines.length<30)throw Error('Could not read force helper');
const branch=lines.indexOf('  br i1 %ready, label %done, label %indirect');if(branch<0)throw Error('Missing force branch');
lines.splice(branch,1,'  br i1 %ready, label %done, label %deferred','deferred:','  %isthunk = icmp eq i32 %tag, 3','  br i1 %isthunk, label %enter, label %indirect');
const slow=lines.indexOf('slow:');
lines.splice(slow,0,
 'enter:',
 '  %code.slot = getelementptr i8, ptr %value, i64 8',
 '  %env.slot = getelementptr i8, ptr %value, i64 16',
 '  %code = load ptr, ptr %code.slot, align 8',
 '  %env = load ptr, ptr %env.slot, align 8',
 '  store i32 1, ptr %value, align 4',
 '  store ptr null, ptr %code.slot, align 8',
 '  store ptr null, ptr %env.slot, align 8',
 '  %returned = call ptr %code(ptr %env, ptr null)',
 '  %canonical = call ptr @mlf_force(ptr %returned)',
 '  store i32 2, ptr %value, align 4',
 '  store ptr %canonical, ptr %code.slot, align 8',
 '  ret ptr %canonical');
block='forceDefinition : Int -> List String\nforceDefinition header = if header /= 0 then Nil else\n'+lines.map((line,i)=>'  Cons '+JSON.stringify(line)+(i===lines.length-1?' Nil'+')'.repeat(lines.length-1):' (')).join('\n')+'\n';
s=s.slice(0,start)+block+s.slice(end);fs.writeFileSync(p,s);
const runtime='runtime/mlf_runtime.c';s=fs.readFileSync(runtime,'utf8');fs.writeFileSync(b+'/before-inline-force-runtime.c',s,{flag:'wx'});
const marker='_Static_assert(offsetof(MlfValue, as.packed.identity) == 8, "constructor identity ABI");';
if(!s.includes(marker))throw Error('Missing compact ABI assertions');
s=s.replace(marker,'_Static_assert(BUSY == 1 && INDIRECT == 2 && THUNK == 3 && CLOSURE == 5, "compact force tag ABI");\n_Static_assert(offsetof(MlfValue, tag) == 0 && offsetof(MlfValue, as.closure.code) == 8 && offsetof(MlfValue, as.closure.env) == 16, "compact force payload ABI");\n'+marker);fs.writeFileSync(runtime,s);
