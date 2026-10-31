-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- File-owned candidate route. No raw AST, Solver, region, or callback escapes.
module Bootstrap.CrateSession (compileSpecFile) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.ST as ST;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.IntRank as Rank;
  import Bootstrap.Crate (CrateSpec, PreparedCrate, withPrelude, prepareCrate,
    withDependencies, loadSourcesInPackage, decodeSpec, specIdentity, specSources,
    specDependencies, specCache, specMode, preparedLowered, preparedSourcePlan,
    preparedResolution, preparedNames, preparedLayouts, preparedReach,
    preparedData, preparedClasses, preparedInstances, preparedEntry);
  import qualified Bootstrap.CrateQuery as Query;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.InferenceUnit as Inference;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.SourceInference as Source;
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

  compilePreparedWithEncoding :: forall a. Bool ->
    (Artifact.CrateObject -> String -> Query.QueryReport -> a) ->
    CrateSpec -> [] ((,) String Artifact.CrateInterface) -> PreparedCrate ->
    IO (Either String a);
  compilePreparedWithEncoding shareEncoding complete spec interfaces prepared =
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
        Just plan -> if shareEncoding
          then compileParsedSourceGroups (specIdentity spec) (specCache spec)
            imported protected plan
          else Query.compileSourceGroups (specIdentity spec) (specCache spec)
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
               case Artifact.makeObjectWithPayload iface fragments of {
                 (,) object payload -> do {
                   Artifact.validateInterface (Artifact.objectInterface object);
                   Right (complete object payload report)
                 }
               }
             })
      }
    };

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
                  Artifact.writeObjectWithPayload prefix object payload;
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

  compileSpecFile :: String -> String -> IO (Either String ());
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
                       -- Both source and dependency values originate in the
                       -- parsers/decoders above, not caller-supplied lazy ASTs.
                       compileSourcesWithEncoding True normalized sources interfaces prefix
                   }
                 }
             }
           }
    };

  runSourceGroupsWithEncodings :: Maybe Query.SourceEncodings -> String -> String -> String ->
    Query.TypeInventory -> Source.SourcePlan -> [] ([] String) -> Map String Source.SourceContract ->
    [] Separate.UnitObject -> Int -> Int -> [] Query.GroupResult ->
    IO (Either String ((,,) ([] Separate.UnitObject) Query.QueryReport (Map String Source.SourceContract)));
  runSourceGroupsWithEncodings encodings crateId compilerHash cacheDir inventory plan groups contracts
    objects inferred reused results = case groups of {
    [] -> ioReturn (Right ((,,) (reverse objects)
      (Query.QueryReport inferred reused (reverse results)) contracts));
    (:) names rest -> case Source.prepareGroup plan contracts names of {
      Left error -> ioReturn (Left error);
      Right prepared -> do {
        let { bindings = Source.groupBindings prepared };
        let { members = Source.groupMembers prepared };
        let { datatypes = Query.requiredDataIn inventory members
          (append bindings (Source.groupCandidateBindings prepared)) };
        let { name = Query.groupName crateId names };
        let { key = case encodings of {
          Nothing -> Query.sourceQueryKey crateId compilerHash prepared contracts datatypes;
          Just pool -> Query.sourceQueryKeyWithContext crateId compilerHash prepared contracts
            (Query.encodeDatatypeContextWithPool pool datatypes)
        } };
        writeFile (cacheDir ++ "/query-key.new") key;
        digest <- fileDigest (cacheDir ++ "/query-key.new");
        let { destination = cacheDir ++ "/" ++ digest ++ ".mlfq" };
        present <- fileExists destination;
        cached <- if present then do {
          input <- readFile destination;
          ioReturn (do {
            object <- Query.decodeCached key name bindings datatypes names input;
            Source.validatePreparedRaw prepared object
          })
        } else ioReturn (Left "cache miss");
        let { raw = case cached of {
          Right object -> Right ((,) True object);
          Left _ -> mapEither ((,) False) (case encodings of {
            Nothing -> compileLoweredGroup name
              ((:) (Query.dependencyInterface bindings) []) datatypes members;
            Just (Query.SourceEncodings pool _) -> compileLoweredGroupWithDatatypes pool name
              ((:) (Query.dependencyInterface bindings) []) datatypes members
          })
        } };
        case raw of {
          Left error -> ioReturn (Left error);
          Right ((,) hit object) -> case Source.finishGroup prepared object of {
            Left error -> ioReturn (Left error);
            Right finalized -> do {
              saved <- if hit then ioReturn (Right ())
                else Query.writeCache destination (case encodings of {
                  Nothing -> Query.encodeCached key object;
                  Just (Query.SourceEncodings pool _) -> Query.encodeCachedWithDatatypes pool key object
                });
              case saved of {
                Left error -> ioReturn (Left error);
                Right _ -> do {
                  let { finalObject = Source.finalGroupObject finalized };
                  let { finalContracts = Source.finalGroupContracts finalized };
                  let { semantic = Separate.fingerprint (Query.list Query.encodeBinding
                    (Separate.unitBindings (Separate.objectInterface finalObject))) };
                  runSourceGroupsWithEncodings encodings crateId compilerHash cacheDir inventory plan rest
                    (M.union compareString finalContracts contracts)
                    ((:) finalObject objects) (inferred + (if hit then 0 else 1))
                    (reused + (if hit then 1 else 0))
                    ((:) (Query.GroupResult name names hit semantic digest) results)
                }
              }
            }
          }
        }
      }
    }
  };

  compileParsedSourceGroups :: String -> String -> [] Separate.UnitInterface ->
    Map String Bool -> Source.SourcePlan ->
    IO (Either String ((,,) ([] Separate.UnitObject) Query.QueryReport (Map String Source.SourceContract)));
  compileParsedSourceGroups crateId directory imports protected originalPlan =
    compileSourceGroupsWithEncoding True crateId directory imports protected originalPlan;
  compileSourceGroupsWithEncoding :: Bool -> String -> String -> [] Separate.UnitInterface ->
    Map String Bool -> Source.SourcePlan ->
    IO (Either String ((,,) ([] Separate.UnitObject) Query.QueryReport (Map String Source.SourceContract)));
  compileSourceGroupsWithEncoding shareEncoding crateId directory imports protected originalPlan =
    case Source.initializeProtection originalPlan protected of {
      Left error -> ioReturn (Left error);
      Right plan -> case Query.prepareData (Source.planData plan) of {
      Left error -> ioReturn (Left error);
      Right inventory -> case foldM Inference.mergeExternal M.empty
        (concatMap Separate.unitBindings imports) of {
        Left error -> ioReturn (Left error);
        Right types -> case Source.initialContracts plan types protected of {
          Left error -> ioReturn (Left error);
          Right contracts ->
            if stringLength directory == 0 then ioReturn (Left "inference cache directory is empty")
            else do {
              let { cacheDir = Query.cachePath directory };
              code <- Query.cacheCommand ((:) "/bin/mkdir" ((:) "-p" ((:) cacheDir [])));
              if code /= 0 then ioReturn (Left "cannot create inference cache directory") else do {
                lock <- acquireFileLock (cacheDir ++ "/.lock");
                executable <- getExecutablePath;
                compilerHash <- fileDigest executable;
                let { encodings = if shareEncoding
                      then Just (Query.prepareSourceEncodings (Source.planData plan)) else Nothing };
                result <- runSourceGroupsWithEncodings encodings
                  crateId compilerHash cacheDir inventory plan (Source.planGroups plan) contracts [] 0 0 [];
                releaseFileLock lock;
                ioReturn result
              }
            }
        }
      }
    }
  };

  compileLoweredGroup :: String ->
                         [] Separate.UnitInterface ->
                         [] DataDecl ->
                         [] ((,,) String (Maybe SAnnotation) SExpr) ->
                         Either String Separate.UnitObject;
  -- SCC fragments are parameters, not independently imported modules. The
  -- crate artifact validates the selected schemes and owns the crate DAG;
  -- module interface dependency hashes would cause transitive invalidation.
  compileLoweredGroup name dependencies datatypes members =
    compileLoweredGroupUsing (\term -> Separate.fingerprint (Pretty.prettyTerm term))
      name dependencies datatypes members;
  compileLoweredGroupWithDatatypes :: Separate.DatatypeEncodings -> String ->
    [] Separate.UnitInterface -> [] DataDecl ->
    [] ((,,) String (Maybe SAnnotation) SExpr) -> Either String Separate.UnitObject;
  compileLoweredGroupWithDatatypes pool name dependencies datatypes members =
    compileLoweredGroupUsing (Separate.fingerprintTermWithDatatypes pool)
      name dependencies datatypes members;
  compileLoweredGroupUsing :: (XTerm -> String) -> String ->
    [] Separate.UnitInterface -> [] DataDecl ->
    [] ((,,) String (Maybe SAnnotation) SExpr) -> Either String Separate.UnitObject;
  compileLoweredGroupUsing payloadFingerprint name dependencies datatypes members =
    do {
      ensure (not (null members)) "cannot infer an empty declaration group";
      externalTypes <- foldM Inference.mergeExternal M.empty (concatMap Separate.unitBindings dependencies);
      traverseEither
        (\((,,) n _ _) ->
           ensure (not (M.member compareString n externalTypes))
             ("inference group also imports its own binding: " ++ n))
        members;
      body <- Surface.bindValues members (SConstructor "()");
      let {
        -- Members already contain explicit evidence applications. Recovering
        -- source qualifications here would insert the managed argument twice.
        externals = M.map (Separate.sourceSchemeIn M.empty False) externalTypes
      };
      lowered <- Classes.lowerSeparateClasses externals [] (SProgram datatypes body);
      compiled <- mapLeft Compiler.prettyError (finishCompilation lowered);
      let {
        coreAndData =
          case Compiler.compiledTerm compiled of {
            XWithData ds term -> (,) ds term;
            term -> (,) [] term
          }
      };
      let {
        declarations = fst coreAndData
      };
      let {
        core = snd coreAndData
      };
      boundValueShared9 <-
        if M.null externalTypes
        then Right ((,) [] core)
        else case core of {
               XLetRec bindings rest ->
                 do {
                   ensure
                     (eqList eqString (map (\((,,) n _ _) -> X.nameHint n) bindings)
                        (M.keys externalTypes))
                     "inference parameter order mismatch";
                   traverseEither
                     (\((,,) n ty _) ->
                        ensure
                          (case M.lookup compareString (X.nameHint n) externalTypes of {
                             Nothing -> False;
                             Just expected -> T.alphaEq ty expected
                           })
                          ("dependency scheme changed during inference: " ++ X.nameHint n))
                     bindings;
                   Right ((,) (map (\((,,) n ty _) -> (,) n ty) bindings) rest)
                 };
               _ -> Left "inference did not retain external parameters"
             };
      case boundValueShared9 of {
        (,) parameters implementation ->
          do {
            dataEnv <- D.validateDeclarations declarations;
            bindings <-
              Separate.collectBindings dataEnv (XEnv M.empty (M.fromList X.compareName parameters))
                implementation;
            ensure
              (eqList eqString (sortBy compareString (map (\((,) n _) -> X.nameHint n) bindings))
                 (sortBy compareString (map (\((,,) n _ _) -> n) members)))
              "inference fragment changed declaration ownership";
            let {
              payload =
                XWithData declarations
                  (foldr (\((,) n ty) term -> XAbs n ty term) implementation parameters)
            };
            checked <- Checked.check payload;
            let {
              iface =
                Separate.UnitInterface name [] [] declarations [] []
                  (Separate.sortBindings
                     (map (\((,) n ty) -> (,) (X.nameHint n) (Separate.normalType ty)) bindings))
                  (payloadFingerprint payload)
            };
            Right (Separate.CheckedUnitObject iface checked)
          }
      }
    };

  finishCompilation :: (,) SProgram (Map String String) -> Either CompileError Compiler.Compilation;
  finishCompilation ((,) program names) =
    case program of {
      SClassProgram _ _ _ _ ->
        Left (CompileError Inference "class translation did not produce a core program");
      SProgram declarations expression ->
        do {
          constraints <- Compiler.atPhase Inference (C.generateProgram program);
          solved <- Compiler.atPhase Inference (solveGenerated constraints);
          let {
            graph = S.solverGraph solved
          };
          let {
            types = E.prepareTypes graph
          };
          evidence <- Compiler.atPhase Resolution (E.resolveEvidenceIn types (C.skeleton constraints));
          body <-
            Compiler.atPhase Elaboration
              (E.elaboratePreparedIn types solved evidence (C.skeleton constraints));
          let {
            term = if L.null declarations then body else XWithData declarations body
          };
          checked <- Compiler.atPhase Verification (Checked.check term);
          let {
            ty = Checked.typeOf checked
          };
          let {
            expected = E.schemeTypeIn types (C.generalization (C.skeleton constraints))
          };
          if L.not (T.alphaEq ty expected)
          then Left (CompileError Verification "elaboration changed the inferred type")
          else if L.not
                    (X.equalErased (X.erase term)
                       (C.eraseSourceWith evidence (C.skeleton constraints)))
               then Left (CompileError Verification "elaboration changed source erasure")
               else Right (Compiler.Compilation checked graph (Classes.prettyQualified names ty))
        }
    };

  -- Private epoch state: old Graph/ScopeIndex values are immutable, while the
  -- Store always denotes the CURRENT epoch. Never use an old Session as history.
  data Session s = Session Graph ScopeIndex (K.Store s);
  data Visit = VisitNode Int | VisitStructural Int | VisitBinding Int;
  graph :: forall s. Session s -> Graph;
  graph (Session current scopes store) = current;
  scopeIndex :: forall s. Session s -> ScopeIndex;
  scopeIndex (Session current scopes store) = scopes;
  mkSession :: forall s. Graph -> ScopeIndex -> K.Store s -> Session s;
  mkSession current scopes store =
    let { strict = G.strictGraph current; strictScopes = S.strictScopes scopes } in
    seq strict (seq strictScopes (Session strict strictScopes store));
  withGraph :: forall s. Graph -> Session s -> Session s;
  withGraph current (Session old scopes store) = mkSession current scopes store;
  openSession :: forall s. Solver -> ST s (Session s);
  openSession solver =
    stBind (K.importIndices (S.structuralParents solver) (S.bindingChildren solver))
      (\store -> stReturn (mkSession (S.graph solver) (S.scopeIndex solver) store));
  -- Only this sealed parsed-file route changes initial reverse-index storage.
  -- Keep prepare's checks outside the region and its successful graph lazy.
  prepareGraph :: Graph -> Either String Graph;
  prepareGraph input =
    G.bindE (G.validateGraph input)
      (\ignored -> prepareValidatedGraph input);
  -- Both callers have already validated this unchanged graph. Identity, alias
  -- and index admission still happens before opening a session.
  prepareValidatedGraph :: Graph -> Either String Graph;
  prepareValidatedGraph input =
    if L.any (\n -> IM.member n (G.links input)) (IM.keys (G.nodes input))
    then Left "live graph identities cannot also be aliases"
    else if L.any (\n -> (n >= G.nextId input)) (IM.keys (G.nodes input))
         then Left "fresh identity counter overlaps graph nodes"
         else if L.any (\n -> (n >= G.nextId input)) (IM.keys (G.links input))
              then Left "fresh identity counter overlaps graph aliases"
              else Right (G.canonicalize input);
  openPreparedSession :: forall s. Graph -> ST s (Session s);
  openPreparedSession canonical =
    stBind (K.importIndices IM.empty IM.empty)
      (\store ->
        stBind (ST.fold addInitialNode
          (mkSession canonical (S.indexScopes canonical) store)
          (IM.toList (G.nodes canonical)))
          (\prepared -> seq prepared (stReturn prepared)));
  -- ST.fold first inspects the same node-list spine as prepare's strict fold.
  -- Then force the initial state before the node pair, as S.addNode does. The
  -- final force above also admits strict graph/scope roots for an empty graph.
  addInitialNode :: forall s. Session s -> (,) Int Node -> ST s (Session s);
  addInitialNode state entry = seq state (addNode state entry);
  freezeSession :: forall s. Session s -> ST s Solver;
  freezeSession (Session current scopes store) =
    stBind (K.freezeIndices store)
      (\((,) parents descendants) -> stReturn (S.mkSolver current parents descendants scopes));
  readBucket :: forall s. K.Index -> Int -> Session s -> ST s IntSet;
  readBucket index key (Session current scopes store) = K.readBucket index key store;
  commit :: forall s. [] K.Edit -> Session s -> ST s (Session s);
  commit edits state@(Session current scopes store) =
    stBind (K.commitEdits edits store) (\ignored -> stReturn state);
  finish :: forall s. Session s -> ST s (Either String Graph);
  finish state = stBind (freezeSession state) (\snapshot -> stReturn (S.finish snapshot));
  finishNormalized :: forall s. Session s -> ST s (Either String Solver);
  finishNormalized state = stBind (freezeSession state) (\snapshot -> stReturn (S.finishNormalized snapshot));
  audit :: forall s. Session s -> ST s (Either String (Session s));
  audit state = ST.bindE (finish state) (\checked -> ST.pureE state);
  solvePrepared :: Constraints -> Either String Solver;
  solvePrepared constraints =
    solvePreparedGraph (prepareGraph (C.initialGraph constraints)) constraints;
  -- This private route is used only immediately after generateProgram succeeds;
  -- it has already validated exactly initialGraph. Arbitrary constraints retain
  -- solvePrepared's original validation, and final validation is unchanged.
  solveGenerated :: Constraints -> Either String Solver;
  solveGenerated constraints =
    solvePreparedGraph (prepareValidatedGraph (C.initialGraph constraints)) constraints;
  solvePreparedGraph :: Either String Graph -> Constraints -> Either String Solver;
  solvePreparedGraph prepared constraints = G.bindE prepared
    (\canonical -> runST
      (stBind (openPreparedSession canonical)
        (\initial -> ST.bindE (solverUnify (C.equalities constraints) initial)
          (\unified -> ST.bindE (evaluateSteps unified (C.solveSteps constraints))
            finishNormalized))));
  evaluateStep :: forall s. Session s -> SolveStep -> ST s (Either String (Session s));
  evaluateStep state step = case step of {
    Instantiate edge -> instantiateClosed (C.fromGen edge) (C.toNode edge) state;
    ProjectCase fields -> projectCaseFields fields state
  };
  evaluateSteps :: forall s. Session s -> [] SolveStep -> ST s (Either String (Session s));
  evaluateSteps initial steps = ST.foldE evaluateStep initial steps;
  addNode :: forall s. Session s -> (,) Int Node -> ST s (Session s);
  addNode state ((,) identity node) =
    commit (L.append
      (L.map (\child -> K.InsertMember K.Structural child identity) (G.children (G.tag node)))
      (case G.binder node of {
        Nothing -> [];
        Just parent -> (:) (K.InsertMember K.Binding parent identity) []
      })) state;
  removeNode :: forall s. Session s -> (,) Int Node -> ST s (Session s);
  removeNode state ((,) identity node) =
    commit (L.append
      (L.map (\child -> K.RemoveMember K.Structural child identity) (G.children (G.tag node)))
      (case G.binder node of {
        Nothing -> [];
        Just parent -> (:) (K.RemoveMember K.Binding parent identity) []
      })) state;
  patchNodeEdges :: forall s. Int -> Node -> Node -> Session s -> ST s (Session s);
  patchNodeEdges identity old next state =
    let { before = G.children (G.tag old); after = G.children (G.tag next);
          sameChildren = L.eqList eqInt before after;
          sameBinder = G.equalMaybeInt (G.binder old) (G.binder next) } in
    if sameChildren && sameBinder then stReturn state else
    let { structural = if sameChildren then [] else
            L.append
              (L.map (\child -> K.RemoveMember K.Structural child identity) (S.missingChildren before after))
              (L.map (\child -> K.InsertMember K.Structural child identity) (S.missingChildren after before));
          binding = if sameBinder then [] else
            L.append (case G.binder old of {
              Nothing -> []; Just parent -> (:) (K.RemoveMember K.Binding parent identity) []
            }) (case G.binder next of {
              Nothing -> []; Just parent -> (:) (K.InsertMember K.Binding parent identity) []
            }) } in
    commit (L.append structural binding) state;
  patchIndexedNodes :: forall s. Session s -> [] ((,) Int Node) -> [] ((,) Int Node) -> ST s (Session s);
  patchIndexedNodes state before after = case before of {
    [] -> ST.fold addNode state after;
    (:) ((,) n old) rest -> case after of {
      [] -> ST.fold removeNode state before;
      (:) ((,) m next) tail ->
        if n < m then stBind (removeNode state ((,) n old))
          (\following -> patchIndexedNodes following rest after)
        else if n > m then stBind (addNode state ((,) m next))
          (\following -> patchIndexedNodes following before tail)
        else stBind (patchNodeEdges n old next state)
          (\following -> patchIndexedNodes following rest tail)
    }
  };
  componentCanonicalNodesVisit :: forall s. Session s -> IntMap Node -> IntSet -> [] Int ->
    ST s (Either String ((,) (IntMap Node) IntSet));
  componentCanonicalNodesVisit state seen scopes pending =
    componentVisitWork state seen scopes (L.map VisitNode pending);
  -- Work items defer each index read until its exact position after the old
  -- children/binder traversal. Captured bucket roots, never ST actions, supply
  -- the subsequent immutable node-ID list. Gen boundaries schedule no reads.
  componentVisitWork :: forall s. Session s -> IntMap Node -> IntSet -> [] Visit ->
    ST s (Either String ((,) (IntMap Node) IntSet));
  componentVisitWork state seen scopes pending = case pending of {
    [] -> ST.pureE ((,) seen scopes);
    (:) visit rest -> case visit of {
      VisitStructural identity -> stBind (readBucket K.Structural identity state)
        (\bucket -> componentVisitWork state seen scopes
          (L.append (L.map VisitNode (IS.toList bucket)) rest));
      VisitBinding identity -> stBind (readBucket K.Binding identity state)
        (\bucket -> componentVisitWork state seen scopes
          (L.append (L.map VisitNode (IS.toList bucket)) rest));
      VisitNode identity ->
        if IM.member identity seen then componentVisitWork state seen scopes rest
        else case IM.lookup identity (G.nodes (graph state)) of {
          Nothing -> ST.failE ("missing graph node " ++ showInt identity);
          Just node ->
            let { boundary = G.isGen (G.tag node);
                  connected = if boundary then rest else
                    L.append (L.map VisitNode (G.children (G.tag node)))
                      (L.append (L.map VisitNode (L.maybeToList (G.binder node)))
                        ((:) (VisitStructural identity) ((:) (VisitBinding identity) rest))) } in
            componentVisitWork state (IM.insert identity node seen)
              (if boundary then IS.insert identity scopes else scopes) connected
        }
    }
  };

  unifyProjection :: [] ((,) Int Int) -> Graph -> ScopeIndex -> IntMap Node -> IntSet ->
    Either String ((,,,) ([] ((,) Int Node)) (Rank.MapIndex Node) Int Graph);
  unifyProjection equations current scopeValue connected boundaries =
         let {
           old = current
         } in
         let {
           scopes = S.projectScopes scopeValue boundaries
         } in
         let {
           selected =
             L.foldlStrict
               (\found n ->
                  if IM.member n found then found else IM.insert n (IM.get n (G.nodes old)) found)
               connected
               (IM.keys scopes)
         } in
         let {
           originals = IM.toList selected
         } in
         let {
           count = L.length originals
         } in
         let {
           forward =
             Rank.indexMap selected
         } in
         let {
           backward = forward
         } in
         let {
           compact = \n -> S.rankIdentity (G.resolve old n) 0 forward
         } in
         let {
           hiddenRoots =
             L.filter
               (\entry ->
                  case entry of {
                    (,) n v ->
                      case G.tag v of {
                        GGen root -> L.not (IM.member root selected);
                        _ -> False
                      }
                  })
               originals
         } in
         let {
           stubIds = L.range count ((count + L.length hiddenRoots) - 1)
         } in
         let {
           stubs =
             IM.fromDistinctAscList
               (L.zip
                  (L.map
                     (\entry ->
                        case entry of {
                          (,) n v -> n
                        })
                     hiddenRoots)
                  stubIds)
         } in
         let {
           existing = S.projectCanonicalNodes forward scopes stubs 0 originals
         } in
         let {
           placeholders =
             L.map
               (\entry ->
                  case entry of {
                    (,) original stub ->
                      (,) stub (G.mkNode GBot (Just (S.rankIdentity original 0 forward)) Flexible)
                  })
               (IM.toList stubs)
         } in
         let {
           local =
             G.mkGraph (G.nodesFromDistinctAscList (L.append existing placeholders)) IM.empty
               (count + L.length hiddenRoots)
         } in
         G.bindE
           (G.unify
              (L.map
                 (\entry ->
                    case entry of {
                      (,) a b -> (,) (compact a) (compact b)
                    })
                 equations)
              local)
           (\solved ->
              G.bindE
                (G.mapE_
                   (\stub ->
                      G.check
                        (S.matchesNode (G.nodes solved) stub (G.nodeAt local stub) &&
                         (G.resolve solved stub == stub))
                        "local unification changed a hidden scope root")
                   (IM.elems stubs))
                (\checkedStubs ->
                   G.bindE (G.mapE_ (S.checkPreservedScope old solved forward scopes) originals)
                     (\checkedScopes ->
                        Right ((,,,) originals backward count solved))));

  restoreProjectionPlan :: Graph -> [] ((,) Int Node) -> Rank.MapIndex Node -> Int -> Graph ->
    Either String ((,,) Graph ([] ((,) Int Node)) ([] ((,) Int Node)));
  restoreProjectionPlan current originals backward count solved =
    G.bindE (G.mapE (S.restoreAliases backward) (IM.toList (G.links solved)))
      (\aliases ->
         let {
           originalGraph = current
         } in
         let {
           withAliases =
             G.mkGraph (G.nodes originalGraph)
               (IM.union (IM.fromDistinctAscList aliases) (G.links originalGraph))
               (G.nextId originalGraph)
         } in
         G.bindE
           (S.restoreProjectedNodes withAliases backward 0 originals
              (L.filter
                 (\entry ->
                    case entry of {
                      (,) n v -> (n < count)
                    })
                 (IM.toList (G.nodes solved))))
           (\restored ->
              case S.projectionChanges originals restored of {
                (,,) removedNodes changedNodes deleted ->
                  let {
                    retained =
                      L.foldlStrict (\ns -> \n -> IM.delete n ns) (G.nodes originalGraph) deleted
                  } in
                  let {
                    updated =
                      L.foldlStrict
                        (\ns ->
                           \entry ->
                             case entry of {
                               (,) n v -> G.insertNodeMap n v ns
                             })
                        retained
                        changedNodes
                  } in
                  let {
                    patched = G.mkGraph updated (G.links withAliases) (G.nextId originalGraph)
                  } in
                  Right ((,,) patched removedNodes changedNodes)
              }));

  restoreProjection :: forall s. Session s -> [] ((,) Int Node) -> Rank.MapIndex Node -> Int -> Graph ->
    ST s (Either String (Session s));
  restoreProjection state originals backward count solved =
    ST.bindE (stReturn (restoreProjectionPlan (graph state) originals backward count solved))
      (\((,,) patched removed changed) -> stBind (patchIndexedNodes state removed changed)
        (\indexed -> ST.pureE (withGraph patched indexed)));
  unifyDistinct :: forall s. [] ((,) Int Int) -> Session s -> ST s (Either String (Session s));
  unifyDistinct equations state =
    ST.bindE (componentCanonicalNodesVisit state IM.empty IS.empty
      (L.map (G.resolve (graph state)) (L.concatMap G.equationNodes equations)))
      (\((,) connected boundaries) ->
        ST.bindE (stReturn (unifyProjection equations (graph state) (scopeIndex state) connected boundaries))
          (\((,,,) originals backward count solved) ->
            restoreProjection state originals backward count solved));
  solverUnify :: forall s. [] ((,) Int Int) -> Session s -> ST s (Either String (Session s));
  solverUnify equations state =
    let { old = graph state;
          canonical = L.map (\((,) a b) -> (,) (G.resolve old a) (G.resolve old b)) equations } in
    ST.bindE (stReturn
      (G.mapE_ (\n -> G.check (IM.member n (G.nodes old)) ("missing graph node " ++ showInt n))
        (L.concatMap G.equationNodes canonical)))
      (\checked ->
        let { pending = L.filter (\((,) a b) -> L.not (a == b)) canonical } in
        case pending of {
          [] -> ST.pureE state;
          (:) first rest -> unifyDistinct pending state
        });
  expanded :: forall s. Int -> Int -> Session s ->
    ST s (Either String ((,,,) Int (IntMap Int) ([] ((,) Int Int)) (Session s)));
  expanded source target state =
    let { old = graph state } in
    case IM.lookup (G.resolve old source) (G.nodes old) of {
      Nothing -> ST.failE "missing instance source";
      Just sourceNode ->
        if L.not (G.isGen (G.tag sourceNode))
        then ST.failE "instance source must be a gen node"
        else case IM.lookup (G.resolve old target) (G.nodes old) of {
          Nothing -> ST.failE "missing instance target";
          Just targetNode -> case G.binder targetNode of {
            Nothing -> ST.failE "instance target has no binder";
            Just destination ->
              ST.bindE (stReturn (G.expandWithScopes (S.scopeIntervals (scopeIndex state)) source destination old))
                (\((,) ((,,) root copies frontier) next) ->
                  let { fresh = S.allocatedNodes (G.nextId old) (G.nextId next) (G.nodes next) } in
                  stBind (ST.fold addNode (withGraph next state) fresh)
                    (\indexed -> ST.pureE ((,,,) root copies frontier indexed)))
          }
        }
    };
  projectFieldUsing :: forall s. (Int -> Int -> Graph -> Either String ((,) (IntMap Int) Graph)) ->
    Int -> Int -> Session s -> ST s (Either String ((,) (IntMap Int) (Session s)));
  projectFieldUsing materialize source destination state =
    let { old = graph state; target = G.resolve old destination } in
    ST.bindE (stReturn (materialize source target old))
      (\((,) copies next) ->
        let { fresh = S.allocatedNodes (G.nextId old) (G.nextId next) (G.nodes next) } in
        stBind (removeNode state ((,) target (G.nodeAt old target)))
          (\removed -> stBind (ST.fold addNode removed ((:) ((,) target (G.nodeAt next target)) fresh))
            (\indexed -> ST.pureE ((,) copies (withGraph next indexed)))));
  projectCaseFields :: forall s. [] ((,) Int Int) -> Session s -> ST s (Either String (Session s));
  projectCaseFields fields state =
    let { current = graph state } in
    ST.bindE (stReturn
      (G.mapE (\((,) source destination) ->
        G.bindE (G.require current destination)
          (\proxy -> G.bindE
            (G.check (case G.tag proxy of {
              GGen root -> G.resolve current root == G.resolve current source &&
                L.not (G.underBinder current source destination);
              _ -> False
            }) "pattern projection requires its original external-root proxy")
            (\checked -> G.bindE (G.knownFieldInterface current source)
              (\eligible -> Right (if eligible then Just ((,) source destination) else Nothing))))) fields))
      (\classified -> case L.catMaybes classified of {
        [] -> ST.pureE state;
        selected -> ST.bindE
          (ST.foldE (\currentState ((,) source destination) ->
            ST.bindE (projectFieldUsing G.materializeFieldIn source destination currentState)
              (\answer -> ST.pureE (L.snd answer))) state selected)
          audit
      });

  freshBottomGraft :: forall s. Int -> Int -> Int -> [] ((,) Int Int) -> Session s -> ST s (Maybe (Session s));
  freshBottomGraft first originalTarget root frontier solver =
    let { current = graph solver; target = G.resolve current originalTarget } in
    if L.not (L.null frontier) || target >= first || root < first || root == target
    then stReturn Nothing
    else case IM.lookup target (G.nodes current) of {
      Nothing -> stReturn Nothing;
      Just old -> case G.tag old of {
        GBot -> freshBottomGraftKind first target root old Star solver;
        GBotK kind -> freshBottomGraftKind first target root old kind solver;
        _ -> stReturn Nothing
      }
    };

  freshBottomGraftKind :: forall s. Int -> Int -> Int -> Node -> Kind -> Session s -> ST s (Maybe (Session s));
  freshBottomGraftKind first target root old kind solver =
    let {
      current = graph solver;
      directGen = case G.binder old of {
        Nothing -> False;
        Just parent -> case IM.lookup parent (G.nodes current) of {
          Just node -> G.isGen (G.tag node) && G.equalFlag (G.flag node) Flexible;
          Nothing -> False
        }
      }
    } in
    if L.not (S.green current target) || L.not directGen
    then stReturn Nothing
    else stBind (readBucket K.Binding target solver)
      (\targetChildren -> if L.not (IS.null targetChildren) then stReturn Nothing
       else case IM.lookup root (G.nodes current) of {
      Nothing -> stReturn Nothing;
      Just source ->
        if L.not (G.equalFlag (G.flag source) Flexible) ||
           L.not (G.equalMaybeInt (G.binder source) (G.binder old))
        then stReturn Nothing
        else let {
          fresh = S.allocatedNodes first (G.nextId current) (G.nodes current);
          identities = IS.fromList (L.map L.fst fresh);
          closed = \((,) identity node) ->
            L.not (G.isGen (G.tag node)) &&
            L.all (\child -> IS.member child identities) (G.children (G.tag node)) &&
            (if identity == root then True else case G.binder node of {
              Nothing -> False;
              Just parent -> IS.member parent identities
            })
        } in
        if L.not (IS.member root identities && L.all closed fresh &&
          S.validFreshFragment root (G.binder old) fresh (G.nextId current))
        then stReturn Nothing
        else case G.kindAt current root of {
          Left _ -> stReturn Nothing;
          Right sourceKind ->
            if L.not (G.equalKind sourceKind kind)
            then stReturn Nothing
            else let {
              image = \identity -> if identity == root then target else identity;
              mergedTag = if G.isBottom (G.tag source) then G.tag old else G.tag source;
              replacement = G.mkNode (G.mapTag image mergedTag)
                (G.binder old) (G.flag old);
              descendants = L.map (\((,) identity node) ->
                (,) identity (G.mkNode (G.mapTag image (G.tag node))
                  (G.mapMaybeInt image (G.binder node)) (G.flag node)))
                (L.filter (\((,) identity _) -> identity /= root) fresh);
              updated = G.insertNodeMap target replacement
                (IM.union (G.nodesFromDistinctAscList descendants)
                  (IM.delete root (G.nodes current)));
              next = G.mkGraph updated (IM.insert root target (G.links current))
                (G.nextId current);
              before = ((:) ((,) target old) fresh);
              after = ((:) ((,) target replacement) descendants)
            } in stBind (patchIndexedNodes solver before after)
              (\indexed -> stReturn (Just (withGraph next indexed)))
        }
    });

  groundGraft :: forall s. Int -> Int -> Session s -> ST s (Maybe (Session s));
  groundGraft source destination solver =
    let {
      current = graph solver
    } in
    let {
      target = G.resolve current destination
    } in
    case IM.lookup target (G.nodes current) of {
      Nothing -> stReturn Nothing;
      Just old ->
        case G.tag old of {
          GBot -> groundGraftKind source target old Star solver;
          GBotK kind -> groundGraftKind source target old kind solver;
          _ -> stReturn Nothing
        }
    };

  groundGraftKind :: forall s. Int -> Int -> Node -> Kind -> Session s -> ST s (Maybe (Session s));
  groundGraftKind source target old kind solver =
    let {
      current = graph solver
    } in
    if L.not (S.green current target)
    then stReturn Nothing
    else case IM.lookup (G.resolve current source) (G.nodes current) of {
           Nothing -> stReturn Nothing;
           Just sourceNode ->
             case G.tag sourceNode of {
               GGen originalRoot ->
                 let {
                   root = G.resolve current originalRoot
                 } in
                 case S.groundNodes current IS.empty ((:) root []) of {
                   Nothing -> stReturn Nothing;
                   Just originals ->
                     case G.kindAt current root of {
                       Left message -> stReturn Nothing;
                       Right sourceKind ->
                         if L.not (G.equalKind sourceKind kind)
                         then stReturn Nothing
                         else let {
                                descendants = IS.toList (IS.delete root originals)
                              } in
                              let {
                                count = L.length descendants
                              } in
                              let {
                                copies =
                                  IM.insert root target
                                    (IM.fromDistinctAscList
                                       (L.zip descendants
                                          (L.range (G.nextId current)
                                             ((G.nextId current + count) - 1))))
                              } in
                              let {
                                image = \n -> IM.get (G.resolve current n) copies
                              } in
                              let {
                                replacement =
                                  G.mkNode (G.mapTag image (G.tag (G.nodeAt current root)))
                                    (G.binder old)
                                    (G.flag old)
                              } in
                              let {
                                fresh =
                                  L.map
                                    (\n ->
                                       (,) (image n)
                                         (G.mkNode (G.mapTag image (G.tag (G.nodeAt current n)))
                                            (Just target)
                                            Rigid))
                                    descendants
                              } in
                              let {
                                next =
                                  G.mkGraph
                                    (G.insertNodeMap target replacement
                                       (IM.union (G.nodesFromDistinctAscList fresh)
                                          (G.nodes current)))
                                    (G.links current)
                                    (G.nextId current + count)
                              } in
                              stBind (removeNode solver ((,) target old))
                                (\removed -> stBind
                                  (ST.fold addNode removed ((:) ((,) target replacement) fresh))
                                  (\indexed -> stReturn (Just (withGraph next indexed))))
                     }
                 };
               _ -> stReturn Nothing
             }
         };
  -- Exact seed groundGraft guard: a flexible chain must reach a Gen. Unlike a
  -- general permission query, a known bottom needs no inertness index, and a
  -- missing binder is not a S.green graft destination.

  allST :: forall s a. (a -> ST s Bool) -> [] a -> ST s Bool;
  allST predicate values = case values of {
    [] -> stReturn True;
    (:) value rest -> stBind (predicate value)
      (\accepted -> if accepted then allST predicate rest else stReturn False)
  };
  frontierGraftSource :: forall s. Int -> Int -> Int -> IntSet -> Session s -> (,) Int Int -> ST s Bool;
  frontierGraftSource first target destination identities state pair =
    stBind (frontierGraftSourceShape first target destination identities state pair)
      (\shape -> if shape then stReturn (S.sameGraftKinds (graph state) ((:) pair [])) else stReturn False);
  frontierGraftSourceShape :: forall s. Int -> Int -> Int -> IntSet -> Session s -> (,) Int Int -> ST s Bool;
  frontierGraftSourceShape first target destination identities state ((,) original proxy) =
    let { current = graph state } in
    if original < first && original /= target && IS.member proxy identities then
    case IM.lookup original (G.nodes current) of {
      Nothing -> stReturn False;
      Just source -> case IM.lookup proxy (G.nodes current) of {
        Nothing -> stReturn False;
        Just copy ->
          if L.not (L.not (G.isGen (G.tag source)) && G.isBottom (G.tag copy) &&
            (L.not (G.isBottom (G.tag source)) || G.equalTag (G.tag source) (G.tag copy)) &&
            G.equalFlag (G.flag copy) Flexible &&
            G.equalMaybeInt (G.binder copy) (Just destination))
          then stReturn False else
          stBind (readBucket K.Binding proxy state)
            (\children -> if L.not (IS.null children) then stReturn False else
              stBind (readBucket K.Structural proxy state)
                (\parents -> stReturn
                  (L.all (\parent -> parent >= first) (IS.toList parents) &&
                   IS.notMember target (G.reachableVisit current IS.empty ((:) original [])) &&
                   (case G.binder source of {
                     Nothing -> False;
                     Just parent -> case IM.lookup parent (G.nodes current) of {
                       Nothing -> False;
                       Just scope -> G.isGen (G.tag scope) && G.equalFlag (G.flag scope) Flexible &&
                         S.scopeContains (scopeIndex state) parent destination
                     }
                   }))))
      }
    } else stReturn False;
  frontierIdentityGraft :: forall s. Int -> Int -> Int -> [] ((,) Int Int) -> Session s -> ST s (Maybe (Session s));
  frontierIdentityGraft first originalTarget root frontier state =
    let { current = graph state; target = G.resolve current originalTarget } in
    case frontier of {
      (:) ((,) original proxy) [] ->
        if original /= target || proxy /= root || root < first || target >= first
        then stReturn Nothing else case IM.lookup target (G.nodes current) of {
          Nothing -> stReturn Nothing;
          Just old -> case G.binder old of {
            Nothing -> stReturn Nothing;
            Just destination -> case IM.lookup destination (G.nodes current) of {
              Nothing -> stReturn Nothing;
              Just scope -> case S.allocatedNodes first (G.nextId current) (G.nodes current) of {
                (:) ((,) identity copy) [] ->
                  if identity /= root || G.isGen (G.tag old) ||
                     L.not (G.isGen (G.tag scope) && G.equalFlag (G.flag scope) Flexible &&
                       G.isBottom (G.tag copy) && G.equalFlag (G.flag copy) Flexible &&
                       G.equalMaybeInt (G.binder copy) (Just destination) &&
                       (L.not (G.isBottom (G.tag old)) || G.equalTag (G.tag old) (G.tag copy)))
                  then stReturn Nothing else
                  stBind (readBucket K.Structural root state)
                    (\parents -> if L.not (IS.null parents) then stReturn Nothing else
                      stBind (readBucket K.Binding root state)
                        (\children -> if L.not (IS.null children &&
                          S.validFreshFragment root (Just destination) ((:) ((,) root copy) []) (G.nextId current))
                        then stReturn Nothing else case G.kindAt current target of {
                          Left _ -> stReturn Nothing;
                          Right kind -> case G.kindAt current root of {
                            Left _ -> stReturn Nothing;
                            Right proxyKind ->
                              if L.not (G.equalKind kind proxyKind) then stReturn Nothing else
                              let { next = G.mkGraph (IM.delete root (G.nodes current))
                                      (IM.insert root target (G.links current)) (G.nextId current) } in
                              stBind (patchIndexedNodes state ((:) ((,) root copy) []) [])
                                (\indexed -> stReturn (Just (withGraph next indexed)))
                          }
                        }));
                _ -> stReturn Nothing
              }
            }
          }
        };
      _ -> stReturn Nothing
    };
  frontierBottomGraft :: forall s. Int -> Int -> Int -> [] ((,) Int Int) -> Session s -> ST s (Maybe (Session s));
  frontierBottomGraft first originalTarget root frontier state =
    let { current = graph state; target = G.resolve current originalTarget } in
    case IM.lookup target (G.nodes current) of {
      Nothing -> stReturn Nothing;
      Just old -> case G.binder old of {
        Nothing -> stReturn Nothing;
        Just destination -> case IM.lookup destination (G.nodes current) of {
          Nothing -> stReturn Nothing;
          Just scope ->
            if L.null frontier || target >= first || root < first ||
               L.not (G.isBottom (G.tag old) && G.equalFlag (G.flag old) Flexible &&
                 G.isGen (G.tag scope) && G.equalFlag (G.flag scope) Flexible)
            then stReturn Nothing else
            stBind (readBucket K.Binding target state)
              (\children -> if L.not (IS.null children) then stReturn Nothing
                else frontierBottomGraftIn first target destination root old frontier state)
        }
      }
    };

  frontierBottomGraftIn :: forall s. Int -> Int -> Int -> Int -> Node -> [] ((,) Int Int) -> Session s -> ST s (Maybe (Session s));
  frontierBottomGraftIn first target destination root old frontier solver =
    let {
      current = graph solver;
      fresh = S.allocatedNodes first (G.nextId current) (G.nodes current);
      identities = IS.fromList (L.map L.fst fresh);
      proxies = IM.fromList (L.map (\((,) original proxy) -> (,) proxy original) frontier);
      closed = \((,) identity node) ->
        L.not (G.isGen (G.tag node)) &&
        L.all (\child -> IS.member child identities) (G.children (G.tag node)) &&
        (case G.binder node of {
          Nothing -> False;
          Just parent -> parent == destination || IS.member parent identities
        });
      rootOriginal = IM.lookup root proxies;
      rootAllowed = case rootOriginal of {
        Nothing -> True;
        Just original -> original < target && L.length fresh == 1 &&
          (case IM.lookup original (G.nodes current) of {
            Nothing -> False;
            Just node -> L.not (G.isBottom (G.tag node)) || G.equalTag (G.tag node) (G.tag old)
          })
      }
    } in
    if L.not (IS.member root identities && IM.size proxies == L.length frontier &&
      rootAllowed && L.all closed fresh &&
      G.equalMaybeInt (G.binder (G.nodeAt current root)) (Just destination) &&
      G.equalFlag (G.flag (G.nodeAt current root)) Flexible &&
      S.validFreshFragment root (Just destination) fresh (G.nextId current))
    then stReturn Nothing
    else stBind (allST (frontierGraftSource first target destination identities solver) frontier)
      (\sourcesOkay -> if L.not sourcesOkay then stReturn Nothing else case G.kindAt current root of {
      Left _ -> stReturn Nothing;
      Right kind -> case G.kindAt current target of {
        Left _ -> stReturn Nothing;
        Right expected ->
          if L.not (G.equalKind kind expected) then stReturn Nothing else
          stBind (case rootOriginal of {
            Nothing -> stReturn IS.empty;
            Just ignored -> readBucket K.Structural target solver
          }) (\capturedParents ->
          let {
            aliases = case rootOriginal of {
              Nothing -> IM.insert root target proxies;
              Just original -> IM.insert target original proxies
            };
            image = \identity -> IM.findWithDefault identity identity aliases;
            rewrite = \node -> G.mkNode (G.mapTag image (G.tag node))
              (G.mapMaybeInt image (G.binder node)) (G.flag node);
            descendants = L.map (\((,) identity node) -> (,) identity (rewrite node))
              (L.filter (\((,) identity _) -> IM.notMember identity aliases) fresh);
            parents = case rootOriginal of {
              Nothing -> [];
              Just _ -> L.map (\identity -> (,) identity (G.nodeAt current identity))
                (IS.toList capturedParents)
            };
            replacement = case rootOriginal of {
              Just _ -> [];
              Nothing -> (:) ((,) target (G.mkNode
                (G.mapTag image (G.tag (G.nodeAt current root))) (G.binder old) (G.flag old))) []
            };
            before = IM.fromList (L.append ((:) ((,) target old) fresh) parents);
            after = IM.fromList (L.append replacement
              (L.append descendants (L.map (\((,) identity node) -> (,) identity (rewrite node)) parents)));
            removed = L.foldlStrict (\nodes identity -> IM.delete identity nodes)
              (G.nodes current) (IM.keys aliases);
            next = G.mkGraph (IM.union after removed)
              (IM.union aliases (G.links current)) (G.nextId current);
            beforeEntries = IM.toList before;
            afterEntries = IM.toList after
          } in stBind (patchIndexedNodes solver beforeEntries afterEntries)
            (\indexed -> stReturn (Just (withGraph next indexed))))
      }
    });

  congruentExpansionGraft :: forall s. Int -> Int -> Int -> [] ((,) Int Int) -> Session s -> ST s (Maybe (Session s));
  congruentExpansionGraft first originalTarget root frontier solver =
    let { current = graph solver; target = G.resolve current originalTarget;
      fresh = S.allocatedNodes first (G.nextId current) (G.nodes current);
      identities = IS.fromList (L.map L.fst fresh);
      proxies = IM.fromList (L.map (\((,) original proxy) -> (,) proxy original) frontier)
    } in
    case IM.lookup target (G.nodes current) of {
      Nothing -> stReturn Nothing;
      Just old -> case G.binder old of {
        Nothing -> stReturn Nothing;
        Just destination -> case IM.lookup destination (G.nodes current) of {
          Nothing -> stReturn Nothing;
          Just scope ->
            if L.not (G.isGen (G.tag scope) && G.equalFlag (G.flag scope) Flexible &&
              L.all (\((,) identity node) -> L.not (G.isGen (G.tag node)) &&
                L.all (\child -> IS.member child identities) (G.children (G.tag node)) &&
                (case G.binder node of { Nothing -> False; Just parent -> parent == destination || IS.member parent identities })) fresh)
            then stReturn Nothing else
            case S.congruentExpansionMap current first proxies ((:) ((,) root target) []) of {
              Nothing -> stReturn Nothing;
              Just images ->
                if IM.size images /= L.length fresh ||
                   L.not (S.validFreshFragment root (Just destination) fresh (G.nextId current))
                then stReturn Nothing else
                stBind (allST (frontierGraftSourceShape first target destination identities solver) frontier)
                  (\sourcesOkay -> if L.not sourcesOkay then stReturn Nothing else
                let { image = \identity -> IM.findWithDefault identity identity images;
                  permitted = \identity -> G.equalFlag (G.flag (G.nodeAt current identity)) Rigid || S.green current identity;
                  exact = \((,) identity node) ->
                    if IM.member identity proxies then True else
                    let { destination = IM.get identity images; old = G.nodeAt current destination } in
                    G.equalMaybeInt (G.mapMaybeInt image (G.binder node)) (G.binder old) &&
                    (G.equalFlag (G.flag node) Flexible || G.equalFlag (G.flag old) Rigid) &&
                    permitted identity && permitted destination &&
                    (if G.isBottom (G.tag node) then S.green current identity
                     else G.equalTag (G.mapTag image (G.tag node)) (G.tag old))
                } in
                if L.not (L.all exact fresh) ||
                   L.not (S.sameGraftKinds current (IM.toList images))
                then stReturn Nothing
                else let {
                  remaining = L.foldlStrict (\nodes identity -> IM.delete identity nodes) (G.nodes current) (IM.keys images);
                  next = G.mkGraph remaining (IM.union images (G.links current)) (G.nextId current);
                  removed = fresh
                } in stBind (patchIndexedNodes solver removed [])
                  (\indexed -> stReturn (Just (withGraph next indexed))))
            }
        }
      }
    };

  expansionBottomGraft :: forall s. Int -> Int -> Int -> [] ((,) Int Int) -> Session s -> ST s (Maybe (Session s));
  expansionBottomGraft first target root frontier state =
    stBind (if L.null frontier then freshBottomGraft first target root frontier state
      else stBind (frontierIdentityGraft first target root frontier state)
        (\answer -> case answer of {
          Just grafted -> stReturn (Just grafted);
          Nothing -> frontierBottomGraft first target root frontier state
        }))
      (\direct -> case direct of {
        Just grafted -> stReturn (Just grafted);
        Nothing -> congruentExpansionGraft first target root frontier state
      });
  instantiateWithFreshBottom :: forall s. Int -> Int -> Session s -> ST s (Either String (Session s));
  instantiateWithFreshBottom source target state =
    let { oldGraph = graph state } in
    ST.bindE (expanded source target state)
      (\((,,,) root copies frontier next) ->
        stBind (expansionBottomGraft (G.nextId oldGraph) target root frontier next)
          (\answer -> case answer of {
            Just grafted -> ST.pureE grafted;
            Nothing -> solverUnify (L.append frontier ((:) ((,) root target) [])) next
          }));
  instantiateClosed :: forall s. Int -> Int -> Session s -> ST s (Either String (Session s));
  instantiateClosed source target state =
    stBind (groundGraft source target state)
      (\answer -> case answer of {
        Just grafted -> ST.pureE grafted;
        Nothing -> if S.groundInstance (graph state) source target
          then ST.pureE state else instantiateWithFreshBottom source target state
      });

}
