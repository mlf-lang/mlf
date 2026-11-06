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

  data State = State G.Session (Map String Source.SourceContract)
    (Map String Open.Environment) ([] ((,) String Open.Fragment)) Int Int ([] Q.GroupResult) (Maybe IntArray);
  bindingKey name = G.key "Binding" name;
  datatypeKey name = G.key "Datatype" name;
  contractValue contract = W.VNode 420
    [A.toXType (Separate.normalType (Source.contractType contract)),
     A.toList A.toText (Source.contractClasses contract),A.toBool (Source.contractProtected contract)];
  -- Each input is refreshed once from current source/checked metadata. Derived
  -- nodes have explicit edges back to that authority, including empty scopes.
  input identity value session = G.record (G.inputKey identity) [] False value session;
  recordInitialBindings values session = case values of {
    [] -> ioReturn (Right session);
    (:) ((,) name contract) rest -> do {
      observed <- input (bindingKey name) (contractValue contract) session;
      case observed of { Left e -> ioReturn (Left e); Right ((,) leaf next) -> do {
        recorded <- G.record (bindingKey name) [G.edge leaf] True (contractValue contract) next;
        case recorded of { Left e -> ioReturn (Left e); Right ((,) _ final) -> recordInitialBindings rest final }
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
  preparedValue prepared = W.VNode 421
    [W.VText (Q.list (compose Q.encodeMember Q.canonicalMember) (Source.groupOriginal prepared)),
     W.VText (Q.list (compose Q.encodeMember Q.canonicalMember) (Source.groupMembers prepared)),
     A.toList A.toText (Q.sourceGroupMetadataUsing candidateMetadata prepared)];
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
      Right ((,,) plan inventory contracts)
    } of {
      Left e -> ioReturn (Left e);
      Right ((,,) plan inventory contracts) -> start verify crateId compilerHash cacheDir
        "source" inventory (Source.planData plan) contracts (Source.prepareGroupSparse plan) (Source.planGroups plan)
    };
  -- The already-lowered fallback has no unsigned-root evidence finalization.
  -- It still uses the same open bodies, dependency graph and crate transaction.
  -- Preserve its existing conservative (protected, no source-class slots)
  -- calling contract, including mixed source/dictionary recursive groups.
  compileLowered verify crateId compilerHash cacheDir imports datatypes members =
    case do {
      groups <- Dependency.declarationGroups members;
      inventory <- Q.prepareData datatypes;
      types <- foldM Inference.mergeExternal M.empty (concatMap Separate.unitBindings imports);
      let { contracts = M.map (\ty -> Source.SourceContract ty [] True) types;
        values = M.fromList compareString (map (\m@((,,) name _ _) -> (,) name m) members) };
      Right ((,,,) groups inventory contracts values)
    } of {
      Left e -> ioReturn (Left e);
      Right ((,,,) groups inventory contracts values) -> start verify crateId compilerHash cacheDir
        "lowered" inventory datatypes contracts (prepareLowered values) groups
    };
  prepareLowered :: Map String ((,,) String (Maybe SAnnotation) SExpr) ->
    Map String Source.SourceContract -> [] String -> Either String Source.PreparedGroup;
  prepareLowered values contracts names = do {
    members <- traverseEither (\name -> case M.lookup compareString name values of {
      Just member -> Right member; Nothing -> Left "lowered query member disappeared"
    }) names;
    let { bindings = Source.selectedContractBindings members contracts };
    Right (Source.PreparedGroup members members bindings M.empty
      (map (\name -> (,,) name [] True) names) Nothing
      (map (\((,) name _) -> (,) name True) bindings))
  };
  start verify crateId compilerHash cacheDir flavor inventory datatypes contracts prepare groups = do {
        statistics <- G.profile;
        graphStarted <- G.clock statistics;
        auditSetting <- getEnv "MLF_QUERY_SEMANTIC_AUDIT";
        started <- G.begin (cacheDir ++ "/query-graph-v1")
          (Separate.pack [crateId,compilerHash,Q.sourceQueryFormat,"open-fragment-checker-1",flavor]);
        case started of { Left e -> ioReturn (Left e); Right session -> do {
          initial <- recordInitialBindings (M.toList contracts) session;
          case initial of { Left e -> ioReturn (Left e); Right first -> do {
            loaded <- recordDatatypes datatypes first;
            case loaded of { Left e -> ioReturn (Left e); Right ready -> do {
              G.elapsed statistics 0 graphStarted;
              runGroups verify (eqString auditSetting "1") crateId inventory prepare groups
                (State ready contracts M.empty [] 0 0 [] statistics)
            } }
          } }
        } }
    };
  runGroups verify audit crateId inventory prepare groups state = case groups of {
    [] -> ioReturn (Right state);
    (:) names rest -> case state of {
      State session contracts contexts objects inferred reused reports statistics ->
        case prepare contracts names of {
          Left e -> ioReturn (Left e);
          Right prepared -> do {
            let { declarations = Q.requiredDataIn inventory (Source.groupMembers prepared)
                    (append (Source.groupBindings prepared) (Source.groupCandidateBindings prepared));
              group = Q.groupName crateId (sortBy compareString names);
              identity = Separate.pack (sortBy compareString names);
              rawKey = G.key "InferScc" identity };
            graphStarted <- G.clock statistics;
            source <- input (G.key "Prepared" identity) (preparedValue prepared) session;
            case source of { Left e -> ioReturn (Left e); Right ((,) sourceNode first) -> do {
              scopeInput <- input (G.key "ScopeInventory" identity) (scopeInventory prepared) first;
              case scopeInput of { Left e -> ioReturn (Left e); Right ((,) scopeLeaf second) ->
                case do {
                  candidateNodes <- requireNodes (map (compose bindingKey fst) (Source.groupCandidateBindings prepared)) second;
                  bindingNodes <- requireNodes (map (compose bindingKey fst) (Source.groupBindings prepared)) second;
                  dataNodes <- requireNodes (map (compose datatypeKey D.datatypeName) declarations) second;
                  Right ((,,) candidateNodes bindingNodes dataNodes)
                } of {
                  Left e -> ioReturn (Left e);
                  Right ((,,) candidateNodes bindingNodes dataNodes) -> do {
                    scoped <- G.record (G.key "Scope" identity)
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
                              loaded <- Open.decodeTrusted (G.payloadPath active digest) digest references "raw" group env
                                (Source.groupBindings prepared) names;
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
                                      Source.validatePreparedOpen prepared checked;
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
                              Source.validatePreparedOpen prepared canonical;
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
                            case Source.prepareOpenFinish prepared fragment of {
                              Left e -> ioReturn (Left e);
                              Right finish -> do {
                                evidence <- resolveRequests env identity ((:) (G.edge scopeNode) (map G.edge dataNodes))
                                  (Source.openFinishRequests finish) fourth;
                                case evidence of { Left e -> ioReturn (Left e); Right ((,,) answers evidenceReads afterEvidence) ->
                                case Source.completeOpenFinish finish answers of {
                                Left e -> ioReturn (Left e);
                                Right finished -> do {
                                let { final = Source.openFinalObject finished; delta = Source.openFinalContracts finished };
                                case requireNodes (map (compose bindingKey (compose X.nameHint fst))
                                  (Open.parameters final)) afterEvidence of {
                                Left e -> ioReturn (Left e);
                                Right finalBindings -> do {
                                completed <- G.record (G.key "FinishScc" identity)
                                  (append [G.edge rawNode,G.edge sourceNode,G.edge scopeNode]
                                    (append evidenceReads (map G.edge finalBindings))) False
                                  (W.VNode 424 [Open.encodeBody "final" group final,
                                    A.toList (A.toPair A.toText A.toText)
                                      (append (map G.edge finalBindings) (map G.edge dataNodes)),
                                    A.toList (A.toPair A.toText contractValue) (M.toList delta)]) afterEvidence;
                                case completed of { Left e -> ioReturn (Left e); Right ((,) finishNode fifth) -> do {
                                  supplied <- recordBindings (G.edge finishNode) (M.toList delta) fifth;
                                  case supplied of { Left e -> ioReturn (Left e); Right next -> do {
                                    G.elapsed statistics 3 finishStarted;
                                    runGroups verify audit crateId inventory prepare rest
                                      (State next (M.union compareString delta contracts) currentContexts
                                        ((:) ((,) group final) objects)
                                        (inferred + if hit then 0 else 1) (reused + if hit then 1 else 0)
                                        ((:) (Q.GroupResult group names hit
                                          (Separate.fingerprint (Q.list Q.encodeSourceContract (M.toList delta)))
                                          (G.nodeHash rawNode)) reports) statistics)
                                  } }
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
  recordBindings dependency values session = case values of {
    [] -> ioReturn (Right session);
    (:) ((,) name contract) rest -> do {
      recorded <- G.record (bindingKey name) [dependency] True (contractValue contract) session;
      case recorded of { Left e -> ioReturn (Left e); Right ((,) _ next) -> recordBindings dependency rest next }
    }
  };
  result (State session contracts _ objects inferred reused reports _) =
    (,,,) (reverse objects) (Q.QueryReport inferred reused (reverse reports)) contracts session;
  statistics (State _ _ _ _ _ _ _ stats) = stats;
  evidenceNames candidates = zip (map Boundary.candidateName candidates)
    (map (\((,) index candidate) -> XName (0 - index - 1) (X.nameHint (Boundary.candidateName candidate)))
      (zip (range 0 (length candidates - 1)) candidates));
  evidenceValue goal references candidates answer = let {
    names = M.fromList X.compareName (evidenceNames candidates);
    canonical = mapOptional (Separate.mapTerm (\n -> M.findWithDefault X.compareName n n names) (\a -> a)) answer
  } in W.VNode 426 [A.toXType (Separate.normalType goal),
    A.toList (A.toPair A.toText A.toText) references,A.toMaybe A.toXTerm canonical];
  decodeEvidence graph goal references candidates = do {
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
        let { replacements = M.fromList X.compareName (map (\((,) a b) -> (,) b a) (evidenceNames candidates)) };
        Right (mapOptional (Separate.mapTerm (\n -> M.findWithDefault X.compareName n n replacements) (\a -> a)) proof)
      };
      _ -> Left "invalid stable evidence record"
    }
  };
  resolveRequests env identity dependencies requests session = case requests of {
    [] -> ioReturn (Right ((,,) [] [] session));
    (:) ((,,) ordinal goal candidates) rest -> do {
      let { wanted = G.key "Evidence" (Separate.pack [identity,showInt ordinal,
          Pretty.prettyType (Separate.normalType goal)]);
        validated = G.validate wanted session; previous = fst validated; current = snd validated };
      cached <- case previous of {
        Nothing -> ioReturn (Left "dirty evidence query");
        Just node -> case G.nodePayload node of {
          Nothing -> ioReturn (Left "missing evidence payload");
          Just digest -> do {
            read <- G.readValue (G.payloadPath current digest) (Just digest);
            ioReturn (bindEither read (\graph -> decodeEvidence graph goal dependencies candidates))
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
          Left _ -> G.record wanted dependencies True (evidenceValue goal dependencies candidates proof) current
        };
        case recorded of { Left e -> ioReturn (Left e); Right ((,) node next) -> do {
          tail <- resolveRequests env identity dependencies rest next;
          ioReturn (mapEither (\((,,) answers edges final) ->
            (,,) ((:) ((,) ordinal proof) answers) ((:) (G.edge node) edges) final) tail)
        } }
      } }
    }
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
