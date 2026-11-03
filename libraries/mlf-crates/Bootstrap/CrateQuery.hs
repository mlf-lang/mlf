-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.CrateQuery where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Desugar as Desugar;
  import qualified Bootstrap.InferenceUnit as Inference;
  import qualified Bootstrap.SourceInference as Source;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Bitstream as W;
  import qualified Bootstrap.ArtifactStructure as Structure;
  import qualified Bootstrap.ArtifactStorage as Storage;
  import qualified Bootstrap.Primitive as Primitive;
  import qualified Bootstrap.Host as Host;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.SourceEquality as SourceEquality;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Pretty as Pretty;
  -- Length framing and constructor tags preserve the complete lowered syntax.
  -- Pretty source text is unsuitable here: annotations, evidence roles, signed
  -- zero, quantifier flags and binder scopes are semantic query inputs.
  node tag fields = Separate.pack ((:) tag fields);
  list encode values = Separate.pack (map encode values);
  optional encode value =
    case value of {
      Nothing -> node "none" [];
      Just a -> node "some" ((:) (encode a) [])
    };
  boolean :: Bool -> String;
  boolean b = if b then "true" else "false";
  encodeKind :: Kind -> String;
  encodeKind kind =
    case kind of {
      Star -> node "star" [];
      KArrow a b -> node "kind-arrow" ((:) (encodeKind a) ((:) (encodeKind b) []))
    };
  encodeFlag :: Flag -> String;
  encodeFlag flag =
    case flag of {
      Flexible -> "flexible";
      Rigid -> "rigid"
    };
  encodeType :: SType -> String;
  encodeType ty =
    case ty of {
      STVar n -> node "variable" ((:) n []);
      SBottom -> node "bottom" [];
      SBottomKind k -> node "bottom-kind" ((:) (encodeKind k) []);
      SArrow a b -> node "arrow" ((:) (encodeType a) ((:) (encodeType b) []));
      SCon n args -> node "constructor" ((:) n ((:) (list encodeType args) []));
      STypeApp f a -> node "application" ((:) (encodeType f) ((:) (encodeType a) []));
      SForall flag n bound body ->
        node "forall"
          ((:) (encodeFlag flag) ((:) n ((:) (encodeType bound) ((:) (encodeType body) []))));
      SQualified predicates body ->
        node "qualified" ((:) (list encodePredicate predicates) ((:) (encodeType body) []))
    };
  encodePredicate :: SPredicate -> String;
  encodePredicate (SPredicate n args) = node "predicate" ((:) n ((:) (list encodeType args) []));
  encodeAnnotation (SAnnotation existential ty) =
    node "annotation" ((:) (Separate.pack existential) ((:) (encodeType ty) []));
  encodeSourceString :: SourceString -> String;
  encodeSourceString s = case s of {
    ScalarString text -> node "scalar-source-string" ((:) text []);
    CharString codes -> node "char-source-string" ((:) (list showInt codes) [])
  };
  encodePattern :: SPattern -> String;
  encodePattern pattern =
    case pattern of {
      SConstructorPattern n names ->
        node "constructor-pattern" ((:) n ((:) (list (optional id) names) []));
      SDefaultPattern name -> node "default-pattern" ((:) (optional id name) []);
      SNestedPattern n patterns ->
        node "nested-pattern" ((:) n ((:) (list encodePattern patterns) []));
      SAnnotatedPattern n a -> node "annotated-pattern" ((:) n ((:) (encodeAnnotation a) []));
      SIntPattern n -> node "integer-pattern" ((:) (showInt n) []);
      SAsPattern n pattern -> node "as-pattern" ((:) n ((:) (encodePattern pattern) []));
      SLazyPattern pattern -> node "lazy-pattern" ((:) (encodePattern pattern) []);
      SStringPattern s -> node "string-pattern" ((:) s []);
      SOverloadedStringPattern s equal fromString ->
        node "overloaded-string-pattern" ((:) (encodeSourceString s) ((:) equal ((:) fromString [])));
      SBoolPattern b -> node "boolean-pattern" ((:) (boolean b) [])
    };
  encodeRole :: EvidenceRole -> String;
  encodeRole role =
    case role of {
      GivenEvidence -> "given";
      SuperclassEvidence -> "superclass";
      InstanceEvidence -> "instance"
    };
  encodeCandidate ((,) role name) = node (encodeRole role) ((:) name []);
  encodeSourceSpan (SourceSpan packageName moduleName file startLine startColumn endLine endColumn) =
    node "source-span"
      ((:) packageName ((:) moduleName ((:) file
         ((:) (showInt startLine) ((:) (showInt startColumn)
            ((:) (showInt endLine) ((:) (showInt endColumn) [])))))));
  encodeExpression :: SExpr -> String;
  encodeExpression expression =
    case expression of {
      SVar n -> node "variable" ((:) n []);
      SConstructor n -> node "constructor" ((:) n []);
      SLam n annotation body ->
        node "lambda"
          ((:) n ((:) (optional encodeAnnotation annotation) ((:) (encodeExpression body) [])));
      SApp a b -> node "apply" ((:) (encodeExpression a) ((:) (encodeExpression b) []));
      SLet n a b -> node "let" ((:) n ((:) (encodeExpression a) ((:) (encodeExpression b) [])));
      SAnn a annotation ->
        node "annotate" ((:) (encodeExpression a) ((:) (encodeAnnotation annotation) []));
      SSignature a annotation ->
        node "signature" ((:) (encodeExpression a) ((:) (encodeAnnotation annotation) []));
      SIntLit n -> node "integer" ((:) (showInt n) []);
      SDoubleLit n -> node "double-bits" ((:) (showInt (doubleToBits n)) []);
      SBoolLit b -> node "boolean" ((:) (boolean b) []);
      SStringLit s -> node "string" ((:) s []);
      SPrimitive p -> node "primitive" ((:) (Primitive.primitiveName p) []);
      SCase a branches ->
        node "case" ((:) (encodeExpression a) ((:) (list encodeAlternative branches) []));
      SSourceDefinition body -> node "source-definition" ((:) (encodeExpression body) []);
      SCallSite label span body ->
        node "call-site" ((:) label ((:) (encodeSourceSpan span) ((:) (encodeExpression body) [])));
      SSharedBind pattern action continuation bindMethod failure ->
        node "shared-bind"
          ((:) (encodePattern pattern) ((:) (encodeExpression action)
             ((:) (encodeExpression continuation) ((:) (encodeExpression bindMethod)
                ((:) (encodeExpression failure) [])))));
      SDo statements body ->
        node "do" ((:) (list encodeStatement statements) ((:) (encodeExpression body) []));
      SEquations rows -> node "equations" ((:) (list encodeEquation rows) []);
      SLetRec definitions body ->
        node "letrec" ((:) (list encodeRecursive definitions) ((:) (encodeExpression body) []));
      SWanted dictionary candidates ->
        node "wanted" ((:) dictionary ((:) (list encodeCandidate candidates) []));
      SChecked ty body -> node "checked" ((:) (encodeType ty) ((:) (encodeExpression body) []))
    };
  encodeAlternative :: SAlternative -> String;
  encodeAlternative (SAlternative pattern body) =
    node "alternative" ((:) (encodePattern pattern) ((:) (encodeExpression body) []));
  encodeEquation :: (,) ([] SPattern) SExpr -> String;
  encodeEquation ((,) patterns body) =
    node "equation" ((:) (list encodePattern patterns) ((:) (encodeExpression body) []));
  encodeRecursive :: (,,) String RecursiveMode SExpr -> String;
  encodeRecursive ((,,) n mode body) =
    case mode of {
      InferRecursive -> node "recursive-infer" ((:) n ((:) (encodeExpression body) []));
      -- Preserve the signed representation used by existing query keys.
      CheckRecursive annotation ->
        node "recursive"
          ((:) n ((:) (encodeAnnotation annotation) ((:) (encodeExpression body) [])))
    };
  encodeStatement :: SStatement -> String;
  encodeStatement statement =
    case statement of {
      SDoBind pattern body ->
        node "do-bind" ((:) (encodePattern pattern) ((:) (encodeExpression body) []));
      SDoThen body -> node "do-then" ((:) (encodeExpression body) []);
      SDoLet n annotation body ->
        node "do-let"
          ((:) n ((:) (optional encodeAnnotation annotation) ((:) (encodeExpression body) [])));
      SDoLetRec definitions -> node "do-letrec" ((:) (list encodeRecursive definitions) [])
    };
  encodeMember ((,,) n annotation body) =
    node "member"
      ((:) n ((:) (optional encodeAnnotation annotation) ((:) (encodeExpression body) [])));
  -- Query keys are finite parser-owned syntax. Retain field lengths in a tree
  -- and flatten once, instead of copying every enclosing expression at each
  -- node. The ordinary encoders above remain independent format oracles.
  data SourceKey = KeyText String | KeyFields ([] SourceKey)
    | KeyScope ([] ((,) EvidenceRole String));
  data FramedKey = FramedText String | FramedFields Int ([] FramedKey);
  keyNode :: String -> [] SourceKey -> SourceKey;
  keyNode tag fields = KeyFields ((:) (KeyText tag) fields);
  keyList :: forall a. (a -> SourceKey) -> [] a -> SourceKey;
  keyList encode values = KeyFields (map encode values);
  inlineScopeKey :: [] ((,) EvidenceRole String) -> SourceKey;
  inlineScopeKey candidates = keyList (\candidate -> KeyText (encodeCandidate candidate)) candidates;
  expressionKey :: ([] ((,) EvidenceRole String) -> SourceKey) -> SExpr -> SourceKey;
  expressionKey scope expression = let { child = expressionKey scope } in case expression of {
    SVar n -> keyNode "variable" [KeyText n];
    SConstructor n -> keyNode "constructor" [KeyText n];
    SLam n annotation body -> keyNode "lambda"
      [KeyText n, KeyText (optional encodeAnnotation annotation), child body];
    SApp a b -> keyNode "apply" [child a, child b];
    SLet n a b -> keyNode "let" [KeyText n, child a, child b];
    SAnn a annotation -> keyNode "annotate" [child a, KeyText (encodeAnnotation annotation)];
    SSignature a annotation -> keyNode "signature" [child a, KeyText (encodeAnnotation annotation)];
    SIntLit n -> keyNode "integer" [KeyText (showInt n)];
    SDoubleLit n -> keyNode "double-bits" [KeyText (showInt (doubleToBits n))];
    SBoolLit b -> keyNode "boolean" [KeyText (boolean b)];
    SStringLit s -> keyNode "string" [KeyText s];
    SPrimitive p -> keyNode "primitive" [KeyText (Primitive.primitiveName p)];
    SCase a branches -> keyNode "case" [child a, keyList (alternativeKey scope) branches];
    SSourceDefinition body -> keyNode "source-definition" [child body];
    SCallSite label span body -> keyNode "call-site" [KeyText label, KeyText (encodeSourceSpan span), child body];
    SSharedBind pattern action continuation bindMethod failure -> keyNode "shared-bind"
      [KeyText (encodePattern pattern), child action, child continuation, child bindMethod, child failure];
    SDo statements body -> keyNode "do" [keyList (statementKey scope) statements, child body];
    SEquations rows -> keyNode "equations" [keyList (equationKey scope) rows];
    SLetRec definitions body -> keyNode "letrec" [keyList (recursiveKey scope) definitions, child body];
    SWanted dictionary candidates -> keyNode "wanted" [KeyText dictionary, scope candidates];
    SChecked ty body -> keyNode "checked" [KeyText (encodeType ty), child body]
  };
  alternativeKey :: ([] ((,) EvidenceRole String) -> SourceKey) -> SAlternative -> SourceKey;
  alternativeKey scope (SAlternative pattern body) =
    keyNode "alternative" [KeyText (encodePattern pattern), expressionKey scope body];
  equationKey :: ([] ((,) EvidenceRole String) -> SourceKey) -> (,) ([] SPattern) SExpr -> SourceKey;
  equationKey scope ((,) patterns body) =
    keyNode "equation" [KeyText (list encodePattern patterns), expressionKey scope body];
  recursiveKey :: ([] ((,) EvidenceRole String) -> SourceKey) ->
    (,,) String RecursiveMode SExpr -> SourceKey;
  recursiveKey scope ((,,) name mode body) = case mode of {
    InferRecursive -> keyNode "recursive-infer" [KeyText name, expressionKey scope body];
    CheckRecursive annotation -> keyNode "recursive"
      [KeyText name, KeyText (encodeAnnotation annotation), expressionKey scope body]
  };
  statementKey :: ([] ((,) EvidenceRole String) -> SourceKey) -> SStatement -> SourceKey;
  statementKey scope statement = case statement of {
    SDoBind pattern body -> keyNode "do-bind" [KeyText (encodePattern pattern), expressionKey scope body];
    SDoThen body -> keyNode "do-then" [expressionKey scope body];
    SDoLet name annotation body -> keyNode "do-let"
      [KeyText name, KeyText (optional encodeAnnotation annotation), expressionKey scope body];
    SDoLetRec definitions -> keyNode "do-letrec" [keyList (recursiveKey scope) definitions]
  };
  memberKey :: ([] ((,) EvidenceRole String) -> SourceKey) ->
    (,,) String (Maybe SAnnotation) SExpr -> SourceKey;
  memberKey scope ((,,) name annotation body) = keyNode "member"
    [KeyText name, KeyText (optional encodeAnnotation annotation), expressionKey scope body];
  compareCandidateScopes :: [] ((,) EvidenceRole String) -> [] ((,) EvidenceRole String) -> Int;
  compareCandidateScopes left right = case left of {
    [] -> if null right then 0 else 0 - 1;
    (:) ((,) role name) rest -> case right of {
      [] -> 1;
      (:) ((,) otherRole otherName) following -> let {
        roleOrder = compareString (encodeRole role) (encodeRole otherRole);
        nameOrder = compareString name otherName
      } in if roleOrder /= 0 then roleOrder else if nameOrder /= 0 then nameOrder
        else compareCandidateScopes rest following
    }
  };
  keyScopes :: SourceKey -> Set ([] ((,) EvidenceRole String)) -> Set ([] ((,) EvidenceRole String));
  keyScopes key known = case key of {
    KeyText _ -> known;
    KeyScope candidates -> S.insert compareCandidateScopes candidates known;
    KeyFields fields -> foldlStrict (\found field -> keyScopes field found) known fields
  };
  framedLength :: FramedKey -> Int;
  framedLength key = case key of {
    FramedText text -> stringLength text;
    FramedFields size _ -> size
  };
  frameKey :: Map ([] ((,) EvidenceRole String)) Int -> SourceKey -> FramedKey;
  frameKey scopes key = case key of {
    KeyText text -> FramedText text;
    KeyScope candidates -> case M.lookup compareCandidateScopes candidates scopes of {
      Nothing -> panic "query key scope missing from its own inventory";
      Just index -> FramedText (showInt index)
    };
    KeyFields children -> let { fields = map (frameKey scopes) children } in let {
      size = foldlStrict (\total field -> let { count = framedLength field }
        in total + stringLength (showInt count) + 1 + count) 0 fields
    } in seq size (FramedFields size fields)
  };
  framedChunks :: FramedKey -> [] String -> [] String;
  framedChunks key rest = case key of {
    FramedText text -> (:) text rest;
    FramedFields _ fields -> foldr (\field tail ->
      (:) (showInt (framedLength field) ++ ":") (framedChunks field tail)) rest fields
  };
  renderKey :: Map ([] ((,) EvidenceRole String)) Int -> SourceKey -> String;
  renderKey scopes key = concatStringList (framedChunks (frameKey scopes key) []);
  -- Pool exact ordered (role, canonical binding) lists, not just class names
  -- or hashes. The table is itself part of the authenticated query key. No
  -- candidate is removed, reordered, or selected here, and no inference or
  -- checked-object admission path consumes these references as authority.
  pooledSourceKey :: [] SourceKey -> String;
  pooledSourceKey fields = let {
    candidates = S.toList (keyScopes (KeyFields fields) S.empty);
    scopes = M.fromList compareCandidateScopes (zip candidates (range 0 (length candidates - 1)));
    table = keyList inlineScopeKey candidates
  } in renderKey scopes (KeyFields (snoc fields table));
  encodeField :: Field -> String;
  encodeField field =
    case field of {
      Parameter n -> node "parameter" ((:) n []);
      Function a b -> node "function-field" ((:) (encodeField a) ((:) (encodeField b) []));
      Applied n args -> node "applied-field" ((:) n ((:) (list encodeField args) []));
      Application a b -> node "application-field" ((:) (encodeField a) ((:) (encodeField b) []));
      Quantified n k body ->
        node "quantified-field" ((:) n ((:) (encodeKind k) ((:) (encodeField body) [])))
    };
  encodeConstructor (ConstructorDecl n fields) =
    node "constructor" ((:) n ((:) (list encodeField fields) []));
  canonicalField :: Map String String -> Int -> Field -> Field;
  canonicalField env depth field =
    case field of {
      Parameter n -> Parameter (canonicalReference env n);
      Function a b -> Function (canonicalField env depth a) (canonicalField env depth b);
      Applied n args -> Applied n (map (canonicalField env depth) args);
      Application a b ->
        let {
          f = canonicalField env depth a
        } in
        let {
          argument = canonicalField env depth b
        } in
        case f of {
          Applied n args -> Applied n (snoc args argument);
          _ -> Application f argument
        };
      Quantified n kind body ->
        Quantified ("type:" ++ showInt depth) kind
          (canonicalField (M.insert compareString n ("type:" ++ showInt depth) env) (depth + 1)
             body)
    };
  encodeDatatype declaration =
    let {
      parameters = D.datatypeBinders declaration
    } in
    let {
      scope = canonicalScope "type:" M.empty 0 (map fst parameters)
    } in
    let {
      constructors =
        map
          (\(ConstructorDecl n fields) ->
             ConstructorDecl n (map (canonicalField scope (length parameters)) fields))
          (D.datatypeConstructors declaration)
    } in
    node "data"
      ((:) (D.datatypeName declaration)
         ((:)
            (list
               (\((,) n k) ->
                  node "parameter" ((:) (canonicalReference scope n) ((:) (encodeKind k) [])))
               parameters)
            ((:) (list encodeConstructor constructors) [])));
  -- Wire dictionary for the short v7 tag. Its meaning is fixed independently
  -- of the running compiler's declarations. Do not use D's builtin builders
  -- here: changing a builder must not also change the meaning of stored keys.
  v7BuiltinDictionary :: [] DataDecl;
  v7BuiltinDictionary = let {
    product = \name parameters fields -> DataDecl name parameters [ConstructorDecl name fields];
    tuple = \arity -> let {
      name = "(" ++ concatStringList (replicate (arity - 1) ",") ++ ")";
      parameters = map (\i -> "a" ++ showInt i) (range 1 arity)
    } in product name parameters (map Parameter parameters);
    listData = DataDecl "[]" ["a"] [ConstructorDecl "[]" [],
      ConstructorDecl ":" [Parameter "a", Applied "[]" [Parameter "a"]]];
    frame = product "MLFStackFrame" []
      (append (replicate 4 (Applied "String" [])) (replicate 4 (Applied "Int" [])));
    evidence = product "MLFStackEvidence" [] [Applied "MLFCallStack" []]
  } in append [product "MLFLegacyUnit" [] [], product "()" [] [], listData]
    (append (map tuple (range 2 4)) (append [frame, evidence] (map tuple (range 5 64))));
  -- The escape preserves even binder spellings, the declaration variant and
  -- constructor order. It has disjoint framing from the fixed dictionary tag.
  literalBuiltin :: DataDecl -> String;
  literalBuiltin declaration = case declaration of {
    DataDecl name parameters constructors ->
      node "data" [name, Separate.pack parameters, list encodeConstructor constructors];
    DataDeclK name parameters constructors -> node "kinded-data"
      [name, list (\((,) n k) -> Separate.pack [n, encodeKind k]) parameters,
       list encodeConstructor constructors]
  };
  sourceFormatFor :: [] DataDecl -> String;
  sourceFormatFor builtins = let { tag = "MLF-SOURCE-CRATE-QUERY-7" } in
    if eqList SourceEquality.eqDataDecl builtins v7BuiltinDictionary then tag
    else node tag [list literalBuiltin builtins];
  sourceQueryFormat :: String;
  sourceQueryFormat = sourceFormatFor D.builtinDeclarations;
  -- In v7 only user declarations are projected into the shared carrier. The
  -- builtin identity stays in the record's format field beside compilerHash.
  encodeSourceDatatypes :: [] DataDecl -> String;
  encodeSourceDatatypes = list encodeDatatype;
  data QueryDatatypeEncoding = QueryDatatypeEncoding DataDecl String;
  data SourceEncodings = SourceEncodings Separate.DatatypeEncodings
    (Map String ([] QueryDatatypeEncoding));
  prepareSourceEncodings :: [] DataDecl -> SourceEncodings;
  prepareSourceEncodings declarations =
    SourceEncodings (Separate.prepareDatatypeEncodings declarations)
      (M.fromListWith compareString append
        (map (\d -> (,) (D.datatypeName d) ((:) (QueryDatatypeEncoding d (encodeDatatype d)) []))
          declarations));
  findQueryDatatypeEncoding :: DataDecl -> [] QueryDatatypeEncoding -> String;
  findQueryDatatypeEncoding declaration entries = case entries of {
    [] -> encodeDatatype declaration;
    (:) (QueryDatatypeEncoding original text) rest ->
      if SourceEquality.eqDataDecl declaration original then text
      else findQueryDatatypeEncoding declaration rest
  };
  encodeSourceDatatypesWithPool :: SourceEncodings -> [] DataDecl -> String;
  encodeSourceDatatypesWithPool (SourceEncodings _ entries) declarations =
    list (\d -> findQueryDatatypeEncoding d
      (M.findWithDefault compareString [] (D.datatypeName d) entries))
      declarations;
  -- Preserve the complete legacy encoder for callers outside the v7 source path.
  encodeDatatypeContextWithPool :: SourceEncodings -> [] DataDecl -> String;
  encodeDatatypeContextWithPool pool declarations =
    encodeSourceDatatypesWithPool pool (append D.builtinDeclarations declarations);
  -- File-owned, finite declarations only. Keep one complete context; a miss
  -- uses the original encoder, including its duplicate-name/layout fallback.
  data DatatypeContextEncoding = DatatypeContextEncoding ([] DataDecl) String;
  emptyDatatypeContextEncoding :: SourceEncodings -> DatatypeContextEncoding;
  emptyDatatypeContextEncoding pool = DatatypeContextEncoding []
    (encodeSourceDatatypesWithPool pool []);
  reuseDatatypeContext :: SourceEncodings -> DatatypeContextEncoding -> [] DataDecl ->
    (,) String DatatypeContextEncoding;
  reuseDatatypeContext pool (DatatypeContextEncoding original encoded) declarations =
    let { text = if eqList SourceEquality.eqDataDecl original declarations then encoded
          else encodeSourceDatatypesWithPool pool declarations }
    in (,) text (DatatypeContextEncoding declarations text);
  encodeXType :: XType -> String;
  encodeXType ty =
    case ty of {
      XVar (XTyVar n) -> node "variable" ((:) (showInt n) []);
      XBot -> node "bottom" [];
      XBotKind k -> node "bottom-kind" ((:) (encodeKind k) []);
      XArrow a b -> node "arrow" ((:) (encodeXType a) ((:) (encodeXType b) []));
      XCon n args -> node "constructor" ((:) n ((:) (list encodeXType args) []));
      XApply a b -> node "application" ((:) (encodeXType a) ((:) (encodeXType b) []));
      XForall (XTyVar n) bound body ->
        node "forall" ((:) (showInt n) ((:) (encodeXType bound) ((:) (encodeXType body) [])))
    };
  normalizeXType :: XType -> XType;
  normalizeXType ty =
    case ty of {
      XBotKind Star -> XBot;
      XArrow a b -> XArrow (normalizeXType a) (normalizeXType b);
      XCon n args -> XCon n (map normalizeXType args);
      XApply f a -> T.apply (normalizeXType f) (normalizeXType a);
      XForall n bound body -> XForall n (normalizeXType bound) (normalizeXType body);
      _ -> ty
    };
  encodeBinding ((,) n ty) =
    node "binding" ((:) n ((:) (encodeXType (Separate.normalType (normalizeXType ty))) []));
  -- Local names are alpha-normalized independently for each declaration. Free
  -- symbols use a disjoint tagged namespace, so a user's spelling can never
  -- collide with a canonical local binder. Evidence candidates share that
  -- lexical environment, including given dictionaries introduced by lowering.
  canonicalReference env name =
    if Separate.managedIntrinsicName name then name
    else M.findWithDefault compareString ("global:" ++ name) name env;
  canonicalScope prefix env depth names =
    foldlStrict
      (\scope entry ->
         case entry of {
           (,) position name -> M.insert compareString name (prefix ++ showInt position) scope
         })
      env
      (zip (range depth ((depth + length names) - 1)) names);
  canonicalTypeIn :: Map String String -> Int -> SType -> SType;
  canonicalTypeIn env depth ty =
    case ty of {
      STVar n -> STVar (canonicalReference env n);
      SArrow a b -> SArrow (canonicalTypeIn env depth a) (canonicalTypeIn env depth b);
      SCon n args -> SCon n (map (canonicalTypeIn env depth) args);
      STypeApp a b -> STypeApp (canonicalTypeIn env depth a) (canonicalTypeIn env depth b);
      SForall flag n bound body ->
        SForall flag ("type:" ++ showInt depth) (canonicalTypeIn env depth bound)
          (canonicalTypeIn (M.insert compareString n ("type:" ++ showInt depth) env) (depth + 1)
             body);
      SQualified predicates body ->
        SQualified (map (canonicalPredicate env depth) predicates) (canonicalTypeIn env depth body);
      _ -> ty
    };
  canonicalPredicate :: Map String String -> Int -> SPredicate -> SPredicate;
  canonicalPredicate env depth (SPredicate n args) =
    SPredicate n (map (canonicalTypeIn env depth) args);
  canonicalAnnotation env depth (SAnnotation names ty) =
    let {
      scope = canonicalScope "type:" env depth names
    } in
    SAnnotation (map (canonicalReference scope) names)
      (canonicalTypeIn scope (depth + length names) ty);
  leadingTypes :: SType -> [] String;
  leadingTypes ty =
    case ty of {
      SForall Flexible n SBottom body -> (:) n (leadingTypes body);
      SForall Flexible n (SBottomKind _) body -> (:) n (leadingTypes body);
      _ -> []
    };
  canonicalPattern :: Map String String -> Map String String -> Int -> SPattern -> SPattern;
  canonicalPattern env types typeDepth pattern =
    case pattern of {
      SConstructorPattern n names ->
        SConstructorPattern n (map (Separate.mapMaybeValue (canonicalReference env)) names);
      SDefaultPattern name ->
        SDefaultPattern (Separate.mapMaybeValue (canonicalReference env) name);
      SNestedPattern n patterns ->
        SNestedPattern n (map (canonicalPattern env types typeDepth) patterns);
      SAnnotatedPattern n annotation ->
        SAnnotatedPattern (canonicalReference env n)
          (canonicalAnnotation types typeDepth annotation);
      SOverloadedStringPattern s equal fromString ->
        SOverloadedStringPattern s (canonicalReference env equal) (canonicalReference env fromString);
      SAsPattern n pattern ->
        SAsPattern (canonicalReference env n) (canonicalPattern env types typeDepth pattern);
      SLazyPattern pattern -> SLazyPattern (canonicalPattern env types typeDepth pattern);
      _ -> pattern
    };
  canonicalExpression :: Map String String -> Int -> Map String String -> Int -> SExpr -> SExpr;
  canonicalExpression env depth types typeDepth expression =
    let {
      child = canonicalExpression env depth types typeDepth
    } in
    case expression of {
      SVar n -> SVar (canonicalReference env n);
      SLam n annotation body ->
        SLam ("local:" ++ showInt depth)
          (Separate.mapMaybeValue (canonicalAnnotation types typeDepth) annotation)
          (canonicalExpression (M.insert compareString n ("local:" ++ showInt depth) env)
             (depth + 1)
             types
             typeDepth
             body);
      SApp a b -> SApp (child a) (child b);
      SLet n a b ->
        SLet ("local:" ++ showInt depth) (child a)
          (canonicalExpression (M.insert compareString n ("local:" ++ showInt depth) env)
             (depth + 1)
             types
             typeDepth
             b);
      SAnn a annotation -> SAnn (child a) (canonicalAnnotation types typeDepth annotation);
      SSignature a annotation ->
        let {
          names = case annotation of {
            SAnnotation [] ty -> leadingTypes ty;
            _ -> []
          }
        } in
        SSignature
          (canonicalExpression env depth (canonicalScope "type:" types typeDepth names)
             (typeDepth + length names) a)
          (canonicalAnnotation types typeDepth annotation);
      SCase a branches ->
        SCase (child a)
          (map
             (\(SAlternative pattern body) ->
                let {
                  names = Desugar.patternVariables pattern
                } in
                let {
                  scope = canonicalScope "local:" env depth names
                } in
                SAlternative (canonicalPattern scope types typeDepth pattern)
                  (canonicalExpression scope (depth + length names) types typeDepth body))
             branches);
      SEquations rows ->
        SEquations
          (map
             (\((,) patterns body) ->
                let {
                  names = concatMap Desugar.patternVariables patterns
                } in
                let {
                  scope = canonicalScope "local:" env depth names
                } in
                (,) (map (canonicalPattern scope types typeDepth) patterns)
                  (canonicalExpression scope (depth + length names) types typeDepth body))
             rows);
      SSourceDefinition body -> SSourceDefinition (child body);
      SCallSite label span body -> SCallSite label span (child body);
      SSharedBind pattern action continuation bindMethod failure ->
        let { names = Desugar.patternVariables pattern } in
        let { scope = canonicalScope "local:" env depth names } in
        SSharedBind (canonicalPattern scope types typeDepth pattern) (child action)
          (canonicalExpression scope (depth + length names) types typeDepth continuation)
          (child bindMethod) (child failure);
      SDo _ _ -> child (Desugar.desugarDo expression);
      SLetRec definitions body ->
        let {
          names = map (\((,,) n _ _) -> n) definitions
        } in
        let {
          scope = canonicalScope "local:" env depth names
        } in
        let {
          nextDepth = (depth + length names)
        } in
        SLetRec (map (canonicalRecursive scope nextDepth types typeDepth) definitions)
          (canonicalExpression scope nextDepth types typeDepth body);
      SWanted dictionary candidates ->
        SWanted dictionary
          (map (\((,) role n) -> (,) role (canonicalReference env n)) candidates);
      SChecked ty body ->
        let {
          names = leadingTypes ty
        } in
        SChecked (canonicalTypeIn types typeDepth ty)
          (canonicalExpression env depth (canonicalScope "type:" types typeDepth names)
             (typeDepth + length names)
             body);
      _ -> expression
    };
  canonicalRecursive :: Map String String ->
                        Int ->
                        Map String String ->
                        Int -> (,,) String RecursiveMode SExpr -> (,,) String RecursiveMode SExpr;
  canonicalRecursive env depth types typeDepth ((,,) n mode body) =
    case mode of {
      InferRecursive ->
        (,,) (canonicalReference env n) InferRecursive
          (canonicalExpression env depth types typeDepth body);
      CheckRecursive annotation ->
        let {
          names =
            case annotation of {
              SAnnotation [] ty -> leadingTypes ty;
              _ -> []
            }
        } in
        (,,) (canonicalReference env n)
          (CheckRecursive (canonicalAnnotation types typeDepth annotation))
          (canonicalExpression env depth (canonicalScope "type:" types typeDepth names)
             (typeDepth + length names)
             body)
    };
  canonicalMember ((,,) n annotation body) =
    let {
      names = case annotation of {
        Just (SAnnotation [] ty) -> leadingTypes ty;
        _ -> []
      }
    } in
    (,,) n (Separate.mapMaybeValue (canonicalAnnotation M.empty 0) annotation)
      (canonicalExpression M.empty 0 (canonicalScope "type:" M.empty 0 names) (length names) body);
  data TypeInventory =
    TypeInventory (Map String DataDecl) (Map String String) (Map String ([] String));
  prepareData datatypes =
    do {
      D.validateDeclarations datatypes;
      Right
        (TypeInventory (M.fromList compareString (map (\d -> (,) (D.datatypeName d) d) datatypes))
           (M.fromList compareString
              (concatMap
                 (\d ->
                    map (\c -> (,) (D.constructorName c) (D.datatypeName d))
                      (D.datatypeConstructors d))
                 datatypes))
           (M.fromList compareString
              (map
                 (\d ->
                    (,) (D.datatypeName d) (Dependency.typeNames (Dependency.observeDatatype d)))
                 datatypes)))
    };
  xTypeNames :: XType -> [] String;
  xTypeNames ty =
    case ty of {
      XArrow a b -> append (xTypeNames a) (xTypeNames b);
      XCon n args -> (:) n (concatMap xTypeNames args);
      XApply a b -> append (xTypeNames a) (xTypeNames b);
      XForall _ a b -> append (xTypeNames a) (xTypeNames b);
      _ -> []
    };
  requiredDataIn (TypeInventory datatypes constructors edges) members schemes =
    let {
      observations = map Dependency.observeDeclaration members
    } in
    let {
      direct = concatMap Dependency.typeNames observations
    } in
    let {
      owners =
        catMaybes
          (map (\n -> M.lookup compareString n constructors)
             (concatMap Dependency.constructorNames observations))
    } in
    let {
      roots = append direct (append owners (concatMap (\((,) _ ty) -> xTypeNames ty) schemes))
    } in
    let {
      needed = Inference.closeDependencies edges S.empty roots
    } in
    map snd (filter (\entry -> S.member compareString (fst entry) needed) (M.toList datatypes));
  requiredData :: [] DataDecl ->
                  [] ((,,) String (Maybe SAnnotation) SExpr) ->
                  [] ((,) String XType) -> Either String ([] DataDecl);
  requiredData datatypes members schemes =
    do {
      inventory <- prepareData datatypes;
      Right (requiredDataIn inventory members schemes)
    };
  data GroupResult = GroupResult String ([] String) Bool String String;
  data QueryReport = QueryReport Int Int ([] GroupResult);
  inferredCount (QueryReport n _ _) = n;
  reusedCount (QueryReport _ n _) = n;
  inferenceUnits (QueryReport _ _ groups) = map (\(GroupResult _ names _ _ _) -> names) groups;
  queryKeys (QueryReport _ _ groups) = map (\(GroupResult _ _ _ _ key) -> key) groups;
  jsonCharacter code =
    if (code == 34)
    then "\\\""
    else if (code == 92)
         then "\\\\"
         else if (code < 32)
              then ("\\u00" ++
                    (stringSlice "0123456789abcdef" (quotInt code 16) 1 ++
                     stringSlice "0123456789abcdef" (remInt code 16) 1))
              else stringFromCode code;
  jsonFrom :: String -> Int -> String;
  jsonFrom value position =
    if (position >= stringLength value)
    then ""
    else (jsonCharacter (stringCodeAt value position) ++ jsonFrom value (position + 1));
  jsonString value = ("\"" ++ (jsonFrom value 0 ++ "\""));
  jsonArray values = ("[" ++ (intercalate "," values ++ "]"));
  groupJSON (GroupResult identity names cached semantic key) =
    ("{\"id\":" ++
     (jsonString identity ++
      (",\"members\":" ++
       (jsonArray (map jsonString names) ++
        (",\"cached\":" ++
         (boolean cached ++
          (",\"semantic_fingerprint\":" ++
           (jsonString semantic ++ (",\"query_key\":" ++ (jsonString key ++ "}"))))))))));
  reportJSON crateId semantic (QueryReport inferred reused groups) =
    ("{\"format\":1,\"crate\":" ++
     (jsonString crateId ++
      (",\"semantic_fingerprint\":" ++
       (jsonString semantic ++
        (",\"inferred_groups\":" ++
         (showInt inferred ++
          (",\"reused_groups\":" ++
           (showInt reused ++
            (",\"groups\":" ++ (jsonArray (map groupJSON groups) ++ "}\n"))))))))));
  data QueryState =
    QueryState (Map String XType) ([] Separate.UnitObject) Int Int ([] GroupResult);
  -- SCCs are disjoint and their members sorted. Their minimum stable identity
  -- is unique within a crate; the full member inventory remains in the key.
  groupName crateId names =
    ("Query_" ++ (Separate.encoded crateId ++ ("z_" ++ Separate.encoded (head names))));
  selectedBindings members available =
    let {
      used =
        S.fromList compareString
          (concatMap (\member -> Dependency.valueNames (Dependency.observeDeclaration member))
             members)
    } in
    M.toList (M.filterWithKey (\n _ -> S.member compareString n used) available);
  -- Builtin families are reconstructed rather than written as user declarations.
  -- Include them explicitly: constructor count and nested fields affect whether
  -- a patterned do bind requires MonadFail, even with identical user layouts.
  encodeDatatypeContext datatypes = list encodeDatatype (append D.builtinDeclarations datatypes);
  queryKey crateId compilerHash members bindings datatypes =
    node "MLF-CRATE-QUERY-4"
      ((:) crateId
         ((:) compilerHash
            ((:) (list (\member -> encodeMember (canonicalMember member)) members)
               ((:) (list encodeBinding bindings) ((:) (encodeDatatypeContext datatypes) [])))));
  dependencyInterface bindings =
    Separate.UnitInterface "QueryInputs" [] [] [] [] [] bindings "parameters";
  peelParameters :: XTerm -> (,) ([] ((,) XName XType)) XTerm;
  peelParameters term =
    case term of {
      XAbs n ty body ->
        case peelParameters body of {
          (,) parameters implementation -> (,) ((:) ((,) n ty) parameters) implementation
        };
      _ -> (,) [] term
    };
  validateCached :: String ->
                    [] ((,) String XType) ->
                    [] DataDecl ->
                    [] String -> Separate.UnitObject -> Either String Separate.UnitObject;
  -- Normalize only alpha-equivalent binders and equivalent application
  -- representations, including parser normalization of Field constructors.
  -- The target wire syntax omits an empty data wrapper. Reintroduce it at
  -- the fragment boundary after checking the empty context against metadata.
  -- A contextual cache already checks this exact datatype spelling. Reuse its
  -- opaque proof only when the complete datatype AST agrees exactly. Legacy
  -- alpha-renamed contexts are rebuilt and independently checked as before.
  validateCached expectedName expectedParameters expectedData expectedMembers object =
    do {
      let {
        iface = Separate.objectInterface object
      };
      ensure (eqString (Separate.unitName iface) expectedName) "cached group identity mismatch";
      ensure
        (null (Separate.unitDependencies iface) &&
         (null (Separate.unitExports iface) &&
          (null (Separate.unitClasses iface) && null (Separate.unitInstances iface))))
        "cached fragment contains module metadata";
      let {
        dataKey = list encodeDatatype expectedData
      };
      ensure (eqString (list encodeDatatype (Separate.unitData iface)) dataKey)
        "cached datatype metadata mismatch";
      let {
        contextAndBody =
          case Separate.objectTerm object of {
            XWithData ds body -> (,) ds body;
            body -> (,) [] body
          }
      };
      let {
        datatypes = fst contextAndBody
      };
      let {
        inner = snd contextAndBody
      };
      ensure (eqString (list encodeDatatype datatypes) dataKey) "cached datatype context mismatch";
      let {
        parameters = fst (peelParameters inner)
      };
      let {
        implementation = snd (peelParameters inner)
      };
      ensure
        (eqList Separate.sameSignature (map (\((,) n ty) -> (,) (X.nameHint n) ty) parameters)
           expectedParameters)
        "cached dependency parameter mismatch";
      ds <- D.validateDeclarations datatypes;
      bindings <-
        Separate.collectBindings ds (XEnv M.empty (M.fromList X.compareName parameters))
          implementation;
      let {
        actual =
          Separate.sortBindings
            (map (\((,) n ty) -> (,) (X.nameHint n) (Separate.normalType ty)) bindings)
      };
      ensure (eqList eqString (map fst actual) expectedMembers)
        "cached declaration ownership mismatch";
      ensure (eqList Separate.sameSignature actual (Separate.unitBindings iface))
        "cached declaration scheme mismatch";
      let {
        payload = XWithData expectedData inner
      };
      checked <-
        case Separate.objectTerm object of {
          XWithData _ _ ->
            if eqList SourceEquality.eqDataDecl datatypes expectedData
            then Separate.objectChecked object
            else Checked.check payload;
          _ -> Checked.check payload
        };
      let {
        current =
          Separate.UnitInterface expectedName [] [] expectedData [] []
            (Separate.unitBindings iface)
            (Separate.fingerprint (Pretty.prettyTerm payload))
      };
      Right (Separate.CheckedUnitObject current checked)
    };
  decodeCached :: String ->
                  String ->
                  [] ((,) String XType) ->
                  [] DataDecl -> [] String -> String -> Either String Separate.UnitObject;
  decodeCached key name bindings datatypes names input =
    do {
      fields <- Separate.unpack input;
      let {
        matchValueShared1 = fields
      } in
      case matchValueShared1 of {
        (:) matchValueShared2 matchValueShared3 ->
          if MLF.Primitive.eqString matchValueShared2 "MLF-QUERY-CACHE-2"
          then case matchValueShared3 of {
                 (:) matchValueShared10 matchValueShared11 ->
                   case matchValueShared11 of {
                     (:) matchValueShared12 matchValueShared13 ->
                       case matchValueShared13 of {
                         [] ->
                           let {
                             savedKey = matchValueShared10
                           } in
                           let {
                             payload = matchValueShared12
                           } in
                           do {
                             ensure (eqString key savedKey) "cached query key mismatch";
                             object <- Separate.decodeContextualObject datatypes datatypes payload;
                             validateCached name bindings datatypes names object
                           };
                         _ -> Left "unsupported query cache format"
                       };
                     _ -> Left "unsupported query cache format"
                   };
                 _ -> Left "unsupported query cache format"
               }
          else if MLF.Primitive.eqString matchValueShared2 "MLF-QUERY-CACHE-1"
               then case matchValueShared3 of {
                      (:) matchValueShared4 matchValueShared5 ->
                        case matchValueShared5 of {
                          (:) matchValueShared6 matchValueShared7 ->
                            case matchValueShared7 of {
                              (:) matchValueShared8 matchValueShared9 ->
                                case matchValueShared9 of {
                                  [] ->
                                    let {
                                      savedKey = matchValueShared4
                                    } in
                                    let {
                                      metadata = matchValueShared6
                                    } in
                                    let {
                                      payload = matchValueShared8
                                    } in
                                    do {
                                      ensure (eqString key savedKey) "cached query key mismatch";
                                      iface <- Separate.decodeInterface metadata;
                                      object <- Separate.decodeObject iface payload;
                                      validateCached name bindings datatypes names object
                                    };
                                  _ -> Left "unsupported query cache format"
                                };
                              _ -> Left "unsupported query cache format"
                            };
                          _ -> Left "unsupported query cache format"
                        };
                      _ -> Left "unsupported query cache format"
                    }
               else Left "unsupported query cache format";
        _ -> Left "unsupported query cache format"
      }
    };
  -- The complete key already carries the canonical required layouts. Check the
  -- producer's two contexts before omitting their repeated source headers. The
  -- reader supplies the recomputed layouts, including alpha-equivalent binder
  -- spellings, and still performs every closed/ownership/parameter check.
  contextualCache :: String -> Separate.UnitObject -> Bool;
  contextualCache key object =
    let {
      matchValueShared14 = Separate.unpack key
    } in
    case matchValueShared14 of {
      Right matchValueShared15 ->
        case matchValueShared15 of {
          (:) matchValueShared16 matchValueShared17 ->
            if MLF.Primitive.eqString matchValueShared16 "MLF-CRATE-QUERY-4"
            then case matchValueShared17 of {
                   (:) matchValueShared18 matchValueShared19 ->
                     case matchValueShared19 of {
                       (:) matchValueShared20 matchValueShared21 ->
                         case matchValueShared21 of {
                           (:) matchValueShared22 matchValueShared23 ->
                             case matchValueShared23 of {
                               (:) matchValueShared24 matchValueShared25 ->
                                 case matchValueShared25 of {
                                   (:) matchValueShared26 matchValueShared27 ->
                                     case matchValueShared27 of {
                                       [] ->
                                         let {
                                           expected = matchValueShared26
                                         } in
                                         (eqString expected
                                            (encodeDatatypeContext
                                               (Separate.unitData
                                                  (Separate.objectInterface object))) &&
                                          eqString expected
                                            (encodeDatatypeContext (Separate.objectContext object)));
                                       _ -> False
                                     };
                                   _ -> False
                                 };
                               _ -> False
                             };
                           _ -> False
                         };
                       _ -> False
                     };
                   _ -> False
                 }
            else False;
          _ -> False
        };
      _ -> False
    };
  encodeCached key object =
    if contextualCache key object
    then Separate.pack
           ((:) "MLF-QUERY-CACHE-2" ((:) key ((:) (Separate.encodeContextualObject object) [])))
    else Separate.pack
           ((:) "MLF-QUERY-CACHE-1"
              ((:) key
                 ((:) (Separate.encodeInterface (Separate.objectInterface object))
                    ((:) (Separate.encodeObject object) []))));
  encodeCachedWithDatatypes :: Separate.DatatypeEncodings -> String -> Separate.UnitObject -> String;
  encodeCachedWithDatatypes pool key object =
    if contextualCache key object
    then Separate.pack
      ((:) "MLF-QUERY-CACHE-2" ((:) key ((:) (Separate.encodeContextualObject object) [])))
    else let { encoded = Separate.encodeUnitWithDatatypes pool object } in
      Separate.pack ((:) "MLF-QUERY-CACHE-1"
        ((:) key ((:) (fst encoded) ((:) (snd encoded) []))));
  -- Source cache format3 shares the exact finite datatype-key context on disk.
  -- It is deliberately separate from format2's legacy QUERY-4 contract. The
  -- complete source-query-v7 key is reconstructed before any object admission.
  sourceCacheParts :: String -> Maybe ((,) String String);
  sourceCacheParts key = case Separate.unpack key of {
    Right fields -> case fields of {
      (:) format ((:) crateId ((:) compilerHash ((:) members ((:) bindings
        ((:) context ((:) prepared ((:) contracts ((:) scopes [])))))))) ->
        if eqString format sourceQueryFormat
          && eqString key (Separate.pack fields)
        then Just ((,) (Separate.pack
          [format, crateId, compilerHash, members, bindings, prepared, contracts, scopes]) context)
        else Nothing;
      _ -> Nothing
    };
    Left _ -> Nothing
  };
  restoreSourceCacheKey :: String -> String -> Either String String;
  restoreSourceCacheKey context compact = do {
    fields <- Separate.unpack compact;
    case fields of {
      (:) format ((:) crateId ((:) compilerHash ((:) members ((:) bindings
        ((:) prepared ((:) contracts ((:) scopes []))))))) -> do {
        ensure (eqString format sourceQueryFormat
          && eqString compact (Separate.pack fields)) "unsupported source query key";
        Right (Separate.pack
          [format, crateId, compilerHash, members, bindings, context, prepared, contracts, scopes])
      };
      _ -> Left "unsupported source query key"
    }
  };
  sourceContextDigestFrom :: String -> Int -> Bool;
  sourceContextDigestFrom digest i =
    if i >= 64 then True else let { code = stringCodeAt digest i } in
      ((code >= 48 && code <= 57) || (code >= 97 && code <= 102))
        && sourceContextDigestFrom digest (i + 1);
  validSourceContextDigest :: String -> Bool;
  validSourceContextDigest digest =
    stringLength digest == 64 && sourceContextDigestFrom digest 0;
  sourceContextPath :: String -> String -> String;
  sourceContextPath cacheDir digest = cacheDir ++ "/context-" ++ digest ++ ".mlfqc";
  sourceContextContents :: String -> String;
  sourceContextContents context =
    Separate.pack ["MLF-SOURCE-QUERY-CONTEXT-1", context];
  sourceCacheReference :: String -> Either String (Maybe String);
  sourceCacheReference input = do {
    fields <- Separate.unpack input;
    case fields of {
      (:) format rest ->
        if eqString format "MLF-QUERY-CACHE-3" then case rest of {
          (:) digest ((:) _ ((:) _ [])) -> do {
            ensure (validSourceContextDigest digest) "invalid source query context reference";
            Right (Just digest)
          };
          _ -> Left "unsupported source query cache format"
        } else Right Nothing;
      _ -> Left "unsupported query cache format"
    }
  };
  -- actualDigest is computed from the bounded-name file by readSourceCached;
  -- neither the reference nor its hash substitutes for full context/key checks.
  decodeSourceCached :: String -> String -> String ->
    [] ((,) String XType) -> [] DataDecl -> [] String -> String -> String ->
    Either String Separate.UnitObject;
  decodeSourceCached actualDigest key name bindings datatypes names contextInput input =
    decodeSourceCachedWithEncoding (encodeSourceDatatypes datatypes) actualDigest key name
      bindings datatypes names contextInput input;
  -- Only an encoding verified against structurally identical datatypes may be
  -- reused here. The public stateless decoder still computes the original encoding.
  decodeSourceCachedWithEncoding :: String -> String -> String -> String ->
    [] ((,) String XType) -> [] DataDecl -> [] String -> String -> String ->
    Either String Separate.UnitObject;
  decodeSourceCachedWithEncoding verifiedEncoding actualDigest key name bindings datatypes names contextInput input =
    decodeSourceCachedWithKeyParts verifiedEncoding actualDigest (sourceCacheParts key)
      name bindings datatypes names contextInput input;
  -- Trusted internal decomposition, not an unforgeable capability. Supported
  -- callers pass only sourceCacheParts of the complete expected key. Keep
  -- record/reference checks before inspecting the parts so error order agrees.
  decodeSourceCachedWithKeyParts :: String -> String -> Maybe ((,) String String) -> String ->
    [] ((,) String XType) -> [] DataDecl -> [] String -> String -> String ->
    Either String Separate.UnitObject;
  decodeSourceCachedWithKeyParts verifiedEncoding actualDigest expectedParts name bindings datatypes names contextInput input = do {
    fields <- Separate.unpack input;
    case fields of {
      (:) format ((:) digest ((:) compact ((:) payload []))) -> do {
        ensure (eqString format "MLF-QUERY-CACHE-3" && eqString input (Separate.pack fields)
          && validSourceContextDigest digest && eqString actualDigest digest)
          "invalid source query context reference";
        case expectedParts of {
          Nothing -> Left "unsupported source query key";
          Just ((,) expectedCompact expectedContext) -> do {
            ensure (eqString expectedContext verifiedEncoding)
              "cached source query datatype context mismatch";
            ensure (eqString contextInput (sourceContextContents expectedContext))
              "cached source query context mismatch";
            -- Both projections are canonical: equal compact fields plus the
            -- independently checked context imply equality of the full key.
            -- Preserve old malformed-key diagnostics on the rejected path.
            if eqString compact expectedCompact then Right () else do {
              _ <- restoreSourceCacheKey expectedContext compact;
              Left "cached query key mismatch"
            };
            object <- Separate.decodeContextualObject datatypes datatypes payload;
            validateCached name bindings datatypes names object
          }
        }
      };
      _ -> Left "unsupported source query cache format"
    }
  };
  readSourceCached :: String -> String -> String ->
    [] ((,) String XType) -> [] DataDecl -> [] String -> String ->
    IO (Either String Separate.UnitObject);
  readSourceCached cacheDir key name bindings datatypes names input = do {
    result <- readSourceCachedWithWindow [] cacheDir key name bindings datatypes names input;
    ioReturn (case result of { (,,) _ _ decoded -> decoded })
  };
  -- Only successful reads under the caller's directory lock enter this finite
  -- call-owned window. Entries are trusted derived values, not serialized
  -- credentials. MRU is first and at most eight entries survive a successful read.
  -- Cooperative writers use that same lock; hostile writes and same-process
  -- concurrent callers remain outside this existing lock's guarantees.
  data SourceContextRead = SourceContextRead String String ([] DataDecl) String String;
  -- Route lookup does not inspect datatype/encoding/blob values of other entries.
  findSourceContextRead :: String -> String -> [] SourceContextRead -> Maybe SourceContextRead;
  findSourceContextRead cacheDir digest entries =
    findSourceContextReadWithin 8 cacheDir digest entries;
  findSourceContextReadWithin :: Int -> String -> String -> [] SourceContextRead -> Maybe SourceContextRead;
  findSourceContextReadWithin remaining cacheDir digest entries =
    if remaining <= 0 then Nothing else case entries of {
    [] -> Nothing;
    (:) entry rest -> case entry of {
      SourceContextRead directory reference _ _ _ ->
        if eqString directory cacheDir && eqString reference digest
        then Just entry else findSourceContextReadWithin (remaining - 1) cacheDir digest rest
    }
  };
  retainSourceContextRead :: SourceContextRead -> String -> String ->
    [] SourceContextRead -> [] SourceContextRead;
  retainSourceContextRead entry cacheDir digest entries =
    take 8 ((:) entry (filter
      (\previous -> case previous of {
        SourceContextRead directory reference _ _ _ ->
          not (eqString directory cacheDir && eqString reference digest)
      }) (take 8 entries)));
  -- Keep the previous singleton API and its exact returned entry/error behavior.
  -- The Bool reports context-snapshot reuse, never record/raw-validation success.
  readSourceCachedWithContext :: Maybe SourceContextRead -> String -> String -> String ->
    [] ((,) String XType) -> [] DataDecl -> [] String -> String ->
    IO ((,,) (Maybe SourceContextRead) Bool (Either String Separate.UnitObject));
  readSourceCachedWithContext previous cacheDir key name bindings datatypes names input = do {
    observed <- readSourceCachedWithWindow (case previous of {
      Nothing -> [];
      Just entry -> [entry]
    }) cacheDir key name bindings datatypes names input;
    ioReturn (case observed of {
      (,,) next reused result -> (,,) (case next of {
        [] -> Nothing;
        (:) entry _ -> Just entry
      }) reused result
    })
  };
  readSourceCachedWithWindow :: [] SourceContextRead -> String -> String -> String ->
    [] ((,) String XType) -> [] DataDecl -> [] String -> String ->
    IO ((,,) ([] SourceContextRead) Bool (Either String Separate.UnitObject));
  readSourceCachedWithWindow previous cacheDir key name bindings datatypes names input =
    let { bounded = take 8 previous } in
    case sourceCacheReference input of {
      Left error -> ioReturn ((,,) [] False (Left error));
      Right Nothing -> ioReturn ((,,) [] False
        (decodeCached key name bindings datatypes names input));
      Right (Just digest) -> case sourceCacheParts key of {
        Nothing -> ioReturn ((,,) [] False (Left "unsupported source query key"));
        Just ((,) expectedCompact expectedContext) ->
          let { selection = case findSourceContextRead cacheDir digest bounded of {
            Nothing -> (,) Nothing bounded;
            Just entry -> case entry of {
              SourceContextRead _ _ declarations encoded _ ->
                if eqString expectedContext encoded
                  && eqList SourceEquality.eqDataDecl declarations datatypes
                then (,) (Just entry) bounded else (,) Nothing []
            }
          } } in case fst selection of {
            Just entry -> case entry of {
              SourceContextRead _ _ _ encoded blob ->
                let { decoded = decodeSourceCachedWithKeyParts encoded digest
                      (Just ((,) expectedCompact expectedContext)) name
                      bindings datatypes names blob input } in
                ioReturn (case decoded of {
                  Left error -> (,,) [] True (Left error);
                  Right object -> (,,)
                    (retainSourceContextRead entry cacheDir digest (snd selection))
                    True (Right object)
                })
            };
            Nothing -> do {
              let { path = sourceContextPath cacheDir digest };
              loaded <- readLegacySourceContext path;
              case loaded of {
                Left error -> ioReturn ((,,) [] False (Left error));
                Right ((,) blob actualDigest) -> do {
                  let { decoded = decodeSourceCachedWithKeyParts (encodeSourceDatatypes datatypes)
                        actualDigest (Just ((,) expectedCompact expectedContext)) name
                        bindings datatypes names blob input };
                  ioReturn (case decoded of {
                    Left error -> (,,) [] False (Left error);
                    Right object -> (,,)
                      (retainSourceContextRead
                        (SourceContextRead cacheDir digest datatypes expectedContext blob)
                        cacheDir digest (snd selection)) False (Right object)
                  })
                }
              }
            }
          }
      }
    };
  -- Caller holds the directory lock and has just written this fixed stage.
  -- Preserve the publication failure even if removing that stage also fails.
  -- Refuse directories: the Windows remove adapter would recurse into them.
  -- Host exceptions and uncooperative replacement races remain outside this
  -- normal-return cleanup; no other cache path is removed.
  rejectSourceContextPublication :: String -> String -> IO (Either String String);
  rejectSourceContextPublication cacheDir error = do {
    let { staging = cacheDir ++ "/source-context.new" };
    isDirectory <- directoryExists staging;
    cleaned <- if isDirectory
      then ioReturn (Left "cannot remove source query context staging: path is a directory")
      else do {
        code <- cacheCommand ["/bin/rm", "-f", staging];
        ioReturn (if code == 0 then Right ()
          else Left "cannot remove source query context staging")
      };
    ioReturn (case cleaned of {
      Right _ -> Left error;
      Left cleanupError -> Left (error ++ "; " ++ cleanupError)
    })
  };
  -- The existing cache-directory lock owns this staging file. Publish the
  -- complete context first; a crash can leave an unreachable blob, never a
  -- record pointing at a partially written context. No garbage collection is
  -- attempted. Reusing equal bytes preserves the shared blob's modification time.
  publishSourceContext :: String -> String -> IO (Either String String);
  publishSourceContext cacheDir context = do {
    let { staging = cacheDir ++ "/source-context.new";
          contents = sourceContextContents context };
    writeFile staging contents;
    digest <- fileDigest staging;
    if not (validSourceContextDigest digest)
    then ioReturn (Left "cannot fingerprint source query context") else do {
      let { destination = sourceContextPath cacheDir digest };
      isDirectory <- directoryExists destination;
      if isDirectory
      then rejectSourceContextPublication cacheDir
        "cannot publish source query context: destination is a directory"
      else do {
      present <- fileExists destination;
      same <- if present then do {
        previous <- readFile destination;
        ioReturn (eqString previous contents)
      } else ioReturn False;
      code <- if same
        then cacheCommand ["/bin/rm", "-f", staging]
        else cacheCommand ["/bin/mv", "-f", staging, destination];
      ioReturn (if code == 0 then Right digest else Left "cannot publish source query context")
      }
    }
  };
  writeSourceCached :: Maybe SourceEncodings -> String -> String -> String ->
    Separate.UnitObject -> IO (Either String ());
  writeSourceCached encodings cacheDir destination key object =
    let { contextEncoding = case encodings of {
      Nothing -> encodeSourceDatatypes;
      Just pool -> encodeSourceDatatypesWithPool pool
    }; declarations = Separate.unitData (Separate.objectInterface object) } in
    case sourceCacheParts key of {
      Just ((,) compact context) ->
        if eqString context (contextEncoding declarations)
          && eqString context (contextEncoding (Separate.objectContext object))
          && (case Separate.objectTerm object of { XWithData _ _ -> True; _ -> False })
        then do {
          published <- publishBinarySourceContext cacheDir declarations;
          case published of {
            Left error -> ioReturn (Left error);
            Right digest -> case Separate.unpack compact of {
              Left error -> ioReturn (Left error);
              Right fields -> writeBinaryCache destination
                [W.VNode 301 [W.VText digest, Structure.toList Structure.toText fields,
                  Structure.toUnitInterface (Separate.withInterfaceData
                    (Separate.objectInterface object) []
                    (Separate.fingerprint (Pretty.prettyTerm (Separate.objectBody object)))),
                  Structure.toXTerm (Separate.objectBody object)]]
            }
          }
        } else writeBinaryCache destination
          [W.VNode 300 [W.VText key, Structure.toRawUnitObject object]];
      Nothing -> writeBinaryCache destination
        [W.VNode 300 [W.VText key, Structure.toRawUnitObject object]]
    };
  -- The old text helpers remain callable, but actual source drivers enter this
  -- byte-oriented file dispatcher. Magic recognition never falls back on error.
  readLegacySourceContext :: String -> IO (Either String ((,) String String));
  readLegacySourceContext path = do {
    present <- fileExists path;
    raw <- if present then Storage.readRaw path
      else ioReturn (Left "source query context cache miss");
    case raw of {
      Left error -> ioReturn (Left error);
      Right bytes -> do {
        text <- W.strictUtf8 Storage.maxBytes bytes;
        case text of {
          Left error -> ioReturn (Left error);
          Right blob -> do { digest <- byteArrayDigest bytes; ioReturn (Right ((,) blob digest)) }
        }
      }
    }
  };
  writeBinaryCache :: String -> [] W.Value -> IO (Either String ());
  writeBinaryCache destination roots = do {
    written <- Storage.write 2 (destination ++ ".new") roots;
    case written of {
      Left error -> ioReturn (Left error);
      Right _ -> do {
        code <- cacheCommand ["/bin/mv", "-f", destination ++ ".new", destination];
        ioReturn (if code == 0 then Right () else Left "cannot publish inference query cache")
      }
    }
  };
  publishBinarySourceContext :: String -> [] DataDecl -> IO (Either String String);
  publishBinarySourceContext cacheDir declarations = do {
    encoded <- Storage.encode 1 [Structure.toDataContext declarations];
    case encoded of {
      Left error -> ioReturn (Left error);
      Right bytes -> do {
        digest <- byteArrayDigest bytes;
        if not (validSourceContextDigest digest)
        then ioReturn (Left "cannot fingerprint source query context") else do {
          let { destination = sourceContextPath cacheDir digest;
                staging = cacheDir ++ "/source-context.new" };
          isDirectory <- directoryExists destination;
          if isDirectory then ioReturn (Left "cannot publish source query context: destination is a directory")
          else do {
            previous <- Storage.readRaw destination;
            same <- case previous of {
              Left _ -> ioReturn False;
              Right old -> Storage.sameBytes old bytes
            };
            if same then ioReturn (Right digest) else do {
              written <- Storage.writeRaw staging bytes;
              case written of {
                Left error -> rejectSourceContextPublication cacheDir error;
                Right _ -> do {
                  code <- cacheCommand ["/bin/mv", "-f", staging, destination];
                  if code == 0 then ioReturn (Right digest)
                  else rejectSourceContextPublication cacheDir "cannot publish source query context"
                }
              }
            }
          }
        }
      }
    }
  };
  loadBinarySourceContext :: String -> String -> String -> [] DataDecl -> IO (Either String String);
  loadBinarySourceContext cacheDir digest expectedContext datatypes = do {
    let { path = sourceContextPath cacheDir digest };
    present <- fileExists path;
    raw <- if present then Storage.readRaw path
      else ioReturn (Left "source query context cache miss");
    case raw of {
      Left error -> ioReturn (Left error);
      Right bytes -> do {
        actual <- byteArrayDigest bytes;
        if not (eqString actual digest) then ioReturn (Left "invalid source query context reference")
        else if not (eqString (encodeSourceDatatypes datatypes) expectedContext)
        then ioReturn (Left "cached source query datatype context mismatch")
        else do {
          decoded <- W.decodeGraph W.defaultLimits 1 bytes;
          ioReturn (do {
            graph <- decoded;
            declarations <- case W.graphRoots graph of {
              [value] -> Structure.fromGraphDataContext graph value;
              _ -> Left "malformed binary source context roots"
            };
            let { encoded = encodeSourceDatatypes declarations };
            ensure (eqString encoded expectedContext) "cached source query context mismatch";
            Right encoded
          })
        }
      }
    }
  };
  decodeBinarySourceRecord :: String -> String -> [] ((,) String XType) -> [] DataDecl -> [] String ->
    W.Graph -> String -> [] String -> Int -> Int -> Either String Separate.UnitObject;
  decodeBinarySourceRecord key name bindings datatypes names graph context fields metadata bodyValue = do {
    ensure (length fields == 8) "unsupported source query key";
    saved <- restoreSourceCacheKey context (Separate.pack fields);
    ensure (eqString saved key) "cached query key mismatch";
    -- Disk acquisition precedes this guard, retaining the old missing-context
    -- diagnostic order. Memo hits still bind the caller's full canonical data.
    ensure (eqString (encodeSourceDatatypes datatypes) context)
      "cached source query datatype context mismatch";
    header <- Structure.fromGraphUnitInterface graph metadata;
    ensure (null (Separate.unitData header)) "contextual fragment contains an inline datatype header";
    body <- Structure.fromGraphXTerm graph bodyValue;
    Storage.admit [Storage.AdmitTerm body];
    ensure (eqString (Separate.fingerprint (Pretty.prettyTerm body))
      (Separate.unitObjectFingerprint header)) "contextual fragment body checksum mismatch";
    let { term = XWithData datatypes body;
          object = Separate.UnitObject
          (Separate.withInterfaceData header datatypes (Separate.fingerprint (Pretty.prettyTerm term))) term };
    checked <- Storage.checkUnit object;
    validateCached name bindings datatypes names checked
  };
  data BinaryQuery = BinaryInline String Int | BinaryShared String ([] String) Int Int;
  binaryQueryText :: W.Graph -> Int -> Either String String;
  binaryQueryText graph identity = do {
    value <- W.lookupGraphNode graph identity;
    case value of { W.GText text -> Right text; _ -> Left "malformed binary query text" }
  };
  binaryQuery :: W.Graph -> Either String BinaryQuery;
  binaryQuery graph = case W.graphRoots graph of {
    [root] -> do {
      value <- W.lookupGraphNode graph root;
      case value of {
        W.GNode 300 [key, object] -> do {
          saved <- binaryQueryText graph key;
          Right (BinaryInline saved object)
        };
        W.GNode 301 [reference, compact, metadata, body] -> do {
          digest <- binaryQueryText graph reference;
          fieldList <- W.lookupGraphNode graph compact;
          fields <- case fieldList of {
            W.GNode 1 values -> do {
              ensure (length values == 8) "unsupported source query key";
              traverseEither (binaryQueryText graph) values
            };
            _ -> Left "malformed binary query key fields"
          };
          Right (BinaryShared digest fields metadata body)
        };
        _ -> Left "malformed binary query roots"
      }
    };
    _ -> Left "malformed binary query roots"
  };
  readBinarySourceGraph :: [] SourceContextRead -> String -> String -> String ->
    [] ((,) String XType) -> [] DataDecl -> [] String -> W.Graph ->
    IO ((,,) ([] SourceContextRead) Bool (Either String Separate.UnitObject));
  readBinarySourceGraph previous cacheDir key name bindings datatypes names graph =
    case binaryQuery graph of {
      Left error -> ioReturn ((,,) [] False (Left error));
      Right (BinaryInline saved value) -> ioReturn ((,,) [] False (do {
        ensure (eqString saved key) "cached query key mismatch";
        object <- bindEither (Structure.fromGraphRawUnitObject graph value) Storage.checkUnit;
        validateCached name bindings datatypes names object
      }));
      Right (BinaryShared digest fields metadata body) ->
        if not (validSourceContextDigest digest)
        then ioReturn ((,,) [] False (Left "invalid source query context reference"))
        else case sourceCacheParts key of {
          Nothing -> ioReturn ((,,) [] False (Left "unsupported source query key"));
          Just ((,) _ expectedContext) -> let {
              bounded = take 8 previous;
              selected = case findSourceContextRead cacheDir digest bounded of {
                Nothing -> (,) Nothing bounded;
                Just entry -> case entry of { SourceContextRead _ _ declarations encoded kind ->
                  if eqString kind "MLF-BINARY-SOURCE-CONTEXT-1"
                    && eqString encoded expectedContext && eqList SourceEquality.eqDataDecl declarations datatypes
                  then (,) (Just entry) bounded else (,) Nothing [] }
              };
              finish = \encoded -> decodeBinarySourceRecord key name bindings datatypes names
                graph encoded fields metadata body
            } in case fst selected of {
              Just entry -> case entry of { SourceContextRead _ _ _ encoded _ ->
                ioReturn (case finish encoded of {
                  Left error -> (,,) [] True (Left error);
                  Right object -> (,,) (retainSourceContextRead entry cacheDir digest (snd selected))
                    True (Right object)
                }) };
              Nothing -> do {
                loaded <- loadBinarySourceContext cacheDir digest expectedContext datatypes;
                ioReturn (case bindEither loaded finish of {
                  Left error -> (,,) [] False (Left error);
                  Right object -> (,,) (retainSourceContextRead
                    (SourceContextRead cacheDir digest datatypes expectedContext
                      "MLF-BINARY-SOURCE-CONTEXT-1") cacheDir digest (snd selected))
                    False (Right object)
                })
              }
            }
        }
    };
  readSourceCacheFileWithWindow :: [] SourceContextRead -> String -> String -> String ->
    [] ((,) String XType) -> [] DataDecl -> [] String -> String ->
    IO ((,,) ([] SourceContextRead) Bool (Either String Separate.UnitObject));
  readSourceCacheFileWithWindow previous cacheDir key name bindings datatypes names path = do {
    input <- Storage.read 2 path;
    case input of {
      Left error -> ioReturn ((,,) [] False (Left error));
      Right (Storage.LegacyText text) -> readSourceCachedWithWindow previous cacheDir key name
        bindings datatypes names text;
      Right (Storage.BinaryInput roots) -> readBinarySourceGraph previous cacheDir key name
        bindings datatypes names roots
    }
  };
  -- Commands receive NUL-separated argv directly; paths never enter a shell.
  cacheCommand arguments =
    do {
      command <- Host.hostArguments arguments;
      runProcess ""
        (concatMapString (\field -> (field ++ stringFromCode 0))
           ((:) "1800" ((:) "" ((:) "" ((:) "" command)))))
    };
  cachePath path = if Host.absolutePath path then path else ("./" ++ path);
  -- Caller holds the cache-directory lock and has normalized cacheDir with
  -- cachePath. Clean only this fixed scratch after a normal Either return,
  -- never records, contexts or other .new files. This costs one subprocess
  -- per invocation, not per group. Host exceptions/panic are not caught here.
  -- The directory is trusted: POSIX process locks do not serialize threads
  -- in one process or protect against uncooperative filesystem replacement.
  -- Windows mlf-host remove is recursive for directories, so refuse them.
  cleanupQueryKey :: forall a. String -> Either String a -> IO (Either String a);
  cleanupQueryKey cacheDir result = do {
    let { scratch = cacheDir ++ "/query-key.new" };
    isDirectory <- directoryExists scratch;
    cleaned <- if isDirectory
      then ioReturn (Left "cannot remove query key scratch: path is a directory")
      else do {
        code <- cacheCommand ["/bin/rm", "-f", scratch];
        ioReturn (if code == 0 then Right ()
          else Left "cannot remove query key scratch")
      };
    ioReturn (case cleaned of {
      Right _ -> result;
      Left cleanupError -> case result of {
        Left error -> Left (error ++ "; " ++ cleanupError);
        Right _ -> Left cleanupError
      }
    })
  };
  writeCache :: String -> String -> IO (Either String ());
  writeCache path contents =
    do {
      writeFile (path ++ ".new") contents;
      code <- cacheCommand ((:) "/bin/mv" ((:) "-f" ((:) (path ++ ".new") ((:) path []))));
      ioReturn (if (code == 0) then Right () else Left "cannot publish inference query cache")
    };
  writeAtomic :: String -> String -> IO (Either String ());
  writeAtomic path contents = writeCache (cachePath path) contents;
  ensureDirectory :: String -> IO (Either String ());
  ensureDirectory path =
    do {
      code <- cacheCommand ((:) "/bin/mkdir" ((:) "-p" ((:) (cachePath path) [])));
      ioReturn (if (code == 0) then Right () else Left "cannot create inference cache directory")
    };
  runGroups :: String ->
               String ->
               String ->
               TypeInventory ->
               Map String ((,,) String (Maybe SAnnotation) SExpr) ->
               [] ([] String) ->
               QueryState -> IO (Either String ((,) ([] Separate.UnitObject) QueryReport));
  runGroups crateId compilerHash cacheDir inventory values groups (QueryState available objects inferred reused results) =
    case groups of {
      [] ->
        ioReturn (Right ((,) (reverse objects) (QueryReport inferred reused (reverse results))));
      (:) names rest ->
        do {
          let {
            members = map (\n -> M.get compareString n values) names
          };
          let {
            bindings = selectedBindings members available
          };
          let {
            datatypes = requiredDataIn inventory members bindings
          };
          let {
            name = groupName crateId names
          };
          let {
            key = queryKey crateId compilerHash members bindings datatypes
          };
          writeFile (cacheDir ++ "/query-key.new") key;
          digest <- fileDigest (cacheDir ++ "/query-key.new");
          let {
            destination = (cacheDir ++ ("/" ++ (digest ++ ".mlfq")))
          };
          present <- fileExists destination;
          cached <-
            if present
            then do {
                   ((,,) _ _ decoded) <- readSourceCacheFileWithWindow [] cacheDir key name
                     bindings datatypes names destination;
                   ioReturn decoded
                 }
            else ioReturn (Left "cache miss");
          let {
            result =
              case cached of {
                Right object -> Right ((,) True object);
                Left _ ->
                  mapEither ((,) False)
                    (Inference.compileLoweredGroup name
                       (if null bindings then [] else (:) (dependencyInterface bindings) [])
                       datatypes
                       members)
              }
          };
          case result of {
            Left error -> ioReturn (Left error);
            Right ((,) hit object) ->
              do {
                saved <-
                  if hit
                  then ioReturn (Right ())
                  else writeBinaryCache destination
                    [W.VNode 300 [W.VText key, Structure.toRawUnitObject object]];
                case saved of {
                  Left error -> ioReturn (Left error);
                  Right _ ->
                    case foldM Inference.mergeExternal available
                           (Separate.unitBindings (Separate.objectInterface object)) of {
                      Left error -> ioReturn (Left error);
                      Right next ->
                        let {
                          semantic =
                            Separate.fingerprint
                              (list encodeBinding
                                 (Separate.unitBindings (Separate.objectInterface object)))
                        } in
                        runGroups crateId compilerHash cacheDir inventory values rest
                          (QueryState next ((:) object objects) (inferred + (if hit then 0 else 1))
                             (reused + (if hit then 1 else 0))
                             ((:) (GroupResult name names hit semantic digest) results))
                    }
                }
              }
          }
        }
    };
  compileGroups :: String ->
                   String ->
                   [] Separate.UnitInterface ->
                   [] DataDecl ->
                   [] ((,,) String (Maybe SAnnotation) SExpr) ->
                   IO (Either String ((,) ([] Separate.UnitObject) QueryReport));
  compileGroups crateId directory imports datatypes members =
    case Dependency.declarationGroups members of {
      Left error -> ioReturn (Left error);
      Right groups ->
        case prepareData datatypes of {
          Left error -> ioReturn (Left error);
          Right inventory ->
            case foldM Inference.mergeExternal M.empty
                   (concatMap Separate.unitBindings imports) of {
              Left error -> ioReturn (Left error);
              Right available ->
                if (stringLength directory == 0)
                then ioReturn (Left "inference cache directory is empty")
                else do {
                       let {
                         cacheDir = cachePath directory
                       };
                       code <- cacheCommand ((:) "/bin/mkdir" ((:) "-p" ((:) cacheDir [])));
                       if (code /= 0)
                       then ioReturn (Left "cannot create inference cache directory")
                       else do {
                              lock <- acquireFileLock (cacheDir ++ "/.lock");
                              executable <- getExecutablePath;
                              compilerHash <- fileDigest executable;
                              result <-
                                runGroups crateId compilerHash cacheDir inventory
                                  (M.fromList compareString
                                     (map
                                        (\member ->
                                           case member of {
                                             (,,) n _ _ -> (,) n member
                                           })
                                        members))
                                  groups
                                  (QueryState available [] 0 0 []);
                              cleaned <- cleanupQueryKey cacheDir result;
                              releaseFileLock lock;
                              ioReturn cleaned
                            }
                     }
            }
        }
    };
  encodeSourceContract ((,) name contract) = node "source-contract"
    ((:) (encodeBinding ((,) name (Source.contractType contract)))
      ((:) (list (\x -> x) (Source.contractClasses contract))
        ((:) (boolean (Source.contractProtected contract)) [])));
  encodeSourceGroup prepared = node "prepared-source-group"
    ((:) (list (\member -> encodeMember (canonicalMember member)) (Source.groupOriginal prepared))
      (sourceGroupMetadata prepared));
  sourceGroupMetadata :: Source.PreparedGroup -> [] String;
  sourceGroupMetadata = sourceGroupMetadataUsing encodeTypedCandidate;
  encodeTypedCandidate protectedCandidates ((,,) role candidate ty) =
    encodeTypedCandidateBinding role candidate protectedCandidates (encodeBinding ((,) candidate ty));
  encodeTypedCandidateBinding role candidate protectedCandidates binding = node "typed-definition-candidate"
    ((:) (encodeRole role) ((:) binding
      ((:) (boolean (elem eqString candidate protectedCandidates)) [])));
  -- This pool belongs to one parsed-source driver and its current contract map.
  -- prepareGroup obtains candidate types and selected group bindings from that
  -- exact map. Apply every
  -- finalized delta to both maps with the same left bias before the next group;
  -- this ownership permits name lookup without repeating structural type checks.
  -- Map values and both encoded fields remain lazy, including unused contracts.
  data SourceContractEncoding = SourceContractEncoding String String;
  data SourceContractEncodings = SourceContractEncodings (Map String SourceContractEncoding);
  prepareSourceContractEncoding name contract =
    let { binding = encodeBinding ((,) name (Source.contractType contract)) } in
    SourceContractEncoding binding (node "source-contract"
      ((:) binding ((:) (list (\x -> x) (Source.contractClasses contract))
        ((:) (boolean (Source.contractProtected contract)) []))));
  prepareSourceContractEncodings contracts =
    SourceContractEncodings (M.mapWithKey prepareSourceContractEncoding contracts);
  extendSourceContractEncodings contracts (SourceContractEncodings entries) =
    SourceContractEncodings (M.union compareString
      (M.mapWithKey prepareSourceContractEncoding contracts) entries);
  cachedSourceContract (SourceContractEncodings entries) pair@((,) name _) =
    case M.lookup compareString name entries of {
      Just (SourceContractEncoding _ text) -> text;
      Nothing -> encodeSourceContract pair
    };
  cachedBinding (SourceContractEncodings entries) pair@((,) name _) =
    case M.lookup compareString name entries of {
      Just (SourceContractEncoding binding _) -> binding;
      -- Keep the structural fallback for absent entries. A present entry is
      -- valid only under the driver-owned, synchronized environment invariant.
      Nothing -> encodeBinding pair
    };
  cachedTypedCandidate encodings protectedCandidates ((,,) role name ty) =
    encodeTypedCandidateBinding role name protectedCandidates
      (cachedBinding encodings ((,) name ty));
  sourceGroupMetadataUsing candidateEncoding prepared =
      ((:) (list (\((,) name dictionary) -> node "class-dictionary" ((:) name ((:) dictionary [])))
        (M.toList (Source.groupRegistry prepared)))
      ((:) (list (\((,,) name classes protected) -> node "result-contract"
        ((:) name ((:) (list (\x -> x) classes) ((:) (boolean protected) []))))
        (Source.groupContracts prepared))
      ((:) (case Source.groupAuthority prepared of {
        Nothing -> node "unchanged-source-or-support" [];
        Just (Source.RootAuthority name labels protected candidates protectedCandidates) -> node "unsigned-source-root"
          ((:) name ((:) (list (\((,,) binder cls dictionary) -> node "exact-slot"
            ((:) binder ((:) cls ((:) dictionary [])))) labels)
          ((:) (boolean protected) ((:) (list (candidateEncoding protectedCandidates) candidates) []))))
      }) ((:) (list (\((,) name flag) -> node "raw-parameter-protection"
        ((:) name ((:) (boolean flag) []))) (Source.groupParameterProtection prepared)) []))));
  sourceGroupKey :: Source.PreparedGroup -> SourceKey;
  sourceGroupKey = sourceGroupKeyUsing encodeTypedCandidate;
  sourceGroupKeyUsing candidateEncoding prepared = keyNode "prepared-source-group"
    ((:) (keyList (\member -> memberKey KeyScope (canonicalMember member)) (Source.groupOriginal prepared))
      (map KeyText (sourceGroupMetadataUsing candidateEncoding prepared)));
  sourceQueryKey crateId compilerHash prepared contracts datatypes =
    sourceQueryKeyWithContext crateId compilerHash prepared contracts (encodeSourceDatatypes datatypes);
  sourceQueryKeyWithContext :: String -> String -> Source.PreparedGroup ->
    Map String Source.SourceContract -> String -> String;
  sourceQueryKeyWithContext = sourceQueryKeyUsing encodeBinding encodeTypedCandidate encodeSourceContract;
  sourceQueryKeyUsing bindingEncoding candidateEncoding contractEncoding =
    sourceQueryKeyWithSelection bindingEncoding candidateEncoding (encodeObservedContracts contractEncoding);
  encodeObservedContracts contractEncoding observed contracts =
    let { relevant = M.filterWithKey (\name _ -> S.member compareString name observed) contracts }
    in list contractEncoding (M.toList relevant);
  -- Finite file-owned contract and encoding maps have identical domains and
  -- receive the same finalized deltas. Ascending observed names preserve the
  -- original filtered-map order, while absent names contribute no entry.
  cachedObservedContracts (SourceContractEncodings entries) observed contracts =
    list (\text -> text) (concatMap (\name -> case M.lookup compareString name entries of {
      Just (SourceContractEncoding _ text) -> [text];
      Nothing -> case M.lookup compareString name contracts of {
        Nothing -> [];
        Just contract -> [encodeSourceContract ((,) name contract)]
      }
    }) (S.toList observed));
  sourceQueryKeyWithSelection bindingEncoding candidateEncoding observedContractEncoding crateId compilerHash prepared contracts datatypeContext =
    let { observed = S.fromList compareString
      (append (map fst (Source.groupBindings prepared))
        (append (map fst (Source.groupCandidateBindings prepared))
          (concatMap (\member -> Dependency.valueNames (Dependency.observeDeclaration member))
            (Source.groupOriginal prepared)))) } in
    pooledSourceKey
      [KeyText sourceQueryFormat, KeyText crateId, KeyText compilerHash,
       keyList (\member -> memberKey KeyScope (canonicalMember member)) (Source.groupMembers prepared),
       KeyText (list bindingEncoding (Source.groupBindings prepared)), KeyText datatypeContext,
       sourceGroupKeyUsing candidateEncoding prepared, KeyText (observedContractEncoding observed contracts)];
  sourceQueryKeyWithContractEncodings encodings =
    sourceQueryKeyWithSelection (cachedBinding encodings) (cachedTypedCandidate encodings) (cachedObservedContracts encodings);
  -- Raw checked inference payloads retain their established validator.
  -- Source keys use their own format3 admission, never the legacy format2
  -- key parser; unsupported source contexts retain the self-contained format1.
  runSourceGroups :: String -> String -> String -> TypeInventory -> Source.SourcePlan ->
    [] ([] String) -> Map String Source.SourceContract -> [] Separate.UnitObject ->
    Int -> Int -> [] GroupResult ->
    IO (Either String ((,,) ([] Separate.UnitObject) QueryReport (Map String Source.SourceContract)));
  runSourceGroups crateId compilerHash cacheDir inventory plan groups contracts
    objects inferred reused results =
    runSourceGroupsWithEncodings Nothing crateId compilerHash cacheDir inventory plan groups contracts
      objects inferred reused results;
  runSourceGroupsWithEncodings :: Maybe SourceEncodings -> String -> String -> String ->
    TypeInventory -> Source.SourcePlan -> [] ([] String) -> Map String Source.SourceContract ->
    [] Separate.UnitObject -> Int -> Int -> [] GroupResult ->
    IO (Either String ((,,) ([] Separate.UnitObject) QueryReport (Map String Source.SourceContract)));
  runSourceGroupsWithEncodings encodings crateId compilerHash cacheDir inventory plan groups contracts
    objects inferred reused results =
    runSourceGroupsWithContext encodings Nothing crateId compilerHash cacheDir inventory plan groups contracts
      objects inferred reused results;
  runSourceGroupsWithContext encodings datatypeContext crateId compilerHash cacheDir inventory plan groups contracts
    objects inferred reused results =
    runSourceGroupsWithOwnedContracts encodings datatypeContext Nothing crateId compilerHash cacheDir inventory plan
      groups contracts objects inferred reused results;
  runSourceGroupsWithOwnedContracts encodings datatypeContext contractEncodings crateId compilerHash cacheDir inventory plan groups contracts
    objects inferred reused results =
    runSourceGroupsWithOwnedContext encodings datatypeContext contractEncodings Nothing crateId compilerHash cacheDir inventory plan
      groups contracts objects inferred reused results;
  runSourceGroupsWithOwnedContext encodings datatypeContext contractEncodings ownedContext crateId compilerHash cacheDir inventory plan groups contracts
    objects inferred reused results =
      runSourceGroupsWithReadContext encodings datatypeContext contractEncodings ownedContext []
        crateId compilerHash cacheDir inventory plan groups contracts objects inferred reused results;
  runSourceGroupsWithReadContext encodings datatypeContext contractEncodings ownedContext readWindow crateId compilerHash cacheDir inventory plan groups contracts
    objects inferred reused results = case groups of {
    [] -> ioReturn (Right ((,,) (reverse objects)
      (QueryReport inferred reused (reverse results)) contracts));
    (:) names rest -> case (case ownedContext of {
      Just owned -> Source.prepareGroupOwned owned plan contracts names;
      Nothing -> case contractEncodings of {
        Nothing -> Source.prepareGroup plan contracts names;
        Just _ -> Source.prepareGroupSparse plan contracts names
      }
    }) of {
      Left error -> ioReturn (Left error);
      Right prepared -> do {
        let { bindings = Source.groupBindings prepared };
        let { members = Source.groupMembers prepared };
        let { datatypes = requiredDataIn inventory members
          (append bindings (Source.groupCandidateBindings prepared)) };
        let { name = groupName crateId names };
        let { context = case encodings of {
          Nothing -> (,) (encodeSourceDatatypes datatypes) Nothing;
          Just pool -> case datatypeContext of {
            Nothing -> (,) (encodeSourceDatatypesWithPool pool datatypes) Nothing;
            Just previous -> case reuseDatatypeContext pool previous datatypes of {
              (,) text next -> (,) text (Just next)
            }
          }
        }; key = case contractEncodings of {
          Nothing -> sourceQueryKeyWithContext crateId compilerHash prepared contracts (fst context);
          Just pool -> sourceQueryKeyWithContractEncodings pool crateId compilerHash prepared contracts (fst context)
        } };
        writeFile (cacheDir ++ "/query-key.new") key;
        digest <- fileDigest (cacheDir ++ "/query-key.new");
        let { destination = cacheDir ++ "/" ++ digest ++ ".mlfq" };
        present <- fileExists destination;
        cachedRead <- if present then do {
          observed <- readSourceCacheFileWithWindow readWindow cacheDir key name
            bindings datatypes names destination;
          ioReturn (case observed of {
            (,,) next _ decoded -> case (do {
              object <- decoded;
              Source.validatePreparedRaw prepared object
            }) of {
              Left error -> (,) [] (Left error);
              Right object -> (,) next (Right object)
            }
          })
        } else ioReturn ((,) [] (Left "cache miss"));
        let { cached = snd cachedRead };
        let { raw = case cached of {
          Right object -> Right ((,) True object);
          Left _ -> mapEither ((,) False) (case encodings of {
            Nothing -> Inference.compileLoweredGroup name
              ((:) (dependencyInterface bindings) []) datatypes members;
            Just (SourceEncodings pool _) -> Inference.compileLoweredGroupWithDatatypes pool name
              ((:) (dependencyInterface bindings) []) datatypes members
          })
        } };
        case raw of {
          Left error -> ioReturn (Left error);
          Right ((,) hit object) -> case Source.finishGroup prepared object of {
            Left error -> ioReturn (Left error);
            Right finalized -> do {
              saved <- if hit then ioReturn (Right ())
                else writeSourceCached encodings cacheDir destination key object;
              case saved of {
                Left error -> ioReturn (Left error);
                Right _ -> do {
                  let { finalObject = Source.finalGroupObject finalized };
                  let { finalContracts = Source.finalGroupContracts finalized };
                  let { semantic = Separate.fingerprint (list encodeBinding
                    (Separate.unitBindings (Separate.objectInterface finalObject))) };
                  runSourceGroupsWithReadContext encodings (snd context) (case contractEncodings of {
                    Nothing -> Nothing;
                    Just pool -> Just (extendSourceContractEncodings finalContracts pool)
                  }) (case ownedContext of {
                    Nothing -> Nothing;
                    Just owned -> Just (Source.extendOwnedSourceContext finalContracts owned)
                  }) (if hit then fst cachedRead else [])
                    crateId compilerHash cacheDir inventory plan rest
                    (M.union compareString finalContracts contracts)
                    ((:) finalObject objects) (inferred + (if hit then 0 else 1))
                    (reused + (if hit then 1 else 0))
                    ((:) (GroupResult name names hit semantic digest) results)
                }
              }
            }
          }
        }
      }
    }
  };
  compileSourceGroups :: String -> String -> [] Separate.UnitInterface ->
    Map String Bool -> Source.SourcePlan ->
    IO (Either String ((,,) ([] Separate.UnitObject) QueryReport (Map String Source.SourceContract)));
  compileSourceGroups crateId directory imports protected originalPlan =
    compileSourceGroupsWithEncoding False crateId directory imports protected originalPlan;
  -- Internal file-producer entry: the plan was built from finite parsed source
  -- and decoded dependencies. Keep the original API independent of any pool.
  compileParsedSourceGroups :: String -> String -> [] Separate.UnitInterface ->
    Map String Bool -> Source.SourcePlan ->
    IO (Either String ((,,) ([] Separate.UnitObject) QueryReport (Map String Source.SourceContract)));
  compileParsedSourceGroups crateId directory imports protected originalPlan =
    compileSourceGroupsWithEncoding True crateId directory imports protected originalPlan;
  compileSourceGroupsWithEncoding :: Bool -> String -> String -> [] Separate.UnitInterface ->
    Map String Bool -> Source.SourcePlan ->
    IO (Either String ((,,) ([] Separate.UnitObject) QueryReport (Map String Source.SourceContract)));
  compileSourceGroupsWithEncoding shareEncoding crateId directory imports protected originalPlan =
    case Source.initializeProtection originalPlan protected of {
      Left error -> ioReturn (Left error);
      Right plan -> case prepareData (Source.planData plan) of {
      Left error -> ioReturn (Left error);
      Right inventory -> case foldM Inference.mergeExternal M.empty
        (concatMap Separate.unitBindings imports) of {
        Left error -> ioReturn (Left error);
        Right types -> case Source.initialContracts plan types protected of {
          Left error -> ioReturn (Left error);
          Right contracts ->
            if stringLength directory == 0 then ioReturn (Left "inference cache directory is empty")
            else do {
              let { cacheDir = cachePath directory };
              code <- cacheCommand ((:) "/bin/mkdir" ((:) "-p" ((:) cacheDir [])));
              if code /= 0 then ioReturn (Left "cannot create inference cache directory") else do {
                lock <- acquireFileLock (cacheDir ++ "/.lock");
                executable <- getExecutablePath;
                compilerHash <- fileDigest executable;
                let { encodings = if shareEncoding
                      then Just (prepareSourceEncodings (Source.planData plan)) else Nothing };
                result <- runSourceGroupsWithOwnedContext encodings (case encodings of {
                  Nothing -> Nothing;
                  Just pool -> Just (emptyDatatypeContextEncoding pool)
                }) (if shareEncoding then Just (prepareSourceContractEncodings contracts) else Nothing)
                  (if shareEncoding then Just (Source.prepareOwnedSourceContext plan contracts) else Nothing)
                  crateId compilerHash cacheDir inventory plan (Source.planGroups plan) contracts [] 0 0 [];
                cleaned <- cleanupQueryKey cacheDir result;
                releaseFileLock lock;
                ioReturn cleaned
              }
            }
        }
      }
    }
  }

}
