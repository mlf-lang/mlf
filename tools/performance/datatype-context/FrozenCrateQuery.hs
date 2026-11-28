-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module FrozenCrateQuery where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Desugar as Desugar;
  import qualified Bootstrap.SourceInference as Source;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Primitive as Primitive;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.X.Type as T;
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
  -- Builtin families are reconstructed rather than written as user declarations.
  -- Include them explicitly: constructor count and nested fields affect whether
  -- a patterned do bind requires MonadFail, even with identical user layouts.
  encodeDatatypeContext datatypes = list encodeDatatype (append D.builtinDeclarations datatypes);
  encodeSourceContract ((,) name contract) = node "source-contract"
    ((:) (encodeBinding ((,) name (Source.contractType contract)))
      ((:) (list (\x -> x) (Source.contractClasses contract))
        ((:) (boolean (Source.contractProtected contract)) [])));
  encodeSourceGroup prepared = node "prepared-source-group"
    ((:) (list (\member -> encodeMember (canonicalMember member)) (Source.groupOriginal prepared))
      (sourceGroupMetadata prepared));
  sourceGroupMetadata :: Source.PreparedGroup -> [] String;
  sourceGroupMetadata prepared =
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
          ((:) (boolean protected) ((:) (list
            (\((,,) role candidate ty) -> node "typed-definition-candidate"
              ((:) (encodeRole role) ((:) (encodeBinding ((,) candidate ty))
                ((:) (boolean (elem eqString candidate protectedCandidates)) [])))) candidates) []))))
      }) ((:) (list (\((,) name flag) -> node "raw-parameter-protection"
        ((:) name ((:) (boolean flag) []))) (Source.groupParameterProtection prepared)) []))));
  sourceGroupKey :: Source.PreparedGroup -> SourceKey;
  sourceGroupKey prepared = keyNode "prepared-source-group"
    ((:) (keyList (\member -> memberKey KeyScope (canonicalMember member)) (Source.groupOriginal prepared))
      (map KeyText (sourceGroupMetadata prepared)));
  sourceQueryKey crateId compilerHash prepared contracts datatypes =
    sourceQueryKeyWithContext crateId compilerHash prepared contracts (list encodeDatatype datatypes);
  sourceQueryKeyWithContext :: String -> String -> Source.PreparedGroup ->
    Map String Source.SourceContract -> String -> String;
  sourceQueryKeyWithContext crateId compilerHash prepared contracts datatypeContext =
    let { observed = S.fromList compareString
      (append (map fst (Source.groupBindings prepared))
        (append (map fst (Source.groupCandidateBindings prepared))
          (concatMap (\member -> Dependency.valueNames (Dependency.observeDeclaration member))
            (Source.groupOriginal prepared)))) } in
    let { relevant = M.filterWithKey (\name _ -> S.member compareString name observed) contracts } in
    pooledSourceKey
      [KeyText "MLF-SOURCE-CRATE-QUERY-7", KeyText crateId, KeyText compilerHash,
       keyList (\member -> memberKey KeyScope (canonicalMember member)) (Source.groupMembers prepared),
       KeyText (list encodeBinding (Source.groupBindings prepared)), KeyText datatypeContext,
       sourceGroupKey prepared, KeyText (list encodeSourceContract (M.toList relevant))];
}
