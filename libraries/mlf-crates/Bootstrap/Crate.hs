-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Crate where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Host as Host;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Lexer as Lexer;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.InferenceUnit as Inference;
  import qualified Bootstrap.CrateQuery as Query;
  import qualified Bootstrap.SourceInference as Source;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Resolved as R;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.BuiltinPreludeContext as Builtin;
  import qualified Bootstrap.BuiltinPreludeLiteral as Literal;
  -- The package driver supplies the source inventory for exactly one crate.
  -- Dependency paths designate generated metadata, never upstream sources.
  data CrateSpec =
    CrateSpec String String PreludeMode ([] ((,) String String)) ([] String) String String;
  specIdentity (CrateSpec identity _ _ _ _ _ _) = identity;
  specEntry (CrateSpec _ entry _ _ _ _ _) = entry;
  specMode (CrateSpec _ _ mode _ _ _ _) = mode;
  specSources (CrateSpec _ _ _ sources _ _ _) = sources;
  specDependencies (CrateSpec _ _ _ _ dependencies _ _) = dependencies;
  specCache (CrateSpec _ _ _ _ _ cache _) = cache;
  specPrelude (CrateSpec _ _ _ _ _ _ prelude) = prelude;
  withDependencies (CrateSpec identity entry mode sources _ cache prelude) dependencies =
    CrateSpec identity entry mode sources dependencies cache prelude;
  decodeSpec text =
    do {
      fields <- Separate.unpack text;
      let {
        matchValueShared2 = fields
      } in
      case matchValueShared2 of {
        (:) matchValueShared3 matchValueShared4 ->
          if MLF.Primitive.eqString matchValueShared3 "MLF-CRATE-1"
          then case matchValueShared4 of {
                 (:) matchValueShared5 matchValueShared6 ->
                   case matchValueShared6 of {
                     (:) matchValueShared7 matchValueShared8 ->
                       case matchValueShared8 of {
                         (:) matchValueShared9 matchValueShared10 ->
                           case matchValueShared10 of {
                             (:) matchValueShared11 matchValueShared12 ->
                               case matchValueShared12 of {
                                 (:) matchValueShared13 matchValueShared14 ->
                                   case matchValueShared14 of {
                                     (:) matchValueShared15 matchValueShared16 ->
                                       case matchValueShared16 of {
                                         (:) matchValueShared17 matchValueShared18 ->
                                           case matchValueShared18 of {
                                             [] ->
                                               let {
                                                 identity = matchValueShared5
                                               } in
                                               let {
                                                 entry = matchValueShared7
                                               } in
                                               let {
                                                 noPrelude = matchValueShared9
                                               } in
                                               let {
                                                 sources = matchValueShared11
                                               } in
                                               let {
                                                 dependencies = matchValueShared13
                                               } in
                                               let {
                                                 cache = matchValueShared15
                                               } in
                                               let {
                                                 prelude = matchValueShared17
                                               } in
                                               do {
                                                 ensure (stringLength identity > 0)
                                                   "crate identity is empty";
                                                 mode <-
                                                   let {
                                                     matchValueShared1 = noPrelude
                                                   } in
                                                   if MLF.Primitive.eqString matchValueShared1
                                                        "true"
                                                   then Right NoImplicitPrelude
                                                   else if MLF.Primitive.eqString matchValueShared1
                                                             "false"
                                                        then Right ImplicitPrelude
                                                        else Left "invalid crate prelude mode";
                                                 sourceFields <- Separate.unpack sources;
                                                 paths <-
                                                   traverseEither Separate.decodePair sourceFields;
                                                 deps <- Separate.unpack dependencies;
                                                 ensure (not (null paths))
                                                   "crate has no source modules";
                                                 ensure
                                                   (length paths ==
                                                    length
                                                      (nubBy (\a b -> eqString (fst a) (fst b))
                                                         paths))
                                                   "duplicate crate source module";
                                                 traverseEither
                                                   (\((,) name path) ->
                                                      do {
                                                        Separate.validModuleName name;
                                                        ensure (Host.absolutePath path)
                                                          "crate source path must be absolute"
                                                      })
                                                   paths;
                                                 ensure
                                                   (eqString entry "" ||
                                                    any (\p -> eqString (fst p) entry) paths)
                                                   "crate entry module is outside its source inventory";
                                                 ensure (Host.absolutePath cache)
                                                   "crate query cache path must be absolute";
                                                 ensure (Host.absolutePath prelude)
                                                   "shared prelude artifact prefix must be absolute";
                                                 Right
                                                   (CrateSpec identity entry mode
                                                      (sortBy
                                                         (\a b -> compareString (fst a) (fst b))
                                                         paths)
                                                      deps
                                                      cache
                                                      prelude)
                                               };
                                             _ ->
                                               Left
                                                 "unsupported or malformed crate specification (expected MLF-CRATE-1)"
                                           };
                                         _ ->
                                           Left
                                             "unsupported or malformed crate specification (expected MLF-CRATE-1)"
                                       };
                                     _ ->
                                       Left
                                         "unsupported or malformed crate specification (expected MLF-CRATE-1)"
                                   };
                                 _ ->
                                   Left
                                     "unsupported or malformed crate specification (expected MLF-CRATE-1)"
                               };
                             _ ->
                               Left
                                 "unsupported or malformed crate specification (expected MLF-CRATE-1)"
                           };
                         _ ->
                           Left
                             "unsupported or malformed crate specification (expected MLF-CRATE-1)"
                       };
                     _ -> Left "unsupported or malformed crate specification (expected MLF-CRATE-1)"
                   };
                 _ -> Left "unsupported or malformed crate specification (expected MLF-CRATE-1)"
               }
          else Left "unsupported or malformed crate specification (expected MLF-CRATE-1)";
        _ -> Left "unsupported or malformed crate specification (expected MLF-CRATE-1)"
      }
    };
  loadSources :: [] ((,) String String) -> IO (Either String ([] SourceModule));
  loadSources = loadSourcesInPackage "main";
  loadSourcesInPackage :: String -> [] ((,) String String) -> IO (Either String ([] SourceModule));
  loadSourcesInPackage sourcePackage paths =
    case paths of {
      [] -> ioReturn (Right []);
      (:) ((,) name path) rest ->
        do {
          present <- fileExists path;
          if not present
          then ioReturn (Left ("crate source does not exist: " ++ path))
          else do {
                 text <- readFile path;
                 case Parser.parseModuleInPackage sourcePackage path text of {
                   Left message -> ioReturn (Left message);
                   Right source ->
                     case do {
                            ensure (eqString name (Modules.moduleIdentity source))
                              ("crate source declares " ++
                               (Modules.moduleIdentity source ++ (", expected " ++ name)));
                            Separate.cleanParsedReserving
                              (not (Lexer.isSharedSyntax (Modules.sourceSyntax source)) ||
                               stringLength text /= stringUtf8Length text ||
                               Separate.sourceHasHygienePrefix text) source
                          } of {
                       Left message -> ioReturn (Left message);
                       Right clean ->
                         do {
                           remaining <- loadSourcesInPackage sourcePackage rest;
                           ioReturn (mapEither ((:) clean) remaining)
                         }
                     }
                 }
               }
        }
    };
  -- Only direct dependency namespaces are source-visible. The transitive
  -- metadata closure supplies their nominal identities and implementation ABI.
  externalNamespaces direct interfaces =
    do {
      let {
        accessible = filter (\((,) path iface) -> elem eqString path direct) interfaces
      };
      let {
        exports =
          append (concatMap (\p -> Artifact.crateExports (snd p)) accessible)
            (concatMap
               (\((,) _ iface) ->
                  filter (\p -> Modules.isBuiltinModule (fst p)) (Artifact.crateExports iface))
               interfaces)
      };
      foldM
        (\acc ((,) name entities) ->
           case M.lookup compareString name acc of {
             Nothing -> Right (M.insert compareString name (Modules.interface entities) acc);
             Just prior ->
               do {
                 ensure
                   (Set.eqSet (\a b -> (Modules.compareEntity a b == 0)) (Modules.visible prior)
                      (Set.fromList Modules.compareEntity entities))
                   ("conflicting dependency module: " ++ name);
                 Right acc
               }
           })
        M.empty
        exports
    };
  moduleOwners identity sources interfaces =
    foldM
      (\acc ((,) name owner) ->
         case M.lookup compareString name acc of {
           Nothing -> Right (M.insert compareString name owner acc);
           Just earlier ->
             if eqString earlier owner
             then Right acc
             else Left ("module belongs to multiple crates: " ++ name)
         })
      M.empty
      (append (map (\source -> (,) (Modules.moduleIdentity source) identity) sources)
         (concatMap
            (\((,) _ iface) ->
               map (\name -> (,) name (Artifact.crateId iface)) (Artifact.crateModules iface))
            interfaces));
  data CrateEntry = NoEntry | CrateEntry Dependency.Symbols (V.Index Declaration);
  entryName NoEntry = "";
  entryName (CrateEntry symbols i) = Dependency.symbolName symbols i;
  data PreparedCrate = PreparedCrate Modules.ResolvedCrate ([] DataDecl)
    ([] SClassDecl) ([] ((,) String SInstanceDecl)) Inference.LoweredDeclarations
    CrateEntry (Map String (Set String)) (Maybe Source.SourcePlan);
  preparedResolution (PreparedCrate r _ _ _ _ _ _ _) = r;
  preparedData (PreparedCrate _ ds _ _ _ _ _ _) = ds;
  preparedClasses (PreparedCrate _ _ cs _ _ _ _ _) = cs;
  preparedInstances (PreparedCrate _ _ _ instances _ _ _ _) = instances;
  preparedLowered (PreparedCrate _ _ _ _ lowered _ _ _) = lowered;
  preparedEntryId (PreparedCrate _ _ _ _ _ entry _ _) = entry;
  preparedEntry prepared = entryName (preparedEntryId prepared);
  preparedReach (PreparedCrate _ _ _ _ _ _ reach _) = reach;
  preparedSourcePlan (PreparedCrate _ _ _ _ _ _ _ plan) = plan;
  preparedLayouts prepared = case preparedSourcePlan prepared of {
    Just plan -> Source.planData plan;
    Nothing -> Inference.loweredData (preparedLowered prepared)
  };
  preparedNames prepared = case preparedSourcePlan prepared of {
    Just plan -> Source.planNames plan;
    Nothing -> Inference.loweredNames (preparedLowered prepared)
  };
  entryBindings spec resolution = let {
    modules = Modules.resolvedCrateModules resolution;
    expression = case find (\r -> eqString (Modules.moduleIdentity (Modules.resolvedSource r)) (specEntry spec)) modules of {
      Nothing -> Left "crate entry module was not resolved"; Just r -> Modules.entryExpr resolution r
    }
  } in entryBindingsFor spec (Modules.boundIn resolution modules) expression;
  entryBindingsFor spec bindings expression =
    if eqString (specEntry spec) "" then Right ((,) NoEntry bindings) else do {
      body <- expression;
      let { symbol = Artifact.definitionName (specIdentity spec)
        (Modules.Entity (specEntry spec) "<crate-entry>" Modules.Value) };
      case Dependency.appendBoundWithId bindings symbol body of {
        (,) slot allocated@(Dependency.BoundValues symbols _) -> Right ((,) (CrateEntry symbols slot) allocated)
      }
    };
  externalInstanceOwners interfaces =
    concatMap
      (\((,) _ iface) ->
         map
           (\((,) name inst) ->
              mapEither (\owner -> (,) owner ((,) name inst)) (Artifact.instanceOwner iface name))
           (Artifact.crateInstances iface))
      interfaces;
  -- File compilation needs the checked export namespace and renamed
  -- declarations. The public prepared-crate API also retains its source
  -- modules for inspection.
  data CompilationModule = CompilationModule String Modules.Renamed
    (Either String (R.Expr Declaration)) (Either String Modules.Interface);
  data CompilationModules = CompilationModules Modules.Bindings ([] CompilationModule) (Map String (Set String));
  compilationName (CompilationModule name _ _ _) = name;
  compilationContents (CompilationModule _ contents _ _) = contents;
  compilationEntry (CompilationModule _ _ entry _) = entry;
  compilationExports (CompilationModule _ _ _ exports) = exports;
  compilationBindings = compose Modules.renamedBindings compilationContents;
  compilationNames (CompilationModules table rows _) = Modules.displayBindingNames table
    (concatMap (compose (map Dependency.boundId) compilationBindings) rows);
  prepareCrate = prepareCrateUsing (\mode external definition sources -> do {
    full <- Modules.resolveCrateDefinitions mode external definition sources;
    let { row item = CompilationModule (Modules.moduleIdentity (Modules.resolvedSource item))
            (Modules.resolvedContents item) (Modules.entryExpr full item) (Modules.resolvedExports mode item);
          inputs = CompilationModules (Modules.resolvedCrateBindings full) (map row (Modules.resolvedCrateModules full))
            (Modules.resolvedCrateReach full)
    };
    Right ((,) inputs (PreparedCrate full))
  });
  prepareFileCrate finish = prepareCrateUsing (\mode external definition sources -> let {
    capture bindings source env exported renamed = let {
      owner = Modules.moduleIdentity source;
      hasMain = any (\v -> eqString (Modules.valueName v) "main") (Modules.sourceValues source);
      entry = Modules.moduleEntryExpr bindings owner hasMain env renamed
    } in seq owner (seq hasMain (Right (CompilationModule owner renamed entry (Right exported))));
    collect selected original bindings units = let {
      reach = Modules.crateReach selected original;
      result = CompilationModules bindings units reach
    } in seq (M.foldlWithKeyStrict (\_ name reachable -> seq name (seq (Set.size reachable) ())) () reach) ((,) result (finish result));
    run = Modules.resolveModuleRows (Modules.resolveFileModuleUsing capture) collect
  } in Modules.resolveWithTermKeyUsing run mode external definition definition sources);
  prepareCrateUsing resolve spec interfaces sources =
    do {
      traverseEither
        (\source ->
           ensure
             (eqString (Modules.moduleIdentity source) (specEntry spec) ||
              (case Modules.sourceBody source of {
                 Nothing -> True;
                 Just _ -> False
               }))
             ("imported module contains a top-level expression: " ++ Modules.moduleIdentity source))
        sources;
      external <- externalNamespaces (specDependencies spec) interfaces;
      owners <- moduleOwners (specIdentity spec) sources interfaces;
      let {
        -- All names owned by a crate share this exact encoded prefix.
        encodedOwners = M.map Separate.compactName owners;
        encodedDefault = Separate.compactName (specIdentity spec);
        mangle =
          \entity ->
            Artifact.definitionNameEncoded
              (M.findWithDefault compareString encodedDefault (Modules.owner entity) encodedOwners)
              entity
      };
      (,) inputs@(CompilationModules table resolved ownedReach) complete <- resolve (specMode spec) external mangle sources;
      let { symbols = Modules.bindingSymbols table;
            ownBindings = Dependency.BoundValues symbols (concatMap compilationBindings resolved) };
      (,) ownData ownClasses <- Classes.canonicalSourceHeaders Set.empty
        (concatMap (compose Artifact.crateData snd) interfaces)
        (concatMap (compose Artifact.crateClasses snd) interfaces)
        (concatMap (compose Modules.renamedDatatypes compilationContents) resolved)
        (concatMap (compose Modules.renamedClasses compilationContents) resolved);
      let { expression = case find (\unit -> eqString (compilationName unit) (specEntry spec)) resolved of {
        Nothing -> Left "crate entry module was not resolved"; Just unit -> compilationEntry unit
      } };
      entryAndBindings <- entryBindingsFor spec ownBindings expression;
      case entryAndBindings of {
        (,) entry bindings ->
          do {
            let {
              localRows = concatMap (\unit -> map (\inst -> (,) (compilationName unit) inst)
                (Modules.resolvedInstances (compilationContents unit))) resolved;
              describe ((,) owner row) = let { inst = R.namedInstance (Dependency.symbolName symbols) row } in
                (,) owner ((,) (Artifact.instanceName (specIdentity spec) owner inst) inst);
              localInstances = map describe localRows
            };
            inheritedInstances <- sequenceEither (externalInstanceOwners interfaces);
            let {
              instances = append inheritedInstances localInstances
            };
            let {
              externalReach =
                M.fromList compareString
                  (concatMap
                     (\((,) _ iface) ->
                        map (\((,) name reach) -> (,) name (Set.fromList compareString reach))
                          (Artifact.crateImports iface))
                     interfaces)
            };
            let {
              direct = M.union compareString ownedReach externalReach
            };
            let {
              reach = Modules.moduleReach direct
            };
            let {
              candidates =
                Modules.candidateScope reach
                  (map (\((,) owner value) -> (,) owner (snd value)) instances)
            };
            let {
              valueScopes = case bindings of { Dependency.BoundValues symbols _ ->
                let { group unit = let {
                  name = compilationName unit;
                  extra = case entry of {
                    CrateEntry _ i -> if eqString name (specEntry spec) then [i] else []; NoEntry -> []
                  }
                } in (,) name (append (map Dependency.boundId (compilationBindings unit)) extra)
                } in Dependency.indexedModuleScopes symbols (map group resolved) (map fst instances) candidates
              }
            };
            let {
              allData = append (concatMap (\p -> Artifact.crateData (snd p)) interfaces) ownData
            };
            let {
              allClasses =
                append (concatMap (\p -> Artifact.crateClasses (snd p)) interfaces) ownClasses
            };
            let {
              dictionaries =
                M.fromList compareString
                  (map (\c -> (,) ("Dict_" ++ Classes.className c) (Classes.className c))
                     allClasses)
            };
            let {
              importedTypes =
                M.fromList compareString
                  (concatMap (\p -> Artifact.crateBindings (snd p)) interfaces)
            };
            let {
              importDictionaries name =
                if eqString (stringSlice name 0 7) "module_" then dictionaries else M.empty;
              conventions = M.mapWithKey (\name ty -> Separate.importClasses (importDictionaries name) ty) importedTypes;
              imported =
                M.mapWithKey
                  (\name ty ->
                     Separate.sourceScheme (importDictionaries name) ty)
                  importedTypes
            };
            let {
              sourceNames = compilationNames inputs
            };
            let {
              diagnosticNames =
                M.union compareString (M.map (Modules.displayNames sourceNames) dictionaries)
                  sourceNames
            };
            (,) sourcePlan legacy <- mapLeft (Modules.displayNames diagnosticNames) (do {
              let { members = Dependency.boundValues bindings;
                    memberMap = M.fromList compareString (map (\m -> (,) (Modules.valueName m) m) members) };
              importedInstances <- traverseEither (\((,) _ ((,) name inst)) ->
                mapEither ((,) name) (Surface.closeSourceInstance members memberMap inst)) inheritedInstances;
              let { closeLocal = Surface.closeIndexedInstance (Surface.helperScope bindings) };
              local <- traverseEither (\((,) metadata row) -> mapEither ((,) (fst (snd metadata))) (closeLocal (snd row)))
                (zip localInstances localRows);
              Source.prepareResolvedSourcePlanWithImports conventions bindings imported allData allClasses (map snd instances)
                (append importedInstances local) valueScopes (map (\((,) owner _) -> candidates owner) instances)
            });
            lowered <- case sourcePlan of {
              Nothing -> mapLeft (Modules.displayNames diagnosticNames) legacy;
              Just plan -> Right (case Source.planLegacy plan of {
                Right legacy -> legacy;
                Left message -> panic message
              })
            };
            Right
              (complete ownData ownClasses
                 (map (\((,) _ ((,) name inst)) -> (,) name (Separate.stripInstance inst))
                    localInstances)
                 lowered
                 entry
                 reach sourcePlan)
          }
      }
    };
  -- Query compilation consumes only metadata-derived schemes. Upstream checked
  -- bodies are opened later by the linker and never enter an inference key.
  compilePrepared spec interfaces prepared =
    compilePreparedWith (\object _ report -> (,) object report) spec interfaces prepared;
  -- Preserve compilePrepared's public result while allowing the file producer
  -- to carry the exact finalized pooled payload through its result builder.
  -- The builder runs only after the same interface validation as before.
  compilePreparedWith :: forall a. (Artifact.CrateObject -> String -> Query.QueryReport -> a) ->
    CrateSpec -> [] ((,) String Artifact.CrateInterface) -> PreparedCrate ->
    IO (Either String a);
  compilePreparedWith complete spec interfaces prepared =
    compilePreparedWithEncoding False complete spec interfaces prepared;
  -- Only compileSpecFile enables this internal parsed-source encoding path.
  -- Generic prepared/source APIs retain their original no-pool demand behavior.
  compilePreparedWithEncoding :: forall a. Bool ->
    (Artifact.CrateObject -> String -> Query.QueryReport -> a) ->
    CrateSpec -> [] ((,) String Artifact.CrateInterface) -> PreparedCrate ->
    IO (Either String a);
  compilePreparedWithEncoding shareEncoding = compilePreparedUsing
    (if shareEncoding then Query.compileParsedSourceGroups else Query.compileSourceGroups);
  compilePreparedUsing compileGroups complete spec interfaces prepared =
    do {
      let {
        lowered = preparedLowered prepared
      };
      let {
        imported =
          map
            (\((,) _ iface) ->
               Separate.UnitInterface (Artifact.crateId iface) [] [] [] [] []
                 (Artifact.crateBindings iface)
                 "metadata")
            interfaces
      };
      let {
        protected = foldl
          (\acc entry -> M.insert compareString (fst entry)
            (snd entry || M.findWithDefault compareString False (fst entry) acc) acc)
          M.empty (concatMap (\p -> Artifact.crateProtection (snd p)) interfaces)
      };
      compiled <- case preparedSourcePlan prepared of {
        Just plan -> compileGroups (specIdentity spec) (specCache spec) imported protected plan;
        Nothing -> do {
          result <- Query.compileLoweredFileGroups (specIdentity spec) (specCache spec) imported lowered;
          ioReturn (mapEither (\((,) fragments report) -> (,,) fragments report
            (M.fromList compareString
              (map (\((,) name ty) -> (,) name (Source.SourceContract ty [] True))
                (concatMap (\f -> Separate.unitBindings (Separate.objectInterface f)) fragments)))) result)
        }
      };
      case compiled of {
        Left message -> ioReturn (Left message);
        Right ((,,) fragments report contracts) ->
          ioReturn
            (do {
               let {
                 resolved = Modules.resolvedCrateModules (preparedResolution prepared)
               };
               exports <-
                 traverseEither
                   (\r ->
                      mapEither
                        (\scope ->
                           (,) (Modules.moduleIdentity (Modules.resolvedSource r))
                             (Set.toList (Modules.visible scope)))
                        (Modules.resolvedExports (specMode spec) r))
                   resolved;
               let {
                 dependencies =
                   map
                     (\path ->
                        case find (\p -> eqString (fst p) path) interfaces of {
                          Nothing -> panic "missing direct crate metadata";
                          Just ((,) _ iface) ->
                            (,,) (Artifact.crateId iface) path
                              (Artifact.semanticFingerprint iface)
                        })
                     (specDependencies spec)
               };
               let {
                 externalLayouts =
                   Set.fromList compareString
                     (concatMap
                        (\((,) _ iface) -> map D.datatypeName (Artifact.crateLoweredData iface))
                        interfaces)
               };
               let {
                 layouts =
                   filter (\d -> not (Set.member compareString (D.datatypeName d) externalLayouts))
                     (preparedLayouts prepared)
               };
               let {
                 modules = map (\r -> Modules.moduleIdentity (Modules.resolvedSource r)) resolved
               };
               let {
                 reach =
                   map
                     (\name ->
                        (,) name
                          (Set.toList
                             (M.findWithDefault compareString Set.empty name
                                (preparedReach prepared))))
                     modules
               };
               let {
                 bindings =
                   concatMap (\f -> Separate.unitBindings (Separate.objectInterface f)) fragments
               };
               protection <- traverseEither
                 (\((,) name _) -> case M.lookup compareString name contracts of {
                   Just contract -> Right ((,) name (Source.contractProtected contract));
                   Nothing -> Left ("final source binding lacks a protection contract: " ++ name)
                 }) bindings;
               let {
                 iface =
                   Artifact.CrateInterface (specIdentity spec) dependencies modules exports reach
                     (preparedData prepared)
                     (preparedClasses prepared)
                     (preparedInstances prepared)
                     layouts
                     bindings
                     (preparedEntry prepared)
                     "pending"
                     protection
               };
               case Artifact.makeObjectWithPayload iface fragments of {
                 (,) object payload -> do {
                   Artifact.validateInterface (Artifact.objectInterface object);
                   Right (complete object payload report)
                 }
               }
             })
      }
    };
  parentDirectory path = Host.parentDirectory path;
  ensureBuiltin = ensureBuiltinWith Nothing;
  -- Both formal readers and exact interface equality guard disk hits. A
  -- miss can install the split object generated with the checked compiler
  -- witness. Any failure in the embedded object's admission takes the fresh path.
  ensureBuiltinWith witness prefix =
    case (case witness of {
      Nothing -> mapEither Artifact.objectInterface Artifact.builtinPrelude;
      Just ((,) checked _) -> Right (Builtin.interface checked)
    }) of {
      Left message -> ioReturn (Left message);
      Right expected ->
        do {
          let {
            metadata = (prefix ++ ".mlfci")
          };
          code <-
            Query.cacheCommand ((:) "/bin/mkdir" ((:) "-p" ((:) (parentDirectory prefix) [])));
          if (code /= 0)
          then ioReturn (Left "cannot create shared Prelude directory")
          else do {
                 lock <- acquireFileLock (prefix ++ ".lock");
                 existing <- Artifact.readInterface metadata;
                 object <-
                   case existing of {
                     Left message -> ioReturn (Left message);
                     Right iface -> Artifact.readObject (prefix ++ ".mlfco") iface
                   };
                 let {
                   valid =
                     case object of {
                       Left _ -> False;
                       Right prior ->
                         eqString (Artifact.encodeInterface expected)
                           (Artifact.encodeInterface (Artifact.objectInterface prior))
                     }
                 };
                 result <-
                   if valid
                   then ioReturn (Right ())
                   else case builtinForInstall witness of {
                     Left message -> ioReturn (Left message);
                     Right builtin -> Artifact.writeObjectAtomicEither prefix builtin
                   };
                 releaseFileLock lock;
                 ioReturn (mapEither (\_ -> metadata) result)
               }
        }
    };
  builtinForInstall witness = case witness of {
    Just ((,) checked encoded) -> case Literal.checkedCrateObject checked encoded of {
      Right object -> Right object;
      Left _ -> Artifact.builtinPrelude
    };
    Nothing -> Artifact.builtinPrelude
  };
  withPrelude = withPreludeUsing ensureBuiltin;
  withPreludeUsing = withPreludeLoading Artifact.loadInterfaces;
  withPreludeLoading = withPreludeMetadata (\((,) path iface) ->
    mapEither (\_ -> path) (Artifact.validateInterface iface));
  withPreludeMetadata existing load install spec sources interfaces =
    if any
         (\source ->
            (Lexer.isSharedSyntax (Modules.sourceSyntax source) || any (\entry -> Modules.isBuiltinModule (Modules.importedModule entry))
              (Modules.importsFor (specMode spec) source)))
         sources
    then do {
           builtin <-
             case find
                    (\((,) _ iface) ->
                       (elem eqString "Prelude" (Artifact.crateModules iface) &&
                        elem eqString "MLF.Primitive" (Artifact.crateModules iface)))
                    interfaces of {
               Just entry -> ioReturn (existing entry);
               Nothing -> install (specPrelude spec)
             };
           case builtin of {
             Left message -> ioReturn (Left message);
             Right metadata ->
               do {
                 let {
                   updated =
                     withDependencies spec (nubBy eqString ((:) metadata (specDependencies spec)))
                 };
                 loaded <- load (specDependencies updated);
                 ioReturn (mapEither ((,) updated) loaded)
               }
           }
         }
    else ioReturn (Right ((,) spec interfaces));
  compileSources spec sources interfaces prefix =
    compileSourcesWithEncoding False spec sources interfaces prefix;
  compileSourcesWithEncoding :: Bool -> CrateSpec -> [] SourceModule ->
    [] ((,) String Artifact.CrateInterface) -> String -> IO (Either String ());
  compileSourcesWithEncoding shareEncoding spec sources interfaces prefix =
    do {
      dependencies <- withPrelude spec sources interfaces;
      case do {
             boundValueShared20 <- dependencies;
             case boundValueShared20 of {
               (,) updated loaded ->
                 do {
                   prepared <- prepareCrate updated loaded sources;
                   Right ((,,) updated loaded prepared)
                 }
             }
           } of {
        Left message -> ioReturn (Left message);
        Right ((,,) updated loaded prepared) ->
          do {
            result <- compilePreparedWithEncoding shareEncoding
              (\object payload report -> (,,) object payload report) updated loaded prepared;
            case result of {
              Left message ->
                let {
                  names = Modules.resolvedCrateDisplayNames (preparedResolution prepared)
                } in
                let {
                  diagnostics =
                    M.union compareString
                      (M.map (Modules.displayNames names)
                         (preparedNames prepared))
                      names
                } in
                ioReturn (Left (Modules.displayNames diagnostics message));
              Right ((,,) object payload report) ->
                do {
                  written <- Artifact.writeObjectWithPayloadEither prefix object payload;
                  case written of {
                    Left message -> ioReturn (Left message);
                    Right _ -> do {
                      writeFile (prefix ++ ".queries")
                        (Query.reportJSON (specIdentity spec)
                           (Artifact.semanticFingerprint (Artifact.objectInterface object)) report);
                      ioReturn (Right ())
                    }
                  }
                }
            }
          }
      }
    };
  loadSpecFile load file = do {
    present <- fileExists file;
    if not present then ioReturn (Left ("crate specification does not exist: " ++ file)) else do {
      text <- readFile file;
      case decodeSpec text of {
        Left message -> ioReturn (Left message);
        Right spec -> do {
          sourceResult <- loadSourcesInPackage (specIdentity spec) (specSources spec);
          paths <- mapM canonicalPath (specDependencies spec);
          dependencies <- load paths;
          ioReturn (do {
            sources <- sourceResult;
            interfaces <- dependencies;
            Right ((,,) (withDependencies spec paths) sources interfaces)
          })
        }
      }
    }
  };
  compileSpecFile file prefix = do {
    loaded <- loadSpecFile Artifact.loadInterfaces file;
    case loaded of {
      Left message -> ioReturn (Left message);
      Right ((,,) spec sources interfaces) -> compileSourcesWithEncoding True spec sources interfaces prefix
    }
  }
}
