-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.EvidenceBoundary where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Evidence as E;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Type as XT;
  import qualified Bootstrap.X.Syntax as X;
  -- These records are issued by the validated source lowerer. They are not
  -- authority reconstructed from dictionary-shaped types or identifier text.
  data Origin = UnsignedRoot | SignedRoot | RecursiveRoot | CopiedHelper | InstanceSupport | NestedLocal;
  data Role = GeneratedOrdinary String String | ExplicitSlot | ManagedSlot;
  data Boundary = Boundary Int Origin Bool Int ([] XName);
  data Slot = Slot Int Int XName Role Int;
  data Candidate = Candidate EvidenceRole XName XType;
  data EvidenceScope = EvidenceScope Int ([] Candidate);
  data Reconstruction = Retain XName XType | Discharge XTerm ([] XName);
  data OpenPlan = OpenPlan XType XType XTerm Checked.CheckedTerm
    ([] ((,) XName XType)) ([] XName) ([] Reconstruction) ([] Int) Bool String;
  openOldType (OpenPlan a _ _ _ _ _ _ _ _ _) = a;
  openNewType (OpenPlan _ a _ _ _ _ _ _ _ _) = a;
  openRawAdapter (OpenPlan _ _ a _ _ _ _ _ _ _) = a;
  openCheckedClosure (OpenPlan _ _ _ a _ _ _ _ _ _) = a;
  openRequiredParameters (OpenPlan _ _ _ _ a _ _ _ _ _) = a;
  openProofSupports (OpenPlan _ _ _ _ _ a _ _ _ _) = a;
  openReconstructions (OpenPlan _ _ _ _ _ _ a _ _ _) = a;
  openResidualOrdinals (OpenPlan _ _ _ _ _ _ _ a _ _) = a;
  openChanged (OpenPlan _ _ _ _ _ _ _ _ a _) = a;
  openDisposition (OpenPlan _ _ _ _ _ _ _ _ _ a) = a;
  candidateName :: Candidate -> XName;
  candidateName (Candidate _ n _) = n;
  candidateType :: Candidate -> XType;
  candidateType (Candidate _ _ t) = t;
  candidateTriple :: Candidate -> (,,) EvidenceRole XName XType;
  candidateTriple (Candidate r n t) = (,,) r n t;
  isGiven :: Candidate -> Bool;
  isGiven (Candidate GivenEvidence _ _) = True;
  isGiven _ = False;
  eligible :: Origin -> Bool;
  eligible UnsignedRoot = True;
  eligible _ = False;
  ordinary :: Role -> Bool;
  ordinary (GeneratedOrdinary _ _) = True;
  ordinary _ = False;
  scopeIdentity :: EvidenceScope -> Int;
  scopeIdentity (EvidenceScope n _) = n;
  scopeCandidates :: EvidenceScope -> [] Candidate;
  scopeCandidates (EvidenceScope _ cs) = cs;
  nubNames :: [] XName -> [] XName;
  nubNames [] = [];
  nubNames ((:) n ns) = (:) n (nubNames (filter (\x -> not (X.equalName n x)) ns));
  uniqueNames :: [] XName -> Bool;
  uniqueNames [] = True;
  uniqueNames ((:) n ns) = not (any (X.equalName n) ns) && uniqueNames ns;
  uniqueInts :: [] Int -> Bool;
  uniqueInts [] = True;
  uniqueInts ((:) n ns) = not (any (eqInt n) ns) && uniqueInts ns;
  names :: XTerm -> [] XName;
  names term = case term of {
    XVarTerm n -> (:) n [];
    XAbs n _ b -> (:) n (names b);
    XApp a b -> append (names a) (names b);
    XTypeAbs _ _ b -> names b;
    XTypeApp b _ -> names b;
    XLet n a b -> (:) n (append (names a) (names b));
    XLetRec ds b -> append (concatMap (\((,,) n _ v) -> (:) n (names v)) ds) (names b);
    XCase a _ bs -> append (names a) (concatMap (\(XAlternative p b) -> append (X.patternNames p) (names b)) bs);
    XWithData _ b -> names b;
    XIntTerm _ -> [];
    XDoubleTerm _ -> [];
    XBoolTerm _ -> [];
    XStringTerm _ -> [];
    XPrimitive _ _ -> [];
    XConstructor _ _ -> []
  };
  freeNames :: XTerm -> [] XName;
  freeNames term = case term of {
    XVarTerm n -> (:) n [];
    XAbs n _ b -> filter (\x -> not (X.equalName n x)) (freeNames b);
    XApp a b -> append (freeNames a) (freeNames b);
    XTypeAbs _ _ b -> freeNames b;
    XTypeApp b _ -> freeNames b;
    XLet n a b -> append (freeNames a) (filter (\x -> not (X.equalName n x)) (freeNames b));
    XLetRec ds b -> let {
      bound = map (\((,,) n _ _) -> n) ds;
      uses = append (concatMap (\((,,) _ _ v) -> freeNames v) ds) (freeNames b)
    } in filter (\n -> not (any (X.equalName n) bound)) uses;
    XCase a _ bs -> append (freeNames a)
      (concatMap (\(XAlternative p b) -> filter (\n -> not (any (X.equalName n) (X.patternNames p))) (freeNames b)) bs);
    XWithData _ b -> freeNames b;
    XIntTerm _ -> [];
    XDoubleTerm _ -> [];
    XBoolTerm _ -> [];
    XStringTerm _ -> [];
    XPrimitive _ _ -> [];
    XConstructor _ _ -> []
  };
  ground :: XType -> Bool;
  ground ty = case ty of {
    XCon _ xs -> all ground xs;
    XArrow a b -> ground a && ground b;
    XApply a b -> ground a && ground b;
    XVar _ -> False;
    XBot -> False;
    XBotKind _ -> False;
    XForall _ _ _ -> False
  };
  hasForall :: XType -> Bool;
  hasForall ty = case ty of {
    XForall _ _ _ -> True;
    XCon _ xs -> any hasForall xs;
    XArrow a b -> hasForall a || hasForall b;
    XApply a b -> hasForall a || hasForall b;
    XVar _ -> False;
    XBot -> False;
    XBotKind _ -> False
  };
  mergeTypes :: [] ((,) XName XType) -> Either String ([] ((,) XName XType));
  mergeTypes values = foldM mergeType [] values;
  mergeType :: [] ((,) XName XType) -> (,) XName XType -> Either String ([] ((,) XName XType));
  mergeType values entry = case entry of { (,) n t ->
    case filter (\((,) m _) -> X.equalName n m) values of {
      [] -> Right (snoc values entry);
      (:) ((,) _ prior) [] -> do {
        ensure (XT.alphaEq t prior) "conflicting ambient/candidate parameter types";
        Right values
      };
      _ -> Left "duplicate merged parameter identity"
    }
  };
  prefixTypes :: Int -> XType -> Either String ([] XType);
  prefixTypes count ty = if eqInt count 0 then Right [] else case ty of {
    XArrow domain body -> mapEither ((:) domain) (prefixTypes (subInt count 1) body);
    _ -> Left "authoritative slot prefix exceeds checked arrow arity"
  };
  directPrefix :: Int -> XTerm -> XType -> Maybe ((,) ([] ((,) XName XType)) XType);
  directPrefix count term ty = if eqInt count 0 then Just ((,) [] ty) else case term of {
    XAbs n domain body -> case ty of {
      XArrow expected result -> if XT.alphaEq domain expected then
        case directPrefix (subInt count 1) body result of {
          Nothing -> Nothing;
          Just ((,) rest final) -> Just ((,) ((:) ((,) n domain) rest) final)
        } else Nothing;
      _ -> Nothing
    };
    _ -> Nothing
  };
  validateRole :: Map String String -> Role -> XType -> Either String ();
  validateRole registry role domain = case role of {
    GeneratedOrdinary klass expected -> if eqString klass "MLFHasCallStack" || eqString expected "MLFStackEvidence"
      then Left "managed evidence cannot be labelled ordinary"
      else case M.lookup compareString klass registry of {
        Nothing -> Left "ordinary slot class is not in the authoritative registry";
        Just dictionary -> do {
          ensure (eqString dictionary expected) "ordinary slot registry dictionary identity mismatch";
          case domain of {
            XCon actual _ -> ensure (eqString actual expected) "ordinary slot dictionary identity mismatch";
            _ -> Left "ordinary slot is not its recorded dictionary type"
          }
        }
      };
    ExplicitSlot -> Right ();
    ManagedSlot -> Right ()
  };
  validateSlots :: Int -> Int -> [] EvidenceScope -> Int -> [] XName -> [] Slot -> Either String ();
  validateSlots boundary root scopes ordinal expected slots = case expected of {
    [] -> ensure (null slots) "missing/duplicate authoritative slot";
    (:) name rest -> case slots of {
      [] -> Left "missing/duplicate authoritative slot";
      (:) (Slot owner index binder _ sid) remaining -> do {
        ensure (eqInt owner boundary && eqInt index ordinal && X.equalName name binder) "forged slot provenance";
        ensure (eqInt sid root) "slot scope differs from authoritative definition scope";
        ensure (eqInt (length (filter (\scope -> eqInt (scopeIdentity scope) sid) scopes)) 1) "unknown slot scope";
        validateSlots boundary root scopes (addInt ordinal 1) rest remaining
      }
    }
  };
  validateDomains :: Map String String -> [] XType -> [] Slot -> Either String ();
  validateDomains registry domains slots = case domains of {
    [] -> ensure (null slots) "slot domain count mismatch";
    (:) ty rest -> case slots of {
      [] -> Left "slot domain count mismatch";
      (:) (Slot _ _ _ role _) remaining -> do {
        validateRole registry role ty;
        validateDomains registry rest remaining
      }
    }
  };
  eligibleSlots :: [] XType -> [] Slot -> Bool;
  eligibleSlots domains slots = case domains of {
    [] -> null slots;
    (:) ty rest -> case slots of {
      [] -> False;
      (:) (Slot _ _ _ role _) remaining -> ordinary role && ground ty && eligibleSlots rest remaining
    }
  };
  sameBinders :: [] ((,) XName XType) -> [] XName -> Bool;
  sameBinders binders expected = case binders of {
    [] -> null expected;
    (:) ((,) name _) rest -> case expected of {
      [] -> False;
      (:) n ns -> X.equalName name n && sameBinders rest ns
    }
  };
  reconstruct :: DataEnv -> [] Candidate -> Int -> Int -> [] XType -> [] Slot -> Either String ([] Reconstruction);
  reconstruct datatypes authorized base index domains slots = case domains of {
    [] -> if null slots then Right [] else Left "slot domain count mismatch";
    (:) domain rest -> case slots of {
      [] -> Left "slot domain count mismatch";
      (:) (Slot _ _ _ role _) remaining -> do {
        let { retained = Retain (XName (addInt base index) "retainedEvidence") domain };
        item <- if not (ordinary role) || not (ground domain) then Right retained else
          case E.resolveDictionaryDetailed datatypes M.empty (map candidateTriple authorized) domain of {
            Left (E.NoEntailment _) -> Right retained;
            Left (E.InvalidEvidence message) -> Left message;
            Right proof -> let { dependencies = nubNames (freeNames proof) } in do {
              ensure (all (\n -> any (\candidate -> X.equalName n (candidateName candidate)) authorized) dependencies)
                "proof escaped definition evidence scope";
              Right (Discharge proof dependencies)
            }
          };
        tail <- reconstruct datatypes authorized base (addInt index 1) rest remaining;
        Right ((:) item tail)
      }
    }
  };
  keptFrom :: Int -> [] Reconstruction -> [] ((,,) Int XName XType);
  keptFrom index items = case items of {
    [] -> [];
    (:) item rest -> case item of {
      Retain n t -> (:) ((,,) index n t) (keptFrom (addInt index 1) rest);
      Discharge _ _ -> keptFrom (addInt index 1) rest
    }
  };
  argument :: Reconstruction -> XTerm;
  argument (Retain n _) = XVarTerm n;
  argument (Discharge proof _) = proof;
  proofNames :: Reconstruction -> [] XName;
  proofNames (Retain _ _) = [];
  proofNames (Discharge _ ns) = ns;
  ordinalsFrom :: Int -> Int -> [] Int;
  ordinalsFrom index count = if index >= count then [] else (:) index (ordinalsFrom (addInt index 1) count);
  finalize :: [] DataDecl -> DataEnv -> [] ((,) XName XType) -> XType -> XType -> XTerm ->
    [] Reconstruction -> [] Int -> [] XName -> Bool -> String -> Either String OpenPlan;
  finalize declarations datatypes combined old target body reconstruction residual supports changed disposition = do {
    let { used = nubNames (freeNames body) };
    ensure (all (\n -> any (\entry -> X.equalName n (fst entry)) combined) used)
      "adapter escaped authorized parameter environment";
    let { required = filter (\entry -> any (X.equalName (fst entry)) used) combined };
    actual <- Check.inferWithData datatypes (XEnv M.empty (M.fromList X.compareName required)) body;
    ensure (XT.alphaEq actual target) "raw adapter checked type mismatch";
    checked <- Checked.check (XWithData declarations (foldr (\((,) n t) b -> XAbs n t b) body required));
    ensure (XT.alphaEq (Checked.typeOf checked) (foldr (\((,) _ t) b -> XArrow t b) target required))
      "parametric closure checked type mismatch";
    Right (OpenPlan old target body checked required supports reconstruction residual changed disposition)
  };
  -- Production publication is deliberately all-or-none.
  adaptOpen :: Map String String -> [] DataDecl -> Boundary -> [] Slot -> [] ((,) XName XType) -> [] EvidenceScope -> XType -> XTerm -> Either String OpenPlan;
  adaptOpen registry declarations boundary slots ambient scopes expectedType rhs = case boundary of {
    Boundary bid origin managed root expected -> do {
      ensure (eqInt (length expected) (length slots) && uniqueNames expected) "missing/duplicate authoritative slot";
      ensure (uniqueNames (map fst ambient)) "duplicate ambient import identity";
      ensure (uniqueInts (map scopeIdentity scopes)) "duplicate scope identity";
      validateSlots bid root scopes 0 expected slots;
      mapM_ (\scope -> ensure (uniqueNames (map candidateName (scopeCandidates scope))) "duplicate scoped candidate identity") scopes;
      let {
        allCandidates = concatMap scopeCandidates scopes;
        authorized = concatMap scopeCandidates (filter (\scope -> eqInt (scopeIdentity scope) root) scopes);
        allTypes = append ambient (map (\candidate -> (,) (candidateName candidate) (candidateType candidate)) allCandidates)
      };
      consistency <- mergeTypes allTypes;
      combined <- mergeTypes (append ambient (map (\candidate -> (,) (candidateName candidate) (candidateType candidate)) authorized));
      datatypes <- D.validateDeclarations declarations;
      mapM_ (\entry -> Check.termType datatypes M.empty (snd entry)) allTypes;
      actual <- Check.inferWithData datatypes (XEnv M.empty (M.fromList X.compareName combined)) rhs;
      ensure (XT.alphaEq actual expectedType) "original checked type mismatch";
      let { unchanged = finalize declarations datatypes combined expectedType expectedType rhs [] (ordinalsFrom 0 (length slots)) [] False "unchanged-no-plan" };
      if not (eligible origin) || managed || hasForall expectedType then unchanged else do {
        ensure (not (any isGiven authorized)) "unsigned no-givens provenance contradicts scope";
        domains <- prefixTypes (length slots) expectedType;
        validateDomains registry domains slots;
        case directPrefix (length slots) rhs expectedType of {
          Nothing -> unchanged;
          Just ((,) binders result) -> do {
            ensure (sameBinders binders expected) "slot does not name checked outer binder";
            if not (eligibleSlots domains slots)
            then finalize declarations datatypes combined expectedType expectedType rhs
              (map (\((,) n t) -> Retain n t) binders) (ordinalsFrom 0 (length slots)) [] False "unchanged-no-discharge"
            else do {
            let { base = addInt 1 (foldl (\n name -> if n >= X.nameId name then n else X.nameId name) 0 (append (names rhs) (map fst combined))) };
            items <- reconstruct datatypes authorized base 0 domains slots;
            let {
              kept = keptFrom 0 items;
              body = foldr (\((,,) _ n t) b -> XAbs n t b) (foldl XApp rhs (map argument items)) kept;
              target = foldr (\((,,) _ _ t) b -> XArrow t b) result kept;
              dependencies = nubNames (concatMap proofNames items)
            };
            let { preserve = not (null kept) || null slots };
            if preserve
            then finalize declarations datatypes combined expectedType expectedType rhs
              (map (\((,) n t) -> Retain n t) binders) (ordinalsFrom 0 (length slots)) [] False "unchanged-no-discharge"
            else finalize declarations datatypes combined expectedType target body items
              (map (\((,,) index _ _) -> index) kept) dependencies True "monomorphic-reconstruction"
            }
          }
        }
      }
    }
  }
}
