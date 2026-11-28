-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.TestCompilation where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Package.OS as O;
  import qualified Package.Json as J;
  import qualified Package.Build as B;
  import qualified Package.Manifest as M;
  import qualified Package.Command as C;
  import qualified Tests.TestSources as Sources;

  -- Only immutable compilation products live in Package.Build's checked store.
  -- Test invocations, assertions, input streams and runtime observations never
  -- enter these keys. A fresh/cold test selects a private cache in its Builder.
  data Service = Service B.Builder;
  fromBuilder :: B.Builder -> Service;
  fromBuilder value = Service value;
  builder :: Service -> B.Builder;
  builder (Service value) = value;
  -- A stage service owns compilation products, not the repository's package
  -- build plan. Its real command-only context avoids reparsing unrelated source
  -- packages for each test matrix; each stage captures its actual inputs below.
  workingDirectory :: Service -> String;
  workingDirectory (Service b) =
    J.getText "test-working-directory" (B.root b) (B.config b);
  open :: String -> String -> String -> String -> IO Service;
  open root compiler cache directory = openWith root
    (B.info [(,) "compiler" (J.str compiler), (,) "cache-dir" (J.str cache)]) directory;
  openWith :: String -> J.Json -> String -> IO Service;
  openWith root settings directory = do {
    actualRoot <- canonicalPath root;
    defaultClang <- O.envDefault "MLF_CLANG" "clang";
    environmentClang <- O.envDefault "CC" defaultClang;
    environmentGC <- getEnv "MLF_GC_PREFIX";
    let { selected = J.set "clang" (J.str (J.getText "clang" environmentClang settings))
            (J.set "gc-prefix" (J.str (J.getText "gc-prefix" environmentGC settings)) settings) };
    producer <- O.which (J.getText "compiler" "emlf" settings);
    O.mkdir directory;
    actualDirectory <- canonicalPath directory;
    let { context = actualDirectory ++ "/context";
          manifest = context ++ "/mlf-package.json";
          probe = B.obj1 "command" (J.stringArray [producer, "--help"]) };
    O.mkdir context;
    J.write manifest
      (B.info [(,) "format" (J.num 1), (,) "name" (J.str "mlf-test-compilation"),
        (,) "version" (J.str "0.1.0"), (,) "tests" (B.obj1 "producer" probe)]);
    graph <- M.load manifest;
    options <- C.configureGC actualRoot
      (J.set "compiler" (J.str producer)
        (J.set "test-working-directory" (J.str actualRoot)
          (J.set "runtime" (J.str (J.getText "runtime"
            (actualRoot ++ "/runtime/mlf_runtime.c") settings))
            (J.set "timeout" (J.str (J.getText "timeout" "1800" settings)) selected))));
    created <- B.create graph options actualDirectory;
    return (Service created)
  };
  -- Keep pkg-config's relative search paths based on the real work directory,
  -- independently of the small private package used for the Builder report.
  gcFlags :: Service -> IO J.Json;
  gcFlags service = B.gcFlagsIn (builder service) (workingDirectory service);
  finish :: Service -> IO ();
  finish (Service value) = do {
    report <- J.read (B.reportPath value);
    S.mapM_ verifyTool
      (J.values (J.getOr "test_compilation_producers" (J.Array []) report));
    verifyNativeEnvironment value;
    B.finish value
  };
  -- Version the stage protocol when its interpretation changes. The actual
  -- producer/tool bytes identify executable semantics; the calling suite's
  -- binary is verified in its own Builder report, not part of a shared key.
  stage :: String -> J.Json -> J.Json;
  stage name inputs = J.set "test_compilation" (J.str ("v1/" ++ name)) inputs;
  verifyFile :: String -> String -> IO ();
  verifyFile path expected = do {
    actual <- fileDigest path;
    O.require (eqString actual expected) ("test compilation input changed: " ++ path)
  };
  verifyTool :: J.Json -> IO ();
  verifyTool identity = verifyFile (J.getText "path" "" identity)
    (J.getText "sha256" "" identity);
  verifyNative :: B.Builder -> IO ();
  verifyNative b = do {
    verifyTool (J.get "clang" (B.tools b));
    verifyNativeEnvironment b
  };
  verifyNativeEnvironment :: B.Builder -> IO ();
  verifyNativeEnvironment b =
    S.mapM_ (\entry -> do {
      actual <- getEnv (S.fst entry);
      O.require (eqString actual (J.text (S.snd entry)))
        ("native environment changed during test compilation: " ++ S.fst entry)
    }) (J.items (J.get "native_environment" (B.tools b)));
  -- Stable suite invocations register each producer once. Warm lookups need
  -- only artifact/input-byte checks; finish validates the tool snapshot before
  -- the invocation can qualify. A miss checks it around the actual command,
  -- before publication, so a changed tool cannot poison the shared store.
  registerProducer :: Service -> String -> IO J.Json;
  registerProducer (Service b) producer = do {
    identity <- B.tool producer;
    B.record b "test_compilation_producers" identity;
    return identity
  };
  failurePrefix :: String;
  failurePrefix = "MLF test compilation failed: ";
  reject :: Int -> String -> String -> IO ();
  reject code out err = ioError (userError (textToChars
    (failurePrefix ++ J.render (B.info [(,) "exit_code" (J.num code),
      (,) "stdout" (J.str out), (,) "stderr" (J.str err)]))));
  recover :: IO String -> IO (Either ((,,) Int String String) String);
  recover action = catchIOError (do { value <- action; return (Right value) })
    (\error -> let { message = textFromChars (ioeGetErrorString error) } in
      if O.starts failurePrefix message then
        case J.parse (O.drop (stringLength failurePrefix) message) of {
          Left _ -> ioError error;
          Right result -> return (Left ((,,) (case J.get "exit_code" result of { J.Number value -> readInt value; _ -> (0 - 1) })
            (J.getText "stdout" "" result) (J.getText "stderr" "" result)))
        }
      else ioError error);
  requireArtifact :: Either ((,,) Int String String) String -> IO String;
  requireArtifact result = case result of {
    Right path -> return path;
    Left ((,,) code out err) -> O.fatal ("test compilation failed (" ++ showInt code ++
      "): " ++ err ++ out)
  };
  -- Retain diagnostics in this invocation's command report. Rejected processes
  -- throw only inside the checked store's exception-safe lock/staging scope.
  -- The outer recover converts them back to ordinary test failure data.
  command :: B.Builder -> String -> [] String -> String -> Int -> Bool -> IO String;
  command b cwd argv output seconds quiet = do {
    report <- J.read (B.reportPath b);
    let { stem = B.directory b ++ "/commands/" ++
          showInt (S.length (J.values (J.get "commands" report)));
          stdout = stem ++ ".stdout"; stderr = stem ++ ".stderr" };
    code <- O.exec cwd argv "" stdout stderr seconds;
    B.record b "commands" (B.info [(,) "argv" (J.stringArray argv),
      (,) "cwd" (J.str cwd), (,) "exit_code" (J.num code),
      (,) "stdout" (J.str stdout), (,) "stderr" (J.str stderr)]);
    err <- readFile stderr;
    if code /= 0 || (quiet && S.not (eqString err "")) then do {
      out <- readFile stdout;
      reject code out err
    } else return ();
    if eqString output "" then return () else O.copy stdout output;
    return stderr
  };
  checkedSource :: Service -> [] String -> String -> IO String;
  checkedSource service includes source = checkedSourceWith service [] includes source;
  checkedSourceWith :: Service -> [] String -> [] String -> String -> IO String;
  checkedSourceWith (Service b) options includes source = do {
    -- Import roots are a separate ordered input so no option can silently
    -- introduce a dependency outside the closure captured below.
    O.require (S.all (eqString "--no-prelude") options)
      "test source options require explicit include roots (only --no-prelude is supported)";
    inputs <- Sources.sourceInputs includes source;
    let { producer = J.get "compiler" (B.tools b);
          identity = stage "checked-source"
            (B.info [(,) "producer" producer, (,) "source" inputs,
              (,) "options" (J.stringArray options)]);
          verify = do {
            current <- Sources.sourceInputs includes source;
            O.require (J.equal current inputs)
              "test source resolution changed during compilation"
          } };
    verify;
    attempt <- recover (B.cached b "test checked source" identity (\work -> do {
      verifyTool producer;
      verify;
      errors <- command b (J.getText "cwd" "" inputs)
        (S.append [(B.compiler b)] (S.append options
          (S.append (S.concatMap (\path -> ["-i", path]) includes) [source])))
        (work ++ "/target.xmlf") 1800 False;
      O.copy errors (work ++ "/source.stderr");
      checked <- command b (J.getText "cwd" "" inputs)
        [B.compiler b, "--check", work ++ "/target.xmlf"]
        (work ++ "/checked.type") 1800 False;
      verify;
      verifyTool producer
    }));
    verify;
    requireArtifact attempt
  };
  emittedLLVM :: Service -> String -> String -> [] String -> String -> Int ->
                 IO (Either ((,,) Int String String) String);
  -- The convenience route captures a fresh identity for each request. It also
  -- supports tests that deliberately replace a producer within one service.
  emittedLLVM service producer mode options target seconds = do {
    identity <- B.tool producer;
    result <- emittedLLVMWithIdentity service identity mode options target seconds;
    verifyTool identity;
    return result
  };
  emittedLLVMWithIdentity :: Service -> J.Json -> String -> [] String -> String -> Int ->
                             IO (Either ((,,) Int String String) String);
  -- identity must come from registerProducer for the current invocation. The
  -- producer path is verified but only its bytes identify emission, allowing
  -- identical copied drivers in distinct suite directories to share products.
  emittedLLVMWithIdentity (Service b) identity mode options target seconds = do {
    digest <- fileDigest target;
    let { inputs = stage "serialized-llvm"
            (B.info [(,) "producer_sha256" (J.get "sha256" identity),
              (,) "mode" (J.str mode), (,) "options" (J.stringArray options),
              (,) "target_sha256" (J.str digest),
              (,) "system" (J.get "system" (B.tools b)),
              (,) "machine" (J.get "machine" (B.tools b))]);
          verify = verifyFile target digest };
    verify;
    result <- recover (B.cached b "test serialized LLVM" inputs (\work -> do {
      verifyTool identity;
      verify;
      ignored <- command b (workingDirectory (Service b))
        (S.append [J.getText "path" "" identity, mode] (S.append options [target]))
        (work ++ "/program.ll") seconds True;
      verify;
      verifyTool identity
    }));
    verify;
    return result
  };
  -- Match Package.Build.nativeLLVMObject's key and flags so a driver and a
  -- fixture with identical LLVM can reuse its existing object artifact.
  llvmObjectResult :: Service -> String -> IO (Either ((,,) Int String String) String);
  llvmObjectResult (Service b) llvm = do {
    digest <- fileDigest llvm;
    let { options = B.llvmObjectFlags b J.empty;
          inputs = B.info (S.append
            (S.map (\key -> (,) key (J.get key (B.tools b)))
              (O.words "clang system machine native_environment"))
            [(,) "llvm" (J.str digest), (,) "flags" (J.stringArray options)]);
          verify = do { verifyFile llvm digest; verifyNativeEnvironment b } };
    verify;
    result <- recover (B.cached b "LLVM object" inputs (\work -> do {
      verifyNative b;
      verify;
      ignored <- command b work
        (S.append [B.clang b] (S.append options [llvm, "-o", work ++ "/program.o"]))
        "" 1800 False;
      present <- fileExists (work ++ "/program.o");
      O.require present "test LLVM compiler did not produce an object";
      verify;
      verifyNative b
    }));
    verify;
    return result
  };
  llvmObject :: Service -> String -> IO String;
  llvmObject service llvm = do {
    result <- llvmObjectResult service llvm;
    requireArtifact result
  };
  matchingNative :: Service -> J.Json -> [] String -> IO J.Json;
  matchingNative service identity flags =
    if J.equal (J.get "flags" identity) (J.stringArray flags)
    then return identity
    else nativeIdentity service flags;
  -- This convenience route preserves the caller's original single Clang
  -- compile-and-link command. Trailing optimization, target and sanitizer
  -- options therefore still affect LLVM compilation as well as linking.
  nativeLLVMWithIdentityResult :: Service -> J.Json -> String -> [] String -> [] String ->
                                  IO (Either ((,,) Int String String) String);
  nativeLLVMWithIdentityResult service@(Service b) prepared llvm objects flags = do {
    native <- matchingNative service prepared flags;
    let { paths = (:) llvm objects; options = O.words "-O2 -Wno-override-module" };
    hashes <- B.hashFiles paths;
    let { inputs = stage "llvm-executable"
            (J.set "llvm" (J.get llvm hashes)
              (J.set "objects" (J.Array (S.map (\path -> J.get path hashes) objects))
                (J.set "flags" (J.stringArray (S.append options flags))
                  (nativeInputs service native))));
          verify = do {
            B.verifyHashes hashes;
            B.verifyHashes (J.get "headers" native);
            B.verifyHashes (J.get "libraries" native);
            verifyNativeEnvironment b
          } };
    verify;
    result <- recover (B.cached b "test LLVM executable" inputs (\work -> do {
      verifyNative b;
      verify;
      ignored <- command b (workingDirectory (Service b))
        (S.append ((:) (B.clang b) options) (S.append paths
          (S.append flags ["-o", B.executable b (work ++ "/program")])))
        "" 1800 False;
      present <- fileExists (B.executable b (work ++ "/program"));
      O.require present "test LLVM compiler did not produce an executable";
      B.copyWindowsFiles b work;
      verify;
      verifyNative b
    }));
    verify;
    return result
  };
  nativeLLVMResult :: Service -> String -> [] String -> [] String ->
                      IO (Either ((,,) Int String String) String);
  nativeLLVMResult service llvm objects flags = do {
    native <- nativeIdentity service flags;
    nativeLLVMWithIdentityResult service native llvm objects flags
  };
  nativeLLVM :: Service -> String -> [] String -> [] String -> IO String;
  nativeLLVM service llvm objects flags = do {
    result <- nativeLLVMResult service llvm objects flags;
    requireArtifact result
  };

  -- These native products depend on the actual C/LLVM bytes and native toolchain,
  -- independently of the source frontend that produced a driver's LLVM.
  nativeInputs :: Service -> J.Json -> J.Json;
  nativeInputs (Service builder) native =
    J.set "native" native
      (B.info
         (S.map (\key -> (,) key (J.get key (B.tools builder)))
            (O.words "clang system machine native_environment windows")));
  -- pkg-config may omit -L for a library in the compiler's default search path.
  -- Fingerprint those resolved files as well as explicit library/include paths.
  nativeIdentity :: Service -> [] String -> IO J.Json;
  nativeIdentity (Service builder) flags =
    do {
      explicit <- B.flagIdentity flags;
      implicit <-
        S.mapM
          (\flag ->
             do {
               candidates <-
                 S.mapM
                   (\suffix ->
                      do {
                        let {
                          name = ("lib" ++ (O.drop 2 flag ++ suffix))
                        };
                        text <-
                          B.capture builder (workingDirectory (Service builder))
                            ((:) (B.clang builder) ((:) ("-print-file-name=" ++ name) []))
                            ""
                            "";
                        let {
                          path =
                            if O.ends "\r\n" text
                            then stringSlice text 0 (stringLength text - 2)
                            else if O.ends "\n" text
                                 then stringSlice text 0 (stringLength text - 1)
                                 else text
                        };
                        present <- fileExists path;
                        if present
                        then do {
                               actual <- canonicalPath path;
                               return (Just actual)
                             }
                        else return Nothing
                      })
                   (O.words ".dylib .so .dll.a .a");
               return (S.catMaybes candidates)
             })
          (S.filter (O.starts "-l") flags);
      libraries <-
        B.hashFiles
          (S.append (S.map S.fst (J.items (J.get "libraries" explicit))) (S.concat implicit));
      let {
        identity = J.set "libraries" libraries explicit
      };
      B.record builder "native_inputs" identity;
      return identity
    };
  -- Clang emits Make words, whose quotes are literal filename characters. Shell
  -- word parsing would drop apostrophes and double quotes from dependency paths.
  dependencyWords :: String -> [] String;
  dependencyWords source = dependencyWordsAt source 0 "" [];
  dependencyWordsAt :: String -> Int -> String -> [] String -> [] String;
  dependencyWordsAt source offset word done =
    if (offset >= stringLength source)
    then S.reverse (if eqString word "" then done else (:) word done)
    else let {
           c = stringCodeAt source offset
         } in
         if ((c == 92) && ((offset + 1) < stringLength source))
         then let {
                next = stringCodeAt source (offset + 1)
              } in
              if (next == 10)
              then dependencyWordsAt source (offset + 2) word done
              else if ((next == 13) &&
                       (((offset + 2) < stringLength source) &&
                        (stringCodeAt source (offset + 2) == 10)))
                   then dependencyWordsAt source (offset + 3) word done
                   else if (J.space next || ((next == 35) || ((next == 92) || (next == 58))))
                        then dependencyWordsAt source (offset + 2)
                               (word ++ O.char source (offset + 1))
                               done
                        else dependencyWordsAt source (offset + 1) (word ++ "\\") done
         else if ((c == 36) &&
                  (((offset + 1) < stringLength source) &&
                   (stringCodeAt source (offset + 1) == 36)))
              then dependencyWordsAt source (offset + 2) (word ++ "$") done
              else if J.space c
                   then dependencyWordsAt source (offset + 1) ""
                          (if eqString word "" then done else (:) word done)
                   else dependencyWordsAt source (offset + 1) (word ++ O.char source offset) done;
  cObject :: Service -> J.Json -> String -> J.Json -> [] String -> IO String;
  -- Include the headers Clang actually resolves, including default include
  -- directories and SDK headers that need not appear as explicit -I flags.
  cObject (Service builder) native source dependencies options =
    do {
      text <-
        B.capture builder (workingDirectory (Service builder))
          (S.append ((:) (B.clang builder) options)
             ((:) "-M" ((:) "-MT" ((:) "test-driver" ((:) source [])))))
          ""
          "";
      let {
        paths = S.drop 1 (dependencyWords text)
      };
      O.require (S.not (S.null paths)) "test driver C dependency scan produced no files";
      headers <- B.hashFiles paths;
      B.record builder "native_inputs" (B.obj2 "headers" headers "libraries" J.empty);
      let {
        inputs =
          J.set "format" (J.num 1)
            (J.set "compiler_dependencies" headers
               (J.set "source" (J.str source)
                  (J.set "source_files" dependencies
                     (J.set "flags" (J.stringArray options) (nativeInputs (Service builder) native)))))
      };
      verifyNativeEnvironment builder;
      artifact <-
        B.cached builder "test driver C object" inputs
          (\work ->
             do {
               verifyNative builder;
               ignored <-
                 B.capture builder (workingDirectory (Service builder))
                   (S.append ((:) (B.clang builder) options)
                      ((:) "-c" ((:) source ((:) "-o" ((:) (work ++ "/object.o") [])))))
                   ""
                   "";
               present <- fileExists (work ++ "/object.o");
               O.require present "test driver C compiler did not produce an object";
               B.verifyHashes dependencies;
               B.verifyHashes headers;
               verifyNative builder
             });
      B.verifyHashes dependencies;
      B.verifyHashes headers;
      verifyNativeEnvironment builder;
      return artifact
    };
  -- Object ordering and duplicate inputs affect linking; preserve both while
  -- excluding suite-local paths from the identity of equal immutable bytes.
  linkObjectsResult :: Service -> J.Json -> [] String -> [] String ->
                       IO (Either ((,,) Int String String) String);
  linkObjectsResult service@(Service b) prepared paths flags = do {
    native <- matchingNative service prepared flags;
    hashes <- B.hashFiles paths;
    let { options = O.words "-O2 -Wno-override-module";
          inputs = stage "native-link"
            (J.set "objects" (J.Array (S.map (\path -> J.get path hashes) paths))
              (J.set "flags" (J.stringArray (S.append options flags))
                (nativeInputs service native)));
          verify = do {
            B.verifyHashes hashes;
            B.verifyHashes (J.get "headers" native);
            B.verifyHashes (J.get "libraries" native);
            verifyNativeEnvironment b
          } };
    verify;
    result <- recover (B.cached b "test native link" inputs (\work -> do {
      verifyNative b;
      verify;
      ignored <- command b (workingDirectory (Service b))
        (S.append ((:) (B.clang b) options) (S.append paths
          (S.append flags ["-o", B.executable b (work ++ "/program")])))
        "" 1800 False;
      present <- fileExists (B.executable b (work ++ "/program"));
      O.require present "test linker did not produce an executable";
      B.copyWindowsFiles b work;
      verify;
      verifyNative b
    }));
    verify;
    return result
  };
  linkObjects :: Service -> J.Json -> [] String -> [] String -> IO String;
  linkObjects service native paths flags = do {
    result <- linkObjectsResult service native paths flags;
    requireArtifact result
  };
  linkObject :: Service -> J.Json -> String -> [] String -> [] String -> IO String;
  linkObject service native llvm objects flags =
    linkObjects service native ((:) (llvm ++ "/program.o") objects) flags;
  -- Read the checked cache decision made by this group's builder. Never infer
  -- reuse from the mere presence of a file or from a matching binary elsewhere.
  receipt :: Service -> String -> IO J.Json;
  receipt (Service builder) artifact =
    do {
      saved <- J.read (artifact ++ "/artifact.json");
      let {
        key = J.getText "key" "" saved
      };
      valid <- B.cacheValid artifact key;
      O.require valid "test driver artifact changed before recording";
      report <- J.read (B.reportPath builder);
      let {
        rows =
          S.filter (\row -> eqString (J.getText "key" "" row) key)
            (J.values (J.get "builds" report))
      };
      O.require (S.not (S.null rows)) "test driver artifact has no group build receipt";
      hash <- fileDigest (artifact ++ "/artifact.json");
      return
        (J.set "directory" (J.str artifact)
           (J.set "artifact_sha256" (J.str hash)
              (J.set "files" (J.get "files" saved) (S.last rows))))
    }
}
