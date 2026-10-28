-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Crate where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
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
  import qualified Bootstrap.CrateArtifact as Artifact;
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
                            Separate.cleanSource source
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
  data PreparedCrate = PreparedCrate Modules.ResolvedCrate ([] DataDecl)
    ([] SClassDecl) ([] ((,) String SInstanceDecl)) Inference.LoweredDeclarations
    String (Map String (Set String)) (Maybe Source.SourcePlan);
  preparedResolution (PreparedCrate r _ _ _ _ _ _ _) = r;
  preparedData (PreparedCrate _ ds _ _ _ _ _ _) = ds;
  preparedClasses (PreparedCrate _ _ cs _ _ _ _ _) = cs;
  preparedInstances (PreparedCrate _ _ _ instances _ _ _ _) = instances;
  preparedLowered (PreparedCrate _ _ _ _ lowered _ _ _) = lowered;
  preparedEntry (PreparedCrate _ _ _ _ _ entry _ _) = entry;
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
  entryDeclaration spec resolution =
    if eqString (specEntry spec) ""
    then Right ((,) "" [])
    else do {
           entry <-
             case find
                    (\r ->
                       eqString (Modules.moduleIdentity (Modules.resolvedSource r))
                         (specEntry spec))
                    (Modules.resolvedCrateModules resolution) of {
               Nothing -> Left "crate entry module was not resolved";
               Just r -> Right r
             };
           expression <-
             case Modules.renamedBody (Modules.resolvedContents entry) of {
               Just body -> Right body;
               Nothing ->
                 if any (\value -> eqString (Modules.valueName value) "main")
                      (Modules.sourceValues (Modules.resolvedSource entry))
                 then mapEither SVar
                        (Modules.resolvedName (Modules.resolvedCrateNames resolution)
                           (Modules.Entity (specEntry spec) "main" Modules.Value))
                 else Modules.resolveExpr (Modules.resolvedCrateNames resolution)
                        (Modules.resolvedScope entry)
                        (SVar "main")
             };
           let {
             symbol =
               Artifact.definitionName (specIdentity spec)
                 (Modules.Entity (specEntry spec) "<crate-entry>" Modules.Value)
           };
           Right ((,) symbol ((:) ((,,) symbol Nothing expression) []))
         };
  externalInstanceOwners interfaces =
    concatMap
      (\((,) _ iface) ->
         map
           (\((,) name inst) ->
              mapEither (\owner -> (,) owner ((,) name inst)) (Artifact.instanceOwner iface name))
           (Artifact.crateInstances iface))
      interfaces;
  prepareCrate spec interfaces sources =
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
        mangle =
          \entity ->
            Artifact.definitionName
              (M.findWithDefault compareString (specIdentity spec) (Modules.owner entity) owners)
              entity
      };
      resolution <- Modules.resolveCrate (specMode spec) external mangle sources;
      let {
        resolved = Modules.resolvedCrateModules resolution
      };
      -- Canonicalize only this crate's freshly resolved source declarations.
      -- Imported checked layouts are validation context, never rewrite input.
      -- Do this before SourcePlan, dictionary inventory and cache-key creation.
      ownData <- D.canonicalSourceDeclarations
        (concatMap (\p -> Artifact.crateData (snd p)) interfaces)
        (concatMap (\r -> Modules.renamedDatatypes (Modules.resolvedContents r)) resolved);
      -- Checked class headers are ABI context. Canonicalize only this crate's
      -- fresh headers, before selectors, dictionary inventory and saved metadata.
      ownClasses <- Classes.canonicalSourceClasses Set.empty
        (append (concatMap (\p -> Artifact.crateData (snd p)) interfaces) ownData)
        (concatMap (\p -> Artifact.crateClasses (snd p)) interfaces)
        (concatMap (\r -> Modules.renamedClasses (Modules.resolvedContents r)) resolved);
      let {
        ownValues = concatMap (\r -> Modules.renamedValues (Modules.resolvedContents r)) resolved
      };
      boundValueShared19 <- entryDeclaration spec resolution;
      case boundValueShared19 of {
        (,) entry extra ->
          do {
            let {
              values = append ownValues extra
            };
            let {
              localInstances =
                map
                  (\((,) owner inst) ->
                     (,) owner ((,) (Artifact.instanceName (specIdentity spec) owner inst) inst))
                  (Modules.resolvedCrateInstances resolution)
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
              direct = M.union compareString (Modules.resolvedCrateReach resolution) externalReach
            };
            let {
              reach = Modules.settleReach direct direct
            };
            let {
              candidates =
                Modules.candidateScope reach
                  (map (\((,) owner value) -> (,) owner (snd value)) instances)
            };
            let {
              valueScopes =
                M.fromList compareString
                  (append
                     (concatMap
                        (\r ->
                           map
                             (\((,,) name _ _) ->
                                (,) name
                                  (candidates (Modules.moduleIdentity (Modules.resolvedSource r))))
                             (Modules.renamedValues (Modules.resolvedContents r)))
                        resolved)
                     (if eqString entry ""
                      then []
                      else (:) ((,) entry (candidates (specEntry spec))) []))
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
              imported =
                M.mapWithKey
                  (\name ty ->
                     Separate.sourceScheme
                       (if eqString (stringSlice name 0 7) "module_" then dictionaries else M.empty)
                       ty)
                  importedTypes
            };
            let {
              sourceNames = Modules.resolvedCrateDisplayNames resolution
            };
            let {
              diagnosticNames =
                M.union compareString (M.map (Modules.displayNames sourceNames) dictionaries)
                  sourceNames
            };
            sourcePlan <- mapLeft (Modules.displayNames diagnosticNames)
              (Source.prepareSourcePlan imported allData allClasses (map snd instances)
                valueScopes (map (\((,) owner _) -> candidates owner) instances) values);
            lowered <- case sourcePlan of {
              Nothing -> mapLeft (Modules.displayNames diagnosticNames)
                (Inference.lowerDeclarationsWithImports imported allData allClasses
                  (map snd instances) valueScopes
                  (map (\((,) owner _) -> candidates owner) instances) values);
              Just plan -> Right (case Source.planLegacy plan of {
                Right legacy -> legacy;
                Left message -> panic message
              })
            };
            Right
              (PreparedCrate resolution ownData ownClasses
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
        Just plan -> Query.compileSourceGroups (specIdentity spec) (specCache spec)
          imported protected plan;
        Nothing -> do {
          result <- Query.compileGroups (specIdentity spec) (specCache spec) imported
            (Inference.loweredData lowered) (Inference.loweredValues lowered);
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
               let {
                 object = Artifact.makeObject iface fragments
               };
               Artifact.validateInterface (Artifact.objectInterface object);
               Right ((,) object report)
             })
      }
    };
  parentDirectory path = Host.parentDirectory path;
  ensureBuiltin prefix =
    case Artifact.builtinPrelude of {
      Left message -> ioReturn (Left message);
      Right builtin ->
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
                         eqString (Artifact.encodeInterface (Artifact.objectInterface builtin))
                           (Artifact.encodeInterface (Artifact.objectInterface prior))
                     }
                 };
                 result <-
                   if valid
                   then ioReturn (Right ())
                   else do {
                          body <-
                            Query.writeCache (prefix ++ ".mlfco") (Artifact.encodeObject builtin);
                          case body of {
                            Left message -> ioReturn (Left message);
                            Right _ ->
                              Query.writeCache metadata
                                (Artifact.encodeInterface (Artifact.objectInterface builtin))
                          }
                        };
                 releaseFileLock lock;
                 ioReturn (mapEither (\_ -> metadata) result)
               }
        }
    };
  withPrelude spec sources interfaces =
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
               Just ((,) metadata iface) ->
                 ioReturn (mapEither (\_ -> metadata) (Artifact.validateInterface iface));
               Nothing -> ensureBuiltin (specPrelude spec)
             };
           case builtin of {
             Left message -> ioReturn (Left message);
             Right metadata ->
               do {
                 let {
                   updated =
                     withDependencies spec (nubBy eqString ((:) metadata (specDependencies spec)))
                 };
                 loaded <- Artifact.loadInterfaces (specDependencies updated);
                 ioReturn (mapEither ((,) updated) loaded)
               }
           }
         }
    else ioReturn (Right ((,) spec interfaces));
  compileSources spec sources interfaces prefix =
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
            result <- compilePrepared updated loaded prepared;
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
              Right ((,) object report) ->
                do {
                  Artifact.writeObject prefix object;
                  writeFile (prefix ++ ".queries")
                    (Query.reportJSON (specIdentity spec)
                       (Artifact.semanticFingerprint (Artifact.objectInterface object))
                       report);
                  ioReturn (Right ())
                }
            }
          }
      }
    };
  compileSpecFile file prefix =
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
                       compileSources normalized sources interfaces prefix
                   }
                 }
             }
           }
    }
}
