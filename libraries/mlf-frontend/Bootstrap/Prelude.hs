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
  withPrelude :: PreludeMode -> SProgram -> Pair (Set String) SProgram;
  withPrelude mode program =
    case mode of {
      NoImplicitPrelude -> Pair Set.empty program;
      ImplicitPrelude ->
        case programParts program of {
          Quad datatypes classes instances body ->
            if L.any isMonadClass classes
            then Pair Set.empty program
            else let {
                   methods = Set.fromList compareString (L.concatMap classMethodNames classes)
                 } in
                 let {
                   expressions = Cons body (L.concatMap instanceBodies instances)
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
                              (Set.fromList compareString (Cons "return" (Cons "bind" Nil))))) ||
                      (L.any exprMentionsMonad expressions ||
                       (L.any classMentionsMonad classes || L.any instanceMentionsMonad instances)))
                 } in
                 if needed
                 then Pair (Set.singleton "Monad")
                        (SClassProgram datatypes (Cons monadClass classes)
                           (Cons ioInstance (Cons stInstance instances))
                           body)
                 else Pair Set.empty program
        }
    };
  programParts :: SProgram -> Quad (List DataDecl) (List SClassDecl) (List SInstanceDecl) SExpr;
  programParts program =
    case program of {
      SProgram datatypes body -> Quad datatypes Nil Nil body;
      SClassProgram datatypes classes instances body -> Quad datatypes classes instances body
    };
  isMonadClass :: SClassDecl -> Bool;
  isMonadClass (SClassDecl name parameters superclasses methods) = eqString name "Monad";
  classMethodNames :: SClassDecl -> List String;
  classMethodNames (SClassDecl name parameters superclasses methods) = L.map L.fst methods;
  instanceBodies :: SInstanceDecl -> List SExpr;
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
    SClassDecl "Monad" (Cons (Pair "m" (KArrow Star Star)) Nil) Nil
      (Cons (Pair "return" (forallType "a" (SArrow a ma)))
         (Cons (Pair "bind" (forallType "a" (forallType "b" (SArrow ma (SArrow (SArrow a mb) mb)))))
            Nil));
  forallType :: String -> SType -> SType;
  forallType name body = SForall Flexible name SBottom body;
  ioInstance :: SInstanceDecl;
  ioInstance =
    SInstanceDecl Nil Nil "Monad" (Cons (SCon "IO" Nil) Nil)
      (Cons (Pair "return" (SPrimitive PIOReturn)) (Cons (Pair "bind" (SPrimitive PIOBind)) Nil));
  stInstance :: SInstanceDecl;
  stInstance =
    SInstanceDecl (Cons (Pair "s" Star) Nil) Nil "Monad"
      (Cons (SCon "ST" (Cons (STVar "s") Nil)) Nil)
      (Cons (Pair "return" (SPrimitive PSTReturn)) (Cons (Pair "bind" (SPrimitive PSTBind)) Nil));
  freeNames :: SExpr -> Set String;
  freeNames expression =
    case expression of {
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
          (Set.unions compareString (Cons (freeNames body) (L.map recursiveNames definitions)))
          (Set.fromList compareString (L.map recursiveName definitions));
      SChecked ty value -> freeNames value;
      _ -> Set.empty
    };
  alternativeNames :: SAlternative -> Set String;
  alternativeNames (SAlternative pattern body) =
    Set.difference compareString (freeNames body) (patternNames pattern);
  recursiveNames :: Triple String SAnnotation SExpr -> Set String;
  recursiveNames (Triple name annotation body) = freeNames body;
  recursiveName :: Triple String SAnnotation SExpr -> String;
  recursiveName (Triple name annotation body) = name;
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
          (Set.unions compareString (Cons rest (L.map recursiveNames definitions)))
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
  equationMentionsMonad :: Pair (List SPattern) SExpr -> Bool;
  equationMentionsMonad (Pair patterns body) =
    (L.any patternMentionsMonad patterns || exprMentionsMonad body);
  recursiveMentionsMonad :: Triple String SAnnotation SExpr -> Bool;
  recursiveMentionsMonad (Triple name annotation body) =
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
      SAnnotatedPattern name annotation -> annotationMentionsMonad annotation;
      SNestedPattern name patterns -> L.any patternMentionsMonad patterns;
      _ -> False
    };

  -- Standard Haskell class identities are owned by the reserved shared facade.
  -- Legacy Prelude.Monad remains an independent guest API.
  sharedClasses :: List SClassDecl;
  sharedClasses = Cons (SClassDecl "Functor" (Cons (Pair "f" (KArrow Star Star)) Nil) (Nil) (Cons (Pair "fmap" (forallType "a" (forallType "b" (SArrow (SArrow (STVar "a") (STVar "b")) (SArrow (STypeApp (STVar "f") (STVar "a")) (STypeApp (STVar "f") (STVar "b"))))))) (Cons (Pair "<$" (forallType "a" (forallType "b" (SArrow (STVar "a") (SArrow (STypeApp (STVar "f") (STVar "b")) (STypeApp (STVar "f") (STVar "a"))))))) (Nil)))) (Cons (SClassDecl "Applicative" (Cons (Pair "f" (KArrow Star Star)) Nil) (Cons (SPredicate "Functor" (Cons (STVar "f") Nil)) (Nil)) (Cons (Pair "pure" (forallType "a" (SArrow (STVar "a") (STypeApp (STVar "f") (STVar "a"))))) (Cons (Pair "<*>" (forallType "a" (forallType "b" (SArrow (STypeApp (STVar "f") (SArrow (STVar "a") (STVar "b"))) (SArrow (STypeApp (STVar "f") (STVar "a")) (STypeApp (STVar "f") (STVar "b"))))))) (Cons (Pair "liftA2" (forallType "a" (forallType "b" (forallType "c" (SArrow (SArrow (STVar "a") (SArrow (STVar "b") (STVar "c"))) (SArrow (STypeApp (STVar "f") (STVar "a")) (SArrow (STypeApp (STVar "f") (STVar "b")) (STypeApp (STVar "f") (STVar "c"))))))))) (Cons (Pair "*>" (forallType "a" (forallType "b" (SArrow (STypeApp (STVar "f") (STVar "a")) (SArrow (STypeApp (STVar "f") (STVar "b")) (STypeApp (STVar "f") (STVar "b"))))))) (Cons (Pair "<*" (forallType "a" (forallType "b" (SArrow (STypeApp (STVar "f") (STVar "a")) (SArrow (STypeApp (STVar "f") (STVar "b")) (STypeApp (STVar "f") (STVar "a"))))))) (Nil))))))) (Cons (SClassDecl "Monad" (Cons (Pair "f" (KArrow Star Star)) Nil) (Cons (SPredicate "Applicative" (Cons (STVar "f") Nil)) (Nil)) (Cons (Pair ">>=" (forallType "a" (forallType "b" (SArrow (STypeApp (STVar "f") (STVar "a")) (SArrow (SArrow (STVar "a") (STypeApp (STVar "f") (STVar "b"))) (STypeApp (STVar "f") (STVar "b"))))))) (Cons (Pair ">>" (forallType "a" (forallType "b" (SArrow (STypeApp (STVar "f") (STVar "a")) (SArrow (STypeApp (STVar "f") (STVar "b")) (STypeApp (STVar "f") (STVar "b"))))))) (Cons (Pair "return" (forallType "a" (SArrow (STVar "a") (STypeApp (STVar "f") (STVar "a"))))) (Nil))))) (Nil)));
  sharedInstances :: List SInstanceDecl;
  sharedInstances = Cons (SInstanceDecl (Nil) Nil "Functor" (Cons (SCon "IO" Nil) Nil) (Cons (Pair "fmap" (SLam "$f" Nothing (SLam "$xs" Nothing (SApp (SApp (SPrimitive PIOBind) (SVar "$xs")) (SLam "$x" Nothing (SApp (SPrimitive PIOReturn) (SApp (SVar "$f") (SVar "$x")))))))) (Nil))) (Cons (SInstanceDecl (Nil) Nil "Applicative" (Cons (SCon "IO" Nil) Nil) (Cons (Pair "pure" (SPrimitive PIOReturn)) (Cons (Pair "<*>" (SLam "$fs" Nothing (SLam "$xs" Nothing (SApp (SApp (SPrimitive PIOBind) (SVar "$fs")) (SLam "$f" Nothing (SApp (SApp (SPrimitive PIOBind) (SVar "$xs")) (SLam "$x" Nothing (SApp (SPrimitive PIOReturn) (SApp (SVar "$f") (SVar "$x")))))))))) (Nil)))) (Cons (SInstanceDecl (Nil) Nil "Monad" (Cons (SCon "IO" Nil) Nil) (Cons (Pair ">>=" (SPrimitive PIOBind)) (Nil))) (Cons (SInstanceDecl (Cons (Pair "s" Star) Nil) Nil "Functor" (Cons (SCon "ST" (Cons (STVar "s") Nil)) Nil) (Cons (Pair "fmap" (SLam "$f" Nothing (SLam "$xs" Nothing (SApp (SApp (SPrimitive PSTBind) (SVar "$xs")) (SLam "$x" Nothing (SApp (SPrimitive PSTReturn) (SApp (SVar "$f") (SVar "$x")))))))) (Nil))) (Cons (SInstanceDecl (Cons (Pair "s" Star) Nil) Nil "Applicative" (Cons (SCon "ST" (Cons (STVar "s") Nil)) Nil) (Cons (Pair "pure" (SPrimitive PSTReturn)) (Cons (Pair "<*>" (SLam "$fs" Nothing (SLam "$xs" Nothing (SApp (SApp (SPrimitive PSTBind) (SVar "$fs")) (SLam "$f" Nothing (SApp (SApp (SPrimitive PSTBind) (SVar "$xs")) (SLam "$x" Nothing (SApp (SPrimitive PSTReturn) (SApp (SVar "$f") (SVar "$x")))))))))) (Nil)))) (Cons (SInstanceDecl (Cons (Pair "s" Star) Nil) Nil "Monad" (Cons (SCon "ST" (Cons (STVar "s") Nil)) Nil) (Cons (Pair ">>=" (SPrimitive PSTBind)) (Nil))) (Nil))))));
  standardMethodClass :: String -> String;
  standardMethodClass name =
    if L.elem eqString name (Cons "fmap" (Cons "<$" Nil)) then "Functor"
    else if L.elem eqString name (Cons "pure" (Cons "<*>" (Cons "liftA2" (Cons "*>" (Cons "<*" Nil))))) then "Applicative"
    else "Monad";
  providedMethod name methods =
    case L.find (\entry -> eqString name (L.fst entry)) methods of {
      Just entry -> L.snd entry;
      Nothing -> SVar ("$missing builtin method " ++ name)
    };
  hasMethod name methods = L.any (\entry -> eqString name (L.fst entry)) methods;
  addDefault name body methods = if hasMethod name methods then methods else L.append methods (Cons (Pair name body) Nil);
  standardDefaults :: String -> List (Pair String SExpr) -> Either String (List (Pair String SExpr));
  standardDefaults klass methods =
    if eqString klass "Functor" then
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
}
