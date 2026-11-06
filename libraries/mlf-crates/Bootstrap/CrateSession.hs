-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- File-owned candidate route. No raw AST, Solver, region, or callback escapes.
module Bootstrap.CrateSession (compileSpecFile, compileSpecFileWithPrelude, compileSpecFileWithVerification, compileSpecFileUsingInstaller, compileDiscoveredRoot, compileDiscoveredRootMatching, OrderedPlanReceipt(..)) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.ST as ST;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Resolved as R;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.IntRank as Rank;
  import qualified Bootstrap.BuiltinPreludeContext as Builtin;
  import Bootstrap.Crate (CrateSpec, PreparedCrate, withPreludeUsing, ensureBuiltinWith, prepareCrate, prepareDiscoveredCrate, parseDiscoveredSource,
    withDependencies, loadSourcesInPackage, decodeSpec, specIdentity, specSources,
    specDependencies, specCache, specMode, preparedLowered, preparedSourcePlan,
    preparedResolution, preparedNames, preparedLayouts, preparedReach, CrateEntry(..), preparedEntryId,
    preparedData, preparedClasses, preparedInstances, preparedEntry);
  import qualified Bootstrap.CrateQuery as Query;
  import qualified Bootstrap.CrateGraph as CrateGraph;
  import qualified Bootstrap.QueryGraph as QueryGraph;
  import qualified Bootstrap.OpenFragment as Open;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.InferenceUnit as Inference;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.SourceInference as Source;
  import qualified Bootstrap.SourceUnit as Unit;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Host as Host;
  import qualified Bootstrap.CompilerCore as Compiler;
  import qualified Bootstrap.Constraint as C;
  import qualified Bootstrap.Elaborate as E;
  import qualified Bootstrap.Graph as G;
  import qualified Bootstrap.Graph.Solver as S;
  import qualified Bootstrap.Graph.IndexStore as K;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Pretty as Pretty;

  data OrderedPlanReceipt = OrderedPlanReceipt
    ([] ((,,) Int String ([] ((,) EvidenceRole String)))) ([] ([] ((,,) Int String Bool)));
  orderedPlanReceipt :: PreparedCrate -> Either String OrderedPlanReceipt;
  orderedPlanReceipt prepared = case preparedSourcePlan prepared of {
    Just plan -> case Source.planGraph plan of {
      Source.IndexedPlan symbols _ locals _ groups -> case Classes.inventoryDeclarations (Source.planInventory plan) of {
        Nothing -> Left "ordered plan lost allocated evidence authority";
        Just generation -> let {
          inventory = Source.planInventory plan; evidence = Dependency.generatedSymbols generation;
          row i = (,,) (V.toInt i) (Dependency.symbolKey symbols i)
            (map (\((,) role slot) -> (,) role (Dependency.symbolKey evidence slot)) (Classes.inventoryCandidateIds inventory i));
          member ((,) i recursive) = (,,) (V.toInt i) (Dependency.symbolKey symbols i) recursive
        } in Right (OrderedPlanReceipt (map row locals) (map (map member) groups))
      };
      _ -> Left "ordered file route did not produce indexed SCCs"
    };
    Nothing -> Left "ordered file route cannot enter fallback"
  };
  compileSourcesUsingInstaller verifyAll install shareEncoding spec sources interfaces prefix =
    do {
      dependencies <- withPreludeUsing install spec sources interfaces;
      case dependencies of {
        Left message -> ioReturn (Left message);
        Right ((,) updated loaded) ->
          compileLoadedSourcesWith prepareCrate (\_ -> Right ()) verifyAll updated sources loaded prefix
      }
    };
  compileLoadedSourcesWith prepare receipt verifyAll spec sources interfaces prefix =
    case do {
      prepared <- prepare spec interfaces sources;
      report <- receipt prepared;
      Right ((,) prepared report)
    } of {
      Left message -> ioReturn (Left message);
      Right ((,) prepared report) -> do {
        result <- compileGraphSources verifyAll spec interfaces prepared (preparedSourcePlan prepared) prefix;
        case result of {
          Left message ->
            let { names = Modules.resolvedCrateDisplayNames (preparedResolution prepared);
                  diagnostics = M.union compareString (M.map (Modules.displayNames names)
                    (preparedNames prepared)) names }
            in ioReturn (Left (Modules.displayNames diagnostics message));
          Right _ -> ioReturn (Right report)
        }
      }
    };

  compileGraphSources verify spec interfaces prepared plan prefix = do {
    let { directory = Query.cachePath (specCache spec) };
    created <- Query.cacheCommand ["/bin/mkdir","-p",directory];
    if created /= 0 then ioReturn (Left "cannot create query graph cache directory") else do {
      lock <- acquireFileLock (directory ++ "/.lock");
      result <- catchIOError (compileGraphLocked verify spec interfaces prepared plan prefix directory)
        (\error -> ioReturn (Left (textFromChars (ioeGetErrorString error))));
      releaseFileLock lock;
      ioReturn result
    }
  };
  compileGraphLocked verify spec interfaces prepared plan prefix directory = do {
    executable <- getExecutablePath;
    compiler <- fileDigest executable;
    let { imported = map (\((,) _ iface) -> Separate.UnitInterface (Artifact.crateId iface)
          [] [] [] [] [] (Artifact.crateBindings iface) "metadata") interfaces;
      protected = M.fromList compareString (concatMap (compose Artifact.crateProtection snd) interfaces) };
    compiled <- if Query.validSourceContextDigest compiler
      then case plan of {
        Just source -> CrateGraph.compile verify (specIdentity spec) compiler directory imported protected source;
        Nothing -> CrateGraph.compileLoweredIn (preparedLowered prepared) verify (specIdentity spec) compiler directory imported
      }
      else ioReturn (Left "cannot fingerprint query graph compiler");
    case compiled of { Left e -> ioReturn (Left e); Right state -> case CrateGraph.checkedResult state of {
      (,,,) fragments report contracts session -> case graphInterface spec interfaces prepared fragments contracts of {
        Left e -> ioReturn (Left e);
        Right iface -> do {
          outputStarted <- QueryGraph.clock (CrateGraph.statistics state);
          made <- Artifact.makeOpenObject iface (map snd interfaces) (map (\((,,) n f _) -> (,) n f) fragments);
          case made of { Left e -> ioReturn (Left e); Right object -> do {
            written <- Artifact.writeObjectEither prefix object;
            case written of { Left e -> ioReturn (Left e); Right _ -> do {
              writeFile (prefix ++ ".queries") (Query.reportJSON (specIdentity spec)
                (Artifact.semanticFingerprint (Artifact.objectInterface object)) report);
              QueryGraph.elapsed (CrateGraph.statistics state) 4 outputStarted;
              publishStarted <- QueryGraph.clock (CrateGraph.statistics state);
              published <- QueryGraph.publish session;
              QueryGraph.elapsed (CrateGraph.statistics state) 5 publishStarted;
              QueryGraph.writeProfile (prefix ++ ".query-profile") (CrateGraph.statistics state);
              ioReturn (mapEither (\_ -> ()) published)
            } }
          } }
        }
      }
    } }
  };
  graphInterface spec interfaces prepared fragments contracts = do {
    let { resolved = Modules.resolvedCrateModules (preparedResolution prepared);
      modules = map (compose Modules.moduleIdentity Modules.resolvedSource) resolved;
      dependencies = map (\path -> case find (\p -> eqString (fst p) path) interfaces of {
        Nothing -> panic "missing direct crate metadata";
        Just ((,) _ iface) -> (,,) (Artifact.crateId iface) path (Artifact.semanticFingerprint iface)
      }) (specDependencies spec);
      external = Set.fromList compareString (concatMap (\((,) _ iface) ->
        map D.datatypeName (Artifact.crateLoweredData iface)) interfaces);
      layouts = filter (\d -> not (Set.member compareString (D.datatypeName d) external)) (preparedLayouts prepared);
      reach = map (\name -> (,) name (Set.toList
        (M.findWithDefault compareString Set.empty name (preparedReach prepared)))) modules;
      symbols = Source.contractSymbols contracts; scope = Source.checkedScope contracts;
      owners = IS.fromList (concatMap (\((,,) _ _ ids) -> map V.toInt ids) fragments);
      methods = IS.fromList (concatMap (\r -> concatMap (\(R.Class _ _ _ items) ->
        map (compose V.toInt fst) items) (Modules.resolvedClasses (Modules.resolvedContents r))) resolved);
      termTable = Modules.resolvedCrateBindings (preparedResolution prepared);
      validateOwned entity ids = do {
        i <- Modules.termId termTable entity;
        ensure (IS.member (V.toInt i) ids) ("crate exports an undeclared entity: " ++ Modules.label entity)
      };
      validateExport entity = if Artifact.isPrimitiveEntity entity || not (elem eqString (Modules.owner entity) modules)
        then Right () else case Modules.role entity of {
          Modules.Value -> validateOwned entity owners; Modules.Method _ -> validateOwned entity methods; _ -> Right ()
        };
      project ((,) i ((,) name ty)) = do {
        checked <- Source.checkedBinding contracts i;
        ensure (eqString (Source.declName scope i) (X.nameHint name) && T.alphaEq ty (Source.contractType checked))
          "open final binding differs from its checked declaration";
        let { key = Dependency.symbolKey symbols i };
        Right ((,) ((,) key (Separate.normalType ty)) ((,) key (Source.contractProtected checked)))
      } };
    rows <- traverseEither (\((,,) _ fragment ids) -> do {
      let { bound = Open.bindings fragment };
      ensure (length ids == length bound) "open final binding ownership mismatch";
      traverseEither project (zip ids bound)
    }) fragments;
    let { output = concat rows };
    exports <- traverseEither (\r -> mapEither (\visible ->
      (,) (Modules.moduleIdentity (Modules.resolvedSource r)) (Set.toList (Modules.visible visible)))
      (Modules.resolvedExports (specMode spec) r)) resolved;
    mapM_ validateExport (concatMap snd exports);
    entry <- case preparedEntryId prepared of {
      NoEntry -> Right "";
      CrateEntry allocated i -> do {
        ensure (IS.member (V.toInt i) owners && eqString (Dependency.symbolKey allocated i) (Dependency.symbolKey symbols i))
          "open final crate entry lacks its checked owner";
        Right (Dependency.symbolKey symbols i)
      }
    };
    let { iface = Artifact.CrateInterface (specIdentity spec) dependencies modules exports reach
      (preparedData prepared) (preparedClasses prepared) (preparedInstances prepared)
      layouts (map fst output) entry "pending" (map snd output) };
    Artifact.validateInterface iface;
    Right iface
  };

  compileSpecFile :: String -> String -> IO (Either String ());
  compileSpecFile = compileSpecFileWithPrelude Nothing;
  compileSpecFileWithPrelude :: Maybe ((,) Builtin.PreparedPrelude String) -> String -> String -> IO (Either String ());
  compileSpecFileWithPrelude = compileSpecFileWithVerification False;
  compileSpecFileWithVerification :: Bool -> Maybe ((,) Builtin.PreparedPrelude String) -> String -> String -> IO (Either String ());
  compileSpecFileWithVerification verifyAll witness = compileSpecFileUsingInstaller verifyAll (ensureBuiltinWith witness);
  compileSpecFileUsingInstaller verifyAll install file prefix =
    do {
      present <- fileExists file;
      if not present
      then ioReturn (Left ("crate specification does not exist: " ++ file))
      else do {
             text <- readFile file;
             case decodeSpec text of {
               Left message -> ioReturn (Left message);
               Right spec ->
                 do {
                   sourceResult <- loadSourcesInPackage (specIdentity spec) (specSources spec);
                   paths <- mapM canonicalPath (specDependencies spec);
                   let {
                     normalized = withDependencies spec paths
                   };
                   dependencies <- Artifact.loadInterfaces paths;
                   case do {
                          sources <- sourceResult;
                          interfaces <- dependencies;
                          Right ((,) sources interfaces)
                        } of {
                     Left message -> ioReturn (Left message);
                     Right ((,) sources interfaces) ->
                       -- Both source and dependency values originate in the
                       -- parsers/decoders above, not caller-supplied lazy ASTs.
                       compileSourcesUsingInstaller verifyAll install True normalized sources interfaces prefix
                   }
                 }
             }
           }
    };

  -- Named root discovery uses the direct compiler's loader and search roots.
  -- Both parsers consume the captured text; there is no second source read.
  -- Only the separately admitted builtin may be an artifact dependency.
  compileDiscoveredRoot :: Bool -> String -> [] String -> String -> String -> String -> String ->
    IO (Either String OrderedPlanReceipt);
  compileDiscoveredRoot = compileDiscoveredRootUsing Nothing;
  compileDiscoveredRootMatching :: [] ((,,,) String String String String) ->
    Bool -> String -> [] String -> String -> String -> String -> String -> IO (Either String OrderedPlanReceipt);
  compileDiscoveredRootMatching expected = compileDiscoveredRootUsing (Just expected);
  compileDiscoveredRootUsing expected verifyAll identity roots entry cache builtinMetadata prefix =
    if not (Host.absolutePath cache) || eqString identity Artifact.builtinCrateIdentity
    then ioReturn (Left "invalid discovered crate identity or query cache")
    else do {
      present <- fileExists entry;
      if not present then ioReturn (Left ("discovered source root does not exist: " ++ entry))
      else do {
        text <- readFile entry;
        case Parser.parseModule entry text of {
          Left message -> ioReturn (Left message);
          Right root -> case Modules.sourceModuleName root of {
            Nothing -> ioReturn (Left "discovered ordered crate requires a named source root");
            Just entryName -> do {
              discovered <- Modules.loadModuleFilesWithEvidence roots root text;
              case discovered of {
                Left message -> ioReturn (Left message);
                Right loaded -> compileDiscoveredSources expected verifyAll identity entryName cache builtinMetadata loaded prefix
              }
            }
          }
        }
      }
    };
  compileDiscoveredSources expected verifyAll identity entryName cache builtinMetadata loaded prefix = do {
    captured <- mapM (\item -> do {
      let { source = Modules.loadedSource item; loaderPath = Modules.sourcePath source };
      canonical <- canonicalPath loaderPath;
      ioReturn ((,,,) (Modules.moduleIdentity source) loaderPath canonical (Modules.loadedText item))
    }) (Modules.loadedEntries loaded);
    sourceMatches <- case expected of {
      Nothing -> ioReturn True;
      Just rows -> do {
        observed <- mapM (\((,,,) name loaderPath canonical body) -> do {
          bytes <- byteArrayFromString body;
          digest <- byteArrayDigest bytes;
          ioReturn ((,,,) name loaderPath canonical digest)
        }) captured;
        let { same ((,,,) a b c d) ((,,,) w x y z) =
                eqString a w && eqString b x && eqString c y && eqString d z };
        ioReturn (eqList same rows observed)
      }
    };
    if sourceMatches
    then compileDiscoveredCaptured verifyAll identity entryName cache builtinMetadata loaded captured prefix
    else ioReturn (Left "discovered source snapshot differs from the expected loader rows")
  };
  compileDiscoveredCaptured verifyAll identity entryName cache builtinMetadata loaded captured prefix = do {
    builtin <- canonicalPath builtinMetadata;
    let { extension = stringSlice builtin (stringLength builtin - 6) 6 };
    if not (stringLength builtin > 6 && eqString extension ".mlfci")
    then ioReturn (Left "discovered ordered crate needs a builtin .mlfci")
    else do {
      let { sorted = sortBy (\((,,,) a _ _ _) ((,,,) b _ _ _) -> compareString a b) captured;
            sourcePaths = map (\((,,,) _ _ canonical _) -> canonical) sorted;
            builtinPrefix = stringSlice builtin 0 (stringLength builtin - 6);
            wire = Separate.pack ["MLF-CRATE-1",identity,entryName,"false",
              Separate.pack (map (\((,,,) name _ canonical _) -> Separate.pack [name,canonical]) sorted),
              Separate.pack [builtin],cache ++ "/discovered-order-v1",builtinPrefix] };
      case do {
        ensure (Set.size (Set.fromList compareString sourcePaths) == length sourcePaths)
          "discovered source path has multiple module owners";
        spec <- decodeSpec wire;
        -- Suffix and SourceSpan depend on the spelling the loader read.
        sources <- traverseEither (\((,,,) name loaderPath _ text) ->
          parseDiscoveredSource identity name loaderPath text) sorted;
        Right ((,) spec sources)
      } of {
        Left message -> ioReturn (Left message);
        Right ((,) spec sources) -> do {
          loadedInterfaces <- Artifact.loadInterfaces [builtin];
          case loadedInterfaces of {
            Left message -> ioReturn (Left message);
            Right interfaces -> case interfaces of {
              [(,) path iface] -> if not (eqString builtin path && eqString (Artifact.crateId iface) Artifact.builtinCrateIdentity)
                then ioReturn (Left "unexpected discovered crate builtin identity")
                else do {
                  raw <- Artifact.readObject (Artifact.objectPath builtin) iface;
                  case bindEither raw (Builtin.prepareObject "discovered-order-v1") of {
                    Left message -> ioReturn (Left message);
                    Right _ ->
                      compileLoadedSourcesWith (prepareDiscoveredCrate (Modules.loadedSources loaded))
                        orderedPlanReceipt verifyAll spec sources interfaces prefix
                  }
                };
              _ -> ioReturn (Left "discovered ordered crate requires only its admitted builtin")
            }
          }
        }
      }
    }
  };

}
