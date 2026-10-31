-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.ImportedRoot
  (Compilation, finishCompilation, checkedWrapper, inferredType, sourceType,
   remove, finishLinked, materializeImports, materializeLinked, usedImportSignatures) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Constraint as C;
  import qualified Bootstrap.Graph as G;
  import qualified Bootstrap.Graph.Solver as Solver;
  import qualified Bootstrap.Elaborate as E;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.CompilerCore as Core;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Checked as Checked;

  -- The independently checked wrapper has import arrows. Its user result type
  -- is stored separately; it is never passed off as an ordinary Compilation.
  data Compilation = Compilation Checked.CheckedTerm XType String;
  checkedWrapper (Compilation checked _ _) = checked;
  inferredType (Compilation _ ty _) = ty;
  sourceType (Compilation _ _ rendered) = rendered;
  -- The composition constructor accepts actual checked terms only. Requested
  -- imports select a verified prefix; they never supply a claimed result type.
  finishLinked linked signatures compiled = do {
    checked <- Checked.finishSpine linked
      (map (\key -> (,) key (C.targetNameHint key)) (M.keys signatures))
      (checkedWrapper compiled);
    ensure (T.alphaEq (Checked.typeOf checked) (inferredType compiled))
      "prepared library graft changed the user root type";
    Right checked
  };

  importVariableReads source = let {
    child = importVariableReads;
    join = S.unions X.compareName
  } in case source of {
    XVarTerm name -> S.singleton name;
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
    _ -> S.empty
  };
  usedImportSignatures signatures compiled = do {
    let { term = case Checked.term (checkedWrapper compiled) of { XWithData _ body -> body; body -> body } };
    split <- takeParameters (M.toList signatures) term;
    let { identities = importVariableReads (snd split);
      used = S.fromList compareString (map (\((,,) key _ _) -> key)
        (filter (\((,,) _ name _) -> S.member X.compareName name identities) (fst split))) };
    Right (M.filterWithKey (\key _ -> S.member compareString key used) signatures)
  };
  materializeLinked linked signatures compiled = do {
    result <- Checked.materializeSpine linked
      (map (\key -> (,) key (C.targetNameHint key)) (M.keys signatures)) (checkedWrapper compiled);
    let { remaining = M.filterWithKey (\key _ -> elem eqString key (snd result)) signatures;
      expected = foldr (\((,) _ ty) result -> XArrow ty result) (inferredType compiled) (M.toList remaining) };
    ensure (T.alphaEq (Checked.typeOf (fst result)) expected) "materialized import wrapper changed its checked type";
    Right ((,) (fst result) remaining)
  };
  -- Materialize an independently admitted declaration spine while retaining
  -- the exact remaining native import abstraction. All new identities are
  -- disjoint, and the resulting wrapper crosses the independent checker again.
  materializeImports signatures compiled serial available bodies = do {
    let { remaining = M.filterWithKey (\key _ -> not (M.member compareString key available)) signatures };
    if M.size remaining == M.size signatures then Right ((,) (checkedWrapper compiled) signatures) else do {
      let { fresh = Separate.freshObject serial (Checked.term (checkedWrapper compiled));
            expression = snd fresh;
            declarations = case expression of { XWithData ds _ -> ds; _ -> [] };
            parameters = map (\((,) index ((,) key ty)) ->
              (,,) key (XName index (C.targetNameHint key)) ty)
              (zip (range (fst fresh) (advanceIdentity (fst fresh) (M.size remaining) - 1)) (M.toList remaining));
            external = M.fromList compareString (map (\((,,) key name ty) -> (,) key ((,) name ty)) parameters) };
      inner <- remove signatures (M.union compareString available external) expression;
      grafted <- foldEither (\rest spine -> Separate.graft spine rest) inner bodies;
      let { wrapped = foldr (\((,,) _ name ty) body -> XAbs name ty body) grafted parameters;
            expected = foldr (\((,) _ ty) result -> XArrow ty result) (inferredType compiled) (M.toList remaining) };
      checked <- Checked.check (XWithData declarations wrapped);
      ensure (T.alphaEq (Checked.typeOf checked) expected) "materialized import wrapper changed its checked type";
      Right ((,) checked remaining)
    }
  };

  -- Only the exact prefix emitted by complete class lowering is eligible. In
  -- particular a caller cannot turn an arbitrary checked RHS into an import.
  parameter ((,,) name mode rhs) = case (,) mode rhs of {
    (,) (CheckRecursive (SAnnotation [] annotation))
      (SChecked checked (SApp (SPrimitive PPanic) (SStringLit message))) -> do {
        ensure (C.sameType annotation checked && eqString message "unlinked module parameter")
          "direct import parameter is not an authenticated placeholder";
        Right ((,,) name mode (C.desugar rhs))
      };
    _ -> Left "direct import parameter is not an authenticated placeholder"
  };
  declareImported datatypes definitions = do {
    -- Keep build/buildRecursive's outer scope and declaration geometry. The
    -- sole omitted work is building and proving the synthetic panic RHSs.
    gen <- C.newNode (GGen (-1)) Nothing Flexible;
    root <- C.newNode GBot (Just gen) Flexible;
    C.setNode gen (Node (GGen root) Nothing Flexible);
    before <- C.getGraph;
    declarations <- mapM (C.declareRecursive datatypes gen) definitions;
    after <- C.getGraph;
    return ((,,,) gen root declarations
      (IM.size (G.nodes after) - IM.size (G.nodes before)))
  };
  buildImported datatypes definitions inner = do {
    declared <- declareImported datatypes definitions;
    let { gen = case declared of { (,,,) value _ _ _ -> value };
          root = case declared of { (,,,) _ value _ _ -> value };
          declarations = case declared of { (,,,) _ _ value _ -> value };
          allocated = case declared of { (,,,) _ _ _ value -> value } };
    let { scope = M.fromList compareString
      (map (\((,,,) name target source _) -> (,) name (Poly target source)) declarations) };
    continuation <- C.build datatypes M.empty (Just gen) scope (C.desugar inner);
    proof <- C.edge (C.generalization continuation) root;
    return ((,,) (Typed gen (FRecursive [] continuation proof)) declarations allocated)
  };
  generate signatures program = case program of {
    SClassProgram _ _ _ _ -> Left "class declarations must be translated before constraint generation";
    SProgram declarations expression -> do {
      -- Keep validation before inspection, including every unused user RHS.
      datatypes <- D.validateDeclarations declarations;
      lowered <- Surface.lowerExpression expression;
      C.validateAnnotations datatypes lowered;
      if M.null signatures then do {
        result <- C.runGenerate (C.build datatypes M.empty Nothing M.empty (C.desugar lowered))
          (C.Generation G.emptyGraph [] []);
        case result of { (,) typed (C.Generation graph equalities steps) -> do {
          G.validateGraph graph;
          Right ((,,) (Constraints graph typed (reverse equalities) (reverse steps)) [] 0)
        } }
      } else case lowered of {
        SLetRec parameters inner -> do {
          ensure (eqList eqString (map (\((,,) name _ _) -> name) parameters) (M.keys signatures))
            "direct import parameter inventory mismatch";
          traverseEither (\((,) _ ty) -> ensure (S.null (T.freeVars ty))
            "direct import contract is not closed") (M.toList signatures);
          definitions <- traverseEither parameter parameters;
          result <- C.runGenerate (buildImported datatypes definitions inner)
            (C.Generation G.emptyGraph [] []);
          case result of {
            (,) ((,,) typed imports allocated) (C.Generation graph equalities steps) -> do {
              G.validateGraph graph;
              Right ((,,) (Constraints graph typed (reverse equalities) (reverse steps)) imports allocated)
            }
          }
        };
        _ -> Left "direct import parameters are missing from lowered root"
      }
    }
  };
  finishCompilation :: Map String XType -> (,) SProgram (Map String String) ->
    Either CompileError Compilation;
  finishCompilation signatures ((,) program names) = case program of {
    SClassProgram _ _ _ _ -> Left (CompileError Inference "class translation did not produce a core program");
    SProgram declarations _ -> do {
      generated <- Core.atPhase Inference (generate signatures program);
      let { constraints = case generated of { (,,) value _ _ -> value };
            imports = case generated of { (,,) _ value _ -> value };
            allocated = case generated of { (,,) _ _ value -> value } };
      solved <- Core.atPhase Inference (C.solvePrepared constraints);
      let { graph = Solver.solverGraph solved; types = E.prepareTypes graph };
      -- Check each declaration, including unused parameters, against the exact
      -- authenticated target contract after solving. Poly is intentionally the
      -- same binding form as buildRecursive, not declared-field provenance.
      parameters <- Core.atPhase Verification (traverseEither
        (\((,,,) key name source _) -> case M.lookup compareString key signatures of {
          Nothing -> Left "direct import contract disappeared";
          Just expected -> do {
            ensure (T.alphaEq (E.schemeTypeIn types source) expected)
              ("direct import declaration changed its contract: " ++ key);
            Right ((,) name expected)
          }
        }) imports);
      evidence <- Core.atPhase Resolution (E.resolveEvidenceIn types (C.skeleton constraints));
      body <- Core.atPhase Elaboration (E.elaboratePreparedIn types solved evidence (C.skeleton constraints));
      let { userType = E.schemeTypeIn types (C.generalization (C.skeleton constraints));
            wrapped = foldr (\((,) name ty) rest -> XAbs name ty rest) body parameters;
            term = if null declarations then wrapped else XWithData declarations wrapped;
            expected = foldr (\((,) _ ty) rest -> XArrow ty rest) userType parameters;
            erased = foldr (\((,) name _) rest -> XEAbs name rest)
              (C.eraseSourceWith evidence (C.skeleton constraints)) parameters };
      checked <- Core.atPhase Verification (Checked.check term);
      Core.atPhase Verification (ensure (T.alphaEq (Checked.typeOf checked) expected)
        "direct import elaboration changed the inferred type");
      Core.atPhase Verification (ensure (X.equalErased (X.erase term) erased)
        "direct import elaboration changed source erasure");
      Right (Compilation checked userType (Classes.prettyQualified names userType))
    }
  };

  -- Strip exactly the authenticated prefix. splitParameters would also consume
  -- a user's returned lambda. Zero imports preserve every user-owned binder.
  takeParameters signatures term = case signatures of {
    [] -> Right ((,) [] term);
    (:) ((,) key expected) rest -> case term of {
      XAbs name actual body -> do {
        ensure (eqString (X.nameHint name) (C.targetNameHint key) && T.alphaEq expected actual)
          ("direct import wrapper mismatch: " ++ key);
        next <- takeParameters rest body;
        Right ((,) ((:) ((,,) key name actual) (fst next)) (snd next))
      };
      _ -> Left "direct import wrapper lost a parameter"
    }
  };
  removeEmptyGroup :: XTerm -> Either String XTerm;
  removeEmptyGroup term = case term of {
    XTypeAbs variable bound body -> mapEither (XTypeAbs variable bound) (removeEmptyGroup body);
    XTypeApp body proof -> mapEither (\value -> XTypeApp value proof) (removeEmptyGroup body);
    XLetRec [] body -> Right body;
    _ -> Left "direct import elaboration lost its empty scope wrapper"
  };
  bindsImport parameters term = let {
    member = \name -> S.member compareInt (X.nameId name) parameters;
    child = bindsImport parameters
  } in case term of {
    XAbs name _ body -> member name || child body;
    XApp a b -> child a || child b;
    XTypeAbs _ _ body -> child body;
    XTypeApp body _ -> child body;
    XLet name rhs body -> member name || child rhs || child body;
    XLetRec definitions body -> any (\((,,) name _ rhs) -> member name || child rhs) definitions || child body;
    XCase subject _ alternatives -> child subject || any
      (\(XAlternative pattern body) -> any member (X.patternNames pattern) || child body) alternatives;
    XWithData _ body -> child body;
    _ -> False
  };
  remove :: Map String XType -> Map String ((,) XName XType) -> XTerm -> Either String XTerm;
  remove signatures available expression = do {
    let { term = case expression of { XWithData _ body -> body; _ -> expression } };
    let { hints = map C.targetNameHint (M.keys signatures) };
    ensure (length hints == length (nubBy eqString hints)) "direct import source hints are ambiguous";
    split <- takeParameters (M.toList signatures) term;
    let { parameters = fst split;
          parameterNames = map (\((,,) _ name _) -> name) parameters;
          identities = Separate.termIdentities expression S.empty };
    ensure (length parameterNames == length (nubBy X.equalName parameterNames))
      "direct import wrapper reused a binder identity";
    replacements <- traverseEither (\((,,) key name actual) ->
      case M.lookup compareString key available of {
        Nothing -> Left ("missing direct import symbol: " ++ key);
        Just ((,) exported expected) -> do {
          ensure (T.alphaEq actual expected) ("direct import symbol type mismatch: " ++ key);
          ensure (not (S.member compareInt (X.nameId exported) identities))
            ("direct import substitution would capture an identity: " ++ key);
          Right ((,) name exported)
        }
      }) parameters;
    body <- if M.null signatures then Right (snd split) else removeEmptyGroup (snd split);
    ensure (not (bindsImport (S.fromList compareInt (map X.nameId parameterNames)) body))
      "direct import body rebinds a parameter identity";
    let { substitution = M.fromList X.compareName replacements };
    Right (Separate.mapTerm (\name -> M.findWithDefault X.compareName name name substitution) (\a -> a) body)
  }
}
