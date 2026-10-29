-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.X.Checked (CheckedTerm, check, term, typeOf, declarationBindings, ContextPool, contextPool, checkWithContexts, validateContext, LinkedSpine, emptySpine, appendSpine, finishSpine, materializeSpine, FreshFragment, freshFragment, freshSerial, freshTerm, freshBindings, appendFreshSpine, latestSpineBody) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Std as L;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  -- The constructor is private. Ordinary receipts pair a term with its own
  -- independent check; composition below derives a term and type only from
  -- such evidence. Callers cannot attach a claimed type to raw syntax.
  data CheckedTerm = CheckedTerm XTerm XType (Either String ([] ((,) XName XType)));
  check :: XTerm -> Either String CheckedTerm;
  check source =
    do {
      answer <- Check.checkClosedWithBindings source;
      case answer of {
        (,) ty bindings -> Right (CheckedTerm source ty bindings)
      }
    };
  -- Opaque, local memo of exact datatype ASTs and deferred validations. No
  -- caller-supplied environment or equality predicate can manufacture a proof.
  data ContextPool = ContextPool ([] ((,) ([] DataDecl) (Either String DataEnv)));
  contextPool declarations = ContextPool (L.map (\ds -> (,) ds (D.validateDeclarations ds)) declarations);
  contextIn (ContextPool entries) declarations = contextLookup entries declarations;
  contextLookup entries declarations = case entries of {
    [] -> D.validateDeclarations declarations;
    (:) ((,) recorded result) rest -> if L.eqList eqDataDecl recorded declarations
      then result else contextLookup rest declarations
  };
  validateContext pool declarations = do { contextIn pool declarations; Right () };
  checkWithContexts pool source = case source of {
    XWithData declarations body -> do {
      context <- contextIn pool declarations;
      answer <- Check.inferParameterSpine context Check.emptyEnv body;
      case answer of { (,) ty bindings -> Right (CheckedTerm source ty bindings) }
    };
    _ -> check source
  };
  eqField :: Field -> Field -> Bool;
  eqField a b =
    case a of {
      Parameter x0 ->
        case b of {
          Parameter y0 -> eqString x0 y0;
          _ -> False
        };
      Function x0 x1 ->
        case b of {
          Function y0 y1 -> (eqField x0 y0 && eqField x1 y1);
          _ -> False
        };
      Applied x0 x1 ->
        case b of {
          Applied y0 y1 -> (eqString x0 y0 && L.eqList eqField x1 y1);
          _ -> False
        };
      Application x0 x1 ->
        case b of {
          Application y0 y1 -> (eqField x0 y0 && eqField x1 y1);
          _ -> False
        };
      Quantified x0 x1 x2 ->
        case b of {
          Quantified y0 y1 y2 -> (eqString x0 y0 && (L.eqKind x1 y1 && eqField x2 y2));
          _ -> False
        }
    };
  eqConstructorDecl :: ConstructorDecl -> ConstructorDecl -> Bool;
  eqConstructorDecl a b =
    case a of {
      ConstructorDecl x0 x1 ->
        case b of {
          ConstructorDecl y0 y1 -> (eqString x0 y0 && L.eqList eqField x1 y1)
        }
    };
  eqDataDecl :: DataDecl -> DataDecl -> Bool;
  eqDataDecl a b =
    case a of {
      DataDecl x0 x1 x2 ->
        case b of {
          DataDecl y0 y1 y2 ->
            (eqString x0 y0 && (L.eqList eqString x1 y1 && L.eqList eqConstructorDecl x2 y2));
          _ -> False
        };
      DataDeclK x0 x1 x2 ->
        case b of {
          DataDeclK y0 y1 y2 ->
            (eqString x0 y0 &&
             (L.eqList (L.eqPair eqString L.eqKind) x1 y1 && L.eqList eqConstructorDecl x2 y2));
          _ -> False
        }
    };
  term :: CheckedTerm -> XTerm;
  term (CheckedTerm source _ _) = source;
  typeOf :: CheckedTerm -> XType;
  typeOf (CheckedTerm _ ty _) = ty;
  -- Inferred by an independent check of this exact term. Ordinary receipts
  -- share their initial check; composed receipts defer the inventory query.
  -- The inventory excludes leading import parameters and RHS-local binders.
  declarationBindings :: CheckedTerm -> Either String ([] ((,) XName XType));
  declarationBindings (CheckedTerm _ _ bindings) = bindings;
  -- Construction evidence is private and contains only independently checked
  -- fragments. No raw linked state, caller type, renamer or DataEnv enters.
  data LinkedSpine = LinkedSpine Int (Map String ((,) XName XType))
    ([] XTerm) ([] ((,) ([] DataDecl) XTerm));
  emptySpine = LinkedSpine 0 M.empty [] [];
  compositionParts source = case source of {
    XWithData declarations body -> (,) declarations body;
    _ -> (,) [] source
  };
  compositionFresh serial source = let {
    ids = IS.toList (compositionTermIdentities source IS.empty);
    replacements = IM.fromDistinctAscList (zip ids (range serial (serial + length ids - 1)));
    identity = \n -> IM.get n replacements;
    name = \(XName n hint) -> XName (identity n) hint
  } in (,,) (serial + length ids)
    (compositionMapTerm name (\(XTyVar n) -> XTyVar (identity n)) source) name;
  compositionParameters source = case source of {
    XAbs name ty body -> let { next = compositionParameters body }
      in (,) ((:) ((,) name ty) (fst next)) (snd next);
    _ -> (,) [] source
  };
  -- Only exact leading parameters of an actual checked term reach this
  -- private substitution. Check.inferParameterSpine retains those identities
  -- throughout termEnv; inferIn/inferRecursiveScope/checkAlternative reject
  -- every binder already present there. XTypeAbs preserves termEnv. Injective
  -- freshening preserves that no-rebinding proof, so no second RHS scan is
  -- needed. Raw ImportedRoot.remove still performs its explicit binder scan.
  compositionSubstitute [] _ body = Right body;
  compositionSubstitute parameters available body = do {
    let { names = map fst parameters };
    ensure (length names == length (nubBy X.equalName names)) "composition duplicate parameter identity";
    replacements <- traverseEither (\((,) name key) -> case M.lookup compareString key available of {
      Nothing -> Left ("composition missing import: " ++ key);
      Just ((,) actual _) -> Right ((,) name actual)
    }) parameters;
    let { substitutions = M.fromList X.compareName replacements };
    Right (compositionMapTerm (\name -> M.findWithDefault X.compareName name name substitutions) (\a -> a) body)
  };
  compositionImport available ((,) name ty) = case M.lookup compareString (X.nameHint name) available of {
    Nothing -> Left ("composition missing import: " ++ X.nameHint name);
    Just ((,) _ expected) -> ensure (T.alphaEq ty expected) "composition import type mismatch"
  };
  compositionGraft :: XTerm -> XTerm -> Either String XTerm;
  compositionGraft spine body = case spine of {
    XLet name rhs rest -> mapEither (XLet name rhs) (compositionGraft rest body);
    XLetRec definitions rest -> mapEither (XLetRec definitions) (compositionGraft rest body);
    XConstructor "()" [] -> Right body;
    _ -> Left "composition invalid declaration spine"
  };
  -- A fresh receipt binds its projections to one checked source and an exact
  -- serial interval. Admission may inspect these values but cannot fabricate it.
  data FreshFragment = FreshFragment Int Int XTerm
    (Either String ([] ((,) XName XType))) XTerm;
  freshFragment serial checked = let {
    fresh = compositionFresh serial (term checked);
    next = case fresh of { (,,) value _ _ -> value };
    renamed = case fresh of { (,,) _ value _ -> value };
    rename = case fresh of { (,,) _ _ value -> value }
  } in FreshFragment serial next renamed
    (mapEither (map (\((,) name ty) -> (,) (rename name) ty)) (declarationBindings checked)) (term checked);
  freshSerial (FreshFragment _ next _ _ _) = next;
  freshTerm (FreshFragment _ _ source _ _) = source;
  freshBindings (FreshFragment _ _ _ bindings _) = bindings;
  latestSpineBody (LinkedSpine _ _ bodies _) = case bodies of {
    (:) body _ -> Just body;
    [] -> Nothing
  };
  appendSpine :: LinkedSpine -> CheckedTerm -> Either String LinkedSpine;
  appendSpine linked checked = case linked of {
    LinkedSpine serial _ _ _ -> appendFreshSpine linked (freshFragment serial checked)
  };
  appendFreshSpine :: LinkedSpine -> FreshFragment -> Either String LinkedSpine;
  appendFreshSpine (LinkedSpine serial available bodies contexts)
      (FreshFragment start next renamed bindings original) = do {
    ensure (serial == start) "composition fresh interval mismatch";
    own <- bindings;
    let { parts = compositionParts renamed;
          split = compositionParameters (snd parts);
          parameters = fst split;
          implementation = snd split;
          exports = map (\((,) name ty) -> (,) (X.nameHint name) ((,) name ty)) own };
    traverseEither (compositionImport available) parameters;
    ensure (length exports == length (nubBy eqString (map fst exports))) "composition duplicate export name";
    ensure (all (\entry -> not (M.member compareString (fst entry) available)) exports)
      "composition export already linked";
    linked <- compositionSubstitute (map (\entry -> (,) (fst entry) (X.nameHint (fst entry))) parameters) available implementation;
    compositionGraft linked (XConstructor "()" []);
    Right (LinkedSpine next (M.union compareString (M.fromList compareString exports) available)
      ((:) linked bodies) ((:) ((,) (fst parts) original) contexts))
  };
  compositionRootImports requested available source ty = case requested of {
    [] -> Right ((,,) [] source ty);
    (:) ((,) key hint) rest -> case (,) source ty of {
      (,) (XAbs name actual body) (XArrow expected result) -> do {
        ensure (eqString (X.nameHint name) hint && T.alphaEq actual expected) "composition root wrapper mismatch";
        case M.lookup compareString key available of {
          Nothing -> Left ("composition missing root import: " ++ key);
          Just ((,) _ exported) -> ensure (T.alphaEq actual exported) "composition root import type mismatch"
        };
        next <- compositionRootImports rest available body result;
        case next of { (,,) names inner answer -> Right ((,,) ((:) ((,) name key) names) inner answer) }
      };
      _ -> Left "composition root import prefix missing"
    }
  };
  compositionRemoveEmpty :: XTerm -> Either String XTerm;
  compositionRemoveEmpty source = case source of {
    XTypeAbs variable bound body -> mapEither (XTypeAbs variable bound) (compositionRemoveEmpty body);
    XTypeApp body proof -> mapEither (\value -> XTypeApp value proof) (compositionRemoveEmpty body);
    XLetRec [] body -> Right body;
    _ -> Left "composition root empty group missing"
  };
  -- Unknown XCon names use a fallback kind in the independent checker.
  -- Weakening must not give those names a newly declared, different meaning.
  compositionSameDeclaration a b =
    eqString (D.datatypeName a) (D.datatypeName b) &&
    eqList (eqPair eqString eqKind) (D.datatypeBinders a) (D.datatypeBinders b) &&
    eqList eqConstructorDecl (D.datatypeConstructors a) (D.datatypeConstructors b);
  compositionContextExtensions full fullNames declarations = do {
    traverseEither (\d -> case M.lookup compareString (D.datatypeName d) full of {
      Nothing -> Left "composition datatype layout changed";
      Just actual -> ensure (compositionSameDeclaration d actual) "composition datatype layout changed"
    }) declarations;
    Right (Set.difference compareString fullNames
      (Set.fromList compareString (map D.datatypeName declarations)))
  };
  compositionContextLookup declarations memo = case memo of {
    [] -> Nothing;
    (:) ((,) previous introduced) rest ->
      if eqList compositionSameDeclaration previous declarations then Just introduced
      else compositionContextLookup declarations rest
  };
  compositionContexts declarations contexts = let {
    full = M.fromList compareString (map (\d -> (,) (D.datatypeName d) d) declarations);
    fullNames = Set.fromList compareString (map D.datatypeName declarations)
  } in compositionContextsFrom full fullNames [((,) declarations Set.empty)] contexts;
  compositionContextsFrom full fullNames memo contexts = case contexts of {
    [] -> Right ();
    (:) ((,) declarations source) rest -> do {
      selected <- case compositionContextLookup declarations memo of {
        Just introduced -> Right ((,) memo introduced);
        Nothing -> do {
          introduced <- compositionContextExtensions full fullNames declarations;
          Right ((,) ((:) ((,) declarations introduced) memo) introduced)
        }
      };
      let { introduced = snd selected };
      if Set.null introduced then Right () else
        ensure (all (\name -> not (Set.member compareString name introduced))
          (Set.toList (compositionConstructorNames source)))
          "composition datatype extension changes an unresolved type constructor";
      compositionContextsFrom full fullNames (fst selected) rest
    }
  };
  finishSpine :: LinkedSpine -> [] ((,) String String) -> CheckedTerm -> Either String CheckedTerm;
  finishSpine (LinkedSpine serial available bodies contexts) requested checked = do {
    let { fresh = compositionFresh serial (term checked);
          source = case fresh of { (,,) _ value _ -> value };
          parts = compositionParts source;
          declarations = fst parts };
    compositionContexts declarations contexts;
    imports <- compositionRootImports requested available (snd parts) (typeOf checked);
    case imports of { (,,) parameters body answer -> do {
      inner <- if null requested then Right body else compositionRemoveEmpty body;
      actual <- compositionSubstitute parameters available inner;
      grafted <- foldEither (\rest spine -> compositionGraft spine rest) actual bodies;
      let { result = XWithData declarations grafted;
            inventory = do { independently <- Check.checkClosedWithBindings result; snd independently } };
      -- Alpha-equivalent closed export contracts and capture-free variable
      -- substitution preserve the derived root result type. The optional
      -- fragment inventory remains an independent, deferred exact query.
      Right (CheckedTerm result answer inventory)
    } }
  };
  -- Partial composition consumes the exact actual import prefix. Kept native
  -- binders remain outside the graft; no caller type or raw linked state enters.
  -- All occurrences (including unused local RHSs) count as uses. The original
  -- checker proves no inner binder reuses a leading parameter identity.
  compositionVariableReads source = let {
    child = compositionVariableReads;
    join = Set.unions X.compareName
  } in case source of {
    XVarTerm name -> Set.singleton name;
    XAbs _ _ body -> child body;
    XApp a b -> join [child a, child b];
    XTypeAbs _ _ body -> child body;
    XTypeApp body _ -> child body;
    XLet _ rhs body -> join [child rhs, child body];
    XLetRec definitions body -> join ((:) (child body)
      (map (\((,,) _ _ rhs) -> child rhs) definitions));
    XCase subject _ alternatives -> join ((:) (child subject)
      (map (\(XAlternative _ body) -> child body) alternatives));
    XWithData _ body -> child body;
    _ -> Set.empty
  };
  compositionPartialPrefix requested source ty = case requested of {
    [] -> Right ((,,) [] source ty);
    (:) ((,) key hint) rest -> case (,) source ty of {
      (,) (XAbs name actual body) (XArrow expected result) -> do {
        ensure (eqString (X.nameHint name) hint && T.alphaEq actual expected)
          "partial composition root wrapper mismatch";
        next <- compositionPartialPrefix rest body result;
        case next of { (,,) parameters inner answer ->
          Right ((,,) ((:) ((,,) key name actual) parameters) inner answer) }
      };
      _ -> Left "partial composition root import prefix missing"
    }
  };
  materializeSpine :: LinkedSpine -> [] ((,) String String) -> CheckedTerm ->
    Either String ((,) CheckedTerm ([] String));
  materializeSpine (LinkedSpine serial available bodies contexts) requested checked = do {
    ensure (length requested == length (nubBy eqString (map fst requested)))
      "partial composition duplicate import key";
    ensure (length requested == length (nubBy eqString (map snd requested)))
      "partial composition ambiguous import hint";
    let { fresh = compositionFresh serial (term checked);
          source = case fresh of { (,,) _ value _ -> value };
          parts = compositionParts source;
          declarations = fst parts };
    compositionContexts declarations contexts;
    split <- compositionPartialPrefix requested (snd parts) (typeOf checked);
    case split of { (,,) parameters body answer -> do {
      inner <- if null requested then Right body else compositionRemoveEmpty body;
      let { reads = compositionVariableReads inner;
            used = filter (\((,,) _ name _) -> Set.member X.compareName name reads) parameters;
            admitted = filter (\((,,) key _ _) -> M.member compareString key available) parameters;
            provided = filter (\((,,) key _ _) -> M.member compareString key available) used;
            remaining = filter (\((,,) key _ _) -> not (M.member compareString key available)) used };
      traverseEither (\((,,) key _ actual) -> case M.lookup compareString key available of {
        Nothing -> Left "partial composition lost admitted export";
        Just ((,) _ expected) -> ensure (T.alphaEq actual expected)
          "partial composition import type mismatch"
      }) admitted;
      substituted <- compositionSubstitute (map (\((,,) key name _) -> (,) name key) provided) available inner;
      grafted <- foldEither (\rest spine -> compositionGraft spine rest) substituted bodies;
      let { wrapped = foldr (\((,,) _ name ty) rest -> XAbs name ty rest) grafted remaining;
            result = XWithData declarations wrapped;
            derived = foldr (\((,,) _ _ ty) rest -> XArrow ty rest) answer remaining;
            inventory = do { independently <- Check.checkClosedWithBindings result; snd independently } };
      Right ((,) (CheckedTerm result derived inventory) (map (\((,,) key _ _) -> key) remaining))
    } }
  };
  compositionTypeNames ty = case ty of {
    XCon name arguments -> Set.insert compareString name (Set.unions compareString (map compositionTypeNames arguments));
    XArrow a b -> Set.union compareString (compositionTypeNames a) (compositionTypeNames b);
    XApply a b -> Set.union compareString (compositionTypeNames a) (compositionTypeNames b);
    XForall _ bound body -> Set.union compareString (compositionTypeNames bound) (compositionTypeNames body);
    _ -> Set.empty
  };
  compositionProofNames proof = case proof of {
    XBottom ty -> compositionTypeNames ty;
    XInner body -> compositionProofNames body;
    XOuter _ body -> compositionProofNames body;
    XThen a b -> Set.union compareString (compositionProofNames a) (compositionProofNames b);
    _ -> Set.empty
  };
  compositionConstructorNames source = let {
    child = compositionConstructorNames;
    join = Set.unions compareString;
    ty = compositionTypeNames
  } in case source of {
    XAbs _ annotation body -> join [ty annotation, child body];
    XApp a b -> join [child a, child b];
    XTypeAbs _ bound body -> join [ty bound, child body];
    XTypeApp body proof -> join [child body, compositionProofNames proof];
    XLet _ rhs body -> join [child rhs, child body];
    XLetRec definitions body -> join ((:) (child body) (concatMap (\((,,) _ annotation rhs) -> [ty annotation, child rhs]) definitions));
    XPrimitive _ arguments -> join (map ty arguments);
    XConstructor _ arguments -> join (map ty arguments);
    XCase subject result alternatives -> join ((:) (child subject) ((:) (ty result)
      (map (\(XAlternative _ body) -> child body) alternatives)));
    XWithData _ body -> child body;
    _ -> Set.empty
  };
  compositionMapType :: (XTyVar -> XTyVar) -> XType -> XType;
  compositionMapType variable ty =
    case ty of {
      XVar a -> XVar (variable a);
      XArrow a b -> XArrow (compositionMapType variable a) (compositionMapType variable b);
      XCon c ts -> XCon c (map (compositionMapType variable) ts);
      XApply a b -> XApply (compositionMapType variable a) (compositionMapType variable b);
      XForall a bound b -> XForall (variable a) (compositionMapType variable bound) (compositionMapType variable b);
      _ -> ty
    };
  compositionMapComputation :: (XTyVar -> XTyVar) -> XComputation -> XComputation;
  compositionMapComputation variable computation =
    case computation of {
      XBottom t -> XBottom (compositionMapType variable t);
      XHyp a -> XHyp (variable a);
      XInner p -> XInner (compositionMapComputation variable p);
      XOuter a p -> XOuter (variable a) (compositionMapComputation variable p);
      XIntro a -> XIntro (variable a);
      XIntroKind a k -> XIntroKind (variable a) k;
      XThen a b -> XThen (compositionMapComputation variable a) (compositionMapComputation variable b);
      _ -> computation
    };
  compositionMapPattern name pattern =
    case pattern of {
      XConstructorPattern c ns -> XConstructorPattern c (map (mapOptional name) ns);
      XDefaultPattern n -> XDefaultPattern (mapOptional name n)
    };
  compositionMapTerm :: (XName -> XName) -> (XTyVar -> XTyVar) -> XTerm -> XTerm;
  compositionMapTerm name variable term =
    case term of {
      XVarTerm n -> XVarTerm (name n);
      XAbs n ty b -> XAbs (name n) (compositionMapType variable ty) (compositionMapTerm name variable b);
      XApp a b -> XApp (compositionMapTerm name variable a) (compositionMapTerm name variable b);
      XTypeAbs a bound b ->
        XTypeAbs (variable a) (compositionMapType variable bound) (compositionMapTerm name variable b);
      XTypeApp a p -> XTypeApp (compositionMapTerm name variable a) (compositionMapComputation variable p);
      XLet n a b -> XLet (name n) (compositionMapTerm name variable a) (compositionMapTerm name variable b);
      XLetRec bs b ->
        XLetRec
          (map (\((,,) n t a) -> (,,) (name n) (compositionMapType variable t) (compositionMapTerm name variable a))
             bs)
          (compositionMapTerm name variable b);
      XPrimitive p ts -> XPrimitive p (map (compositionMapType variable) ts);
      XConstructor c ts -> XConstructor c (map (compositionMapType variable) ts);
      XCase a t bs ->
        XCase (compositionMapTerm name variable a) (compositionMapType variable t)
          (map (\(XAlternative p b) -> XAlternative (compositionMapPattern name p) (compositionMapTerm name variable b))
             bs);
      XWithData ds b -> XWithData ds (compositionMapTerm name variable b);
      _ -> term
    };
  -- Dense renumbering also handles valid object IDs near the parser's Int64
  -- limit. Adding an offset to original IDs would overflow that wire format.
  compositionTypeIdentities :: XType -> IntSet -> IntSet;
  compositionTypeIdentities ty seen =
    case ty of {
      XVar (XTyVar a) -> IS.insert a seen;
      XArrow a b -> compositionTypeIdentities b (compositionTypeIdentities a seen);
      XCon _ ts -> foldl (\acc t -> compositionTypeIdentities t acc) seen ts;
      XApply a b -> compositionTypeIdentities b (compositionTypeIdentities a seen);
      XForall (XTyVar a) bound b ->
        compositionTypeIdentities b (compositionTypeIdentities bound (IS.insert a seen));
      _ -> seen
    };
  compositionComputationIdentities :: XComputation -> IntSet -> IntSet;
  compositionComputationIdentities p seen =
    case p of {
      XBottom t -> compositionTypeIdentities t seen;
      XHyp (XTyVar a) -> IS.insert a seen;
      XInner q -> compositionComputationIdentities q seen;
      XOuter (XTyVar a) q -> compositionComputationIdentities q (IS.insert a seen);
      XIntro (XTyVar a) -> IS.insert a seen;
      XIntroKind (XTyVar a) _ -> IS.insert a seen;
      XThen a b -> compositionComputationIdentities b (compositionComputationIdentities a seen);
      _ -> seen
    };
  compositionTermIdentities :: XTerm -> IntSet -> IntSet;
  compositionTermIdentities term seen =
    case term of {
      XVarTerm n -> IS.insert (X.nameId n) seen;
      XAbs n ty b -> compositionTermIdentities b (compositionTypeIdentities ty (IS.insert (X.nameId n) seen));
      XApp a b -> compositionTermIdentities b (compositionTermIdentities a seen);
      XTypeAbs (XTyVar a) bound b ->
        compositionTermIdentities b (compositionTypeIdentities bound (IS.insert a seen));
      XTypeApp a p -> compositionComputationIdentities p (compositionTermIdentities a seen);
      XLet n a b -> compositionTermIdentities b (compositionTermIdentities a (IS.insert (X.nameId n) seen));
      XLetRec bs b ->
        compositionTermIdentities b
          (foldl
             (\acc ((,,) n t a) ->
                compositionTermIdentities a (compositionTypeIdentities t (IS.insert (X.nameId n) acc)))
             seen
             bs);
      XPrimitive _ ts -> foldl (\acc t -> compositionTypeIdentities t acc) seen ts;
      XConstructor _ ts -> foldl (\acc t -> compositionTypeIdentities t acc) seen ts;
      XCase a t bs ->
        foldl
          (\acc (XAlternative p b) ->
             compositionTermIdentities b
               (foldl (\ids n -> IS.insert (X.nameId n) ids) acc (X.patternNames p)))
          (compositionTypeIdentities t (compositionTermIdentities a seen))
          bs;
      XWithData _ b -> compositionTermIdentities b seen;
      _ -> seen
    };
}
