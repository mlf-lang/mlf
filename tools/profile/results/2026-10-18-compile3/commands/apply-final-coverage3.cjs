const fs=require('fs'),b='.mlf-build/compile3',backup=b+'/coverage3-before';fs.mkdirSync(backup);
const files=['tests/Tests/Core.emlf','tests/CoreMain.emlf','tests/Tests/NativeABI.emlf','tests/Tests/BenchmarkSuite.emlf','tests/HarnessMain.emlf','tests/mlf-package.json','package/Package/CompilerTests.emlf','bootstrap/Bootstrap/LLVM/Codegen.emlf'];
for(const p of files)fs.copyFileSync(p,backup+'/'+p.replaceAll('/','__'));
let ref=fs.readFileSync(b+'/ComponentReference.emlf','utf8');
const reference=ref.slice(ref.indexOf('-- Find incoming'),ref.indexOf('\ncheck solver'));
const checkComponent=ref.slice(ref.indexOf('check solver'),ref.indexOf('\nchain count')).replace('check solver','checkComponent solver');
const chain=ref.slice(ref.indexOf('chain count'));
let scopes=fs.readFileSync(b+'/ComponentScopesProbe.emlf','utf8');scopes=scopes.slice(scopes.indexOf('check solver'));
scopes=scopes.replaceAll('R.reference','reference').replaceAll('R.check','checkComponent').replaceAll('R.chain','chain').replace('check solver starts =','checkScopes solver starts =').replace('(check solver)','(checkScopes solver)').replace('main = do','scopes : IO Unit\nscopes = do').replace(' putStrLn "378 independently enumerated component and boundary cases passed"',' return Unit');
let projection=fs.readFileSync(b+'/ProjectEnumerationProbe.emlf','utf8');projection=projection.slice(projection.indexOf('check solver'));
projection=projection.replaceAll('N.right','H.right').replaceAll('N.assert','H.assert').replaceAll('N.chain','chain').replace('check solver starts =','checkProjection solver starts =').replace('(check solver)','(checkProjection solver)').replace('main = do','projection : IO Unit\nprojection = do').replace(' putStrLn "180 projection enumerations matched explicit rank lookups"',' return Unit');
const imports=`module Tests.ComponentProjection where
import Bootstrap.Types
import qualified Bootstrap.Std as L
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified Tests.DenseNormalization as N
import qualified Tests.Helpers as H

`;
fs.writeFileSync('tests/Tests/ComponentProjection.emlf',imports+reference+'\n'+checkComponent+'\n'+chain+'\n'+scopes+'\n'+projection+'\nsuite : List (Pair String (IO Unit))\nsuite = Cons (Pair "component scopes agree with independent edge enumeration" scopes) (Cons (Pair "projected nodes preserve explicit rank identities" projection) Nil)\n',{flag:'wx'});
let p='tests/Tests/Core.emlf',s=fs.readFileSync(p,'utf8');s=s.replace('import qualified Tests.IndexEdges as IndexEdges','import qualified Tests.IndexEdges as IndexEdges\nimport qualified Tests.ComponentProjection as ComponentProjection');s=s.replace(/^suite = (.+)$/m,'suite = S.append ComponentProjection.suite ($1)');fs.writeFileSync(p,s);
p='tests/mlf-package.json';let j=JSON.parse(fs.readFileSync(p));function add(x){if(!x||typeof x!=='object')return; if(x['Tests.IndexEdges'])x['Tests.ComponentProjection']='Tests/ComponentProjection.emlf';else for(const v of Object.values(x))add(v);}add(j);fs.writeFileSync(p,JSON.stringify(j,null,2)+'\n');
for(p of ['tests/CoreMain.emlf','package/Package/CompilerTests.emlf']){s=fs.readFileSync(p,'utf8').replaceAll('650','652');fs.writeFileSync(p,s);}
// Exercise the emitted helper itself, including error and collector paths.
fs.copyFileSync(b+'/runtime_inline_force.c','test/runtime_inline_force.c');
let body=fs.readFileSync(b+'/BuildForceProbe.emlf','utf8');body=body.slice(body.indexOf(' code <- O.exec'),body.indexOf(' putStrLn "15 generated force'));
body=body.replaceAll('contains "','H.contains "').replace('  let flags = S.append (O.words "-O2 -std=c11 -Wno-override-module -Iruntime -DMLF_USE_BDWGC -DMLF_COMPACT_BDWGC") (S.append (Cons ("-I" ++ gc ++ "/include") (Cons (gc ++ "/lib/libgc.a") Nil)) (S.append (O.words "-I/opt/homebrew/Cellar/gmp/6.3.0/include -L/opt/homebrew/Cellar/gmp/6.3.0/lib -lgmp -lm") macros))','  let options = S.append (O.words "-O2 -std=c11 -Wno-override-module -Iruntime -DMLF_USE_BDWGC -DMLF_COMPACT_BDWGC") (S.append gc (S.append gmp (S.append (Cons "-lm" Nil) macros)))').replace('Cons "/opt/homebrew/Cellar/llvm/23.1.3/bin/clang-23" flags','Cons "clang" options');
const force='\ngeneratedForce = H.withScratch (\\directory -> do\n compiler <- getEnv "MLF_BOOTSTRAP_COMPILER"\n gc <- collectorFlags directory\n gmp <- flags directory\n let source = "test/runtime_inline_force.c"\n'+body+' )\n';
p='tests/Tests/NativeABI.emlf';s=fs.readFileSync(p,'utf8');const i=s.indexOf('\nsuite =');if(i<0)throw Error('Missing ABI suite');s=s.slice(0,i)+force+s.slice(i);s=s.replace('suite = Cons','suite = Cons (Pair "test_generated_force_preserves_memoization_and_errors" generatedForce) (Cons');s=s.trimEnd()+')\n';fs.writeFileSync(p,s);
p='tests/HarnessMain.emlf';s=fs.readFileSync(p,'utf8');s=s.replace(' waitFor "runtime.started" 300\n O.run "" (O.words "/bin/sleep 0.1")',' fast <- getEnv "MLF_MOCK_FAST_FRONTEND"\n streaming <- getEnv "MLF_BENCH_STREAM_LLVM"\n if eqString fast "1" then return Unit else do\n  waitFor "runtime.started" 300\n  if eqString streaming "1" then waitFor "llvm.launched" 300 else return Unit\n  O.run "" (O.words "/bin/sleep 0.1")');s=s.replace('  ir <- readFile "program.ll"','  if S.elem eqString "--mlf-stream-ir" args then do\n   writeFile "llvm.launched" ""\n   fast <- getEnv "MLF_MOCK_FAST_FRONTEND"\n   if eqString fast "1" then O.run "" (O.words "/bin/sleep 0.05") else return Unit\n   code <- O.exec "" (O.words "/bin/cat program.ll.pipe") "" "program.ll" "stream-read.err" 5\n   H.assert (code == 0) "streaming LLVM archive failed"\n   else return Unit\n  ir <- readFile "program.ll"');s=s.replace('53 native benchmark/bootstrap/release harness tests passed','56 native benchmark/bootstrap/release harness tests passed');fs.writeFileSync(p,s);
p='tests/Tests/BenchmarkSuite.emlf';s=fs.readFileSync(p,'utf8');s=s.replace('buildFailures = do\n','buildFailures = do\n'+fs.readFileSync(b+'/stream-tests.part','utf8'));fs.writeFileSync(p,s);
p='package/Package/CompilerTests.emlf';s=fs.readFileSync(p,'utf8').replace('53 native benchmark/bootstrap/release harness tests passed','56 native benchmark/bootstrap/release harness tests passed').replace('MLF_BOOTSTRAP_INTERPRETER MLF_BOOTSTRAP_LLVM','MLF_BENCH_STREAM_LLVM MLF_BENCH_MLF_CLANG MLF_MOCK_FAST_FRONTEND MLF_BOOTSTRAP_INTERPRETER MLF_BOOTSTRAP_LLVM');fs.writeFileSync(p,s);
p='bootstrap/Bootstrap/LLVM/Codegen.emlf';s=fs.readFileSync(p,'utf8').replace('-- Runtime fallback preserves null/cycle errors and evaluates deferred values.','-- A single thunk can use its own update root directly. Mark it busy before\n-- calling, clear captures through its callback, then force and memoize its\n-- result. Runtime fallback preserves null/cycle errors and longer spines.');fs.writeFileSync(p,s);
