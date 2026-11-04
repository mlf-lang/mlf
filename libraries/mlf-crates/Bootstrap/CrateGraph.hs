-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.CrateGraph where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.SourceInference as Source;
  import qualified Bootstrap.InferenceUnit as Inference;
  import qualified Bootstrap.CrateQuery as Q;
  import qualified Bootstrap.QueryGraph as G;
  import qualified Bootstrap.OpenFragment as Open;
  import qualified Bootstrap.Bitstream as W;
  import qualified Bootstrap.ArtifactStructure as A;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.Evidence as Evidence;
  import qualified Bootstrap.EvidenceBoundary as Boundary;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.IndexVec as V;

  data State = State G.Session Source.CheckedContracts
    (Map String Open.Environment) ([] ((,,) String Open.Fragment ([] (V.Index Declaration)))) Int Int ([] Q.GroupResult) (Maybe IntArray);
  bindingKey scope i = G.key "Binding" (Source.declStable scope i);
  requireBindings scope ids = requireNodes (map (bindingKey scope) ids);
  -- In-memory SCC queries use the full ordered member list. Packing its
  -- stable definitions is the boundary to the generation and receipt formats.
  data GroupQuery = PreparedQuery | ScopeInventoryQuery | ScopeQuery | InferQuery | FinishQuery;
  groupQueryKind :: GroupQuery -> String;
  groupQueryKind kind = case kind of {
    PreparedQuery -> "Prepared"; ScopeInventoryQuery -> "ScopeInventory";
    ScopeQuery -> "Scope"; InferQuery -> "InferScc"; FinishQuery -> "FinishScc"
  };
  groupIdentity slots = Separate.pack (map (Source.declStable (Source.slotScope slots)) (Source.memberIds slots));
  groupKey kind slots = G.key (groupQueryKind kind) (groupIdentity slots);
  datatypeKey name = G.key "Datatype" name;
  contractValue contract = W.VNode 420
    [A.toXType (Separate.normalType (Source.contractType contract)),
     A.toList A.toText (Source.contractClasses contract),A.toBool (Source.contractProtected contract)];
  -- Each input is refreshed once from current source/checked metadata. Derived
  -- nodes have explicit edges back to that authority, including empty scopes.
  input identity value session = G.record (G.inputKey identity) [] False value session;
  recordInitialBindings scope values session = case values of {
    [] -> ioReturn (Right session);
    (:) ((,) i contract) rest -> do {
      observed <- input (bindingKey scope i) (contractValue contract) session;
      case observed of { Left e -> ioReturn (Left e); Right ((,) leaf next) -> do {
        recorded <- G.record (bindingKey scope i) [G.edge leaf] True (contractValue contract) next;
        case recorded of { Left e -> ioReturn (Left e); Right ((,) _ final) -> recordInitialBindings scope rest final }
      } }
    }
  };
  recordDatatypes values session = case values of {
    [] -> ioReturn (Right session);
    (:) declaration rest -> do {
      let { wanted = datatypeKey (D.datatypeName declaration); value = Open.declarationValue declaration };
      observed <- input wanted value session;
      case observed of { Left e -> ioReturn (Left e); Right ((,) leaf next) -> do {
        recorded <- G.record wanted [G.edge leaf] True value next;
        case recorded of { Left e -> ioReturn (Left e); Right ((,) _ final) -> recordDatatypes rest final }
      } }
    }
  };
  requireNodes wanted session = traverseEither (\identity ->
    case M.lookup compareString identity (G.currentNodes session) of {
      Just node -> Right node; Nothing -> Left ("query dependency is not available: " ++ identity)
    }) wanted;
  candidateMetadata protected ((,,) role name _) = Q.node "candidate"
    [Q.encodeRole role,name,Q.boolean (elem eqString name protected)];
  preparedValue slots prepared = let {
    table = Q.referenceTable slots prepared; member = compose Q.encodeMember (Q.referenceMember table);
    token = Q.referenceToken table;
    candidate protected ((,,) role n _) = Q.node "candidate"
      [Q.encodeRole role,token n,Q.boolean (elem eqString n protected)]
  } in W.VNode 421 [W.VText "prepared-declarations-1", A.toList A.toText (Q.referenceDefinitions table),
    W.VText (Q.list member (Source.groupOriginal prepared)), W.VText (Q.list member (Source.groupMembers prepared)),
    A.toList A.toText (Q.sourceGroupMetadataWith token candidate prepared)];
  scopeInventory prepared = case Source.groupAuthority prepared of {
    Nothing -> W.VNode 422 [];
    Just (Source.RootAuthority _ _ _ candidates protected) -> W.VNode 422
      (map (\candidate -> W.VText (candidateMetadata protected candidate)) candidates)
  };
  scopeValue prepared dependencies = W.VNode 423
    [scopeInventory prepared,A.toList (A.toPair A.toText A.toText) (map G.edge dependencies)];
  rawValue references group fragment = W.VNode 425
    [A.toList (A.toPair A.toText A.toText) references,Open.encodeBody "raw" group fragment];
  compile verify crateId compilerHash cacheDir imports protected originalPlan =
    case do {
      plan <- Source.initializeProtection originalPlan protected;
      inventory <- Q.prepareData (Source.planData plan);
      types <- foldM Inference.mergeExternal M.empty (concatMap Separate.unitBindings imports);
      contracts <- Source.initialContracts plan types protected;
      let { scope = Source.planScope plan (M.keys contracts) };
      checked <- Source.installContracts scope contracts;
      steps <- Source.querySteps plan scope;
      Right ((,,,) plan inventory checked steps)
    } of {
      Left e -> ioReturn (Left e);
      Right ((,,,) plan inventory checked steps) -> start verify crateId compilerHash cacheDir
        "source" inventory (Source.planData plan) checked steps
    };
  -- The already-lowered fallback has no unsigned-root evidence finalization.
  -- It still uses the same open bodies, dependency graph and crate transaction.
  -- Preserve its existing conservative (protected, no source-class slots)
  -- calling contract, including mixed source/dictionary recursive groups.
  compileLowered verify crateId compilerHash cacheDir imports datatypes members =
    compileLoweredIn (Dependency.BoundValues (Dependency.symbols []) [])
      verify crateId compilerHash cacheDir imports datatypes members;
  compileLoweredIn (Dependency.BoundValues base source) verify crateId compilerHash cacheDir imports datatypes members =
    case do {
      groups <- Dependency.declarationGroups members;
      inventory <- Q.prepareData datatypes;
      types <- foldM Inference.mergeExternal M.empty (concatMap Separate.unitBindings imports);
      let { contracts = M.map (\ty -> Source.SourceContract ty [] True) types;
        values = M.fromList compareString (map (\m@((,,) name _ _) -> (,) name m) members) };
      let { sourceIds = map Dependency.boundId source;
        locals = S.fromList compareString (map (Dependency.symbolName base) sourceIds);
        extra = filter (\n -> not (S.member compareString n locals)) (map Source.sourceName members);
        all = Dependency.extendSymbols base extra;
        generated = map V.fromInt (range (V.count (Dependency.symbolNodes base)) (V.count (Dependency.symbolNodes all) - 1));
        scope = Source.declarationScope all (append sourceIds generated) [] (M.keys contracts) };
      checked <- Source.installContracts scope contracts;
      steps <- traverseEither (\names -> mapEither (\ids -> (,) ids (\current -> prepareLowered values current names))
        (traverseEither (Source.requireDecl scope) names)) groups;
      Right ((,,) steps inventory checked)
    } of {
      Left e -> ioReturn (Left e);
      Right ((,,) steps inventory checked) -> start verify crateId compilerHash cacheDir
        "lowered" inventory datatypes checked steps
    };
  prepareLowered :: Map String ((,,) String (Maybe SAnnotation) SExpr) ->
    Map String Source.SourceContract -> [] String -> Either String Source.PreparedGroup;
  prepareLowered values contracts names = do {
    members <- traverseEither (\name -> case M.lookup compareString name values of {
      Just member -> Right member; Nothing -> Left "lowered query member disappeared"
    }) names;
    Right (Source.PreparedGroup members members [] M.empty
      (map (\name -> (,,) name [] True) names) Nothing [])
  };
  start verify crateId compilerHash cacheDir flavor inventory datatypes contracts groups = do {
        statistics <- G.profile;
        graphStarted <- G.clock statistics;
        auditSetting <- getEnv "MLF_QUERY_SEMANTIC_AUDIT";
        started <- G.begin (cacheDir ++ "/query-graph-v1")
          (Separate.pack [crateId,compilerHash,Q.sourceQueryFormat,"open-fragment-checker-1/finish-receipt-1",flavor]);
        case started of { Left e -> ioReturn (Left e); Right session -> do {
          initial <- case contracts of { Source.CheckedContracts scope indexed _ ->
            recordInitialBindings scope (M.toList indexed) session };
          case initial of { Left e -> ioReturn (Left e); Right first -> do {
            loaded <- recordDatatypes datatypes first;
            case loaded of { Left e -> ioReturn (Left e); Right ready -> do {
              G.elapsed statistics 0 graphStarted;
              runGroups verify (eqString auditSetting "1") crateId inventory groups
                (State ready contracts M.empty [] 0 0 [] statistics)
            } }
          } }
        } }
    };
  runGroups verify audit crateId inventory groups state = case groups of {
    [] -> ioReturn (Right state);
    (:) ((,) owners prepare) rest -> case state of {
      State session contracts contexts objects inferred reused reports statistics ->
        let { scope = Source.checkedScope contracts; names = map (Source.declName scope) owners } in
        case bindEither (prepare (Source.checkedNamed contracts)) (Source.slotPrepared contracts owners) of {
          Left e -> ioReturn (Left e);
          Right ((,) slots prepared) -> do {
            let { declarations = Q.requiredDataIn inventory (Source.groupMembers prepared)
                    (append (Source.groupBindings prepared) (Source.groupCandidateBindings prepared));
              group = Q.groupName crateId names;
              rawKey = groupKey InferQuery slots };
            graphStarted <- G.clock statistics;
            source <- input (groupKey PreparedQuery slots) (preparedValue slots prepared) session;
            case source of { Left e -> ioReturn (Left e); Right ((,) sourceNode first) -> do {
              scopeInput <- input (groupKey ScopeInventoryQuery slots) (scopeInventory prepared) first;
              case scopeInput of { Left e -> ioReturn (Left e); Right ((,) scopeLeaf second) ->
                case do {
                  candidateNodes <- requireBindings scope (Source.candidateIds slots) second;
                  bindingNodes <- requireBindings scope (Source.parameterIds slots) second;
                  dataNodes <- requireNodes (map (compose datatypeKey D.datatypeName) declarations) second;
                  Right ((,,) candidateNodes bindingNodes dataNodes)
                } of {
                  Left e -> ioReturn (Left e);
                  Right ((,,) candidateNodes bindingNodes dataNodes) -> do {
                    scoped <- G.record (groupKey ScopeQuery slots)
                      ((:) (G.edge scopeLeaf) (map G.edge candidateNodes)) True
                      (scopeValue prepared candidateNodes) second;
                    case scoped of { Left e -> ioReturn (Left e); Right ((,) scopeNode third) -> do {
                      let { dataIdentity = Separate.pack (map G.nodeHash dataNodes);
                        environment = case M.lookup compareString dataIdentity contexts of {
                          Just env -> Right env; Nothing -> Open.environment declarations } };
                      case environment of { Left e -> ioReturn (Left e); Right env -> do {
                        let { currentContexts = M.insert compareString dataIdentity env contexts;
                          references = append (map G.edge bindingNodes) (map G.edge dataNodes);
                          reads = append [G.edge sourceNode,G.edge scopeNode] references;
                          validated = G.validate rawKey third;
                          previous = fst validated; active = snd validated };
                        seq previous (G.elapsed statistics 0 graphStarted);
                        loadStarted <- G.clock statistics;
                        cached <- case previous of {
                          Nothing -> ioReturn (Left "query is dirty");
                          Just node -> case G.nodePayload node of {
                            Nothing -> ioReturn (Left "query result is absent");
                            Just digest -> do {
                              loaded <- Open.decodeTrustedIds (G.payloadPath active digest) digest references "raw" group env
                                (Source.expectedParameters slots prepared) (zip owners names);
                              case loaded of {
                                Left e -> ioReturn (Left e);
                                Right fragment -> do {
                                  fingerprint <- if verify then G.hashValue (rawValue references group fragment)
                                    else ioReturn (Right digest);
                                  ioReturn (do {
                                    actual <- fingerprint;
                                    ensure (eqString actual digest) "source query ICH verification failed";
                                    if audit then do {
                                      checked <- Open.audit fragment;
                                      Source.validatePreparedOpen slots prepared checked;
                                      Right checked
                                    } else Right fragment
                                  })
                                }
                              }
                            }
                          }
                        };
                        seq cached (G.elapsed statistics 1 loadStarted);
                        inferStarted <- G.clock statistics;
                        let { hit = case cached of { Right _ -> True; Left _ -> False };
                          raw = case cached of {
                            Right fragment -> Right fragment;
                            Left _ -> do {
                              fragment <- Inference.compileOpenGroup group
                                [Q.dependencyInterface (Source.groupBindings prepared)] declarations (Source.groupMembers prepared);
                              canonical <- Source.canonicalOpen fragment;
                              Source.validatePreparedOpen slots prepared canonical;
                              Right canonical
                            }
                          } };
                        case raw of { Left e -> ioReturn (Left e); Right fragment -> do {
                          recorded <- if hit then case previous of {
                            Just node -> ioReturn (Right ((,) node active));
                            Nothing -> ioReturn (Left "missing validated source query")
                          } else G.record rawKey reads True (rawValue references group fragment) active;
                          G.elapsed statistics 2 inferStarted;
                          finishStarted <- G.clock statistics;
                          case recorded of { Left e -> ioReturn (Left e); Right ((,) rawNode fourth) ->
                            case Source.prepareOpenFinish slots contracts prepared fragment of {
                              Left e -> ioReturn (Left e);
                              Right finish -> do {
                                evidence <- resolveRequests env slots ((:) (G.edge scopeNode) (map G.edge dataNodes))
                                  (Source.openFinishRequests finish) fourth;
                                case evidence of { Left e -> ioReturn (Left e); Right ((,,) answers evidenceReads afterEvidence) ->
                                case Source.completeOpenFinish contracts finish answers of {
                                Left e -> ioReturn (Left e);
                                Right (Source.OpenFinalGroup body delta) -> do {
                                let { final = Source.openFinalObject fragment body };
                                case bindEither (Source.finalParameterIds slots contracts final)
                                  (\ids -> requireBindings scope ids afterEvidence) of {
                                Left e -> ioReturn (Left e);
                                Right finalBindings -> do {
                                let { bindingEdges = map G.edge finalBindings;
                                  finalRefs = append bindingEdges (map G.edge dataNodes);
                                  reads = append [G.edge rawNode,G.edge sourceNode,G.edge scopeNode]
                                    (append evidenceReads bindingEdges) };
                                content <- finishContentHash (verify || audit) group body final rawNode references finalRefs;
                                supplied <- case content of { Left e -> ioReturn (Left e); Right hash ->
                                  recordFinish slots group hash delta reads afterEvidence };
                                case supplied of { Left e -> ioReturn (Left e); Right next -> do {
                                    G.elapsed statistics 3 finishStarted;
                                    runGroups verify audit crateId inventory rest
                                      (State next (Source.publishContracts contracts delta) currentContexts
                                        ((:) ((,,) group final (map fst delta)) objects)
                                        (inferred + if hit then 0 else 1) (reused + if hit then 1 else 0)
                                        ((:) (Q.GroupResult group names hit
                                          (Separate.fingerprint (Q.list Q.encodeSourceContract (map (\((,) i c) -> (,) (Source.declName scope i) c) (sortedDelta slots delta))))
                                          (G.nodeHash rawNode)) reports) statistics)
                                  } }
                                }
                                }
                                }
                                } }
                              }
                            }
                          }
                        } }
                      } }
                    } }
                  }
                }
              }
            } }
          }
        }
    }
  };
  -- One canonical content address for a fragment and its ordered environment,
  -- regardless of how it was produced. KeepRawBody proves the body is exactly
  -- the one obtained from InferScc. A changed environment invalidates reuse.
  finishContentHash recheck group body final rawNode rawRefs finalRefs =
    let { same = case body of {
      Source.KeepRawBody -> eqList (eqPair eqString eqString) rawRefs finalRefs;
      Source.AdaptedBody _ -> False
    }; rawHash = G.nodeHash rawNode } in
    if same && not recheck then ioReturn (Right rawHash) else do {
      hashed <- G.hashValue (rawValue finalRefs group final);
      ioReturn (do { digest <- hashed;
        ensure (not same || eqString digest rawHash) "retained final fragment SHA mismatch";
        Right digest })
    };
  -- The generation binds the FinishScc key and ordered reads to this small
  -- value. Reconstruct it from current checked results, so neither a swapped
  -- receipt nor a stale index row can supply a result hash. Exported contracts
  -- share the very bytes subsequently published by their Binding nodes.
  sortedDelta slots = sortBy (\a b -> compareString (Source.declName (Source.slotScope slots) (fst a))
    (Source.declName (Source.slotScope slots) (fst b)));
  recordFinish slots group fragmentHash delta reads session = do {
    encoded <- mapM (\((,) i contract) -> do {
      result <- G.encodeHashed (contractValue contract);
      ioReturn (mapEither (\((,) digest bytes) -> (,,) i digest bytes) result)
    }) (sortedDelta slots delta);
    case sequenceEither encoded of { Left e -> ioReturn (Left e); Right entries -> do {
      let { scope = Source.slotScope slots; contracts = map (\((,,) i digest _) -> (,) (Source.declName scope i) digest) entries;
        receipt = W.VNode 427 [W.VText group,W.VText fragmentHash,A.toList (A.toPair A.toText A.toText) contracts];
        binding dependency current ((,,) i digest bytes) = snd (G.recordDigest (bindingKey scope i)
          [dependency] (Just digest) digest (Just bytes) current) };
      recorded <- G.record (groupKey FinishQuery slots) reads True receipt session;
      ioReturn (mapEither (\((,) finish next) -> foldlStrict (binding (G.edge finish)) next entries) recorded)
    } }
  };
  checkedResult (State session contracts _ objects inferred reused reports _) =
    (,,,) (reverse objects) (Q.QueryReport inferred reused (reverse reports)) contracts session;
  result state = case checkedResult state of { (,,,) fragments report contracts session ->
    (,,,) (map (\((,,) n f _) -> (,) n f) fragments) report (Source.checkedNamed contracts) session
  };
  statistics (State _ _ _ _ _ _ _ stats) = stats;
  data EvidenceQuery = EvidenceQuery Source.GroupSlots Int XType;
  evidenceKey (EvidenceQuery slots site goal) = G.key "Evidence"
    (Separate.pack [groupIdentity slots,showInt site,Pretty.prettyType (Separate.normalType goal)]);
  -- Resolve the checked boundary's candidate binders once, in the exact
  -- declared order. Negative identities in the payload are evidence-local
  -- ordinals, never the compilation's numeric declaration slots.
  evidenceNames slots candidates = do {
    let { ids = Source.candidateIds slots; scope = Source.slotScope slots };
    ensure (length ids == length candidates) "evidence candidate inventory changed";
    traverseEither (\((,) index ((,) i candidate)) -> do {
      let { name = Boundary.candidateName candidate; stable = Source.declStable scope i };
      ensure (eqString (X.nameHint name) (Source.declName scope i)) "evidence candidate declaration mismatch";
      Right ((,) name (XName (0 - index - 1) stable))
    }) (zip (range 0 (length ids - 1)) (zip ids candidates))
  };
  evidenceValue goal references aliases answer = let {
    names = M.fromList X.compareName aliases;
    canonical = mapOptional (Separate.mapTerm (\n -> M.findWithDefault X.compareName n n names) (\a -> a)) answer
  } in W.VNode 426 [A.toXType (Separate.normalType goal),
    A.toList (A.toPair A.toText A.toText) references,A.toMaybe A.toXTerm canonical];
  decodeEvidence graph goal references aliases = do {
    root <- case W.graphRoots graph of { [root] -> Right root; _ -> Left "evidence root count" };
    value <- W.lookupGraphNode graph root;
    case value of {
      W.GNode 426 [g,rs,p] -> do {
        savedGoal <- A.fromGraphXType graph g;
        ensure (T.alphaEq savedGoal goal) "evidence goal changed";
        raw <- A.decodeGraphValue (A.ShapeList (A.ShapePair A.ShapeText A.ShapeText)) graph rs;
        savedReferences <- A.expectList (A.expectPair A.expectText A.expectText) raw;
        ensure (eqList (eqPair eqString eqString) savedReferences references) "evidence environment changed";
        decoded <- A.decodeGraphValue (A.ShapeMaybe A.ShapeXTerm) graph p;
        proof <- A.expectMaybe A.expectXTerm decoded;
        let { replacements = M.fromList X.compareName (map (\((,) a b) -> (,) b a) aliases) };
        Right (mapOptional (Separate.mapTerm (\n -> M.findWithDefault X.compareName n n replacements) (\a -> a)) proof)
      };
      _ -> Left "invalid stable evidence record"
    }
  };
  resolveRequests env slots dependencies requests session = case requests of {
    [] -> ioReturn (Right ((,,) [] [] session));
    (:) ((,,) ordinal goal candidates) rest -> case evidenceNames slots candidates of {
      Left e -> ioReturn (Left e); Right aliases -> do {
      let { wanted = evidenceKey (EvidenceQuery slots ordinal goal);
        validated = G.validate wanted session; previous = fst validated; current = snd validated };
      cached <- case previous of {
        Nothing -> ioReturn (Left "dirty evidence query");
        Just node -> case G.nodePayload node of {
          Nothing -> ioReturn (Left "missing evidence payload");
          Just digest -> do {
            read <- G.readValue (G.payloadPath current digest) (Just digest);
            ioReturn (bindEither read (\graph -> decodeEvidence graph goal dependencies aliases))
          }
        }
      };
      let { answer = case cached of {
        Right value -> Right value;
        Left _ -> case Evidence.resolveDictionaryDetailed (Open.dataEnvironment env) M.empty
          (map Boundary.candidateTriple candidates) goal of {
          Left (Evidence.NoEntailment _) -> Right Nothing;
          Left (Evidence.InvalidEvidence message) -> Left message;
          Right proof -> Right (Just proof)
        }
      } };
      case answer of { Left e -> ioReturn (Left e); Right proof -> do {
        recorded <- case cached of {
          Right _ -> case previous of {
            Just node -> ioReturn (Right ((,) node current));
            Nothing -> ioReturn (Left "evidence validation invariant")
          };
          Left _ -> G.record wanted dependencies True (evidenceValue goal dependencies aliases proof) current
        };
        case recorded of { Left e -> ioReturn (Left e); Right ((,) node next) -> do {
          tail <- resolveRequests env slots dependencies rest next;
          ioReturn (mapEither (\((,,) answers edges final) ->
            (,,) ((:) ((,) ordinal proof) answers) ((:) (G.edge node) edges) final) tail)
        } }
      } }
    } }
  };
  -- The standalone source-root boundary publishes only after every SCC has
  -- completed. CrateSession uses compile/result and owns the later IO boundary.
  compileSourceGroups verify crateId directory imports protected plan = do {
    let { cache = Q.cachePath directory };
    code <- Q.cacheCommand ["/bin/mkdir","-p",cache];
    if code /= 0 then ioReturn (Left "cannot create source query directory") else do {
      lock <- acquireFileLock (cache ++ "/.lock");
      computed <- catchIOError (do {
        executable <- getExecutablePath;
        compiler <- fileDigest executable;
        run <- compile verify crateId compiler cache imports protected plan;
        case run of { Left e -> ioReturn (Left e); Right state -> case result state of {
          (,,,) objects report contracts session -> do {
            published <- G.publish session;
            ioReturn (mapEither (\_ -> (,,) objects report contracts) published)
          }
        } }
      }) (\e -> ioReturn (Left (textFromChars (ioeGetErrorString e))));
      releaseFileLock lock;
      ioReturn computed
    }
  }
}
