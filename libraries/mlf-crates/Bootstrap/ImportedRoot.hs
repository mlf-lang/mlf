-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.ImportedRoot
  (Compilation, fromCheckedWrapper, finishCompilation, finishSelected, fileImports, finishFileImports, finishFileImportsIn, checkedWrapper, inferredType, sourceType,
   remove, finishLinked, materializeImports, materializeLinked, usedImportSignatures) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.OpenFragment as Open;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Constraint as C;
  import qualified Bootstrap.Graph as G;
  import qualified Bootstrap.Graph.Solver as Solver;
  import qualified Bootstrap.Elaborate as E;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.CompilerCore as Core;
  import qualified Bootstrap.ImportParameters as Parameters;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Kind as K;
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
  -- A grouped crate already carries checked declaration bodies. Its user
  -- type is the codomain after exactly the authenticated external binders.
  fromCheckedWrapper :: Map String XType -> Checked.CheckedTerm -> Either String Compilation;
  fromCheckedWrapper signatures checked = do {
    let { expression = case Checked.term checked of { XWithData _ body -> body; body -> body };
          consume ty row = case ty of {
            XArrow argument answer -> do {
              ensure (T.alphaEq argument (snd row)) "checked crate import arrow type mismatch";
              Right answer
            };
            _ -> Left "checked crate import arrow missing"
          } };
    _ <- takeParameters (M.toList signatures) expression;
    answer <- foldEither consume (Checked.typeOf checked) (M.toList signatures);
    Right (Compilation checked answer (Classes.prettyQualified M.empty answer))
  };
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
    XInstantiationSpine n rows -> join ((:) (S.singleton n) (map (\((,,) _ _ val) -> child val) rows));
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
  data ImportedDeclaration = ImportedGraph String XName Int | ImportedEvidence String XName XType;
  -- Only prenex bottom-bound schemes with a compound body and all binders
  -- present in the canonical traversal order have this direct embedding.
  evidenceTemplate datatypes first scheme = let {
    nominalRoot body = case body of { XCon _ _ -> True; XArrow _ _ -> True; _ -> False };
    -- Unknown raw type symbols use occurrence arity as a fallback. Only the
    -- authenticated schema can supply one invariant kind for all occurrences.
    kindOf name = case datatypes of { DataEnv _ _ kinds -> M.lookup compareString name kinds };
    visit names body = case body of {
      XVar v -> do { w <- IM.lookup (T.tyVarId v) names;
        Just ((,,,) (XVar w) 0 [] [T.tyVarId v]) };
      XArrow a b -> do {
        (,,,) left n ks u <- visit names a; (,,,) right m js v <- visit names b;
        Just ((,,,) (XArrow left right) (1+n+m) (append ks js) (append u v))
      };
      XApply f a -> do {
        (,,,) x n ks u <- visit names f; (,,,) y m js v <- visit names a;
        case x of { XCon _ _ -> Nothing;
          _ -> Just ((,,,) (XApply x y) (1+n+m) (append ks js) (append u v)) }
      };
      XCon key xs -> do {
        kind <- kindOf key;
        rows <- mapM (visit names) xs;
        Just ((,,,) (XCon key (map (\((,,,) x _ _ _) -> x) rows))
          (1+length xs+sum (map (\((,,,) _ n _ _) -> n) rows))
          (append (if K.eqKind kind Star then [] else [(,) key kind]) (concatMap (\((,,,) _ _ ks _) -> ks) rows))
          (concatMap (\((,,,) _ _ _ vs) -> vs) rows))
      };
      _ -> Nothing
    };
    prefix ordinal names order bound t = case t of {
      XForall v b body -> let {
        id = T.tyVarId v; w = XTyVar (advanceIdentity first ordinal);
        next = prefix (ordinal+1) (IM.insert id w names) ((:) id order) ((:) ((,) w b) bound) body
      } in if IM.member id names then Nothing else case b of {
        XBot -> next; XBotKind k -> if K.eqKind k Star then Nothing else next; _ -> Nothing };
      _ -> if not (nominalRoot t) then Nothing else do {
        (,,,) body n kinds seen <- visit names t;
        if not (eqList eqInt (reverse order) (nubBy eqInt seen)) then Nothing else
          Just ((,,) (foldl (\ty ((,) v b) -> XForall v b ty) body bound) (ordinal+n) kinds)
      }
    }
  } in prefix 0 IM.empty [] [] scheme;
  declareImported admitted datatypes definitions = do {
    gen <- C.newNode (GGen (-1)) Nothing Flexible;
    root <- C.newNode GBot (Just gen) Flexible;
    C.setNode gen (Node (GGen root) Nothing Flexible);
    let { allocate d@((,,) key mode _) = let {
      ordinary = do {
        (,,,) n binder source _ <- C.declareRecursive datatypes gen d;
        return ((,) (ImportedGraph n binder source) [])
      }
    } in case (,) (M.lookup compareString key admitted) mode of {
      (,) (Just checked) (CheckRecursive (SAnnotation [] written)) ->
        if not (C.sameType written (Separate.sourceSchemeIn M.empty False checked)) then ordinary else do {
          graph <- C.getGraph;
          let { first = advanceIdentity (G.nextId graph) 2 };
          case evidenceTemplate datatypes first checked of {
            Nothing -> ordinary;
            Just ((,,) rebuilt width kinds) -> do {
              name <- C.freshName key;
              C.setGraph (G.mkGraph (G.nodes graph) (G.links graph) (advanceIdentity first width));
              return ((,) (ImportedEvidence key name rebuilt) kinds)
            }
          }
        };
      _ -> ordinary
    } };
    rows <- mapM allocate definitions;
    return ((,,,) gen root (map fst rows) (concatMap snd rows))
  };
  evidenceOnly slots signatures inner = let {
    declared refs = IS.fromList (map V.toInt (Dependency.occurrenceGlobalIds (\_ -> refs) inner));
    allReads = Dependency.valueOccurrences True False inner;
    values = Dependency.valueOccurrences False False inner;
    candidates = IS.difference (declared allReads) (declared values);
    names = S.fromList compareString (mapMaybe (\ref -> case ref of {
      LexicalRef name -> Just name; DeclRef _ _ -> Nothing
    }) values)
  } in M.fromList compareString (mapMaybe (\((,) slot p@((,) name _)) ->
    if IS.member (V.toInt slot) candidates && not (S.member compareString name names)
    then Just p else Nothing) (zip slots signatures));
  buildImported admitted datatypes ids definitions inner = do {
    (,,,) gen root imports kinds <- declareImported admitted datatypes definitions;
    let { graphBinding imported = case imported of {
      ImportedGraph key name source -> Just ((,) key (Poly name source)); _ -> Nothing };
      evidenceBinding imported = case imported of {
        ImportedEvidence _ name ty -> Just ((,) name ty); _ -> Nothing };
      indexed slots project = M.fromList C.compareRefSlot (mapMaybe (\((,) i row) ->
        mapOptional ((,) i) (project row)) (zip slots imports));
      scope = case ids of {
        Nothing -> C.BindingEnv (M.fromList compareString (mapMaybe graphBinding imports)) M.empty;
        Just slots -> C.BindingEnv M.empty (indexed slots (\row -> mapOptional snd (graphBinding row)))
      };
      evidence = case ids of { Nothing -> M.empty; Just slots -> indexed slots evidenceBinding }
    };
    continuation <- C.buildInWithEvidence evidence datatypes M.empty (Just gen) scope (C.desugar inner);
    proof <- C.edge (C.generalization continuation) root;
    return ((,,) (Typed gen (FRecursive [] continuation proof)) imports kinds)
  };
  generate selected = generateWith C.SeparateEnvironments True
    (Parameters.entries selected) (Parameters.namedEntries selected);
  generateWith = generateIn Nothing;
  generateIn = generateUsing False;
  generateUsing compact known memo validateInput slots signatures program = let {
    validate graph = if validateInput then G.validateGraph graph else Right ()
  } in case program of {
    SClassProgram _ _ _ _ -> Left "class declarations must be translated before constraint generation";
    SProgram declarations expression -> do {
      -- Keep validation before inspection, including every unused user RHS.
      datatypes <- case known of {
        Nothing -> D.validateDeclarations declarations;
        Just _ -> mapEither Open.dataEnvironment (Open.environmentUsing known declarations)
      };
      lowered <- Surface.lowerExpression expression;
      C.validateAnnotations datatypes lowered;
      if null signatures then do {
        result <- C.startGeneration memo (C.build datatypes M.empty Nothing M.empty (C.desugar lowered));
        case result of { (,) typed (C.Generation graph equalities steps) -> do {
          validate graph;
          Right ((,,) (Constraints graph typed (reverse equalities) (reverse steps)) [] [])
        } }
      } else case Parameters.prefix lowered of {
        Just ((,,) ids parameters inner) -> do {
          ensure (case ids of { Nothing -> True; Just actual -> Parameters.matchesPrefix actual slots })
            "direct import declaration inventory mismatch";
          ensure (eqList eqString (map (\((,,) name _ _) -> name) parameters) (map fst signatures))
            "direct import parameter inventory mismatch";
          traverseEither (\((,) _ ty) -> ensure (S.null (T.freeVars ty))
            "direct import contract is not closed") signatures;
          definitions <- traverseEither parameter parameters;
          let { admitted = case (,) compact ids of { (,) True (Just actual) -> evidenceOnly actual signatures inner; _ -> M.empty } };
          result <- C.startGeneration memo (buildImported admitted datatypes ids definitions inner);
          case result of {
            (,) ((,,) typed imports allocated) (C.Generation graph equalities steps) -> do {
              validate graph;
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
  finishCompilation signatures = finishSelected (Parameters.namedImports signatures);
  finishSelected selected = finishUsing (generate selected) (Parameters.namedEntries selected);
  verifyImportedParameter types ((,) imported ((,) stable expected)) = let {
    verify key name actual = do {
      ensure (eqString key stable) "direct import contract disappeared";
      ensure (T.alphaEq actual expected) ("direct import declaration changed its contract: " ++ key);
      Right ((,) name expected)
    }
  } in case imported of {
    ImportedGraph key name source -> verify key name (E.schemeTypeIn types source);
    ImportedEvidence key name actual -> verify key name actual
  };
  finishUsing = finishUsingChecked Checked.check;
  finishUsingChecked = finishUsingSolver C.solvePrepared;
  finishUsingSolver solveConstraints check generateInputs signatures ((,) program names) = case program of {
    SClassProgram _ _ _ _ -> Left (CompileError Inference "class translation did not produce a core program");
    SProgram declarations _ -> do {
      generated <- Core.atPhase Inference (generateInputs program);
      let { constraints = case generated of { (,,) value _ _ -> value };
            imports = case generated of { (,,) _ value _ -> value };
            kinds = case generated of { (,,) _ _ value -> value } };
      solved <- Core.atPhase Inference (solveConstraints constraints);
      let { graph = Solver.solverGraph solved; types = E.prepareValidatedSolvedTypes solved };
      -- Check each declaration, including unused parameters, against the exact
      -- authenticated target contract after solving. Poly is intentionally the
      -- same binding form as buildRecursive, not declared-field provenance.
      parameters <- Core.atPhase Verification (do {
        ensure (length imports == length signatures) "direct import contract disappeared";
        traverseEither (verifyImportedParameter types) (zip imports signatures)
      });
      let { datatypes = if null kinds then E.graphDatatypes graph else
        D.withKinds (append kinds (mapMaybe E.nodeConstructorKind (IM.elems (G.nodes graph)))) };
      (,) checked userType <- Core.finishCheckedRoot types datatypes constraints solved declarations parameters check
        "direct import elaboration changed the inferred type" "direct import elaboration changed source erasure";
      Right (Compilation checked userType (Classes.prettyQualified names userType))
    }
  };

  -- The file-unit caller has the consumer-local slots along with each independent
  -- certificate. Only the exact lowering-owned group is eligible.
  fileImports rows ((,) program _) = case program of {
    SProgram _ expression -> case Parameters.prefix expression of {
      Just ((,,) (Just ids) definitions _) -> let {
        ordered = sortBy (\((,,) _ a _) ((,,) _ b _) -> compareString a b) rows;
        signatures = map (\((,,) _ name ty) -> (,) name ty) ordered;
        slots = map (\((,,) i _ ty) -> (,) i ty) ordered
      } in do {
        ensure (not (null rows) && Parameters.matchesPrefix ids slots &&
          eqList eqString (map (\((,,) n _ _) -> n) definitions) (map fst signatures))
          "file import prefix inventory mismatch";
        traverseEither parameter definitions;
        Right ((,) slots signatures)
      };
      _ -> Left "file import prefix is not indexed"
    };
    _ -> Left "file import prefix needs a class-lowered program"
  };
  finishFileImports = finishFileImportsIn Nothing;
  -- Graph allocation order can occur in a later type or evidence error. Replay
  -- the entire checked file wrapper on rejection, through its original order.
  finishFileImportsIn known inputs lowered = let {
    run compact memo = finishFileImportsUsing compact known memo inputs lowered;
    batches = C.BatchedEnvironments IM.empty;
    original = case run False batches of {
      Right result -> Right result; Left _ -> run False (C.SharedEnvironments IM.empty)
    }
  } in case known of {
    Nothing -> original;
    Just _ -> case run True batches of { Right result -> Right result; Left _ -> original }
  };
  finishFileImportsUsing compact known memo ((,) slots signatures) lowered = do {
    let { check = case known of { Nothing -> Checked.check; Just env -> Open.checkClosedIn env } };
    result <- mapLeft Core.prettyError
      (finishUsingSolver C.solveFileConstraints check (generateUsing compact known memo False slots signatures) signatures lowered);
    let { parts = case Checked.term (checkedWrapper result) of {
      XWithData ds body -> (,) ds body; body -> (,) [] body
    } };
    (,) parameters inner <- takeParameters signatures (snd parts);
    implementation <- removeEmptyGroup inner;
    Right ((,,) (fst parts) (map (\((,,) _ name ty) -> (,) name ty) parameters) implementation)
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
