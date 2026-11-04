-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- New opt-in module evidence policy. Existing standalone export/6 is untouched.
module MLF.ResourceModuleExport where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.X.Checked as K;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Syntax as X;
  import qualified MLF.ResourceExport as E;
  import qualified MLF.ResourceModules as Modules;
  import qualified MLF.ResourceProjection as Projection;
  import qualified Package.Json as J;

  lookupDeclaration declarations nominal = E.closedFindDeclaration declarations nominal;
  declarationIndex :: [] DataDecl -> String -> Either String Int;
  declarationIndex declarations nominal = case L.find
    (\((,) _ declaration) -> eqString nominal (D.datatypeName declaration))
    (L.mapIndexed (\i declaration -> (,) i declaration) declarations) of {
      Nothing -> Left "module census has unknown declaration identity";
      Just ((,) i _) -> Right i
  };
  fullDeclarations ds supplied = do {
    let { names = L.map D.datatypeName supplied;
          constructors = L.concatMap (L.compose (L.map D.constructorName) D.datatypeConstructors) supplied };
    L.ensure (L.length names == L.length (L.nubBy eqString names)) "module full context repeats a nominal family";
    L.ensure (L.length constructors == L.length (L.nubBy eqString constructors)) "module full context repeats a constructor";
    L.ensure (L.all (\n -> L.not (M.member compareString n D.primitiveKinds || M.member compareString n D.builtinDatatypes)) names)
      "module full context shadows a compiler builtin family";
    L.ensure (L.all (\n -> L.not (M.member compareString n D.builtinConstructors)) constructors)
      "module full context shadows a compiler builtin constructor";
    L.traverseEither (\expected -> do {
      actual <- D.lookupDatatype ds (D.datatypeName expected);
      L.ensure (eqString (J.render (Modules.rawDeclaration expected)) (J.render (Modules.rawDeclaration actual)))
        "module census lookup changed complete original declaration";
      L.traverseEither (E.actualConstructor ds actual) (D.datatypeConstructors actual);
      Right actual
    }) supplied
  };
  -- A closed view keeps the original declaration index AND resolved identity.
  -- Equal physical fields never merge phantom or nullary parameter vectors.
  data ConcreteView = ConcreteView Int String ([] XType);
  viewIndex (ConcreteView index _ _) = index;
  viewName (ConcreteView _ nominal _) = nominal;
  viewArguments (ConcreteView _ _ arguments) = arguments;
  sameView (ConcreteView ai an aa) (ConcreteView bi bn ba) =
    ai == bi && eqString an bn && X.equalList T.alphaEq aa ba;
  hasView view registry = L.any (sameView view) registry;
  argumentRank :: XType -> Int;
  argumentRank ty = case ty of { XCon "Int" [] -> 0; XCon "Bool" [] -> 1; _ -> 2 };
  compareArguments :: [] XType -> [] XType -> Int;
  compareArguments aa ba = case aa of {
    [] -> if L.null ba then 0 else (-1);
    (:) a rest -> case ba of {
      [] -> 1;
      (:) b more -> let { order = L.compareInt (argumentRank a) (argumentRank b) }
        in if order == 0 then compareArguments rest more else order
    }
  };
  compareView :: ConcreteView -> ConcreteView -> Int;
  compareView (ConcreteView ai _ aa) (ConcreteView bi _ ba) =
    let { order = L.compareInt ai bi } in if order == 0 then compareArguments aa ba else order;
  instanceRef :: ConcreteView -> J.Json;
  instanceRef (ConcreteView index nominal arguments) = J.Object [
    ("declaration_index", J.num index), ("datatype", J.String nominal),
    ("arguments", J.Array (L.map Modules.rawType arguments))];
  register declarations registry nominal arguments = do {
    declaration <- lookupDeclaration declarations nominal;
    index <- declarationIndex declarations nominal;
    let { constructors = D.datatypeConstructors declaration; parameters = D.datatypeBinders declaration;
      view = ConcreteView index nominal arguments };
    L.ensure (L.not (L.null constructors) && L.length constructors <= 64) "used module family requires 1..64 complete variants";
    if E.isSumDeclaration declaration then do {
      L.ensure (L.length parameters <= 8 && L.all (\((,) _ k) -> L.eqKind k Star) parameters)
        "used module sum requires bounded Star parameters";
      L.ensure (L.length arguments == L.length parameters && L.all E.closedArgument arguments)
        "module nominal use requires exact closed Int/Bool arguments"
    } else L.ensure (L.null parameters && L.null arguments) "used parameterized record is unsupported";
    if hasView view registry then Right registry else do {
      L.ensure (L.not (E.isSumDeclaration declaration) ||
        L.length (L.filter (\prior -> L.any (\d -> eqString (viewName prior) (D.datatypeName d) && E.isSumDeclaration d) declarations) registry) < 64)
        "module concrete runtime sum view census exceeds 64";
      Right (L.append registry [view])
    }
  };
  typeInstances declarations registry annotation = case annotation of {
    XCon nominal arguments -> do {
      current <- if L.any (\d -> eqString nominal (D.datatypeName d)) declarations
        then register declarations registry nominal arguments
        else do {
          L.ensure (L.null arguments && (eqString nominal "Int" || eqString nominal "Bool" || eqString nominal "()"))
            "retained module type is outside closed scalar/Unit/declared nominal representation";
          Right registry
        };
      L.foldEither (typeInstances declarations) current arguments
    };
    XArrow a b -> do { next <- typeInstances declarations registry a; typeInstances declarations next b };
    _ -> Left "retained module runtime annotation is not fully concrete"
  };
  termInstances ds declarations registry term = case term of {
    XVarTerm _ -> Right registry;
    XAbs _ annotation body -> do { next <- typeInstances declarations registry annotation; termInstances ds declarations next body };
    XApp a b -> do { next <- termInstances ds declarations registry a; termInstances ds declarations next b };
    XLet _ rhs body -> do { next <- termInstances ds declarations registry rhs; termInstances ds declarations next body };
    XLetRec definitions body -> do {
      next <- L.foldEither (\state ((,,) _ annotation rhs) -> do {
        typed <- typeInstances declarations state annotation; termInstances ds declarations typed rhs
      }) registry definitions;
      termInstances ds declarations next body
    };
    XTypeAbs _ _ _ -> Left "module census cannot admit unresolved type abstraction";
    XTypeApp _ _ -> Left "module census cannot admit unresolved type computation";
    XConstructor constructor arguments -> do {
      pair <- D.lookupConstructor ds constructor;
      case pair of { (,) owner actual ->
        if eqString (D.datatypeName owner) "()" && eqString (D.constructorName actual) "()" && L.null arguments
          then Right registry else do {
          declaration <- lookupDeclaration declarations (D.datatypeName owner);
          E.actualConstructor ds declaration actual;
          next <- register declarations registry (D.datatypeName owner) arguments;
          L.foldEither (typeInstances declarations) next arguments
        }
      }
    };
    XPrimitive _ arguments -> L.foldEither (typeInstances declarations) registry arguments;
    XCase subject result alternatives -> do {
      typed <- typeInstances declarations registry result;
      next <- termInstances ds declarations typed subject;
      L.foldEither (\state (XAlternative _ body) -> termInstances ds declarations state body) next alternatives
    };
    XWithData _ _ -> Left "nested module declaration context is unsupported";
    XIntTerm _ -> Right registry; XBoolTerm _ -> Right registry;
    XDoubleTerm _ -> Left "retained module Double is not target-admitted";
    XStringTerm _ -> Left "retained module String is not target-admitted"
  };
  sumFieldSyntax field = case field of {
    Parameter _ -> True; Applied _ arguments -> L.all sumFieldSyntax arguments; _ -> False
  };
  fields ds declaration arguments constructor =
    if E.isSumDeclaration declaration then do {
      L.ensure (L.all sumFieldSyntax (D.constructorFields constructor))
        "module sum fields require actual Parameter/Applied syntax";
      E.closedInstantiatedFields ds declaration arguments constructor
    }
    else do {
      E.actualConstructor ds declaration constructor;
      L.ensure (L.null arguments && L.null (D.datatypeBinders declaration)) "record fields cannot be polymorphic";
      answer <- L.traverseEither E.fieldType (D.constructorFields constructor);
      L.traverseEither (Check.termType ds M.empty) answer;
      Right answer
    };
  fieldInstances declarations registry sumOwner field =
    if sumOwner then case field of {
      XCon nominal arguments -> if (eqString nominal "Int" || eqString nominal "Bool") && L.null arguments
        then Right registry else do {
          declaration <- lookupDeclaration declarations nominal;
          L.ensure (E.isSumDeclaration declaration) "module sum field requires scalar or registered sum family";
          register declarations registry nominal arguments
        };
      _ -> Left "module sum field requires scalar or registered sum family"
    } else typeInstances declarations registry field;
  close ds declarations visited registry = case L.find (\view -> L.not (hasView view visited)) registry of {
    Nothing -> Right registry;
    Just view -> do {
      declaration <- lookupDeclaration declarations (viewName view);
      index <- declarationIndex declarations (viewName view);
      L.ensure (index == viewIndex view) "module view declaration identity changed during closure";
      allFields <- L.traverseEither (fields ds declaration (viewArguments view)) (D.datatypeConstructors declaration);
      next <- L.foldEither (\state field -> fieldInstances declarations state (E.isSumDeclaration declaration) field)
        registry (L.concat allFields);
      close ds declarations ((:) view visited) next
    }
  };
  typeEdges :: [] DataDecl -> [] ConcreteView -> ConcreteView -> Int -> Int -> [] String -> XType -> Either String ([] J.Json);
  typeEdges declarations registry source variant field path annotation = case annotation of {
    XArrow a b -> do {
      left <- typeEdges declarations registry source variant field (L.append path ["from"]) a;
      right <- typeEdges declarations registry source variant field (L.append path ["to"]) b;
      Right (L.append left right)
    };
    XCon nominal arguments -> if L.any (\d -> eqString nominal (D.datatypeName d)) declarations
      then do {
        index <- declarationIndex declarations nominal;
        let { target = ConcreteView index nominal arguments };
        L.ensure (hasView target registry) "module closure edge target has no exact registered view";
        Right [J.Object [("source", instanceRef source), ("variant_index", J.num variant),
          ("field_index", J.num field), ("type_path", J.Array (L.map J.String path)),
          ("target", instanceRef target)]]
      } else Right [];
    _ -> Left "unexpected nonconcrete module closure edge"
  };
  closureEdges ds declarations registry = do {
    rows <- L.traverseEither (\view -> do {
      declaration <- lookupDeclaration declarations (viewName view);
      variants <- L.traverseEither (\((,) variant constructor) -> do {
        payloads <- fields ds declaration (viewArguments view) constructor;
        edges <- L.traverseEither (\((,) field annotation) ->
          typeEdges declarations registry view variant field [] annotation)
          (L.mapIndexed (\i field -> (,) i field) payloads);
        Right (L.concat edges)
      }) (L.mapIndexed (\i constructor -> (,) i constructor) (D.datatypeConstructors declaration));
      Right (L.concat variants)
    }) (L.sortBy compareView registry);
    Right (L.concat rows)
  };
  caseView declarations registry subjectType = case subjectType of {
    XCon "()" [] -> Right J.Null;
    XCon nominal arguments -> do {
      index <- declarationIndex declarations nominal;
      let { view = ConcreteView index nominal arguments };
      L.ensure (hasView view registry) "module case requires its exact closed scrutinee view in the census";
      Right (instanceRef view)
    };
    _ -> Left "module case scrutinee is not a closed nominal type"
  };
  caseNameNode :: Maybe XName -> J.Json;
  caseNameNode optional = case optional of {
    Nothing -> J.Null;
    Just name -> J.Object [("id", J.num (X.nameId name)), ("hint", J.String (X.nameHint name))]
  };
  extendTerms env pairs = XEnv (Check.typeEnv env)
    (M.union X.compareName (M.fromList X.compareName pairs) (Check.termEnv env));
  variantIndex :: DataDecl -> String -> Either String Int;
  variantIndex owner constructor = case L.find
    (\((,) _ member) -> eqString (D.constructorName member) constructor)
    (L.mapIndexed (\i member -> (,) i member) (D.datatypeConstructors owner)) of {
      Nothing -> Left "module case constructor absent from complete owner";
      Just ((,) i _) -> Right i
  };
  caseObligations :: DataEnv -> [] DataDecl -> [] ConcreteView -> XEnv -> String -> XTerm -> Either String ([] J.Json);
  caseObligations ds declarations registry env path term = case term of {
    XCase subject result alternatives -> do {
      L.ensure (L.not (L.null alternatives)) "module case alternatives cannot be empty";
      subjectType <- Check.inferIn ds env subject;
      owner <- D.checkAlternatives ds (L.map Check.shape alternatives);
      parameters <- Check.caseParameters ds subjectType owner;
      view <- caseView declarations registry subjectType;
      arms <- L.traverseEither (\((,) ordinal alternative) -> case alternative of {
        XAlternative pattern body -> case pattern of {
          XDefaultPattern _ -> Left "module retained default case unsupported";
          XConstructorPattern constructor names -> do {
            Check.checkAlternative ds env subjectType result parameters alternative;
            pair <- D.lookupConstructor ds constructor;
            case pair of { (,) declaration actual -> do {
              L.ensure (L.length names == L.length (D.constructorFields actual)) "module case field arity differs";
              number <- variantIndex declaration constructor;
              payloads <- L.traverseEither (T.instantiateField parameters) (D.constructorFields actual);
              L.ensure (L.length payloads == L.length names) "module case field witness would truncate";
              let { fieldRows = L.mapIndexed (\index ((,) name annotation) -> J.Object [
                ("field_index", J.num index), ("name", caseNameNode name),
                ("type", Modules.rawType annotation)]) (L.zip names payloads) };
              bindings <- Check.patternBindings ds subjectType parameters pattern;
              nested <- caseObligations ds declarations registry (extendTerms env bindings)
                (path ++ ".alternatives[" ++ showInt ordinal ++ "].body") body;
              Right ((,) (J.Object [("constructor", J.String constructor), ("variant_index", J.num number),
                ("fields", J.Array fieldRows)]) nested)
            } }
          }
        }
      }) (L.mapIndexed (\i alternative -> (,) i alternative) alternatives);
      subjectRows <- caseObligations ds declarations registry env (path ++ ".scrutinee") subject;
      let { row = J.Object [("path", J.String path), ("scrutinee_type", Modules.rawType subjectType),
        ("view", view), ("arms", J.Array (L.map L.fst arms))] };
      Right ((:) row (L.append subjectRows (L.concatMap L.snd arms)))
    };
    XAbs name annotation body -> caseObligations ds declarations registry
      (extendTerms env [((,) name annotation)]) (path ++ ".body") body;
    XApp a b -> do {
      left <- caseObligations ds declarations registry env (path ++ ".function") a;
      right <- caseObligations ds declarations registry env (path ++ ".argument") b;
      Right (L.append left right)
    };
    XLet name rhs body -> do {
      annotation <- Check.inferLetBinding ds env name rhs;
      left <- caseObligations ds declarations registry env (path ++ ".value") rhs;
      right <- caseObligations ds declarations registry (extendTerms env [((,) name annotation)]) (path ++ ".body") body;
      Right (L.append left right)
    };
    XLetRec definitions body -> do {
      scope <- Check.inferRecursiveScope ds env definitions;
      rows <- L.traverseEither (\((,) index ((,,) _ _ rhs)) -> caseObligations ds declarations registry scope
        (path ++ ".bindings[" ++ showInt index ++ "].value") rhs)
        (L.mapIndexed (\i definition -> (,) i definition) definitions);
      rest <- caseObligations ds declarations registry scope (path ++ ".body") body;
      Right (L.append (L.concat rows) rest)
    };
    XTypeAbs _ _ _ -> Left "module case witness cannot admit unresolved type abstraction";
    XTypeApp _ _ -> Left "module case witness cannot admit unresolved type computation";
    XWithData _ _ -> Left "module case witness nested declaration context unsupported";
    _ -> Right []
  };
  concreteInstance ds declarations ordinal view = do {
    declaration <- lookupDeclaration declarations (viewName view);
    constructors <- L.traverseEither (\constructor -> do {
      payloads <- fields ds declaration (viewArguments view) constructor;
      Right (J.Object [("constructor", J.String (D.constructorName constructor)),
        ("arity", J.num (L.length payloads)), ("fields", J.Array (L.map E.ty payloads))])
    }) (D.datatypeConstructors declaration);
    Right (J.Object [("view_index", J.num ordinal), ("declaration_index", J.num (viewIndex view)),
      ("datatype", J.String (viewName view)), ("arguments", J.Array (L.map E.ty (viewArguments view))),
      ("constructors", J.Array constructors)])
  };
  moduleMetadata checked = do {
    ds <- E.checkedDataEnv checked;
    declarations <- fullDeclarations ds (E.closedDeclarations (K.term checked));
    root <- typeInstances declarations [] (K.typeOf checked);
    let { body = case K.term checked of { XWithData _ expression -> expression; other -> other };
      path = case K.term checked of { XWithData _ _ -> "root.body"; _ -> "root" } };
    seeds <- termInstances ds declarations root body;
    registry <- close ds declarations [] seeds;
    cases <- caseObligations ds declarations registry Check.emptyEnv path body;
    let { indexed = L.mapIndexed (\index declaration -> (,) index declaration) declarations;
      selected = L.filter (\((,) index _) -> L.any (\view -> viewIndex view == index) registry) indexed;
      unused = L.filter (\((,) index _) -> L.not (L.any (\view -> viewIndex view == index) registry)) indexed;
      sums = L.filter (\((,) _ declaration) -> E.isSumDeclaration declaration) selected;
      records = L.filter (\((,) _ declaration) -> L.not (E.isSumDeclaration declaration)) selected;
      sumViews = L.sortBy compareView (L.filter (\view -> L.any (\((,) index _) -> viewIndex view == index) sums) registry) };
    recordNodes <- L.traverseEither (\((,) _ declaration) -> case D.datatypeConstructors declaration of {
      [constructor] -> E.recordMetadata ds declaration constructor;
      _ -> Left "module record family no longer singleton"
    }) records;
    instances <- L.traverseEither (\((,) ordinal view) -> concreteInstance ds declarations ordinal view)
      (L.mapIndexed (\i view -> (,) i view) sumViews);
    edges <- closureEdges ds declarations registry;
    unit <- E.unitMetadata; scalars <- E.builtinScalarMetadata;
    Right ((,) (J.Object [("builtin_unit", unit), ("builtin_scalars", scalars),
      ("custom_datatypes", J.Array recordNodes),
      ("custom_sums", J.Array (L.map (\((,) index declaration) -> E.closedTemplate index declaration) sums)),
      ("sum_instances", J.Array instances)])
      (J.Object [("policy", J.String "normalized-concrete-family-views/1"),
      ("seed_instances", J.Array (L.map instanceRef seeds)), ("closure_instances", J.Array (L.map instanceRef registry)),
      ("closure_edges", J.Array edges), ("case_obligations", J.Array cases),
      ("selected_declaration_indices", J.Array (L.map (\((,) i _) -> J.num i) selected)),
      ("evidence_only_declaration_indices", J.Array (L.map (\((,) i _) -> J.num i) unused))]))
  };

  exportCaptured sourceCommit dependencyDigest captured = do {
    projected <- Projection.projectChecked (Modules.checkedTerm captured);
    let { input = Projection.projected projected };
    normalized <- if E.closedRoute (K.term input) then E.normalizeClosedChecked input else E.normalizeChecked input;
    case normalized of { (,,) normalizationOriginal current normalizationSteps -> do {
      L.ensure (eqString (J.render (Modules.rawTerm (K.term input)))
        (J.render (Modules.rawTerm (K.term normalizationOriginal)))) "module normalization input changed before transformation";
      runtimeAnnotations <- E.annotated (K.term current);
      originalAnnotations <- E.rawAnnotated (K.term normalizationOriginal);
      normalizedAnnotations <- E.rawAnnotated (K.term current);
      originalErasure <- E.erased (X.erase (K.term normalizationOriginal));
      actualErasure <- E.erased (X.erase (K.term current));
      oldSkeleton <- E.closedSkeleton (K.term normalizationOriginal);
      newSkeleton <- E.closedSkeleton (K.term current);
      metadata <- moduleMetadata current;
      let { newPolicy = E.closedRoute (K.term normalizationOriginal);
        skeletonFields = if newPolicy then [("original_term_skeleton", oldSkeleton), ("normalized_term_skeleton", newSkeleton)] else [];
        normalization = J.Object (L.append [
          ("policy", J.String (if newPolicy then "single-closed-instance/1" else if E.containsConditional (K.term normalizationOriginal)
            then "closed-int-standard-instantiation/1" else "identity-no-conditional/1")),
          ("original_checked_type", E.ty (K.typeOf normalizationOriginal)),
          ("original_checked_type_pretty", J.String "module projected checked type; structural value authoritative"),
          ("original_checked_term_pretty", J.String "module projected checked term; raw value authoritative"),
          ("original_declaration_bindings", E.bindings normalizationOriginal),
          ("original_annotated", originalAnnotations), ("original_erased", originalErasure),
          ("normalized_annotated", normalizedAnnotations), ("steps", J.Array normalizationSteps),
          ("original_rechecked", J.Boolean True), ("normalized_rechecked", J.Boolean True),
          ("root_type_alpha_equal", J.Boolean True), ("erasure_equal", J.Boolean True)] skeletonFields) };
      let { output = J.Object [
        ("format", J.String "mlf-checked-module-export/2"),
        ("producer", J.Object [("source_commit", J.String sourceCommit), ("dependency_digest", J.String dependencyDigest)]),
        ("module_custody", Modules.moduleCustody captured),
        ("original", J.Object [
          ("checked_type", Modules.rawType (K.typeOf (Projection.original projected))),
          ("annotated", Modules.rawTerm (K.term (Projection.original projected))),
          ("erased", Modules.rawErased (X.erase (K.term (Projection.original projected)))),
          ("source_erased", Modules.rawErased (Modules.sourceErasure captured)),
          ("binder_origins", Modules.binderOrigins captured),
          ("ordinary_whole_check_passed", J.Boolean True),
          ("root_type_alpha_equal", J.Boolean True), ("source_erasure_equal", J.Boolean True)]),
        ("projection", Projection.evidence projected),
        ("normalization", J.Object [("fragment", normalization),
          ("raw_normalized", Modules.rawTerm (K.term current))]),
        ("runtime_inventory", L.snd metadata), ("representation", L.fst metadata),
        ("annotated", runtimeAnnotations), ("erased", actualErasure), ("checked_type", E.ty (K.typeOf current))] };
      let { rendered = J.render output };
      L.ensure (stringLength rendered <= 33554432) "module evidence export exceeds 32MiB character bound; byte bound also enforced by transport";
      Right rendered
    } }
  };
}
