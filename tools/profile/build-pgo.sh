#!/bin/bash
set -euo pipefail
# Train only on frozen compiler sources; no benchmark programs or inputs.
# Native package builds produce both instrumented and profile-use compilers.
if [[ $# != 4 ]]; then echo 'build-pgo.sh SEED FROZEN_BOOTSTRAP LLVM_PREFIX FRESH_OUTPUT' >&2; exit 64; fi
seed=$1
frozen=$2
llvm=$3
out=$4
root=$(cd "$(dirname "$0")/../.." && pwd)
if [[ -z ${MLF_PACKAGE_MANAGER:-} || ! -x $MLF_PACKAGE_MANAGER ]]; then
 echo 'Set MLF_PACKAGE_MANAGER to the native package manager.' >&2; exit 64
fi
if [[ -e $out ]]; then echo 'Use a fresh output directory.' >&2; exit 64; fi
mkdir -p "$out/training/raw"
out=$(cd "$out" && pwd)
node - "$seed" "$frozen" "$llvm" "$out" "${BASH_SOURCE[0]}" <<'CONFIGURE'
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const [seed,frozen,llvm,out,script]=process.argv.slice(2);
const quote=s=>"'"+s.replaceAll("'","'\\''")+"'";
const clang=fs.realpathSync(path.join(llvm,'bin/clang'));
const profile=path.join(out,'training/compiler.profdata');
for(const mode of ['generate','use']){
 const flags=mode==='generate'?['-fprofile-generate='+path.join(out,'training/raw')]:['-fprofile-use='+profile,'-Werror=profile-instr-unprofiled','-Werror=profile-instr-out-of-date'];
 fs.writeFileSync(path.join(out,'clang-'+mode),`#!/bin/bash\nset -euo pipefail\nfor arg in "$@"; do\n if [[ $arg == -O2 ]]; then\n  exec ${quote(clang)} "$@" ${flags.map(quote).join(' ')}\n fi\ndone\nexec ${quote(clang)} "$@"\n`,{mode:0o755});
}
const sha256={};const add=p=>{p=fs.realpathSync(p);sha256[p]=crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')};
function walk(d){for(const n of fs.readdirSync(d)){const p=path.join(d,n);fs.statSync(p).isDirectory()?walk(p):add(p)}}
[seed,clang,path.join(llvm,'bin/llvm-profdata'),script,path.join(out,'clang-generate'),path.join(out,'clang-use')].forEach(add);walk(frozen);
fs.writeFileSync(path.join(out,'training-inputs.json'),JSON.stringify({training:'frozen compiler only',type_weight:4,emission_weight:1,sha256},null,2)+'\n');
CONFIGURE
cd "$root"
"$MLF_PACKAGE_MANAGER" --compiler "$seed" --clang "$out/clang-generate" \
 --build-dir "$out/instrumented" --timeout 21600 build --target emlf > "$out/generate-build.log" 2>&1
LLVM_PROFILE_FILE="$out/training/type.profraw" "$out/instrumented/bin/emlf" \
 -i "$frozen" --type "$frozen/Main.emlf" > "$out/training/type.txt" 2> "$out/training/type.stderr"
LLVM_PROFILE_FILE="$out/training/emit.profraw" "$out/instrumented/bin/emlf" \
 -i "$frozen" --emit-llvm-gc "$frozen/Main.emlf" > "$out/training/compiler.ll" 2> "$out/training/compiler.stderr"
"$llvm/bin/llvm-profdata" merge -output="$out/training/compiler.profdata" \
 -weighted-input=4,"$out/training/type.profraw" -weighted-input=1,"$out/training/emit.profraw"
"$MLF_PACKAGE_MANAGER" --compiler "$seed" --clang "$out/clang-use" \
 --build-dir "$out/candidate" --timeout 21600 build --target emlf > "$out/use-build.log" 2>&1
node - "$out" <<'VERIFY'
const fs=require('fs'),path=require('path'),crypto=require('crypto');const out=process.argv[2];
const r=JSON.parse(fs.readFileSync(path.join(out,'training-inputs.json')));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
for(const [p,h] of Object.entries(r.sha256))if(hash(p)!==h)throw Error('Training input changed: '+p);
for(const rel of ['training/compiler.profdata','training/type.profraw','training/emit.profraw','candidate/bin/emlf']){const p=path.join(out,rel);r.sha256[p]=hash(p)}
r.inputs_unchanged=true;fs.writeFileSync(path.join(out,'provenance.json'),JSON.stringify(r,null,2)+'\n');
VERIFY
