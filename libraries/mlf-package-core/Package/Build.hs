-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Package.Build where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Lexer as Lexer;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.Host as Host;
  import qualified Package.OS as O;
  import qualified Package.Json as J;
  import qualified Package.Manifest as M;
  import qualified Package.Release as R;
  data Builder = Builder M.PackageGraph J.Json String J.Json J.Json;
  config :: Builder -> J.Json;
  config (Builder _ c _ _ _) = c;
  graph :: Builder -> M.PackageGraph;
  graph (Builder g _ _ _ _) = g;
  directory :: Builder -> String;
  directory (Builder _ _ d _ _) = d;
  cacheDirectory :: Builder -> String;
  cacheDirectory b = J.getText "cache-dir" (directory b ++ "/cache") (config b);
  tools :: Builder -> J.Json;
  tools (Builder _ _ _ t _) = t;
  initial :: Builder -> J.Json;
  initial (Builder _ _ _ _ s) = s;
  root :: Builder -> String;
  root b = M.packageRoot (M.rootPackage (graph b));
  compiler :: Builder -> String;
  compiler b = J.getText "path" "" (J.get "compiler" (tools b));
  clang :: Builder -> String;
  clang b = J.getText "path" "" (J.get "clang" (tools b));
  reportPath :: Builder -> String;
  reportPath b = (directory b ++ "/build-report.json");
  record :: Builder -> String -> J.Json -> IO ();
  record b key value =
    do {
      report <- J.read (reportPath b);
      J.write (reportPath b) (J.add key value report)
    };
  info :: [] ((,) String J.Json) -> J.Json;
  info fields = J.Object fields;
  obj1 :: String -> J.Json -> J.Json;
  obj1 k v = J.Object ((:) ((,) k v) []);
  obj2 :: String -> J.Json -> String -> J.Json -> J.Json;
  obj2 k v l w = J.Object ((:) ((,) k v) ((:) ((,) l w) []));
  hashFiles :: [] String -> IO J.Json;
  hashFiles paths =
    do {
      rows <-
        S.mapM
          (\path ->
             do {
               hash <- fileDigest path;
               ioReturn ((,) path (J.str hash))
             })
          (S.sortBy compareString (S.nubBy eqString paths));
      ioReturn (J.Object rows)
    };
  tool :: String -> IO J.Json;
  tool name =
    do {
      path <- O.which name;
      hash <- fileDigest path;
      ioReturn (obj2 "path" (J.str path) "sha256" (J.str hash))
    };
  raw :: String -> [] String -> IO String;
  raw directory argv =
    do {
      let {
        output = (directory ++ "/query.out")
      };
      let {
        errors = (directory ++ "/query.err")
      };
      code <- O.exec "" argv "" output errors 1800;
      if (code /= 0)
      then do {
             error <- readFile errors;
             O.fatal
               ("command failed (" ++
                (showInt code ++ ("): " ++ (S.intercalate " " argv ++ ("\n" ++ error)))))
           }
      else readFile output
    };
  -- Keep temporary directories on the destination filesystem. Each allocation
  -- has a new owner identity: a child surviving a killed lock owner cannot write
  -- into staging that a later owner publishes. Preserve whitespace in paths.
  temporaryDirectory :: String -> String -> IO String;
  temporaryDirectory scratch prefix = O.temporaryDirectory scratch prefix;
  -- pkg-config uses shell-style quoting in its output; decode words without
  -- executing them. In particular, escaped spaces remain in one argv entry.
  flags :: String -> [] String;
  flags text = flagsAt text 0 0 False "" [];
  flagsAt :: String -> Int -> Int -> Bool -> String -> [] String -> [] String;
  flagsAt text i quote escaped word acc =
    if (i >= stringLength text)
    then if ((quote /= 0) || escaped)
         then panic "invalid pkg-config quoting"
         else S.reverse (if eqString word "" then acc else (:) word acc)
    else let {
           c = stringCodeAt text i
         } in
         if escaped
         then flagsAt text (i + 1) quote False (word ++ O.char text i) acc
         else if ((c == 92) && (quote /= 39))
              then flagsAt text (i + 1) quote True word acc
              else if (quote /= 0)
                   then if (c == quote)
                        then flagsAt text (i + 1) 0 False word acc
                        else flagsAt text (i + 1) quote False (word ++ O.char text i) acc
                   else if ((c == 34) || (c == 39))
                        then flagsAt text (i + 1) c False word acc
                        else if J.space c
                             then flagsAt text (i + 1) 0 False ""
                                    (if eqString word "" then acc else (:) word acc)
                             else flagsAt text (i + 1) 0 False (word ++ O.char text i) acc;
  libraryFiles :: [] String -> IO ([] String);
  libraryFiles flags =
    do {
      let {
        dirs = S.map (O.drop 2) (S.filter (O.starts "-L") flags)
      };
      selected <-
        S.mapM
          (\flag ->
             do {
               present <- fileExists flag;
               if present
               then do {
                      path <- canonicalPath flag;
                      ioReturn ((:) path [])
                    }
               else if O.starts "-l" flag
                    then do {
                           candidates <-
                             S.mapM
                               (\dir ->
                                  S.mapM
                                    (\suffix ->
                                       do {
                                         let {
                                           path = (dir ++ ("/lib" ++ (O.drop 2 flag ++ suffix)))
                                         };
                                         yes <- fileExists path;
                                         if yes
                                         then do {
                                                actual <- canonicalPath path;
                                                ioReturn (Just actual)
                                              }
                                         else ioReturn Nothing
                                       })
                                    ((:) ".dylib" ((:) ".so" ((:) ".dll.a" ((:) ".a" [])))))
                               dirs;
                           ioReturn (S.take 1 (S.mapMaybe S.id (S.concat candidates)))
                         }
                    else ioReturn []
             })
          flags;
      ioReturn (S.concat selected)
    };
  flagIdentity :: [] String -> IO J.Json;
  flagIdentity flags =
    do {
      libraries <- libraryFiles flags;
      hashes <- hashFiles libraries;
      let {
        includes = S.map (O.drop 2) (S.filter (O.starts "-I") flags)
      };
      trees <- S.mapM O.files includes;
      headers <- hashFiles (S.filter (O.ends ".h") (S.concat trees));
      ioReturn
        (info
           ((:) ((,) "flags" (J.stringArray flags))
              ((:) ((,) "libraries" hashes) ((:) ((,) "headers" headers) []))))
    };
  -- Native PGO is an explicit construction option for one root executable.
  -- It never changes the source compiler identity or any other target's flags.
  pgoConfiguration :: M.PackageGraph -> J.Json -> IO J.Json;
  pgoConfiguration graph options =
    do {
      let {
        generate = J.has "pgo-generate" options
      };
      let {
        use = J.has "pgo-use" options
      };
      let {
        selected = J.has "pgo-target" options
      };
      O.require
        (S.not (generate && (use || selected)) && (if use then selected else S.not selected))
        "use either --pgo-generate TARGET or --pgo-target TARGET --pgo-use FILE";
      if S.not (generate || use)
      then ioReturn J.empty
      else do {
             let {
               name = J.getText (if generate then "pgo-generate" else "pgo-target") "" options
             };
             O.require
               (J.has name (J.getObject "executables" (M.packageData (M.rootPackage graph))))
               "PGO target must name a root executable";
             let {
               entry =
                 obj2 "target" (J.str name) "mode" (J.str (if generate then "generate" else "use"))
             };
             if generate
             then ioReturn entry
             else do {
                    path <- canonicalPath (J.getText "pgo-use" "" options);
                    hash <- fileDigest path;
                    ioReturn
                      (J.set "profile" (obj2 "path" (J.str path) "sha256" (J.str hash)) entry)
                  }
           }
    };
  pgoForTarget :: Builder -> M.Package -> String -> J.Json;
  pgoForTarget b p name =
    let {
      profile = J.getObject "native-pgo" (config b)
    } in
    if (eqString (M.packagePath p) (M.packagePath (M.rootPackage (graph b))) &&
        eqString name (J.getText "target" "" profile))
    then profile
    else J.empty;
  pgoFlags :: J.Json -> [] String;
  pgoFlags profile =
    let {
      matchValueShared1 = J.getText "mode" "" profile
    } in
    if MLF.Primitive.eqString matchValueShared1 ""
    then []
    else if MLF.Primitive.eqString matchValueShared1 "generate"
         then (:) "-fprofile-generate" []
         else if MLF.Primitive.eqString matchValueShared1 "use"
              then (:) ("-fprofile-use=" ++ J.getText "path" "" (J.get "profile" profile))
                     (O.words
                        "-Werror=profile-instr-unprofiled -Werror=profile-instr-out-of-date -Werror=backend-plugin")
              else panic "invalid native PGO mode";
  pgoInputs :: J.Json -> J.Json -> J.Json;
  pgoInputs profile inputs =
    if S.null (J.items profile) then inputs else J.set "native-pgo" profile inputs;
  verifyPgo :: J.Json -> IO ();
  verifyPgo profile =
    if eqString (J.getText "mode" "" profile) "use"
    then do {
           let {
             input = J.get "profile" profile
           };
           actual <- fileDigest (J.getText "path" "" input);
           O.require (eqString actual (J.getText "sha256" "" input))
             "native PGO profile changed during build/test"
         }
    else ioReturn ();
  create :: M.PackageGraph -> J.Json -> String -> IO Builder;
  create g options buildDirectory =
    do {
      profile <- pgoConfiguration g options;
      let {
        requestedCache = J.getText "cache-dir" (buildDirectory ++ "/cache") options
      };
      O.mkdir requestedCache;
      cache <- canonicalPath requestedCache;
      O.mkdir (cache ++ "/.locks");
      O.mkdir (buildDirectory ++ "/commands");
      comp <- tool (J.getText "compiler" "emlf" options);
      help <- raw buildDirectory ((:) (J.getText "path" "" comp) ((:) "--help" []));
      let {
        queryReport = S.elem eqString "--query-report" (O.words help)
      };
      implementation <-
        if S.elem eqString "--implementation-identity" (O.words help)
        then raw buildDirectory
               ((:) (J.getText "path" "" comp) ((:) "--implementation-identity" []))
        else ioReturn "legacy-unknown";
      cc <- tool (J.getText "clang" "clang" options);
      pkg <- tool (J.getText "pkg-config" "pkg-config" options);
      manager <- getExecutablePath;
      managerHash <- fileDigest manager;
      system <- raw buildDirectory ((:) "/usr/bin/uname" ((:) "-s" []));
      machine <- raw buildDirectory ((:) "/usr/bin/uname" ((:) "-m" []));
      version <- raw buildDirectory ((:) (J.getText "path" "" cc) ((:) "--version" []));
      windows <- O.isWindows;
      helper <-
        if windows
        then do {
               path <- O.windowsHost;
               tool path
             }
        else ioReturn J.empty;
      prefix <- if windows then O.nativePrefix else ioReturn "";
      dlls <-
        if windows
        then hashFiles
               (S.map (\name -> (prefix ++ ("/bin/" ++ name)))
                  (O.words "libgmp-10.dll libgc-1.dll libwinpthread-1.dll libpkgconf-8.dll"))
        else ioReturn J.empty;
      gmpText <-
        raw buildDirectory ((:) (J.getText "path" "" pkg) (O.words "--cflags --libs gmp"));
      gmp <- flagIdentity (flags gmpText);
      runtimeText <-
        if J.has "runtime" options
        then ioReturn (J.getText "runtime" "" options)
        else raw buildDirectory ((:) (J.getText "path" "" comp) ((:) "--llvm-runtime" []));
      runtime <- canonicalPath (O.trim runtimeText);
      runtimeFiles <- O.entries (O.parent runtime);
      runtimeHashes <-
        hashFiles
          (S.map (O.join (O.parent runtime))
             (S.filter (\n -> (O.ends ".c" n || O.ends ".h" n)) runtimeFiles));
      env <-
        S.mapM
          (\key ->
             do {
               value <- getEnv key;
               ioReturn ((,) key (J.str value))
             })
          (O.words "SDKROOT MACOSX_DEPLOYMENT_TARGET CPATH C_INCLUDE_PATH LIBRARY_PATH");
      snapshot <- M.snapshot g;
      let {
        baseIdentity =
          info
            ((:) ((,) "compiler" comp)
               ((:) ((,) "clang" cc)
                  ((:) ((,) "pkg-config" pkg)
                     ((:)
                        ((,) "manager" (obj2 "path" (J.str manager) "sha256" (J.str managerHash)))
                        ((:) ((,) "system" (J.str (O.trim system)))
                           ((:) ((,) "machine" (J.str (O.trim machine)))
                              ((:) ((,) "native_environment" (J.Object env))
                                 ((:) ((,) "runtime" runtimeHashes)
                                    ((:) ((,) "runtime-path" (J.str runtime))
                                       ((:) ((,) "gmp" gmp) []))))))))))
      };
      let {
        irFlags =
          if (windows && S.any (O.starts "clang version 14.") (O.lines version))
          then O.words "-mllvm -opaque-pointers"
          else []
      };
      let {
        identity =
          J.set "implementation-identity" (J.str (O.trim implementation))
            (J.set "compiler-query-report" (J.Boolean queryReport)
               (J.set "ir-flags" (J.stringArray irFlags)
                  (if windows
                   then J.set "windows"
                          (info
                             ((:) ((,) "helper" helper)
                                ((:) ((,) "prefix" (J.str prefix))
                                   ((:) ((,) "dlls" dlls) []))))
                          baseIdentity
                   else baseIdentity)))
      };
      let {
        b =
          Builder g
            (J.set "build-directory" (J.str buildDirectory)
               (J.set "cache-dir" (J.str cache) (J.set "native-pgo" profile options)))
            buildDirectory
            identity
            snapshot
      };
      J.write (reportPath b)
        (J.set "cache_directory" (J.str cache)
           (info
              ((:) ((,) "format" (J.num 1))
                 ((:) ((,) "complete" (J.Boolean False))
                    ((:) ((,) "implementation" (J.str "MLF"))
                       ((:) ((,) "packages" snapshot)
                          ((:) ((,) "toolchain" identity)
                             ((:) ((,) "commands" (J.Array []))
                                ((:) ((,) "builds" (J.Array []))
                                   ((:) ((,) "tests" (J.Array [])) []))))))))));
      ioReturn b
    };
  -- Workers inherit the coordinator's resolved graph and input snapshot. Each
  -- action gets its own report, command numbering and fingerprint scratch files.
  -- Only the coordinator merges these reports or publishes executable names.
  isolate :: Builder -> String -> IO Builder;
  isolate b path =
    do {
      O.mkdir (path ++ "/commands");
      let {
        worker = Builder (graph b) (config b) path (tools b) (initial b)
      };
      J.write (reportPath worker)
        (info
           ((:) ((,) "complete" (J.Boolean False))
              ((:) ((,) "commands" (J.Array [])) ((:) ((,) "builds" (J.Array [])) []))));
      ioReturn worker
    };
  reportKeys :: [] String;
  reportKeys =
    O.words "commands builds crates releases codegen native_inputs tests pending-publications";
  mergeReport :: Builder -> J.Json -> IO ();
  mergeReport b saved =
    S.mapM_ (\key -> S.mapM_ (record b key) (J.values (J.getOr key (J.Array []) saved)))
      reportKeys;
  mergeReports :: Builder -> [] Builder -> IO ();
  mergeReports b workers =
    S.mapM_
      (\worker ->
         do {
           saved <- J.read (reportPath worker);
           mergeReport b saved
         })
      workers;
  artifactPath :: J.Json -> String;
  artifactPath result = J.getText "artifact" "" result;
  -- Released roots keep their canonical installed paths so a directly selected
  -- release and another release's bundled copy share one compiler identity.
  importPath :: J.Json -> String;
  importPath result = J.getText "import_artifact" (artifactPath result) result;
  capture :: Builder -> String -> [] String -> String -> String -> IO String;
  capture b cwd argv input output =
    do {
      report <- J.read (reportPath b);
      let {
        stem =
          (directory b ++ ("/commands/" ++ showInt (S.length (J.values (J.get "commands" report)))))
      };
      let {
        result = if eqString output "" then (stem ++ ".stdout") else output
      };
      let {
        errors = (stem ++ ".stderr")
      };
      code <- O.exec cwd argv input result errors (readInt (J.getText "timeout" "1800" (config b)));
      record b "commands"
        (info
           ((:) ((,) "argv" (J.stringArray argv))
              ((:) ((,) "cwd" (J.str cwd))
                 ((:) ((,) "exit_code" (J.num code))
                    ((:) ((,) "stdout" (J.str result))
                       ((:) ((,) "stderr" (J.str errors)) []))))));
      if (code /= 0)
      then do {
             error <- readFile errors;
             O.fatal
               ("command failed (" ++
                (showInt code ++ ("): " ++ (S.intercalate " " argv ++ ("\n" ++ error)))))
           }
      else if eqString output "" then readFile result else ioReturn ""
    };
  gcFlags :: Builder -> IO J.Json;
  gcFlags b =
    do {
      let {
        prefix = J.getText "gc-prefix" "" (config b)
      };
      selected <-
        if eqString prefix ""
        then do {
               text <-
                 capture b (root b)
                   ((:) (J.getText "path" "" (J.get "pkg-config" (tools b)))
                      (O.words "--cflags --libs bdw-gc"))
                   ""
                   "";
               ioReturn (flags text)
             }
        else do {
               path <- canonicalPath prefix;
               let {
                 library =
                   (path ++
                    (if eqString (J.getText "system" "" (tools b)) "Windows"
                     then "/lib/libgc.dll.a"
                     else "/lib/libgc.a"))
               };
               present <- fileExists library;
               O.require present ("missing BDWGC library: " ++ library);
               ioReturn
                 ((:) ("-I" ++ (path ++ "/include"))
                    ((:) library
                       (if eqString (J.getText "system" "" (tools b)) "Linux"
                        then (:) "-ldl" []
                        else [])))
             };
      identity <- flagIdentity selected;
      record b "native_inputs" identity;
      ioReturn identity
    };
  stackFlags :: Builder -> [] String;
  stackFlags b =
    if eqString (J.getText "system" "" (tools b)) "Darwin"
    then (:) "-Wl,-stack_size,0x10000000" []
    else if eqString (J.getText "system" "" (tools b)) "Windows"
         then (:) "-Wl,--stack,268435456" []
         else [];
  -- COFF timestamps are not semantic inputs. Keep separately rebuilt objects
  -- byte-identical so content-addressed linking can reuse their actual bytes.
  objectFlags :: Builder -> [] String;
  objectFlags b =
    if J.has "windows" (tools b) then (:) "-mno-incremental-linker-compatible" [] else [];
  executable b path =
    if eqString (J.getText "system" "" (tools b)) "Windows" then (path ++ ".exe") else path;
  windowsFiles b =
    if J.has "windows" (tools b)
    then O.words "libgmp-10.dll libgc-1.dll libwinpthread-1.dll mlf-host.exe"
    else [];
  copyWindowsFiles b destination =
    do {
      let {
        prefix = J.getText "prefix" "" (J.get "windows" (tools b))
      };
      S.mapM_
        (\name ->
           do {
             source <-
               if eqString name "mlf-host.exe"
               then O.windowsHost
               else ioReturn (prefix ++ ("/bin/" ++ name));
             O.copy source (destination ++ ("/" ++ name))
           })
        (windowsFiles b)
    };
  fingerprint :: Builder -> J.Json -> IO String;
  fingerprint b value =
    do {
      J.write (directory b ++ "/fingerprint.json")
        (obj2 "semantic-schema"
           (J.str (Lexer.frontendSemanticVersion ++ ("/" ++ Lexer.builtinInterfaceVersion)))
           "value"
           value);
      fileDigest (directory b ++ "/fingerprint.json")
    };
  validFiles :: String -> J.Json -> IO Bool;
  validFiles destination saved =
    do {
      checks <-
        S.mapM
          (\entry ->
             do {
               let {
                 path = S.fst entry
               };
               if (O.absolute path ||
                   (O.drivePath path || S.elem eqString ".." (O.split 47 (O.normalize path))))
               then ioReturn False
               else do {
                      present <- fileExists (destination ++ ("/" ++ path));
                      if present
                      then do {
                             actual <- fileDigest (destination ++ ("/" ++ path));
                             ioReturn (eqString actual (J.text (S.snd entry)))
                           }
                      else ioReturn False
                    }
             })
          (J.items saved);
      ioReturn (S.not (S.null checks) && S.and checks)
    };
  cacheValid :: String -> String -> IO Bool;
  cacheValid destination key =
    do {
      let {
        stamp = (destination ++ "/artifact.json")
      };
      present <- fileExists stamp;
      if S.not present
      then ioReturn False
      else do {
             text <- readFile stamp;
             case J.parse text of {
               Left _ -> ioReturn False;
               Right value ->
                 case value of {
                   J.Object _ ->
                     if J.equal (J.get "key" value) (J.str key)
                     then case J.get "files" value of {
                            J.Object _ -> validFiles destination (J.get "files" value);
                            _ -> ioReturn False
                          }
                     else ioReturn False;
                   _ -> ioReturn False
                 }
             }
           }
    };
  cached :: Builder -> String -> J.Json -> (String -> IO ()) -> IO String;
  cached b kind inputs action = cachedChecked b kind inputs (\_ -> ioReturn True) action;
  cachedChecked :: Builder ->
                   String -> J.Json -> (String -> IO Bool) -> (String -> IO ()) -> IO String;
  cachedChecked b kind inputs validate action =
    do {
      result <- cachedCheckedResult b kind inputs validate action;
      ioReturn (artifactPath result)
    };
  cachedResult :: Builder -> String -> J.Json -> (String -> IO ()) -> IO J.Json;
  cachedResult b kind inputs action =
    cachedCheckedResult b kind inputs (\_ -> ioReturn True) action;
  cachedCheckedResult :: Builder ->
                         String ->
                         J.Json -> (String -> IO Bool) -> (String -> IO ()) -> IO J.Json;
  cachedCheckedResult b kind inputs validate action =
    do {
      key <- fingerprint b (obj2 "kind" (J.str kind) "inputs" inputs);
      let {
        destination = (cacheDirectory b ++ ("/" ++ key))
      };
      lock <- acquireFileLock (cacheDirectory b ++ ("/.locks/" ++ key));
      ownValid <- cacheValid destination key;
      reusable <- if ownValid then validate destination else ioReturn False;
      if reusable
      then ioReturn ()
      else do {
             putErr ("Building " ++ (kind ++ "\n"));
             work <- temporaryDirectory (directory b) (destination ++ ".work-");
             action work;
             paths <- O.files work;
             hashes <-
               S.mapM
                 (\path ->
                    do {
                      hash <- fileDigest path;
                      ioReturn ((,) (O.relative work path) (J.str hash))
                    })
                 paths;
             O.require (S.not (S.null hashes)) (kind ++ " produced no artifacts");
             J.write (work ++ "/artifact.json")
               (info
                  ((:) ((,) "key" (J.str key))
                     ((:) ((,) "inputs" inputs) ((:) ((,) "files" (J.Object hashes)) []))));
             O.remove destination;
             O.move work destination
           };
      let {
        row =
          info
            ((:) ((,) "kind" (J.str kind))
               ((:) ((,) "key" (J.str key)) ((:) ((,) "cached" (J.Boolean reusable)) [])))
      };
      stamp <- J.read (destination ++ "/artifact.json");
      record b "builds" row;
      releaseFileLock lock;
      ioReturn
        (J.set "artifact" (J.str destination)
           (J.set "receipt" (J.str (destination ++ "/artifact.json"))
              (J.set "files" (J.get "files" stamp) (J.set "builds" (J.Array ((:) row [])) row))))
    };
  -- The package graph orders crates. Module imports only determine namespaces;
  -- declarations inside a crate are resolved and inferred together by the compiler.
  pack :: [] String -> String;
  pack fields =
    S.concatMapString (\value -> (showInt (stringLength value) ++ (":" ++ value))) fields;
  packPair :: (,) String String -> String;
  packPair ((,) a b) = pack ((:) a ((:) b []));
  directLibraries :: M.Package -> [] ((,) String String) -> [] String;
  directLibraries p built =
    S.mapMaybe (\name -> S.lookup eqString name built)
      (S.sortBy compareString (M.keys (J.getObject "dependencies" (M.packageData p))));
  validCrateClosure :: String -> IO Bool;
  -- The ordinary artifact stamp already checks our metadata, object and this
  -- receipt. Its recursive inputs were independently checked when saved;
  -- identical SHA256 bytes can reuse that check without decoding every SCC.
  validCrateClosure destination =
    do {
      present <- fileExists (destination ++ "/dependency-files.json");
      if S.not present
      then ioReturn False
      else do {
             saved <- J.read (destination ++ "/dependency-files.json");
             validDependencyFiles saved
           }
    };
  validDigest value =
    case value of {
      J.String digest ->
        ((stringLength digest == 64) &&
         S.all
           (\i ->
              let {
                c = stringCodeAt digest i
              } in
              (((c >= 48) && (c <= 57)) || ((c >= 97) && (c <= 102))))
           (S.range 0 63));
      _ -> False
    };
  validDependencyShape saved =
    case saved of {
      J.Object entries ->
        let {
          paths = S.map S.fst entries
        } in
        ((S.length paths == S.length (S.nubBy eqString paths)) &&
         S.all (\((,) path digest) -> (Host.absolutePath path && validDigest digest)) entries);
      _ -> False
    };
  validDependencyFiles saved =
    case saved of {
      J.Object entries ->
        do {
          if S.not (validDependencyShape saved)
          then ioReturn False
          else do {
                 matches <-
                   S.mapM
                     (\((,) path expected) ->
                        do {
                          present <- fileExists path;
                          if S.not present
                          then ioReturn False
                          else do {
                                 actual <- fileDigest path;
                                 ioReturn (J.equal expected (J.str actual))
                               }
                        })
                     entries;
                 ioReturn (S.and matches)
               }
        };
      _ -> ioReturn False
    };
  -- A diamond may name one verified file repeatedly, but conflicting SHA256
  -- claims must never be combined into a proof. Reject malformed receipts too.
  mergeDependencyProof left right =
    if S.not (validDependencyShape left && validDependencyShape right)
    then Left "malformed crate dependency proof"
    else do {
           entries <-
             S.foldEither
               (\done ((,) path digest) ->
                  case S.lookup eqString path done of {
                    Nothing -> Right ((:) ((,) path digest) done);
                    Just previous ->
                      if J.equal previous digest
                      then Right done
                      else Left ("conflicting crate dependency proof: " ++ path)
                  })
               (J.items left)
               (J.items right);
           Right (J.Object entries)
         };
  readProofJson path =
    do {
      present <- fileExists path;
      if S.not present
      then ioReturn Nothing
      else do {
             text <- readFile path;
             ioReturn (S.either (\_ -> Nothing) Just (J.parse text))
           }
    };
  validProofStamp artifact stamp =
    case stamp of {
      J.Object _ ->
        case J.get "files" stamp of {
          J.Object files ->
            (validDigest (J.str (O.base artifact)) &&
             (J.equal (J.get "key" stamp) (J.str (O.base artifact)) &&
              (S.all (\name -> J.has name (J.get "files" stamp))
                 (O.words "unit.mlfci unit.mlfco dependency-files.json") &&
               S.all (\((,) _ digest) -> validDigest digest) files)));
          _ -> False
        };
      _ -> False
    };
  verifiedDependencyProof artifact =
    do {
      saved <- readProofJson (artifact ++ "/artifact.json");
      case saved of {
        Nothing -> ioReturn J.empty;
        Just stamp ->
          if S.not (Host.absolutePath artifact && validProofStamp artifact stamp)
          then ioReturn J.empty
          else do {
                 ownValid <- cacheValid artifact (O.base artifact);
                 if S.not ownValid
                 then ioReturn J.empty
                 else do {
                        receipt <- readProofJson (artifact ++ "/dependency-files.json");
                        case receipt of {
                          Nothing -> ioReturn J.empty;
                          Just transitive ->
                            if S.not (validDependencyShape transitive)
                            then ioReturn J.empty
                            else do {
                                   closureValid <- validCrateClosure artifact;
                                   if S.not closureValid
                                   then ioReturn J.empty
                                   else do {
                                          let {
                                            files = J.get "files" stamp
                                          };
                                          receiptHash <-
                                            fileDigest (artifact ++ "/dependency-files.json");
                                          if S.not
                                               (J.equal (J.get "dependency-files.json" files)
                                                  (J.str receiptHash))
                                          then ioReturn J.empty
                                          else case mergeDependencyProof
                                                      (obj2 (artifact ++ "/unit.mlfci")
                                                         (J.get "unit.mlfci" files)
                                                         (artifact ++ "/unit.mlfco")
                                                         (J.get "unit.mlfco" files))
                                                      transitive of {
                                                 Left message -> O.fatal message;
                                                 Right proof -> ioReturn proof
                                               }
                                        }
                                 }
                        }
                      }
               }
      }
    };
  -- Check every claimed path, including transitive paths outside the
  -- metadata graph we are about to consume. A changed proof falls back to
  -- independent decoding rather than authorizing a stale cached check.
  dependencyProofs artifacts =
    do {
      saved <- S.mapM verifiedDependencyProof artifacts;
      case S.foldEither mergeDependencyProof J.empty saved of {
        Left message -> O.fatal message;
        Right proof ->
          do {
            guarded <- validDependencyFiles proof;
            ioReturn (if guarded then proof else J.empty)
          }
      }
    };
  provenCrateFiles proof metadata =
    let {
      object = Artifact.objectPath metadata
    } in
    if S.not (validDependencyShape proof && (J.has metadata proof && J.has object proof))
    then ioReturn False
    else validDependencyFiles (obj2 metadata (J.get metadata proof) object (J.get object proof));
  checkCrateObjects ownMetadata proof interfaces =
    do {
      checked <-
        S.mapM
          (\((,) metadata iface) ->
             do {
               reused <-
                 if eqString metadata ownMetadata
                 then ioReturn False
                 else provenCrateFiles proof metadata;
               if reused
               then ioReturn ((,) True True)
               else do {
                      object <- Artifact.readObject (Artifact.objectPath metadata) iface;
                      ioReturn ((,) (S.either (\_ -> False) (\_ -> True) object) False)
                    }
             })
          interfaces;
      let {
        count = S.length checked
      };
      let {
        reused = S.length (S.filter S.snd checked)
      };
      let {
        report =
          info
            ((:) ((,) "format" (J.num 1))
               ((:) ((,) "object_count" (J.num count))
                  ((:) ((,) "checked_objects" (J.num (count - reused)))
                     ((:) ((,) "reused_objects" (J.num reused))
                        ((:)
                           ((,) "root_checked"
                              (J.Boolean
                                 (S.any (\((,) metadata _) -> eqString metadata ownMetadata)
                                    interfaces)))
                           [])))))
      };
      ioReturn ((,) (S.all S.fst checked) report)
    };
  saveCrateClosure destination directArtifacts =
    do {
      loaded <- Artifact.loadInterfaces ((:) (destination ++ "/unit.mlfci") []);
      case loaded of {
        Left message -> O.fatal ("invalid generated crate dependency closure: " ++ message);
        Right interfaces ->
          do {
            proof <- dependencyProofs directArtifacts;
            ownMetadata <- canonicalPath (destination ++ "/unit.mlfci");
            boundValueShared2 <- checkCrateObjects ownMetadata proof interfaces;
            case boundValueShared2 of {
              (,) checked validation ->
                do {
                  O.require checked "invalid generated crate dependency object";
                  O.require (J.getBool "root_checked" False validation)
                    "generated crate object was not independently checked";
                  let {
                    dependencies =
                      S.filter (\((,) path _) -> S.not (eqString path ownMetadata)) interfaces
                  };
                  hashes <-
                    hashFiles
                      (S.concatMap
                         (\((,) path _) -> (:) path ((:) (Artifact.objectPath path) []))
                         dependencies);
                  J.write (destination ++ "/dependency-files.json") hashes;
                  J.write (destination ++ "/unit.validation.json") validation
                }
            }
          }
      }
    };
  -- Keep declaration identities in the immutable compiler query report. Build
  -- actions repeatedly read their own report, so embed only the bounded summary.
  crateQuerySummary saved =
    J.set "group_count" (J.num (S.length (J.values (J.get "groups" saved))))
      (J.Object (S.filter (\((,) key _) -> S.not (eqString key "groups")) (J.items saved)));
  compileCrate :: Builder ->
                  M.Package ->
                  String -> String -> [] M.Module -> [] String -> Bool -> IO String;
  compileCrate b p kind entry modules dependencies noPrelude =
    do {
      result <- compileCrateResult b p kind entry modules dependencies noPrelude;
      ioReturn (artifactPath result)
    };
  compileCrateResult :: Builder ->
                        M.Package ->
                        String -> String -> [] M.Module -> [] String -> Bool -> IO J.Json;
  -- Keep query storage outside content-addressed crate artifacts so source edits
  -- can reuse checked declaration groups. Compiler identities isolate schemas.
  compileCrateResult b p kind entry modules dependencies noPrelude =
    do {
      let {
        identity = M.crateIdentity p kind
      };
      let {
        ordered = S.sortBy (\a b -> compareString (M.moduleName a) (M.moduleName b)) modules
      };
      sources <-
        S.mapM
          (\m ->
             do {
               hash <- fileDigest (M.moduleSource m);
               text <- readFile (M.moduleSource m);
               syntax <-
                 case Lexer.sourceSyntax (M.moduleSource m) text of {
                   Left error -> O.fatal error;
                   Right value -> ioReturn (Lexer.sourceSyntaxName value)
                 };
               ioReturn
                 ((,) (M.moduleName m)
                    (J.set "syntax" (J.str syntax)
                       (obj2 "path" (J.str (M.moduleSource m)) "sha256" (J.str hash))))
             })
          ordered;
      imports <-
        S.mapM
          (\artifact ->
             do {
               metadata <- fileDigest (artifact ++ "/unit.mlfci");
               object <- fileDigest (artifact ++ "/unit.mlfco");
               ioReturn
                 (info
                    ((:) ((,) "path" (J.str (artifact ++ "/unit.mlfci")))
                       ((:) ((,) "metadata" (J.str metadata))
                          ((:) ((,) "object" (J.str object)) []))))
             })
          dependencies;
      let {
        inputs =
          info
            ((:) ((,) "compiler" (J.get "compiler" (tools b)))
               ((:) ((,) "manager" (J.get "manager" (tools b)))
                  ((:) ((,) "crate" (J.str identity))
                     ((:) ((,) "entry" (J.str entry))
                        ((:) ((,) "no-prelude" (J.Boolean noPrelude))
                           ((:) ((,) "sources" (J.Object sources))
                              ((:) ((,) "dependencies" (J.Array imports)) [])))))))
      };
      let {
        queries =
          (cacheDirectory b ++
           ("/.queries/" ++
            (identity ++ ("/" ++ J.getText "sha256" "" (J.get "compiler" (tools b))))))
      };
      let {
        builtin =
          (cacheDirectory b ++
           ("/.queries/builtin-prelude/" ++
            (J.getText "sha256" "" (J.get "compiler" (tools b)) ++ "/unit")))
      };
      O.mkdir queries;
      O.mkdir (O.parent builtin);
      result <-
        cachedCheckedResult b ("crate " ++ identity) inputs validCrateClosure
          (\work ->
             do {
               let {
                 spec =
                   pack
                     ((:) "MLF-CRATE-1"
                        ((:) identity
                           ((:) entry
                              ((:) (if noPrelude then "true" else "false")
                                 ((:)
                                    (pack
                                       (S.map
                                          (\m ->
                                             packPair ((,) (M.moduleName m) (M.moduleSource m)))
                                          ordered))
                                    ((:)
                                       (pack
                                          (S.map (\path -> (path ++ "/unit.mlfci")) dependencies))
                                       ((:) queries ((:) builtin []))))))))
               };
               writeFile (work ++ "/crate.spec") spec;
               ignored <-
                 capture b work
                   ((:) (compiler b)
                      ((:) "--compile-crate"
                         ((:) (work ++ "/crate.spec") ((:) "-o" ((:) (work ++ "/unit") [])))))
                   ""
                   "";
               S.mapM_
                 (\extension ->
                    do {
                      present <- fileExists (work ++ ("/unit" ++ extension));
                      O.require present ("compiler did not produce crate artifact " ++ extension)
                    })
                 (O.words ".mlfci .mlfco .queries");
               saveCrateClosure work dependencies;
               detailed <- J.read (work ++ "/unit.queries");
               J.write (work ++ "/unit.query-summary.json") (crateQuerySummary detailed);
               O.remove (work ++ "/crate.spec")
             });
      let {
        artifact = artifactPath result
      };
      saved <- J.read (artifact ++ "/unit.query-summary.json");
      validation <- J.read (artifact ++ "/unit.validation.json");
      let {
        reused = J.getBool "cached" False result
      };
      let {
        current =
          if reused
          then J.set "inferred_groups" (J.num 0)
                 (J.set "reused_groups" (J.get "group_count" saved) saved)
          else saved
      };
      let {
        queriesNow =
          J.set "outer_cached" (J.Boolean reused)
            (J.set "cache_source" (J.str (if reused then "crate-artifact" else "inference-queries"))
               current)
      };
      let {
        validationNow =
          J.set "outer_cached" (J.Boolean reused)
            (J.set "cache_source"
               (J.str (if reused then "crate-artifact" else "dependency-receipts"))
               (if reused
                then J.set "root_checked" (J.Boolean False)
                       (J.set "checked_objects" (J.num 0)
                          (J.set "reused_objects" (J.get "object_count" validation) validation))
                else validation))
      };
      let {
        row =
          info
            ((:) ((,) "crate" (J.str identity))
               ((:) ((,) "outer_cached" (J.Boolean reused))
                  ((:) ((,) "metadata" (J.str (artifact ++ "/unit.mlfci")))
                     ((:) ((,) "query_report" (J.str (artifact ++ "/unit.queries")))
                        ((:) ((,) "queries" queriesNow)
                           ((:)
                              ((,) "validation_report"
                                 (J.str (artifact ++ "/unit.validation.json")))
                              ((:) ((,) "validation" validationNow) [])))))))
      };
      record b "crates" row;
      ioReturn
        (J.set "crates" (J.Array ((:) row []))
           (J.set "metadata" (J.str (artifact ++ "/unit.mlfci"))
              (J.set "validation" validationNow result)))
    };
  libraries :: Builder -> Bool -> IO ([] ((,) String String));
  libraries b noPrelude = libraryLoop b noPrelude [] (M.packages (graph b));
  -- A checked release is a library action too. Wrap its relocated root in an
  -- ordinary artifact receipt so workers and final validation use one contract.
  -- Materialization still runs on a cache hit to verify the pinned producer
  -- bundle and repair any damaged installed dependency before receipt reuse.
  libraryResult :: Builder -> M.Package -> [] String -> Bool -> IO J.Json;
  libraryResult b p dependencies noPrelude =
    if S.not (M.isRelease p)
    then compileCrateResult b p "library" "" (M.packageModules p) dependencies noPrelude
    else do {
           let {
             digest = J.getText "release-sha256" "" (M.packageData p)
           };
           let {
             identity = M.crateIdentity p "library"
           };
           path <-
             R.materializePinned (M.packageRoot p) digest (cacheDirectory b)
               (J.getText "sha256" "" (J.get "compiler" (tools b)))
               noPrelude;
           current <- fileDigest (M.packagePath p);
           O.require (eqString current digest) "release manifest SHA-256 changed during import";
           metadata <- fileDigest (path ++ "/unit.mlfci");
           object <- fileDigest (path ++ "/unit.mlfco");
           let {
             inputs =
               info
                 ((:) ((,) "compiler" (J.get "compiler" (tools b)))
                    ((:) ((,) "manager" (J.get "manager" (tools b)))
                       ((:) ((,) "crate" (J.str identity))
                          ((:) ((,) "release" (J.str digest))
                             ((:) ((,) "no-prelude" (J.Boolean noPrelude))
                                ((:) ((,) "metadata" (J.str metadata))
                                   ((:) ((,) "object" (J.str object)) [])))))))
           };
           result <-
             cachedCheckedResult b ("release " ++ identity) inputs validCrateClosure
               (\work ->
                  do {
                    O.copy (path ++ "/unit.mlfci") (work ++ "/unit.mlfci");
                    O.copy (path ++ "/unit.mlfco") (work ++ "/unit.mlfco");
                    copiedMetadata <- fileDigest (work ++ "/unit.mlfci");
                    copiedObject <- fileDigest (work ++ "/unit.mlfco");
                    O.require (eqString metadata copiedMetadata && eqString object copiedObject)
                      "installed release changed during import";
                    saveCrateClosure work [];
                    closure <- J.read (work ++ "/dependency-files.json");
                    let {
                      installed =
                        obj2 (path ++ "/unit.mlfci") (J.str metadata) (path ++ "/unit.mlfco")
                          (J.str object)
                    };
                    case mergeDependencyProof closure installed of {
                      Left message -> O.fatal message;
                      Right proof -> J.write (work ++ "/dependency-files.json") proof
                    }
                  });
           let {
             row =
               info
                 ((:) ((,) "crate" (J.str identity))
                    ((:) ((,) "sha256" (J.str digest))
                       ((:) ((,) "metadata" (J.str (path ++ "/unit.mlfci")))
                          ((:) ((,) "artifact" (J.str (artifactPath result)))
                             ((:) ((,) "outer_cached" (J.get "cached" result))
                                ((:) ((,) "inferred_groups" (J.num 0)) []))))))
           };
           record b "releases" row;
           ioReturn
             (J.set "import_artifact" (J.str path)
                (J.set "releases" (J.Array ((:) row []))
                   (J.set "metadata" (J.str (path ++ "/unit.mlfci")) result)))
         };
  libraryLoop :: Builder ->
                 Bool ->
                 [] ((,) String String) -> [] M.Package -> IO ([] ((,) String String));
  libraryLoop b noPrelude done pending =
    case pending of {
      [] -> ioReturn done;
      (:) p rest ->
        if S.null (M.packageModules p)
        then libraryLoop b noPrelude done rest
        else do {
               result <- libraryResult b p (directLibraries p done) noPrelude;
               libraryLoop b noPrelude (S.snoc done ((,) (M.packageName p) (importPath result)))
                 rest
             }
    };
  releasePackage b destination =
    do {
      let {
        p = M.rootPackage (graph b)
      };
      O.require (S.not (S.null (M.packageModules p))) "release requires a package library";
      built <- libraries b False;
      let {
        artifact =
          S.fromMaybe (panic "missing release library") (S.lookup eqString (M.packageName p) built)
      };
      verifyInputs b;
      R.publish (artifact ++ "/unit.mlfci") (J.getText "sha256" "" (J.get "compiler" (tools b)))
        False
        (M.packageName p)
        (J.getText "version" "" (M.packageData p))
        destination
    };
  runtimeObject :: Builder -> J.Json -> IO String;
  runtimeObject b gc = runtimeObjectWithPgo b gc J.empty;
  runtimeObjectWithPgo :: Builder -> J.Json -> J.Json -> IO String;
  runtimeObjectWithPgo b gc profile =
    do {
      result <- runtimeObjectWithPgoResult b gc profile;
      ioReturn (artifactPath result)
    };
  runtimeObjectWithPgoResult :: Builder -> J.Json -> J.Json -> IO J.Json;
  -- Relative basename makes internal C function profile names independent of
  -- the build directory. Ordinary builds retain their original invocation.
  runtimeObjectWithPgoResult b gc profile =
    do {
      let {
        allFlags = S.append (J.getStrings "flags" (J.get "gmp" (tools b))) (J.getStrings "flags" gc)
      };
      let {
        cflags =
          S.append (S.filter (\f -> (O.starts "-I" f || O.starts "-D" f)) allFlags) (objectFlags b)
      };
      let {
        inputs =
          info
            (S.append
               (S.map (\key -> (,) key (J.get key (tools b)))
                  (O.words "clang runtime runtime-path system machine native_environment gmp"))
               ((:) ((,) "gc" gc)
                  ((:) ((,) "flags" (J.stringArray (S.append (O.words "-O2 -std=c11") cflags)))
                     [])))
      };
      let {
        options = S.append (O.words "-O2 -std=c11") (S.append cflags (pgoFlags profile))
      };
      let {
        runtime = J.getText "runtime-path" "" (tools b)
      };
      let {
        profiled = S.not (S.null (J.items profile))
      };
      let {
        nativeInputs =
          if profiled
          then J.set "runtime-cwd" (J.str (O.parent runtime))
                 (J.set "flags" (J.stringArray options) (pgoInputs profile inputs))
          else inputs
      };
      cachedResult b "runtime object" nativeInputs
        (\work ->
           do {
             ignored <-
               capture b (if profiled then O.parent runtime else work)
                 (S.append ((:) (clang b) options)
                    ((:) "-c"
                       ((:) (if profiled then O.base runtime else runtime)
                          ((:) "-o" ((:) (work ++ "/runtime.o") [])))))
                 ""
                 "";
             present <- fileExists (work ++ "/runtime.o");
             O.require present "C compiler did not produce runtime object"
           })
    };
  emitCrate :: Builder -> String -> String -> String -> IO String;
  emitCrate b crate metadataHash objectHash =
    do {
      result <- emitCrateResult b "legacy" crate metadataHash objectHash;
      ioReturn (artifactPath result)
    };
  emitCrateResult :: Builder -> String -> String -> String -> String -> IO J.Json;
  -- Query storage follows a stable target identity, never invocation IDs or the
  -- worker count. Independent targets therefore do not share an emission lock.
  -- Bootstrap seeds predate explicit report outputs. Their query storage is
  -- private to this worker even if an interrupted coordinator is restarted.
  emitCrateResult b targetIdentity crate metadataHash objectHash =
    do {
      let {
        inputs =
          info
            ((:) ((,) "compiler" (J.get "compiler" (tools b)))
               ((:) ((,) "crate-path" (J.str crate))
                  ((:) ((,) "metadata" (J.str metadataHash))
                     ((:) ((,) "object" (J.str objectHash))
                        ((:) ((,) "abi" (J.str "compact-bdwgc-v1")) [])))))
      };
      partition <- fingerprint b (J.str targetIdentity);
      let {
        explicitReport = J.getBool "compiler-query-report" False (tools b)
      };
      let {
        codegen =
          ((if explicitReport
            then (cacheDirectory b ++ ("/.codegen/" ++ partition))
            else (directory b ++ ("/codegen-cache/" ++ partition))) ++
           ("/" ++ J.getText "sha256" "" (J.get "compiler" (tools b))))
      };
      O.mkdir codegen;
      result <-
        cachedResult b "LLVM emission" inputs
          (\work ->
             do {
               let {
                 report = (work ++ "/codegen-query.json")
               };
               let {
                 arguments =
                   (:) (compiler b)
                     ((:) "--crate-to-llvm-gc"
                        ((:) (crate ++ "/unit.mlfci")
                           ((:) "--cache"
                              ((:) codegen
                                 (if explicitReport
                                  then (:) "--query-report" ((:) report [])
                                  else [])))))
               };
               ignored <- capture b work arguments "" (work ++ "/program.ll");
               if explicitReport
               then ioReturn ()
               else do {
                      O.copy (codegen ++ "/last-query.json") report
                    };
               present <- fileExists report;
               O.require present "compiler did not report the LLVM cache query"
             });
      let {
        artifact = artifactPath result
      };
      saved <- J.read (artifact ++ "/codegen-query.json");
      let {
        reused = J.getBool "cached" False result
      };
      let {
        current =
          if reused
          then J.set "input_reused" (J.Boolean True)
                 (J.set "optimized_reused" (J.Boolean True) saved)
          else saved
      };
      let {
        queries =
          J.set "outer_cached" (J.Boolean reused)
            (J.set "cache_source"
               (J.str (if reused then "emission-artifact" else "codegen-queries"))
               current)
      };
      let {
        row =
          info
            ((:) ((,) "metadata" (J.str (crate ++ "/unit.mlfci")))
               ((:) ((,) "query_report" (J.str (artifact ++ "/codegen-query.json")))
                  ((:) ((,) "queries" queries) [])))
      };
      record b "codegen" row;
      ioReturn (J.set "codegen" (J.Array ((:) row [])) result)
    };
  nativeLLVMObject :: Builder -> String -> IO String;
  nativeLLVMObject b emitted = nativeLLVMObjectWithPgo b emitted J.empty;
  nativeLLVMObjectWithPgo :: Builder -> String -> J.Json -> IO String;
  nativeLLVMObjectWithPgo b emitted profile =
    do {
      result <- nativeLLVMObjectWithPgoResult b emitted profile;
      ioReturn (artifactPath result)
    };
  nativeLLVMObjectWithPgoResult :: Builder -> String -> J.Json -> IO J.Json;
  nativeLLVMObjectWithPgoResult b emitted profile =
    do {
      digest <- fileDigest (emitted ++ "/program.ll");
      let {
        options =
          S.append (O.words "-O2 -Wno-override-module -c")
            (S.append (J.getStrings "ir-flags" (tools b))
               (S.append (objectFlags b) (pgoFlags profile)))
      };
      let {
        inputs =
          info
            (S.append
               (S.map (\key -> (,) key (J.get key (tools b)))
                  (O.words "clang system machine native_environment"))
               ((:) ((,) "llvm" (J.str digest))
                  ((:) ((,) "flags" (J.stringArray options)) [])))
      };
      cachedResult b "LLVM object" (pgoInputs profile inputs)
        (\work ->
           do {
             ignored <-
               capture b work
                 (S.append ((:) (clang b) options)
                    ((:) (emitted ++ "/program.ll") ((:) "-o" ((:) (work ++ "/program.o") []))))
                 ""
                 "";
             present <- fileExists (work ++ "/program.o");
             O.require present "LLVM compiler did not produce native object"
           })
    };
  linkNative :: Builder -> String -> String -> J.Json -> IO String;
  linkNative b llvm runtime gc = linkNativeWithPgo b llvm runtime gc J.empty;
  linkNativeWithPgo :: Builder -> String -> String -> J.Json -> J.Json -> IO String;
  linkNativeWithPgo b llvm runtime gc profile =
    do {
      result <- linkNativeWithPgoResult b llvm runtime gc profile;
      ioReturn (artifactPath result)
    };
  linkNativeWithPgoResult :: Builder -> String -> String -> J.Json -> J.Json -> IO J.Json;
  linkNativeWithPgoResult b llvm runtime gc profile =
    do {
      llvmHash <- fileDigest (llvm ++ "/program.o");
      runtimeHash <- fileDigest (runtime ++ "/runtime.o");
      let {
        libraries =
          S.append (J.getStrings "flags" (J.get "gmp" (tools b))) (J.getStrings "flags" gc)
      };
      let {
        options =
          S.append (O.words "-O2 -Wno-override-module")
            (if eqString (J.getText "mode" "" profile) "generate"
             then (:) "-fprofile-generate" []
             else [])
      };
      let {
        hostFlags =
          if J.has "windows" (tools b)
          then (:) "-lshell32" ((:) "-Wl,--no-insert-timestamp" (stackFlags b))
          else stackFlags b
      };
      let {
        trailing = S.append libraries (S.append ((:) "-lm" []) hostFlags)
      };
      let {
        inputs =
          info
            (S.append
               (S.map (\key -> (,) key (J.get key (tools b)))
                  (O.words "clang system machine native_environment gmp"))
               ((:) ((,) "gc" gc)
                  ((:) ((,) "llvm-object" (J.str llvmHash))
                     ((:) ((,) "runtime-object" (J.str runtimeHash))
                        ((:) ((,) "flags" (J.stringArray (S.append options trailing))) [])))))
      };
      cachedResult b "native link"
        (pgoInputs profile
           (if J.has "windows" (tools b)
            then J.set "windows" (J.get "windows" (tools b)) inputs
            else inputs))
        (\work ->
           do {
             ignored <-
               capture b work
                 (S.append ((:) (clang b) options)
                    ((:) (llvm ++ "/program.o")
                       ((:) (runtime ++ "/runtime.o")
                          (S.append trailing
                             ((:) "-o" ((:) (executable b (work ++ "/program")) []))))))
                 ""
                 "";
             present <- fileExists (executable b (work ++ "/program"));
             O.require present "linker did not produce executable";
             copyWindowsFiles b work
           })
    };
  buildTarget :: Builder -> M.Package -> String -> J.Json -> Bool -> IO ((,) String String);
  buildTarget b p name target publish =
    do {
      boundValueShared3 <- M.targetCrateModules (graph b) p target;
      case boundValueShared3 of {
        (,) entry ms ->
          do {
            let {
              noPrelude = J.getBool "no-prelude" False target
            };
            gc <- gcFlags b;
            built <- libraries b noPrelude;
            let {
              dependencies =
                S.nubBy eqString
                  (S.append
                     (S.mapMaybe (\n -> S.lookup eqString n built)
                        (M.targetDependencyNames p target))
                     (S.maybe [] (\path -> (:) path [])
                        (S.lookup eqString (M.packageName p) built)))
            };
            crate <- compileCrate b p ("target-" ++ name) entry ms dependencies noPrelude;
            metadataHash <- fileDigest (crate ++ "/unit.mlfci");
            objectHash <- fileDigest (crate ++ "/unit.mlfco");
            emission <-
              emitCrateResult b (M.crateIdentity p ("target-" ++ name)) crate metadataHash
                objectHash;
            let {
              emitted = artifactPath emission
            };
            let {
              profile = pgoForTarget b p name
            };
            llvm <- nativeLLVMObjectWithPgo b emitted profile;
            runtime <- runtimeObjectWithPgo b gc profile;
            linked <- linkNativeWithPgo b llvm runtime gc profile;
            result <- assembleTargetResult b p name target crate emitted linked profile;
            let {
              artifact = artifactPath result
            };
            if publish then queuePublication b name artifact else ioReturn ();
            ioReturn ((,) (executable b (artifact ++ "/program")) artifact)
          }
      }
    };
  assembleTargetResult :: Builder ->
                          M.Package ->
                          String -> J.Json -> String -> String -> String -> J.Json -> IO J.Json;
  -- Preserve both the metadata's object sibling and the fixed-point IR record.
  assembleTargetResult b p name target crate emitted linked profile =
    do {
      metadataHash <- fileDigest (crate ++ "/unit.mlfci");
      objectHash <- fileDigest (crate ++ "/unit.mlfco");
      binaryHash <- fileDigest (executable b (linked ++ "/program"));
      llvmHash <- fileDigest (emitted ++ "/program.ll");
      let {
        inputs =
          info
            ((:) ((,) "toolchain" (tools b))
               ((:) ((,) "target" target)
                  ((:) ((,) "crate-path" (J.str crate))
                     ((:) ((,) "metadata" (J.str metadataHash))
                        ((:) ((,) "object" (J.str objectHash))
                           ((:) ((,) "llvm" (J.str llvmHash))
                              ((:) ((,) "binary" (J.str binaryHash)) [])))))))
      };
      result <-
        cachedCheckedResult b ("executable " ++ (M.packageName p ++ (":" ++ name)))
          (pgoInputs profile inputs)
          validCrateClosure
          (\work ->
             do {
               O.copy (crate ++ "/unit.mlfci") (work ++ "/unit.mlfci");
               O.copy (crate ++ "/unit.mlfco") (work ++ "/unit.mlfco");
               O.copy (crate ++ "/dependency-files.json") (work ++ "/dependency-files.json");
               O.copy (emitted ++ "/program.ll") (work ++ "/program.ll");
               O.copy (executable b (linked ++ "/program")) (executable b (work ++ "/program"));
               copyWindowsFiles b work
             });
      ioReturn (J.set "binary" (J.str (executable b (artifactPath result ++ "/program"))) result)
    };
  queuePublication :: Builder -> String -> String -> IO ();
  queuePublication b name artifact =
    do {
      stamp <- J.read (artifact ++ "/artifact.json");
      record b "pending-publications"
        (J.set "name" (J.str name)
           (J.set "binary" (J.str (executable b (artifact ++ "/program")))
              (J.set "files" (J.get "files" stamp)
                 (obj2 "artifact" (J.str artifact) "key" (J.str (O.base artifact))))))
    };
  -- A worker receipt fixes the bytes that the invocation consumed. Comparing
  -- it with the current artifact stamp also rejects a replacement whose own
  -- checksums are internally consistent but differ from the completed action.
  validActionResult :: J.Json -> IO Bool;
  validActionResult result =
    do {
      let {
        artifact = artifactPath result
      };
      let {
        key = J.getText "key" "" result
      };
      if S.not
           (Host.absolutePath artifact &&
            (validDigest (J.str key) && eqString (O.base artifact) key))
      then ioReturn False
      else do {
             own <- cacheValid artifact key;
             if S.not own
             then ioReturn False
             else do {
                    stamp <- J.read (artifact ++ "/artifact.json");
                    if S.not (J.equal (J.get "files" result) (J.get "files" stamp))
                    then ioReturn False
                    else do {
                           imported <- validImportResult result;
                           if S.not imported
                           then ioReturn False
                           else if (J.has "metadata" result || J.has "binary" result)
                                then validCrateClosure artifact
                                else ioReturn True
                         }
                  }
           }
    };
  validImportResult result =
    if S.not (J.has "import_artifact" result)
    then ioReturn True
    else do {
           let {
             path = importPath result
           };
           if S.not
                (Host.absolutePath path &&
                 eqString (J.getText "metadata" "" result) (path ++ "/unit.mlfci"))
           then ioReturn False
           else do {
                  saved <- readProofJson (artifactPath result ++ "/dependency-files.json");
                  case saved of {
                    Nothing -> ioReturn False;
                    Just proof ->
                      do {
                        let {
                          files = J.get "files" result
                        };
                        ioReturn
                          (validDependencyShape proof &&
                           (J.has (path ++ "/unit.mlfci") proof &&
                            (J.has (path ++ "/unit.mlfco") proof &&
                             (J.equal (J.get (path ++ "/unit.mlfci") proof)
                                (J.get "unit.mlfci" files) &&
                              J.equal (J.get (path ++ "/unit.mlfco") proof)
                                (J.get "unit.mlfco" files)))))
                      }
                  }
                }
         };
  validateWorkerResults :: J.Json -> IO ();
  validateWorkerResults scheduled =
    do {
      let {
        directory = O.parent (J.getText "plan" "" scheduled)
      };
      invocation <- fileDigest (directory ++ "/context.json");
      planDigest <- fileDigest (J.getText "plan" "" scheduled);
      O.require
        (eqString invocation (J.getText "invocation_id" "" scheduled) &&
         eqString planDigest (J.getText "plan_digest" "" scheduled))
        "build invocation changed during build/test";
      S.mapM_
        (\job ->
           do {
             let {
               identity = J.getText "id" "" job
             };
             saved <- J.read (directory ++ ("/jobs/" ++ (identity ++ "/result.json")));
             O.require
               (J.getBool "complete" False saved &&
                (eqString (J.getText "id" "" saved) identity &&
                 eqString (J.getText "invocation_id" "" saved) invocation))
               ("worker receipt changed during build/test: " ++ identity);
             valid <- validActionResult (J.get "result" saved);
             O.require valid ("worker artifact changed during build/test: " ++ identity)
           })
        (J.values (J.get "jobs" scheduled))
    };
  -- Published names form one transaction, including shared DLLs and the manager's
  -- helper. Backups remain until every rename succeeds. Recovery runs under the
  -- build-directory lock before a later command overwrites its report.
  publicationRoot :: String -> String;
  publicationRoot buildDirectory = (buildDirectory ++ "/bin/.mlf-publications");
  publicationName :: String -> Bool;
  publicationName name =
    ((stringLength name > 0) &&
     (S.not (O.starts "." name) &&
      S.all
        (\i ->
           let {
             c = stringCodeAt name i
           } in
           (((c >= 48) && (c <= 57)) ||
            (((c >= 65) && (c <= 90)) ||
             (((c >= 97) && (c <= 122)) || ((c == 45) || ((c == 46) || (c == 95)))))))
        (S.range 0 (stringLength name - 1))));
  publicationFile :: String -> String -> String -> J.Json;
  publicationFile name source digest =
    J.set "sha256" (J.str digest) (obj2 "name" (J.str name) "source" (J.str source));
  publicationFiles :: Builder -> J.Json -> [] J.Json -> IO ([] J.Json);
  publicationFiles b report publications =
    do {
      let {
        binaries =
          S.concatMap
            (\row ->
               let {
                 artifact = J.getText "artifact" "" row
               } in
               let {
                 files = J.get "files" row
               } in
               (:)
                 (publicationFile (O.base (executable b (J.getText "name" "" row)))
                    (executable b (artifact ++ "/program"))
                    (J.text (J.get (O.base (executable b "program")) files)))
                 (S.map
                    (\name ->
                       publicationFile name (artifact ++ ("/" ++ name)) (J.text (J.get name files)))
                    (windowsFiles b)))
            publications
      };
      let {
        manager =
          (eqString (M.packageName (M.rootPackage (graph b))) "mlf-compiler" &&
           S.any (\row -> eqString (J.getText "name" "" row) "mlfpkg") publications)
      };
      helper <-
        if manager
        then do {
               let {
                 helpers =
                   S.map (J.get "helper") (J.values (J.getOr "scheduler" (J.Array []) report))
               };
               O.require (S.not (S.null helpers)) "missing build runner installation identity";
               let {
                 identity = S.head helpers
               };
               ioReturn
                 ((:)
                    (publicationFile (O.base (executable b "mlf-build-runner"))
                       (J.getText "path" "" identity)
                       (J.getText "sha256" "" identity))
                    [])
             }
        else ioReturn [];
      S.foldM
        (\saved row ->
           do {
             let {
               name = J.getText "name" "" row
             };
             O.require (publicationName name && validDigest (J.get "sha256" row))
               "invalid publication file";
             case S.find (\old -> eqString (J.getText "name" "" old) name) saved of {
               Nothing -> ioReturn (S.append saved ((:) row []));
               Just old ->
                 do {
                   O.require (J.equal (J.get "sha256" old) (J.get "sha256" row))
                     ("conflicting publication files: " ++ name);
                   ioReturn saved
                 }
             }
           })
        []
        (S.append binaries helper)
    };
  publicationMove :: String -> String -> IO Int;
  publicationMove source destination =
    O.exec "" ((:) "/bin/mv" ((:) "-f" ((:) source ((:) destination [])))) "" "" "" 1800;
  publicationRemove :: String -> IO Int;
  publicationRemove path = O.exec "" ((:) "/bin/rm" ((:) "-rf" ((:) path []))) "" "" "" 1800;
  publicationDigest :: String -> IO String;
  publicationDigest path =
    do {
      present <- fileExists path;
      if present then fileDigest path else ioReturn ""
    };
  preparePublications :: String -> [] J.Json -> IO String;
  -- No published destination has changed when this recovery journal is written.
  preparePublications buildDirectory files =
    do {
      let {
        base = publicationRoot buildDirectory
      };
      O.mkdir base;
      transaction <- temporaryDirectory base (base ++ "/transaction.");
      O.mkdir (transaction ++ "/new");
      O.mkdir (transaction ++ "/old");
      O.mkdir (transaction ++ "/restore");
      let {
        names = S.map (J.getText "name" "") files
      };
      O.require
        ((S.length names == S.length (S.nubBy eqString names)) && S.all publicationName names)
        "duplicate or invalid publication filename";
      entries <-
        S.mapM
          (\row ->
             do {
               let {
                 name = J.getText "name" "" row
               };
               let {
                 destination = (buildDirectory ++ ("/bin/" ++ name))
               };
               let {
                 expected = J.getText "sha256" "" row
               };
               O.require (validDigest (J.str expected)) "invalid publication checksum";
               isDirectory <- directoryExists destination;
               O.require (S.not isDirectory)
                 ("publication destination is a directory: " ++ destination);
               O.copy (J.getText "source" "" row) (transaction ++ ("/new/" ++ name));
               staged <- fileDigest (transaction ++ ("/new/" ++ name));
               O.require (eqString staged expected) ("publication source changed: " ++ name);
               old <- publicationDigest destination;
               if eqString old ""
               then ioReturn ()
               else do {
                      O.copy destination (transaction ++ ("/old/" ++ name));
                      backup <- fileDigest (transaction ++ ("/old/" ++ name));
                      O.require (eqString backup old)
                        ("published file changed while staging: " ++ name)
                    };
               ioReturn (J.set "old" (J.str old) (obj2 "name" (J.str name) "new" (J.str expected)))
             })
          files;
      J.write (transaction ++ "/journal.json")
        (obj2 "format" (J.num 1) "entries" (J.Array entries));
      writeFile (transaction ++ "/committed.new") "complete\n";
      ioReturn transaction
    };
  publicationEntries :: String -> IO ([] J.Json);
  publicationEntries transaction =
    do {
      journal <- J.read (transaction ++ "/journal.json");
      let {
        entries = J.values (J.get "entries" journal)
      };
      let {
        names = S.map (J.getText "name" "") entries
      };
      O.require
        (J.equal (J.get "format" journal) (J.num 1) &&
         ((S.length names == S.length (S.nubBy eqString names)) &&
          (S.all publicationName names &&
           S.all
             (\row ->
                (validDigest (J.get "new" row) &&
                 (eqString (J.getText "old" "" row) "" || validDigest (J.get "old" row))))
             entries)))
        "invalid publication recovery journal";
      ioReturn entries
    };
  rollbackPublications :: String -> String -> [] J.Json -> IO Bool;
  -- Validate all backups and destinations before restoring anything. A changed
  -- unrelated file is never overwritten by recovery; keep the journal instead.
  rollbackPublications buildDirectory transaction entries =
    do {
      checks <-
        S.mapM
          (\row ->
             do {
               let {
                 name = J.getText "name" "" row
               };
               let {
                 old = J.getText "old" "" row
               };
               let {
                 destination = (buildDirectory ++ ("/bin/" ++ name))
               };
               isDirectory <- directoryExists destination;
               current <-
                 if isDirectory then ioReturn "directory" else publicationDigest destination;
               backup <-
                 if eqString old ""
                 then ioReturn ""
                 else publicationDigest (transaction ++ ("/old/" ++ name));
               ioReturn
                 (eqString old backup &&
                  (eqString current "" ||
                   (eqString current old || eqString current (J.getText "new" "" row))))
             })
          entries;
      if S.not (S.and checks)
      then ioReturn False
      else do {
             restored <-
               S.mapM
                 (\row ->
                    do {
                      let {
                        name = J.getText "name" "" row
                      };
                      let {
                        old = J.getText "old" "" row
                      };
                      let {
                        destination = (buildDirectory ++ ("/bin/" ++ name))
                      };
                      current <- publicationDigest destination;
                      if eqString current old
                      then ioReturn True
                      else if eqString old ""
                           then do {
                                  code <- publicationRemove destination;
                                  ioReturn (code == 0)
                                }
                           else do {
                                  let {
                                    staged = (transaction ++ ("/restore/" ++ name))
                                  };
                                  copied <-
                                    O.exec ""
                                      ((:) "/bin/cp"
                                         ((:) "-p"
                                            ((:) (transaction ++ ("/old/" ++ name))
                                               ((:) staged []))))
                                      ""
                                      ""
                                      ""
                                      1800;
                                  if (copied /= 0)
                                  then ioReturn False
                                  else do {
                                         code <- publicationMove staged destination;
                                         ioReturn (code == 0)
                                       }
                                }
                    })
                 (S.reverse entries);
             ioReturn (S.and restored)
           }
    };
  recoverPublication :: String -> String -> IO ();
  recoverPublication buildDirectory transaction =
    do {
      committed <- fileExists (transaction ++ "/committed");
      journal <- fileExists (transaction ++ "/journal.json");
      if (committed || S.not journal)
      then O.remove transaction
      else do {
             entries <- publicationEntries transaction;
             restored <- rollbackPublications buildDirectory transaction entries;
             O.require restored
               ("cannot restore interrupted publication; preserved backups in " ++ transaction);
             O.remove transaction
           }
    };
  recoverPublications :: String -> IO ();
  recoverPublications buildDirectory =
    do {
      let {
        base = publicationRoot buildDirectory
      };
      present <- directoryExists base;
      if S.not present
      then ioReturn ()
      else do {
             names <- O.entries base;
             S.mapM_
               (\name ->
                  if O.starts "transaction." name
                  then recoverPublication buildDirectory (base ++ ("/" ++ name))
                  else ioReturn ())
               (S.sortBy compareString names)
           }
    };
  commitPublicationFiles :: String ->
                            String -> (String -> String -> IO Int) -> [] J.Json -> IO Bool;
  commitPublicationFiles buildDirectory transaction move entries =
    case entries of {
      [] ->
        do {
          code <- publicationMove (transaction ++ "/committed.new") (transaction ++ "/committed");
          ioReturn (code == 0)
        };
      (:) row rest ->
        do {
          let {
            name = J.getText "name" "" row
          };
          code <- move (transaction ++ ("/new/" ++ name)) (buildDirectory ++ ("/bin/" ++ name));
          if (code /= 0)
          then ioReturn False
          else commitPublicationFiles buildDirectory transaction move rest
        }
    };
  publishFilesUsing :: String -> (String -> String -> IO Int) -> [] J.Json -> IO Bool;
  -- Cleanup failure does not turn a completed commit into a failed command.
  -- A committed journal can safely be cleaned by the next locked command.
  publishFilesUsing buildDirectory move files =
    if S.null files
    then ioReturn True
    else do {
           recoverPublications buildDirectory;
           transaction <- preparePublications buildDirectory files;
           entries <- publicationEntries transaction;
           success <- commitPublicationFiles buildDirectory transaction move entries;
           if success
           then do {
                  ignored <- publicationRemove transaction;
                  ioReturn True
                }
           else do {
                  restored <- rollbackPublications buildDirectory transaction entries;
                  O.require restored
                    ("publication failed and rollback is pending; preserved backups in " ++
                     transaction);
                  O.remove transaction;
                  ioReturn False
                }
         };
  verifyHashes :: J.Json -> IO ();
  verifyHashes values =
    S.mapM_
      (\entry ->
         do {
           actual <- fileDigest (S.fst entry);
           O.require (eqString actual (J.text (S.snd entry)))
             ("input changed during build/test: " ++ S.fst entry)
         })
      (J.items values);
  finish :: Builder -> IO ();
  -- Validate the whole set before replacing any published name. Command tests
  -- run after scheduling and may have changed an artifact or its closure.
  finish b =
    do {
      validate b;
      report <- J.read (reportPath b);
      let {
        publications = J.values (J.getOr "pending-publications" (J.Array []) report)
      };
      S.mapM_
        (\row ->
           do {
             valid <- validActionResult row;
             O.require valid
               ("queued executable changed during build/test: " ++ J.getText "name" "" row);
             let {
               files = J.get "files" row
             };
             O.require
               (S.all (\name -> J.has name files)
                  ((:) (O.base (executable b "program")) (windowsFiles b)))
               "queued executable is missing a publication file"
           })
        publications;
      files <- publicationFiles b report publications;
      published <- publishFilesUsing (directory b) publicationMove files;
      O.require published "publication failed; previous executables restored";
      complete b
    };
  complete :: Builder -> IO ();
  complete b =
    do {
      report <- J.read (reportPath b);
      J.write (reportPath b) (J.set "complete" (J.Boolean True) report)
    };
  verifyInputs :: Builder -> IO ();
  verifyInputs b = validate b;
  validate :: Builder -> IO ();
  validate b =
    do {
      verifyPgo (J.getObject "native-pgo" (config b));
      snapshot <- M.snapshot (graph b);
      O.require (J.equal snapshot (initial b))
        "package sources or manifests changed during build/test";
      S.mapM_
        (\key ->
           do {
             let {
               identity = J.get key (tools b)
             };
             actual <- fileDigest (J.getText "path" "" identity);
             O.require (eqString actual (J.getText "sha256" "" identity))
               (key ++ " changed during build/test")
           })
        (O.words "compiler clang pkg-config manager");
      verifyHashes (J.get "runtime" (tools b));
      verifyHashes (J.get "libraries" (J.get "gmp" (tools b)));
      verifyHashes (J.get "headers" (J.get "gmp" (tools b)));
      if J.has "windows" (tools b)
      then do {
             verifyHashes (J.get "dlls" (J.get "windows" (tools b)));
             let {
               helper = J.get "helper" (J.get "windows" (tools b))
             };
             actual <- fileDigest (J.getText "path" "" helper);
             O.require (eqString actual (J.getText "sha256" "" helper))
               "Windows host helper changed during build/test"
           }
      else ioReturn ();
      report <- J.read (reportPath b);
      S.mapM_
        (\value ->
           do {
             verifyHashes (J.get "libraries" value);
             verifyHashes (J.get "headers" value)
           })
        (J.values (J.getOr "native_inputs" (J.Array []) report));
      S.mapM_
        (\row ->
           do {
             let {
               helper = J.get "helper" row
             };
             actual <- fileDigest (J.getText "path" "" helper);
             O.require (eqString actual (J.getText "sha256" "" helper))
               "build runner changed during build/test"
           })
        (J.values (J.getOr "scheduler" (J.Array []) report));
      S.mapM_ validateWorkerResults (J.values (J.getOr "scheduler" (J.Array []) report))
    }
}
