-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Entry.Emlf where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Parser as SourceParser;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Map as SourceMap;
  import qualified Bootstrap.Version as Version;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Compiler as C;
  import qualified MLF.PreparedCompiler as Prepared;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Parser as Parse;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.Runtime as Runtime;
  import qualified Bootstrap.LLVM as LLVM;
  import qualified Bootstrap.Crate as Crate;
  import qualified Bootstrap.CrateArtifact as CrateArtifact;
  import qualified Bootstrap.CrateCodegen as CrateCodegen;
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
              Right () -> putStrLn "builtin Prelude verified"
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
  runArgs :: PreludeMode -> [] String -> [] String -> IO ();
  runArgs mode paths arguments =
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
                                 then case matchValueShared8 of {
                                        (:) matchValueShared33 matchValueShared34 ->
                                          case matchValueShared34 of {
                                            (:) matchValueShared35 matchValueShared36 ->
                                              if MLF.Primitive.eqString matchValueShared35 "-o"
                                              then case matchValueShared36 of {
                                                     (:) matchValueShared37 matchValueShared38 ->
                                                       case matchValueShared38 of {
                                                         [] ->
                                                           let {
                                                             file = matchValueShared33
                                                           } in
                                                           let {
                                                             prefix = matchValueShared37
                                                           } in
                                                           do {
                                                             result <-
                                                               Crate.compileSpecFile file prefix;
                                                             case result of {
                                                               Left message -> fatal message;
                                                               Right _ -> ioReturn ()
                                                             }
                                                           };
                                                         _ ->
                                                           sourceCommand mode paths
                                                             (PrintSource False)
                                                             []
                                                             arguments
                                                       };
                                                     _ ->
                                                       sourceCommand mode paths (PrintSource False)
                                                         []
                                                         arguments
                                                   }
                                              else sourceCommand mode paths (PrintSource False) []
                                                     arguments;
                                            _ ->
                                              sourceCommand mode paths (PrintSource False) []
                                                arguments
                                          };
                                        _ ->
                                          sourceCommand mode paths (PrintSource False) [] arguments
                                      }
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
  cachedCrateCommand cache file =
    do {
      chunks <- CrateCodegen.emitFile cache False file;
      printLLVM chunks
    };
  cachedCrateReportCommand cache file report =
    do {
      chunks <- CrateCodegen.emitFileReport cache False file report;
      printLLVM chunks
    };
  crateCommand command args file =
    do {
      result <- CrateArtifact.linkCheckedFile file;
      case result of {
        Left message -> fatal message;
        Right checked ->
          case command of {
            PrintSource _ -> putStrLn (Pretty.prettyTerm (Checked.term checked));
            RunSource -> execute args (Checked.term checked);
            EmitSource -> printLLVM (LLVM.emitCheckedChunks False checked);
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
     (crateUsage ++ baseUsage));
  crateUsage :: String;
  crateUsage =
    "Crate compilation: emlf --compile-crate SPEC -o PREFIX\n       emlf --show-crate FILE.mlfci\n       emlf --link-crate FILE.mlfci\n       emlf --run-crate FILE.mlfci [-- ARGS...]\n       emlf --crate-to-llvm[-gc] FILE.mlfci [--cache DIR [ --query-report FILE ]]\n";
  baseUsage :: String;
  baseUsage =
    "Usage: emlf [--no-prelude] [-i DIR ...] [--type] [FILE | --expr SOURCE]\n       emlf --check [XMLF_FILE]\n       emlf [--no-prelude] [-i DIR ...] --run [FILE | --expr SOURCE] [-- ARG ...]\n       emlf --run-xmlf [XMLF_FILE] [-- ARG ...]\n       emlf [--no-prelude] [-i DIR ...] --emit-llvm [FILE | --expr SOURCE]\n       emlf --xmlf-to-llvm [XMLF_FILE]\n       emlf [--no-prelude] [-i DIR ...] --emit-llvm-gc [FILE | --expr SOURCE]\n       emlf --xmlf-to-llvm[-io]-gc [XMLF_FILE]\n       emlf --llvm-runtime\nWith no FILE, read eMLF from standard input.\nImports load Foo.Bar from marked Foo/Bar.hs or legacy Foo/Bar.emlf beside the entry or in -i roots; ambiguous duplicates are rejected.\nThe standard prelude supplies Monad and Monad IO; --no-prelude disables it.\nAll LLVM commands emit the compact BDWGC ABI; -gc spellings are aliases.\nLink LLVM IR with clang, runtime/mlf_runtime.c, GMP and BDWGC.\n"
}
