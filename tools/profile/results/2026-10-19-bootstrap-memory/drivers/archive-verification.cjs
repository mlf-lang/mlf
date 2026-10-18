'use strict';
const fs=require('fs'),p=require('path'),cp=require('child_process'),crypto=require('crypto'),z=require('zlib');
const base=p.resolve('.mlf-build/bootstrap-memory-2026-10-19'),out=p.resolve('tools/profile/results/2026-10-19-bootstrap-memory'),vr=p.join(base,'verification');
const hash=f=>crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');const read=f=>JSON.parse(fs.readFileSync(f));
const audit=read(p.join(vr,'audit.json'));if(!audit.complete||audit.rows.length!==6)throw Error('Verification incomplete');
const equality=read(p.join(vr,'llvm-equality/report.json'));if(!equality.complete||equality.rows.length!==18||!equality.all_18_pairs_equal)throw Error('LLVM comparison incomplete');
const legacy=read(p.join(base,'legacy-audit.json'));if(!legacy.complete)throw Error('Legacy gate incomplete');
function copy(src,dst){fs.mkdirSync(p.dirname(dst),{recursive:true});fs.copyFileSync(src,dst);}
function gzip(src,dst){fs.mkdirSync(p.dirname(dst),{recursive:true});fs.writeFileSync(dst,z.gzipSync(fs.readFileSync(src),{level:9}));}
function walk(dir,fn,rel=''){for(const e of fs.readdirSync(p.join(dir,rel),{withFileTypes:true})){const file=p.join(rel,e.name);if(e.isDirectory())walk(dir,fn,file);else if(e.isFile())fn(file);}}
function pack(dir,files,dst){
 fs.mkdirSync(p.dirname(dst),{recursive:true});const inventory=Object.fromEntries(files.sort().map(rel=>[rel,hash(p.join(dir,rel))]));
 fs.writeFileSync(dst+'.contents.json',JSON.stringify(inventory,null,2)+'\n');
 const list=fs.mkdtempSync(p.join(p.resolve('.mlf-build'),'memory-filelist-'))+'/files';fs.writeFileSync(list,files.join('\0')+'\0');
 cp.execFileSync('/usr/bin/tar',['--null','-czf',dst,'-C',dir,'-T',list],{env:{...process.env,COPYFILE_DISABLE:'1'}});fs.rmSync(p.dirname(list),{recursive:true});
 const tmp=fs.mkdtempSync(p.join(p.resolve('.mlf-build'),'memory-unpack-'));cp.execFileSync('/usr/bin/tar',['-xzf',dst,'-C',tmp]);
 for(const [rel,expected]of Object.entries(inventory))if(hash(p.join(tmp,rel))!==expected)throw Error('Archive mismatch: '+rel);
 fs.rmSync(tmp,{recursive:true});
}
copy(p.join(vr,'audit.json'),p.join(out,'verification/audit.json'));
for(const row of audit.rows){
 const dir=p.join(vr,'compiler-tests',row.group),dst=p.join(out,'verification',row.group);copy(p.join(dir,'verification.json'),p.join(dst,'verification.json'));
 for(const name of Object.keys(row.logs)){copy(p.join(dir,name+'.log'),p.join(dst,name+'.log'));if(hash(p.join(dst,name+'.log'))!==row.logs[name])throw Error('Primary log changed');}
 gzip(p.join(vr,row.group+'.log'),p.join(dst,'native-driver.log.gz'));
 const files=[];walk(dir,rel=>{if(/\.(log|stderr|err|out|stdout|status\.json|xmlf|type|emlf|expected|stdin)$/.test(rel)||rel.endsWith('rows.jsonl')||rel.endsWith('current-label')||rel.endsWith('build-report.json')||rel.endsWith('artifact.json'))files.push(rel);});
 pack(dir,files,p.join(dst,'diagnostics.tar.gz'));
}
const suite=p.join(vr,'compiler-tests/mlf-test-suite'),suiteFiles=[];walk(suite,rel=>{if(rel==='build-report.json'||rel.endsWith('artifact.json')||rel.startsWith('commands/'))suiteFiles.push(rel);});
pack(suite,suiteFiles,p.join(out,'verification/native-test-build.tar.gz'));
copy(p.join(vr,'llvm-equality/report.json'),p.join(out,'llvm/generated-equality.json'));
const files=fs.readdirSync(p.join(vr,'llvm-equality')).filter(f=>f.endsWith('.ll')||f.endsWith('.stderr'));
pack(p.join(vr,'llvm-equality'),files,p.join(out,'llvm/generated-workloads.tar.gz'));
for(const name of ['audit-verification.cjs','compare-generated-llvm.cjs','finish-verification.sh','archive-verification.cjs'])copy(p.join(base,name),p.join(out,'drivers',name));
copy(p.join(base,'finish-verification.log'),p.join(out,'verification/finish.log'));
copy(p.join(base,'legacy-audit.json'),p.join(out,'legacy/audit.json'));
copy(p.join(base,'legacy.log'),p.join(out,'legacy/native-driver.log'));
copy(p.join(base,'legacy-export.env'),p.join(out,'legacy/github-env.txt'));
for(const rel of ['build-report.json','timing/context.json','timing/host.txt','timing/summary.json','timing/summary.md'])copy(p.join(base,'legacy',rel),p.join(out,'legacy',rel));
const raw=[];walk(p.join(base,'legacy'),rel=>{if(rel.startsWith('commands/')||rel.startsWith('timing/commands/')||rel.startsWith('timing/bin/')||rel==='timing/events.log'||rel.endsWith('artifact.json'))raw.push(rel);});
pack(p.join(base,'legacy'),raw,p.join(out,'legacy/raw-commands.tar.gz'));
console.log(JSON.stringify({complete:true,groups:audit.rows.map(r=>r.group),llvm_pairs:equality.rows.length,legacy:legacy.complete}));
