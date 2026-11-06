-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.NativeBuild (run) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.CompilerCore as Core;
  import qualified MLF.PreparedCompiler as Prepared;
  import qualified MLF.PreparedNativeData as Native;
  import qualified Package.Json as J;
  import qualified Package.OS as O;

  fatal :: forall a. String -> IO a;
  fatal message = do { putErr ("emlf: " ++ message ++ "\n"); exitWith 1; panic "exitWith returned" };
  require condition message = if condition then ioReturn () else fatal message;
  data Options = Options PreludeMode ([] String) String String String;
  parse :: Options -> [] String -> Either String Options;
  parse options args = case args of {
    [] -> case options of {
      Options _ _ source output _ -> if eqString source "" || eqString output ""
        then Left "usage: emlf [-i DIR ...] SOURCE -o OUTPUT [--build-dir FRESH]" else Right options
    };
    (:) argument rest -> case options of {
      Options mode paths source output build ->
        if eqString argument "-o" then case rest of {
          (:) value tail -> if eqString output "" then parse (Options mode paths source value build) tail
            else Left "duplicate output option";
          _ -> Left "-o requires an output path"
        } else if eqString argument "--build-dir" then case rest of {
          (:) value tail -> if eqString build "" then parse (Options mode paths source output value) tail
            else Left "duplicate build directory";
          _ -> Left "--build-dir requires a fresh directory"
        } else if eqString argument "-i" then case rest of {
          (:) value tail -> parse (Options mode (S.snoc paths value) source output build) tail;
          _ -> Left "-i requires a module search directory"
        } else if O.starts "-i" argument && stringLength argument > 2 then
          parse (Options mode (S.snoc paths (O.drop 2 argument)) source output build) rest
        else if eqString argument "--no-prelude" then parse (Options NoImplicitPrelude paths source output build) rest
        else if O.starts "-" argument then Left ("unknown compilation option: " ++ argument)
        else if eqString source "" then parse (Options mode paths argument output build) rest
        else Left "executable compilation accepts exactly one source file"
    }
  };
  exists path = do { file <- fileExists path; dir <- directoryExists path; ioReturn (file || dir) };
  ensureDirectory path = do {
    present <- directoryExists path;
    if present then ioReturn () else O.mkdir path
  };
  -- canonicalPath requires an existing filesystem object. Resolve the nearest
  -- existing parent before checking a destination that will be created later.
  destinationPath :: String -> IO String;
  destinationPath path = do {
    present <- exists path;
    if present then canonicalPath path else do {
      let { parent = O.parent path; name = O.base path };
      require (S.not (eqString parent path)) ("cannot resolve destination: " ++ path);
      resolved <- destinationPath parent;
      ioReturn (if eqString name "." then resolved else if eqString name ".."
        then O.parent resolved else O.join resolved name)
    }
  };
  freshDirectory path = do {
    present <- exists path;
    require (S.not present) ("build directory must be fresh: " ++ path);
    ensureDirectory (O.parent path);
    code <- O.exec "" ["/bin/mkdir", "-m", "700", path] "" "" "" 1800;
    require (code == 0) ("cannot create fresh build directory: " ++ path)
  };
  allocateDirectory :: String -> Int -> IO String;
  allocateDirectory prefix serial = do {
    require (serial < 10000) "too many retained build directories; choose --build-dir";
    let { path = prefix ++ showInt serial };
    present <- exists path;
    if present then allocateDirectory prefix (serial + 1) else do {
      code <- O.exec "" ["/bin/mkdir", "-m", "700", path] "" "" "" 1800;
      if code == 0 then ioReturn path else do {
        raced <- exists path;
        if raced then allocateDirectory prefix (serial + 1) else fatal ("cannot create build directory: " ++ path)
      }
    }
  };
  save build receipt = writeFile (build ++ "/receipt.json") (J.render receipt ++ "\n");
  failBuild :: forall a. String -> J.Json -> String -> IO a;
  failBuild build receipt message = do {
    save build (J.set "error" (J.str message) receipt);
    fatal message
  };
  runPhase build receipt phase command = do {
    let { output = build ++ "/" ++ phase ++ ".stdout"; errors = build ++ "/" ++ phase ++ ".stderr" };
    code <- O.exec "" command "" output errors 1800;
    let { updated = J.add "commands" (J.object [
      (,) "phase" (J.str phase), (,) "command" (J.stringArray command),
      (,) "exit_code" (J.num code), (,) "stdout" (J.str output), (,) "stderr" (J.str errors)]) receipt };
    save build updated;
    if code == 0 then ioReturn updated else failBuild build updated
      (phase ++ " failed; see " ++ errors)
  };
  validateFile row = do {
    let { path = J.getText "path" "" row; digest = J.getText "sha256" "" row };
    require (O.absolute path && stringLength digest == 64) "invalid installed file record";
    present <- fileExists path;
    require present ("installed file missing: " ++ path);
    actual <- fileDigest path;
    require (eqString actual digest) ("installed file changed: " ++ path);
    ioReturn path
  };
  validateFiles rows = S.mapM validateFile rows;
  validateSources inputs = S.mapM (\((,) path expected) -> do {
    actual <- readFile path;
    require (eqString actual expected) ("source changed during compilation: " ++ path);
    digest <- fileDigest path;
    ioReturn (J.object [(,) "path" (J.str path), (,) "sha256" (J.str digest)])
  }) inputs;
  protect output paths = do {
    resolved <- destinationPath output;
    protected <- S.mapM destinationPath paths;
    require (S.not (S.elem eqString resolved protected)) "output would replace a compilation input"
  };
  run :: PreludeMode -> [] String -> [] String -> IO ();
  run mode paths arguments = case parse (Options mode paths "" "" "") arguments of {
    Left message -> fatal message;
    Right (Options selected roots sourceText outputText requestedBuild) -> do {
      source <- canonicalPath sourceText;
      present <- fileExists source;
      require present ("source file missing: " ++ source);
      cwd <- canonicalPath ".";
      let { output = O.join cwd outputText };
      compiler <- getExecutablePath;
      protect output [source, compiler, Native.manifestPath];
      isDirectory <- directoryExists output;
      require (S.not isDirectory) "output is a directory";
      let { initial = J.object [
        (,) "format" (J.str "MLF-NATIVE-PROGRAM-BUILD-2"), (,) "complete" (J.Boolean False),
        (,) "source" (J.str source), (,) "output" (J.str output),
        (,) "compiler" (J.str compiler), (,) "fresh_user_compilation" (J.Boolean True),
        (,) "llvm_jobs" (J.num 1), (,) "commands" (J.array [])] };
      sourceHash <- fileDigest source;
      input <- readFile source;
      result <- Prepared.compileNativeSource selected roots source input;
      case result of {
        Left error -> fatal (Core.prettyError error);
        Right compiled -> case J.parse (Prepared.nativeManifest compiled) of {
          Left message -> fatal message;
          Right installation -> do {
            let { objectRows = J.values (J.get "objects" installation);
                  linkRows = J.values (J.get "link_inputs" installation);
                  flags = J.getStrings "link_args" installation;
                  fallback = Prepared.nativeFallback compiled;
                  count = Prepared.nativeExportCount compiled;
                  inlineCount = Prepared.nativeInlineCount compiled;
                  sourceInputs = Prepared.nativeInputs compiled;
                  receipt = J.set "installation" installation
                    (J.set "source_sha256" (J.str sourceHash)
                    (J.set "fixed_library_reused" (J.Boolean (eqString fallback "" && count > 0))
                    (J.set "stdlib_path" (J.str (if eqString fallback "" then "installed" else "fallback"))
                    (J.set "native_export_count" (J.num count)
                    (J.set "builtin_inline_count" (J.num inlineCount)
                    (J.set "fixed_runtime_reused" (J.Boolean True)
                    (J.set "fallback_reason" (J.str fallback) initial))))))) };
            -- compileNativeSource already authenticated this exact manifest
            -- and its files. Keep their paths for destination protection; the
            -- bytes are checked again immediately before and after linking.
            let { objects = S.map (J.getText "path" "") objectRows;
                  dependencies = S.map (J.getText "path" "") linkRows };
            clang <- validateFile (J.get "clang" installation);
            protect output (S.append [source, compiler, Native.manifestPath, clang]
              (S.append (S.map S.fst sourceInputs) (S.append objects dependencies)));
            canonicalOutput <- destinationPath output;
            sourceRoots <- S.mapM canonicalPath (J.getStrings "source_roots" installation);
            require (S.not (S.any (\root -> O.starts (root ++ "/") canonicalOutput || eqString root canonicalOutput) sourceRoots))
              "output would modify an installed standard-library source directory";
            let { selectedBuild = if eqString requestedBuild "" then
                    O.join (O.parent output) (".emlf-" ++ O.base output ++ "-")
                    else O.join cwd requestedBuild };
            canonicalBuild <- destinationPath selectedBuild;
            require (S.not (S.any (\root -> O.starts (root ++ "/") canonicalBuild || eqString root canonicalBuild) sourceRoots))
              "build directory would modify an installed standard-library source directory";
            validateSources sourceInputs;
            ensureDirectory (O.parent output);
            build <- if eqString requestedBuild "" then allocateDirectory selectedBuild 0 else do {
              freshDirectory selectedBuild;
              ioReturn selectedBuild
            };
            protect output (S.map (\name -> build ++ "/" ++ name)
              ["receipt.json", "program.ll", "program.o", "program", "llvm.stdout", "llvm.stderr", "link.stdout", "link.stderr"]);
            require (S.not (eqString output build)) "output is the build directory";
            save build receipt;
            writeFile (build ++ "/program.ll") (S.concatStrings (Prepared.nativeChunks compiled));
            afterLLVM <- runPhase build receipt "llvm"
              [clang, "-O2", "-Wno-override-module", "-c", build ++ "/program.ll", "-o", build ++ "/program.o"];
            validateFiles objectRows;
            validateFiles linkRows;
            afterLink <- runPhase build afterLLVM "link"
              (S.append [clang, build ++ "/program.o"]
                (S.append objects (S.append flags ["-o", build ++ "/program"])));
            validateFiles objectRows;
            validateFiles linkRows;
            sourceRows <- validateSources sourceInputs;
            sourceAfter <- fileDigest source;
            require (eqString sourceHash sourceAfter) "source changed during compilation";
            publish <- allocateDirectory (O.join (O.parent output) ".emlf-publish-") 0;
            -- Paths are positional arguments to a fixed script, never shell
            -- source. One supervised process owns publication and cleanup.
            O.run "" ["/bin/sh", "-c",
              "/bin/cp -p \"$1\" \"$2/program\" && /bin/mv -f \"$2/program\" \"$3\" && /bin/rmdir \"$2\"",
              "emlf-publish", build ++ "/program", publish, output];
            outputHash <- fileDigest output;
            llvmHash <- fileDigest (build ++ "/program.ll");
            objectHash <- fileDigest (build ++ "/program.o");
            save build (J.set "source_inputs" (J.array sourceRows) (J.set "complete" (J.Boolean True)
              (J.set "output_sha256" (J.str outputHash)
              (J.set "llvm_sha256" (J.str llvmHash)
              (J.set "user_object_sha256" (J.str objectHash) afterLink)))));
            putStrLn (build ++ "/receipt.json")
          }
        }
      }
    }
  }
}
