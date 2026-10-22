#!/usr/bin/env node
// Configure a generic MLF LLVM backend; this never reads workload sources.
// All per-program optimization, runtime compilation and linking remain timed.
const fs = require('fs'), path = require('path'), cp = require('child_process'), crypto = require('crypto');
const [clangArg, optArg, linkerArg, outputArg, ...extra] = process.argv.slice(2);
const waitAt = extra.indexOf('--prestart-link');
let waitArg=null;
if(waitAt>=0){if(waitAt!==extra.length-2)throw Error('Expected --prestart-link MLF_LINK at the end');waitArg=extra[waitAt+1];extra.splice(waitAt,2);}
const waitLinker=waitArg?fs.realpathSync(waitArg):null;
const single = extra[0] === '--single-process';
const llcArg = !single && extra.length === 1 ? extra[0] : null;
const backendArg = single ? extra[1] : null;
if (!outputArg || (single ? !backendArg || extra.length !== 2 : extra.length > 1)) throw Error('configure-backend.cjs CLANG OPT LD64_LLD FRESH_OUTPUT_DIRECTORY [LLC | --single-process MLF_LLVM]');
if (process.platform !== 'darwin' || process.arch !== 'arm64') throw Error('This direct-link configuration is validated only on Darwin arm64.');
const absolute = p => fs.realpathSync(p);
const clang = absolute(clangArg), opt = absolute(optArg), linker = absolute(linkerArg);
const llc = llcArg ? absolute(llcArg) : null;
const singleBackend = backendArg ? absolute(backendArg) : null;
const out = path.resolve(outputArg);
if (fs.existsSync(out)) throw Error('Use a fresh configuration directory.');
fs.mkdirSync(out, {recursive:true});
const first = path.join(out,'probe-a.o'), second = path.join(out,'probe-b.o'), destination = path.join(out,'probe');
fs.writeFileSync(first,''); fs.writeFileSync(second,'');
const probeArgs = ['-###', '-fuse-ld='+path.resolve(linkerArg), first, second, '-lm', '-o', destination];
const probe = cp.spawnSync(clang,probeArgs,{encoding:'utf8'});
fs.writeFileSync(path.join(out,'clang-link-job.txt'),probe.stderr || '');
fs.unlinkSync(first); fs.unlinkSync(second);
if (probe.status !== 0) throw Error('Clang linker discovery failed: '+probe.stderr);
const jobs = probe.stderr.split('\n').filter(s=>/^\s*"/.test(s));
if (jobs.length !== 1) throw Error('Expected one linker job.');
const tokens = jobs[0].match(/"(?:[^"\\]|\\.)*"/g).map(s=>JSON.parse(s));
if (absolute(tokens[0]) !== linker) throw Error('Unexpected linker.');
const template=[], prefix=[], suffix=[]; let afterInputs=false;
for (let i=1; i<tokens.length; i++) {
 const value=tokens[i];
 if(value===first || value===second) {afterInputs=true;continue;}
 if(value==='-lm') continue;
 if(value==='-o' && tokens[i+1]===destination) {i++;continue;}
 template.push(value); (afterInputs ? suffix : prefix).push(value);
}
if(!template.includes('-platform_version') || !template.includes('-arch') || !template.includes('arm64')) throw Error('Missing platform contract.');
let machine = null;
if(llc || singleBackend){
 const input=path.join(out,'probe.ll');fs.writeFileSync(input,'');
 const result=cp.spawnSync(clang,['-###','-O1','-c',input,'-o',first],{encoding:'utf8'});
 fs.unlinkSync(input);fs.writeFileSync(path.join(out,'clang-machine-job.txt'),result.stderr||'');
 if(result.status!==0)throw Error('Clang machine configuration failed');
 const jobs=result.stderr.split('\n').filter(s=>/^\s*"/.test(s));
 if(jobs.length!==1)throw Error('Expected one cc1 job');
 const args=jobs[0].match(/"(?:[^"\\]|\\.)*"/g).map(s=>JSON.parse(s));
 const value=flag=>{const i=args.indexOf(flag);return i<0?'':args[i+1];};
 const features=[];for(let i=0;i<args.length;i++)if(args[i]==='-target-feature')features.push(args[i+1]);
 machine={triple:value('-triple'),cpu:value('-target-cpu'),tune:value('-tune-cpu'),abi:value('-target-abi'),features};
 if(!machine.triple||!machine.cpu)throw Error('Missing machine target');
}
const quote = s => "'"+s.replaceAll("'", "'\\''")+"'";
const passes='globaldce,function(early-cse,instcombine,simplifycfg,tailcallelim),globaldce';
const machineArgs=machine ? ['-O1','-enable-misched=false','-filetype=obj','-relocation-model=pic','-mtriple='+machine.triple,'-mcpu='+machine.cpu,...(machine.tune?['-mtune='+machine.tune]:[]),...(machine.features.length?['-mattr='+machine.features.join(',')]:[])] : [];
const machineCommand=llc ? `exec ${quote(llc)} ${machineArgs.map(quote).join(' ')} "$bitcode" -o "$output"` : `exec ${quote(clang)} "\${forwarded[@]}" -O1 -Xclang -disable-llvm-passes -mllvm -enable-misched=false`;
const singleArgs=singleBackend ? [machine.triple,machine.cpu,machine.tune,machine.features.join(','),machine.abi] : [];
const emit=singleBackend ? `if $stream; then exec ${quote(singleBackend)} "$ir.pipe" "$output" ${singleArgs.map(quote).join(' ')} "$ir"; fi
 exec ${quote(singleBackend)} "$ir" "$output" ${singleArgs.map(quote).join(' ')}` : `if $stream; then echo 'Streaming requires the single-process LLVM helper' >&2; exit 2; fi
 bitcode=$output.opt.bc
 ${quote(opt)} ${quote('-passes='+passes)} "$ir" -o "$bitcode"
 forwarded=()
 for arg in "\${args[@]}"; do
  if [[ $arg == "$ir" ]]; then forwarded+=("$bitcode"); else forwarded+=("$arg"); fi
 done
 ${machineCommand}`;
const script=`#!/bin/bash
set -euo pipefail
# Generated by tools/bench/configure-backend.cjs; see toolchain.json.
args=()
ir=''
output=''
compile=false
stream=false
waitObjects=false
irCount=0
previous=''
for arg in "$@"; do
 if [[ $previous == -o ]]; then output=$arg; fi
 previous=$arg
 case "$arg" in
  --mlf-stream-ir) stream=true ;;
  --mlf-wait-objects) waitObjects=true ;;
  -O2) args+=(-O2) ;;
  *.ll) ir=$arg; irCount=$((irCount + 1)); args+=("$arg") ;;
  -c) compile=true; args+=("$arg") ;;
  *) args+=("$arg") ;;
 esac
done
# The native package manager can combine LLVM compilation and linking in one
# driver invocation. Support that form too; all work stays in this invocation.
irLink=true
expectOutput=false
for arg in "\${args[@]}"; do
 if $expectOutput; then expectOutput=false; continue; fi
 case "$arg" in
  -o) expectOutput=true ;;
  *.o|*.a) if $compile; then irLink=false; fi ;;
  *.ll|-c|-O2|-Wno-override-module|-I*|-L*|-l*|-Wl,*) ;;
  *) irLink=false ;;
 esac
done
if $compile && $irLink && [[ $irCount == 1 && -n $output ]]; then
 ${emit}
fi
if ! $compile && $irLink && [[ $irCount == 1 && -n $output ]]; then
 temporary=$output.llvm.o
 ( output=$temporary
   args=(-c "$ir" -o "$temporary")
   ${emit}
 )
 linkedArgs=()
 for arg in "\${args[@]}"; do
  if [[ $arg == "$ir" ]]; then linkedArgs+=("$temporary"); else
   case "$arg" in
    -O2|-Wno-override-module) ;;
    *) linkedArgs+=("$arg") ;;
   esac
  fi
 done
 args=("\${linkedArgs[@]}")
fi
# Only translate the object-only link form. Other Clang modes use its driver.
object=false
supported=true
expectOutput=false
linked=()
for arg in "\${args[@]}"; do
 if $expectOutput; then linked+=("$arg"); expectOutput=false; continue; fi
 case "$arg" in
  *.o|*.a) object=true; linked+=("$arg") ;;
  -o) expectOutput=true; linked+=("$arg") ;;
  -I*) ;;
  -L*|-l*) linked+=("$arg") ;;
  *) supported=false ;;
 esac
done
if ! $compile && $object && $supported && ! $expectOutput; then
 if $waitObjects; then
  ${waitLinker?`ready=(); markOutput=false
  for arg in "\${args[@]}"; do
   if $markOutput; then markOutput=false; continue; fi
   case "$arg" in -o) markOutput=true;; *.o) ready+=("$arg.ready");; esac
  done
  exec ${quote(waitLinker)} "\${ready[@]}" -- ${quote(path.resolve(linkerArg))} ${prefix.map(quote).join(' ')} "\${linked[@]}" ${suffix.map(quote).join(' ')}`:`echo 'Prestarted linking requires --prestart-link configuration' >&2; exit 2`}
 fi
 exec ${quote(path.resolve(linkerArg))} ${prefix.map(quote).join(' ')} "\${linked[@]}" ${suffix.map(quote).join(' ')}
fi
exec ${quote(clang)} "\${args[@]}"
`;
const backend=path.join(out,'clang-mlf'); fs.writeFileSync(backend,script,{mode:0o755});
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const files=[...(waitLinker?[waitLinker,path.join(path.dirname(waitLinker),'build.json')]:[]),'/bin/bash','/bin/cat','/usr/bin/mkfifo','/usr/bin/touch',clang,opt,linker,...(llc?[llc]:[]),...(singleBackend?[singleBackend,path.join(path.dirname(singleBackend),'build.json')]:[]),__filename,backend,...template.filter(p=>path.isAbsolute(p)&&fs.existsSync(p)&&fs.statSync(p).isFile())];
const config = probe.stderr.split('\n').find(line=>line.startsWith('Configuration file: '));
if(config) files.push(config.slice('Configuration file: '.length));
const sdk = template[template.indexOf('-syslibroot')+1];
for(const relative of ['SDKSettings.json','usr/lib/libSystem.tbd']) {const p=path.join(sdk,relative);if(fs.existsSync(p)) files.push(p);}
// Clang and the helper use shared LLVM libraries. Bind their on-disk dependency
// closure as well as the small driver executables. System shared-cache entries
// are recorded by install name; the run context also records the OS build.
const dynamicLibraries={};
function dependencies(file, executable, inherited=[]) {
 const real=absolute(file); if(dynamicLibraries[real])return;
 const directory=path.dirname(real),executableDirectory=path.dirname(executable);
 const expand=p=>p.replace(/^@loader_path(?=\/|$)/,directory).replace(/^@executable_path(?=\/|$)/,executableDirectory);
 const loadCommands=cp.execFileSync('/usr/bin/otool',['-l',real],{encoding:'utf8'}).split('\n');
 const rpaths=[];
 for(let i=0;i<loadCommands.length;i++)if(loadCommands[i].trim()==='cmd LC_RPATH'){
  const line=loadCommands.slice(i+1,i+5).find(s=>/^\s*path /.test(s));
  if(line)rpaths.push(expand(line.trim().replace(/^path /,'').replace(/ \(offset \d+\)$/,'')));
 }
 const search=[...rpaths,...inherited];
 const names=cp.execFileSync('/usr/bin/otool',['-L',real],{encoding:'utf8'}).split('\n').slice(1).map(s=>s.trim().split(' (')[0]).filter(Boolean);
 dynamicLibraries[real]=[];
 for(const reference of names){
  const candidates=reference.startsWith('@rpath/')?search.map(p=>path.join(p,reference.slice(7))):[expand(reference)];
  const resolved=candidates.find(p=>path.isAbsolute(p)&&fs.existsSync(p));
  const system=reference.startsWith('/usr/lib/')||reference.startsWith('/System/Library/');
  if(!resolved&&!system)throw Error('Cannot fingerprint dynamic dependency '+reference+' of '+real);
  dynamicLibraries[real].push({reference,resolved:resolved?absolute(resolved):null,system_shared_cache:!resolved&&system});
  if(resolved){files.push(absolute(resolved));dependencies(resolved,executable,search);}
 }
}
for(const executable of [...(waitLinker?[waitLinker]:[]),clang,opt,linker,...(llc?[llc]:[]),...(singleBackend?[singleBackend]:[])])dependencies(executable,executable);
const identities=Object.fromEntries([...new Set(files)].map(p=>[absolute(p),hash(p)]));
fs.writeFileSync(path.join(out,'toolchain.json'),JSON.stringify({format:1,platform:process.platform,architecture:process.arch,environment:Object.fromEntries(['SDKROOT','MACOSX_DEPLOYMENT_TARGET','CPATH','C_INCLUDE_PATH','LIBRARY_PATH','DYLD_LIBRARY_PATH','DYLD_INSERT_LIBRARIES'].map(k=>[k,process.env[k]||''])),dynamic_libraries:dynamicLibraries,resolved_invocations:{[path.resolve(linkerArg)]:linker},configure_command:process.argv,probe_command:[clang,...probeArgs],prestarted_linker:waitLinker,link_template:[path.resolve(linkerArg),...prefix,'<object/link arguments>',...suffix],llvm_passes:passes,runtime_optimization:'unchanged (-O2 in the benchmark pipeline)',machine_optimization:'-O1; instruction scheduling disabled',machine_command:singleBackend?[singleBackend,'<input>','<output>',...singleArgs]:llc?[llc,...machineArgs]:[clang,'-O1','-Xclang','-disable-llvm-passes','-mllvm','-enable-misched=false'],c_baseline:'unmodified; invoke the real C compiler directly',sha256:identities},null,2)+'\n');
console.log(backend);
