-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.SourceInference where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import Bootstrap.Fresh;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.EvidenceBoundary as Boundary;
  import qualified Bootstrap.InferenceUnit as Inference;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Data as Data;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as Type;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Pretty as Pretty;

  -- Internal explicit source calling convention, paired with a checked target
  -- scheme. No dictionary-arrow inspection constructs this overload list.
  data SourceContract = SourceContract XType ([] String) Bool;
  contractType (SourceContract ty _ _) = ty;
  contractClasses (SourceContract _ classes _) = classes;
  contractProtected (SourceContract _ _ protected) = protected;
  contractTypes contracts = M.map contractType contracts;
  contractOverloads contracts = M.mapWithKey
    (\name contract -> (,) name (contractClasses contract)) contracts;

  -- Keep this helper below CrateQuery to avoid a query/orchestrator cycle.
  selectedBindings members available =
    let { used = Set.fromList compareString
      (concatMap (\member -> Dependency.valueNames (Dependency.observeDeclaration member)) members) }
    in M.toList (M.filterWithKey (\name _ -> Set.member compareString name used) available);

  -- Provisional is never an available contract/cache hit. Source-issued labels
  -- and exact candidate scope travel with its independently checked object.
  data ProvisionalRoot = ProvisionalRoot String Separate.UnitObject
    ([] ((,,) String String String)) ([] ((,) EvidenceRole String)) Bool
    (Map String String) ([] ((,,) EvidenceRole String XType)) ([] String);
  provisionalObject (ProvisionalRoot _ object _ _ _ _ _ _) = object;
  provisionalLabels (ProvisionalRoot _ _ labels _ _ _ _ _) = labels;
  provisionalCandidates (ProvisionalRoot _ _ _ candidates _ _ _ _) = candidates;
  provisionalProtected (ProvisionalRoot _ _ _ _ protected _ _ _) = protected;

  protectedCandidateNames contracts names = filter
    (\name -> case M.lookup compareString name contracts of {
      Nothing -> True;
      Just contract -> contractProtected contract
    }) names;
  checkedDependencyProtected :: [] ((,) String Bool) -> Separate.UnitObject -> Either String Bool;
  checkedDependencyProtected flags object = do {
    let { term = case Separate.objectTerm object of { XWithData _ body -> body; body -> body } };
    let { split = Separate.splitParameters term };
    let { parameters = fst split };
    let { used = Boundary.nubNames (Boundary.freeNames (snd split)) };
    protected <- traverseEither (\name -> do {
      parameter <- case find (\((,) binder _) -> X.equalName binder name) parameters of {
        Nothing -> Left "checked raw implementation has an unowned free parameter";
        Just value -> Right (fst value)
      };
      case find (\((,) hint _) -> eqString hint (X.nameHint parameter)) flags of {
        Nothing -> Left "used checked predecessor lacks protection authority";
        Just entry -> Right (snd entry)
      }
    }) used;
    Right (any (\flag -> flag) protected)
  };
  parameterProtection contracts bindings = map
    (\((,) name _) -> (,) name (case M.lookup compareString name contracts of {
      Nothing -> True;
      Just contract -> contractProtected contract
    })) bindings;

  -- The validated lowerer derives source/selector/transitive protection;
  -- callers cannot obtain eligibility merely by passing a false flag.
  prepareUnsignedRoot :: Classes.ClassInventory -> Map String SourceContract ->
    String -> SExpr -> Fresh ProvisionalRoot;
  prepareUnsignedRoot inventory contracts name original =
    do {
      freshLift (ensure (not (M.member compareString name contracts))
        "source root also occurs in predecessor contracts");
      lowered <- Classes.lowerUnsignedSourceRootProtected inventory
        (contractOverloads contracts) (M.map contractProtected contracts) name original;
      case lowered of {
        Classes.SourceRootLowering rhs labels candidates protected ->
          do {
            let { members = (:) ((,,) name Nothing rhs) [] };
            let { selected = selectedBindings members (contractTypes contracts) };
            let { datatypes = case inventory of {
              Classes.ClassInventory ds _ _ _ _ _ _ _ _ -> ds
            } };
            object <- freshLift
              (Inference.compileLoweredGroup name
                ((:) (Separate.UnitInterface "SourceInputs" [] [] [] [] [] selected "parameters") []) datatypes members);
            typedCandidates <- freshLift (traverseEither
              (\((,) role candidate) -> case M.lookup compareString candidate contracts of {
                Nothing -> Left ("definition evidence support has not been checked: " ++ candidate);
                Just contract -> Right ((,,) role candidate (contractType contract))
              }) candidates);
            usedProtected <- freshLift
              (checkedDependencyProtected (parameterProtection contracts selected) object);
            freshPure (ProvisionalRoot name object labels candidates
              (protected || usedProtected)
              (Classes.inventoryOrdinaryRegistry inventory) typedCandidates
              (protectedCandidateNames contracts (map snd candidates)))
          }
      }
    };

  data RootParts = RootParts ([] DataDecl) ([] ((,) XName XType)) XName XType XTerm;
  rootParts :: ProvisionalRoot -> Either String RootParts;
  rootParts (ProvisionalRoot name object _ _ _ _ _ _) =
    do {
      let { datatypes = Separate.unitData (Separate.objectInterface object) };
      let { term = case Separate.objectTerm object of {
        XWithData _ body -> body; body -> body
      } };
      let { split = Separate.splitParameters term };
      found <- case snd split of {
        XLet binder rhs (XConstructor "()" []) -> Right ((,) binder rhs);
        _ -> Left "source root did not retain a single nonrecursive checked binding"
      };
      case Separate.unitBindings (Separate.objectInterface object) of {
        (:) ((,) exported ty) [] -> do {
          ensure (eqString exported name && eqString (X.nameHint (fst found)) name)
            "source root checked ownership mismatch";
          Right (RootParts datatypes (fst split) (fst found) ty (snd found))
        };
        _ -> Left "source root changed binding count"
      }
    };

  -- Direct representation map only. Unsupported target wrappers are an
  -- unchanged-boundary fallback, never grounds for invented binder identities.
  targetSlots :: [] ((,,) String String String) -> XTerm ->
    Either String (Maybe ([] ((,,) XName String String)));
  targetSlots labels rhs = case labels of {
    [] -> Right (Just []);
    (:) ((,,) sourceName className dictionaryName) rest -> case rhs of {
      XAbs binder _ body -> do {
        ensure (eqString (X.nameHint binder) sourceName)
          "source-issued slot does not match checked target binder";
        following <- targetSlots rest body;
        Right (case following of {
          Nothing -> Nothing;
          Just values -> Just ((:) ((,,) binder className dictionaryName) values)
        })
      };
      _ -> Right Nothing
    }
  };

  data FinalRoot = FinalRoot Separate.UnitObject SourceContract;
  finalObject (FinalRoot object _) = object;
  finalContract (FinalRoot _ contract) = contract;
  unchangedRoot :: ProvisionalRoot -> Either String FinalRoot;
  unchangedRoot root@(ProvisionalRoot _ object labels _ protected _ _ _) =
    do {
      parts <- rootParts root;
      case parts of {
        RootParts _ _ _ ty _ ->
          Right (FinalRoot object
            (SourceContract ty (map (\((,,) _ className _) -> className) labels) protected))
      }
    };

  -- A typed boundary adapter supplies a raw term and exact parameter list; no
  -- dictionary body is duplicated here. This verifies the public target binding
  -- independently of the adapter before returning the compact source contract.
  -- Only ALL-ground zero-residual plans may call this first-slice constructor.
  checkedCompactRoot :: ProvisionalRoot -> XType -> XTerm ->
    [] ((,) XName XType) -> Either String FinalRoot;
  checkedCompactRoot root@(ProvisionalRoot name _ _ _ protected _ _ _) ty adapter parameters =
    do {
      ensure (not protected) "cannot compact a protected source boundary";
      parts <- rootParts root;
      case parts of {
        RootParts datatypes _ binder _ _ -> do {
          let { implementation = XLet binder adapter (XConstructor "()" []) };
          let { payload = XWithData datatypes
            (foldr (\((,) n t) body -> XAbs n t body) implementation parameters) };
          checked <- Checked.check payload;
          dataEnv <- Data.validateDeclarations datatypes;
          bindings <- Separate.collectBindings dataEnv
            (XEnv M.empty (M.fromList X.compareName parameters)) implementation;
          ensure (case bindings of {
            (:) ((,) actualName actualType) [] ->
              X.equalName actualName binder && Type.alphaEq actualType ty;
            _ -> False
          }) "compact root binding and checked adapter type disagree";
          let { iface = Separate.UnitInterface
            (Separate.unitName (Separate.objectInterface (provisionalObject root))) [] [] datatypes [] []
            ((:) ((,) name ty) []) (Separate.fingerprint (Pretty.prettyTerm payload)) };
          Right (FinalRoot (Separate.CheckedUnitObject iface checked)
            (SourceContract ty [] False))
        }
      }
    };

  candidateParameters :: [] ((,) XName XType) ->
    XTerm -> [] ((,,) EvidenceRole String XType) -> Either String ([] Boundary.Candidate);
  candidateParameters parameters term candidates =
    let {
      first = 1 + foldl max 0 (Set.toList (Separate.termIdentities term Set.empty))
    } in
    traverseEither
      (\((,) ordinal ((,,) role name ty)) -> do {
        let { binder = case find (\((,) n _) -> eqString (X.nameHint n) name) parameters of {
          Just ((,) n _) -> n;
          Nothing -> XName (first + ordinal) name
        } };
        Right (Boundary.Candidate role binder ty)
      })
      (zip (range 0 (length candidates - 1)) candidates);

  finishUnsignedRoot :: ProvisionalRoot -> Either String FinalRoot;
  finishUnsignedRoot root@(ProvisionalRoot rootName object labels roles protected registry typedCandidates protectedCandidates) =
    if protected then unchangedRoot root else do {
      parts <- rootParts root;
      case parts of {
        RootParts datatypes parameters binder ty rhs -> do {
          slots <- targetSlots labels rhs;
          case slots of {
            Nothing -> unchangedRoot root;
            Just mapped -> do {
              authorized <- candidateParameters parameters (Separate.objectTerm object) typedCandidates;
              let { boundary = Boundary.Boundary 0 Boundary.UnsignedRoot False 0
                (map (\((,,) n _ _) -> n) mapped) };
              let { obligations = map
                (\((,) ordinal ((,,) n className dictionaryName)) ->
                  Boundary.Slot 0 ordinal n (Boundary.GeneratedOrdinary className dictionaryName) 0)
                (zip (range 0 (length mapped - 1)) mapped) };
              plan <- Boundary.adaptOpen registry
                datatypes boundary obligations parameters
                ((:) (Boundary.EvidenceScope 0 authorized) []) ty rhs;
              if any (\support -> elem eqString (X.nameHint support) protectedCandidates)
                   (Boundary.openProofSupports plan)
              then unchangedRoot (ProvisionalRoot rootName object labels roles True registry
                typedCandidates protectedCandidates)
              else if Boundary.openChanged plan
              then do {
                ensure (null (Boundary.openResidualOrdinals plan))
                  "partial evidence contraction is outside source boundary policy";
                checkedCompactRoot root (Boundary.openNewType plan)
                  (Boundary.openRawAdapter plan) (Boundary.openRequiredParameters plan)
              }
              else unchangedRoot root
            }
          }
        }
      }
    };
  compileUnsignedRoot :: Classes.ClassInventory -> Map String SourceContract ->
    String -> SExpr -> Fresh FinalRoot;
  compileUnsignedRoot inventory contracts name rhs = do {
    provisional <- prepareUnsignedRoot inventory contracts name rhs;
    freshLift (finishUnsignedRoot provisional)
  };

  -- Source planning retains original annotations/ownership until after routing.
  -- The legacy recipe is lazy and is used only by the explicit whole-path
  -- fallback or compatibility diagnostics, never to prepare source queries.
  data SourcePlan = SourcePlan Classes.ClassInventory
    ([] ((,,) String (Maybe SAnnotation) SExpr))
    ([] ((,,) String (Maybe SAnnotation) SExpr)) ([] ([] String))
    Int (Set String) (Map String SType) (Either String Inference.LoweredDeclarations)
    ([] ((,) String SInstanceDecl)) (Map String Bool);
  planInventory (SourcePlan inventory _ _ _ _ _ _ _ _ _) = inventory;
  planSources (SourcePlan _ values _ _ _ _ _ _ _ _) = values;
  planSupports (SourcePlan _ _ values _ _ _ _ _ _ _) = values;
  planGroups (SourcePlan _ _ _ groups _ _ _ _ _ _) = groups;
  planData plan = case planInventory plan of {
    Classes.ClassInventory ds _ _ _ _ _ _ _ _ -> ds
  };
  planNames plan = case planInventory plan of {
    Classes.ClassInventory _ _ _ _ _ _ _ names _ -> names
  };
  planLegacy (SourcePlan _ _ _ _ _ _ _ legacy _ _) = legacy;
  sourceName ((,,) name _ _) = name;
  sourceRhs ((,,) _ _ rhs) = rhs;
  isCopied :: SExpr -> Bool;
  isCopied (SSourceDefinition _) = True;
  isCopied (SCallSite _ _ body) = isCopied body;
  isCopied (SAnn body _) = isCopied body;
  isCopied (SSignature body _) = isCopied body;
  isCopied (SChecked _ body) = isCopied body;
  isCopied _ = False;
  prepareSourcePlan :: Map String SType -> [] DataDecl -> [] SClassDecl ->
    [] ((,) String SInstanceDecl) -> Map String IntSet -> [] IntSet ->
    [] ((,,) String (Maybe SAnnotation) SExpr) -> Either String (Maybe SourcePlan);
  prepareSourcePlan externals datatypes classes instances valueScopes instanceScopes members = do {
    closedInstances <- traverseEither
      (\((,) name inst) -> mapEither ((,) name) (Separate.closeInstance members inst)) instances;
    body <- Surface.bindValues members (SConstructor "()");
    prepared <- Classes.withScopedClassInventory externals (map fst closedInstances)
      valueScopes instanceScopes
      (SClassProgram datatypes classes (map snd closedInstances) body)
      (\inventory -> Fresh (\count used -> Right ((,,) ((,,) inventory count used) count used)));
    case prepared of { (,,) inventory count used -> do {
      let { supports = case inventory of {
        Classes.ClassInventory _ _ _ _ _ _ definitions _ _ ->
          map (\((,,) name annotation rhs) -> (,,) name (Just annotation) rhs) definitions
      } };
      let { allMembers = append supports members };
      ensure (length allMembers == Set.size (Set.fromList compareString (map sourceName allMembers)))
        "duplicate source/support binding";
      let { sourceNames = Set.fromList compareString (map sourceName members) };
      let { supportNames = Set.fromList compareString (map sourceName supports) };
      let { edges = case inventory of {
        Classes.ClassInventory _ _ _ scopes _ methods _ _ _ ->
          append (Dependency.declarationEdges supports)
            (map (\member ->
              let { name = sourceName member } in
              let { references = Dependency.valueNames (Dependency.observeDeclaration member) } in
              (,) name (append
                (map (\reference -> case M.lookup compareString reference methods of {
                  Nothing -> reference; Just ((,) target _) -> target
                }) references)
                (map snd (M.findWithDefault compareString [] name scopes)))) members)
      } };
      let { groups = Dependency.components edges };
      let { unsupported = any (\names ->
        (any (\name -> Set.member compareString name sourceNames) names &&
         any (\name -> Set.member compareString name supportNames) names) ||
        any (\name -> case find (\member -> eqString (sourceName member) name) members of {
          Nothing -> False;
          Just member -> isCopied (sourceRhs member)
        }) names) groups };
      if unsupported then Right Nothing else
        Right (Just (SourcePlan inventory members supports groups count used externals
          (Inference.lowerDeclarationsWithImports externals datatypes classes instances
            valueScopes instanceScopes members) instances M.empty))
    } }
  };
  initializeProtection :: SourcePlan -> Map String Bool -> Either String SourcePlan;
  initializeProtection (SourcePlan inventory sources supports groups count used externals legacy instances _) imported = do {
    flags <- Classes.inventoryProtection inventory imported instances sources;
    Right (SourcePlan inventory sources supports groups count used externals legacy instances flags)
  };
  initialContracts :: SourcePlan -> Map String XType -> Map String Bool ->
    Either String (Map String SourceContract);
  initialContracts (SourcePlan _ _ _ _ _ _ externals _ _ _) types protected =
    mapEither (M.fromList compareString) (traverseEither
      (\((,) name ty) -> do {
        source <- case M.lookup compareString name externals of {
          Nothing -> Left ("source dependency lacks an import contract: " ++ name);
          Just value -> Right value
        };
        let { classes = case Classes.scheme source of {
          (,,) _ predicates _ -> map (\(SPredicate cls _) -> cls) predicates
        } };
        Right ((,) name (SourceContract ty classes
          (M.findWithDefault compareString True name protected || Classes.managedType source)))
      }) (M.toList types));

  -- A sealed prepared query contains raw input and all finalization authority.
  -- No checked object is admitted until the existing raw cache/inference checks.
  data PreparedGroup = PreparedGroup
    ([] ((,,) String (Maybe SAnnotation) SExpr))
    ([] ((,,) String (Maybe SAnnotation) SExpr))
    ([] ((,) String XType)) (Map String String)
    ([] ((,,) String ([] String) Bool)) (Maybe RootAuthority) ([] ((,) String Bool));
  data RootAuthority = RootAuthority String ([] ((,,) String String String)) Bool
    ([] ((,,) EvidenceRole String XType)) ([] String);
  groupOriginal (PreparedGroup original _ _ _ _ _ _) = original;
  groupMembers (PreparedGroup _ members _ _ _ _ _) = members;
  groupBindings (PreparedGroup _ _ bindings _ _ _ _) = bindings;
  groupRegistry (PreparedGroup _ _ _ registry _ _ _) = registry;
  groupContracts (PreparedGroup _ _ _ _ contracts _ _) = contracts;
  groupAuthority (PreparedGroup _ _ _ _ _ authority _) = authority;
  groupParameterProtection (PreparedGroup _ _ _ _ _ _ flags) = flags;
  groupCandidateBindings group = case groupAuthority group of {
    Nothing -> [];
    Just (RootAuthority _ _ _ candidates _) ->
      map (\((,,) _ name ty) -> (,) name ty) candidates
  };
  makePrepared original lowered registry specs authority contracts =
    let { bindings = selectedBindings lowered (contractTypes contracts) } in
    PreparedGroup original lowered bindings registry specs authority
      (parameterProtection contracts bindings);
  eligibleSource :: [] ((,,) String (Maybe SAnnotation) SExpr) -> Bool;
  eligibleSource members = case members of {
    (:) ((,,) name Nothing rhs) [] ->
      not (isCopied rhs) && not (elem eqString name (Surface.freeNames rhs)) &&
      null (Classes.sourceDeclaredClasses Nothing rhs);
    _ -> False
  };
  prepareGroup :: SourcePlan -> Map String SourceContract -> [] String -> Either String PreparedGroup;
  prepareGroup plan@(SourcePlan inventory sources supports _ count used _ _ _ supportProtection) contracts names = do {
    let { original = filter (\member -> elem eqString (sourceName member) names) sources };
    let { support = filter (\member -> elem eqString (sourceName member) names) supports };
    ensure (length original + length support == length names) "source SCC ownership mismatch";
    traverseEither (\name -> ensure (not (M.member compareString name contracts))
      "source SCC imports its own checked predecessor") names;
    let { registry = Classes.inventoryOrdinaryRegistry inventory };
    if not (null support) then do {
      ensure (null original) "mixed support/source SCC requires whole-path fallback";
      specs <- traverseEither (\name -> case M.lookup compareString name supportProtection of {
        Nothing -> Left ("generated support lacks source protection provenance: " ++ name);
        Just protected -> Right ((,,) name []
          (protected || any (\peer -> M.findWithDefault compareString True peer supportProtection) names))
      }) names;
      Right (makePrepared support support registry specs Nothing contracts)
    } else do {
      outcome <- runFreshState
        (if eligibleSource original then case original of {
          (:) ((,,) name Nothing rhs) [] -> do {
            lowered <- Classes.lowerUnsignedSourceRootProtected inventory
              (contractOverloads contracts) (M.map contractProtected contracts) name rhs;
            case lowered of { Classes.SourceRootLowering body labels candidates protected -> do {
              typed <- freshLift (traverseEither
                (\((,) role candidate) -> case M.lookup compareString candidate contracts of {
                  Nothing -> Left ("definition evidence support has not been checked: " ++ candidate);
                  Just contract -> Right ((,,) role candidate (contractType contract))
                }) candidates);
              let { loweredMembers = (:) ((,,) name Nothing body) [] };
              let { protectedNow = protected };
              freshPure (makePrepared original loweredMembers registry
                ((:) ((,,) name (map (\((,,) _ cls _) -> cls) labels) protectedNow) [])
                (Just (RootAuthority name labels protectedNow typed
                  (protectedCandidateNames contracts (map snd candidates)))) contracts)
            } }
          };
          _ -> freshFail "invalid eligible source group"
        } else do {
          lowered <- Classes.lowerSourceGroupUnchanged inventory (contractOverloads contracts)
            (M.map contractProtected contracts) original;
          case lowered of { (,) body specs -> do {
            values <- freshLift (Inference.extractLoweredDeclarations body);
            freshPure (makePrepared original values registry specs Nothing contracts)
          } }
        }) count used;
      case outcome of { (,,) prepared _ _ -> Right prepared }
    }
  };
  validateRawSlots :: [] ((,,) String String String) -> XErased -> Either String ();
  validateRawSlots labels rhs = case labels of {
    [] -> Right ();
    (:) ((,,) name _ _) rest -> case rhs of {
      XEAbs binder body -> do {
        ensure (eqString name (X.nameHint binder)) "raw source evidence prefix identity mismatch";
        validateRawSlots rest body
      };
      _ -> Left "raw source evidence prefix is missing"
    }
  };
  validatePreparedRaw :: PreparedGroup -> Separate.UnitObject -> Either String Separate.UnitObject;
  validatePreparedRaw prepared object = case groupAuthority prepared of {
    Nothing -> Right object;
    Just (RootAuthority name labels protected candidates protectedCandidates) -> do {
      parts <- rootParts (ProvisionalRoot name object labels
        (map (\((,,) role candidate _) -> (,) role candidate) candidates)
        protected (groupRegistry prepared) candidates protectedCandidates);
      case parts of { RootParts _ _ _ _ rhs -> do {
        validateRawSlots labels (X.erase rhs);
        Right object
      } }
    }
  };
  data FinalGroup = FinalGroup Separate.UnitObject (Map String SourceContract);
  finalGroupObject (FinalGroup object _) = object;
  finalGroupContracts (FinalGroup _ contracts) = contracts;
  finishGroup :: PreparedGroup -> Separate.UnitObject -> Either String FinalGroup;
  finishGroup prepared object = do {
    validatePreparedRaw prepared object;
    usedProtected <- checkedDependencyProtected (groupParameterProtection prepared) object;
    let { expected = sortBy compareString (map sourceName (groupMembers prepared)) };
    ensure (eqList eqString expected (map fst (Separate.unitBindings (Separate.objectInterface object))))
      "raw group changed source ownership";
    case groupAuthority prepared of {
      Just (RootAuthority name labels protected candidates protectedCandidates) -> do {
        root <- finishUnsignedRoot (ProvisionalRoot name object labels
          (map (\((,,) role candidate _) -> (,) role candidate) candidates) (protected || usedProtected)
          (groupRegistry prepared) candidates protectedCandidates);
        Right (FinalGroup (finalObject root)
          (M.fromList compareString ((:) ((,) name (finalContract root)) [])))
      };
      Nothing -> do {
        contracts <- traverseEither
          (\((,) name ty) -> case find (\((,,) n _ _) -> eqString n name) (groupContracts prepared) of {
            Nothing -> Left "final source group lacks calling-convention metadata";
            Just ((,,) _ classes protected) -> Right ((,) name (SourceContract ty classes (protected || usedProtected)))
          }) (Separate.unitBindings (Separate.objectInterface object));
        Right (FinalGroup object (M.fromList compareString contracts))
      }
    }
  }

}
