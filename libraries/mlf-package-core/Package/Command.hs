-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Package.Command where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Package.OS as O;
  import qualified Package.Json as J;
  import qualified Package.Manifest as M;
  import qualified Package.Build as B;
  import qualified Package.Distribution as Distribution;
  import qualified Package.Scheduler as Scheduler;
  usage :: String;
  usage =
    "Usage: mlfpkg [--manifest FILE] [--build-dir DIR] [--cache-dir DIR] [--compiler TOOL] [--clang TOOL]\n              [--pkg-config TOOL] [--runtime FILE] [--gc-prefix DIR] [--timeout SECONDS] [--jobs N] [--locked] [--offline]\n              [--pgo-generate TARGET | --pgo-target TARGET --pgo-use FILE]\n              plan | lock | build [--target NAME ...] | test [--target NAME ...] | run NAME [-- ARGS...]\n              release DIRECTORY | pack RELEASE_DIRECTORY ASSET_FILE\nPackage manifests: mlf-package.json. Dependencies select local source, checked directories, or pinned GitHub release assets.\n";
  options :: J.Json -> [] String -> IO ((,) J.Json ([] String));
  options config args =
    let {
      matchValueShared1 = args
    } in
    case matchValueShared1 of {
      (:) matchValueShared2 matchValueShared3 ->
        if MLF.Primitive.eqString matchValueShared2 "--locked"
        then let {
               rest = matchValueShared3
             } in
             options (J.set "locked" (J.Boolean True) config) rest
        else if MLF.Primitive.eqString matchValueShared2 "--offline"
             then let {
                    rest = matchValueShared3
                  } in
                  options (J.set "offline" (J.Boolean True) config) rest
             else case matchValueShared3 of {
                    (:) matchValueShared4 matchValueShared5 ->
                      let {
                        value = matchValueShared4
                      } in
                      let {
                        rest = matchValueShared5
                      } in
                      let {
                        option = matchValueShared2
                      } in
                      if S.elem eqString option
                           (O.words
                              "--manifest --build-dir --cache-dir --compiler --clang --pkg-config --runtime --gc-prefix --timeout --jobs --pgo-generate --pgo-target --pgo-use")
                      then options (J.set (O.drop 2 option) (J.str value) config) rest
                      else ioReturn ((,) config args);
                    _ -> ioReturn ((,) config args)
                  };
      _ -> ioReturn ((,) config args)
    };
  selections :: [] String -> [] String -> IO ([] String);
  selections acc args =
    let {
      matchValueShared6 = args
    } in
    case matchValueShared6 of {
      [] ->
        do {
          O.require (S.length acc == S.length (S.nubBy eqString acc)) "duplicate target selection";
          ioReturn acc
        };
      (:) matchValueShared7 matchValueShared8 ->
        if MLF.Primitive.eqString matchValueShared7 "--target"
        then case matchValueShared8 of {
               (:) matchValueShared9 matchValueShared10 ->
                 let {
                   name = matchValueShared9
                 } in
                 let {
                   rest = matchValueShared10
                 } in
                 selections (S.snoc acc name) rest;
               _ -> O.fatal usage
             }
        else O.fatal usage;
      _ -> O.fatal usage
    };
  configureCompiler :: M.Package -> String -> J.Json -> IO J.Json;
  configureCompiler package buildDirectory config =
    do {
      let {
        requested = J.getText "compiler" "" config
      };
      if S.not (eqString requested "")
      then ioReturn config
      else do {
             let {
               checkout = M.packageRoot package
             };
             let {
               candidates0 =
                 if eqString (M.packageName package) "mlf-compiler"
                 then (:) (buildDirectory ++ "/bin/emlf")
                        ((:) (checkout ++ "/.mlf-build/bin/emlf")
                           ((:) (checkout ++ "/.mlf-build/mlf-native/bin/emlf") []))
                 else []
             };
             candidates <- S.mapM O.executable candidates0;
             available <-
               S.mapM
                 (\path ->
                    do {
                      present <- fileExists path;
                      ioReturn (if present then Just path else Nothing)
                    })
                 candidates;
             let {
               selected = S.fromMaybe "emlf" (S.listToMaybe (S.catMaybes available))
             };
             ioReturn (J.set "compiler" (J.str selected) config)
           }
    };
  -- A source checkout can provide BDWGC without installing pkg-config metadata.
  -- Explicit options and the environment take precedence over that installation.
  configureGC :: String -> J.Json -> IO J.Json;
  -- Compiler test commands and nested package builds inherit the selection.
  configureGC packageRoot config =
    do {
      windows <- O.isWindows;
      let {
        requested = J.getText "gc-prefix" "" config
      };
      selected <-
        if S.not (eqString requested "")
        then canonicalPath requested
        else do {
               let {
                 dependencies = (packageRoot ++ "/.mlf-build/deps")
               };
               present <- directoryExists dependencies;
               candidates <-
                 if present
                 then do {
                        names <- O.entries dependencies;
                        found <-
                          S.mapM
                            (\name ->
                               do {
                                 let {
                                   prefix = (dependencies ++ ("/" ++ name))
                                 };
                                 library <-
                                   fileExists
                                     (prefix ++
                                      (if windows then "/lib/libgc.dll.a" else "/lib/libgc.a"));
                                 directHeader <- fileExists (prefix ++ "/include/gc.h");
                                 nestedHeader <- fileExists (prefix ++ "/include/gc/gc.h");
                                 let {
                                   header = (directHeader || nestedHeader)
                                 };
                                 if (library && header)
                                 then do {
                                        path <- canonicalPath prefix;
                                        ioReturn (Just path)
                                      }
                                 else ioReturn Nothing
                               })
                            (S.filter (\name -> (O.starts "bdwgc-" name && O.ends "-install" name))
                               names);
                        ioReturn (S.nubBy eqString (S.catMaybes found))
                      }
                 else ioReturn [];
               case candidates of {
                 [] -> ioReturn "";
                 (:) prefix [] -> ioReturn prefix;
                 _ ->
                   O.fatal
                     "multiple local BDWGC installations; select one with --gc-prefix or MLF_GC_PREFIX"
               }
             };
      if eqString selected ""
      then ioReturn config
      else do {
             setEnv "MLF_GC_PREFIX" selected;
             ioReturn (J.set "gc-prefix" (J.str selected) config)
           }
    };
  expand :: [] ((,) String String) -> String -> String;
  expand replacements text =
    S.foldl (\acc entry -> O.replace (S.fst entry) (S.snd entry) acc) text replacements;
  commandTest :: B.Builder ->
                 M.Package -> [] ((,) String String) -> String -> J.Json -> IO J.Json;
  commandTest b p built name target =
    do {
      let {
        binaries =
          S.map
            (\n ->
               (,) ("{bin:" ++ (n ++ "}"))
                 (B.executable b (builtArtifact built ("e-" ++ n) ++ "/program")))
            (J.getStrings "requires" target)
      };
      let {
        requested = J.getStrings "command" target
      };
      let {
        replacements =
          S.append binaries
            ((:) ((,) "{root}" (M.packageRoot p))
               ((:) ((,) "{build}" (B.directory b))
                  ((:) ((,) "{cache}" (B.cacheDirectory b)) [])))
      };
      let {
        argv = S.map (expand replacements) requested
      };
      O.require
        (S.all
           (\arg ->
              S.all (\prefix -> eqString arg (O.replace prefix "" arg))
                (O.words "{root {build {cache {bin:"))
           argv)
        "unresolved test placeholder";
      let {
        log = (B.directory b ++ ("/tests/" ++ (name ++ ".log")))
      };
      O.mkdir (O.parent log);
      setEnv "MLF_BUILD_REPORT" (B.reportPath b);
      code <-
        O.exec (M.packageRoot p) argv "" log log
          (readInt (J.getText "timeout" "1800" (B.config b)));
      hash <- fileDigest log;
      B.record b "commands"
        (B.info
           ((:) ((,) "argv" (J.stringArray argv))
              ((:) ((,) "cwd" (J.str (M.packageRoot p)))
                 ((:) ((,) "exit_code" (J.num code))
                    ((:) ((,) "log" (J.str log)) ((:) ((,) "sha256" (J.str hash)) []))))));
      O.require (code == 0)
        ("test " ++ (name ++ (" failed (" ++ (showInt code ++ ("); see " ++ log)))));
      text <- readFile log;
      putStr (O.drop (S.max 0 (stringLength text - 3000)) text);
      ioReturn
        (B.info
           ((:) ((,) "name" (J.str name))
              ((:) ((,) "log" (J.str log)) ((:) ((,) "sha256" (J.str hash)) []))))
    };
  nativeTest :: B.Builder ->
                M.Package -> [] ((,) String String) -> String -> J.Json -> IO J.Json;
  nativeTest b p built name target =
    do {
      let {
        artifact = builtArtifact built ("t-test-" ++ name)
      };
      let {
        binary = B.executable b (artifact ++ "/program")
      };
      let {
        command =
          (:) (B.compiler b)
            ((:) "--run-crate"
               ((:) (artifact ++ "/unit.mlfci") ((:) "--" (J.getStrings "arguments" target))))
      };
      let {
        testDir = (B.directory b ++ ("/tests/" ++ name))
      };
      O.mkdir testDir;
      writeFile (testDir ++ "/stdin") (J.getText "stdin" "" target);
      S.mapM_
        (\entry ->
           do {
             let {
               backend = S.fst entry
             };
             code <-
               O.exec artifact (S.snd entry) (testDir ++ "/stdin")
                 (testDir ++ ("/" ++ (backend ++ ".stdout")))
                 (testDir ++ ("/" ++ (backend ++ ".stderr")))
                 (readInt (J.getText "timeout" "1800" (B.config b)));
             out <- readFile (testDir ++ ("/" ++ (backend ++ ".stdout")));
             err <- readFile (testDir ++ ("/" ++ (backend ++ ".stderr")));
             O.require (code == 0)
               ("test " ++ (name ++ (" (" ++ (backend ++ (") exited " ++ showInt code)))));
             O.require (eqString out (J.getText "stdout" "" target))
               ("test " ++
                (name ++ (" (" ++ (backend ++ ("): unexpected stdout " ++ J.quote out)))));
             O.require (eqString err "")
               ("test " ++
                (name ++ (" (" ++ (backend ++ ("): unexpected stderr " ++ J.quote err)))))
           })
        ((:) ((,) "interpreter" command)
           ((:) ((,) "llvm" ((:) binary (J.getStrings "arguments" target))) []));
      hash <- fileDigest (testDir ++ "/llvm.stdout");
      ioReturn
        (B.info
           ((:) ((,) "name" (J.str name))
              ((:) ((,) "backends" (J.stringArray (O.words "interpreter llvm")))
                 ((:) ((,) "stdout_sha256" (J.str hash)) []))))
    };
  runTests :: B.Builder -> M.Package -> [] ((,) String String) -> [] String -> IO ();
  runTests b p built names =
    S.mapM_
      (\name ->
         do {
           putStrLn ("Testing " ++ name);
           let {
             target = J.get name (J.getObject "tests" (M.packageData p))
           };
           row <-
             if J.has "command" target
             then commandTest b p built name target
             else nativeTest b p built name target;
           B.record b "tests" (J.set "passed" (J.Boolean True) row)
         })
      names;
  builtArtifact built name =
    S.fromMaybe (panic ("missing built target " ++ name)) (S.lookup eqString name built);
  buildRequests p action names =
    let {
      executables = J.getObject "executables" (M.packageData p)
    } in
    if S.not (eqString action "test")
    then S.map (\name -> Scheduler.request name (J.get name executables) True) names
    else let {
           tests = J.getObject "tests" (M.packageData p)
         } in
         let {
           required =
             S.nubBy eqString
               (S.concatMap (\name -> J.getStrings "requires" (J.get name tests)) names)
         } in
         S.append (S.map (\name -> Scheduler.request name (J.get name executables) True) required)
           (S.map (\name -> Scheduler.request ("test-" ++ name) (J.get name tests) False)
              (S.filter (\name -> J.has "main" (J.get name tests)) names));
  run :: [] String -> IO ();
  run args =
    do {
      O.setupWindows;
      compiler <- getEnv "MLF_COMPILER";
      defaultClang <- O.envDefault "MLF_CLANG" "clang";
      clang <- O.envDefault "CC" defaultClang;
      gc <- getEnv "MLF_GC_PREFIX";
      boundValueShared27 <-
        options
          (B.info
             ((:) ((,) "compiler" (J.str compiler))
                ((:) ((,) "clang" (J.str clang)) ((:) ((,) "gc-prefix" (J.str gc)) []))))
          args;
      case boundValueShared27 of {
        (,) config command ->
          do {
            let {
              matchValueShared14 = command
            } in
            case matchValueShared14 of {
              (:) matchValueShared15 matchValueShared16 ->
                if MLF.Primitive.eqString matchValueShared15 "__build-worker"
                then case matchValueShared16 of {
                       (:) matchValueShared21 matchValueShared22 ->
                         case matchValueShared22 of {
                           (:) matchValueShared23 matchValueShared24 ->
                             case matchValueShared24 of {
                               (:) matchValueShared25 matchValueShared26 ->
                                 case matchValueShared26 of {
                                   [] ->
                                     let {
                                       context = matchValueShared21
                                     } in
                                     let {
                                       invocation = matchValueShared23
                                     } in
                                     let {
                                       identity = matchValueShared25
                                     } in
                                     Scheduler.worker context invocation identity;
                                   _ ->
                                     let {
                                       rest = matchValueShared16
                                     } in
                                     let {
                                       action = matchValueShared15
                                     } in
                                     do {
                                       O.require
                                         (S.elem eqString action
                                            (O.words "plan lock build test run release"))
                                         usage;
                                       let {
                                         manifest = J.getText "manifest" "mlf-package.json" config
                                       };
                                       path <- canonicalPath manifest;
                                       let {
                                         packageDir = O.parent path
                                       };
                                       let {
                                         buildDir =
                                           J.getText "build-dir" (packageDir ++ "/.mlf-build")
                                             config
                                       };
                                       let {
                                         building =
                                           S.elem eqString action (O.words "build test run release")
                                       };
                                       if building then O.mkdir buildDir else ioReturn ();
                                       dir <-
                                         if building
                                         then canonicalPath buildDir
                                         else ioReturn buildDir;
                                       lock <-
                                         if building
                                         then acquireFileLock (dir ++ "/.lock")
                                         else ioReturn (0 - 1);
                                       if building
                                       then B.recoverPublications dir
                                       else ioReturn ();
                                       if building
                                       then J.write (dir ++ "/build-report.json")
                                              (B.obj2 "complete" (J.Boolean False) "implementation"
                                                 (J.str "MLF"))
                                       else ioReturn ();
                                       graph <-
                                         M.loadWith path
                                           (J.set "cache-dir"
                                              (J.getOr "cache-dir" (J.str (dir ++ "/cache")) config)
                                              config);
                                       snapshot <- M.snapshot graph;
                                       let {
                                         p = M.rootPackage graph
                                       };
                                       let {
                                         lockPath = (M.packageRoot p ++ "/mlf.lock")
                                       };
                                       if J.getBool "locked" False config
                                       then do {
                                              saved <- J.read lockPath;
                                              O.require (J.equal saved snapshot)
                                                "mlf.lock is stale; review local changes and run mlfpkg lock"
                                            }
                                       else ioReturn ();
                                       if eqString action "plan"
                                       then do {
                                              O.require (S.null rest) usage;
                                              crates <- M.cratePlan graph;
                                              putStrLn
                                                (J.render
                                                   (J.set "crates" crates
                                                      (J.set "modules"
                                                         (J.stringArray
                                                            (S.map M.moduleName (M.modules graph)))
                                                         (J.set "executables"
                                                            (J.stringArray
                                                               (M.keys
                                                                  (J.getObject "executables"
                                                                     (M.packageData p))))
                                                            (J.set "tests"
                                                               (J.stringArray
                                                                  (M.keys
                                                                     (J.getObject "tests"
                                                                        (M.packageData p))))
                                                               snapshot)))))
                                            }
                                       else if eqString action "lock"
                                            then do {
                                                   O.require (S.null rest) usage;
                                                   J.write lockPath snapshot;
                                                   putStrLn lockPath
                                                 }
                                            else if eqString action "release"
                                                 then case rest of {
                                                        (:) destination [] ->
                                                          do {
                                                            compilerSettings <-
                                                              configureCompiler p dir config;
                                                            settings <-
                                                              configureGC (M.packageRoot p)
                                                                compilerSettings;
                                                            b <- B.create graph settings dir;
                                                            B.releasePackage b destination;
                                                            B.finish b;
                                                            releaseFileLock lock;
                                                            putStrLn
                                                              ("release passed: " ++ destination)
                                                          };
                                                        _ -> O.fatal usage
                                                      }
                                                 else do {
                                                        let {
                                                          targets =
                                                            J.getObject
                                                              (if eqString action "test"
                                                               then "tests"
                                                               else "executables")
                                                              (M.packageData p)
                                                        };
                                                        selected <-
                                                          if eqString action "run"
                                                          then case rest of {
                                                                 (:) name _ ->
                                                                   ioReturn ((:) name []);
                                                                 [] -> O.fatal usage
                                                               }
                                                          else selections [] rest;
                                                        let {
                                                          names =
                                                            if S.null selected
                                                            then M.keys targets
                                                            else selected
                                                        };
                                                        O.require
                                                          (S.all (\name -> J.has name targets)
                                                             names)
                                                          ("unknown target; available: " ++
                                                           S.intercalate ", " (M.keys targets));
                                                        O.require
                                                          (S.not (S.null names) ||
                                                           (eqString action "build" &&
                                                            S.not (S.null (M.packageModules p))))
                                                          "no targets selected";
                                                        compilerSettings <-
                                                          configureCompiler p dir config;
                                                        settings <-
                                                          configureGC (M.packageRoot p)
                                                            compilerSettings;
                                                        b <- B.create graph settings dir;
                                                        built <-
                                                          Scheduler.execute b
                                                            (eqString action "build" &&
                                                             S.null names)
                                                            (buildRequests p action names);
                                                        if eqString action "test"
                                                        then runTests b p built names
                                                        else ioReturn ();
                                                        B.finish b;
                                                        if eqString action "build"
                                                        then S.mapM_
                                                               (\name ->
                                                                  putStrLn
                                                                    (B.executable b
                                                                       (dir ++ ("/bin/" ++ name))))
                                                               names
                                                        else ioReturn ();
                                                        releaseFileLock lock;
                                                        if eqString action "run"
                                                        then case rest of {
                                                               (:) name arguments ->
                                                                 do {
                                                                   let {
                                                                     forwarded =
                                                                       let {
                                                                         matchValueShared11 =
                                                                           arguments
                                                                       } in
                                                                       case matchValueShared11 of {
                                                                         (:) matchValueShared12 matchValueShared13 ->
                                                                           if MLF.Primitive.eqString
                                                                                matchValueShared12
                                                                                "--"
                                                                           then let {
                                                                                  tail =
                                                                                    matchValueShared13
                                                                                } in
                                                                                tail
                                                                           else arguments;
                                                                         _ -> arguments
                                                                       }
                                                                   };
                                                                   code <-
                                                                     O.exec (M.packageRoot p)
                                                                       ((:)
                                                                          (B.executable b
                                                                             (dir ++
                                                                              ("/bin/" ++ name)))
                                                                          forwarded)
                                                                       ""
                                                                       ""
                                                                       ""
                                                                       (readInt
                                                                          (J.getText "timeout"
                                                                             "1800"
                                                                             config));
                                                                   exitWith code
                                                                 };
                                                               [] -> O.fatal usage
                                                             }
                                                        else putStrLn
                                                               (action ++
                                                                (" passed; report: " ++
                                                                 (dir ++ "/build-report.json")))
                                                      }
                                     }
                                 };
                               _ ->
                                 let {
                                   rest = matchValueShared16
                                 } in
                                 let {
                                   action = matchValueShared15
                                 } in
                                 do {
                                   O.require
                                     (S.elem eqString action
                                        (O.words "plan lock build test run release"))
                                     usage;
                                   let {
                                     manifest = J.getText "manifest" "mlf-package.json" config
                                   };
                                   path <- canonicalPath manifest;
                                   let {
                                     packageDir = O.parent path
                                   };
                                   let {
                                     buildDir =
                                       J.getText "build-dir" (packageDir ++ "/.mlf-build") config
                                   };
                                   let {
                                     building =
                                       S.elem eqString action (O.words "build test run release")
                                   };
                                   if building then O.mkdir buildDir else ioReturn ();
                                   dir <-
                                     if building then canonicalPath buildDir else ioReturn buildDir;
                                   lock <-
                                     if building
                                     then acquireFileLock (dir ++ "/.lock")
                                     else ioReturn (0 - 1);
                                   if building then B.recoverPublications dir else ioReturn ();
                                   if building
                                   then J.write (dir ++ "/build-report.json")
                                          (B.obj2 "complete" (J.Boolean False) "implementation"
                                             (J.str "MLF"))
                                   else ioReturn ();
                                   graph <-
                                     M.loadWith path
                                       (J.set "cache-dir"
                                          (J.getOr "cache-dir" (J.str (dir ++ "/cache")) config)
                                          config);
                                   snapshot <- M.snapshot graph;
                                   let {
                                     p = M.rootPackage graph
                                   };
                                   let {
                                     lockPath = (M.packageRoot p ++ "/mlf.lock")
                                   };
                                   if J.getBool "locked" False config
                                   then do {
                                          saved <- J.read lockPath;
                                          O.require (J.equal saved snapshot)
                                            "mlf.lock is stale; review local changes and run mlfpkg lock"
                                        }
                                   else ioReturn ();
                                   if eqString action "plan"
                                   then do {
                                          O.require (S.null rest) usage;
                                          crates <- M.cratePlan graph;
                                          putStrLn
                                            (J.render
                                               (J.set "crates" crates
                                                  (J.set "modules"
                                                     (J.stringArray
                                                        (S.map M.moduleName (M.modules graph)))
                                                     (J.set "executables"
                                                        (J.stringArray
                                                           (M.keys
                                                              (J.getObject "executables"
                                                                 (M.packageData p))))
                                                        (J.set "tests"
                                                           (J.stringArray
                                                              (M.keys
                                                                 (J.getObject "tests"
                                                                    (M.packageData p))))
                                                           snapshot)))))
                                        }
                                   else if eqString action "lock"
                                        then do {
                                               O.require (S.null rest) usage;
                                               J.write lockPath snapshot;
                                               putStrLn lockPath
                                             }
                                        else if eqString action "release"
                                             then case rest of {
                                                    (:) destination [] ->
                                                      do {
                                                        compilerSettings <-
                                                          configureCompiler p dir config;
                                                        settings <-
                                                          configureGC (M.packageRoot p)
                                                            compilerSettings;
                                                        b <- B.create graph settings dir;
                                                        B.releasePackage b destination;
                                                        B.finish b;
                                                        releaseFileLock lock;
                                                        putStrLn ("release passed: " ++ destination)
                                                      };
                                                    _ -> O.fatal usage
                                                  }
                                             else do {
                                                    let {
                                                      targets =
                                                        J.getObject
                                                          (if eqString action "test"
                                                           then "tests"
                                                           else "executables")
                                                          (M.packageData p)
                                                    };
                                                    selected <-
                                                      if eqString action "run"
                                                      then case rest of {
                                                             (:) name _ ->
                                                               ioReturn ((:) name []);
                                                             [] -> O.fatal usage
                                                           }
                                                      else selections [] rest;
                                                    let {
                                                      names =
                                                        if S.null selected
                                                        then M.keys targets
                                                        else selected
                                                    };
                                                    O.require
                                                      (S.all (\name -> J.has name targets) names)
                                                      ("unknown target; available: " ++
                                                       S.intercalate ", " (M.keys targets));
                                                    O.require
                                                      (S.not (S.null names) ||
                                                       (eqString action "build" &&
                                                        S.not (S.null (M.packageModules p))))
                                                      "no targets selected";
                                                    compilerSettings <-
                                                      configureCompiler p dir config;
                                                    settings <-
                                                      configureGC (M.packageRoot p)
                                                        compilerSettings;
                                                    b <- B.create graph settings dir;
                                                    built <-
                                                      Scheduler.execute b
                                                        (eqString action "build" && S.null names)
                                                        (buildRequests p action names);
                                                    if eqString action "test"
                                                    then runTests b p built names
                                                    else ioReturn ();
                                                    B.finish b;
                                                    if eqString action "build"
                                                    then S.mapM_
                                                           (\name ->
                                                              putStrLn
                                                                (B.executable b
                                                                   (dir ++ ("/bin/" ++ name))))
                                                           names
                                                    else ioReturn ();
                                                    releaseFileLock lock;
                                                    if eqString action "run"
                                                    then case rest of {
                                                           (:) name arguments ->
                                                             do {
                                                               let {
                                                                 forwarded =
                                                                   let {
                                                                     matchValueShared11 = arguments
                                                                   } in
                                                                   case matchValueShared11 of {
                                                                     (:) matchValueShared12 matchValueShared13 ->
                                                                       if MLF.Primitive.eqString
                                                                            matchValueShared12
                                                                            "--"
                                                                       then let {
                                                                              tail =
                                                                                matchValueShared13
                                                                            } in
                                                                            tail
                                                                       else arguments;
                                                                     _ -> arguments
                                                                   }
                                                               };
                                                               code <-
                                                                 O.exec (M.packageRoot p)
                                                                   ((:)
                                                                      (B.executable b
                                                                         (dir ++ ("/bin/" ++ name)))
                                                                      forwarded)
                                                                   ""
                                                                   ""
                                                                   ""
                                                                   (readInt
                                                                      (J.getText "timeout" "1800"
                                                                         config));
                                                               exitWith code
                                                             };
                                                           [] -> O.fatal usage
                                                         }
                                                    else putStrLn
                                                           (action ++
                                                            (" passed; report: " ++
                                                             (dir ++ "/build-report.json")))
                                                  }
                                 }
                             };
                           _ ->
                             let {
                               rest = matchValueShared16
                             } in
                             let {
                               action = matchValueShared15
                             } in
                             do {
                               O.require
                                 (S.elem eqString action
                                    (O.words "plan lock build test run release"))
                                 usage;
                               let {
                                 manifest = J.getText "manifest" "mlf-package.json" config
                               };
                               path <- canonicalPath manifest;
                               let {
                                 packageDir = O.parent path
                               };
                               let {
                                 buildDir =
                                   J.getText "build-dir" (packageDir ++ "/.mlf-build") config
                               };
                               let {
                                 building =
                                   S.elem eqString action (O.words "build test run release")
                               };
                               if building then O.mkdir buildDir else ioReturn ();
                               dir <-
                                 if building then canonicalPath buildDir else ioReturn buildDir;
                               lock <-
                                 if building
                                 then acquireFileLock (dir ++ "/.lock")
                                 else ioReturn (0 - 1);
                               if building then B.recoverPublications dir else ioReturn ();
                               if building
                               then J.write (dir ++ "/build-report.json")
                                      (B.obj2 "complete" (J.Boolean False) "implementation"
                                         (J.str "MLF"))
                               else ioReturn ();
                               graph <-
                                 M.loadWith path
                                   (J.set "cache-dir"
                                      (J.getOr "cache-dir" (J.str (dir ++ "/cache")) config)
                                      config);
                               snapshot <- M.snapshot graph;
                               let {
                                 p = M.rootPackage graph
                               };
                               let {
                                 lockPath = (M.packageRoot p ++ "/mlf.lock")
                               };
                               if J.getBool "locked" False config
                               then do {
                                      saved <- J.read lockPath;
                                      O.require (J.equal saved snapshot)
                                        "mlf.lock is stale; review local changes and run mlfpkg lock"
                                    }
                               else ioReturn ();
                               if eqString action "plan"
                               then do {
                                      O.require (S.null rest) usage;
                                      crates <- M.cratePlan graph;
                                      putStrLn
                                        (J.render
                                           (J.set "crates" crates
                                              (J.set "modules"
                                                 (J.stringArray
                                                    (S.map M.moduleName (M.modules graph)))
                                                 (J.set "executables"
                                                    (J.stringArray
                                                       (M.keys
                                                          (J.getObject "executables"
                                                             (M.packageData p))))
                                                    (J.set "tests"
                                                       (J.stringArray
                                                          (M.keys
                                                             (J.getObject "tests"
                                                                (M.packageData p))))
                                                       snapshot)))))
                                    }
                               else if eqString action "lock"
                                    then do {
                                           O.require (S.null rest) usage;
                                           J.write lockPath snapshot;
                                           putStrLn lockPath
                                         }
                                    else if eqString action "release"
                                         then case rest of {
                                                (:) destination [] ->
                                                  do {
                                                    compilerSettings <-
                                                      configureCompiler p dir config;
                                                    settings <-
                                                      configureGC (M.packageRoot p)
                                                        compilerSettings;
                                                    b <- B.create graph settings dir;
                                                    B.releasePackage b destination;
                                                    B.finish b;
                                                    releaseFileLock lock;
                                                    putStrLn ("release passed: " ++ destination)
                                                  };
                                                _ -> O.fatal usage
                                              }
                                         else do {
                                                let {
                                                  targets =
                                                    J.getObject
                                                      (if eqString action "test"
                                                       then "tests"
                                                       else "executables")
                                                      (M.packageData p)
                                                };
                                                selected <-
                                                  if eqString action "run"
                                                  then case rest of {
                                                         (:) name _ -> ioReturn ((:) name []);
                                                         [] -> O.fatal usage
                                                       }
                                                  else selections [] rest;
                                                let {
                                                  names =
                                                    if S.null selected
                                                    then M.keys targets
                                                    else selected
                                                };
                                                O.require
                                                  (S.all (\name -> J.has name targets) names)
                                                  ("unknown target; available: " ++
                                                   S.intercalate ", " (M.keys targets));
                                                O.require
                                                  (S.not (S.null names) ||
                                                   (eqString action "build" &&
                                                    S.not (S.null (M.packageModules p))))
                                                  "no targets selected";
                                                compilerSettings <- configureCompiler p dir config;
                                                settings <-
                                                  configureGC (M.packageRoot p) compilerSettings;
                                                b <- B.create graph settings dir;
                                                built <-
                                                  Scheduler.execute b
                                                    (eqString action "build" && S.null names)
                                                    (buildRequests p action names);
                                                if eqString action "test"
                                                then runTests b p built names
                                                else ioReturn ();
                                                B.finish b;
                                                if eqString action "build"
                                                then S.mapM_
                                                       (\name ->
                                                          putStrLn
                                                            (B.executable b
                                                               (dir ++ ("/bin/" ++ name))))
                                                       names
                                                else ioReturn ();
                                                releaseFileLock lock;
                                                if eqString action "run"
                                                then case rest of {
                                                       (:) name arguments ->
                                                         do {
                                                           let {
                                                             forwarded =
                                                               let {
                                                                 matchValueShared11 = arguments
                                                               } in
                                                               case matchValueShared11 of {
                                                                 (:) matchValueShared12 matchValueShared13 ->
                                                                   if MLF.Primitive.eqString
                                                                        matchValueShared12
                                                                        "--"
                                                                   then let {
                                                                          tail = matchValueShared13
                                                                        } in
                                                                        tail
                                                                   else arguments;
                                                                 _ -> arguments
                                                               }
                                                           };
                                                           code <-
                                                             O.exec (M.packageRoot p)
                                                               ((:)
                                                                  (B.executable b
                                                                     (dir ++ ("/bin/" ++ name)))
                                                                  forwarded)
                                                               ""
                                                               ""
                                                               ""
                                                               (readInt
                                                                  (J.getText "timeout" "1800"
                                                                     config));
                                                           exitWith code
                                                         };
                                                       [] -> O.fatal usage
                                                     }
                                                else putStrLn
                                                       (action ++
                                                        (" passed; report: " ++
                                                         (dir ++ "/build-report.json")))
                                              }
                             }
                         };
                       _ ->
                         let {
                           rest = matchValueShared16
                         } in
                         let {
                           action = matchValueShared15
                         } in
                         do {
                           O.require
                             (S.elem eqString action (O.words "plan lock build test run release"))
                             usage;
                           let {
                             manifest = J.getText "manifest" "mlf-package.json" config
                           };
                           path <- canonicalPath manifest;
                           let {
                             packageDir = O.parent path
                           };
                           let {
                             buildDir = J.getText "build-dir" (packageDir ++ "/.mlf-build") config
                           };
                           let {
                             building = S.elem eqString action (O.words "build test run release")
                           };
                           if building then O.mkdir buildDir else ioReturn ();
                           dir <- if building then canonicalPath buildDir else ioReturn buildDir;
                           lock <-
                             if building
                             then acquireFileLock (dir ++ "/.lock")
                             else ioReturn (0 - 1);
                           if building then B.recoverPublications dir else ioReturn ();
                           if building
                           then J.write (dir ++ "/build-report.json")
                                  (B.obj2 "complete" (J.Boolean False) "implementation"
                                     (J.str "MLF"))
                           else ioReturn ();
                           graph <-
                             M.loadWith path
                               (J.set "cache-dir"
                                  (J.getOr "cache-dir" (J.str (dir ++ "/cache")) config)
                                  config);
                           snapshot <- M.snapshot graph;
                           let {
                             p = M.rootPackage graph
                           };
                           let {
                             lockPath = (M.packageRoot p ++ "/mlf.lock")
                           };
                           if J.getBool "locked" False config
                           then do {
                                  saved <- J.read lockPath;
                                  O.require (J.equal saved snapshot)
                                    "mlf.lock is stale; review local changes and run mlfpkg lock"
                                }
                           else ioReturn ();
                           if eqString action "plan"
                           then do {
                                  O.require (S.null rest) usage;
                                  crates <- M.cratePlan graph;
                                  putStrLn
                                    (J.render
                                       (J.set "crates" crates
                                          (J.set "modules"
                                             (J.stringArray (S.map M.moduleName (M.modules graph)))
                                             (J.set "executables"
                                                (J.stringArray
                                                   (M.keys
                                                      (J.getObject "executables"
                                                         (M.packageData p))))
                                                (J.set "tests"
                                                   (J.stringArray
                                                      (M.keys
                                                         (J.getObject "tests" (M.packageData p))))
                                                   snapshot)))))
                                }
                           else if eqString action "lock"
                                then do {
                                       O.require (S.null rest) usage;
                                       J.write lockPath snapshot;
                                       putStrLn lockPath
                                     }
                                else if eqString action "release"
                                     then case rest of {
                                            (:) destination [] ->
                                              do {
                                                compilerSettings <- configureCompiler p dir config;
                                                settings <-
                                                  configureGC (M.packageRoot p) compilerSettings;
                                                b <- B.create graph settings dir;
                                                B.releasePackage b destination;
                                                B.finish b;
                                                releaseFileLock lock;
                                                putStrLn ("release passed: " ++ destination)
                                              };
                                            _ -> O.fatal usage
                                          }
                                     else do {
                                            let {
                                              targets =
                                                J.getObject
                                                  (if eqString action "test"
                                                   then "tests"
                                                   else "executables")
                                                  (M.packageData p)
                                            };
                                            selected <-
                                              if eqString action "run"
                                              then case rest of {
                                                     (:) name _ -> ioReturn ((:) name []);
                                                     [] -> O.fatal usage
                                                   }
                                              else selections [] rest;
                                            let {
                                              names =
                                                if S.null selected then M.keys targets else selected
                                            };
                                            O.require (S.all (\name -> J.has name targets) names)
                                              ("unknown target; available: " ++
                                               S.intercalate ", " (M.keys targets));
                                            O.require
                                              (S.not (S.null names) ||
                                               (eqString action "build" &&
                                                S.not (S.null (M.packageModules p))))
                                              "no targets selected";
                                            compilerSettings <- configureCompiler p dir config;
                                            settings <-
                                              configureGC (M.packageRoot p) compilerSettings;
                                            b <- B.create graph settings dir;
                                            built <-
                                              Scheduler.execute b
                                                (eqString action "build" && S.null names)
                                                (buildRequests p action names);
                                            if eqString action "test"
                                            then runTests b p built names
                                            else ioReturn ();
                                            B.finish b;
                                            if eqString action "build"
                                            then S.mapM_
                                                   (\name ->
                                                      putStrLn
                                                        (B.executable b (dir ++ ("/bin/" ++ name))))
                                                   names
                                            else ioReturn ();
                                            releaseFileLock lock;
                                            if eqString action "run"
                                            then case rest of {
                                                   (:) name arguments ->
                                                     do {
                                                       let {
                                                         forwarded =
                                                           let {
                                                             matchValueShared11 = arguments
                                                           } in
                                                           case matchValueShared11 of {
                                                             (:) matchValueShared12 matchValueShared13 ->
                                                               if MLF.Primitive.eqString
                                                                    matchValueShared12
                                                                    "--"
                                                               then let {
                                                                      tail = matchValueShared13
                                                                    } in
                                                                    tail
                                                               else arguments;
                                                             _ -> arguments
                                                           }
                                                       };
                                                       code <-
                                                         O.exec (M.packageRoot p)
                                                           ((:)
                                                              (B.executable b
                                                                 (dir ++ ("/bin/" ++ name)))
                                                              forwarded)
                                                           ""
                                                           ""
                                                           ""
                                                           (readInt
                                                              (J.getText "timeout" "1800" config));
                                                       exitWith code
                                                     };
                                                   [] -> O.fatal usage
                                                 }
                                            else putStrLn
                                                   (action ++
                                                    (" passed; report: " ++
                                                     (dir ++ "/build-report.json")))
                                          }
                         }
                     }
                else if MLF.Primitive.eqString matchValueShared15 "--help"
                     then case matchValueShared16 of {
                            [] -> putStr usage;
                            _ ->
                              let {
                                rest = matchValueShared16
                              } in
                              let {
                                action = matchValueShared15
                              } in
                              do {
                                O.require
                                  (S.elem eqString action
                                     (O.words "plan lock build test run release"))
                                  usage;
                                let {
                                  manifest = J.getText "manifest" "mlf-package.json" config
                                };
                                path <- canonicalPath manifest;
                                let {
                                  packageDir = O.parent path
                                };
                                let {
                                  buildDir =
                                    J.getText "build-dir" (packageDir ++ "/.mlf-build") config
                                };
                                let {
                                  building =
                                    S.elem eqString action (O.words "build test run release")
                                };
                                if building then O.mkdir buildDir else ioReturn ();
                                dir <-
                                  if building then canonicalPath buildDir else ioReturn buildDir;
                                lock <-
                                  if building
                                  then acquireFileLock (dir ++ "/.lock")
                                  else ioReturn (0 - 1);
                                if building then B.recoverPublications dir else ioReturn ();
                                if building
                                then J.write (dir ++ "/build-report.json")
                                       (B.obj2 "complete" (J.Boolean False) "implementation"
                                          (J.str "MLF"))
                                else ioReturn ();
                                graph <-
                                  M.loadWith path
                                    (J.set "cache-dir"
                                       (J.getOr "cache-dir" (J.str (dir ++ "/cache")) config)
                                       config);
                                snapshot <- M.snapshot graph;
                                let {
                                  p = M.rootPackage graph
                                };
                                let {
                                  lockPath = (M.packageRoot p ++ "/mlf.lock")
                                };
                                if J.getBool "locked" False config
                                then do {
                                       saved <- J.read lockPath;
                                       O.require (J.equal saved snapshot)
                                         "mlf.lock is stale; review local changes and run mlfpkg lock"
                                     }
                                else ioReturn ();
                                if eqString action "plan"
                                then do {
                                       O.require (S.null rest) usage;
                                       crates <- M.cratePlan graph;
                                       putStrLn
                                         (J.render
                                            (J.set "crates" crates
                                               (J.set "modules"
                                                  (J.stringArray
                                                     (S.map M.moduleName (M.modules graph)))
                                                  (J.set "executables"
                                                     (J.stringArray
                                                        (M.keys
                                                           (J.getObject "executables"
                                                              (M.packageData p))))
                                                     (J.set "tests"
                                                        (J.stringArray
                                                           (M.keys
                                                              (J.getObject "tests"
                                                                 (M.packageData p))))
                                                        snapshot)))))
                                     }
                                else if eqString action "lock"
                                     then do {
                                            O.require (S.null rest) usage;
                                            J.write lockPath snapshot;
                                            putStrLn lockPath
                                          }
                                     else if eqString action "release"
                                          then case rest of {
                                                 (:) destination [] ->
                                                   do {
                                                     compilerSettings <-
                                                       configureCompiler p dir config;
                                                     settings <-
                                                       configureGC (M.packageRoot p)
                                                         compilerSettings;
                                                     b <- B.create graph settings dir;
                                                     B.releasePackage b destination;
                                                     B.finish b;
                                                     releaseFileLock lock;
                                                     putStrLn ("release passed: " ++ destination)
                                                   };
                                                 _ -> O.fatal usage
                                               }
                                          else do {
                                                 let {
                                                   targets =
                                                     J.getObject
                                                       (if eqString action "test"
                                                        then "tests"
                                                        else "executables")
                                                       (M.packageData p)
                                                 };
                                                 selected <-
                                                   if eqString action "run"
                                                   then case rest of {
                                                          (:) name _ -> ioReturn ((:) name []);
                                                          [] -> O.fatal usage
                                                        }
                                                   else selections [] rest;
                                                 let {
                                                   names =
                                                     if S.null selected
                                                     then M.keys targets
                                                     else selected
                                                 };
                                                 O.require
                                                   (S.all (\name -> J.has name targets) names)
                                                   ("unknown target; available: " ++
                                                    S.intercalate ", " (M.keys targets));
                                                 O.require
                                                   (S.not (S.null names) ||
                                                    (eqString action "build" &&
                                                     S.not (S.null (M.packageModules p))))
                                                   "no targets selected";
                                                 compilerSettings <- configureCompiler p dir config;
                                                 settings <-
                                                   configureGC (M.packageRoot p) compilerSettings;
                                                 b <- B.create graph settings dir;
                                                 built <-
                                                   Scheduler.execute b
                                                     (eqString action "build" && S.null names)
                                                     (buildRequests p action names);
                                                 if eqString action "test"
                                                 then runTests b p built names
                                                 else ioReturn ();
                                                 B.finish b;
                                                 if eqString action "build"
                                                 then S.mapM_
                                                        (\name ->
                                                           putStrLn
                                                             (B.executable b
                                                                (dir ++ ("/bin/" ++ name))))
                                                        names
                                                 else ioReturn ();
                                                 releaseFileLock lock;
                                                 if eqString action "run"
                                                 then case rest of {
                                                        (:) name arguments ->
                                                          do {
                                                            let {
                                                              forwarded =
                                                                let {
                                                                  matchValueShared11 = arguments
                                                                } in
                                                                case matchValueShared11 of {
                                                                  (:) matchValueShared12 matchValueShared13 ->
                                                                    if MLF.Primitive.eqString
                                                                         matchValueShared12
                                                                         "--"
                                                                    then let {
                                                                           tail = matchValueShared13
                                                                         } in
                                                                         tail
                                                                    else arguments;
                                                                  _ -> arguments
                                                                }
                                                            };
                                                            code <-
                                                              O.exec (M.packageRoot p)
                                                                ((:)
                                                                   (B.executable b
                                                                      (dir ++ ("/bin/" ++ name)))
                                                                   forwarded)
                                                                ""
                                                                ""
                                                                ""
                                                                (readInt
                                                                   (J.getText "timeout" "1800"
                                                                      config));
                                                            exitWith code
                                                          };
                                                        [] -> O.fatal usage
                                                      }
                                                 else putStrLn
                                                        (action ++
                                                         (" passed; report: " ++
                                                          (dir ++ "/build-report.json")))
                                               }
                              }
                          }
                     else if MLF.Primitive.eqString matchValueShared15 "pack"
                          then case matchValueShared16 of {
                                 (:) matchValueShared17 matchValueShared18 ->
                                   case matchValueShared18 of {
                                     (:) matchValueShared19 matchValueShared20 ->
                                       case matchValueShared20 of {
                                         [] ->
                                           let {
                                             directory = matchValueShared17
                                           } in
                                           let {
                                             output = matchValueShared19
                                           } in
                                           do {
                                             pins <- Distribution.pack directory output;
                                             putStrLn (J.render pins)
                                           };
                                         _ ->
                                           let {
                                             rest = matchValueShared16
                                           } in
                                           let {
                                             action = matchValueShared15
                                           } in
                                           do {
                                             O.require
                                               (S.elem eqString action
                                                  (O.words "plan lock build test run release"))
                                               usage;
                                             let {
                                               manifest =
                                                 J.getText "manifest" "mlf-package.json" config
                                             };
                                             path <- canonicalPath manifest;
                                             let {
                                               packageDir = O.parent path
                                             };
                                             let {
                                               buildDir =
                                                 J.getText "build-dir" (packageDir ++ "/.mlf-build")
                                                   config
                                             };
                                             let {
                                               building =
                                                 S.elem eqString action
                                                   (O.words "build test run release")
                                             };
                                             if building then O.mkdir buildDir else ioReturn ();
                                             dir <-
                                               if building
                                               then canonicalPath buildDir
                                               else ioReturn buildDir;
                                             lock <-
                                               if building
                                               then acquireFileLock (dir ++ "/.lock")
                                               else ioReturn (0 - 1);
                                             if building
                                             then B.recoverPublications dir
                                             else ioReturn ();
                                             if building
                                             then J.write (dir ++ "/build-report.json")
                                                    (B.obj2 "complete" (J.Boolean False)
                                                       "implementation"
                                                       (J.str "MLF"))
                                             else ioReturn ();
                                             graph <-
                                               M.loadWith path
                                                 (J.set "cache-dir"
                                                    (J.getOr "cache-dir" (J.str (dir ++ "/cache"))
                                                       config)
                                                    config);
                                             snapshot <- M.snapshot graph;
                                             let {
                                               p = M.rootPackage graph
                                             };
                                             let {
                                               lockPath = (M.packageRoot p ++ "/mlf.lock")
                                             };
                                             if J.getBool "locked" False config
                                             then do {
                                                    saved <- J.read lockPath;
                                                    O.require (J.equal saved snapshot)
                                                      "mlf.lock is stale; review local changes and run mlfpkg lock"
                                                  }
                                             else ioReturn ();
                                             if eqString action "plan"
                                             then do {
                                                    O.require (S.null rest) usage;
                                                    crates <- M.cratePlan graph;
                                                    putStrLn
                                                      (J.render
                                                         (J.set "crates" crates
                                                            (J.set "modules"
                                                               (J.stringArray
                                                                  (S.map M.moduleName
                                                                     (M.modules graph)))
                                                               (J.set "executables"
                                                                  (J.stringArray
                                                                     (M.keys
                                                                        (J.getObject "executables"
                                                                           (M.packageData p))))
                                                                  (J.set "tests"
                                                                     (J.stringArray
                                                                        (M.keys
                                                                           (J.getObject "tests"
                                                                              (M.packageData p))))
                                                                     snapshot)))))
                                                  }
                                             else if eqString action "lock"
                                                  then do {
                                                         O.require (S.null rest) usage;
                                                         J.write lockPath snapshot;
                                                         putStrLn lockPath
                                                       }
                                                  else if eqString action "release"
                                                       then case rest of {
                                                              (:) destination [] ->
                                                                do {
                                                                  compilerSettings <-
                                                                    configureCompiler p dir config;
                                                                  settings <-
                                                                    configureGC (M.packageRoot p)
                                                                      compilerSettings;
                                                                  b <- B.create graph settings dir;
                                                                  B.releasePackage b destination;
                                                                  B.finish b;
                                                                  releaseFileLock lock;
                                                                  putStrLn
                                                                    ("release passed: " ++
                                                                     destination)
                                                                };
                                                              _ -> O.fatal usage
                                                            }
                                                       else do {
                                                              let {
                                                                targets =
                                                                  J.getObject
                                                                    (if eqString action "test"
                                                                     then "tests"
                                                                     else "executables")
                                                                    (M.packageData p)
                                                              };
                                                              selected <-
                                                                if eqString action "run"
                                                                then case rest of {
                                                                       (:) name _ ->
                                                                         ioReturn ((:) name []);
                                                                       [] -> O.fatal usage
                                                                     }
                                                                else selections [] rest;
                                                              let {
                                                                names =
                                                                  if S.null selected
                                                                  then M.keys targets
                                                                  else selected
                                                              };
                                                              O.require
                                                                (S.all (\name -> J.has name targets)
                                                                   names)
                                                                ("unknown target; available: " ++
                                                                 S.intercalate ", "
                                                                   (M.keys targets));
                                                              O.require
                                                                (S.not (S.null names) ||
                                                                 (eqString action "build" &&
                                                                  S.not
                                                                    (S.null (M.packageModules p))))
                                                                "no targets selected";
                                                              compilerSettings <-
                                                                configureCompiler p dir config;
                                                              settings <-
                                                                configureGC (M.packageRoot p)
                                                                  compilerSettings;
                                                              b <- B.create graph settings dir;
                                                              built <-
                                                                Scheduler.execute b
                                                                  (eqString action "build" &&
                                                                   S.null names)
                                                                  (buildRequests p action names);
                                                              if eqString action "test"
                                                              then runTests b p built names
                                                              else ioReturn ();
                                                              B.finish b;
                                                              if eqString action "build"
                                                              then S.mapM_
                                                                     (\name ->
                                                                        putStrLn
                                                                          (B.executable b
                                                                             (dir ++
                                                                              ("/bin/" ++ name))))
                                                                     names
                                                              else ioReturn ();
                                                              releaseFileLock lock;
                                                              if eqString action "run"
                                                              then case rest of {
                                                                     (:) name arguments ->
                                                                       do {
                                                                         let {
                                                                           forwarded =
                                                                             let {
                                                                               matchValueShared11 =
                                                                                 arguments
                                                                             } in
                                                                             case matchValueShared11 of {
                                                                               (:) matchValueShared12 matchValueShared13 ->
                                                                                 if MLF.Primitive.eqString
                                                                                      matchValueShared12
                                                                                      "--"
                                                                                 then let {
                                                                                        tail =
                                                                                          matchValueShared13
                                                                                      } in
                                                                                      tail
                                                                                 else arguments;
                                                                               _ -> arguments
                                                                             }
                                                                         };
                                                                         code <-
                                                                           O.exec (M.packageRoot p)
                                                                             ((:)
                                                                                (B.executable b
                                                                                   (dir ++
                                                                                    ("/bin/" ++
                                                                                     name)))
                                                                                forwarded)
                                                                             ""
                                                                             ""
                                                                             ""
                                                                             (readInt
                                                                                (J.getText "timeout"
                                                                                   "1800"
                                                                                   config));
                                                                         exitWith code
                                                                       };
                                                                     [] -> O.fatal usage
                                                                   }
                                                              else putStrLn
                                                                     (action ++
                                                                      (" passed; report: " ++
                                                                       (dir ++
                                                                        "/build-report.json")))
                                                            }
                                           }
                                       };
                                     _ ->
                                       let {
                                         rest = matchValueShared16
                                       } in
                                       let {
                                         action = matchValueShared15
                                       } in
                                       do {
                                         O.require
                                           (S.elem eqString action
                                              (O.words "plan lock build test run release"))
                                           usage;
                                         let {
                                           manifest = J.getText "manifest" "mlf-package.json" config
                                         };
                                         path <- canonicalPath manifest;
                                         let {
                                           packageDir = O.parent path
                                         };
                                         let {
                                           buildDir =
                                             J.getText "build-dir" (packageDir ++ "/.mlf-build")
                                               config
                                         };
                                         let {
                                           building =
                                             S.elem eqString action
                                               (O.words "build test run release")
                                         };
                                         if building then O.mkdir buildDir else ioReturn ();
                                         dir <-
                                           if building
                                           then canonicalPath buildDir
                                           else ioReturn buildDir;
                                         lock <-
                                           if building
                                           then acquireFileLock (dir ++ "/.lock")
                                           else ioReturn (0 - 1);
                                         if building
                                         then B.recoverPublications dir
                                         else ioReturn ();
                                         if building
                                         then J.write (dir ++ "/build-report.json")
                                                (B.obj2 "complete" (J.Boolean False)
                                                   "implementation"
                                                   (J.str "MLF"))
                                         else ioReturn ();
                                         graph <-
                                           M.loadWith path
                                             (J.set "cache-dir"
                                                (J.getOr "cache-dir" (J.str (dir ++ "/cache"))
                                                   config)
                                                config);
                                         snapshot <- M.snapshot graph;
                                         let {
                                           p = M.rootPackage graph
                                         };
                                         let {
                                           lockPath = (M.packageRoot p ++ "/mlf.lock")
                                         };
                                         if J.getBool "locked" False config
                                         then do {
                                                saved <- J.read lockPath;
                                                O.require (J.equal saved snapshot)
                                                  "mlf.lock is stale; review local changes and run mlfpkg lock"
                                              }
                                         else ioReturn ();
                                         if eqString action "plan"
                                         then do {
                                                O.require (S.null rest) usage;
                                                crates <- M.cratePlan graph;
                                                putStrLn
                                                  (J.render
                                                     (J.set "crates" crates
                                                        (J.set "modules"
                                                           (J.stringArray
                                                              (S.map M.moduleName
                                                                 (M.modules graph)))
                                                           (J.set "executables"
                                                              (J.stringArray
                                                                 (M.keys
                                                                    (J.getObject "executables"
                                                                       (M.packageData p))))
                                                              (J.set "tests"
                                                                 (J.stringArray
                                                                    (M.keys
                                                                       (J.getObject "tests"
                                                                          (M.packageData p))))
                                                                 snapshot)))))
                                              }
                                         else if eqString action "lock"
                                              then do {
                                                     O.require (S.null rest) usage;
                                                     J.write lockPath snapshot;
                                                     putStrLn lockPath
                                                   }
                                              else if eqString action "release"
                                                   then case rest of {
                                                          (:) destination [] ->
                                                            do {
                                                              compilerSettings <-
                                                                configureCompiler p dir config;
                                                              settings <-
                                                                configureGC (M.packageRoot p)
                                                                  compilerSettings;
                                                              b <- B.create graph settings dir;
                                                              B.releasePackage b destination;
                                                              B.finish b;
                                                              releaseFileLock lock;
                                                              putStrLn
                                                                ("release passed: " ++ destination)
                                                            };
                                                          _ -> O.fatal usage
                                                        }
                                                   else do {
                                                          let {
                                                            targets =
                                                              J.getObject
                                                                (if eqString action "test"
                                                                 then "tests"
                                                                 else "executables")
                                                                (M.packageData p)
                                                          };
                                                          selected <-
                                                            if eqString action "run"
                                                            then case rest of {
                                                                   (:) name _ ->
                                                                     ioReturn ((:) name []);
                                                                   [] -> O.fatal usage
                                                                 }
                                                            else selections [] rest;
                                                          let {
                                                            names =
                                                              if S.null selected
                                                              then M.keys targets
                                                              else selected
                                                          };
                                                          O.require
                                                            (S.all (\name -> J.has name targets)
                                                               names)
                                                            ("unknown target; available: " ++
                                                             S.intercalate ", " (M.keys targets));
                                                          O.require
                                                            (S.not (S.null names) ||
                                                             (eqString action "build" &&
                                                              S.not (S.null (M.packageModules p))))
                                                            "no targets selected";
                                                          compilerSettings <-
                                                            configureCompiler p dir config;
                                                          settings <-
                                                            configureGC (M.packageRoot p)
                                                              compilerSettings;
                                                          b <- B.create graph settings dir;
                                                          built <-
                                                            Scheduler.execute b
                                                              (eqString action "build" &&
                                                               S.null names)
                                                              (buildRequests p action names);
                                                          if eqString action "test"
                                                          then runTests b p built names
                                                          else ioReturn ();
                                                          B.finish b;
                                                          if eqString action "build"
                                                          then S.mapM_
                                                                 (\name ->
                                                                    putStrLn
                                                                      (B.executable b
                                                                         (dir ++
                                                                          ("/bin/" ++ name))))
                                                                 names
                                                          else ioReturn ();
                                                          releaseFileLock lock;
                                                          if eqString action "run"
                                                          then case rest of {
                                                                 (:) name arguments ->
                                                                   do {
                                                                     let {
                                                                       forwarded =
                                                                         let {
                                                                           matchValueShared11 =
                                                                             arguments
                                                                         } in
                                                                         case matchValueShared11 of {
                                                                           (:) matchValueShared12 matchValueShared13 ->
                                                                             if MLF.Primitive.eqString
                                                                                  matchValueShared12
                                                                                  "--"
                                                                             then let {
                                                                                    tail =
                                                                                      matchValueShared13
                                                                                  } in
                                                                                  tail
                                                                             else arguments;
                                                                           _ -> arguments
                                                                         }
                                                                     };
                                                                     code <-
                                                                       O.exec (M.packageRoot p)
                                                                         ((:)
                                                                            (B.executable b
                                                                               (dir ++
                                                                                ("/bin/" ++ name)))
                                                                            forwarded)
                                                                         ""
                                                                         ""
                                                                         ""
                                                                         (readInt
                                                                            (J.getText "timeout"
                                                                               "1800"
                                                                               config));
                                                                     exitWith code
                                                                   };
                                                                 [] -> O.fatal usage
                                                               }
                                                          else putStrLn
                                                                 (action ++
                                                                  (" passed; report: " ++
                                                                   (dir ++ "/build-report.json")))
                                                        }
                                       }
                                   };
                                 _ ->
                                   let {
                                     rest = matchValueShared16
                                   } in
                                   let {
                                     action = matchValueShared15
                                   } in
                                   do {
                                     O.require
                                       (S.elem eqString action
                                          (O.words "plan lock build test run release"))
                                       usage;
                                     let {
                                       manifest = J.getText "manifest" "mlf-package.json" config
                                     };
                                     path <- canonicalPath manifest;
                                     let {
                                       packageDir = O.parent path
                                     };
                                     let {
                                       buildDir =
                                         J.getText "build-dir" (packageDir ++ "/.mlf-build") config
                                     };
                                     let {
                                       building =
                                         S.elem eqString action (O.words "build test run release")
                                     };
                                     if building then O.mkdir buildDir else ioReturn ();
                                     dir <-
                                       if building
                                       then canonicalPath buildDir
                                       else ioReturn buildDir;
                                     lock <-
                                       if building
                                       then acquireFileLock (dir ++ "/.lock")
                                       else ioReturn (0 - 1);
                                     if building then B.recoverPublications dir else ioReturn ();
                                     if building
                                     then J.write (dir ++ "/build-report.json")
                                            (B.obj2 "complete" (J.Boolean False) "implementation"
                                               (J.str "MLF"))
                                     else ioReturn ();
                                     graph <-
                                       M.loadWith path
                                         (J.set "cache-dir"
                                            (J.getOr "cache-dir" (J.str (dir ++ "/cache")) config)
                                            config);
                                     snapshot <- M.snapshot graph;
                                     let {
                                       p = M.rootPackage graph
                                     };
                                     let {
                                       lockPath = (M.packageRoot p ++ "/mlf.lock")
                                     };
                                     if J.getBool "locked" False config
                                     then do {
                                            saved <- J.read lockPath;
                                            O.require (J.equal saved snapshot)
                                              "mlf.lock is stale; review local changes and run mlfpkg lock"
                                          }
                                     else ioReturn ();
                                     if eqString action "plan"
                                     then do {
                                            O.require (S.null rest) usage;
                                            crates <- M.cratePlan graph;
                                            putStrLn
                                              (J.render
                                                 (J.set "crates" crates
                                                    (J.set "modules"
                                                       (J.stringArray
                                                          (S.map M.moduleName (M.modules graph)))
                                                       (J.set "executables"
                                                          (J.stringArray
                                                             (M.keys
                                                                (J.getObject "executables"
                                                                   (M.packageData p))))
                                                          (J.set "tests"
                                                             (J.stringArray
                                                                (M.keys
                                                                   (J.getObject "tests"
                                                                      (M.packageData p))))
                                                             snapshot)))))
                                          }
                                     else if eqString action "lock"
                                          then do {
                                                 O.require (S.null rest) usage;
                                                 J.write lockPath snapshot;
                                                 putStrLn lockPath
                                               }
                                          else if eqString action "release"
                                               then case rest of {
                                                      (:) destination [] ->
                                                        do {
                                                          compilerSettings <-
                                                            configureCompiler p dir config;
                                                          settings <-
                                                            configureGC (M.packageRoot p)
                                                              compilerSettings;
                                                          b <- B.create graph settings dir;
                                                          B.releasePackage b destination;
                                                          B.finish b;
                                                          releaseFileLock lock;
                                                          putStrLn
                                                            ("release passed: " ++ destination)
                                                        };
                                                      _ -> O.fatal usage
                                                    }
                                               else do {
                                                      let {
                                                        targets =
                                                          J.getObject
                                                            (if eqString action "test"
                                                             then "tests"
                                                             else "executables")
                                                            (M.packageData p)
                                                      };
                                                      selected <-
                                                        if eqString action "run"
                                                        then case rest of {
                                                               (:) name _ ->
                                                                 ioReturn ((:) name []);
                                                               [] -> O.fatal usage
                                                             }
                                                        else selections [] rest;
                                                      let {
                                                        names =
                                                          if S.null selected
                                                          then M.keys targets
                                                          else selected
                                                      };
                                                      O.require
                                                        (S.all (\name -> J.has name targets) names)
                                                        ("unknown target; available: " ++
                                                         S.intercalate ", " (M.keys targets));
                                                      O.require
                                                        (S.not (S.null names) ||
                                                         (eqString action "build" &&
                                                          S.not (S.null (M.packageModules p))))
                                                        "no targets selected";
                                                      compilerSettings <-
                                                        configureCompiler p dir config;
                                                      settings <-
                                                        configureGC (M.packageRoot p)
                                                          compilerSettings;
                                                      b <- B.create graph settings dir;
                                                      built <-
                                                        Scheduler.execute b
                                                          (eqString action "build" && S.null names)
                                                          (buildRequests p action names);
                                                      if eqString action "test"
                                                      then runTests b p built names
                                                      else ioReturn ();
                                                      B.finish b;
                                                      if eqString action "build"
                                                      then S.mapM_
                                                             (\name ->
                                                                putStrLn
                                                                  (B.executable b
                                                                     (dir ++ ("/bin/" ++ name))))
                                                             names
                                                      else ioReturn ();
                                                      releaseFileLock lock;
                                                      if eqString action "run"
                                                      then case rest of {
                                                             (:) name arguments ->
                                                               do {
                                                                 let {
                                                                   forwarded =
                                                                     let {
                                                                       matchValueShared11 =
                                                                         arguments
                                                                     } in
                                                                     case matchValueShared11 of {
                                                                       (:) matchValueShared12 matchValueShared13 ->
                                                                         if MLF.Primitive.eqString
                                                                              matchValueShared12
                                                                              "--"
                                                                         then let {
                                                                                tail =
                                                                                  matchValueShared13
                                                                              } in
                                                                              tail
                                                                         else arguments;
                                                                       _ -> arguments
                                                                     }
                                                                 };
                                                                 code <-
                                                                   O.exec (M.packageRoot p)
                                                                     ((:)
                                                                        (B.executable b
                                                                           (dir ++
                                                                            ("/bin/" ++ name)))
                                                                        forwarded)
                                                                     ""
                                                                     ""
                                                                     ""
                                                                     (readInt
                                                                        (J.getText "timeout" "1800"
                                                                           config));
                                                                 exitWith code
                                                               };
                                                             [] -> O.fatal usage
                                                           }
                                                      else putStrLn
                                                             (action ++
                                                              (" passed; report: " ++
                                                               (dir ++ "/build-report.json")))
                                                    }
                                   }
                               }
                          else let {
                                 rest = matchValueShared16
                               } in
                               let {
                                 action = matchValueShared15
                               } in
                               do {
                                 O.require
                                   (S.elem eqString action
                                      (O.words "plan lock build test run release"))
                                   usage;
                                 let {
                                   manifest = J.getText "manifest" "mlf-package.json" config
                                 };
                                 path <- canonicalPath manifest;
                                 let {
                                   packageDir = O.parent path
                                 };
                                 let {
                                   buildDir =
                                     J.getText "build-dir" (packageDir ++ "/.mlf-build") config
                                 };
                                 let {
                                   building =
                                     S.elem eqString action (O.words "build test run release")
                                 };
                                 if building then O.mkdir buildDir else ioReturn ();
                                 dir <-
                                   if building then canonicalPath buildDir else ioReturn buildDir;
                                 lock <-
                                   if building
                                   then acquireFileLock (dir ++ "/.lock")
                                   else ioReturn (0 - 1);
                                 if building then B.recoverPublications dir else ioReturn ();
                                 if building
                                 then J.write (dir ++ "/build-report.json")
                                        (B.obj2 "complete" (J.Boolean False) "implementation"
                                           (J.str "MLF"))
                                 else ioReturn ();
                                 graph <-
                                   M.loadWith path
                                     (J.set "cache-dir"
                                        (J.getOr "cache-dir" (J.str (dir ++ "/cache")) config)
                                        config);
                                 snapshot <- M.snapshot graph;
                                 let {
                                   p = M.rootPackage graph
                                 };
                                 let {
                                   lockPath = (M.packageRoot p ++ "/mlf.lock")
                                 };
                                 if J.getBool "locked" False config
                                 then do {
                                        saved <- J.read lockPath;
                                        O.require (J.equal saved snapshot)
                                          "mlf.lock is stale; review local changes and run mlfpkg lock"
                                      }
                                 else ioReturn ();
                                 if eqString action "plan"
                                 then do {
                                        O.require (S.null rest) usage;
                                        crates <- M.cratePlan graph;
                                        putStrLn
                                          (J.render
                                             (J.set "crates" crates
                                                (J.set "modules"
                                                   (J.stringArray
                                                      (S.map M.moduleName (M.modules graph)))
                                                   (J.set "executables"
                                                      (J.stringArray
                                                         (M.keys
                                                            (J.getObject "executables"
                                                               (M.packageData p))))
                                                      (J.set "tests"
                                                         (J.stringArray
                                                            (M.keys
                                                               (J.getObject "tests"
                                                                  (M.packageData p))))
                                                         snapshot)))))
                                      }
                                 else if eqString action "lock"
                                      then do {
                                             O.require (S.null rest) usage;
                                             J.write lockPath snapshot;
                                             putStrLn lockPath
                                           }
                                      else if eqString action "release"
                                           then case rest of {
                                                  (:) destination [] ->
                                                    do {
                                                      compilerSettings <-
                                                        configureCompiler p dir config;
                                                      settings <-
                                                        configureGC (M.packageRoot p)
                                                          compilerSettings;
                                                      b <- B.create graph settings dir;
                                                      B.releasePackage b destination;
                                                      B.finish b;
                                                      releaseFileLock lock;
                                                      putStrLn ("release passed: " ++ destination)
                                                    };
                                                  _ -> O.fatal usage
                                                }
                                           else do {
                                                  let {
                                                    targets =
                                                      J.getObject
                                                        (if eqString action "test"
                                                         then "tests"
                                                         else "executables")
                                                        (M.packageData p)
                                                  };
                                                  selected <-
                                                    if eqString action "run"
                                                    then case rest of {
                                                           (:) name _ -> ioReturn ((:) name []);
                                                           [] -> O.fatal usage
                                                         }
                                                    else selections [] rest;
                                                  let {
                                                    names =
                                                      if S.null selected
                                                      then M.keys targets
                                                      else selected
                                                  };
                                                  O.require
                                                    (S.all (\name -> J.has name targets) names)
                                                    ("unknown target; available: " ++
                                                     S.intercalate ", " (M.keys targets));
                                                  O.require
                                                    (S.not (S.null names) ||
                                                     (eqString action "build" &&
                                                      S.not (S.null (M.packageModules p))))
                                                    "no targets selected";
                                                  compilerSettings <-
                                                    configureCompiler p dir config;
                                                  settings <-
                                                    configureGC (M.packageRoot p) compilerSettings;
                                                  b <- B.create graph settings dir;
                                                  built <-
                                                    Scheduler.execute b
                                                      (eqString action "build" && S.null names)
                                                      (buildRequests p action names);
                                                  if eqString action "test"
                                                  then runTests b p built names
                                                  else ioReturn ();
                                                  B.finish b;
                                                  if eqString action "build"
                                                  then S.mapM_
                                                         (\name ->
                                                            putStrLn
                                                              (B.executable b
                                                                 (dir ++ ("/bin/" ++ name))))
                                                         names
                                                  else ioReturn ();
                                                  releaseFileLock lock;
                                                  if eqString action "run"
                                                  then case rest of {
                                                         (:) name arguments ->
                                                           do {
                                                             let {
                                                               forwarded =
                                                                 let {
                                                                   matchValueShared11 = arguments
                                                                 } in
                                                                 case matchValueShared11 of {
                                                                   (:) matchValueShared12 matchValueShared13 ->
                                                                     if MLF.Primitive.eqString
                                                                          matchValueShared12
                                                                          "--"
                                                                     then let {
                                                                            tail =
                                                                              matchValueShared13
                                                                          } in
                                                                          tail
                                                                     else arguments;
                                                                   _ -> arguments
                                                                 }
                                                             };
                                                             code <-
                                                               O.exec (M.packageRoot p)
                                                                 ((:)
                                                                    (B.executable b
                                                                       (dir ++ ("/bin/" ++ name)))
                                                                    forwarded)
                                                                 ""
                                                                 ""
                                                                 ""
                                                                 (readInt
                                                                    (J.getText "timeout" "1800"
                                                                       config));
                                                             exitWith code
                                                           };
                                                         [] -> O.fatal usage
                                                       }
                                                  else putStrLn
                                                         (action ++
                                                          (" passed; report: " ++
                                                           (dir ++ "/build-report.json")))
                                                }
                               };
              [] -> O.fatal usage
            }
          }
      }
    }
}
