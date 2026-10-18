// Apply only after the current PGO/build/benchmark command has finished.
const fs=require('fs'),base='.mlf-build/compile3',dir=base+'/streaming-source';
fs.mkdirSync(dir);
const files=['tools/bench/llvm-backend.c','tools/bench/configure-backend.cjs','package/Package/Benchmark.emlf'];
for(const p of files)fs.copyFileSync(p,dir+'/'+p.replaceAll('/','__'));
let p=files[0],s=fs.readFileSync(p,'utf8');
s=s.replace('if (argc != 8)', 'if (argc != 8 && argc != 9)').replace('TRIPLE CPU TUNE FEATURES ABI\\n','TRIPLE CPU TUNE FEATURES ABI [ARCHIVE_IR]\\n');
const read='    if (LLVMCreateMemoryBufferWithContentsOfFile(argv[1], &input, &error))\n        fail("read", error);';
if(!s.includes(read))throw Error('Expected input reader');
s=s.replace(read,`    if (argc == 9) {
        /* A fresh process can initialize while its producer checks source.
         * The FIFO carries only that build's complete LLVM text; retain an
         * identical regular file before parsing or optimization. */
        if (!freopen(argv[1], "rb", stdin)) fail("open stream", argv[1]);
        if (LLVMCreateMemoryBufferWithSTDIN(&input, &error)) fail("read stream", error);
        FILE *archive = fopen(argv[8], "wb");
        size_t size = LLVMGetBufferSize(input);
        if (!archive) fail("archive stream", argv[8]);
        if (fwrite(LLVMGetBufferStart(input), 1, size, archive) != size || fclose(archive))
            fail("archive stream", argv[8]);
    } else if (LLVMCreateMemoryBufferWithContentsOfFile(argv[1], &input, &error))
        fail("read", error);`);fs.writeFileSync(p,s);
p=files[1];s=fs.readFileSync(p,'utf8');
const old="const emit=singleBackend ? `exec ${quote(singleBackend)} \"$ir\" \"$output\" ${singleArgs.map(quote).join(' ')}` : `bitcode=$output.opt.bc";
const next="const emit=singleBackend ? `if $stream; then exec ${quote(singleBackend)} \"$ir.pipe\" \"$output\" ${singleArgs.map(quote).join(' ')} \"$ir\"; fi\n exec ${quote(singleBackend)} \"$ir\" \"$output\" ${singleArgs.map(quote).join(' ')}` : `if $stream; then echo 'Streaming requires the single-process LLVM helper' >&2; exit 2; fi\n bitcode=$output.opt.bc";
if(!s.includes(old))throw Error('Expected emission template');
s=s.replace(old,next).replace('compile=false\nirCount=0','compile=false\nstream=false\nirCount=0').replace('  -O2) args+=(-O2) ;;','  --mlf-stream-ir) stream=true ;;\n  -O2) args+=(-O2) ;;');
s=s.replace('const files=[clang,opt,linker,','const files=[\'/bin/bash\',\'/bin/cat\',\'/usr/bin/mkfifo\',clang,opt,linker,');
fs.writeFileSync(p,s);
p=files[2];s=fs.readFileSync(p,'utf8');
const marker='  let frontend = Cons compiler (Cons mode (Cons source Nil))';
const list=xs=>xs.reduceRight((rest,x)=>'Cons '+x+' ('+rest+')','Nil');
const launch=list(['"/bin/bash"','"-o"','"pipefail"','"-c"',JSON.stringify('fifo=$1; shift; "$@" | /bin/cat > "$fifo"'),'"mlf-stream"','(ir ++ ".pipe")','compiler','mode','source']);
if(!s.includes(marker))throw Error('Expected frontend command');
s=s.replace(marker,'  streaming <- getEnv "MLF_BENCH_STREAM_LLVM"\n  O.require (eqString streaming "" || eqString streaming "1") "invalid streaming compiler setting"\n  let stream = eqString streaming "1"\n  let frontend = if stream then '+launch+' else Cons compiler (Cons mode (Cons source Nil))');
s=s.replace('let llvmCommand = S.append (Cons clang (O.words "-O2 -Wno-override-module -c"))','let llvmCommand = S.append (Cons clang (S.append (if stream then Cons "--mlf-stream-ir" Nil else Nil) (O.words "-O2 -Wno-override-module -c")))');
s=s.replace('  let commands = Cons frontend (Cons runtimeCommand (Cons llvmCommand (Cons linkCommand Nil)))','  let ordinary = Cons frontend (Cons runtimeCommand (Cons llvmCommand (Cons linkCommand Nil)))\n  let commands = if stream then Cons (Cons "/usr/bin/mkfifo" (Cons (ir ++ ".pipe") Nil)) ordinary else ordinary');
s=s.replace('  let dependencies = Cons Nil (Cons Nil (Cons (Cons 0 Nil) (Cons (Cons 1 (Cons 2 Nil)) Nil)))','  let dependencies = if stream then Cons Nil (Cons (Cons 0 Nil) (Cons Nil (Cons (Cons 0 Nil) (Cons (Cons 1 (Cons 2 (Cons 3 Nil))) Nil)))) else Cons Nil (Cons Nil (Cons (Cons 0 Nil) (Cons (Cons 1 (Cons 2 Nil)) Nil)))');
s=s.replace('  let outputs = Cons ir (Cons (directory ++ "/runtime.stdout") (Cons (directory ++ "/llvm.stdout") (Cons (directory ++ "/link.stdout") Nil)))','  let ordinaryOutputs = Cons (if stream then directory ++ "/frontend.stdout" else ir) (Cons (directory ++ "/runtime.stdout") (Cons (directory ++ "/llvm.stdout") (Cons (directory ++ "/link.stdout") Nil)))\n  let outputs = if stream then Cons (directory ++ "/setup.stdout") ordinaryOutputs else ordinaryOutputs');
s=s.replace('  let phases = O.words "frontend runtime llvm link"','  let phases = O.words (if stream then "setup frontend runtime llvm link" else "frontend runtime llvm link")');
fs.writeFileSync(p,s);
