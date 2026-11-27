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
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Compiler as C;
  import qualified MLF.PreparedCompiler as Prepared;
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
  data Source = SourceFile String | SourceText String String | SourceStdin;
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
    ["-Zincremental-verify-ich", file, "-o", prefix] -> compileCrateLLVMCommand True [file,"-o",prefix];
    [file,"-o",prefix,"-Zincremental-verify-ich"] -> compileCrateLLVMCommand True [file,"-o",prefix];
    [file,"-o",prefix] -> compileCrateLLVMUsing verifyAll file prefix Nothing;
    [file,"-o",prefix,"--codegen-cache",cache,"--query-report",report] ->
      compileCrateLLVMUsing verifyAll file prefix (Just ((,) cache report));
    _ -> fatal crateUsage
  };
  compileCrateLLVMUsing = compileCrateLLVMRetaining Nothing SourceMap.empty;
  compileCratePlanCommand plan arguments = let {
    compile file prefix report = do {
      loaded <- readFile plan;
      case cratePlanEntries loaded of {
        Left message -> fatal message;
        Right entries -> do {
          compiler <- CrateSession.compilerImageDigest;
          prelude <- CrateArtifact.newPlanPrelude;
          (,) retained inputs <- compilePlanDependencies (CrateSession.PlanInputs compiler SourceMap.empty prelude)
            SourceMap.empty entries;
          compileCrateLLVMRetaining (Just inputs) retained False file prefix report
        }
      }
    }
  } in case arguments of {
    [file, "-o", prefix] -> compile file prefix Nothing;
    [file, "-o", prefix, "--codegen-cache", cache, "--query-report", report] ->
      compile file prefix (Just ((,) cache report));
    _ -> fatal crateUsage
  };
  cratePlanEntries contents = do {
    fields <- Separate.unpack contents;
    case fields of {
      ["MLF-CRATE-PLAN-1", entries] -> do {
        rows <- Separate.unpack entries;
        L.traverseEither (\row -> do {
          fields <- Separate.unpack row;
          case fields of {
            [spec,prefix] -> if eqString spec "" || eqString prefix ""
              then Left "empty crate plan specification or output"
              else Right ((,) spec prefix);
            _ -> Left "invalid crate plan row"
          }
        }) rows
      };
      _ -> Left "invalid crate plan"
    }
  };
  compilePlanDependencies inputs@(CrateSession.PlanInputs compiler headers prelude) retained rows = case rows of {
    [] -> ioReturn ((,) retained inputs);
    (:) ((,) spec prefix) rest -> do {
      result <- CrateSession.compileSpecFileRetainedInPlan inputs
        False Prepared.installCompilerPrelude spec prefix;
      case result of {
        Left message -> fatal message;
        Right compiled -> do {
          path <- canonicalPath (prefix ++ ".mlfci");
          case CrateSession.compiledMetadata compiled of {
            Nothing -> fatal "crate plan publication lacks metadata";
            Just header -> compilePlanDependencies
              (CrateSession.PlanInputs compiler (SourceMap.insert compareString path header headers) prelude)
              (SourceMap.insert compareString path (CrateSession.compiledObject compiled) retained) rest
          }
        }
      }
    }
  };
  compileCrateLLVMRetaining planInputs retained verifyAll file prefix cacheReport = do {
    result <- case planInputs of {
      Nothing -> CrateSession.compileSpecFileRetainedUsingInstaller verifyAll Prepared.installCompilerPrelude file prefix;
      Just inputs -> CrateSession.compileSpecFileRetainedInPlan inputs verifyAll Prepared.installCompilerPrelude file prefix
    };
      case result of {
        Left message -> fatal message;
        Right compiled -> do {
          linked <- Prepared.linkCompiledCrateRetaining retained compiled;
          case linked of { Left message -> fatal message;
            Right checked -> case cacheReport of {
              Nothing -> printLLVM (LLVM.emitCheckedChunks False checked);
              Just ((,) cache report) -> case planInputs of {
                Nothing -> emitCachedCrate cache (Just report) checked;
                Just (CrateSession.PlanInputs compiler _ _) -> emitCachedCrateUsing
                  (CrateCodegen.emitCrateCheckedUsing (ioReturn compiler)) cache (Just report) checked
              }
            } }
        }
      }
  };
  runArgs :: PreludeMode -> [] String -> [] String -> IO ();
  runArgs mode paths arguments = case arguments of {
    ["--test-parity-batch", request] -> testParityBatch request;
    (:) "--compile-crate-plan" ((:) plan rest) -> compileCratePlanCommand plan rest;
    (:) "--compile-crate-to-llvm-gc" rest -> compileCrateLLVMCommand False rest;
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
  runOrdinaryArgs mode paths arguments =
    let {
      matchValueShared6 = arguments
    } in
    case matchValueShared6 of {
      (:) matchValueShared7 matchValueShared8 ->
        if MLF.Primitive.eqString matchValueShared7 "--implementation-identity"
        then case matchValueShared8 of {
               [] -> putStrLn ("MLF/shared-haskell-v1 " ++ producerHost);
               _ -> sourceCommand mode paths (PrintSource False) [] arguments
             }
        else if MLF.Primitive.eqString matchValueShared7 "--check-shared"
             then let {
                    files = matchValueShared8
                  } in
                  checkSharedFiles files
             else if MLF.Primitive.eqString matchValueShared7 "--version"
                  then case matchValueShared8 of {
                         [] -> putStrLn ("emlf " ++ Version.version);
                         _ -> sourceCommand mode paths (PrintSource False) [] arguments
                       }
                  else if MLF.Primitive.eqString matchValueShared7 "--help"
                       then case matchValueShared8 of {
                              [] -> putStr usage;
                              _ -> sourceCommand mode paths (PrintSource False) [] arguments
                            }
                       else if MLF.Primitive.eqString matchValueShared7 "--llvm-runtime"
                            then case matchValueShared8 of {
                                   [] ->
                                     do {
                                       path <- runtimePath;
                                       putStrLn path
                                     };
                                   _ -> sourceCommand mode paths (PrintSource False) [] arguments
                                 }
                            else if MLF.Primitive.eqString matchValueShared7 "--compile-crate"
                                 then compileCrateCommand False matchValueShared8
                                 else if MLF.Primitive.eqString matchValueShared7 "--show-crate"
                                      then case matchValueShared8 of {
                                             (:) matchValueShared31 matchValueShared32 ->
                                               case matchValueShared32 of {
                                                 [] ->
                                                   let {
                                                     file = matchValueShared31
                                                   } in
                                                   do {
                                                     result <- CrateArtifact.showInterfaceFile file;
                                                     case result of {
                                                       Left message -> fatal message;
                                                       Right text -> putStr text
                                                     }
                                                   };
                                                 _ ->
                                                   sourceCommand mode paths (PrintSource False) []
                                                     arguments
                                               };
                                             _ ->
                                               sourceCommand mode paths (PrintSource False) []
                                                 arguments
                                           }
                                      else if MLF.Primitive.eqString matchValueShared7
                                                "--crate-to-llvm"
                                           then case matchValueShared8 of {
                                                  (:) matchValueShared21 matchValueShared22 ->
                                                    case matchValueShared22 of {
                                                      [] ->
                                                        let {
                                                          file = matchValueShared21
                                                        } in
                                                        crateCommand EmitSource [] file;
                                                      (:) matchValueShared23 matchValueShared24 ->
                                                        if MLF.Primitive.eqString matchValueShared23
                                                             "--cache"
                                                        then case matchValueShared24 of {
                                                               (:) matchValueShared25 matchValueShared26 ->
                                                                 case matchValueShared26 of {
                                                                   [] ->
                                                                     let {
                                                                       file = matchValueShared21
                                                                     } in
                                                                     let {
                                                                       cache = matchValueShared25
                                                                     } in
                                                                     cachedCrateCommand cache file;
                                                                   (:) matchValueShared27 matchValueShared28 ->
                                                                     if MLF.Primitive.eqString
                                                                          matchValueShared27
                                                                          "--query-report"
                                                                     then case matchValueShared28 of {
                                                                            (:) matchValueShared29 matchValueShared30 ->
                                                                              case matchValueShared30 of {
                                                                                [] ->
                                                                                  let {
                                                                                    file =
                                                                                      matchValueShared21
                                                                                  } in
                                                                                  let {
                                                                                    cache =
                                                                                      matchValueShared25
                                                                                  } in
                                                                                  let {
                                                                                    report =
                                                                                      matchValueShared29
                                                                                  } in
                                                                                  cachedCrateReportCommand
                                                                                    cache
                                                                                    file
                                                                                    report;
                                                                                _ ->
                                                                                  sourceCommand mode
                                                                                    paths
                                                                                    (PrintSource
                                                                                       False)
                                                                                    []
                                                                                    arguments
                                                                              };
                                                                            _ ->
                                                                              sourceCommand mode
                                                                                paths
                                                                                (PrintSource False)
                                                                                []
                                                                                arguments
                                                                          }
                                                                     else sourceCommand mode paths
                                                                            (PrintSource False)
                                                                            []
                                                                            arguments;
                                                                   _ ->
                                                                     sourceCommand mode paths
                                                                       (PrintSource False)
                                                                       []
                                                                       arguments
                                                                 };
                                                               _ ->
                                                                 sourceCommand mode paths
                                                                   (PrintSource False)
                                                                   []
                                                                   arguments
                                                             }
                                                        else sourceCommand mode paths
                                                               (PrintSource False)
                                                               []
                                                               arguments;
                                                      _ ->
                                                        sourceCommand mode paths (PrintSource False)
                                                          []
                                                          arguments
                                                    };
                                                  _ ->
                                                    sourceCommand mode paths (PrintSource False) []
                                                      arguments
                                                }
                                           else if MLF.Primitive.eqString matchValueShared7
                                                     "--crate-to-llvm-gc"
                                                then case matchValueShared8 of {
                                                       (:) matchValueShared11 matchValueShared12 ->
                                                         case matchValueShared12 of {
                                                           [] ->
                                                             let {
                                                               file = matchValueShared11
                                                             } in
                                                             crateCommand EmitSource [] file;
                                                           (:) matchValueShared13 matchValueShared14 ->
                                                             if MLF.Primitive.eqString
                                                                  matchValueShared13
                                                                  "--cache"
                                                             then case matchValueShared14 of {
                                                                    (:) matchValueShared15 matchValueShared16 ->
                                                                      case matchValueShared16 of {
                                                                        [] ->
                                                                          let {
                                                                            file =
                                                                              matchValueShared11
                                                                          } in
                                                                          let {
                                                                            cache =
                                                                              matchValueShared15
                                                                          } in
                                                                          cachedCrateCommand cache
                                                                            file;
                                                                        (:) matchValueShared17 matchValueShared18 ->
                                                                          if MLF.Primitive.eqString
                                                                               matchValueShared17
                                                                               "--query-report"
                                                                          then case matchValueShared18 of {
                                                                                 (:) matchValueShared19 matchValueShared20 ->
                                                                                   case matchValueShared20 of {
                                                                                     [] ->
                                                                                       let {
                                                                                         file =
                                                                                           matchValueShared11
                                                                                       } in
                                                                                       let {
                                                                                         cache =
                                                                                           matchValueShared15
                                                                                       } in
                                                                                       let {
                                                                                         report =
                                                                                           matchValueShared19
                                                                                       } in
                                                                                       cachedCrateReportCommand
                                                                                         cache
                                                                                         file
                                                                                         report;
                                                                                     _ ->
                                                                                       sourceCommand
                                                                                         mode
                                                                                         paths
                                                                                         (PrintSource
                                                                                            False)
                                                                                         []
                                                                                         arguments
                                                                                   };
                                                                                 _ ->
                                                                                   sourceCommand
                                                                                     mode
                                                                                     paths
                                                                                     (PrintSource
                                                                                        False)
                                                                                     []
                                                                                     arguments
                                                                               }
                                                                          else sourceCommand mode
                                                                                 paths
                                                                                 (PrintSource False)
                                                                                 []
                                                                                 arguments;
                                                                        _ ->
                                                                          sourceCommand mode paths
                                                                            (PrintSource False)
                                                                            []
                                                                            arguments
                                                                      };
                                                                    _ ->
                                                                      sourceCommand mode paths
                                                                        (PrintSource False)
                                                                        []
                                                                        arguments
                                                                  }
                                                             else sourceCommand mode paths
                                                                    (PrintSource False)
                                                                    []
                                                                    arguments;
                                                           _ ->
                                                             sourceCommand mode paths
                                                               (PrintSource False)
                                                               []
                                                               arguments
                                                         };
                                                       _ ->
                                                         sourceCommand mode paths
                                                           (PrintSource False)
                                                           []
                                                           arguments
                                                     }
                                                else if MLF.Primitive.eqString matchValueShared7
                                                          "--link-crate"
                                                     then case matchValueShared8 of {
                                                            (:) matchValueShared9 matchValueShared10 ->
                                                              case matchValueShared10 of {
                                                                [] ->
                                                                  let {
                                                                    file = matchValueShared9
                                                                  } in
                                                                  crateCommand (PrintSource False)
                                                                    []
                                                                    file;
                                                                _ ->
                                                                  sourceCommand mode paths
                                                                    (PrintSource False)
                                                                    []
                                                                    arguments
                                                              };
                                                            _ ->
                                                              sourceCommand mode paths
                                                                (PrintSource False)
                                                                []
                                                                arguments
                                                          }
                                                     else if MLF.Primitive.eqString
                                                               matchValueShared7
                                                               "--run-crate"
                                                          then let {
                                                                 rest = matchValueShared8
                                                               } in
                                                               case splitArguments rest of {
                                                                 (,) ((:) file []) args ->
                                                                   crateCommand RunSource args file;
                                                                 _ -> fatal usage
                                                               }
                                                          else if MLF.Primitive.eqString
                                                                    matchValueShared7
                                                                    "--type"
                                                               then let {
                                                                      rest = matchValueShared8
                                                                    } in
                                                                    sourceCommand mode paths
                                                                      (PrintSource True)
                                                                      []
                                                                      rest
                                                               else if MLF.Primitive.eqString
                                                                         matchValueShared7
                                                                         "--emit-llvm"
                                                                    then let {
                                                                           rest = matchValueShared8
                                                                         } in
                                                                         sourceCommand mode paths
                                                                           EmitSource
                                                                           []
                                                                           rest
                                                                    else if MLF.Primitive.eqString
                                                                              matchValueShared7
                                                                              "--emit-llvm-gc"
                                                                         then let {
                                                                                rest =
                                                                                  matchValueShared8
                                                                              } in
                                                                              sourceCommand mode
                                                                                paths
                                                                                EmitSource
                                                                                []
                                                                                rest
                                                                         else if MLF.Primitive.eqString
                                                                                   matchValueShared7
                                                                                   "--check"
                                                                              then let {
                                                                                     rest =
                                                                                       matchValueShared8
                                                                                   } in
                                                                                   targetCommand
                                                                                     CheckTarget
                                                                                     []
                                                                                     rest
                                                                              else if MLF.Primitive.eqString
                                                                                        matchValueShared7
                                                                                        "--xmlf-to-llvm"
                                                                                   then let {
                                                                                          rest =
                                                                                            matchValueShared8
                                                                                        } in
                                                                                        targetCommand
                                                                                          EmitTarget
                                                                                          []
                                                                                          rest
                                                                                   else if MLF.Primitive.eqString
                                                                                             matchValueShared7
                                                                                             "--xmlf-to-llvm-gc"
                                                                                        then let {
                                                                                               rest =
                                                                                                 matchValueShared8
                                                                                             } in
                                                                                             targetCommand
                                                                                               EmitTarget
                                                                                               []
                                                                                               rest
                                                                                        else if MLF.Primitive.eqString
                                                                                                  matchValueShared7
                                                                                                  "--xmlf-to-llvm-io"
                                                                                             then let {
                                                                                                    rest =
                                                                                                      matchValueShared8
                                                                                                  } in
                                                                                                  targetCommand
                                                                                                    EmitIOTarget
                                                                                                    []
                                                                                                    rest
                                                                                             else if MLF.Primitive.eqString
                                                                                                       matchValueShared7
                                                                                                       "--xmlf-to-llvm-io-gc"
                                                                                                  then let {
                                                                                                         rest =
                                                                                                           matchValueShared8
                                                                                                       } in
                                                                                                       targetCommand
                                                                                                         EmitIOTarget
                                                                                                         []
                                                                                                         rest
                                                                                                  else if MLF.Primitive.eqString
                                                                                                            matchValueShared7
                                                                                                            "--run"
                                                                                                       then let {
                                                                                                              rest =
                                                                                                                matchValueShared8
                                                                                                            } in
                                                                                                            case splitArguments
                                                                                                                   rest of {
                                                                                                              (,) source arguments ->
                                                                                                                sourceCommand
                                                                                                                  mode
                                                                                                                  paths
                                                                                                                  RunSource
                                                                                                                  arguments
                                                                                                                  source
                                                                                                            }
                                                                                                       else if MLF.Primitive.eqString
                                                                                                                 matchValueShared7
                                                                                                                 "--run-xmlf"
                                                                                                            then let {
                                                                                                                   rest =
                                                                                                                     matchValueShared8
                                                                                                                 } in
                                                                                                                 case splitArguments
                                                                                                                        rest of {
                                                                                                                   (,) source arguments ->
                                                                                                                     targetCommand
                                                                                                                       RunTarget
                                                                                                                       arguments
                                                                                                                       source
                                                                                                                 }
                                                                                                            else if MLF.Primitive.eqString
                                                                                                                      matchValueShared7
                                                                                                                      "--run-program-xmlf"
                                                                                                                 then let {
                                                                                                                        rest =
                                                                                                                          matchValueShared8
                                                                                                                      } in
                                                                                                                      case splitArguments
                                                                                                                             rest of {
                                                                                                                        (,) source arguments ->
                                                                                                                          targetCommand
                                                                                                                            RunProgramTarget
                                                                                                                            arguments
                                                                                                                            source
                                                                                                                      }
                                                                                                                 else sourceCommand
                                                                                                                        mode
                                                                                                                        paths
                                                                                                                        (PrintSource
                                                                                                                           False)
                                                                                                                        []
                                                                                                                        arguments;
      _ -> sourceCommand mode paths (PrintSource False) [] arguments
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
  cachedCrateCommand cache file = cachedCrateUsing cache file Nothing;
  cachedCrateReportCommand cache file report = cachedCrateUsing cache file (Just report);
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
  splitArguments arguments =
    let {
      matchValueShared39 = arguments
    } in
    case matchValueShared39 of {
      [] -> (,) [] [];
      (:) matchValueShared40 matchValueShared41 ->
        if MLF.Primitive.eqString matchValueShared40 "--"
        then let {
               rest = matchValueShared41
             } in
             (,) [] rest
        else let {
               rest = matchValueShared41
             } in
             let {
               a = matchValueShared40
             } in
             case splitArguments rest of {
               (,) source program -> (,) ((:) a source) program
             }
    };
  parseSource :: Bool -> [] String -> Either String Source;
  parseSource expression arguments =
    let {
      matchValueShared42 = arguments
    } in
    case matchValueShared42 of {
      [] -> Right SourceStdin;
      (:) matchValueShared43 matchValueShared44 ->
        if MLF.Primitive.eqString matchValueShared43 "-"
        then case matchValueShared44 of {
               [] -> Right SourceStdin;
               _ -> Left usage
             }
        else if MLF.Primitive.eqString matchValueShared43 "--expr"
             then case matchValueShared44 of {
                    (:) matchValueShared45 matchValueShared46 ->
                      case matchValueShared46 of {
                        [] ->
                          let {
                            text = matchValueShared45
                          } in
                          if expression then Right (SourceText "<expression>" text) else Left usage;
                        _ -> Left usage
                      };
                    [] ->
                      let {
                        file = matchValueShared43
                      } in
                      if ((stringLength file >= 2) && eqString (stringSlice file 0 2) "--")
                      then Left usage
                      else Right (SourceFile file);
                    _ -> Left usage
                  }
             else case matchValueShared44 of {
                    [] ->
                      let {
                        file = matchValueShared43
                      } in
                      if ((stringLength file >= 2) && eqString (stringSlice file 0 2) "--")
                      then Left usage
                      else Right (SourceFile file);
                    _ -> Left usage
                  };
      _ -> Left usage
    };
  sourceCommand :: PreludeMode -> [] String -> Command -> [] String -> [] String -> IO ();
  sourceCommand mode paths command programArguments arguments =
    case parseSource True arguments of {
      Left message -> fatal message;
      Right source ->
        do {
          compiled <-
            case source of {
              SourceFile file -> Prepared.compileFileWithPrelude mode paths file;
              SourceText file input -> Prepared.compileSourceWithImports mode paths file input;
              SourceStdin ->
                do {
                  input <- getContents;
                  Prepared.compileSourceWithImports mode paths "<stdin>" input
                }
            };
          case compiled of {
            Left error -> fatal (C.prettyError error);
            Right result ->
              case command of {
                PrintSource onlyType ->
                  do {
                    putStrLn ((if onlyType then "" else "-- type: ") ++ Prepared.sourceType result);
                    if onlyType
                    then ioReturn ()
                    else putStrLn (Pretty.prettyTerm (Prepared.compiledTerm result))
                  };
                RunSource -> execute programArguments (Prepared.compiledTerm result);
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
      compiled <- Prepared.compileFileWithPrelude mode paths source;
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
      result <- case source of {
        SourceFile file -> Prepared.emitNativeFileChunks mode paths file;
        SourceText file input -> Prepared.emitNativeSourceChunks mode paths file input;
        SourceStdin -> do {
          input <- getContents;
          Prepared.emitNativeSourceChunks mode paths "<stdin>" input
        }
      };
      case result of {
        Left error -> fatal (C.prettyError error);
        Right chunks -> printLLVM (Right chunks)
      }
    }
  };
  load :: Source -> IO ((,) String String);
  load source =
    case source of {
      SourceFile file ->
        do {
          present <- fileExists file;
          if present
          then do {
                 input <- readFile file;
                 ioReturn ((,) file input)
               }
          else fatal ("file does not exist: " ++ file)
        };
      SourceText file input -> ioReturn ((,) file input);
      SourceStdin ->
        do {
          input <- getContents;
          ioReturn ((,) "<stdin>" input)
        }
    };
  targetCommand :: Command -> [] String -> [] String -> IO ();
  targetCommand command programArguments arguments =
    case parseSource False arguments of {
      Left message -> fatal message;
      Right source ->
        do {
          boundValueShared47 <- load source;
          case boundValueShared47 of {
            (,) file input ->
              do {
                case Parse.parseTerm file input of {
                  Left message -> fatal message;
                  Right term ->
                    case command of {
                      CheckTarget ->
                        case Check.checkClosed term of {
                          Left message -> fatal message;
                          Right ty -> putStrLn (Pretty.prettyType ty)
                        };
                      RunTarget -> execute programArguments term;
                      RunProgramTarget ->
                        do {
                          result <- Runtime.runProgramWithArguments programArguments term;
                          case result of {
                            Left message -> panic message;
                            Right ignored -> ioReturn ()
                          }
                        };
                      EmitTarget -> printLLVM (LLVM.emitLLVMChunks term);
                      EmitIOTarget -> printLLVM (LLVM.emitLLVMIOChunks term);
                      _ -> fatal "invalid target command"
                    }
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
  usage =
    ("emlf --version\n       emlf --implementation-identity\n       emlf --check-shared FILE... (grammar and name resolution only)\n" ++
     (crateUsage ++ (nativeUsage ++ baseUsage)));
  nativeUsage :: String;
  nativeUsage =
    "Executable compilation: emlf [--no-prelude] [-i DIR ...] SOURCE -o OUTPUT [--build-dir FRESH]\n       emlf --compile SOURCE -o OUTPUT\nStandard libraries and runtime are reused automatically; user code is freshly compiled with one Clang -O2 job.\nTarget-specific LLVM flags: emlf --native-target-flags TRIPLE\nInstalled native libraries: emlf --native-install-info\n       emlf [-i DIR ...] --emit-native-llvm [FILE | --expr SOURCE]\n       emlf --emit-native-library-llvm\n       emlf --native-library-metadata\nNative IR requires the authenticated link inputs from --native-install-info. Library emission and metadata commands are installation build steps.\n";
  crateUsage :: String;
  crateUsage =
    "Crate compilation: emlf [-Zincremental-verify-ich] --compile-crate SPEC -o PREFIX\n       emlf [-Zincremental-verify-ich] --compile-crate-to-llvm-gc SPEC -o PREFIX [ --codegen-cache DIR --query-report FILE ]\n       emlf --compile-crate-plan PLAN SPEC -o PREFIX [ --codegen-cache DIR --query-report FILE ]\n       emlf --show-crate FILE.mlfci\n       emlf --link-crate FILE.mlfci\n       emlf --run-crate FILE.mlfci [-- ARGS...]\n       emlf --crate-to-llvm[-gc] FILE.mlfci [--cache DIR [ --query-report FILE ]]\n";
  baseUsage :: String;
  baseUsage =
    "Usage: emlf [--no-prelude] [-i DIR ...] [--type] [FILE | --expr SOURCE]\n       emlf --check [XMLF_FILE]\n       emlf [--no-prelude] [-i DIR ...] --run [FILE | --expr SOURCE] [-- ARG ...]\n       emlf --run-xmlf [XMLF_FILE] [-- ARG ...]\n       emlf [--no-prelude] [-i DIR ...] --emit-llvm [FILE | --expr SOURCE]\n       emlf --xmlf-to-llvm [XMLF_FILE]\n       emlf [--no-prelude] [-i DIR ...] --emit-llvm-gc [FILE | --expr SOURCE]\n       emlf --xmlf-to-llvm[-io]-gc [XMLF_FILE]\n       emlf --llvm-runtime\nWith no FILE, read eMLF from standard input.\nImports load Foo.Bar from marked Foo/Bar.hs or legacy Foo/Bar.emlf beside the entry or in -i roots; ambiguous duplicates are rejected.\nThe standard prelude supplies Monad and Monad IO; --no-prelude disables it.\nAll LLVM commands emit the compact BDWGC ABI; -gc spellings are aliases.\nLink LLVM IR with clang, runtime/mlf_runtime.c, GMP and BDWGC.\n"
}
