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
  import qualified Bootstrap.X.Checked as K;
  import qualified Bootstrap.X.Syntax as X;
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
  annotated :: XTerm -> Either String J.Json;
  annotated term = case term of {
    XVarTerm n -> Right (obj "var" [("name", name n)]);
    XAbs n a b -> do { body <- annotated b; Right (obj "lambda" [("parameter", name n), ("parameter_type", ty a), ("body", body)]) };
    XApp f a -> do { function <- annotated f; argument <- annotated a; Right (obj "application" [("function", function), ("argument", argument)]) };
    XLet n a b -> do { rhs <- annotated a; body <- annotated b; Right (obj "let" [("name", name n), ("value", rhs), ("body", body)]) };
    XTypeAbs (XTyVar n) bound b -> do { body <- annotated b; Right (obj "type_lambda" [("id", J.num n), ("bound", ty bound), ("body", body)]) };
    XTypeApp a p -> do { value <- annotated a; Right (obj "type_application" [("value", value), ("witness", J.String (P.prettyComputation p))]) };
    XConstructor c args -> if eqString c "()" && L.null args then Right (obj "unit" [])
      else Right (obj "constructor" [("name", J.String c), ("arguments", J.Array (L.map ty args))]);
    XWithData _ b -> annotated b;
    XLetRec bs b -> do {
      definitions <- L.traverseEither (\((,,) n t v) -> do { value <- annotated v; Right (J.Object [("name", name n), ("type", ty t), ("value", value)]) }) bs;
      body <- annotated b;
      Right (obj "letrec" [("bindings", J.Array definitions), ("body", body)])
    };
    XCase s t alts -> do {
      scrutinee <- annotated s;
      alternatives <- L.traverseEither (\(XAlternative p b) -> do { patternJson <- patternNode p; body <- annotated b; Right (J.Object [("pattern", patternJson), ("body", body)]) }) alts;
      Right (obj "case" [("scrutinee", scrutinee), ("result_type", ty t), ("alternatives", J.Array alternatives)])
    };
    XIntTerm _ -> Left "Int payloads are outside the resource-native fragment (not narrowed or erased)";
    XDoubleTerm _ -> Left "Double payloads are outside the resource-native fragment";
    XBoolTerm _ -> Left "Bool payloads are outside the resource-native fragment";
    XStringTerm _ -> Left "String payloads are outside the resource-native fragment";
    XPrimitive _ _ -> Left "primitive/FFI contracts are outside the resource-native fragment"
  };
  patternNode :: XPattern -> Either String J.Json;
  patternNode p = case p of {
    XConstructorPattern c fields -> Right (J.Object [("constructor", J.String c), ("fields", J.Array (L.map fieldName fields))]);
    XDefaultPattern _ -> Left "default patterns are outside the single-constructor resource-native fragment"
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
    XEInt _ -> Left "unsupported erased Int";
    XEDouble _ -> Left "unsupported erased Double";
    XEBool _ -> Left "unsupported erased Bool";
    XEString _ -> Left "unsupported erased String";
    XEPrimitive _ -> Left "unsupported erased primitive";
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
  customMetadata checked = do {
    env <- checkedDataEnv checked;
    let { declarations = case K.term checked of { XWithData ds _ -> ds; _ -> [] } };
    items <- L.traverseEither (\source -> do {
      d <- D.lookupDatatype env (D.datatypeName source);
      if L.not (L.null (D.datatypeParameters d)) then Left "parameterized datatypes unsupported" else
        case D.datatypeConstructors d of {
          [c] -> do {
            fields <- L.traverseEither fieldType (D.constructorFields c);
            Right (J.Object [("datatype", J.String (D.datatypeName d)), ("constructor", J.String (D.constructorName c)), ("arity", J.num (L.length fields)), ("fields", J.Array (L.map ty fields))])
          };
          _ -> Left "only single-constructor datatypes are supported"
        }
    }) declarations;
    Right (J.Array items)
  };
  exportChecked :: String -> String -> K.CheckedTerm -> Either String String;
  exportChecked sourceCommit dependencyDigest checked = do {
    let { term = K.term checked };
    runtimeAnnotations <- annotated term;
    actualErasure <- erased (X.erase term);
    unit <- unitMetadata;
    custom <- customMetadata checked;
    Right (J.render (J.Object [
      ("format", J.String "mlf-checked-recursion-export/1"),
      ("producer", J.Object [("source_commit", J.String sourceCommit), ("dependency_digest", J.String dependencyDigest)]),
      ("checked_type", ty (K.typeOf checked)),
      ("checked_type_pretty", J.String (P.prettyType (K.typeOf checked))),
      ("checked_term_pretty", J.String (P.prettyTerm term)),
      ("declaration_bindings", bindings checked),
      ("representation", J.Object [("builtin_unit", unit), ("custom_datatypes", custom)]),
      ("annotated", runtimeAnnotations), ("erased", actualErasure)]))
  };
}
