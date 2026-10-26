-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Standalone where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Desugar as Desugar;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Prelude as Prelude;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Lexer as Lexer;

  -- A small writer records whether a genuine facade reference was used. A
  -- marker-free ordinary program keeps the original class-free MLF path.
  data Rewrite a = Rewrite (Either String ((,) Bool a));
  rewriteBind :: forall a b. Rewrite a -> (a -> Rewrite b) -> Rewrite b;
  rewriteBind (Rewrite result) function = Rewrite (do {
    (,) changed value <- result;
    case function value of {
      Rewrite next -> do { (,) changedNext answer <- next; Right ((,) (changed || changedNext) answer) }
    }
  });
  instance Functor Rewrite where {
    fmap function action = rewriteBind action (\value -> Rewrite (Right ((,) False (function value))))
  };
  instance Applicative Rewrite where {
    pure value = Rewrite (Right ((,) False value));
    (<*>) action argument = rewriteBind action (\function -> rewriteBind argument (\value -> pure (function value)))
  };
  instance Monad Rewrite where { (>>=) = rewriteBind };
  unchanged :: forall a. a -> Rewrite a;
  unchanged value = Rewrite (Right ((,) False value));
  changed :: forall a. a -> Rewrite a;
  changed value = Rewrite (Right ((,) True value));
  checked :: forall a. Either String a -> Rewrite a;
  checked result = Rewrite (mapEither ((,) False) result);
  reject :: forall a. String -> Rewrite a;
  reject message = checked (Left message);
  data Scope = Scope PreludeMode Modules.Names Modules.Interface (Set String) (Set String) (Map String String) (Map String String);
  scopeNames (Scope _ names _ _ _ _ _) = names;
  scopeInterface (Scope _ _ env _ _ _ _) = env;
  localTypes (Scope _ _ _ types _ _ _) = types;
  localTerms (Scope _ _ _ _ terms _ _) = terms;
  implicitScope (Scope mode _ _ _ _ _ _) = case mode of { ImplicitPrelude -> True; NoImplicitPrelude -> False };
  addBound bound names = Set.union compareString bound (Set.fromList compareString names);
  hasName name names = Set.member compareString name names;

  normalize :: PreludeMode -> SProgram -> Either String (Maybe ((,,) (Set String) SProgram (Map String String)));
  normalize = normalizeWithScope True;
  normalizeDemanded :: PreludeMode -> SProgram -> Either String (Maybe ((,,) (Set String) SProgram (Map String String)));
  normalizeDemanded = normalizeWithScope False;
  normalizeWithScope :: Bool -> PreludeMode -> SProgram -> Either String (Maybe ((,,) (Set String) SProgram (Map String String)));
  -- Additive opt-in seam: the ordinary path still supplies its original names
  -- and binds the original builtin values below. No checked result is invented.
  data RewrittenRoot = RewrittenRoot Scope SProgram Bool SProgram;
  rewrittenScope (RewrittenRoot scope _ _ _) = scope;
  rewrittenOriginal (RewrittenRoot _ original _ _) = original;
  rewrittenNeeded (RewrittenRoot _ _ needed _) = needed;
  rewrittenProgram (RewrittenRoot _ _ _ program) = program;
  rewrittenDisplay root = case rewrittenScope root of {
    Scope _ names _ _ _ types constructors -> displayMap names types constructors
  };
  rewriteRootWithNames :: PreludeMode -> Modules.Names -> Modules.Interface -> SProgram -> Either String RewrittenRoot;
  rewriteRootWithNames mode names env original = do {
    let {
      parts = Prelude.programParts original;
      datatypes = case parts of { (,,,) value _ _ _ -> value };
      classes = case parts of { (,,,) _ value _ _ -> value };
      types = Set.fromList compareString (append (map D.datatypeName datatypes) (map Modules.className classes));
      terms = Set.fromList compareString (append (concatMap (\declaration -> map D.constructorName (D.datatypeConstructors declaration)) datatypes)
                                  (concatMap (\declaration -> map fst (Modules.classMethods declaration)) classes));
      privateNames = (:) "MLFHasCallStack" ((:) "MLFCallStack" ((:) "MLFStackEvidence" ((:) "MLFStackFrame" ((:) "MLFLegacyUnit" []))));
      used = Set.fromList compareString (append (programNames original)
        (case names of { Modules.Names entries -> M.elems entries }));
      typeRenames = collisionNames used "StandaloneType" (filter (\name -> elem eqString name privateNames) (Set.toList types));
      constructorNames = concatMap (\declaration -> map D.constructorName (D.datatypeConstructors declaration)) datatypes;
      constructorRenames = collisionNames used "StandaloneConstructor" (filter (\name -> elem eqString name ((:) "True" ((:) "False" privateNames))) constructorNames);
      scope = Scope mode names env types terms typeRenames constructorRenames
    };
    case rewriteProgram scope original of {
      Rewrite result -> do {
        (,) needed rewritten <- result;
        Right (RewrittenRoot scope original needed rewritten)
      }
    }
  };
  normalizeWithScope wholeScope mode original = do {
    (,,) names env builtin <- Modules.standaloneBuiltinScope (programNames original);
    root <- rewriteRootWithNames mode names env original;
    if not (rewrittenNeeded root) then Right Nothing else do {
      let {
        rewritten = rewrittenProgram root;
        parts = Prelude.programParts rewritten;
        ds = case parts of { (,,,) value _ _ _ -> value };
        cs = case parts of { (,,,) _ value _ _ -> value };
        ins = case parts of { (,,,) _ _ value _ -> value };
        expression = case parts of { (,,,) _ _ _ value -> value };
        selected = if wholeScope then builtin else demandedBuiltin builtin (Set.fromList compareString (programNames rewritten));
        values = filter (\((,,) name _ _) -> not (eqString name "mlfCallStack")) (Modules.renamedValues selected)
      };
      bound <- Surface.bindValues values expression;
      Right (Just ((,,) (Set.fromList compareString (map Modules.className (Modules.renamedClasses selected)))
        (SClassProgram (append (Modules.renamedDatatypes selected) ds)
          (append (Modules.renamedClasses selected) cs)
          (append (Modules.renamedInstances selected) ins) bound) (rewrittenDisplay root)))
    }
  };
  displayMap (Modules.Names names) typeRenames constructorRenames =
    M.union compareString
      (M.fromList compareString (map (\((,) original renamed) -> (,) renamed original)
        (append (M.toList typeRenames) (M.toList constructorRenames))))
      (M.fromList compareString (map (\((,) entity name) -> (,) name
        (if eqString (Modules.owner entity) "Prelude" then Modules.spelling entity else Modules.label entity))
          (M.toList names)));
  -- Select by resolved declaration identity, never by an inferred/guessed
  -- instance head. Every instance of a demanded class remains available; the
  -- fixed point also includes superclass, context and implementation needs.
  demandedBuiltin :: Modules.Renamed -> Set String -> Modules.Renamed;
  demandedBuiltin builtin needed = let {
    classes = filter (\declaration -> hasName (Modules.className declaration) needed ||
      any (\method -> hasName (fst method) needed) (Modules.classMethods declaration)) (Modules.renamedClasses builtin);
    classSet = Set.fromList compareString (map Modules.className classes);
    instances = filter (\instanceDecl -> hasName (Modules.instanceClass instanceDecl) classSet) (Modules.renamedInstances builtin);
    values = filter (\((,,) name _ _) -> hasName name needed) (Modules.renamedValues builtin);
    references = append (concatMap classNames classes)
      (append (concatMap instanceNames instances)
        (concatMap (\((,,) name annotation body) -> (:) name
          (append (maybe [] annotationNames annotation) (expressionNames body))) values));
    expanded = addBound needed references
  } in if Set.size needed == Set.size expanded
    then Modules.Renamed (Modules.renamedDatatypes builtin) classes instances values Nothing
    else demandedBuiltin builtin expanded;
  -- Only declarations, not unknown nominal annotations or arbitrary basenames,
  -- receive these local identities. Their references use the same explicit map.
  collisionNames :: Set String -> String -> [] String -> Map String String;
  collisionNames used prefix originals = fst (foldl
    (\((,) mapping index) original -> case Modules.chooseName used prefix index of {
      (,) fresh next -> (,) (M.insert compareString original fresh mapping) next
    }) ((,) M.empty 0) originals);
  localTypeName (Scope _ _ _ _ _ renames _) name = renamedLocal renames name;
  localConstructorName (Scope _ _ _ _ _ _ renames) name = do {
    source <- sourceReference name;
    renamedLocal renames source
  };
  -- These parser markers preserve source constructor lookup rather than the
  -- direct-AST Boolean literal identity. They are not trusted builtin hooks.
  sourceReference name =
    if eqString name "$MLF.Source.True" then changed "True"
    else if eqString name "$MLF.Source.False" then changed "False"
    else unchanged name;
  renamedLocal renames name = case M.lookup compareString name renames of {
    Nothing -> unchanged name;
    Just renamed -> changed renamed
  };
  facadeName name =
    if Lexer.textStartsAt name 0 "Prelude."
    then stringSlice name 8 (stringLength name - 8)
    else name;
  facadeEntity scope space name =
    if implicitScope scope
    then case Set.toList (Modules.lookupEntities space (facadeName name) (scopeInterface scope)) of {
      (:) entity [] -> Just entity;
      _ -> Nothing
    }
    else Nothing;
  trustedMethod scope name = do {
    entity <- checked (Modules.lookupEntity Modules.Terms name (scopeInterface scope));
    case Modules.role entity of {
      Modules.Method _ -> if eqString (Modules.owner entity) "MLF.Primitive"
        then do { expression <- checked (Modules.resolveVariable (scopeNames scope) entity); changed expression }
        else reject ("unrecognized compiler-generated method: " ++ name);
      _ -> reject ("unrecognized compiler-generated method: " ++ name)
    }
  };
  variable :: Scope -> Set String -> String -> Rewrite SExpr;
  variable scope bound name =
    if eqString name "$MLF.Stack.callStack" then changed (SVar name)
    else if Lexer.textStartsAt name 0 "$MLF.Primitive."
    then trustedMethod scope (stringSlice name 15 (stringLength name - 15))
    else if Lexer.textStartsAt name 0 "$MLF.Infix."
    then do { value <- variable scope bound (stringSlice name 11 (stringLength name - 11)); changed value }
    else if hasName name bound then unchanged (SVar name)
    else case facadeEntity scope Modules.Terms name of {
      Nothing ->
        -- Keep the intentional low-level primitive fallback of direct ASTs.
        -- Ordinary facade values/methods must not reach that fallback merely
        -- because a primitive happens to share their spelling (pure/bind).
        case Set.toList (Modules.lookupEntities Modules.Terms (facadeName name) (scopeInterface scope)) of {
          (:) entity [] -> case Modules.role entity of {
            Modules.Value -> reject ("standalone facade value is not in scope without implicit Prelude: " ++ name);
            Modules.Method _ -> reject ("standalone facade method is not in scope without implicit Prelude: " ++ name);
            _ -> unchanged (SVar name)
          };
          _ -> unchanged (SVar name)
        };
      Just entity -> case Modules.role entity of {
        Modules.Primitive _ -> if eqString name (Modules.spelling entity)
          then unchanged (SVar name)
          else do { value <- checked (Modules.resolveVariable (scopeNames scope) entity); changed value };
        _ -> do { value <- checked (Modules.resolveVariable (scopeNames scope) entity); changed value }
      }
    };
  constructor scope input = do {
    name <- sourceReference input;
    constructorName scope name
  };
  constructorName scope name =
    if hasName name (localTerms scope)
    then do { renamed <- localConstructorName scope name; unchanged (SConstructor renamed) }
    else if D.sourceBuiltinConstructor name
    then unchanged (SConstructor name)
    else case facadeEntity scope Modules.Terms name of {
      Nothing -> unchanged (SConstructor name);
      Just entity -> do { value <- checked (Modules.resolveConstructor (scopeNames scope) entity); changed value }
    };
  typeName scope input = do {
    name <- sourceReference input;
    resolvedTypeName scope name
  };
  resolvedTypeName scope name =
    if hasName name (localTypes scope) then localTypeName scope name
    else if D.sourceBuiltinType name then unchanged name
    else case facadeEntity scope Modules.Types name of {
      Nothing -> unchanged name;
      Just entity -> if Modules.isRole Modules.Class entity || Modules.isRole Modules.ManagedConstraint entity
        then reject ("class used as a type constructor: " ++ name)
        else do {
          renamed <- checked (Modules.resolvedName (scopeNames scope) entity);
          if eqString name renamed then unchanged name else changed renamed
        }
    };
  predicateName scope name =
    if hasName name (localTypes scope) then localTypeName scope name
    else case facadeEntity scope Modules.Types name of {
      Nothing -> unchanged name;
      Just entity -> if Modules.isRole Modules.Class entity || Modules.isRole Modules.ManagedConstraint entity
        then do { renamed <- checked (Modules.resolvedName (scopeNames scope) entity); changed renamed }
        else reject ("not a class: " ++ name)
    };
  rewriteType :: Scope -> SType -> Rewrite SType;
  rewriteType scope ty = case ty of {
    SCon name arguments -> do { name' <- typeName scope name; arguments' <- mapM (rewriteType scope) arguments; unchanged (SCon name' arguments') };
    SArrow a b -> do { a' <- rewriteType scope a; b' <- rewriteType scope b; unchanged (SArrow a' b') };
    STypeApp f a -> do { f' <- rewriteType scope f; a' <- rewriteType scope a; unchanged (STypeApp f' a') };
    SForall flag name bound body -> do { bound' <- rewriteType scope bound; body' <- rewriteType scope body; unchanged (SForall flag name bound' body') };
    SQualified predicates body -> do { predicates' <- mapM (rewritePredicate scope) predicates; body' <- rewriteType scope body; unchanged (SQualified predicates' body') };
    _ -> unchanged ty
  };
  rewritePredicate :: Scope -> SPredicate -> Rewrite SPredicate;
  rewritePredicate scope (SPredicate name arguments) = do {
    name' <- predicateName scope name;
    arguments' <- mapM (rewriteType scope) arguments;
    unchanged (SPredicate name' arguments')
  };
  rewriteAnnotation :: Scope -> SAnnotation -> Rewrite SAnnotation;
  rewriteAnnotation scope (SAnnotation variables ty) = do { ty' <- rewriteType scope ty; unchanged (SAnnotation variables ty') };
  rewriteOptionalAnnotation :: Scope -> Maybe SAnnotation -> Rewrite (Maybe SAnnotation);
  rewriteOptionalAnnotation scope annotation = case annotation of {
    Nothing -> unchanged Nothing;
    Just value -> do { value' <- rewriteAnnotation scope value; unchanged (Just value') }
  };
  rewriteField :: Scope -> Field -> Rewrite Field;
  rewriteField scope field = case field of {
    Applied name arguments -> do { name' <- typeName scope name; arguments' <- mapM (rewriteField scope) arguments; unchanged (Applied name' arguments') };
    Function a b -> do { a' <- rewriteField scope a; b' <- rewriteField scope b; unchanged (Function a' b') };
    Application f a -> do { f' <- rewriteField scope f; a' <- rewriteField scope a; unchanged (Application f' a') };
    Quantified name kind body -> do { body' <- rewriteField scope body; unchanged (Quantified name kind body') };
    _ -> unchanged field
  };
  rewriteDatatype :: Scope -> DataDecl -> Rewrite DataDecl;
  rewriteDatatype scope declaration = do {
    constructors <- mapM (\(ConstructorDecl name fields) -> do {
      fields' <- mapM (rewriteField scope) fields;
      name' <- localConstructorName scope name;
      unchanged (ConstructorDecl name' fields')
    }) (D.datatypeConstructors declaration);
    case declaration of {
      DataDecl name variables _ -> do { name' <- localTypeName scope name; unchanged (DataDecl name' variables constructors) };
      DataDeclK name variables _ -> do { name' <- localTypeName scope name; unchanged (DataDeclK name' variables constructors) }
    }
  };
  rewriteClass :: Scope -> SClassDecl -> Rewrite SClassDecl;
  rewriteClass scope (SClassDecl name variables supers methods) = do {
    supers' <- mapM (rewritePredicate scope) supers;
    methods' <- mapM (\((,) method ty) -> do { ty' <- rewriteType scope ty; unchanged ((,) method ty') }) methods;
    name' <- localTypeName scope name;
    unchanged (SClassDecl name' variables supers' methods')
  };
  rewriteInstance :: Scope -> SInstanceDecl -> Rewrite SInstanceDecl;
  rewriteInstance scope (SInstanceDecl variables context name head methods) = do {
    context' <- mapM (rewritePredicate scope) context;
    name' <- predicateName scope name;
    head' <- mapM (rewriteType scope) head;
    methods' <- case if hasName name (localTypes scope) then Nothing else facadeEntity scope Modules.Types name of {
      Just entity -> if Modules.isRole Modules.Class entity then do {
        defaults <- checked (Prelude.standardDefaults (Modules.spelling entity) methods);
        mapM (\((,) method body) -> do {
          method' <- checked (Modules.resolvedName (scopeNames scope)
            (Modules.Entity (Modules.owner entity) method (Modules.Method (Modules.spelling entity))));
          body' <- rewriteExpr scope (localTerms scope) body;
          unchanged ((,) method' body')
        }) defaults
      } else reject ("not a class: " ++ name);
      Nothing -> mapM (\((,) method body) -> do { body' <- rewriteExpr scope (localTerms scope) body; unchanged ((,) method body') }) methods
    };
    unchanged (SInstanceDecl variables context' name' head' methods')
  };
  rewriteProgram :: Scope -> SProgram -> Rewrite SProgram;
  rewriteProgram scope program = case Prelude.programParts program of {
    (,,,) datatypes classes instances body -> do {
      datatypes' <- mapM (rewriteDatatype scope) datatypes;
      classes' <- mapM (rewriteClass scope) classes;
      instances' <- mapM (rewriteInstance scope) instances;
      body' <- rewriteExpr scope (localTerms scope) body;
      case program of {
        SProgram _ _ -> unchanged (SProgram datatypes' body');
        SClassProgram _ _ _ _ -> unchanged (SClassProgram datatypes' classes' instances' body')
      }
    }
  };
  rewriteExpr :: Scope -> Set String -> SExpr -> Rewrite SExpr;
  rewriteExpr scope bound expression = case expression of {
    SVar name -> variable scope bound name;
    SConstructor name -> constructor scope name;
    SLam name annotation body -> do {
      annotation' <- rewriteOptionalAnnotation scope annotation;
      body' <- rewriteExpr scope (Set.insert compareString name bound) body;
      unchanged (SLam name annotation' body')
    };
    SApp f a -> do { f' <- rewriteExpr scope bound f; a' <- rewriteExpr scope bound a; unchanged (SApp f' a') };
    SLet name value body -> do {
      value' <- rewriteExpr scope bound value;
      body' <- rewriteExpr scope (Set.insert compareString name bound) body;
      unchanged (SLet name value' body')
    };
    SAnn value annotation -> do { value' <- rewriteExpr scope bound value; annotation' <- rewriteAnnotation scope annotation; unchanged (SAnn value' annotation') };
    SSignature value annotation -> do { value' <- rewriteExpr scope bound value; annotation' <- rewriteAnnotation scope annotation; unchanged (SSignature value' annotation') };
    SCase value alternatives -> do {
      value' <- rewriteExpr scope bound value;
      alternatives' <- mapM (\(SAlternative pattern body) -> do {
        pattern' <- rewritePattern scope bound pattern;
        body' <- rewriteExpr scope (addBound bound (Surface.patternVariables pattern)) body;
        unchanged (SAlternative pattern' body')
      }) alternatives;
      unchanged (SCase value' alternatives')
    };
    SEquations rows -> do {
      rows' <- mapM (\((,) patterns body) -> do {
        patterns' <- mapM (rewritePattern scope bound) patterns;
        body' <- rewriteExpr scope (addBound bound (concatMap Surface.patternVariables patterns)) body;
        unchanged ((,) patterns' body')
      }) rows;
      unchanged (SEquations rows')
    };
    SLetRec definitions body -> do {
      let { bound' = addBound bound (map (\((,,) name _ _) -> name) definitions) };
      definitions' <- mapM (rewriteDefinition scope bound') definitions;
      body' <- rewriteExpr scope bound' body;
      unchanged (SLetRec definitions' body')
    };
    SDo _ _ -> rewriteExpr scope bound (Desugar.desugarDo expression);
    SChecked ty value -> do { ty' <- rewriteType scope ty; value' <- rewriteExpr scope bound value; unchanged (SChecked ty' value') };
    SSourceDefinition body -> do {
      body' <- rewriteExpr scope bound body;
      unchanged (SSourceDefinition body')
    };
    SCallSite display location body -> do {
      body' <- rewriteExpr scope bound body;
      unchanged (if eqString display "an expression type signature" && not (Modules.managedAnnotation body')
        then body' else SCallSite display location body')
    };
    SSharedBind pattern action continuation binding failure -> do {
      pattern' <- rewritePattern scope bound pattern;
      action' <- rewriteExpr scope bound action;
      continuation' <- rewriteExpr scope (addBound bound (Surface.patternVariables pattern)) continuation;
      binding' <- rewriteExpr scope bound binding;
      failure' <- rewriteExpr scope bound failure;
      unchanged (SSharedBind pattern' action' continuation' binding' failure')
    };
    _ -> unchanged expression
  };
  rewriteRecursiveMode :: Scope -> RecursiveMode -> Rewrite RecursiveMode;
  rewriteRecursiveMode scope mode = case mode of {
    InferRecursive -> unchanged InferRecursive;
    CheckRecursive annotation -> do {
      annotation' <- rewriteAnnotation scope annotation;
      unchanged (CheckRecursive annotation')
    }
  };
  rewriteDefinition :: Scope -> Set String -> (,,) String RecursiveMode SExpr -> Rewrite ((,,) String RecursiveMode SExpr);
  rewriteDefinition scope bound ((,,) name mode body) = do {
    mode' <- rewriteRecursiveMode scope mode;
    body' <- rewriteExpr scope bound body;
    unchanged ((,,) name mode' body')
  };
  rewritePattern :: Scope -> Set String -> SPattern -> Rewrite SPattern;
  rewritePattern scope bound pattern = case pattern of {
    SConstructorPattern name variables -> do {
      value <- constructor scope name;
      case value of {
        SConstructor name' -> unchanged (SConstructorPattern name' variables);
        SBoolLit boolean -> if null variables then unchanged (SBoolPattern boolean)
          else reject ("not a constructor pattern: " ++ name);
        _ -> reject ("not a constructor pattern: " ++ name)
      }
    };
    SAnnotatedPattern name annotation -> do { annotation' <- rewriteAnnotation scope annotation; unchanged (SAnnotatedPattern name annotation') };
    SNestedPattern name patterns -> do {
      patterns' <- mapM (rewritePattern scope bound) patterns;
      value <- constructor scope name;
      case value of {
        SConstructor name' -> unchanged (SNestedPattern name' patterns');
        _ -> reject ("not a constructor pattern: " ++ name)
      }
    };
    SAsPattern name inner -> do { inner' <- rewritePattern scope bound inner; unchanged (SAsPattern name inner') };
    SLazyPattern inner -> do { inner' <- rewritePattern scope bound inner; unchanged (SLazyPattern inner') };
    SOverloadedStringPattern text equality conversion -> do {
      equality' <- patternMethod scope bound equality;
      conversion' <- patternMethod scope bound conversion;
      unchanged (SOverloadedStringPattern text equality' conversion')
    };
    _ -> unchanged pattern
  };
  patternMethod :: Scope -> Set String -> String -> Rewrite String;
  patternMethod scope bound name = do {
    value <- variable scope bound name;
    case value of { SVar renamed -> unchanged renamed; _ -> reject "string-pattern evidence must be a named class method" }
  };
  -- Allocation sees names in every namespace, including bound/abstract type
  -- annotations. Expression-only free-name inventories are insufficient here.
  programNames :: SProgram -> [] String;
  programNames program = case Prelude.programParts program of {
    (,,,) datatypes classes instances body -> concat
      ((:) (concatMap datatypeNames datatypes)
        ((:) (concatMap classNames classes)
          ((:) (concatMap instanceNames instances) ((:) (expressionNames body) []))))
  };
  typeNames :: SType -> [] String;
  typeNames ty = case ty of {
    STVar name -> (:) name [];
    SCon name arguments -> (:) name (concatMap typeNames arguments);
    SArrow a b -> append (typeNames a) (typeNames b);
    STypeApp f a -> append (typeNames f) (typeNames a);
    SForall _ name bound body -> (:) name (append (typeNames bound) (typeNames body));
    SQualified predicates body -> append (concatMap predicateNames predicates) (typeNames body);
    _ -> []
  };
  predicateNames :: SPredicate -> [] String;
  predicateNames (SPredicate name arguments) = (:) name (concatMap typeNames arguments);
  annotationNames :: SAnnotation -> [] String;
  annotationNames (SAnnotation variables ty) = append variables (typeNames ty);
  fieldNames :: Field -> [] String;
  fieldNames field = case field of {
    Parameter name -> (:) name [];
    Applied name fields -> (:) name (concatMap fieldNames fields);
    Function a b -> append (fieldNames a) (fieldNames b);
    Application f a -> append (fieldNames f) (fieldNames a);
    Quantified name _ body -> (:) name (fieldNames body)
  };
  datatypeNames :: DataDecl -> [] String;
  datatypeNames declaration = (:) (D.datatypeName declaration)
    (append (map fst (D.datatypeBinders declaration))
      (concatMap (\(ConstructorDecl name fields) -> (:) name (concatMap fieldNames fields)) (D.datatypeConstructors declaration)));
  classNames :: SClassDecl -> [] String;
  classNames (SClassDecl name variables supers methods) = (:) name
    (append (map fst variables) (append (concatMap predicateNames supers)
      (concatMap (\((,) method ty) -> (:) method (typeNames ty)) methods)));
  instanceNames :: SInstanceDecl -> [] String;
  instanceNames (SInstanceDecl variables context name head methods) = (:) name
    (append (map fst variables) (append (concatMap predicateNames context)
      (append (concatMap typeNames head) (concatMap (\((,) method body) -> (:) method (expressionNames body)) methods))));
  patternNames :: SPattern -> [] String;
  patternNames pattern = case pattern of {
    SConstructorPattern name variables -> (:) name (concatMap (maybe [] (\n -> (:) n [])) variables);
    SDefaultPattern variable -> maybe [] (\n -> (:) n []) variable;
    SNestedPattern name patterns -> (:) name (concatMap patternNames patterns);
    SAnnotatedPattern name annotation -> (:) name (annotationNames annotation);
    SOverloadedStringPattern _ equality conversion -> (:) equality ((:) conversion []);
    SAsPattern name inner -> (:) name (patternNames inner);
    SLazyPattern inner -> patternNames inner;
    _ -> []
  };
  expressionNames :: SExpr -> [] String;
  expressionNames expression = case expression of {
    SVar name -> (:) name [];
    SConstructor name -> (:) name [];
    SLam name annotation body -> (:) name (append (maybe [] annotationNames annotation) (expressionNames body));
    SApp f a -> append (expressionNames f) (expressionNames a);
    SLet name value body -> (:) name (append (expressionNames value) (expressionNames body));
    SAnn value annotation -> append (expressionNames value) (annotationNames annotation);
    SSignature value annotation -> append (expressionNames value) (annotationNames annotation);
    SCase value alternatives -> append (expressionNames value)
      (concatMap (\(SAlternative pattern body) -> append (patternNames pattern) (expressionNames body)) alternatives);
    SEquations rows -> concatMap (\((,) patterns body) -> append (concatMap patternNames patterns) (expressionNames body)) rows;
    SLetRec definitions body -> append (concatMap definitionNames definitions) (expressionNames body);
    SDo statements result -> append (concatMap statementNames statements) (expressionNames result);
    SWanted dictionary candidates -> (:) dictionary (map snd candidates);
    SChecked ty value -> append (typeNames ty) (expressionNames value);
    SSourceDefinition body -> expressionNames body;
    SCallSite _ _ body -> expressionNames body;
    SSharedBind pattern action continuation binding failure -> append (patternNames pattern)
      (concatMap expressionNames ((:) action ((:) continuation ((:) binding ((:) failure [])))));
    _ -> []
  };
  recursiveModeNames :: RecursiveMode -> [] String;
  recursiveModeNames mode = case mode of {
    InferRecursive -> [];
    CheckRecursive annotation -> annotationNames annotation
  };
  definitionNames :: (,,) String RecursiveMode SExpr -> [] String;
  definitionNames ((,,) name mode body) = (:) name (append (recursiveModeNames mode) (expressionNames body));
  statementNames :: SStatement -> [] String;
  statementNames statement = case statement of {
    SDoBind pattern value -> append (patternNames pattern) (expressionNames value);
    SDoThen value -> expressionNames value;
    SDoLet name annotation value -> (:) name (append (maybe [] annotationNames annotation) (expressionNames value));
    SDoLetRec definitions -> concatMap definitionNames definitions
  }
}
