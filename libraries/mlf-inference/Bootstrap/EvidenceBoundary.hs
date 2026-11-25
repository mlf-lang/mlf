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
    XProjection rows selected -> append (map (\((,,) n _ _) -> n) rows) [selected];
    XInstantiationSpine n rows -> (:) n (concatMap (\((,,) _ _ value) -> names value) rows);
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
  freeNames term = freeNamesOnto (\_ -> True) term [];
  -- Produce each free occurrence directly into the consumer's tail. Test
  -- inner scopes before outer ones so rejected variables keep their laziness.
  freeNamesOnto allowed term rest = let {
    after = freeNamesOnto allowed;
    bind name n = not (X.equalName name n) && allowed n;
    bindMany names n = not (any (X.equalName n) names) && allowed n
  } in case term of {
    XVarTerm n -> if allowed n then (:) n rest else rest;
    XAbs n _ body -> freeNamesOnto (bind n) body rest;
    XApp f a -> after f (after a rest);
    XTypeAbs _ _ body -> after body rest;
    XProjection _ _ -> rest;
    XInstantiationSpine n rows -> let {
      arguments = foldr (\((,,) _ _ operand) pending -> after operand pending) rest rows
    } in if allowed n then (:) n arguments else arguments;
    XTypeApp body _ -> after body rest;
    XLet n expr body -> after expr (freeNamesOnto (bind n) body rest);
    XLetRec defs body -> let {
      bound = bindMany (map (\((,,) n _ _) -> n) defs);
      visit = freeNamesOnto bound
    } in foldr (\((,,) _ _ rhs) tail -> visit rhs tail) (visit body rest) defs;
    XCase a _ branches -> after a (foldr (\(XAlternative pat body) tail ->
      freeNamesOnto (bindMany (X.patternNames pat)) body tail) rest branches);
    XWithData _ body -> after body rest;
    XIntTerm _ -> rest;
    XDoubleTerm _ -> rest;
    XBoolTerm _ -> rest;
    XStringTerm _ -> rest;
    XPrimitive _ _ -> rest;
    XConstructor _ _ -> rest
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
  };

  -- Planning from a checked open RHS never constructs a closed wrapper or
  -- rechecks that RHS. A changed recipe is independently checked by its owner.
  data CheckedPlan = KeepChecked | ResolveChecked XTerm XType
    ([] ((,) XName XType)) ([] Candidate) Int ([] XType) ([] Slot);
  checkedPlan registry boundary slots ambient scopes expectedType rhs = case boundary of {
    Boundary bid origin managed root expected -> do {
      ensure (length expected == length slots && uniqueNames expected) "missing/duplicate authoritative slot";
      ensure (uniqueNames (map fst ambient) && uniqueInts (map scopeIdentity scopes)) "duplicate evidence environment identity";
      validateSlots bid root scopes 0 expected slots;
      mapM_ (\scope -> ensure (uniqueNames (map candidateName (scopeCandidates scope))) "duplicate scoped candidate") scopes;
      let { authorized = concatMap scopeCandidates (filter (\scope -> scopeIdentity scope == root) scopes) };
      _ <- mergeTypes (append ambient (map (\c -> (,) (candidateName c) (candidateType c)) (concatMap scopeCandidates scopes)));
      combined <- mergeTypes (append ambient (map (\c -> (,) (candidateName c) (candidateType c)) authorized));
      if not (eligible origin) || managed || hasForall expectedType then Right KeepChecked else do {
        ensure (not (any isGiven authorized)) "unsigned no-givens provenance contradicts scope";
        domains <- prefixTypes (length slots) expectedType;
        validateDomains registry domains slots;
        case directPrefix (length slots) rhs expectedType of {
          Nothing -> Right KeepChecked;
          Just ((,) binders result) -> do {
            ensure (sameBinders binders expected) "slot does not name checked outer binder";
            if not (eligibleSlots domains slots) then Right KeepChecked else
              let { base = addInt 1 (foldl (\n name -> if n >= X.nameId name then n else X.nameId name)
                0 (append (names rhs) (map fst combined))) }
              in Right (ResolveChecked rhs result combined authorized base domains slots)
          }
        }
      }
    }
  };
  -- Every request of a checked plan uses the same sealed candidate environment.
  data RequestBatch = RequestBatch ([] Candidate) ([] ((,) Int XType));
  requestRows (RequestBatch candidates requests) =
    map (\((,) ordinal goal) -> (,,) ordinal goal candidates) requests;
  checkedRequests plan = requestRows (checkedRequestBatch plan);
  checkedRequestBatch plan = case plan of {
    KeepChecked -> RequestBatch [] [];
    ResolveChecked _ _ _ candidates _ domains slots -> RequestBatch candidates (map
      (\((,) ordinal ((,) domain _)) -> (,) ordinal domain)
      (filter (\((,) _ ((,) domain (Slot _ _ _ role _))) -> ordinary role && ground domain)
        (zip (range 0 (length domains - 1)) (zip domains slots))))
  };
  data CheckedRecipe = KeepRecipe | ChangeRecipe XType XTerm ([] ((,) XName XType)) ([] XName);
  finishCheckedPlan plan answers = case plan of {
    KeepChecked -> Right KeepRecipe;
    ResolveChecked rhs result combined candidates base domains slots -> do {
      items <- traverseEither (\((,) ordinal ((,) domain (Slot _ _ _ role _))) ->
        let { retained = Retain (XName (base + ordinal) "retainedEvidence") domain }
        in if not (ordinary role) || not (ground domain) then Right retained else
          case lookup eqInt ordinal answers of {
            Nothing -> Left "missing stable evidence query result";
            Just Nothing -> Right retained;
            Just (Just proof) -> let { used = nubNames (freeNames proof) } in do {
              ensure (all (\n -> any (\c -> X.equalName n (candidateName c)) candidates) used)
                "proof escaped definition evidence scope";
              Right (Discharge proof used)
            }
          }) (zip (range 0 (length domains - 1)) (zip domains slots));
      let { kept = keptFrom 0 items };
      if not (null kept) || null slots then Right KeepRecipe else do {
        let { body = foldl XApp rhs (map argument items);
          supports = nubNames (concatMap proofNames items);
          used = nubNames (freeNames body);
          required = filter (\entry -> any (X.equalName (fst entry)) used) combined };
        ensure (all (\name -> any (X.equalName name) (map fst combined)) used)
          "adapter escaped authorized parameter environment";
        Right (ChangeRecipe result body required supports)
      }
    }
  }
;
  -- The caller supplies source-issued ordinary slots for one evidence scope.
  -- Compare predicate arguments inside the same telescope, preserving the
  -- identities of free type variables. Require a concrete type structure
  -- or a named variable before sharing two wanted predicates.
  comparablePredicate :: XType -> Bool;
  comparablePredicate ty = case ty of {
    XVar _ -> True;
    XCon _ arguments -> all comparablePredicate arguments;
    XApply function argument -> comparablePredicate function && comparablePredicate argument;
    XArrow domain range -> comparablePredicate domain && comparablePredicate range;
    _ -> False
  };
  compactInferredPrefix :: Map String String -> [] ((,,) String String String) ->
    XType -> XTerm -> Either String (Maybe ((,,) XType XTerm ([] String)));
  compactInferredPrefix registry labels ty term = let {
    toParameter ((,) ((,,) spelling className dictionaryName) ((,) n domain)) = do {
      ensure (eqString spelling (X.nameHint n)) "inferred evidence prefix changed source identity";
      validateRole registry (GeneratedOrdinary className dictionaryName) domain;
      Right ((,,) n className domain)
    };
    share ((,) retained aliases) row@((,,) n className domain) =
      let {
        same ((,,) _ previous previousType) =
          eqString className previous && XT.alphaEq domain previousType;
        match = if comparablePredicate domain then find same retained else Nothing
      } in case match of {
        Nothing -> (,) ((:) row retained) aliases;
        Just ((,,) previous _ _) -> (,) retained ((:) ((,,) n domain previous) aliases)
      };
    withoutArguments [] value = value;
    withoutArguments ((:) _ remaining) (XAbs _ _ value) = withoutArguments remaining value;
    withoutArguments _ _ = panic "checked evidence prefix disappeared"
  } in case (,) ty term of {
    (,) (XForall expected bound result) (XTypeAbs variable original body) ->
      if XT.equalTyVar expected variable && XT.alphaEq bound original
      then mapEither (mapOptional (\((,,) t value classes) ->
        (,,) (XForall variable bound t) (XTypeAbs variable original value) classes))
        (compactInferredPrefix registry labels result body)
      else Right Nothing;
    _ -> case directPrefix (length labels) term ty of {
      Nothing -> Right Nothing;
      Just ((,) domains result) -> do {
        parameters <- traverseEither toParameter (zip labels domains);
        case foldlStrict share ((,) [] []) parameters of {
          (,) retained aliases -> if null aliases then Right Nothing else let {
            replacements = M.fromList X.compareName
              (map (\((,,) n domain previous) -> (,) n ((,) domain previous)) aliases);
            owners = M.fromList X.compareName (map (\((,,) n _ _) -> (,) n ()) retained);
            rewritten = rewriteGroundRecursiveReads M.empty replacements owners (withoutArguments labels term)
          } in Right (mapOptional (\renamed ->
            (,,) (foldl (\t ((,,) _ _ domain) -> XArrow domain t) result retained)
              (foldl (\value ((,,) n _ domain) -> XAbs n domain value) renamed retained)
              (reverse (map (\((,,) _ className _) -> className) retained))) rewritten)
        }
      }
    }
  };

  -- A checked result-polymorphic dictionary arrow has the form
  -- forall (r >= suffix). D -> r. Its body instantiates the next layer at r.
  -- Closed D can move across this quantifier. Keep the last occurrence of
  -- each predicate so the innermost result abstraction stays in place.
  compactBoundPrefix :: Map String String -> [] ((,,) String String String) ->
    XType -> XTerm -> Maybe ((,,) XType XTerm ([] String));
  compactBoundPrefix registry labels ty term = let {
    scan rows remaining scheme value = case (,,) remaining scheme value of {
      (,,) ((:) ((,,) label cls dict) rest) (XForall v suffix (XArrow domain@(XCon head _) (XVar result)))
        (XTypeAbs declared bound (XAbs name actual body)) ->
        if not (XT.equalTyVar v result && eqString label (X.nameHint name) &&
          ground domain && XT.alphaEq domain actual && eqString dict head &&
          case M.lookup compareString cls registry of { Just known -> eqString known dict; _ -> False })
        then Nothing else let { next = (:) ((,,,) name cls domain declared) rows } in case rest of {
          [] -> if XT.alphaEq suffix bound then Just ((,,) next bound body) else Nothing;
          _ -> case body of {
            XTypeApp child (XHyp used) -> if XT.equalTyVar declared used then scan next rest suffix child else Nothing;
            _ -> Nothing
          }
        };
      _ -> Nothing
    };
    share ((,) retained aliases) row@((,,,) n cls domain _) = case find
      (\((,,,) _ prior old _) -> eqString cls prior && XT.alphaEq domain old) retained of {
        Just ((,,,) previous _ _ _) -> (,) retained (M.insert X.compareName n ((,) domain previous) aliases);
        Nothing -> (,) ((:) row retained) aliases
    };
    layer ((,,,) n _ domain v) bound body =
      (,) (XForall v bound (XArrow domain (XVar v))) (XTypeAbs v bound (XAbs n domain body));
    wrap ((,) bound child) row@((,,,) _ _ _ v) = layer row bound (XTypeApp child (XHyp v))
  } in do {
    (,,) rows bound original <- scan [] labels ty term;
    case foldlStrict share ((,) [] M.empty) rows of {
      (,) retained aliases -> if M.size aliases == 0 then Nothing else do {
        let { owners = M.fromList X.compareName (map (\((,,,) n _ _ _) -> (,) n ()) retained) };
        body <- rewriteGroundRecursiveReads M.empty aliases owners original;
        case reverse retained of {
          (:) last others -> case foldlStrict wrap (layer last bound body) others of {
            (,) result rhs -> Just ((,,) result rhs (map (\((,,,) _ cls _ _) -> cls) retained))
          };
          [] -> Nothing
        }
      }
    }
  };

  -- The source planner issued these labels for every member of one unsigned
  -- SCC. The checked term supplies the actual predicate types.
  data GroundRecursiveMember =
    GroundRecursiveMember XName ([] ((,,) String String String)) XType XTerm;
  data GroundRecursivePrefix = GroundRecursivePrefix XType ([] ((,) XTyVar XType))
    ([] ((,) XName XType)) XTerm;
  data GroundRecursiveRow = GroundRecursiveRow XName XType ([] ((,) XTyVar XType))
    ([] ((,) XName XType)) XTerm;
  data GroundRecursiveResolvedRow = GroundRecursiveResolvedRow XName XType ([] ((,) XTyVar XType))
    ([] ((,,) XName XType XName)) XTerm;
  data GroundRecursivePlan = GroundRecursivePlan ([] Candidate) ([] XType) ([] GroundRecursiveRow);
  data GroundRecursiveCall = GroundRecursiveCall Int ([] ((,) XType XName));

  checkedGroundRecursivePlan :: Map String String -> [] Candidate -> [] GroundRecursiveMember ->
    Either String (Maybe GroundRecursivePlan);
  checkedGroundRecursivePlan registry authorized members = let {
    memberName (GroundRecursiveMember name _ _ _) = name;
    domains (GroundRecursiveRow _ _ _ parameters _) = map snd parameters;
    insert seen ty = if any (XT.alphaEq ty) seen then seen else (:) ty seen;
    validate ((,) ((,,) label cls dictionary) ((,) name domain)) = do {
      ensure (eqString label (X.nameHint name)) "recursive evidence prefix changed source identity";
      validateRole registry (GeneratedOrdinary cls dictionary) domain
    };
    plan (GroundRecursiveMember name labels ty rhs) =
      case groundRecursivePrefix (length labels) ty rhs of {
        Just (GroundRecursivePrefix target abstractions parameters body) -> do {
          traverseEither validate (zip labels parameters);
          Right (if not (null labels) && all (compose ground snd) parameters
            then Just (GroundRecursiveRow name target abstractions parameters body) else Nothing)
        };
        _ -> Right Nothing
      }
  } in do {
    ensure (not (any isGiven authorized)) "unsigned recursive evidence scope contains givens";
    ensure (uniqueNames (map memberName members) && uniqueNames (map candidateName authorized))
      "duplicate recursive evidence owner or candidate";
    planned <- traverseEither plan members;
    Right (case mapM (\entry -> entry) planned of {
      Just rows -> if length rows < 2 || not (callableRecursiveRows rows) then Nothing else
        Just (GroundRecursivePlan authorized (reverse (foldlStrict insert [] (concatMap domains rows))) rows);
      Nothing -> Nothing
    })
  };
  groundRecursiveRequests :: GroundRecursivePlan -> [] ((,,) Int XType ([] Candidate));
  groundRecursiveRequests plan = requestRows (groundRecursiveRequestBatch plan);
  groundRecursiveRequestBatch (GroundRecursivePlan candidates domains _) = RequestBatch candidates
    (zip (range 0 (length domains - 1)) domains);

  -- Only a definition-site instance declaration, possibly instantiated at
  -- closed types, supplies the same term-level value at every peer call.
  finishGroundRecursivePlan = finishGroundRecursivePlanIn D.emptyDataEnv;
  finishGroundRecursivePlanIn :: DataEnv -> GroundRecursivePlan -> [] ((,) Int (Maybe XTerm)) ->
    Either String (Maybe ((,) ([] ((,,) XName XType XTerm)) ([] XName)));
  finishGroundRecursivePlanIn datatypes (GroundRecursivePlan authorized domains members) answers = let {
    candidates = M.fromList X.compareName (map (\candidate -> (,) (candidateName candidate) candidate) authorized);
    -- Type applications erase to the same declaration. Validate each step in
    -- the definition's data environment with an empty type-variable scope.
    -- Evidence applications that require another term keep the original ABI.
    instanceProof value = case value of {
      XVarTerm name -> case M.lookup X.compareName name candidates of {
        Just (Candidate InstanceEvidence found ty) -> do {
          ensure (eqString (X.nameHint found) (X.nameHint name)) "recursive instance proof changed identity or type";
          Right (Just ((,) name ty))
        };
        Just _ -> Right Nothing;
        Nothing -> Left "recursive evidence proof escaped definition scope"
      };
      XTypeApp term proof -> do {
        source <- instanceProof term;
        case source of {
          Nothing -> Right Nothing;
          Just ((,) name ty) -> case Check.checkComputationIn datatypes M.empty proof ty of {
            Right result -> Right (Just ((,) name result));
            Left _ -> Right Nothing
          }
        }
      };
      _ -> Right Nothing
    };
    checkedAnswer ((,) ordinal domain) = case lookup eqInt ordinal answers of {
      Nothing -> Left "missing stable recursive evidence query result";
      Just Nothing -> Right Nothing;
      Just (Just value) -> do {
        root <- instanceProof value;
        case root of {
          Nothing -> Right Nothing;
          Just ((,) name ty) -> do {
            ensure (XT.alphaEq ty domain) "recursive instance proof changed identity or type";
            Right (Just ((,) domain ((,) name value)))
          }
        }
      }
    };
    aliasesFor available (GroundRecursiveRow name ty abstractions parameters body) = do {
      aliases <- mapM (\((,) binder domain) -> mapOptional (\entry -> (,,) binder domain (fst (snd entry)))
        (find (\entry -> XT.alphaEq (fst entry) domain) available)) parameters;
      Just (GroundRecursiveResolvedRow name ty abstractions aliases body)
    };
    call (GroundRecursiveResolvedRow name _ abstractions aliases _) =
      (,) name (GroundRecursiveCall (length abstractions) (map (\((,,) _ domain proof) -> (,) domain proof) aliases));
    rewrite known calls proofs (GroundRecursiveResolvedRow name ty abstractions aliases body) = do {
      let { local = M.fromList X.compareName (map (\((,,) binder domain proof) -> (,) binder ((,) domain proof)) aliases) };
      if length aliases /= M.size local || M.member X.compareName name proofs ||
         any (\binder -> M.member X.compareName binder calls || M.member X.compareName binder proofs) (M.keys local)
      then Nothing else do {
        result <- rewriteGroundRecursiveReadsWith (\ty name -> mapOptional (compose snd snd)
          (find (\entry -> X.equalName name (fst (snd entry)) && XT.alphaEq ty (fst entry)) known))
          calls local proofs body;
        Just ((,,) name ty (foldr (\((,) var bound) rest -> XTypeAbs var bound rest) result abstractions))
      }
    }
  } in do {
    ensure (length domains == length answers) "recursive evidence query count changed";
    proofs <- traverseEither checkedAnswer (zip (range 0 (length domains - 1)) domains);
    Right (do {
      available <- mapM (\entry -> entry) proofs;
      rows <- mapM (aliasesFor available) members;
      let {
        calls = M.fromList X.compareName (map call rows);
        names = nubNames (map (compose fst snd) available);
        proofNames = M.fromList X.compareName (map (\name -> (,) name ()) names)
      };
      definitions <- mapM (rewrite available calls proofNames) rows;
      Just ((,) definitions names)
    })
  };

  -- Scan only paired Star-bottom telescopes. The rhs's type abstraction IDs
  -- can differ from the corresponding declared type binders in a solved SCC.
  groundRecursivePrefix :: Int -> XType -> XTerm -> Maybe GroundRecursivePrefix;
  groundRecursivePrefix count ty term = case (,) ty term of {
    (,) (XForall expected bound result) (XTypeAbs actual original body) ->
      if XT.alphaEq bound XBot && XT.alphaEq original XBot then
        mapOptional (\(GroundRecursivePrefix following abstractions domains value) ->
          GroundRecursivePrefix (XForall expected bound following) ((:) ((,) actual original) abstractions) domains value)
          (groundRecursivePrefix count result body)
      else Nothing;
    (,) (XForall _ _ _) _ -> Nothing;
    (,) _ (XTypeAbs _ _ _) -> Nothing;
    _ -> instantiatedGroundPrefix count ty term
  };
  -- Removing dictionary lambdas must leave each recursive value callable.
  -- The source may partially apply a peer to literals. Check its resolved
  -- identity and residual lambda arity before requesting definition-site
  -- evidence. The rewrite separately verifies each forwarded dictionary.
  callableRecursiveRows rows = let {
    arity value = case value of {
      XAbs _ _ inner -> 1 + arity inner;
      XTypeAbs _ _ inner -> arity inner;
      XTypeApp inner _ -> arity inner;
      _ -> 0
    };
    member (GroundRecursiveRow name _ _ parameters body) =
      (,) name ((,) (length parameters) (arity body));
    functions = M.fromList X.compareName (map member rows);
    forwarded ordinary dictionaries value = case value of {
      XApp inner (XVarTerm _) -> forwarded ordinary (dictionaries + 1) inner;
      XTypeApp inner _ -> forwarded ordinary dictionaries inner;
      XVarTerm name -> case M.lookup X.compareName name functions of {
        Just ((,) required available) -> ordinary > 0 && ordinary < available && dictionaries == required;
        Nothing -> False
      };
      _ -> False
    };
    partial count value = case value of {
      XApp inner (XBoolTerm _) -> partial (count + 1) inner;
      XApp inner (XIntTerm _) -> partial (count + 1) inner;
      XTypeAbs _ _ inner -> partial count inner;
      XTypeApp inner _ -> partial count inner;
      _ -> forwarded count 0 value
    };
    callable (GroundRecursiveRow _ _ _ _ body) = isFunction body;
    isFunction value = case value of {
      XAbs _ _ _ -> True;
      XTypeAbs _ _ inner -> isFunction inner;
      XTypeApp inner _ -> isFunction inner;
      _ -> partial 0 value
    }
  } in all callable rows;
  -- Keep the type-only wrapper in its original order. Each term domain
  -- removed below it must agree with the closed, published argument type.
  instantiatedGroundPrefix :: Int -> XType -> XTerm -> Maybe GroundRecursivePrefix;
  instantiatedGroundPrefix count ty term = case term of {
    XTypeApp inner proof -> mapOptional
      (\(GroundRecursivePrefix result qs params body) -> GroundRecursivePrefix result qs params (XTypeApp body proof))
      (instantiatedGroundPrefix count ty inner);
    XTypeAbs var bound inner -> mapOptional
      (\(GroundRecursivePrefix result qs params body) -> GroundRecursivePrefix result qs params (XTypeAbs var bound body))
      (instantiatedGroundPrefix count ty inner);
    _ -> do {
      (,) domains result <- directPrefix count term ty;
      body <- dropGroundRecursiveLambdas count term;
      Just (GroundRecursivePrefix result [] domains body)
    }
  };
  dropGroundRecursiveLambdas :: Int -> XTerm -> Maybe XTerm;
  dropGroundRecursiveLambdas count term =
    if count == 0 then Just term else case term of {
      XAbs _ _ body -> dropGroundRecursiveLambdas (count - 1) body;
      _ -> Nothing
    };

  -- A peer head may refine and eliminate its leading quantified parameters.
  -- Such a proof is unchanged by deleting ground term arrows below them.
  groundRecursiveProof :: Int -> XComputation -> Bool;
  groundRecursiveProof count proof = let {
    flatten computation rest = case computation of {
      XRefl -> Just rest;
      XThen first second -> do { next <- flatten second rest; flatten first next };
      XInner (XBottom _) -> Just ((:) True rest);
      XElim -> Just ((:) False rest);
      _ -> Nothing
    };
    steps remaining items = case items of {
      [] -> remaining == 0;
      (:) True ((:) False tail) -> remaining > 0 && steps (remaining - 1) tail;
      _ -> False
    }
  } in case flatten proof [] of {
    Nothing -> False;
    Just words -> steps count words
  };

  rewriteGroundRecursiveReads :: Map XName GroundRecursiveCall ->
    Map XName ((,) XType XName) -> Map XName () -> XTerm -> Maybe XTerm;
  rewriteGroundRecursiveReads = rewriteGroundRecursiveReadsWith (\_ name -> Just (XVarTerm name));
  rewriteGroundRecursiveReadsWith replacement calls aliases proofs = let {
    safe name = not (M.member X.compareName name calls ||
      M.member X.compareName name aliases || M.member X.compareName name proofs);
    dropArgs expected actual = case (,) expected actual of {
      (,) [] arguments -> Just arguments;
      (,) ((:) ((,) domain proof) rest) ((:) (XVarTerm binder) arguments) ->
        case M.lookup X.compareName binder aliases of {
          Just ((,) ty actualProof) -> if XT.alphaEq ty domain && X.equalName proof actualProof
            then dropArgs rest arguments else Nothing;
          Nothing -> Nothing
        };
      _ -> Nothing
    };
    spine args value = case value of {
      XApp f x -> spine ((:) x args) f;
      XInstantiationSpine name rows -> spine args (X.expandInstantiationSpine name rows);
      _ -> (,) value args
    };
    headUse value = case value of {
      XVarTerm name -> Just ((,) name XRefl);
      XTypeApp (XVarTerm name) proof -> Just ((,) name proof);
      _ -> Nothing
    };
    changeCall head args = case headUse head of {
      Just ((,) name proof) -> case M.lookup X.compareName name calls of {
        Just (GroundRecursiveCall count expected) ->
          if not (groundRecursiveProof count proof) then Nothing else do {
            rest <- dropArgs expected args;
            rewritten <- mapM visit rest;
            Just (foldl XApp head rewritten)
          };
        Nothing -> ordinaryCall head args
      };
      Nothing -> ordinaryCall head args
    };
    ordinaryCall head args = do {
      callee <- visit head;
      arguments <- mapM visit args;
      Just (foldl XApp callee arguments)
    };
    visit value = case value of {
      XApp _ _ -> case spine [] value of { (,) head args -> changeCall head args };
      XInstantiationSpine name rows -> visit (X.expandInstantiationSpine name rows);
      XVarTerm name ->
        if M.member X.compareName name calls then Nothing else
        case M.lookup X.compareName name aliases of {
          Nothing -> Just value; Just ((,) ty proof) -> replacement ty proof
        };
      XAbs name ty body -> if safe name then mapOptional (XAbs name ty) (visit body) else Nothing;
      XTypeAbs var bound body -> mapOptional (XTypeAbs var bound) (visit body);
      XTypeApp body proof -> mapOptional (\term -> XTypeApp term proof) (visit body);
      XLet name rhs body -> if not (safe name) then Nothing else do {
        binding <- visit rhs;
        result <- visit body;
        Just (XLet name binding result)
      };
      XLetRec definitions body ->
        if not (all (\((,,) name _ _) -> safe name) definitions) then Nothing else do {
          bindings <- mapM (\((,,) name ty rhs) -> mapOptional (\result -> (,,) name ty result) (visit rhs)) definitions;
          result <- visit body;
          Just (XLetRec bindings result)
        };
      XCase scrutinee ty alternatives -> do {
        selected <- visit scrutinee;
        branches <- mapM (\(XAlternative pattern body) -> if all safe (X.patternNames pattern)
          then mapOptional (XAlternative pattern) (visit body) else Nothing) alternatives;
        Just (XCase selected ty branches)
      };
      XWithData _ _ -> Nothing;
      XProjection _ _ -> Just value;
      XIntTerm _ -> Just value;
      XDoubleTerm _ -> Just value;
      XBoolTerm _ -> Just value;
      XStringTerm _ -> Just value;
      XPrimitive _ _ -> Just value;
      XConstructor _ _ -> Just value
    }
  } in visit;
}
