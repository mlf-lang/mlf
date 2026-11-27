-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Entry.Emlf where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Host as Host;
  import qualified Bootstrap.Parser as SourceParser;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Map as SourceMap;
  import qualified Bootstrap.Version as Version;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Compiler as C;
  import qualified MLF.PreparedCompiler as Prepared;
  import qualified Package.DependencyMode as Mode;
  import qualified MLF.NativeBuild as NativeBuild;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Parser as Parse;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.Runtime as Runtime;
  import qualified Bootstrap.LLVM as LLVM;
  import qualified Bootstrap.Crate as Crate;
  import qualified Bootstrap.CrateSession as CrateSession;
  import qualified Bootstrap.CrateArtifact as CrateArtifact;
  import qualified Bootstrap.CrateCodegen as CrateCodegen;
  import qualified MLF.CrateNativeCommand as NativeCommand;
  import qualified Package.Json as J;
  import qualified Package.OS as O;
  data Command =
    PrintSource Bool |
    RunSource |
    EmitSource |
    CheckTarget |
    RunTarget |
    RunProgramTarget |
    EmitTarget |
    EmitIOTarget;
  fatal :: forall a. String -> IO a;
  fatal message = ioBind (putErr (message ++ "\n")) (\ignored -> exitWith 1);
  main =
    do {
      count <- getArgCount;
      arguments <- readArguments 0 count;
      case arguments of {
        (:) command ((:) identity []) ->
          if eqString command "--verify-builtin-prelude" then
            case Prepared.verifyBuiltin identity of {
              Left message -> fatal message;
              Right () -> do {
                images <- Prepared.verifyBuiltinImages;
                case images of { Left message -> fatal message; Right () -> putStrLn "builtin Prelude verified" }
              }
            }
          else options ImplicitPrelude [] arguments;
        _ -> options ImplicitPrelude [] arguments
      }
    };
  readArguments :: Int -> Int -> IO ([] String);
  readArguments i count =
    if (i >= count)
    then ioReturn []
    else do {
           argument <- getArg i;
           rest <- readArguments (i + 1) count;
           ioReturn ((:) argument rest)
         };
  options :: PreludeMode -> [] String -> [] String -> IO ();
  options mode paths arguments =
    let {
      matchValueShared1 = arguments
    } in
    case matchValueShared1 of {
      (:) matchValueShared2 matchValueShared3 ->
        if MLF.Primitive.eqString matchValueShared2 "--no-prelude"
        then let {
               rest = matchValueShared3
             } in
             options NoImplicitPrelude paths rest
        else if MLF.Primitive.eqString matchValueShared2 "-i"
             then case matchValueShared3 of {
                    (:) matchValueShared4 matchValueShared5 ->
                      let {
                        path = matchValueShared4
                      } in
                      let {
                        rest = matchValueShared5
                      } in
                      options mode (L.snoc paths path) rest;
                    [] -> fatal "-i requires a module search directory";
                    _ ->
                      let {
                        rest = matchValueShared3
                      } in
                      let {
                        first = matchValueShared2
                      } in
                      if ((stringLength first > 2) && eqString (stringSlice first 0 2) "-i")
                      then options mode
                             (L.snoc paths (stringSlice first 2 (stringLength first - 2)))
                             rest
                      else runArgs mode paths arguments
                  }
             else let {
                    rest = matchValueShared3
                  } in
                  let {
                    first = matchValueShared2
                  } in
                  if ((stringLength first > 2) && eqString (stringSlice first 0 2) "-i")
                  then options mode (L.snoc paths (stringSlice first 2 (stringLength first - 2)))
                         rest
                  else runArgs mode paths arguments;
      [] -> runArgs mode paths arguments
    };
  compileCrateCommand verifyAll arguments = case arguments of {
    ["-Zincremental-verify-ich", file, "-o", prefix] -> compileCrateCommand True [file, "-o", prefix];
    [file, "-o", prefix, "-Zincremental-verify-ich"] -> compileCrateCommand True [file, "-o", prefix];
    [file, "-o", prefix] -> do {
      result <- if verifyAll then CrateSession.compileSpecFileWithVerification True Prepared.cratePrelude file prefix
        else CrateSession.compileSpecFileUsingInstaller False Prepared.installCompilerPrelude file prefix;
      case result of { Left message -> fatal message; Right () -> ioReturn () }
    };
    _ -> fatal crateUsage
  };
  compileCrateLLVMCommand verifyAll arguments = case arguments of {
    ["-Zincremental-verify-ich", file, "-o", prefix] -> compileCrateLLVMCommand True [file, "-o", prefix];
    [file, "-o", prefix, "-Zincremental-verify-ich"] -> compileCrateLLVMCommand True [file, "-o", prefix];
    _ -> crateLLVMArguments (compileCrateLLVMInSession CrateSession.freshSession verifyAll) arguments
  };
  compileCratePlanCommand plan = crateLLVMArguments (\file prefix report -> do {
    result <- CrateSession.loadPlan Prepared.installCompilerPrelude plan;
    case result of {
      Left message -> fatal message;
      Right session -> compileCrateLLVMInSession session False file prefix report
    }
  });
  data CrateEmission = DirectLLVM | CachedLLVM String String | NativeLLVM NativeCommand.Plan String;
  crateLLVMArguments :: (String -> String -> CrateEmission -> IO ()) -> [] String -> IO ();
  crateLLVMArguments compile arguments = case arguments of {
    [file, "-o", prefix] -> compile file prefix DirectLLVM;
    [file, "-o", prefix, "--codegen-cache", cache, "--query-report", report] ->
      compile file prefix (CachedLLVM cache report);
    (:) file ((:) "-o" ((:) prefix options)) -> case NativeCommand.arguments options of {
      Just ((,) plan report) -> compile file prefix (NativeLLVM plan report);
      Nothing -> fatal crateUsage
    };
    _ -> fatal crateUsage
  };
  requireResult :: forall a. Either String a -> IO a;
  requireResult result = case result of {
    Left message -> fatal message;
    Right value -> ioReturn value
  };
  compileCrateLLVMInSession session verifyAll file prefix emission = do {
    compiled <- ioBind (CrateSession.compileInSession session verifyAll Prepared.installCompilerPrelude file prefix) requireResult;
    let { retained = CrateSession.sessionObjects session;
          link = ioBind (Prepared.linkCompiledCrateRetaining retained compiled) requireResult };
    case emission of {
      DirectLLVM -> do { checked <- link; printLLVM (LLVM.emitCheckedChunks False checked) };
      CachedLLVM cache report -> do {
        checked <- link;
        emitCachedCrateUsing
          (CrateCodegen.emitCrateCheckedUsing (ioReturn (CrateSession.compiledCompilerDigest compiled)))
          cache (Just report) checked
      };
      NativeLLVM plan report -> ioBind (NativeCommand.emitRetained plan report prefix retained
        (CrateSession.compiledInterfaces compiled) (CrateSession.compiledObject compiled)) printChunks
    }
  };
  runArgs :: PreludeMode -> [] String -> [] String -> IO ();
  runArgs mode paths arguments = case arguments of {
    ["--test-parity-batch", request] -> testParityBatch request;
    (:) "--compile-crate-plan" ((:) plan rest) -> compileCratePlanCommand plan rest;
    (:) "--compile-crate-to-llvm-gc" rest -> compileCrateLLVMCommand False rest;
    (:) "--crate-library-to-llvm" rest -> case rest of {
      [file, "--native-identity", identity, "--native-contract", contract] -> ioBind (NativeCommand.emitLibrary file identity contract) printChunks;
      _ -> fatal crateUsage
    };
    (:) "--crate-to-native-llvm" rest -> case rest of {
      (:) file options -> case NativeCommand.arguments options of {
        Just ((,) plan report) -> ioBind (NativeCommand.emitFile plan report file) printChunks;
        Nothing -> fatal crateUsage
      };
      _ -> fatal crateUsage
    };
    (:) "-Zincremental-verify-ich" ((:) "--compile-crate-to-llvm-gc" rest) -> compileCrateLLVMCommand True rest;
    (:) "-Zincremental-verify-ich" ((:) "--compile-crate" rest) -> compileCrateCommand True rest;
    (:) "--compile" rest -> NativeBuild.run mode paths rest;
    ["--native-target-flags", triple] -> putStrLn (J.render (J.stringArray (O.nativeTargetFlags triple)));
    ["--native-install-info"] -> do {
      result <- Prepared.nativeInstallInfo;
      case result of {
        Left message -> fatal message;
        Right info -> putStrLn info
      }
    };
    ["--emit-native-library-llvm"] -> printLLVM Prepared.emitNativeLibraryChunks;
    ["--native-library-metadata"] -> case Prepared.nativeLibraryMetadata of {
      Left message -> fatal message;
      Right info -> putStrLn info
    };
    (:) "--emit-native-llvm" rest -> nativeSourceCommand mode paths rest;
    _ -> if executableBuildArguments arguments then NativeBuild.run mode paths arguments
      else runOrdinaryArgs mode paths arguments
  };
  executableBuildArguments :: [] String -> Bool;
  executableBuildArguments arguments = L.elem eqString "-o" arguments && case arguments of {
    [] -> False;
    (:) first _ -> eqString first "-o" || eqString first "--build-dir" ||
      (stringLength first > 0 && stringCodeAt first 0 /= 45)
  };
  runOrdinaryArgs :: PreludeMode -> [] String -> [] String -> IO ();
  runOrdinaryArgs mode paths arguments = let {
    source = sourceCommand mode paths;
    runWith action rest = case splitArguments rest of {
      (,) input args -> action args input
    };
    emitCrate rest = case rest of {
      [file] -> crateCommand EmitSource [] file;
      [file, "--cache", cache] -> cachedCrateUsing cache file Nothing;
      [file, "--cache", cache, "--query-report", report] -> cachedCrateUsing cache file (Just report);
      _ -> fatal usage
    }
  } in case arguments of {
    ["--help"] -> putStr usage;
    ["--help", "tools"] -> putStr toolsUsage;
    ["--version"] -> putStrLn ("emlf " ++ Version.version);
    ["--implementation-identity"] -> putStrLn ("MLF/shared-haskell-v1 " ++ producerHost);
    ["--llvm-runtime"] -> do { path <- runtimePath; putStrLn path };
    (:) "--check-shared" files -> checkSharedFiles files;
    (:) "--type" rest -> source (PrintSource True) [] rest;
    (:) "--run" rest -> runWith (source RunSource) rest;
    (:) "--emit-llvm" rest -> source EmitSource [] rest;
    (:) "--emit-llvm-gc" rest -> source EmitSource [] rest;
    (:) "--check" rest -> targetCommand CheckTarget [] rest;
    (:) "--run-xmlf" rest -> runWith (targetCommand RunTarget) rest;
    (:) "--run-program-xmlf" rest -> runWith (targetCommand RunProgramTarget) rest;
    (:) "--xmlf-to-llvm" rest -> targetCommand EmitTarget [] rest;
    (:) "--xmlf-to-llvm-gc" rest -> targetCommand EmitTarget [] rest;
    (:) "--xmlf-to-llvm-io" rest -> targetCommand EmitIOTarget [] rest;
    (:) "--xmlf-to-llvm-io-gc" rest -> targetCommand EmitIOTarget [] rest;
    (:) "--compile-crate" rest -> compileCrateCommand False rest;
    ["--show-crate", file] -> do {
      result <- CrateArtifact.showInterfaceFile file;
      case result of { Left message -> fatal message; Right text -> putStr text }
    };
    ["--link-crate", file] -> crateCommand (PrintSource False) [] file;
    (:) "--run-crate" rest -> case splitArguments rest of {
      (,) [file] args -> crateCommand RunSource args file;
      _ -> fatal usage
    };
    (:) "--crate-to-llvm" rest -> emitCrate rest;
    (:) "--crate-to-llvm-gc" rest -> emitCrate rest;
    _ -> source (PrintSource False) [] arguments
  };
  -- The frozen legacy seed bridge uses this native identity. The final shared
  -- source reads the host-specific constant from the stable primitive facade.
  producerHost :: String;
  producerHost = implementationHost;
  checkSharedFiles :: [] String -> IO ();
  checkSharedFiles files =
    do {
      if L.null files
      then fatal "--check-shared requires a complete module source list"
      else ioReturn ();
      sources <-
        L.mapM
          (\file ->
             do {
               text <- readFile file;
               case SourceParser.parseModuleWithProfile SharedHaskellV1 file text of {
                 Left message -> fatal message;
                 Right source -> ioReturn source
               }
             })
          files;
      case Modules.resolveCrateWithAllocator ImplicitPrelude SourceMap.empty Modules.freshNames
             sources of {
        Left message -> fatal message;
        Right _ ->
          putStrLn ("PASS shared syntax/name resolution: " ++ (showInt (L.length sources) ++ " modules"))
      }
    };
  -- All CLI crate routes use the same admitted Prelude and closed-program
  -- linking path, so retained and disk roots share exact codegen cache keys.
  cachedCrateUsing cache file report = do {
    linked <- Prepared.linkCrateFile file;
    case linked of {
      Left message -> fatal message;
      Right checked -> emitCachedCrate cache report checked
    }
  };
  emitCachedCrate = emitCachedCrateUsing CrateCodegen.emitCrateChecked;
  emitCachedCrateUsing generate cache report checked = do {
    generated <- generate cache False checked;
    case generated of {
      Left message -> fatal message;
      Right value -> case report of {
        Nothing -> printLLVM (Right (CrateCodegen.codeChunks value));
        Just path -> do {
          saved <- CrateCodegen.saveReport path value;
          printLLVM (L.mapEither CrateCodegen.codeChunks saved)
        }
      }
    }
  };
  -- This diagnostic file is separate from LLVM and all cache identities.
  crateCommand command args file = do {
    profilePath <- getEnv "MLF_CRATE_PROFILE";
    profile <- if eqString profilePath "" then ioReturn Nothing else Host.newPhaseProfile
      ["read_ms","decode_ms","validate_ms","prelude_check_ms","link_ms",
       "final_check_ms","optimize_ms","emit_ms","other_ms",
       "wire_decode_ms","syntax_decode_ms","image_decode_ms","metadata_hash_ms",
       "reference_validate_ms","fragment_validate_ms"];
    result <- Host.phaseIO profile "other_ms" (Prepared.linkCrateFileProfiled profile file);
    case result of {
      Left message -> do { Host.writePhaseProfile profilePath profile; fatal message };
      Right checked -> case command of {
        PrintSource _ -> do {
          putStrLn (Pretty.prettyTerm (Checked.term checked));
          Host.writePhaseProfile profilePath profile
        };
        RunSource -> do { Host.writePhaseProfile profilePath profile; execute args (Checked.term checked) };
        EmitSource -> do {
          prepared <- LLVM.prepareCheckedProfiled profile False checked;
          case prepared of {
            Left message -> do { Host.writePhaseProfile profilePath profile; fatal message };
            Right entry -> do {
              Host.phaseIO profile "emit_ms" (printLLVM (LLVM.emitPreparedChunks entry));
              Host.writePhaseProfile profilePath profile
            }
          }
        };
        _ -> fatal "invalid crate command"
      }
    }
  };
  splitArguments :: [] String -> (,) ([] String) ([] String);
  splitArguments arguments = case arguments of {
    [] -> (,) [] [];
    (:) "--" rest -> (,) [] rest;
    (:) arg rest -> case splitArguments rest of {
      (,) input program -> (,) ((:) arg input) program
    }
  };
  parseSource :: Bool -> [] String -> Either String Prepared.Source;
  parseSource allowExpression arguments = case arguments of {
    [] -> Right Prepared.SourceStdin;
    ["-"] -> Right Prepared.SourceStdin;
    ["--expr", text] -> if allowExpression then Right (Prepared.SourceText "<expression>" text) else Left usage;
    [file] -> if O.starts "--" file then Left usage else Right (Prepared.SourceFile file);
    _ -> Left usage
  };
  sourceCommand :: PreludeMode -> [] String -> Command -> [] String -> [] String -> IO ();
  sourceCommand mode paths command args arguments = case parseSource True arguments of {
    Left message -> fatal message;
    Right source -> do {
      compiled <- Prepared.compileSourceWithDecisions Mode.emit mode paths source;
      case compiled of {
        Left error -> fatal (C.prettyError error);
        Right result -> case command of {
          PrintSource True -> putStrLn (Prepared.sourceType result);
          PrintSource False -> do {
            putStrLn ("-- type: " ++ Prepared.sourceType result);
            putStrLn (Pretty.prettyTerm (Prepared.compiledTerm result))
          };
          RunSource -> execute args (Prepared.compiledTerm result);
          EmitSource -> printLLVM (LLVM.emitCheckedChunks False (Prepared.checkedTerm result));
          _ -> fatal "invalid source command"
        }
      }
    }
  };
  -- Use the normal file compiler, printer and target checker with each row's
  -- own import paths. Runtime effects still exercise the actual CLI children.
  testParityBatch :: String -> IO ();
  testParityBatch request =
    do {
      manifest <- J.read request;
      L.mapM_ testParityRow (J.values manifest)
    };
  testParityRow :: J.Json -> IO ();
  testParityRow row =
    do {
      let {
        source = J.getText "source" "" row;
        stem = J.getText "stem" "" row;
        mode = if J.getBool "no_prelude" False row then NoImplicitPrelude else ImplicitPrelude;
        paths = J.getStrings "include_dirs" row
      };
      compiled <- Prepared.compileSource mode paths (Prepared.SourceFile source);
      let {
        result = case compiled of {
          Left error -> (,,,) 1 (C.prettyError error ++ "\n") "" (Right "");
          Right value ->
            let {
              target = "-- type: " ++ Prepared.sourceType value ++ "\n" ++
                Pretty.prettyTerm (Prepared.compiledTerm value) ++ "\n";
              checked = case Parse.parseTerm (stem ++ ".xmlf") target of {
                Left error -> Left error;
                Right term -> case Check.checkClosed term of {
                  Left error -> Left error;
                  Right ty -> Right (Pretty.prettyType ty ++ "\n")
                }
              }
            } in (,,,) 0 "" target checked
        }
      };
      case result of {
        (,,,) status diagnostic target checked -> do {
          writeFile (stem ++ ".xmlf") target;
          writeFile (stem ++ ".stderr") diagnostic;
          case checked of {
            Left error -> do { writeFile (stem ++ ".self.err") (error ++ "\n"); writeFile (stem ++ ".self.out") "" };
            Right ty -> do { writeFile (stem ++ ".self.err") ""; writeFile (stem ++ ".self.out") ty }
          };
          putStrLn (J.render (J.set "id" (J.get "id" row)
            (J.set "compile_exit" (J.num status)
              (J.set "candidate_check_exit"
                (J.num (case checked of { Left _ -> 1; Right _ -> 0 })) J.empty))))
        }
      }
    };
  -- Native emission retains the normal source parser and diagnostics. The
  -- prepared adapter authenticates its fixed installation before producing
  -- IR whose explicit link inputs are returned by --native-install-info.
  nativeSourceCommand :: PreludeMode -> [] String -> [] String -> IO ();
  nativeSourceCommand mode paths arguments = case parseSource True arguments of {
    Left message -> fatal message;
    Right source -> do {
      result <- Prepared.compileNativeWithDecisions Mode.emit mode paths source;
      case result of {
        Left error -> fatal (C.prettyError error);
        Right native -> printChunks (Prepared.nativeChunks native)
      }
    }
  };
  targetCommand :: Command -> [] String -> [] String -> IO ();
  targetCommand command args arguments = case parseSource False arguments of {
    Left message -> fatal message;
    Right source -> do {
      loaded <- Prepared.readSource source;
      case loaded of {
        Left message -> fatal message;
        Right ((,) file input) -> case Parse.parseTerm file input of {
          Left message -> fatal message;
          Right term -> case command of {
            CheckTarget -> case Check.checkClosed term of {
              Left message -> fatal message;
              Right ty -> putStrLn (Pretty.prettyType ty)
            };
            RunTarget -> execute args term;
            RunProgramTarget -> do {
              result <- Runtime.runProgramWithArguments args term;
              case result of { Left message -> panic message; Right _ -> ioReturn () }
            };
            EmitTarget -> printLLVM (LLVM.emitLLVMChunks term);
            EmitIOTarget -> printLLVM (LLVM.emitLLVMIOChunks term);
            _ -> fatal "invalid target command"
          }
        }
      }
    }
  };
  execute :: [] String -> XTerm -> IO ();
  execute args term =
    do {
      result <- Runtime.runTermWithArguments args term;
      case result of {
        Left message -> panic message;
        Right ignored -> ioReturn ()
      }
    };
  printLLVM :: Either String ([] String) -> IO ();
  printLLVM result =
    case result of {
      Left message -> fatal message;
      Right chunks -> printChunks chunks
    };
  printChunks :: [] String -> IO ();
  printChunks chunks =
    case chunks of {
      [] -> ioReturn ();
      (:) chunk rest ->
        do {
          putStr chunk;
          printChunks rest
        }
    };
  runtimePath :: IO String;
  runtimePath =
    do {
      executable <- getExecutablePath;
      cwd <- canonicalPath ".";
      chooseRuntime (L.append (ancestors (directory executable)) (ancestors cwd))
    };
  directory :: String -> String;
  directory path =
    let {
      i = lastSlash path (stringLength path - 1)
    } in
    if (i < 0) then "." else if (i == 0) then "/" else stringSlice path 0 i;
  lastSlash :: String -> Int -> Int;
  lastSlash path i =
    if (i < 0)
    then i
    else if ((stringCodeAt path i == 47) || (stringCodeAt path i == 92))
         then i
         else lastSlash path (i - 1);
  ancestors :: String -> [] String;
  ancestors path =
    (:) path (if eqString (directory path) path then [] else ancestors (directory path));
  chooseRuntime :: [] String -> IO String;
  chooseRuntime paths =
    case paths of {
      [] -> fatal "Cannot find runtime/mlf_runtime.c beside the compiler or current directory.";
      (:) path rest ->
        do {
          c <- fileExists (path ++ "/runtime/mlf_runtime.c");
          h <- fileExists (path ++ "/runtime/mlf_runtime.h");
          if (c && h) then canonicalPath (path ++ "/runtime/mlf_runtime.c") else chooseRuntime rest
        }
    };
  usage :: String;
  usage =
    "Usage: emlf [--no-prelude] [-i DIR ...] FILE -o OUTPUT [--build-dir FRESH]\n" ++
    "       emlf [--no-prelude] [-i DIR ...] [ACTION] [INPUT]\n\n" ++
    "Compile a file to an executable with -o. Build a package or workspace with mlfpkg build.\n" ++
    "For the actions below, INPUT is a file, --expr SOURCE, or - for standard input.\n" ++
    "Omit INPUT to read standard input. Use -i to add a module search directory and --no-prelude to disable the implicit Prelude.\n\n" ++
    "  emlf [INPUT]                     Write checked xMLF with its inferred source type.\n" ++
    "  emlf --type [INPUT]              Check the source and print its inferred type.\n" ++
    "  emlf --run [INPUT] [-- ARG ...]  Run an IO program and pass it arguments.\n" ++
    "  emlf --emit-llvm [INPUT]         Write LLVM IR.\n\n" ++
    "With xMLF input\n" ++
    "  emlf --check [XMLF_FILE]                   Print the checked target type.\n" ++
    "  emlf --run-xmlf [XMLF_FILE] [-- ARG ...]   Run an IO program.\n" ++
    "  emlf --xmlf-to-llvm [XMLF_FILE]            Write LLVM IR.\n\n" ++
    "Use emlf --version for the compiler version or emlf --help tools for stage and package commands.\n\n" ++
    -- Released package managers and benchmark tools probe these exact words.
    "Tool capabilities: --implementation-identity --compile-crate-to-llvm-gc --compile-crate-plan --codegen-cache --query-report --native-target-flags --crate-library-to-llvm --crate-to-native-llvm --native-plan-sha256\n";
  toolsUsage :: String;
  toolsUsage =
    "Source and xMLF stages\n" ++
    "  emlf --check-shared FILE...                 Check shared grammar and name resolution.\n" ++
    "  emlf --run-program-xmlf [XMLF_FILE] [-- ARG ...]\n" ++
    "  emlf --xmlf-to-llvm-io [XMLF_FILE]          Require an IO entry point.\n" ++
    "  emlf --llvm-runtime                        Print the path to the C runtime.\n" ++
    "The --emit-llvm and --xmlf-to-llvm commands, including --xmlf-to-llvm-io, accept a -gc suffix.\n" ++
    "Link their LLVM output with the C runtime, GMP and BDWGC.\n\n" ++
    crateUsage ++ "\nInstalled native libraries\n" ++
    "  emlf --native-install-info\n" ++
    "  emlf [-i DIR ...] --emit-native-llvm [FILE | --expr SOURCE]\n" ++
    "  emlf --emit-native-library-llvm\n" ++
    "  emlf --native-library-metadata\n" ++
    "  emlf --native-target-flags TRIPLE\n" ++
    "Use the link inputs from --native-install-info with --emit-native-llvm.\n\n" ++
    "Executable compilation also accepts emlf --compile FILE -o OUTPUT.\n" ++
    "Compiler identity\n  emlf --implementation-identity\n";
  crateUsage :: String;
  crateUsage =
    "Crate compilation\n" ++
    "  emlf [-Zincremental-verify-ich] --compile-crate SPEC -o PREFIX\n" ++
    "  emlf [-Zincremental-verify-ich] --compile-crate-to-llvm-gc SPEC -o PREFIX [--codegen-cache DIR --query-report FILE]\n" ++
    "  emlf --compile-crate-plan PLAN SPEC -o PREFIX [--codegen-cache DIR --query-report FILE]\n" ++
    "  emlf --crate-library-to-llvm FILE.mlfci --native-identity SHA256 --native-contract FILE\n" ++
    "  emlf --crate-to-native-llvm FILE.mlfci --native-dependencies PLAN --native-plan-sha256 SHA256 --native-target TARGET.json --native-report FILE\n" ++
    "  The retained crate commands accept the same native plan options.\n" ++
    "  emlf --show-crate FILE.mlfci\n" ++
    "  emlf --link-crate FILE.mlfci\n" ++
    "  emlf --run-crate FILE.mlfci [-- ARG ...]\n" ++
    "  emlf --crate-to-llvm[-gc] FILE.mlfci [--cache DIR [--query-report FILE]]\n"
}
