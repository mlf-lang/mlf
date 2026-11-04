-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- Experimental projection only: the private CheckedTerm constructor stays private.
-- Ordinary source inference, evidence and erasure verification happen upstream.
module MLF.ResourceExport where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Primitive as Primitive;
  import qualified Bootstrap.X.Checked as K;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Pretty as P;
  import qualified Package.Json as J;
  obj tag fields = J.Object ((:) ((,) "tag" (J.String tag)) fields);
  name n = J.Object [("id", J.num (X.nameId n)), ("hint", J.String (X.nameHint n))];
  kind k = case k of {
    Star -> obj "star" [];
    KArrow a b -> obj "arrow" [("from", kind a), ("to", kind b)]
  };
  ty t = case t of {
    XVar (XTyVar n) -> obj "var" [("id", J.num n)];
    XBot -> obj "bottom" [];
    XBotKind k -> obj "bottom_kind" [("kind", kind k)];
    XArrow a b -> obj "arrow" [("from", ty a), ("to", ty b)];
    XCon c ts -> obj "constructor" [("name", J.String c), ("arguments", J.Array (L.map ty ts))];
    XApply f a -> obj "apply" [("function", ty f), ("argument", ty a)];
    XForall (XTyVar n) bound body -> obj "forall" [("id", J.num n), ("bound", ty bound), ("body", ty body)]
  };
  computationNode :: XComputation -> J.Json;
  computationNode proof = case proof of {
    XRefl -> obj "refl" [];
    XBottom t -> obj "bottom" [("type", ty t)];
    XHyp (XTyVar n) -> obj "hyp" [("id", J.num n)];
    XInner p -> obj "inner" [("witness", computationNode p)];
    XOuter (XTyVar n) p -> obj "outer" [("id", J.num n), ("witness", computationNode p)];
    XElim -> obj "elim" [];
    XIntro (XTyVar n) -> obj "intro" [("id", J.num n)];
    XIntroKind (XTyVar n) k -> obj "intro_kind" [("id", J.num n), ("kind", kind k)];
    XThen a b -> obj "then" [("first", computationNode a), ("second", computationNode b)]
  };
  fieldNode :: Field -> J.Json;
  fieldNode field = case field of {
    Parameter n -> obj "parameter" [("name", J.String n)];
    Function a b -> obj "function" [("from", fieldNode a), ("to", fieldNode b)];
    Applied n args -> obj "applied" [("name", J.String n), ("arguments", J.Array (L.map fieldNode args))];
    Application f a -> obj "application" [("function", fieldNode f), ("argument", fieldNode a)];
    Quantified n k b -> obj "quantified" [("name", J.String n), ("kind", kind k), ("body", fieldNode b)]
  };
  constructorDeclarationNode :: ConstructorDecl -> J.Json;
  constructorDeclarationNode (ConstructorDecl n fields) =
    J.Object [("name", J.String n), ("fields", J.Array (L.map fieldNode fields))];
  declarationNode :: DataDecl -> J.Json;
  declarationNode declaration = case declaration of {
    DataDecl n parameters constructors -> obj "data" [("name", J.String n),
      ("parameters", J.Array (L.map J.String parameters)),
      ("constructors", J.Array (L.map constructorDeclarationNode constructors))];
    DataDeclK n parameters constructors -> obj "data_kind" [("name", J.String n),
      ("parameters", J.Array (L.map (\((,) parameter k) -> J.Object [("name", J.String parameter), ("kind", kind k)]) parameters)),
      ("constructors", J.Array (L.map constructorDeclarationNode constructors))]
  };
  -- Scalar payloads are projected from their intrinsic checked constructors.
  -- Int is the compiler's signed, wrapping Int64; J.num renders that exact Int.
  int64Node :: Int -> J.Json;
  int64Node value = obj "int64" [("value", J.num value)];
  boolNode :: Bool -> J.Json;
  boolNode value = obj "bool" [("value", J.Boolean value)];
  admittedScalarPrimitive :: Primitive -> Either String Primitive;
  admittedScalarPrimitive primitive = case primitive of {
    PAddInt -> Right primitive;
    PSubInt -> Right primitive;
    PMulInt -> Right primitive;
    PEqInt -> Right primitive;
    PLtInt -> Right primitive;
    PIfThenElse -> Right primitive;
    _ -> Left "primitive/FFI contract is outside the resource-native scalar fragment"
  };
  scalarPrimitiveFields :: Primitive -> Either String ([] ((,) String J.Json));
  scalarPrimitiveFields primitive = do {
    actual <- admittedScalarPrimitive primitive;
    Right [("id", J.num (Primitive.primitiveCode actual)), ("name", J.String (Primitive.primitiveName actual))]
  };
  intrinsicInt :: XType -> Bool;
  intrinsicInt target = case target of {
    XCon n [] -> eqString n "Int";
    _ -> False
  };
  annotatedPrimitive :: Primitive -> [] XType -> Either String J.Json;
  annotatedPrimitive = annotatedPrimitiveWith False;
  annotatedPrimitiveWith :: Bool -> Primitive -> [] XType -> Either String J.Json;
  annotatedPrimitiveWith rawEvidence primitive arguments = do {
    fields <- scalarPrimitiveFields primitive;
    case primitive of {
      PIfThenElse -> case arguments of {
        [target] -> if rawEvidence || intrinsicInt target
          then Right (obj "primitive" (L.append fields [("arguments", J.Array [ty target])]))
          else Left "resource conditional requires the exact closed intrinsic Int type";
        _ -> Left "resource conditional requires exactly one type argument"
      };
      _ -> if L.not (L.null arguments) then Left "scalar primitives must have no type arguments"
        else Right (obj "primitive" (L.append fields [("arguments", J.Array [])]))
    }
  };
  erasedPrimitive :: Primitive -> Either String J.Json;
  erasedPrimitive primitive = do {
    fields <- scalarPrimitiveFields primitive;
    Right (obj "primitive" fields)
  };
  annotated :: XTerm -> Either String J.Json;
  annotated = annotatedWith False;
  rawAnnotated :: XTerm -> Either String J.Json;
  rawAnnotated = annotatedWith True;
  annotatedWith :: Bool -> XTerm -> Either String J.Json;
  annotatedWith rawEvidence term = case term of {
    XVarTerm n -> Right (obj "var" [("name", name n)]);
    XAbs n a b -> do { body <- annotatedWith rawEvidence b; Right (obj "lambda" [("parameter", name n), ("parameter_type", ty a), ("body", body)]) };
    XApp f a -> do { function <- annotatedWith rawEvidence f; argument <- annotatedWith rawEvidence a; Right (obj "application" [("function", function), ("argument", argument)]) };
    XLet n a b -> do { rhs <- annotatedWith rawEvidence a; body <- annotatedWith rawEvidence b; Right (obj "let" [("name", name n), ("value", rhs), ("body", body)]) };
    XTypeAbs (XTyVar n) bound b -> do { body <- annotatedWith rawEvidence b; Right (obj "type_lambda" [("id", J.num n), ("bound", ty bound), ("body", body)]) };
    XTypeApp a p -> do { value <- annotatedWith rawEvidence a; Right (obj "type_application" [("value", value), ("witness", computationNode p)]) };
    XConstructor c args -> if eqString c "()" && L.null args then Right (obj "unit" [])
      else Right (obj "constructor" [("name", J.String c), ("arguments", J.Array (L.map ty args))]);
    XWithData declarations b -> do {
      body <- annotatedWith rawEvidence b;
      if rawEvidence then Right (obj "with_data" [("declarations", J.Array (L.map declarationNode declarations)), ("body", body)])
      else Right body
    };
    XLetRec bs b -> do {
      definitions <- L.traverseEither (\((,,) n t v) -> do { value <- annotatedWith rawEvidence v; Right (J.Object [("name", name n), ("type", ty t), ("value", value)]) }) bs;
      body <- annotatedWith rawEvidence b;
      Right (obj "letrec" [("bindings", J.Array definitions), ("body", body)])
    };
    XCase s t alts -> do {
      scrutinee <- annotatedWith rawEvidence s;
      alternatives <- L.traverseEither (\(XAlternative p b) -> do { patternJson <- patternNode p; body <- annotatedWith rawEvidence b; Right (J.Object [("pattern", patternJson), ("body", body)]) }) alts;
      Right (obj "case" [("scrutinee", scrutinee), ("result_type", ty t), ("alternatives", J.Array alternatives)])
    };
    XIntTerm value -> Right (int64Node value);
    XDoubleTerm _ -> Left "Double payloads are outside the resource-native fragment";
    XBoolTerm value -> Right (boolNode value);
    XStringTerm _ -> Left "String payloads are outside the resource-native fragment";
    XPrimitive primitive arguments -> annotatedPrimitiveWith rawEvidence primitive arguments
  };
  patternNode :: XPattern -> Either String J.Json;
  patternNode p = case p of {
    XConstructorPattern c fields -> Right (J.Object [("constructor", J.String c), ("fields", J.Array (L.map fieldName fields))]);
    XDefaultPattern _ -> Left "default patterns are outside the exhaustive constructor-only resource-native fragment"
  };
  fieldName n = case n of { Nothing -> J.Null; Just value -> name value };
  erased :: XErased -> Either String J.Json;
  erased term = case term of {
    XEVar n -> Right (obj "var" [("name", name n)]);
    XEAbs n b -> do { body <- erased b; Right (obj "lambda" [("parameter", name n), ("body", body)]) };
    XEApp f a -> do { function <- erased f; argument <- erased a; Right (obj "application" [("function", function), ("argument", argument)]) };
    XELet n a b -> do { rhs <- erased a; body <- erased b; Right (obj "let" [("name", name n), ("value", rhs), ("body", body)]) };
    XEConstructor c -> if eqString c "()" then Right (obj "unit" []) else Right (obj "constructor" [("name", J.String c)]);
    XELetRec bs b -> do {
      definitions <- L.traverseEither (\((,) n v) -> do { value <- erased v; Right (J.Object [("name", name n), ("value", value)]) }) bs;
      body <- erased b;
      Right (obj "letrec" [("bindings", J.Array definitions), ("body", body)])
    };
    XECase s alts -> do {
      scrutinee <- erased s;
      alternatives <- L.traverseEither (\(XErasedAlternative p b) -> do { patternJson <- patternNode p; body <- erased b; Right (J.Object [("pattern", patternJson), ("body", body)]) }) alts;
      Right (obj "case" [("scrutinee", scrutinee), ("alternatives", J.Array alternatives)])
    };
    XEInt value -> Right (int64Node value);
    XEDouble _ -> Left "unsupported erased Double";
    XEBool value -> Right (boolNode value);
    XEString _ -> Left "unsupported erased String";
    XEPrimitive primitive -> erasedPrimitive primitive;
    XEEvidenceHole _ -> Left "unresolved evidence hole cannot cross resource bridge"
  };
  bindings checked = case K.declarationBindings checked of {
    Left diagnostic -> J.Object [("status", J.String "unavailable"), ("diagnostic", J.String diagnostic)];
    Right bs -> J.Object [("status", J.String "available"), ("bindings", J.Array (L.map (\((,) n t) -> J.Object [("name", name n), ("type", ty t)]) bs))]
  };
  unitMetadata = do {
    pair <- D.lookupConstructor D.emptyDataEnv "()";
    case pair of { (,) d c ->
      if eqString (D.datatypeName d) "()" && L.null (D.datatypeParameters d) && L.null (D.constructorFields c)
      then Right (J.Object [("constructor", J.String "()"), ("datatype", J.String "()"), ("arity", J.num 0), ("fields", J.Array [])])
      else Left "builtin Unit metadata differs from the resource contract"
    }
  };
  -- Int/Bool are primitive kinds, not user datatype/constructor spellings.
  -- Validate compiler-owned membership before publishing the transport contract.
  scalarMetadata :: String -> String -> Either String J.Json;
  scalarMetadata datatype runtimeShape =
    case M.lookup compareString datatype D.scalarPrimitiveKinds of {
      Just Star -> Right (J.Object [("datatype", J.String datatype), ("kind", kind Star),
        ("arity", J.num 0), ("runtime_shape", J.String runtimeShape)]);
      _ -> Left "builtin scalar metadata differs from the resource contract"
    };
  builtinScalarMetadata :: Either String J.Json;
  builtinScalarMetadata = do {
    int <- scalarMetadata "Int" "#i64";
    boolean <- scalarMetadata "Bool" "#bool";
    Right (J.Array [int, boolean])
  };
  checkedDataEnv checked = case K.term checked of {
    XWithData ds _ -> D.validateDeclarations ds;
    _ -> Right D.emptyDataEnv
  };
  fieldType :: Field -> Either String XType;
  fieldType field = case field of {
    Applied c [] -> Right (XCon c []);
    Function a b -> do { aa <- fieldType a; bb <- fieldType b; Right (XArrow aa bb) };
    _ -> Left "datatype fields require closed monomorphic nominal/arrow types"
  };
  -- Nominal metadata comes from the validated DataEnv, never constructor spelling
  -- alone. Resolve every member and retain the complete declaration family/order.
  actualConstructor :: DataEnv -> DataDecl -> ConstructorDecl -> Either String ConstructorDecl;
  actualConstructor env declaration expected = do {
    pair <- D.lookupConstructor env (D.constructorName expected);
    case pair of { (,) owner actual -> do {
      L.ensure (eqString (D.datatypeName owner) (D.datatypeName declaration))
        "constructor metadata belongs to a different nominal family";
      L.ensure (eqString (D.constructorName actual) (D.constructorName expected))
        "constructor lookup identity differs from its declaration";
      L.ensure (eqString (J.render (declarationNode owner)) (J.render (declarationNode declaration)))
        "constructor lookup does not preserve its complete declared family";
      Right actual
    } }
  };
  recordMetadata :: DataEnv -> DataDecl -> ConstructorDecl -> Either String J.Json;
  recordMetadata env declaration constructor = do {
    actual <- actualConstructor env declaration constructor;
    fields <- L.traverseEither fieldType (D.constructorFields actual);
    Right (J.Object [("datatype", J.String (D.datatypeName declaration)),
      ("constructor", J.String (D.constructorName actual)), ("arity", J.num (L.length fields)),
      ("fields", J.Array (L.map ty fields))])
  };
  -- Build a complete registry before inspecting payloads. Nominal references
  -- are checked one level at a time, so self/mutual sum cycles do not unfold.
  metadataDeclaration :: DataEnv -> DataDecl -> Either String DataDecl;
  metadataDeclaration env source = do {
    declaration <- D.lookupDatatype env (D.datatypeName source);
    L.ensure (L.null (D.datatypeBinders declaration)) "parameterized datatypes unsupported";
    L.ensure (L.not (L.null (D.datatypeConstructors declaration))) "nominal datatype family has no constructors";
    L.ensure (L.length (D.datatypeConstructors declaration) <= 64) "nominal sum family exceeds 64 variants";
    Right declaration
  };
  isSumDeclaration :: DataDecl -> Bool;
  isSumDeclaration declaration = case D.datatypeConstructors declaration of {
    [] -> False;
    [_] -> False;
    _ -> True
  };
  registeredSumField :: DataEnv -> [] DataDecl -> String -> Either String XType;
  registeredSumField env registered nominal = do {
    owner <- D.lookupDatatype env nominal;
    L.ensure (L.null (D.datatypeBinders owner)) "sum field owner must be parameterless";
    L.ensure (isSumDeclaration owner) "sum field owner must be a multi-constructor sum, not Unit or a record";
    L.ensure (L.length (D.datatypeConstructors owner) <= 64) "sum field owner exceeds 64 variants";
    L.ensure (L.any (\declaration ->
      eqString (D.datatypeName declaration) (D.datatypeName owner) &&
      eqString (J.render (declarationNode declaration)) (J.render (declarationNode owner))) registered)
      "sum field owner is not in the complete declared sum registry";
    Right (XCon (D.datatypeName owner) [])
  };
  sumFieldType :: DataEnv -> [] DataDecl -> Field -> Either String XType;
  sumFieldType env registered field = case field of {
    Applied nominal [] ->
      if eqString nominal "Int" || eqString nominal "Bool" then
        case M.lookup compareString nominal D.scalarPrimitiveKinds of {
          Just Star -> Right (XCon nominal []);
          _ -> Left "sum scalar field is not the actual intrinsic Star kind"
        }
      else registeredSumField env registered nominal;
    _ -> Left "sum fields require closed intrinsic Int, Bool or registered parameterless sum references"
  };
  sumConstructorMetadata :: DataEnv -> [] DataDecl -> DataDecl -> ConstructorDecl -> Either String J.Json;
  sumConstructorMetadata env registered declaration constructor = do {
    actual <- actualConstructor env declaration constructor;
    L.ensure (L.length (D.constructorFields actual) <= 32) "nominal sum variant exceeds 32 fields";
    -- Traverse every actual position, including unused/wildcard payloads. No
    -- pattern analysis or field pruning is part of metadata projection.
    fields <- L.traverseEither (sumFieldType env registered) (D.constructorFields actual);
    Right (J.Object [("constructor", J.String (D.constructorName actual)),
      ("arity", J.num (L.length fields)), ("fields", J.Array (L.map ty fields))])
  };
  declarationMetadata :: DataEnv -> [] DataDecl -> DataDecl -> Either String (Either J.Json J.Json);
  declarationMetadata env registered declaration =
    case D.datatypeConstructors declaration of {
      [] -> Left "nominal datatype family has no constructors";
      [constructor] -> do {
        record <- recordMetadata env declaration constructor;
        Right (Left record)
      };
      constructors -> do {
        members <- L.traverseEither (sumConstructorMetadata env registered declaration) constructors;
        Right (Right (J.Object [("datatype", J.String (D.datatypeName declaration)),
          ("constructors", J.Array members)]))
      }
    };
  customMetadata :: K.CheckedTerm -> Either String ((,) J.Json J.Json);
  customMetadata checked = do {
    env <- checkedDataEnv checked;
    let { declarations = case K.term checked of { XWithData ds _ -> ds; _ -> [] } };
    -- Phase one resolves all actual declarations before any field reference.
    actual <- L.traverseEither (metadataDeclaration env) declarations;
    let { registered = L.filter isSumDeclaration actual };
    L.ensure (L.length registered <= 64) "resource representation exceeds 64 sum families";
    -- Phase two validates every family/variant/field and preserves each order.
    items <- L.traverseEither (declarationMetadata env registered) actual;
    let {
      records = L.concatMap (\item -> case item of { Left record -> [record]; Right _ -> [] }) items;
      sums = L.concatMap (\item -> case item of { Left _ -> []; Right family -> [family] }) items
    };
    Right ((,) (J.Array records) (J.Array sums))
  };
  -- A bounded, evidence-preserving type-instantiation normalization only.
  -- No term beta-reduction, branch pruning, general proof reduction or erasure
  -- shape inference is performed. The independent checker remains unchanged.
  containsConditional :: XTerm -> Bool;
  containsConditional term = case term of {
    XAbs _ _ b -> containsConditional b;
    XApp f a -> containsConditional f || containsConditional a;
    XTypeAbs _ _ b -> containsConditional b;
    XTypeApp a _ -> containsConditional a;
    XLet _ a b -> containsConditional a || containsConditional b;
    XLetRec definitions b -> L.any (\((,,) _ _ value) -> containsConditional value) definitions || containsConditional b;
    XCase scrutinee _ alternatives -> containsConditional scrutinee || L.any (\(XAlternative _ body) -> containsConditional body) alternatives;
    XWithData _ b -> containsConditional b;
    XPrimitive primitive _ -> case primitive of { PIfThenElse -> True; _ -> False };
    _ -> False
  };
  bottomStar :: XType -> Bool;
  bottomStar bound = case bound of {
    XBot -> True;
    XBotKind Star -> True;
    _ -> False
  };
  substituteIntProof :: XTyVar -> XComputation -> Either String XComputation;
  substituteIntProof variable proof = case proof of {
    XRefl -> Right XRefl;
    XBottom target -> Right (XBottom (T.substitute variable (XCon "Int" []) target));
    XInner witness -> do { result <- substituteIntProof variable witness; Right (XInner result) };
    XElim -> Right XElim;
    XThen first second -> do {
      a <- substituteIntProof variable first;
      b <- substituteIntProof variable second;
      Right (XThen a b)
    };
    _ -> Left "unsupported proof in closed-Int substitution"
  };
  substituteIntTerm :: XTyVar -> XTerm -> Either String XTerm;
  substituteIntTerm variable term = case term of {
    XVarTerm _ -> Right term;
    XAbs n annotation b -> do {
      body <- substituteIntTerm variable b;
      Right (XAbs n (T.substitute variable (XCon "Int" []) annotation) body)
    };
    XApp f a -> do {
      function <- substituteIntTerm variable f;
      argument <- substituteIntTerm variable a;
      Right (XApp function argument)
    };
    XTypeAbs binder bound b -> do {
      -- The binder is not in scope in its own bound. Only its body shadows.
      body <- if T.equalTyVar variable binder then Right b else substituteIntTerm variable b;
      Right (XTypeAbs binder (T.substitute variable (XCon "Int" []) bound) body)
    };
    XTypeApp value proof -> do {
      body <- substituteIntTerm variable value;
      witness <- substituteIntProof variable proof;
      Right (XTypeApp body witness)
    };
    XLet n value b -> do {
      rhs <- substituteIntTerm variable value;
      body <- substituteIntTerm variable b;
      Right (XLet n rhs body)
    };
    XLetRec definitions b -> do {
      values <- L.traverseEither (\((,,) n annotation value) -> do {
        rhs <- substituteIntTerm variable value;
        Right ((,,) n (T.substitute variable (XCon "Int" []) annotation) rhs)
      }) definitions;
      body <- substituteIntTerm variable b;
      Right (XLetRec values body)
    };
    XIntTerm _ -> Right term;
    XDoubleTerm _ -> Right term;
    XBoolTerm _ -> Right term;
    XStringTerm _ -> Right term;
    XPrimitive primitive arguments -> Right (XPrimitive primitive (L.map (T.substitute variable (XCon "Int" [])) arguments));
    XConstructor constructor arguments -> Right (XConstructor constructor (L.map (T.substitute variable (XCon "Int" [])) arguments));
    XCase scrutinee result alternatives -> do {
      value <- substituteIntTerm variable scrutinee;
      branches <- L.traverseEither (\(XAlternative pattern b) -> do {
        body <- substituteIntTerm variable b;
        Right (XAlternative pattern body)
      }) alternatives;
      Right (XCase value (T.substitute variable (XCon "Int" []) result) branches)
    };
    -- Declaration Field variables are nominal strings, not these XTyVar IDs.
    -- Preserve exact declaration syntax; equalErased alone cannot protect it.
    XWithData declarations b -> do {
      body <- substituteIntTerm variable b;
      Right (XWithData declarations body)
    }
  };
  normalizeUnary :: (XTerm -> XTerm) -> XTerm -> Either String ((,) XTerm ([] J.Json));
  normalizeUnary constructor value = do {
    result <- normalizeIntTerm value;
    case result of { (,) body steps -> Right ((,) (constructor body) steps) }
  };
  normalizeBinary :: (XTerm -> XTerm -> XTerm) -> XTerm -> XTerm -> Either String ((,) XTerm ([] J.Json));
  normalizeBinary constructor left right = do {
    first <- normalizeIntTerm left;
    second <- normalizeIntTerm right;
    case first of { (,) a leftSteps -> case second of { (,) b rightSteps ->
      Right ((,) (constructor a b) (L.append leftSteps rightSteps))
    } }
  };
  normalizeDefinition :: (,,) XName XType XTerm -> Either String ((,) ((,,) XName XType XTerm) ([] J.Json));
  normalizeDefinition ((,,) n annotation value) = do {
    result <- normalizeIntTerm value;
    case result of { (,) body steps -> Right ((,) ((,,) n annotation body) steps) }
  };
  normalizeAlternative :: XAlternative -> Either String ((,) XAlternative ([] J.Json));
  normalizeAlternative (XAlternative pattern value) = do {
    result <- normalizeIntTerm value;
    case result of { (,) body steps -> Right ((,) (XAlternative pattern body) steps) }
  };
  normalizeIntTerm :: XTerm -> Either String ((,) XTerm ([] J.Json));
  normalizeIntTerm term = case term of {
    -- Outermost proof redex FIRST: its substitution closes nested Int witnesses.
    XTypeApp value XRefl -> do {
      result <- normalizeIntTerm value;
      case result of { (,) body steps -> Right ((,) body
        ((:) (J.Object [("rule", J.String "erase_refl"), ("witness", computationNode XRefl)]) steps)) }
    };
    XTypeApp (XTypeAbs binder bound body) proof -> case proof of {
      XThen (XInner (XBottom target)) XElim -> do {
        L.ensure (intrinsicInt target) "type-instantiation target is not closed intrinsic Int";
        L.ensure (bottomStar bound) "closed-Int instantiation requires a bottom-Star binder bound";
        substituted <- substituteIntTerm binder body;
        result <- normalizeIntTerm substituted;
        case result of { (,) normalized steps -> Right ((,) normalized ((:)
          (J.Object [("rule", J.String "instantiate_closed_int"), ("binder", J.num (T.tyVarId binder)),
            ("bound", ty bound), ("argument", ty target), ("witness", computationNode proof)]) steps)) }
      };
      _ -> Left "unsupported proof for resource closed-Int instantiation"
    };
    XTypeApp _ _ -> Left "resource type application is not a supported syntactic closed-Int redex";
    XVarTerm _ -> Right ((,) term []);
    XAbs n annotation body -> normalizeUnary (XAbs n annotation) body;
    XApp function argument -> normalizeBinary XApp function argument;
    XTypeAbs binder bound body -> normalizeUnary (XTypeAbs binder bound) body;
    XLet n value body -> normalizeBinary (XLet n) value body;
    XLetRec definitions body -> do {
      values <- L.traverseEither normalizeDefinition definitions;
      result <- normalizeIntTerm body;
      case result of { (,) normalized steps -> Right ((,)
        (XLetRec (L.map L.fst values) normalized) (L.append (L.concatMap L.snd values) steps)) }
    };
    XIntTerm _ -> Right ((,) term []);
    XDoubleTerm _ -> Right ((,) term []);
    XBoolTerm _ -> Right ((,) term []);
    XStringTerm _ -> Right ((,) term []);
    XPrimitive primitive arguments -> case primitive of {
      PIfThenElse -> case arguments of {
        [target] -> if intrinsicInt target then Right ((,) term [])
          else Left "unresolved or non-Int conditional remains after bounded normalization";
        _ -> Left "conditional must have exactly one intrinsic Int type argument"
      };
      _ -> Right ((,) term [])
    };
    XConstructor _ _ -> Right ((,) term []);
    XCase scrutinee result alternatives -> do {
      value <- normalizeIntTerm scrutinee;
      branches <- L.traverseEither normalizeAlternative alternatives;
      case value of { (,) normalized steps -> Right ((,)
        (XCase normalized result (L.map L.fst branches)) (L.append steps (L.concatMap L.snd branches))) }
    };
    XWithData declarations body -> normalizeUnary (XWithData declarations) body
  };
  normalizeChecked :: K.CheckedTerm -> Either String ((,,) K.CheckedTerm K.CheckedTerm ([] J.Json));
  normalizeChecked supplied = do {
    original <- K.check (K.term supplied);
    L.ensure (T.alphaEq (K.typeOf supplied) (K.typeOf original)) "supplied checked receipt disagrees with fresh original check";
    result <- if containsConditional (K.term original) then normalizeIntTerm (K.term original)
      else Right ((,) (K.term original) []);
    case result of { (,) term steps -> do {
      normalized <- K.check term;
      L.ensure (T.alphaEq (K.typeOf original) (K.typeOf normalized)) "bounded normalization changed the checked root type";
      L.ensure (X.equalErased (X.erase (K.term original)) (X.erase (K.term normalized))) "bounded normalization changed exact erasure";
      Right ((,,) original normalized steps)
    } }
  };
  closedSubstituteProof :: XTyVar -> XType -> XComputation -> Either String XComputation;
  closedSubstituteProof variable argument proof = case proof of {
    XRefl -> Right XRefl;
    XBottom target -> Right (XBottom (T.substitute variable argument target));
    XInner witness -> do { result <- closedSubstituteProof variable argument witness; Right (XInner result) };
    XElim -> Right XElim;
    XThen first second -> do {
      a <- closedSubstituteProof variable argument first;
      b <- closedSubstituteProof variable argument second;
      Right (XThen a b)
    };
    _ -> Left "unsupported proof in closed-instance substitution"
  };
  closedSubstituteTerm :: XTyVar -> XType -> XTerm -> Either String XTerm;
  closedSubstituteTerm variable argument term = case term of {
    XVarTerm _ -> Right term;
    XAbs n annotation b -> do {
      body <- closedSubstituteTerm variable argument b;
      Right (XAbs n (T.substitute variable argument annotation) body)
    };
    XApp f a -> do {
      function <- closedSubstituteTerm variable argument f;
      argument <- closedSubstituteTerm variable argument a;
      Right (XApp function argument)
    };
    XTypeAbs binder bound b -> do {
      -- The binder is not in scope in its own bound. Only its body shadows.
      body <- if T.equalTyVar variable binder then Right b else closedSubstituteTerm variable argument b;
      Right (XTypeAbs binder (T.substitute variable argument bound) body)
    };
    XTypeApp value proof -> do {
      body <- closedSubstituteTerm variable argument value;
      witness <- closedSubstituteProof variable argument proof;
      Right (XTypeApp body witness)
    };
    XLet n value b -> do {
      rhs <- closedSubstituteTerm variable argument value;
      body <- closedSubstituteTerm variable argument b;
      Right (XLet n rhs body)
    };
    XLetRec definitions b -> do {
      values <- L.traverseEither (\((,,) n annotation value) -> do {
        rhs <- closedSubstituteTerm variable argument value;
        Right ((,,) n (T.substitute variable argument annotation) rhs)
      }) definitions;
      body <- closedSubstituteTerm variable argument b;
      Right (XLetRec values body)
    };
    XIntTerm _ -> Right term;
    XDoubleTerm _ -> Right term;
    XBoolTerm _ -> Right term;
    XStringTerm _ -> Right term;
    XPrimitive primitive arguments -> Right (XPrimitive primitive (L.map (T.substitute variable argument) arguments));
    XConstructor constructor arguments -> Right (XConstructor constructor (L.map (T.substitute variable argument) arguments));
    XCase scrutinee result alternatives -> do {
      value <- closedSubstituteTerm variable argument scrutinee;
      branches <- L.traverseEither (\(XAlternative pattern b) -> do {
        body <- closedSubstituteTerm variable argument b;
        Right (XAlternative pattern body)
      }) alternatives;
      Right (XCase value (T.substitute variable argument result) branches)
    };
    -- Declaration Field variables are nominal strings, not these XTyVar IDs.
    -- Preserve exact declaration syntax; equalErased alone cannot protect it.
    XWithData declarations b -> do {
      body <- closedSubstituteTerm variable argument b;
      Right (XWithData declarations body)
    }
  };
  -- Restricted closed-use route. None of these functions rewrites term-level
  -- computation: only checked type annotations and type/proof wrappers change.
  data ClosedProofAction = ClosedIdentity | ClosedArgument XType XComputation;
  closedArgument :: XType -> Bool;
  closedArgument argument = case argument of {
    XCon nominal [] -> (eqString nominal "Int" || eqString nominal "Bool") &&
      (case M.lookup compareString nominal D.scalarPrimitiveKinds of { Just Star -> True; _ -> False });
    _ -> False
  };
  closedDeclarations :: XTerm -> [] DataDecl;
  closedDeclarations term = case term of { XWithData declarations _ -> declarations; _ -> [] };
  closedRoute :: XTerm -> Bool;
  closedRoute term = L.any (\declaration -> isSumDeclaration declaration &&
    L.not (L.null (D.datatypeBinders declaration))) (closedDeclarations term);
  closedSkeleton :: XTerm -> Either String J.Json;
  closedSkeleton term = case term of {
    XWithData declarations body -> do {
      inner <- closedSkeleton body;
      Right (obj "with_data" [("declarations", J.Array (L.map declarationNode declarations)), ("body", inner)])
    };
    _ -> erased (X.erase term)
  };
  closedProofLeaves :: XComputation -> [] XComputation;
  closedProofLeaves proof = case proof of {
    XThen a b -> L.append (closedProofLeaves a) (closedProofLeaves b);
    _ -> [proof]
  };
  closedParseLeaves :: XComputation -> Maybe XType -> [] XComputation -> Either String ([] ClosedProofAction);
  closedParseLeaves original pending leaves = case leaves of {
    [] -> case pending of { Nothing -> Right []; Just _ -> Left "incomplete closed proof elimination pair" };
    (:) XRefl rest -> do { actions <- closedParseLeaves original pending rest; Right ((:) ClosedIdentity actions) };
    (:) (XInner (XBottom argument)) rest -> case pending of {
      Nothing -> closedParseLeaves original (Just argument) rest;
      Just _ -> Left "closed proof has consecutive Inner operations"
    };
    (:) XElim rest -> case pending of {
      Nothing -> Left "closed proof has standalone/misordered Elim";
      Just argument -> do { actions <- closedParseLeaves original Nothing rest; Right ((:) (ClosedArgument argument original) actions) }
    };
    _ -> Left "closed-instance proof must contain only Refl or ordered Inner(Bottom argument),Elim pairs"
  };
  closedProofActions :: XComputation -> Either String ([] ClosedProofAction);
  closedProofActions proof = do {
    let { leaves = closedProofLeaves proof };
    L.ensure (L.length leaves <= 64) "closed proof exceeds 64 atoms";
    closedParseLeaves proof Nothing leaves
  };
  closedActions :: [] XComputation -> Either String ([] ClosedProofAction);
  closedActions proofs = do { parts <- L.traverseEither closedProofActions proofs; Right (L.concat parts) };
  closedActionArguments :: [] ClosedProofAction -> [] XType;
  closedActionArguments = L.concatMap (\action -> case action of { ClosedIdentity -> []; ClosedArgument argument _ -> [argument] });
  closedSpine :: XTerm -> (,) XTerm ([] XComputation);
  closedSpine term = case term of {
    XTypeApp value proof -> case closedSpine value of { (,) base proofs -> (,) base (L.append proofs [proof]) };
    _ -> (,) term []
  };
  closedWrapProofs :: XTerm -> [] XComputation -> XTerm;
  closedWrapProofs = L.foldl XTypeApp;
  closedPrefix :: XTerm -> [] ((,) XTyVar XType);
  closedPrefix term = case term of {
    XTypeAbs binder bound body -> (:) ((,) binder bound) (closedPrefix body);
    _ -> []
  };
  closedValidatePrefix :: [] ((,) XTyVar XType) -> Either String ();
  closedValidatePrefix prefix = do {
    L.ensure (L.not (L.null prefix) && L.length prefix <= 8) "closed-instance forall prefix must contain 1..8 binders";
    L.ensure (L.all (\((,) _ bound) -> bottomStar bound) prefix) "closed-instance forall bound must be bottom Star";
    L.ensure (L.length (L.nubBy T.equalTyVar (L.map L.fst prefix)) == L.length prefix) "duplicate closed-instance type binder";
    Right ()
  };
  closedApplyPrefix :: XTerm -> [] XType -> Either String XTerm;
  closedApplyPrefix term arguments = case arguments of {
    [] -> do { L.ensure (L.null (closedPrefix term)) "partial closed forall elimination"; Right term };
    (:) argument rest -> case term of {
      XTypeAbs binder bound body -> do {
        L.ensure (bottomStar bound && closedArgument argument) "closed substitution requires actual Int/Bool and bottom Star";
        substituted <- closedSubstituteTerm binder argument body;
        closedApplyPrefix substituted rest
      };
      _ -> Left "extra closed forall elimination"
    }
  };
  closedApplyType :: XType -> [] XType -> Either String XType;
  closedApplyType source arguments = case arguments of {
    [] -> case source of { XForall _ _ _ -> Left "partial closed scheme elimination"; _ -> Right source };
    (:) argument rest -> case source of {
      XForall binder bound body -> do {
        L.ensure (bottomStar bound && closedArgument argument) "closed scheme requires bottom Star and intrinsic scalar";
        closedApplyType (T.substitute binder argument body) rest
      };
      _ -> Left "extra closed scheme elimination"
    }
  };
  closedDirectSteps :: [] ((,) XTyVar XType) -> [] ClosedProofAction -> Either String ([] J.Json);
  closedDirectSteps prefix actions = case actions of {
    [] -> do { L.ensure (L.null prefix) "partial direct forall elimination"; Right [] };
    (:) ClosedIdentity rest -> do {
      steps <- closedDirectSteps prefix rest;
      Right ((:) (J.Object [("rule", J.String "erase_refl"), ("witness", computationNode XRefl)]) steps)
    };
    (:) (ClosedArgument argument witness) rest -> case prefix of {
      [] -> Left "extra direct forall elimination";
      (:) ((,) binder bound) binders -> do {
        steps <- closedDirectSteps binders rest;
        Right ((:) (J.Object [("rule", J.String "instantiate_closed"), ("binder", J.num (T.tyVarId binder)),
          ("bound", ty bound), ("argument", ty argument), ("witness", computationNode witness)]) steps)
      }
    }
  };
  closedDirectAction :: DataEnv -> XEnv -> [] String -> XTerm -> Either String (Maybe ((,) XTerm ([] J.Json)));
  closedDirectAction _ _ _ term = case term of {
    XTypeApp _ _ -> case closedSpine term of { (,) base proofs -> do {
      actions <- closedActions proofs;
      let { arguments = closedActionArguments actions; prefix = closedPrefix base };
      if L.null arguments then do {
        steps <- closedDirectSteps [] actions;
        Right (Just ((,) base steps))
      } else if L.null prefix then Right Nothing else do {
        closedValidatePrefix prefix;
        L.ensure (L.length prefix == L.length arguments) "partial/extra direct closed-instantiation vector";
        if L.all closedArgument arguments then do {
          body <- closedApplyPrefix base arguments;
          steps <- closedDirectSteps prefix actions;
          Right (Just ((,) body steps))
        } else Right Nothing
      }
    } };
    _ -> Right Nothing
  };
  closedTermEnv :: XEnv -> XName -> XType -> XEnv;
  closedTermEnv (XEnv types terms) binder annotation = XEnv types (M.insert X.compareName binder annotation terms);
  closedTypeEnv :: XEnv -> XTyVar -> XType -> XEnv;
  closedTypeEnv (XEnv types terms) binder bound = XEnv (M.insert T.compareTyVar binder bound types) terms;
  closedPath :: [] String -> String -> [] String;
  closedPath path edge = L.append path [edge];
  closedLift :: (XTerm -> XTerm) -> Maybe ((,) XTerm ([] J.Json)) -> Maybe ((,) XTerm ([] J.Json));
  closedLift constructor result = case result of {
    Nothing -> Nothing;
    Just ((,) body steps) -> Just ((,) (constructor body) steps)
  };
  closedVisit :: (DataEnv -> XEnv -> [] String -> XTerm -> Either String (Maybe ((,) XTerm ([] J.Json)))) ->
    DataEnv -> XEnv -> [] String -> XTerm -> Either String (Maybe ((,) XTerm ([] J.Json)));
  closedVisit action ds env path term = do {
    here <- action ds env path term;
    case here of {
      Just _ -> Right here;
      Nothing -> case term of {
        XAbs binder annotation body -> do {
          result <- closedVisit action ds (closedTermEnv env binder annotation) (closedPath path "body") body;
          Right (closedLift (XAbs binder annotation) result)
        };
        XApp function argument -> do {
          first <- closedVisit action ds env (closedPath path "function") function;
          case first of {
            Just _ -> Right (closedLift (\f -> XApp f argument) first);
            Nothing -> do { second <- closedVisit action ds env (closedPath path "argument") argument; Right (closedLift (XApp function) second) }
          }
        };
        XTypeAbs binder bound body -> do {
          result <- closedVisit action ds (closedTypeEnv env binder bound) path body;
          Right (closedLift (XTypeAbs binder bound) result)
        };
        XTypeApp _ _ -> case closedSpine term of { (,) base proofs -> do {
          result <- closedVisit action ds env path base;
          Right (closedLift (\value -> closedWrapProofs value proofs) result)
        } };
        XLet binder value body -> do {
          first <- closedVisit action ds env (closedPath path "value") value;
          case first of {
            Just _ -> Right (closedLift (\v -> XLet binder v body) first);
            Nothing -> do {
              annotation <- Check.inferIn ds env value;
              second <- closedVisit action ds (closedTermEnv env binder annotation) (closedPath path "body") body;
              Right (closedLift (XLet binder value) second)
            }
          }
        };
        XLetRec definitions body -> do {
          inner <- Check.inferRecursiveScope ds env definitions;
          first <- closedVisitDefinitions action ds inner path 0 definitions;
          case first of {
            Just ((,) values steps) -> Right (Just ((,) (XLetRec values body) steps));
            Nothing -> do { second <- closedVisit action ds inner (closedPath path "body") body; Right (closedLift (XLetRec definitions) second) }
          }
        };
        XCase scrutinee result alternatives -> do {
          first <- closedVisit action ds env (closedPath path "scrutinee") scrutinee;
          case first of {
            Just _ -> Right (closedLift (\s -> XCase s result alternatives) first);
            Nothing -> do {
              subject <- Check.inferIn ds env scrutinee;
              owner <- D.checkAlternatives ds (L.map Check.shape alternatives);
              parameters <- Check.caseParameters ds subject owner;
              second <- closedVisitAlternatives action ds env subject parameters path 0 alternatives;
              case second of {
                Nothing -> Right Nothing;
                Just ((,) branches steps) -> Right (Just ((,) (XCase scrutinee result branches) steps))
              }
            }
          }
        };
        XWithData declarations body -> do {
          actual <- D.validateDeclarations declarations;
          result <- closedVisit action actual env (closedPath path "body") body;
          Right (closedLift (XWithData declarations) result)
        };
        _ -> Right Nothing
      }
    }
  };
  closedVisitDefinitions :: (DataEnv -> XEnv -> [] String -> XTerm -> Either String (Maybe ((,) XTerm ([] J.Json)))) ->
    DataEnv -> XEnv -> [] String -> Int -> [] ((,,) XName XType XTerm) ->
    Either String (Maybe ((,) ([] ((,,) XName XType XTerm)) ([] J.Json)));
  closedVisitDefinitions action ds env path index definitions = case definitions of {
    [] -> Right Nothing;
    (:) ((,,) binder annotation value) rest -> do {
      result <- closedVisit action ds env (L.append path ["bindings", showInt index, "value"]) value;
      case result of {
        Just ((,) body steps) -> Right (Just ((,) ((:) ((,,) binder annotation body) rest) steps));
        Nothing -> do {
          next <- closedVisitDefinitions action ds env path (index + 1) rest;
          case next of { Nothing -> Right Nothing; Just ((,) values steps) -> Right (Just ((,) ((:) ((,,) binder annotation value) values) steps)) }
        }
      }
    }
  };
  closedVisitAlternatives :: (DataEnv -> XEnv -> [] String -> XTerm -> Either String (Maybe ((,) XTerm ([] J.Json)))) ->
    DataEnv -> XEnv -> XType -> Map String XType -> [] String -> Int -> [] XAlternative ->
    Either String (Maybe ((,) ([] XAlternative) ([] J.Json)));
  closedVisitAlternatives action ds env subject parameters path index alternatives = case alternatives of {
    [] -> Right Nothing;
    (:) (XAlternative pattern body) rest -> do {
      bindings <- Check.patternBindings ds subject parameters pattern;
      let { inner = L.foldl (\e ((,) n t) -> closedTermEnv e n t) env bindings };
      result <- closedVisit action ds inner (L.append path ["alternatives", showInt index, "body"]) body;
      case result of {
        Just ((,) value steps) -> Right (Just ((,) ((:) (XAlternative pattern value) rest) steps));
        Nothing -> do {
          next <- closedVisitAlternatives action ds env subject parameters path (index + 1) rest;
          case next of { Nothing -> Right Nothing; Just ((,) values steps) -> Right (Just ((,) ((:) (XAlternative pattern body) values) steps)) }
        }
      }
    }
  };
  data ClosedOccurrence = ClosedOccurrence ([] String) ([] XComputation) ([] XType);
  closedOccurrenceJson :: ClosedOccurrence -> J.Json;
  closedOccurrenceJson (ClosedOccurrence path witnesses _) = J.Object
    [("path", J.Array (L.map J.String path)), ("witnesses", J.Array (L.map computationNode witnesses))];
  closedCollect :: XName -> Int -> [] String -> XTerm -> Either String ((,) XTerm ([] ClosedOccurrence));
  closedCollect target arity path term = case term of {
    XVarTerm variable -> if X.equalName target variable then Left "bare/open/escaping polymorphic occurrence" else Right ((,) term []);
    XTypeApp _ _ -> case closedSpine term of { (,) base proofs -> case base of {
      XVarTerm variable -> if X.equalName target variable then do {
        actions <- closedActions proofs;
        let { arguments = closedActionArguments actions };
        L.ensure (L.length arguments == arity) "polymorphic occurrence must eliminate the complete ordered prefix";
        L.ensure (L.all closedArgument arguments) "polymorphic occurrence arguments must be closed intrinsic Int/Bool";
        Right ((,) base [ClosedOccurrence path proofs arguments])
      } else Right ((,) term []);
      _ -> do {
        result <- closedCollect target arity path base;
        case result of { (,) body occurrences -> Right ((,) (closedWrapProofs body proofs) occurrences) }
      }
    } };
    XAbs binder annotation body -> if X.equalName target binder then Right ((,) term []) else do {
      result <- closedCollect target arity (closedPath path "body") body;
      case result of { (,) value occurrences -> Right ((,) (XAbs binder annotation value) occurrences) }
    };
    XApp function argument -> do {
      first <- closedCollect target arity (closedPath path "function") function;
      second <- closedCollect target arity (closedPath path "argument") argument;
      case first of { (,) f left -> case second of { (,) a right -> Right ((,) (XApp f a) (L.append left right)) } }
    };
    XTypeAbs binder bound body -> do {
      result <- closedCollect target arity path body;
      case result of { (,) value occurrences -> Right ((,) (XTypeAbs binder bound value) occurrences) }
    };
    XLet binder rhs body -> do {
      first <- closedCollect target arity (closedPath path "value") rhs;
      second <- if X.equalName target binder then Right ((,) body []) else closedCollect target arity (closedPath path "body") body;
      case first of { (,) value left -> case second of { (,) result right -> Right ((,) (XLet binder value result) (L.append left right)) } }
    };
    XLetRec definitions body -> if L.any (\((,,) binder _ _) -> X.equalName target binder) definitions
      then Right ((,) term []) else do {
        first <- closedCollectDefinitions target arity path 0 definitions;
        second <- closedCollect target arity (closedPath path "body") body;
        case first of { (,) values left -> case second of { (,) result right -> Right ((,) (XLetRec values result) (L.append left right)) } }
      };
    XCase scrutinee annotation alternatives -> do {
      first <- closedCollect target arity (closedPath path "scrutinee") scrutinee;
      second <- closedCollectAlternatives target arity path 0 alternatives;
      case first of { (,) value left -> case second of { (,) branches right -> Right ((,) (XCase value annotation branches) (L.append left right)) } }
    };
    XWithData declarations body -> do {
      result <- closedCollect target arity (closedPath path "body") body;
      case result of { (,) value occurrences -> Right ((,) (XWithData declarations value) occurrences) }
    };
    _ -> Right ((,) term [])
  };
  closedCollectDefinitions :: XName -> Int -> [] String -> Int -> [] ((,,) XName XType XTerm) ->
    Either String ((,) ([] ((,,) XName XType XTerm)) ([] ClosedOccurrence));
  closedCollectDefinitions target arity path index definitions = case definitions of {
    [] -> Right ((,) [] []);
    (:) ((,,) binder annotation rhs) rest -> do {
      first <- closedCollect target arity (L.append path ["bindings", showInt index, "value"]) rhs;
      second <- closedCollectDefinitions target arity path (index + 1) rest;
      case first of { (,) value left -> case second of { (,) values right -> Right ((,) ((:) ((,,) binder annotation value) values) (L.append left right)) } }
    }
  };
  closedCollectAlternatives :: XName -> Int -> [] String -> Int -> [] XAlternative ->
    Either String ((,) ([] XAlternative) ([] ClosedOccurrence));
  closedCollectAlternatives target arity path index alternatives = case alternatives of {
    [] -> Right ((,) [] []);
    (:) (XAlternative pattern body) rest -> do {
      first <- if L.any (X.equalName target) (X.patternNames pattern) then Right ((,) body [])
        else closedCollect target arity (L.append path ["alternatives", showInt index, "body"]) body;
      second <- closedCollectAlternatives target arity path (index + 1) rest;
      case first of { (,) value left -> case second of { (,) values right -> Right ((,) ((:) (XAlternative pattern value) values) (L.append left right)) } }
    }
  };
  closedLetAction :: DataEnv -> XEnv -> [] String -> XTerm -> Either String (Maybe ((,) XTerm ([] J.Json)));
  closedLetAction ds env path term = case term of {
    XLet binder rhs body -> let { prefix = closedPrefix rhs } in
      if L.null prefix then Right Nothing else do {
        closedValidatePrefix prefix;
        originalType <- Check.inferIn ds env rhs;
        collected <- closedCollect binder (L.length prefix) (closedPath path "body") body;
        case collected of { (,) rewritten occurrences -> do {
          L.ensure (L.not (L.null occurrences) && L.length occurrences <= 256)
            "generalized let requires 1..256 fully recorded occurrences";
          case occurrences of {
            [] -> Left "unused generalized let has no closed instance";
            (:) (ClosedOccurrence _ _ arguments) _ -> do {
              L.ensure (L.all (\(ClosedOccurrence _ _ vector) -> X.equalList T.alphaEq arguments vector) occurrences)
                "generalized let has mixed closed instantiations";
              specialized <- closedApplyPrefix rhs arguments;
              instantiatedType <- closedApplyType originalType arguments;
              actualType <- Check.inferIn ds env specialized;
              L.ensure (T.alphaEq instantiatedType actualType) "specialized let type differs from ordinary inferred instance";
              let { step = J.Object [("rule", J.String "specialize_let"), ("binding", name binder),
                ("type_binders", J.Array (L.map (\((,) variable bound) -> J.Object [("id", J.num (T.tyVarId variable)), ("bound", ty bound)]) prefix)),
                ("arguments", J.Array (L.map ty arguments)), ("original_type", ty originalType),
                ("instantiated_type", ty instantiatedType), ("occurrences", J.Array (L.map closedOccurrenceJson occurrences))] };
              Right (Just ((,) (XLet binder specialized rewritten) [step]))
            }
          }
        } }
      };
    _ -> Right Nothing
  };
  closedHasForall :: XType -> Bool;
  closedHasForall annotation = case annotation of {
    XForall _ _ _ -> True;
    XArrow a b -> closedHasForall a || closedHasForall b;
    XCon _ arguments -> L.any closedHasForall arguments;
    XApply a b -> closedHasForall a || closedHasForall b;
    _ -> False
  };
  closedCheckRecursive :: XTerm -> Either String ();
  closedCheckRecursive term = case term of {
    XLetRec definitions body -> do {
      L.ensure (L.all (\((,,) _ annotation rhs) -> L.not (closedHasForall annotation) && L.null (closedPrefix rhs)) definitions)
        "recursive polymorphic bindings are outside the closed-instance route";
      L.traverseEither (\((,,) _ _ rhs) -> closedCheckRecursive rhs) definitions;
      closedCheckRecursive body
    };
    XAbs _ _ body -> closedCheckRecursive body;
    XApp a b -> do { closedCheckRecursive a; closedCheckRecursive b };
    XTypeAbs _ _ body -> closedCheckRecursive body;
    XTypeApp body _ -> closedCheckRecursive body;
    XLet _ rhs body -> do { closedCheckRecursive rhs; closedCheckRecursive body };
    XCase subject _ alternatives -> do {
      closedCheckRecursive subject;
      L.traverseEither (\(XAlternative _ body) -> closedCheckRecursive body) alternatives;
      Right ()
    };
    XWithData _ body -> closedCheckRecursive body;
    _ -> Right ()
  };
  closedConcreteType :: XType -> Bool;
  closedConcreteType annotation = case annotation of {
    XVar _ -> False;
    XBot -> False;
    XBotKind _ -> False;
    XForall _ _ _ -> False;
    XArrow a b -> closedConcreteType a && closedConcreteType b;
    XCon _ arguments -> L.all closedConcreteType arguments;
    XApply _ _ -> False;
    _ -> True
  };
  closedComplete :: XTerm -> Either String ();
  closedComplete term = case term of {
    XTypeAbs _ _ _ -> Left "unresolved type abstraction remains after closed specialization";
    XTypeApp _ _ -> Left "unresolved type application remains after closed specialization";
    XAbs _ annotation body -> do {
      L.ensure (closedConcreteType annotation) "open/forall lambda annotation remains"; closedComplete body
    };
    XApp a b -> do { closedComplete a; closedComplete b };
    XLet _ rhs body -> do { closedComplete rhs; closedComplete body };
    XLetRec definitions body -> do {
      L.traverseEither (\((,,) _ annotation rhs) -> do {
        L.ensure (closedConcreteType annotation) "open/forall recursive annotation remains"; closedComplete rhs
      }) definitions;
      closedComplete body
    };
    XCase subject annotation alternatives -> do {
      L.ensure (closedConcreteType annotation) "open/forall case result annotation remains";
      closedComplete subject;
      L.traverseEither (\(XAlternative _ body) -> closedComplete body) alternatives;
      Right ()
    };
    XPrimitive _ arguments -> L.ensure (L.all closedConcreteType arguments) "open primitive type argument remains";
    XConstructor _ arguments -> L.ensure (L.all closedArgument arguments) "constructor argument is not closed intrinsic Int/Bool";
    XWithData _ body -> closedComplete body;
    _ -> Right ()
  };
  closedNormalizeLoop :: Int -> XTerm -> Either String ((,) XTerm ([] J.Json));
  closedNormalizeLoop bindingsCount term = do {
    direct <- closedVisit closedDirectAction D.emptyDataEnv Check.emptyEnv [] term;
    case direct of {
      Just ((,) current steps) -> do {
        result <- closedNormalizeLoop bindingsCount current;
        case result of { (,) final rest -> Right ((,) final (L.append steps rest)) }
      };
      Nothing -> do {
        binding <- closedVisit closedLetAction D.emptyDataEnv Check.emptyEnv [] term;
        case binding of {
          Just ((,) current steps) -> do {
            L.ensure (bindingsCount < 64) "closed-instance route exceeds 64 generalized bindings";
            result <- closedNormalizeLoop (bindingsCount + 1) current;
            case result of { (,) final rest -> Right ((,) final (L.append steps rest)) }
          };
          Nothing -> do { closedComplete term; Right ((,) term []) }
        }
      }
    }
  };
  normalizeClosedChecked :: K.CheckedTerm -> Either String ((,,) K.CheckedTerm K.CheckedTerm ([] J.Json));
  normalizeClosedChecked supplied = do {
    original <- K.check (K.term supplied);
    L.ensure (T.alphaEq (K.typeOf supplied) (K.typeOf original)) "supplied checked receipt disagrees with fresh original check";
    closedCheckRecursive (K.term original);
    result <- closedNormalizeLoop 0 (K.term original);
    case result of { (,) term steps -> do {
      current <- K.check term;
      L.ensure (T.alphaEq (K.typeOf original) (K.typeOf current)) "closed-instance normalization changed root type";
      L.ensure (X.equalErased (X.erase (K.term original)) (X.erase term)) "closed-instance normalization changed exact erasure";
      L.ensure (eqString (J.render (J.Array (L.map declarationNode (closedDeclarations (K.term original)))))
        (J.render (J.Array (L.map declarationNode (closedDeclarations term))))) "closed-instance normalization changed declarations";
      before <- closedSkeleton (K.term original);
      after <- closedSkeleton term;
      L.ensure (eqString (J.render before) (J.render after)) "closed-instance normalization changed term skeleton/sharing";
      Right ((,,) original current steps)
    } }
  };
  closedActualDeclarations :: DataEnv -> [] DataDecl -> Either String ([] DataDecl);
  closedActualDeclarations ds declarations = L.traverseEither (\source -> do {
    actual <- D.lookupDatatype ds (D.datatypeName source);
    L.ensure (eqString (J.render (declarationNode source)) (J.render (declarationNode actual))) "datatype registry changes raw declaration";
    L.ensure (L.not (L.null (D.datatypeConstructors actual)) && L.length (D.datatypeConstructors actual) <= 64)
      "datatype requires 1..64 complete variants";
    if isSumDeclaration actual then do {
      L.ensure (L.length (D.datatypeBinders actual) <= 8) "sum template exceeds 8 parameters";
      L.ensure (L.all (\((,) _ k) -> L.eqKind k Star) (D.datatypeBinders actual)) "sum template parameters must have actual Star kind";
      Right actual
    } else do {
      L.ensure (L.null (D.datatypeBinders actual)) "parameterized records are outside the closed sum route";
      Right actual
    }
  }) declarations;
  closedFindDeclaration :: [] DataDecl -> String -> Either String DataDecl;
  closedFindDeclaration declarations nominal = case L.find (\d -> eqString nominal (D.datatypeName d)) declarations of {
    Nothing -> Left "nominal identity is not in the complete user declaration inventory";
    Just declaration -> Right declaration
  };
  closedRegister :: [] DataDecl -> [] ((,) String ([] XType)) -> String -> [] XType ->
    Either String ([] ((,) String ([] XType)));
  closedRegister declarations registry nominal arguments = do {
    declaration <- closedFindDeclaration declarations nominal;
    L.ensure (isSumDeclaration declaration) "closed sum reference names a record, not a sum";
    L.ensure (L.length arguments == L.length (D.datatypeBinders declaration)) "closed instance arity differs from actual declaration";
    L.ensure (L.all closedArgument arguments) "closed sum arguments must be actual intrinsic Int/Bool";
    case L.lookup eqString nominal registry of {
      Just previous -> do {
        L.ensure (X.equalList T.alphaEq previous arguments) "one declaration has mixed closed instance vectors";
        Right registry
      };
      Nothing -> do {
        L.ensure (L.length registry < 64) "closed instance registry exceeds 64 families";
        Right (L.append registry [((,) nominal arguments)])
      }
    }
  };
  closedTypeInstances :: [] DataDecl -> [] ((,) String ([] XType)) -> XType -> Either String ([] ((,) String ([] XType)));
  closedTypeInstances declarations registry annotation = case annotation of {
    XCon nominal arguments -> do {
      current <- case L.find (\d -> eqString nominal (D.datatypeName d)) declarations of {
        Just declaration -> if isSumDeclaration declaration then closedRegister declarations registry nominal arguments else Right registry;
        Nothing -> Right registry
      };
      L.foldEither (closedTypeInstances declarations) current arguments
    };
    XArrow a b -> do { current <- closedTypeInstances declarations registry a; closedTypeInstances declarations current b };
    XApply f a -> do { current <- closedTypeInstances declarations registry f; closedTypeInstances declarations current a };
    XForall _ bound body -> do { current <- closedTypeInstances declarations registry bound; closedTypeInstances declarations current body };
    _ -> Right registry
  };
  closedTermInstances :: DataEnv -> [] DataDecl -> [] ((,) String ([] XType)) -> XTerm ->
    Either String ([] ((,) String ([] XType)));
  closedTermInstances ds declarations registry term = case term of {
    XAbs _ annotation body -> do {
      current <- closedTypeInstances declarations registry annotation;
      closedTermInstances ds declarations current body
    };
    XApp a b -> do { current <- closedTermInstances ds declarations registry a; closedTermInstances ds declarations current b };
    XLet _ rhs body -> do { current <- closedTermInstances ds declarations registry rhs; closedTermInstances ds declarations current body };
    XTypeAbs _ _ body -> closedTermInstances ds declarations registry body;
    XTypeApp body _ -> closedTermInstances ds declarations registry body;
    XLetRec definitions body -> do {
      current <- L.foldEither (\state ((,,) _ annotation rhs) -> do {
        typed <- closedTypeInstances declarations state annotation;
        closedTermInstances ds declarations typed rhs
      }) registry definitions;
      closedTermInstances ds declarations current body
    };
    XConstructor constructor arguments -> do {
      pair <- D.lookupConstructor ds constructor;
      case pair of { (,) owner actual ->
        if eqString (D.datatypeName owner) "()" && eqString (D.constructorName actual) "()" && L.null arguments
          then Right registry else do {
          declaration <- closedFindDeclaration declarations (D.datatypeName owner);
          actualConstructor ds declaration actual;
          if isSumDeclaration declaration then closedRegister declarations registry (D.datatypeName declaration) arguments
          else do { L.ensure (L.null arguments) "record constructor must be parameterless"; Right registry }
        }
      }
    };
    XPrimitive _ arguments -> L.foldEither (closedTypeInstances declarations) registry arguments;
    XCase subject annotation alternatives -> do {
      typed <- closedTypeInstances declarations registry annotation;
      current <- closedTermInstances ds declarations typed subject;
      L.foldEither (\state (XAlternative _ body) -> closedTermInstances ds declarations state body) current alternatives
    };
    XWithData _ body -> closedTermInstances ds declarations registry body;
    _ -> Right registry
  };
  closedInstantiatedFields :: DataEnv -> DataDecl -> [] XType -> ConstructorDecl -> Either String ([] XType);
  closedInstantiatedFields ds declaration arguments constructor = do {
    actual <- actualConstructor ds declaration constructor;
    L.ensure (L.length arguments == L.length (D.datatypeBinders declaration)) "field instance argument arity mismatch";
    L.ensure (L.all closedArgument arguments) "field instance argument is not a closed intrinsic scalar";
    let { parameters = M.fromList compareString (L.zip (D.datatypeParameters declaration) arguments) };
    fields <- L.traverseEither (T.instantiateField parameters) (D.constructorFields actual);
    L.ensure (L.length fields <= 32) "sum variant exceeds 32 complete fields";
    L.traverseEither (Check.termType ds M.empty) fields;
    Right fields
  };
  closedFieldInstance :: [] DataDecl -> [] ((,) String ([] XType)) -> XType -> Either String ([] ((,) String ([] XType)));
  closedFieldInstance declarations registry field =
    if closedArgument field then Right registry else case field of {
      XCon nominal arguments -> closedRegister declarations registry nominal arguments;
      _ -> Left "instantiated sum fields require closed Int/Bool/SUM; no arrow/quantified/application payload"
    };
  closedResolveInstances :: DataEnv -> [] DataDecl -> [] String -> [] ((,) String ([] XType)) ->
    Either String ([] ((,) String ([] XType)));
  closedResolveInstances ds declarations visited registry =
    case L.find (\((,) nominal _) -> L.not (L.any (eqString nominal) visited)) registry of {
      Nothing -> Right registry;
      Just ((,) nominal arguments) -> do {
        declaration <- closedFindDeclaration declarations nominal;
        fields <- L.traverseEither (closedInstantiatedFields ds declaration arguments) (D.datatypeConstructors declaration);
        current <- L.foldEither (closedFieldInstance declarations) registry (L.concat fields);
        closedResolveInstances ds declarations ((:) nominal visited) current
      }
    };
  closedTemplate :: Int -> DataDecl -> J.Json;
  closedTemplate index declaration = J.Object [("declaration_index", J.num index),
    ("datatype", J.String (D.datatypeName declaration)),
    ("parameters", J.Array (L.map (\((,) parameter k) -> J.Object [("name", J.String parameter), ("kind", kind k)]) (D.datatypeBinders declaration))),
    ("constructors", J.Array (L.map (\constructor -> J.Object [("constructor", J.String (D.constructorName constructor)),
      ("arity", J.num (L.length (D.constructorFields constructor))),
      ("fields", J.Array (L.map fieldNode (D.constructorFields constructor)))]) (D.datatypeConstructors declaration)))];
  closedInstance :: DataEnv -> [] ((,) String ([] XType)) -> Int -> DataDecl -> Either String J.Json;
  closedInstance ds registry index declaration =
    case L.lookup eqString (D.datatypeName declaration) registry of {
      Nothing -> Left "parameterized sum has no proven concrete instance; unused schema cannot be pruned";
      Just arguments -> do {
        constructors <- L.traverseEither (\constructor -> do {
          fields <- closedInstantiatedFields ds declaration arguments constructor;
          Right (J.Object [("constructor", J.String (D.constructorName constructor)), ("arity", J.num (L.length fields)),
            ("fields", J.Array (L.map ty fields))])
        }) (D.datatypeConstructors declaration);
        Right (J.Object [("declaration_index", J.num index), ("datatype", J.String (D.datatypeName declaration)),
          ("arguments", J.Array (L.map ty arguments)), ("constructors", J.Array constructors)])
      }
    };
  closedMetadata :: K.CheckedTerm -> Either String ((,,) J.Json J.Json J.Json);
  closedMetadata checked = do {
    ds <- checkedDataEnv checked;
    declarations <- closedActualDeclarations ds (closedDeclarations (K.term checked));
    let { indexed = L.mapIndexed (\index declaration -> (,) index declaration) declarations;
          sums = L.filter (\((,) _ declaration) -> isSumDeclaration declaration) indexed;
          records = L.filter (\((,) _ declaration) -> L.not (isSumDeclaration declaration)) indexed };
    L.ensure (L.length sums <= 64) "sum template registry exceeds 64 families";
    seeds <- L.foldEither (\registry ((,) _ declaration) ->
      if L.null (D.datatypeBinders declaration) then closedRegister declarations registry (D.datatypeName declaration) []
      else Right registry) [] sums;
    used <- closedTermInstances ds declarations seeds (K.term checked);
    registry <- closedResolveInstances ds declarations [] used;
    instances <- L.traverseEither (\((,) index declaration) -> closedInstance ds registry index declaration) sums;
    recordNodes <- L.traverseEither (\((,) _ declaration) -> case D.datatypeConstructors declaration of {
      [constructor] -> recordMetadata ds declaration constructor;
      _ -> Left "record metadata requires its actual singleton constructor"
    }) records;
    Right ((,,) (J.Array recordNodes) (J.Array (L.map (\((,) index declaration) -> closedTemplate index declaration) sums)) (J.Array instances))
  };
  exportChecked :: String -> String -> K.CheckedTerm -> Either String String;
  exportChecked sourceCommit dependencyDigest checked = do {
    normalized <- if closedRoute (K.term checked) then normalizeClosedChecked checked else normalizeChecked checked;
    case normalized of { (,,) original current steps -> do {
      let { originalTerm = K.term original; term = K.term current };
      runtimeAnnotations <- annotated term;
      originalAnnotations <- rawAnnotated originalTerm;
      normalizedAnnotations <- rawAnnotated term;
      originalErasure <- erased (X.erase originalTerm);
      actualErasure <- erased (X.erase term);
      unit <- unitMetadata;
      scalars <- builtinScalarMetadata;
      metadata <- closedMetadata current;
      let { custom = case metadata of { (,,) records _ _ -> records };
            sums = case metadata of { (,,) _ templates _ -> templates };
            instances = case metadata of { (,,) _ _ values -> values } };
      originalSkeleton <- closedSkeleton originalTerm;
      normalizedSkeleton <- closedSkeleton term;
      let { skeletonFields = if closedRoute originalTerm then [("original_term_skeleton", originalSkeleton), ("normalized_term_skeleton", normalizedSkeleton)] else [] };
      Right (J.render (J.Object [
        ("format", J.String "mlf-checked-recursion-export/6"),
        ("producer", J.Object [("source_commit", J.String sourceCommit), ("dependency_digest", J.String dependencyDigest)]),
        ("checked_type", ty (K.typeOf current)),
        ("checked_type_pretty", J.String (P.prettyType (K.typeOf current))),
        ("checked_term_pretty", J.String (P.prettyTerm term)),
        ("declaration_bindings", bindings current),
        ("representation", J.Object [("builtin_unit", unit), ("builtin_scalars", scalars), ("custom_datatypes", custom), ("custom_sums", sums), ("sum_instances", instances)]),
        ("annotated", runtimeAnnotations), ("erased", actualErasure),
        ("normalization", J.Object (L.append [
          ("policy", J.String (if closedRoute originalTerm then "single-closed-instance/1" else if containsConditional originalTerm then "closed-int-standard-instantiation/1" else "identity-no-conditional/1")),
          ("original_checked_type", ty (K.typeOf original)),
          ("original_checked_type_pretty", J.String (P.prettyType (K.typeOf original))),
          ("original_checked_term_pretty", J.String (P.prettyTerm originalTerm)),
          ("original_declaration_bindings", bindings original),
          ("original_annotated", originalAnnotations), ("original_erased", originalErasure),
          ("normalized_annotated", normalizedAnnotations), ("steps", J.Array steps),
          ("original_rechecked", J.Boolean True), ("normalized_rechecked", J.Boolean True),
          ("root_type_alpha_equal", J.Boolean True), ("erasure_equal", J.Boolean True)] skeletonFields))]))
    } }
  };
}
