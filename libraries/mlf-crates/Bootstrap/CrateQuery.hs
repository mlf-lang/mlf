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
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Primitive as Primitive;
  import qualified Bootstrap.Host as Host;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Pretty as Pretty;
  -- Length framing and constructor tags preserve the complete lowered syntax.
  -- Pretty source text is unsuitable here: annotations, evidence roles, signed
  -- zero, quantifier flags and binder scopes are semantic query inputs.
  node tag fields = Separate.pack (Cons tag fields);
  list encode values = Separate.pack (map encode values);
  optional encode value =
    case value of {
      Nothing -> node "none" Nil;
      Just a -> node "some" (Cons (encode a) Nil)
    };
  boolean :: Bool -> String;
  boolean b = if b then "true" else "false";
  encodeKind :: Kind -> String;
  encodeKind kind =
    case kind of {
      Star -> node "star" Nil;
      KArrow a b -> node "kind-arrow" (Cons (encodeKind a) (Cons (encodeKind b) Nil))
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
      STVar n -> node "variable" (Cons n Nil);
      SBottom -> node "bottom" Nil;
      SBottomKind k -> node "bottom-kind" (Cons (encodeKind k) Nil);
      SArrow a b -> node "arrow" (Cons (encodeType a) (Cons (encodeType b) Nil));
      SCon n args -> node "constructor" (Cons n (Cons (list encodeType args) Nil));
      STypeApp f a -> node "application" (Cons (encodeType f) (Cons (encodeType a) Nil));
      SForall flag n bound body ->
        node "forall"
          (Cons (encodeFlag flag) (Cons n (Cons (encodeType bound) (Cons (encodeType body) Nil))));
      SQualified predicates body ->
        node "qualified" (Cons (list encodePredicate predicates) (Cons (encodeType body) Nil))
    };
  encodePredicate :: SPredicate -> String;
  encodePredicate (SPredicate n args) = node "predicate" (Cons n (Cons (list encodeType args) Nil));
  encodeAnnotation (SAnnotation existential ty) =
    node "annotation" (Cons (Separate.pack existential) (Cons (encodeType ty) Nil));
  encodePattern :: SPattern -> String;
  encodePattern pattern =
    case pattern of {
      SConstructorPattern n names ->
        node "constructor-pattern" (Cons n (Cons (list (optional id) names) Nil));
      SDefaultPattern name -> node "default-pattern" (Cons (optional id name) Nil);
      SNestedPattern n patterns ->
        node "nested-pattern" (Cons n (Cons (list encodePattern patterns) Nil));
      SAnnotatedPattern n a -> node "annotated-pattern" (Cons n (Cons (encodeAnnotation a) Nil));
      SIntPattern n -> node "integer-pattern" (Cons (showInt n) Nil);
      SAsPattern n pattern -> node "as-pattern" (Cons n (Cons (encodePattern pattern) Nil));
      SLazyPattern pattern -> node "lazy-pattern" (Cons (encodePattern pattern) Nil);
      SStringPattern s -> node "string-pattern" (Cons s Nil);
      SOverloadedStringPattern s equal fromString ->
        node "overloaded-string-pattern" (Cons s (Cons equal (Cons fromString Nil)));
      SBoolPattern b -> node "boolean-pattern" (Cons (boolean b) Nil)
    };
  encodeRole :: EvidenceRole -> String;
  encodeRole role =
    case role of {
      GivenEvidence -> "given";
      SuperclassEvidence -> "superclass";
      InstanceEvidence -> "instance"
    };
  encodeCandidate (Pair role name) = node (encodeRole role) (Cons name Nil);
  encodeSourceSpan (SourceSpan packageName moduleName file startLine startColumn endLine endColumn) =
    node "source-span"
      (Cons packageName (Cons moduleName (Cons file
         (Cons (showInt startLine) (Cons (showInt startColumn)
            (Cons (showInt endLine) (Cons (showInt endColumn) Nil)))))));
  encodeExpression :: SExpr -> String;
  encodeExpression expression =
    case expression of {
      SVar n -> node "variable" (Cons n Nil);
      SConstructor n -> node "constructor" (Cons n Nil);
      SLam n annotation body ->
        node "lambda"
          (Cons n (Cons (optional encodeAnnotation annotation) (Cons (encodeExpression body) Nil)));
      SApp a b -> node "apply" (Cons (encodeExpression a) (Cons (encodeExpression b) Nil));
      SLet n a b -> node "let" (Cons n (Cons (encodeExpression a) (Cons (encodeExpression b) Nil)));
      SAnn a annotation ->
        node "annotate" (Cons (encodeExpression a) (Cons (encodeAnnotation annotation) Nil));
      SIntLit n -> node "integer" (Cons (showInt n) Nil);
      SDoubleLit n -> node "double-bits" (Cons (showInt (doubleToBits n)) Nil);
      SBoolLit b -> node "boolean" (Cons (boolean b) Nil);
      SStringLit s -> node "string" (Cons s Nil);
      SPrimitive p -> node "primitive" (Cons (Primitive.primitiveName p) Nil);
      SCase a branches ->
        node "case" (Cons (encodeExpression a) (Cons (list encodeAlternative branches) Nil));
      SCallSite label span body ->
        node "call-site" (Cons label (Cons (encodeSourceSpan span) (Cons (encodeExpression body) Nil)));
      SSharedBind pattern action continuation bindMethod failure ->
        node "shared-bind"
          (Cons (encodePattern pattern) (Cons (encodeExpression action)
             (Cons (encodeExpression continuation) (Cons (encodeExpression bindMethod)
                (Cons (encodeExpression failure) Nil)))));
      SDo statements body ->
        node "do" (Cons (list encodeStatement statements) (Cons (encodeExpression body) Nil));
      SEquations rows -> node "equations" (Cons (list encodeEquation rows) Nil);
      SLetRec definitions body ->
        node "letrec" (Cons (list encodeRecursive definitions) (Cons (encodeExpression body) Nil));
      SWanted dictionary candidates ->
        node "wanted" (Cons dictionary (Cons (list encodeCandidate candidates) Nil));
      SChecked ty body -> node "checked" (Cons (encodeType ty) (Cons (encodeExpression body) Nil))
    };
  encodeAlternative :: SAlternative -> String;
  encodeAlternative (SAlternative pattern body) =
    node "alternative" (Cons (encodePattern pattern) (Cons (encodeExpression body) Nil));
  encodeEquation :: Pair (List SPattern) SExpr -> String;
  encodeEquation (Pair patterns body) =
    node "equation" (Cons (list encodePattern patterns) (Cons (encodeExpression body) Nil));
  encodeRecursive :: Triple String SAnnotation SExpr -> String;
  encodeRecursive (Triple n annotation body) =
    node "recursive"
      (Cons n (Cons (encodeAnnotation annotation) (Cons (encodeExpression body) Nil)));
  encodeStatement :: SStatement -> String;
  encodeStatement statement =
    case statement of {
      SDoBind pattern body ->
        node "do-bind" (Cons (encodePattern pattern) (Cons (encodeExpression body) Nil));
      SDoThen body -> node "do-then" (Cons (encodeExpression body) Nil);
      SDoLet n annotation body ->
        node "do-let"
          (Cons n (Cons (optional encodeAnnotation annotation) (Cons (encodeExpression body) Nil)));
      SDoLetRec definitions -> node "do-letrec" (Cons (list encodeRecursive definitions) Nil)
    };
  encodeMember (Triple n annotation body) =
    node "member"
      (Cons n (Cons (optional encodeAnnotation annotation) (Cons (encodeExpression body) Nil)));
  encodeField :: Field -> String;
  encodeField field =
    case field of {
      Parameter n -> node "parameter" (Cons n Nil);
      Function a b -> node "function-field" (Cons (encodeField a) (Cons (encodeField b) Nil));
      Applied n args -> node "applied-field" (Cons n (Cons (list encodeField args) Nil));
      Application a b -> node "application-field" (Cons (encodeField a) (Cons (encodeField b) Nil));
      Quantified n k body ->
        node "quantified-field" (Cons n (Cons (encodeKind k) (Cons (encodeField body) Nil)))
    };
  encodeConstructor (ConstructorDecl n fields) =
    node "constructor" (Cons n (Cons (list encodeField fields) Nil));
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
      (Cons (D.datatypeName declaration)
         (Cons
            (list
               (\(Pair n k) ->
                  node "parameter" (Cons (canonicalReference scope n) (Cons (encodeKind k) Nil)))
               parameters)
            (Cons (list encodeConstructor constructors) Nil)));
  encodeXType :: XType -> String;
  encodeXType ty =
    case ty of {
      XVar (XTyVar n) -> node "variable" (Cons (showInt n) Nil);
      XBot -> node "bottom" Nil;
      XBotKind k -> node "bottom-kind" (Cons (encodeKind k) Nil);
      XArrow a b -> node "arrow" (Cons (encodeXType a) (Cons (encodeXType b) Nil));
      XCon n args -> node "constructor" (Cons n (Cons (list encodeXType args) Nil));
      XApply a b -> node "application" (Cons (encodeXType a) (Cons (encodeXType b) Nil));
      XForall (XTyVar n) bound body ->
        node "forall" (Cons (showInt n) (Cons (encodeXType bound) (Cons (encodeXType body) Nil)))
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
  encodeBinding (Pair n ty) =
    node "binding" (Cons n (Cons (encodeXType (Separate.normalType (normalizeXType ty))) Nil));
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
           Pair position name -> M.insert compareString name (prefix ++ showInt position) scope
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
  leadingTypes :: SType -> List String;
  leadingTypes ty =
    case ty of {
      SForall Flexible n SBottom body -> Cons n (leadingTypes body);
      SForall Flexible n (SBottomKind _) body -> Cons n (leadingTypes body);
      _ -> Nil
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
             (\(Pair patterns body) ->
                let {
                  names = concatMap Desugar.patternVariables patterns
                } in
                let {
                  scope = canonicalScope "local:" env depth names
                } in
                Pair (map (canonicalPattern scope types typeDepth) patterns)
                  (canonicalExpression scope (depth + length names) types typeDepth body))
             rows);
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
          names = map (\(Triple n _ _) -> n) definitions
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
          (map (\(Pair role n) -> Pair role (canonicalReference env n)) candidates);
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
                        Int -> Triple String SAnnotation SExpr -> Triple String SAnnotation SExpr;
  canonicalRecursive env depth types typeDepth (Triple n annotation body) =
    let {
      names =
        case annotation of {
          SAnnotation Nil ty -> leadingTypes ty;
          _ -> Nil
        }
    } in
    Triple (canonicalReference env n) (canonicalAnnotation types typeDepth annotation)
      (canonicalExpression env depth (canonicalScope "type:" types typeDepth names)
         (typeDepth + length names)
         body);
  canonicalMember (Triple n annotation body) =
    Triple n (Separate.mapMaybeValue (canonicalAnnotation M.empty 0) annotation)
      (canonicalExpression M.empty 0 M.empty 0 body);
  data TypeInventory =
    TypeInventory (Map String DataDecl) (Map String String) (Map String (List String));
  prepareData datatypes =
    do {
      D.validateDeclarations datatypes;
      Right
        (TypeInventory (M.fromList compareString (map (\d -> Pair (D.datatypeName d) d) datatypes))
           (M.fromList compareString
              (concatMap
                 (\d ->
                    map (\c -> Pair (D.constructorName c) (D.datatypeName d))
                      (D.datatypeConstructors d))
                 datatypes))
           (M.fromList compareString
              (map
                 (\d ->
                    Pair (D.datatypeName d) (Dependency.typeNames (Dependency.observeDatatype d)))
                 datatypes)))
    };
  xTypeNames :: XType -> List String;
  xTypeNames ty =
    case ty of {
      XArrow a b -> append (xTypeNames a) (xTypeNames b);
      XCon n args -> Cons n (concatMap xTypeNames args);
      XApply a b -> append (xTypeNames a) (xTypeNames b);
      XForall _ a b -> append (xTypeNames a) (xTypeNames b);
      _ -> Nil
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
      roots = append direct (append owners (concatMap (\(Pair _ ty) -> xTypeNames ty) schemes))
    } in
    let {
      needed = Inference.closeDependencies edges S.empty roots
    } in
    map snd (filter (\entry -> S.member compareString (fst entry) needed) (M.toList datatypes));
  requiredData :: List DataDecl ->
                  List (Triple String (Maybe SAnnotation) SExpr) ->
                  List (Pair String XType) -> Either String (List DataDecl);
  requiredData datatypes members schemes =
    do {
      inventory <- prepareData datatypes;
      Right (requiredDataIn inventory members schemes)
    };
  data GroupResult = GroupResult String (List String) Bool String String;
  data QueryReport = QueryReport Int Int (List GroupResult);
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
    QueryState (Map String XType) (List Separate.UnitObject) Int Int (List GroupResult);
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
    node "MLF-CRATE-QUERY-3"
      (Cons crateId
         (Cons compilerHash
            (Cons (list (\member -> encodeMember (canonicalMember member)) members)
               (Cons (list encodeBinding bindings) (Cons (encodeDatatypeContext datatypes) Nil)))));
  dependencyInterface bindings =
    Separate.UnitInterface "QueryInputs" Nil Nil Nil Nil Nil bindings "parameters";
  peelParameters :: XTerm -> Pair (List (Pair XName XType)) XTerm;
  peelParameters term =
    case term of {
      XAbs n ty body ->
        case peelParameters body of {
          Pair parameters implementation -> Pair (Cons (Pair n ty) parameters) implementation
        };
      _ -> Pair Nil term
    };
  validateCached :: String ->
                    List (Pair String XType) ->
                    List DataDecl ->
                    List String -> Separate.UnitObject -> Either String Separate.UnitObject;
  -- Normalize only alpha-equivalent binders and equivalent application
  -- representations, including parser normalization of Field constructors.
  -- The target wire syntax omits an empty data wrapper. Reintroduce it at
  -- the fragment boundary after checking the empty context against metadata.
  -- A contextual cache already checks this exact datatype spelling. Reuse its
  -- opaque proof only when the complete canonical context agrees. Legacy
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
            XWithData ds body -> Pair ds body;
            body -> Pair Nil body
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
        (eqList Separate.sameSignature (map (\(Pair n ty) -> Pair (X.nameHint n) ty) parameters)
           expectedParameters)
        "cached dependency parameter mismatch";
      ds <- D.validateDeclarations datatypes;
      bindings <-
        Separate.collectBindings ds (XEnv M.empty (M.fromList X.compareName parameters))
          implementation;
      let {
        actual =
          Separate.sortBindings
            (map (\(Pair n ty) -> Pair (X.nameHint n) (Separate.normalType ty)) bindings)
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
            if eqList eqString (map D.prettyDeclaration datatypes)
                 (map D.prettyDeclaration expectedData)
            then Separate.objectChecked object
            else Checked.check payload;
          _ -> Checked.check payload
        };
      let {
        current =
          Separate.UnitInterface expectedName Nil Nil expectedData Nil Nil
            (Separate.unitBindings iface)
            (Separate.fingerprint (Pretty.prettyTerm payload))
      };
      Right (Separate.CheckedUnitObject current checked)
    };
  decodeCached :: String ->
                  String ->
                  List (Pair String XType) ->
                  List DataDecl -> List String -> String -> Either String Separate.UnitObject;
  decodeCached key name bindings datatypes names input =
    do {
      fields <- Separate.unpack input;
      let {
        matchValueShared1 = fields
      } in
      case matchValueShared1 of {
        Cons matchValueShared2 matchValueShared3 ->
          if MLF.Primitive.eqString matchValueShared2 "MLF-QUERY-CACHE-2"
          then case matchValueShared3 of {
                 Cons matchValueShared10 matchValueShared11 ->
                   case matchValueShared11 of {
                     Cons matchValueShared12 matchValueShared13 ->
                       case matchValueShared13 of {
                         Nil ->
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
                      Cons matchValueShared4 matchValueShared5 ->
                        case matchValueShared5 of {
                          Cons matchValueShared6 matchValueShared7 ->
                            case matchValueShared7 of {
                              Cons matchValueShared8 matchValueShared9 ->
                                case matchValueShared9 of {
                                  Nil ->
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
          Cons matchValueShared16 matchValueShared17 ->
            if MLF.Primitive.eqString matchValueShared16 "MLF-CRATE-QUERY-3"
            then case matchValueShared17 of {
                   Cons matchValueShared18 matchValueShared19 ->
                     case matchValueShared19 of {
                       Cons matchValueShared20 matchValueShared21 ->
                         case matchValueShared21 of {
                           Cons matchValueShared22 matchValueShared23 ->
                             case matchValueShared23 of {
                               Cons matchValueShared24 matchValueShared25 ->
                                 case matchValueShared25 of {
                                   Cons matchValueShared26 matchValueShared27 ->
                                     case matchValueShared27 of {
                                       Nil ->
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
           (Cons "MLF-QUERY-CACHE-2" (Cons key (Cons (Separate.encodeContextualObject object) Nil)))
    else Separate.pack
           (Cons "MLF-QUERY-CACHE-1"
              (Cons key
                 (Cons (Separate.encodeInterface (Separate.objectInterface object))
                    (Cons (Separate.encodeObject object) Nil))));
  -- Commands receive NUL-separated argv directly; paths never enter a shell.
  cacheCommand arguments =
    do {
      command <- Host.hostArguments arguments;
      runProcess ""
        (concatMapString (\field -> (field ++ stringFromCode 0))
           (Cons "1800" (Cons "" (Cons "" (Cons "" command)))))
    };
  cachePath path = if Host.absolutePath path then path else ("./" ++ path);
  writeCache :: String -> String -> IO (Either String Unit);
  writeCache path contents =
    do {
      writeFile (path ++ ".new") contents;
      code <- cacheCommand (Cons "/bin/mv" (Cons "-f" (Cons (path ++ ".new") (Cons path Nil))));
      ioReturn (if (code == 0) then Right Unit else Left "cannot publish inference query cache")
    };
  writeAtomic :: String -> String -> IO (Either String Unit);
  writeAtomic path contents = writeCache (cachePath path) contents;
  ensureDirectory :: String -> IO (Either String Unit);
  ensureDirectory path =
    do {
      code <- cacheCommand (Cons "/bin/mkdir" (Cons "-p" (Cons (cachePath path) Nil)));
      ioReturn (if (code == 0) then Right Unit else Left "cannot create inference cache directory")
    };
  runGroups :: String ->
               String ->
               String ->
               TypeInventory ->
               Map String (Triple String (Maybe SAnnotation) SExpr) ->
               List (List String) ->
               QueryState -> IO (Either String (Pair (List Separate.UnitObject) QueryReport));
  runGroups crateId compilerHash cacheDir inventory values groups (QueryState available objects inferred reused results) =
    case groups of {
      Nil ->
        ioReturn (Right (Pair (reverse objects) (QueryReport inferred reused (reverse results))));
      Cons names rest ->
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
                   input <- readFile destination;
                   ioReturn (decodeCached key name bindings datatypes names input)
                 }
            else ioReturn (Left "cache miss");
          let {
            result =
              case cached of {
                Right object -> Right (Pair True object);
                Left _ ->
                  mapEither (Pair False)
                    (Inference.compileLoweredGroup name
                       (if null bindings then Nil else Cons (dependencyInterface bindings) Nil)
                       datatypes
                       members)
              }
          };
          case result of {
            Left error -> ioReturn (Left error);
            Right (Pair hit object) ->
              do {
                saved <-
                  if hit
                  then ioReturn (Right Unit)
                  else writeCache destination (encodeCached key object);
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
                          (QueryState next (Cons object objects) (inferred + (if hit then 0 else 1))
                             (reused + (if hit then 1 else 0))
                             (Cons (GroupResult name names hit semantic digest) results))
                    }
                }
              }
          }
        }
    };
  compileGroups :: String ->
                   String ->
                   List Separate.UnitInterface ->
                   List DataDecl ->
                   List (Triple String (Maybe SAnnotation) SExpr) ->
                   IO (Either String (Pair (List Separate.UnitObject) QueryReport));
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
                       code <- cacheCommand (Cons "/bin/mkdir" (Cons "-p" (Cons cacheDir Nil)));
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
                                             Triple n _ _ -> Pair n member
                                           })
                                        members))
                                  groups
                                  (QueryState available Nil 0 0 Nil);
                              releaseFileLock lock;
                              ioReturn result
                            }
                     }
            }
        }
    }
}
