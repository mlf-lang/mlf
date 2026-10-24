-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Prelude where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Surface as Surface;
  -- The source prelude is elaborated and checked like user declarations.
  withPrelude :: PreludeMode -> SProgram -> (,) (Set String) SProgram;
  withPrelude mode program =
    case mode of {
      NoImplicitPrelude -> (,) Set.empty program;
      ImplicitPrelude ->
        case programParts program of {
          (,,,) datatypes classes instances body ->
            if L.any isMonadClass classes
            then (,) Set.empty program
            else let {
                   methods = Set.fromList compareString (L.concatMap classMethodNames classes)
                 } in
                 let {
                   expressions = (:) body (L.concatMap instanceBodies instances)
                 } in
                 let {
                   names =
                     Set.difference compareString
                       (Set.unions compareString (L.map freeNames expressions))
                       methods
                 } in
                 let {
                   needed =
                     (L.not
                        (Set.null
                           (Set.intersection compareString names
                              (Set.fromList compareString ((:) "return" ((:) "bind" []))))) ||
                      (L.any exprMentionsMonad expressions ||
                       (L.any classMentionsMonad classes || L.any instanceMentionsMonad instances)))
                 } in
                 if needed
                 then (,) (Set.singleton "Monad")
                        (SClassProgram datatypes ((:) monadClass classes)
                           ((:) ioInstance ((:) stInstance instances))
                           body)
                 else (,) Set.empty program
        }
    };
  programParts :: SProgram -> (,,,) ([] DataDecl) ([] SClassDecl) ([] SInstanceDecl) SExpr;
  programParts program =
    case program of {
      SProgram datatypes body -> (,,,) datatypes [] [] body;
      SClassProgram datatypes classes instances body -> (,,,) datatypes classes instances body
    };
  isMonadClass :: SClassDecl -> Bool;
  isMonadClass (SClassDecl name parameters superclasses methods) = eqString name "Monad";
  classMethodNames :: SClassDecl -> [] String;
  classMethodNames (SClassDecl name parameters superclasses methods) = L.map L.fst methods;
  instanceBodies :: SInstanceDecl -> [] SExpr;
  instanceBodies (SInstanceDecl variables context name head methods) = L.map L.snd methods;
  monadClass :: SClassDecl;
  monadClass =
    let {
      a = STVar "a"
    } in
    let {
      b = STVar "b"
    } in
    let {
      ma = STypeApp (STVar "m") a
    } in
    let {
      mb = STypeApp (STVar "m") b
    } in
    SClassDecl "Monad" ((:) ((,) "m" (KArrow Star Star)) []) []
      ((:) ((,) "return" (forallType "a" (SArrow a ma)))
         ((:) ((,) "bind" (forallType "a" (forallType "b" (SArrow ma (SArrow (SArrow a mb) mb)))))
            []));
  forallType :: String -> SType -> SType;
  forallType name body = SForall Flexible name SBottom body;
  ioInstance :: SInstanceDecl;
  ioInstance =
    SInstanceDecl [] [] "Monad" ((:) (SCon "IO" []) [])
      ((:) ((,) "return" (SPrimitive PIOReturn)) ((:) ((,) "bind" (SPrimitive PIOBind)) []));
  stInstance :: SInstanceDecl;
  stInstance =
    SInstanceDecl ((:) ((,) "s" Star) []) [] "Monad"
      ((:) (SCon "ST" ((:) (STVar "s") [])) [])
      ((:) ((,) "return" (SPrimitive PSTReturn)) ((:) ((,) "bind" (SPrimitive PSTBind)) []));
  freeNames :: SExpr -> Set String;
  freeNames expression =
    case expression of {
      SSourceDefinition body -> freeNames body;
      SCallSite _ _ body -> freeNames body;
      SSharedBind _ _ _ _ _ -> Set.fromList compareString (Surface.freeNames expression);
      SVar name -> Set.fromList compareString (Surface.freeNames expression);
      SLam name annotation body -> Set.delete compareString name (freeNames body);
      SApp f a -> Set.union compareString (freeNames f) (freeNames a);
      SLet name value body ->
        Set.union compareString (freeNames value) (Set.delete compareString name (freeNames body));
      SAnn value annotation -> freeNames value;
      SCase value branches ->
        Set.union compareString (freeNames value)
          (Set.unions compareString (L.map alternativeNames branches));
      SDo statements result -> L.foldr statementNames (freeNames result) statements;
      SEquations rows -> Set.fromList compareString (Surface.freeNames expression);
      SLetRec definitions body ->
        Set.difference compareString
          (Set.unions compareString ((:) (freeNames body) (L.map recursiveNames definitions)))
          (Set.fromList compareString (L.map recursiveName definitions));
      SChecked ty value -> freeNames value;
      _ -> Set.empty
    };
  alternativeNames :: SAlternative -> Set String;
  alternativeNames (SAlternative pattern body) =
    Set.difference compareString (freeNames body) (patternNames pattern);
  recursiveNames :: (,,) String SAnnotation SExpr -> Set String;
  recursiveNames ((,,) name annotation body) = freeNames body;
  recursiveName :: (,,) String SAnnotation SExpr -> String;
  recursiveName ((,,) name annotation body) = name;
  statementNames :: SStatement -> Set String -> Set String;
  statementNames statement rest =
    case statement of {
      SDoBind pattern value ->
        Set.insert compareString "bind"
          (Set.union compareString (freeNames value)
             (Set.difference compareString rest (patternNames pattern)));
      SDoThen value ->
        Set.insert compareString "bind" (Set.union compareString (freeNames value) rest);
      SDoLet name annotation value ->
        Set.union compareString (freeNames value) (Set.delete compareString name rest);
      SDoLetRec definitions ->
        Set.difference compareString
          (Set.unions compareString ((:) rest (L.map recursiveNames definitions)))
          (Set.fromList compareString (L.map recursiveName definitions))
    };
  patternNames :: SPattern -> Set String;
  patternNames pattern = Set.fromList compareString (Surface.patternVariables pattern);
  predicateMentionsMonad :: SPredicate -> Bool;
  predicateMentionsMonad (SPredicate name arguments) =
    (eqString name "Monad" || L.any typeMentionsMonad arguments);
  typeMentionsMonad :: SType -> Bool;
  typeMentionsMonad ty =
    case ty of {
      SQualified predicates body ->
        (L.any predicateMentionsMonad predicates || typeMentionsMonad body);
      SForall flag name bound body -> (typeMentionsMonad bound || typeMentionsMonad body);
      SArrow a b -> (typeMentionsMonad a || typeMentionsMonad b);
      STypeApp f a -> (typeMentionsMonad f || typeMentionsMonad a);
      SCon name arguments -> L.any typeMentionsMonad arguments;
      _ -> False
    };
  classMentionsMonad :: SClassDecl -> Bool;
  classMentionsMonad (SClassDecl name parameters superclasses methods) =
    (L.any predicateMentionsMonad superclasses ||
     L.any (\entry -> typeMentionsMonad (L.snd entry)) methods);
  instanceMentionsMonad :: SInstanceDecl -> Bool;
  instanceMentionsMonad (SInstanceDecl variables context name head methods) =
    (eqString name "Monad" ||
     (L.any predicateMentionsMonad context || L.any typeMentionsMonad head));
  exprMentionsMonad :: SExpr -> Bool;
  exprMentionsMonad expression =
    case expression of {
      SSourceDefinition body -> exprMentionsMonad body;
      SCallSite _ _ body -> exprMentionsMonad body;
      SSharedBind _ _ _ _ _ -> True;
      SLam name annotation body ->
        (L.maybe False annotationMentionsMonad annotation || exprMentionsMonad body);
      SApp f a -> (exprMentionsMonad f || exprMentionsMonad a);
      SLet name value body -> (exprMentionsMonad value || exprMentionsMonad body);
      SAnn value annotation -> (exprMentionsMonad value || annotationMentionsMonad annotation);
      SCase value branches -> (exprMentionsMonad value || L.any alternativeMentionsMonad branches);
      SDo statements result ->
        (L.any statementMentionsMonad statements || exprMentionsMonad result);
      SEquations rows -> L.any equationMentionsMonad rows;
      SLetRec definitions body ->
        (L.any recursiveMentionsMonad definitions || exprMentionsMonad body);
      SChecked ty value -> (typeMentionsMonad ty || exprMentionsMonad value);
      _ -> False
    };
  annotationMentionsMonad :: SAnnotation -> Bool;
  annotationMentionsMonad (SAnnotation variables ty) = typeMentionsMonad ty;
  alternativeMentionsMonad :: SAlternative -> Bool;
  alternativeMentionsMonad (SAlternative pattern body) =
    (patternMentionsMonad pattern || exprMentionsMonad body);
  equationMentionsMonad :: (,) ([] SPattern) SExpr -> Bool;
  equationMentionsMonad ((,) patterns body) =
    (L.any patternMentionsMonad patterns || exprMentionsMonad body);
  recursiveMentionsMonad :: (,,) String SAnnotation SExpr -> Bool;
  recursiveMentionsMonad ((,,) name annotation body) =
    (annotationMentionsMonad annotation || exprMentionsMonad body);
  statementMentionsMonad :: SStatement -> Bool;
  statementMentionsMonad statement =
    case statement of {
      SDoBind pattern value -> (patternMentionsMonad pattern || exprMentionsMonad value);
      SDoThen value -> exprMentionsMonad value;
      SDoLet name annotation value ->
        (L.maybe False annotationMentionsMonad annotation || exprMentionsMonad value);
      SDoLetRec definitions -> L.any recursiveMentionsMonad definitions
    };
  patternMentionsMonad :: SPattern -> Bool;
  patternMentionsMonad pattern =
    case pattern of {
      SAsPattern _ inner -> patternMentionsMonad inner;
      SLazyPattern inner -> patternMentionsMonad inner;
      SAnnotatedPattern name annotation -> annotationMentionsMonad annotation;
      SNestedPattern name patterns -> L.any patternMentionsMonad patterns;
      _ -> False
    };

  -- Standard Haskell class identities are owned by the reserved shared facade.
  -- Legacy Prelude.Monad remains an independent guest API.
  hierarchyClasses :: [] SClassDecl;
  hierarchyClasses = (:) (SClassDecl "Functor" ((:) ((,) "f" (KArrow Star Star)) []) ([]) ((:) ((,) "fmap" (forallType "a" (forallType "b" (SArrow (SArrow (STVar "a") (STVar "b")) (SArrow (STypeApp (STVar "f") (STVar "a")) (STypeApp (STVar "f") (STVar "b"))))))) ((:) ((,) "<$" (forallType "a" (forallType "b" (SArrow (STVar "a") (SArrow (STypeApp (STVar "f") (STVar "b")) (STypeApp (STVar "f") (STVar "a"))))))) ([])))) ((:) (SClassDecl "Applicative" ((:) ((,) "f" (KArrow Star Star)) []) ((:) (SPredicate "Functor" ((:) (STVar "f") [])) ([])) ((:) ((,) "pure" (forallType "a" (SArrow (STVar "a") (STypeApp (STVar "f") (STVar "a"))))) ((:) ((,) "<*>" (forallType "a" (forallType "b" (SArrow (STypeApp (STVar "f") (SArrow (STVar "a") (STVar "b"))) (SArrow (STypeApp (STVar "f") (STVar "a")) (STypeApp (STVar "f") (STVar "b"))))))) ((:) ((,) "liftA2" (forallType "a" (forallType "b" (forallType "c" (SArrow (SArrow (STVar "a") (SArrow (STVar "b") (STVar "c"))) (SArrow (STypeApp (STVar "f") (STVar "a")) (SArrow (STypeApp (STVar "f") (STVar "b")) (STypeApp (STVar "f") (STVar "c"))))))))) ((:) ((,) "*>" (forallType "a" (forallType "b" (SArrow (STypeApp (STVar "f") (STVar "a")) (SArrow (STypeApp (STVar "f") (STVar "b")) (STypeApp (STVar "f") (STVar "b"))))))) ((:) ((,) "<*" (forallType "a" (forallType "b" (SArrow (STypeApp (STVar "f") (STVar "a")) (SArrow (STypeApp (STVar "f") (STVar "b")) (STypeApp (STVar "f") (STVar "a"))))))) ([]))))))) ((:) (SClassDecl "Monad" ((:) ((,) "f" (KArrow Star Star)) []) ((:) (SPredicate "Applicative" ((:) (STVar "f") [])) ([])) ((:) ((,) ">>=" (forallType "a" (forallType "b" (SArrow (STypeApp (STVar "f") (STVar "a")) (SArrow (SArrow (STVar "a") (STypeApp (STVar "f") (STVar "b"))) (STypeApp (STVar "f") (STVar "b"))))))) ((:) ((,) ">>" (forallType "a" (forallType "b" (SArrow (STypeApp (STVar "f") (STVar "a")) (SArrow (STypeApp (STVar "f") (STVar "b")) (STypeApp (STVar "f") (STVar "b"))))))) ((:) ((,) "return" (forallType "a" (SArrow (STVar "a") (STypeApp (STVar "f") (STVar "a"))))) ([]))))) ([])));
  hierarchyInstances :: [] SInstanceDecl;
  hierarchyInstances = (:) (SInstanceDecl ([]) [] "Functor" ((:) (SCon "IO" []) []) ((:) ((,) "fmap" (SLam "$f" Nothing (SLam "$xs" Nothing (SApp (SApp (SPrimitive PIOBind) (SVar "$xs")) (SLam "$x" Nothing (SApp (SPrimitive PIOReturn) (SApp (SVar "$f") (SVar "$x")))))))) ([]))) ((:) (SInstanceDecl ([]) [] "Applicative" ((:) (SCon "IO" []) []) ((:) ((,) "pure" (SPrimitive PIOReturn)) ((:) ((,) "<*>" (SLam "$fs" Nothing (SLam "$xs" Nothing (SApp (SApp (SPrimitive PIOBind) (SVar "$fs")) (SLam "$f" Nothing (SApp (SApp (SPrimitive PIOBind) (SVar "$xs")) (SLam "$x" Nothing (SApp (SPrimitive PIOReturn) (SApp (SVar "$f") (SVar "$x")))))))))) ([])))) ((:) (SInstanceDecl ([]) [] "Monad" ((:) (SCon "IO" []) []) ((:) ((,) ">>=" (SPrimitive PIOBind)) ([]))) ((:) (SInstanceDecl ((:) ((,) "s" Star) []) [] "Functor" ((:) (SCon "ST" ((:) (STVar "s") [])) []) ((:) ((,) "fmap" (SLam "$f" Nothing (SLam "$xs" Nothing (SApp (SApp (SPrimitive PSTBind) (SVar "$xs")) (SLam "$x" Nothing (SApp (SPrimitive PSTReturn) (SApp (SVar "$f") (SVar "$x")))))))) ([]))) ((:) (SInstanceDecl ((:) ((,) "s" Star) []) [] "Applicative" ((:) (SCon "ST" ((:) (STVar "s") [])) []) ((:) ((,) "pure" (SPrimitive PSTReturn)) ((:) ((,) "<*>" (SLam "$fs" Nothing (SLam "$xs" Nothing (SApp (SApp (SPrimitive PSTBind) (SVar "$fs")) (SLam "$f" Nothing (SApp (SApp (SPrimitive PSTBind) (SVar "$xs")) (SLam "$x" Nothing (SApp (SPrimitive PSTReturn) (SApp (SVar "$f") (SVar "$x")))))))))) ([])))) ((:) (SInstanceDecl ((:) ((,) "s" Star) []) [] "Monad" ((:) (SCon "ST" ((:) (STVar "s") [])) []) ((:) ((,) ">>=" (SPrimitive PSTBind)) ([]))) ([]))))));
  -- Standard class signatures retain [Char] at the conversion boundary;
  -- the implementation's opaque String is an ordinary IsString instance.
  charListType :: SType;
  charListType = SCon "[]" ((:) (SCon "Char" []) []);
  equalityClass :: SClassDecl;
  equalityClass =
    SClassDecl "Eq" ((:) ((,) "a" Star) []) []
      ((:) ((,) "==" (SArrow (STVar "a") (SArrow (STVar "a") (SCon "Bool" []))))
         ((:) ((,) "/=" (SArrow (STVar "a") (SArrow (STVar "a") (SCon "Bool" [])))) []));
  stringClass :: SClassDecl;
  stringClass = SClassDecl "IsString" ((:) ((,) "a" Star) []) []
    ((:) ((,) "fromString" (SArrow charListType (STVar "a"))) []);
  managedStackType :: SType -> SType;
  managedStackType body = SQualified ((:) (SPredicate "HasCallStack" []) []) body;
  monadFailClass :: SClassDecl;
  monadFailClass = SClassDecl "MonadFail" ((:) ((,) "m" (KArrow Star Star)) [])
    ((:) (SPredicate "Monad" ((:) (STVar "m") [])) [])
    ((:) ((,) "fail" (forallType "a" (managedStackType
      (SArrow charListType (STypeApp (STVar "m") (STVar "a")))))) []);
  sharedClasses :: [] SClassDecl;
  sharedClasses = (:) equalityClass ((:) stringClass ((:) monadFailClass hierarchyClasses));
  publicIOErrorType :: SType;
  publicIOErrorType = forallType "a" (managedStackType
    (SArrow (SCon "IOError" []) (SCon "IO" ((:) (STVar "a") []))));
  publicIOErrorBinding :: (,,) String (Maybe SAnnotation) SExpr;
  publicIOErrorBinding = (,,) "ioError" (Just (SAnnotation [] publicIOErrorType))
    (SLam "$error" Nothing
      (SApp (SApp (SPrimitive PIOErrorWithStack) (SVar "$error")) (SVar "$MLF.Stack.callStack")));
  stackFacadeValues :: [] ((,,) String (Maybe SAnnotation) SExpr);
  stackFacadeValues =
    (:) ((,,) "callStack" (Just (SAnnotation [] (managedStackType (SCon "CallStack" []))))
            (SVar "$MLF.Stack.callStack"))
      ((:) ((,,) "prettyCallStack" (Just (SAnnotation []
                      (SArrow (SCon "CallStack" []) charListType))) (SPrimitive PPrettyCallStack))
        ((:) publicIOErrorBinding []));
  ioFailInstance :: SInstanceDecl;
  ioFailInstance = simpleInstance "MonadFail" (SCon "IO" []) "fail"
    (SLam "$message" Nothing
      (SApp (SApp (SPrimitive PIOErrorWithStack) (SApp (SPrimitive PUserError) (SVar "$message")))
        (SVar "$MLF.Stack.callStack")));
  simpleInstance :: String -> SType -> String -> SExpr -> SInstanceDecl;
  simpleInstance klass ty method body =
    SInstanceDecl [] [] klass ((:) ty []) ((:) ((,) method body) []);
  booleanEquality :: SExpr;
  booleanEquality = SLam "$a" Nothing (SLam "$b" Nothing
    (SCase (SVar "$a")
      ((:) (SAlternative (SBoolPattern True) (SVar "$b"))
        ((:) (SAlternative (SBoolPattern False) (negated (SVar "$b"))) []))));
  negated :: SExpr -> SExpr;
  negated value = SApp (SApp (SApp (SPrimitive PIfThenElse) value) (SBoolLit False)) (SBoolLit True);
  charEquality :: SExpr;
  charEquality = SLam "$a" Nothing (SLam "$b" Nothing
    (SApp (SApp (SPrimitive PEqInt) (SApp (SPrimitive PCharCode) (SVar "$a")))
      (SApp (SPrimitive PCharCode) (SVar "$b"))));
  sharedInstances :: [] SInstanceDecl;
  sharedInstances =
    L.append
      ((:) (simpleInstance "Eq" (SCon "Int" []) "==" (SPrimitive PEqInt))
        ((:) (simpleInstance "Eq" (SCon "Double" []) "==" (SPrimitive PEqDouble))
          ((:) (simpleInstance "Eq" (SCon "String" []) "==" (SPrimitive PEqString))
            ((:) (simpleInstance "Eq" (SCon "Bool" []) "==" booleanEquality)
              ((:) (simpleInstance "Eq" (SCon "Char" []) "==" charEquality)
                ((:) (simpleInstance "Eq" (SCon "()" []) "=="
                         collectionUnitEquality)
                  ((:) (simpleInstance "IsString" (SCon "String" []) "fromString" (SPrimitive PTextFromChars))
                    ((:) (simpleInstance "IsString" charListType "fromString" (SLam "$chars" Nothing (SVar "$chars"))) []))))))))
      (L.append canonicalCollectionInstances ((:) ioFailInstance hierarchyInstances));
  standardMethodClass :: String -> String;
  standardMethodClass name =
    if L.elem eqString name ((:) "==" ((:) "/=" [])) then "Eq"
    else if eqString name "fromString" then "IsString"
    else if eqString name "fail" then "MonadFail"
    else if L.elem eqString name ((:) "fmap" ((:) "<$" [])) then "Functor"
    else if L.elem eqString name ((:) "pure" ((:) "<*>" ((:) "liftA2" ((:) "*>" ((:) "<*" []))))) then "Applicative"
    else "Monad";
  providedMethod name methods =
    case L.find (\entry -> eqString name (L.fst entry)) methods of {
      Just entry -> L.snd entry;
      Nothing -> SVar ("$missing builtin method " ++ name)
    };
  hasMethod name methods = L.any (\entry -> eqString name (L.fst entry)) methods;
  addDefault name body methods = if hasMethod name methods then methods else L.append methods ((:) ((,) name body) []);
  standardDefaults :: String -> [] ((,) String SExpr) -> Either String ([] ((,) String SExpr));
  standardDefaults klass methods =
    if eqString klass "Eq" then
      if hasMethod "==" methods then
        Right (addDefault "/=" (SLam "$a" Nothing (SLam "$b" Nothing
          (negated (SApp (SApp (providedMethod "==" methods) (SVar "$a")) (SVar "$b"))))) methods)
      else if hasMethod "/=" methods then
        Right (addDefault "==" (SLam "$a" Nothing (SLam "$b" Nothing
          (negated (SApp (SApp (providedMethod "/=" methods) (SVar "$a")) (SVar "$b"))))) methods)
      else Left "Eq instance requires == or /="
    else if eqString klass "MonadFail" then
      if hasMethod "fail" methods then Right methods
      else Left "MonadFail instance requires fail"
    else if eqString klass "IsString" then
      if hasMethod "fromString" methods then Right methods
      else Left "IsString instance requires fromString"
    else if eqString klass "Functor" then
      if hasMethod "fmap" methods then Right (addDefault "<$" (SLam "$defaultX" Nothing (SApp (providedMethod "fmap" methods) (SLam "$defaultIgnored" Nothing (SVar "$defaultX")))) methods)
      else Left "Functor instance requires fmap"
    else if eqString klass "Applicative" then
      if L.not (hasMethod "pure" methods) then Left "Applicative instance requires pure"
      else if L.not (hasMethod "<*>" methods || hasMethod "liftA2" methods) then Left "Applicative instance requires <*> or liftA2"
      else let {
        ap = if hasMethod "<*>" methods then providedMethod "<*>" methods else SApp (providedMethod "liftA2" methods) (SLam "$defaultA" Nothing (SVar "$defaultA"));
        lift = if hasMethod "liftA2" methods then providedMethod "liftA2" methods else SLam "$defaultF" Nothing (SLam "$defaultX" Nothing (SApp (providedMethod "<*>" methods) (SApp (SApp (SVar "$MLF.Primitive.fmap") (SVar "$defaultF")) (SVar "$defaultX"))));
        complete = addDefault "<*>" ap (addDefault "liftA2" lift methods)
      } in Right (addDefault "*>" (SLam "$defaultX" Nothing (SLam "$defaultY" Nothing (SApp (SApp (ap) (SApp (SApp (SVar "$MLF.Primitive.<$") (SLam "$defaultA" Nothing (SVar "$defaultA"))) (SVar "$defaultX"))) (SVar "$defaultY")))) (addDefault "<*" (SApp (lift) (SLam "$defaultA" Nothing (SLam "$defaultB" Nothing (SVar "$defaultA")))) complete))
    else if eqString klass "Monad" then
      if hasMethod ">>=" methods then Right (addDefault "return" (SVar "$MLF.Primitive.pure") (addDefault ">>" (SLam "$defaultX" Nothing (SLam "$defaultY" Nothing (SApp (SApp (providedMethod ">>=" methods) (SVar "$defaultX")) (SLam "$defaultIgnored" Nothing (SVar "$defaultY"))))) methods))
      else Left "Monad instance requires >>= which defines standard do notation"
    else Right methods;

  -- Canonical base list/tuple instances. Recursion has closed signatures;
  -- element Eq is passed explicitly, avoiding a recursive qualified binding.
  collectionListMap :: SExpr;
  collectionListMap = (SLetRec ((:) ((,,) "$collectionMap" (SAnnotation [] (forallType "a" (forallType "b" (SArrow (SArrow (STVar "a") (STVar "b")) (SArrow (SCon "[]" ((:) (STVar "a") [])) (SCon "[]" ((:) (STVar "b") []))))))) (SLam "$f" Nothing (SLam "$xs" Nothing (SCase (SVar "$xs") ((:) (SAlternative (SConstructorPattern "[]" []) (SConstructor "[]")) ((:) (SAlternative (SConstructorPattern ":" ((:) (Just "$x") ((:) (Just "$xt") []))) (SApp (SApp (SConstructor ":") (SApp (SVar "$f") (SVar "$x"))) (SApp (SApp (SVar "$collectionMap") (SVar "$f")) (SVar "$xt")))) [])))))) []) (SVar "$collectionMap"));
  collectionListBind :: SExpr;
  collectionListBind = (SLetRec ((:) ((,,) "$collectionAppend" (SAnnotation [] (forallType "a" (SArrow (SCon "[]" ((:) (STVar "a") [])) (SArrow (SCon "[]" ((:) (STVar "a") [])) (SCon "[]" ((:) (STVar "a") [])))))) (SLam "$xs" Nothing (SLam "$ys" Nothing (SCase (SVar "$xs") ((:) (SAlternative (SConstructorPattern "[]" []) (SVar "$ys")) ((:) (SAlternative (SConstructorPattern ":" ((:) (Just "$x") ((:) (Just "$xt") []))) (SApp (SApp (SConstructor ":") (SVar "$x")) (SApp (SApp (SVar "$collectionAppend") (SVar "$xt")) (SVar "$ys")))) [])))))) ((:) ((,,) "$collectionBind" (SAnnotation [] (forallType "a" (forallType "b" (SArrow (SCon "[]" ((:) (STVar "a") [])) (SArrow (SArrow (STVar "a") (SCon "[]" ((:) (STVar "b") []))) (SCon "[]" ((:) (STVar "b") []))))))) (SLam "$xs" Nothing (SLam "$f" Nothing (SCase (SVar "$xs") ((:) (SAlternative (SConstructorPattern "[]" []) (SConstructor "[]")) ((:) (SAlternative (SConstructorPattern ":" ((:) (Just "$x") ((:) (Just "$xt") []))) (SApp (SApp (SVar "$collectionAppend") (SApp (SVar "$f") (SVar "$x"))) (SApp (SApp (SVar "$collectionBind") (SVar "$xt")) (SVar "$f")))) [])))))) [])) (SVar "$collectionBind"));
  collectionListEquality :: SExpr;
  collectionListEquality = (SApp (SLetRec ((:) ((,,) "$collectionEq" (SAnnotation [] (forallType "a" (SArrow (SArrow (STVar "a") (SArrow (STVar "a") (SCon "Bool" []))) (SArrow (SCon "[]" ((:) (STVar "a") [])) (SArrow (SCon "[]" ((:) (STVar "a") [])) (SCon "Bool" [])))))) (SLam "$eq" Nothing (SLam "$xs" Nothing (SLam "$ys" Nothing (SCase (SVar "$xs") ((:) (SAlternative (SConstructorPattern "[]" []) (SCase (SVar "$ys") ((:) (SAlternative (SConstructorPattern "[]" []) (SBoolLit True)) ((:) (SAlternative (SConstructorPattern ":" ((:) (Just "$y") ((:) (Just "$yt") []))) (SBoolLit False)) [])))) ((:) (SAlternative (SConstructorPattern ":" ((:) (Just "$x") ((:) (Just "$xt") []))) (SCase (SVar "$ys") ((:) (SAlternative (SConstructorPattern "[]" []) (SBoolLit False)) ((:) (SAlternative (SConstructorPattern ":" ((:) (Just "$y") ((:) (Just "$yt") []))) (SApp (SApp (SApp (SPrimitive PIfThenElse) (SApp (SApp (SVar "$eq") (SVar "$x")) (SVar "$y"))) (SApp (SApp (SApp (SVar "$collectionEq") (SVar "$eq")) (SVar "$xt")) (SVar "$yt"))) (SBoolLit False))) [])))) []))))))) []) (SVar "$collectionEq")) (SVar "$MLF.Primitive.=="));
  collectionUnitEquality :: SExpr;
  collectionUnitEquality = (SLam "$a" Nothing (SLam "$b" Nothing (SCase (SVar "$a") ((:) (SAlternative (SConstructorPattern "()" []) (SCase (SVar "$b") ((:) (SAlternative (SConstructorPattern "()" []) (SBoolLit True)) []))) []))));
  collectionTupleInstance :: String -> [] String -> SInstanceDecl;
  collectionTupleInstance name variables =
    SInstanceDecl (L.map (\n -> (,) n Star) variables)
      (L.map (\n -> SPredicate "Eq" ((:) (STVar n) [])) variables)
      "Eq" ((:) (SCon name (L.map STVar variables)) [])
      ((:) ((,) "==" (collectionTupleEquality name variables)) []);
  collectionTupleEquality :: String -> [] String -> SExpr;
  collectionTupleEquality name variables =
    SLam "$left" Nothing (SLam "$right" Nothing
      (SCase (SVar "$left")
        ((:) (SAlternative
          (SConstructorPattern name (L.map (\n -> Just ("$x" ++ n)) variables))
          (SCase (SVar "$right")
            ((:) (SAlternative
              (SConstructorPattern name (L.map (\n -> Just ("$y" ++ n)) variables))
              (L.foldr
                (\n -> \rest ->
                  SApp (SApp (SApp (SPrimitive PIfThenElse)
                    (SApp (SApp (SVar "$MLF.Primitive.==") (SVar ("$x" ++ n))) (SVar ("$y" ++ n))))
                    rest) (SBoolLit False))
                (SBoolLit True) variables)) []))) [])));
  collectionTupleInstances :: [] SInstanceDecl;
  collectionTupleInstances = L.map
    (\arity -> collectionTupleInstance
      ("(" ++ L.concatStrings (L.replicate (arity - 1) ",") ++ ")")
      (L.map (\i -> "a" ++ showInt i) (L.range 1 arity)))
    (L.range 2 15);
  -- Base's partially-applied tuple Functor instances exist only at arities 2..7.
  -- Prefix fields need no class constraints and remain lazy; the outer tuple is strict.
  collectionTupleFunctorInstance :: Int -> SInstanceDecl;
  collectionTupleFunctorInstance arity =
    let { name = "(" ++ L.concatStrings (L.replicate (arity - 1) ",") ++ ")" } in
    let { variables = L.map (\i -> "a" ++ showInt i) (L.range 1 (arity - 1)) } in
    SInstanceDecl (L.map (\n -> (,) n Star) variables) [] "Functor"
      ((:) (SCon name (L.map STVar variables)) [])
      ((:) ((,) "fmap"
        (SLam "$function" Nothing (SLam "$tuple" Nothing
          (SCase (SVar "$tuple")
            ((:) (SAlternative
              (SConstructorPattern name
                (L.append (L.map (\n -> Just ("$" ++ n)) variables) ((:) (Just "$last") [])))
              (L.foldl SApp (SConstructor name)
                (L.append (L.map (\n -> SVar ("$" ++ n)) variables)
                  ((:) (SApp (SVar "$function") (SVar "$last")) [])))) []))))) []);
  collectionTupleFunctorInstances :: [] SInstanceDecl;
  collectionTupleFunctorInstances = L.map collectionTupleFunctorInstance (L.range 2 7);
  canonicalCollectionInstances :: [] SInstanceDecl;
  canonicalCollectionInstances = L.append ((:) (SInstanceDecl ((:) ((,) "a" Star) []) ((:) (SPredicate "Eq" ((:) (STVar "a") [])) []) "Eq" ((:) (SCon "[]" ((:) (STVar "a") [])) []) ((:) ((,) "==" collectionListEquality) [])) []) (L.append collectionTupleInstances (L.append collectionTupleFunctorInstances ((:) (SInstanceDecl [] [] "Functor" ((:) (SCon "[]" []) []) ((:) ((,) "fmap" collectionListMap) [])) ((:) (SInstanceDecl [] [] "Applicative" ((:) (SCon "[]" []) []) ((:) ((,) "pure" (SLam "$x" Nothing (SApp (SApp (SConstructor ":") (SVar "$x")) (SConstructor "[]")))) ((:) ((,) "<*>" (SLam "$fs" Nothing (SLam "$xs" Nothing (SApp (SApp collectionListBind (SVar "$fs")) (SLam "$f" Nothing (SApp (SApp collectionListMap (SVar "$f")) (SVar "$xs"))))))) []))) ((:) (SInstanceDecl [] [] "Monad" ((:) (SCon "[]" []) []) ((:) ((,) ">>=" collectionListBind) [])) ((:) (SInstanceDecl [] [] "MonadFail" ((:) (SCon "[]" []) []) ((:) ((,) "fail" (SLam "$ignored" Nothing (SConstructor "[]"))) [])) []))))));
}
