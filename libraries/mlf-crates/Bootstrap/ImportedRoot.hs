-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.ImportedRoot
  (Compilation, finishCompilation, finishSelected, finishSelectedWithEvidence, finishSelectedWithEvidenceAndConstraints,
   checkedWrapper, inferredType, sourceType,
   remove, finishLinked, materializeImports, materializeLinked, usedImportSignatures) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Constraint as C;
  import qualified Bootstrap.Graph as G;
  import qualified Bootstrap.Graph.Solver as Solver;
  import qualified Bootstrap.Elaborate as E;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.CompilerCore as Core;
  import qualified Bootstrap.ImportParameters as Parameters;
  import qualified Bootstrap.BuiltinPreludeContext as Context;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Module as Modules;
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
  data ImportType = GraphImport Int | CheckedInstanceImport XType;
  data ImportedDeclaration = ImportedDeclaration String XName ImportType;

  namedReads observed = S.fromList compareString (mapMaybe (\ref -> case ref of {
    LexicalRef key -> Just key;
    DeclRef _ _ -> Nothing
  }) (Dependency.valueRefs observed));
  -- This is a representation decision for the selected named parameters. It
  -- never changes the lowered candidate sequence, selection, or visibility.
  directInstanceTypes context datatypes signatures parameters inner = let {
    iface = Context.interface context;
    instances = M.fromList compareString (Artifact.crateInstances iface);
    interfaceTypes = M.fromList compareString (Artifact.crateBindings iface);
    linked = Artifact.fragmentBindings (Context.linked context);
    visible = S.fromList compareString (map (Artifact.definitionName (Artifact.crateId iface))
      (concatMap snd (Artifact.crateExports iface)));
    allReads = namedReads (Dependency.observeExpression inner);
    otherReads = namedReads (Dependency.observeNonInstanceUses inner);
    owned key = case (,) (M.lookup compareString key instances) (Artifact.instanceOwner iface key) of {
      (,) (Just inst) (Right owner) -> Modules.isBuiltinModule owner &&
        eqString key (Artifact.instanceName (Artifact.crateId iface) owner inst);
      _ -> False
    };
    checked key ty = case (,) (M.lookup compareString key interfaceTypes) (M.lookup compareString key linked) of {
      (,) (Just declared) (Just ((,) _ actual)) -> T.alphaEq declared ty && T.alphaEq actual ty;
      _ -> False
    };
    admissible ((,) ((,) key ty) ((,,) parameterKey mode _)) = case mode of {
      CheckRecursive (SAnnotation [] annotation) ->
        if eqString key parameterKey && S.member compareString key allReads &&
           not (S.member compareString key otherReads) &&
           not (S.member compareString key visible) &&
           not (S.member compareString key (Context.sourceValues context)) && owned key &&
           S.null (T.freeVars ty) && checked key ty &&
           C.sameType annotation (Separate.sourceSchemeIn M.empty False ty)
        then case T.kindOf datatypes M.empty ty of {
          Right kind -> if eqKind kind Star then Just ((,) key ty) else Nothing;
          Left _ -> Nothing
        }
        else Nothing;
      _ -> Nothing
    }
  } in M.fromList compareString (mapMaybe admissible (zip signatures parameters));

  declareImported datatypes direct definitions = do {
    gen <- C.newNode (GGen (-1)) Nothing Flexible;
    root <- C.newNode GBot (Just gen) Flexible;
    C.setNode gen (Node (GGen root) Nothing Flexible);
    declarations <- mapM (\definition@((,,) key _ _) -> case M.lookup compareString key direct of {
      Nothing -> do {
        (,,,) _ name source _ <- C.declareRecursive datatypes gen definition;
        return (ImportedDeclaration key name (GraphImport source))
      };
      Just ty -> do {
        name <- C.freshName key;
        return (ImportedDeclaration key name (CheckedInstanceImport ty))
      }
    }) definitions;
    return ((,,) gen root declarations)
  };
  buildImported datatypes ids direct definitions inner = do {
    (,,) gen root declarations <- declareImported datatypes direct definitions;
    let { bindings = mapMaybe (\(ImportedDeclaration key name ty) -> case ty of {
        GraphImport source -> Just ((,) key (Poly name source));
        CheckedInstanceImport _ -> Nothing
      }) declarations;
      scope = case ids of {
        Nothing -> let { ordinary = C.BindingEnv (M.fromList compareString bindings) M.empty } in
          if M.null direct then ordinary else C.NamedEvidenceImports
            (M.fromList compareString (mapMaybe (\(ImportedDeclaration key name ty) -> case ty of {
              CheckedInstanceImport contract -> Just ((,) key ((,) name contract));
              GraphImport _ -> Nothing
            }) declarations)) ordinary;
        Just slots -> C.BindingEnv M.empty (M.fromList C.compareRefSlot (zip slots (map snd bindings)))
      } };
    continuation <- C.buildIn datatypes M.empty (Just gen) scope (C.desugar inner);
    proof <- C.edge (C.generalization continuation) root;
    return ((,) (Typed gen (FRecursive [] continuation proof)) declarations)
  };
  generate policy selected program = let { signatures = Parameters.namedEntries selected } in case program of {
    SClassProgram _ _ _ _ -> Left "class declarations must be translated before constraint generation";
    SProgram declarations expression -> do {
      -- Keep validation before inspection, including every unused user RHS.
      datatypes <- D.validateDeclarations declarations;
      lowered <- Surface.lowerExpression expression;
      C.validateAnnotations datatypes lowered;
      if null signatures then do {
        result <- C.runGenerate (C.build datatypes M.empty Nothing M.empty (C.desugar lowered))
          (C.Generation G.emptyGraph [] []);
        case result of { (,) typed (C.Generation graph equalities steps) -> do {
          G.validateGraph graph;
          Right ((,,) (Constraints graph typed (reverse equalities) (reverse steps)) [] Nothing)
        } }
      } else case Parameters.prefix lowered of {
        Just ((,,) ids parameters inner) -> do {
          ensure (case ids of { Nothing -> True; Just actual -> Parameters.matchesPrefix actual (Parameters.entries selected) })
            "direct import declaration inventory mismatch";
          ensure (eqList eqString (map (\((,,) name _ _) -> name) parameters) (map fst signatures))
            "direct import parameter inventory mismatch";
          traverseEither (\((,) _ ty) -> ensure (S.null (T.freeVars ty))
            "direct import contract is not closed") signatures;
          definitions <- traverseEither parameter parameters;
          let { direct = case (,) policy ids of {
            (,) (Just context) Nothing -> directInstanceTypes context datatypes signatures parameters inner;
            _ -> M.empty
          } };
          result <- C.runGenerate (buildImported datatypes ids direct definitions inner)
            (C.Generation G.emptyGraph [] []);
          case result of {
            (,) ((,) typed imports) (C.Generation graph equalities steps) -> do {
              G.validateGraph graph;
              Right ((,,) (Constraints graph typed (reverse equalities) (reverse steps)) imports
                (if M.null direct then Nothing else Just datatypes))
            }
          }
        };
        _ -> Left "direct import parameters are missing from lowered root"
      }
    }
  };
  finishCompilation :: Map String XType -> (,) SProgram (Map String String) ->
    Either CompileError Compilation;
  finishCompilation signatures = finishSelected (Parameters.namedImports signatures);
  finishSelected :: Parameters.Signatures -> (,) SProgram (Map String String) -> Either CompileError Compilation;
  finishSelected = finishSelectedUsing (\compiled _ -> compiled) Nothing;
  -- Named standalone imports can use an admitted provider's checked evidence.
  -- Ordinary crate and indexed import callers retain graph-backed bindings.
  finishSelectedWithEvidence :: Context.PreparedPrelude -> Parameters.Signatures ->
    (,) SProgram (Map String String) -> Either CompileError Compilation;
  finishSelectedWithEvidence context = finishSelectedUsing (\compiled _ -> compiled) (Just context);
  -- Return the very same input constraints only after the complete checked finish.
  finishSelectedWithEvidenceAndConstraints :: Context.PreparedPrelude -> Parameters.Signatures ->
    (,) SProgram (Map String String) -> Either CompileError ((,) Compilation Constraints);
  finishSelectedWithEvidenceAndConstraints context = finishSelectedUsing (,) (Just context);
  finishSelectedUsing :: forall a. (Compilation -> Constraints -> a) -> Maybe Context.PreparedPrelude ->
    Parameters.Signatures -> (,) SProgram (Map String String) -> Either CompileError a;
  finishSelectedUsing report policy selected ((,) program names) = let { signatures = Parameters.namedEntries selected } in case program of {
    SClassProgram _ _ _ _ -> Left (CompileError Inference "class translation did not produce a core program");
    SProgram declarations _ -> do {
      (,,) constraints imports validated <- Core.atPhase Inference (generate policy selected program);
      solved <- Core.atPhase Inference (C.solvePrepared constraints);
      let { graph = Solver.solverGraph solved; types = E.prepareTypes graph };
      -- Check each declaration, including unused parameters, against the exact
      -- authenticated target contract after solving. Poly is intentionally the
      -- same binding form as buildRecursive, not declared-field provenance.
      parameters <- Core.atPhase Verification (do {
        ensure (length imports == length signatures) "direct import contract disappeared";
        traverseEither (\((,) (ImportedDeclaration key name imported) ((,) stable expected)) -> do {
          ensure (eqString key stable) "direct import contract disappeared";
          ensure (case imported of {
            GraphImport source -> T.alphaEq (E.schemeTypeIn types source) expected;
            CheckedInstanceImport admitted -> T.alphaEq admitted expected
          })
            ("direct import declaration changed its contract: " ++ key);
          Right ((,) name expected)
        }) (zip imports signatures)
      });
      evidence <- Core.atPhase Resolution (case validated of {
        Nothing -> E.resolveEvidenceIn types (C.skeleton constraints);
        Just datatypes -> E.resolveWithinIn types datatypes M.empty (C.skeleton constraints)
      });
      body <- Core.atPhase Elaboration (case validated of {
        Nothing -> E.elaboratePreparedIn types solved evidence (C.skeleton constraints);
        Just datatypes -> E.elaborateWithinIn types datatypes evidence solved M.empty (C.skeleton constraints)
      });
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
      Right (report (Compilation checked userType (Classes.prettyQualified names userType)) constraints)
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
    member = \name -> IS.member (X.nameId name) parameters;
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
          identities = Separate.termIdentities expression IS.empty };
    ensure (length parameterNames == length (nubBy X.equalName parameterNames))
      "direct import wrapper reused a binder identity";
    replacements <- traverseEither (\((,,) key name actual) ->
      case M.lookup compareString key available of {
        Nothing -> Left ("missing direct import symbol: " ++ key);
        Just ((,) exported expected) -> do {
          ensure (T.alphaEq actual expected) ("direct import symbol type mismatch: " ++ key);
          ensure (not (IS.member (X.nameId exported) identities))
            ("direct import substitution would capture an identity: " ++ key);
          Right ((,) name exported)
        }
      }) parameters;
    body <- if M.null signatures then Right (snd split) else removeEmptyGroup (snd split);
    ensure (not (bindsImport (IS.fromList (map X.nameId parameterNames)) body))
      "direct import body rebinds a parameter identity";
    let { substitution = M.fromList X.compareName replacements };
    Right (Separate.mapTerm (\name -> M.findWithDefault X.compareName name name substitution) (\a -> a) body)
  }
}
