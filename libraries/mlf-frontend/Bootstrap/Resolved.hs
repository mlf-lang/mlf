-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Resolved
  (Expr(Global, Local, CallStack, Constructor, Prim, IntLit, DoubleLit, BoolLit, StringLit,
        Lam, App, Let, Ann, Signature, Case, Equations, LetRec, SourceDefinition, CallSite, SharedBind),
   Pattern(..), Class(..), Instance(..), references, exprRefs, patternRefs,
   namedExpr, indexedExpr, projectExpr, namedPattern, indexedPattern, projectPattern,
   namedClass, namedInstance, fileLeaf, fileApplication, fileApplicationPair, fileCallSite) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.IndexVec as V;

  -- Syntax between module resolution and named class/xMLF lowering. Do has
  -- already been desugared. Compiler-generated dictionary forms arise later.
  data Expr d =
    Global (V.Index d) | Local String | CallStack | Constructor String | Prim Primitive |
    IntLit Int | DoubleLit Double | BoolLit Bool | StringLit String |
    Lam String (Maybe SAnnotation) (Expr d) | App (Expr d) (Expr d) |
    Let String (Expr d) (Expr d) | Ann (Expr d) SAnnotation | Signature (Expr d) SAnnotation |
    Case (Expr d) ([] ((,) (Pattern d) (Expr d))) |
    Equations ([] ((,) ([] (Pattern d)) (Expr d))) |
    LetRec ([] ((,,) String RecursiveMode (Expr d))) (Expr d) |
    SourceDefinition (Expr d) | CallSite String SourceSpan (Expr d) |
    SharedBind (Pattern d) (Expr d) (Expr d) (Expr d) (Expr d) | SlotFree SExpr;
  data Pattern d =
    ConstructorPattern String ([] (Maybe String)) | DefaultPattern (Maybe String) |
    NestedPattern String ([] (Pattern d)) | AnnotatedPattern String SAnnotation |
    IntPattern Int | StringPattern String | BoolPattern Bool |
    OverloadedStringPattern SourceString (V.Index d) (V.Index d) |
    AsPattern String (Pattern d) | LazyPattern (Pattern d);
  data Class d = Class String ([] ((,) String Kind)) ([] SPredicate) ([] ((,) (V.Index d) SType));
  data Instance d = Instance ([] ((,) String Kind)) ([] SPredicate) String ([] SType) ([] ((,) (V.Index d) (Expr d)));

  -- File resolution can retain one projection when both operands are
  -- independent of declaration slots. Only these constructors can make
  -- SlotFree. A binding, pattern or global stays on the ordinary route.
  fileLeaf term = case term of {
    Local name -> SlotFree (SVar name); CallStack -> SlotFree (SVar "$MLF.Stack.callStack");
    Constructor name -> SlotFree (SConstructor name); Prim p -> SlotFree (SPrimitive p);
    IntLit n -> SlotFree (SIntLit n); DoubleLit n -> SlotFree (SDoubleLit n);
    BoolLit b -> SlotFree (SBoolLit b); StringLit text -> SlotFree (SStringLit text);
    _ -> term
  };
  fileApplication f a = case f of {
    SlotFree left -> case a of { SlotFree right -> SlotFree (SApp left right); _ -> App f a };
    _ -> App f a
  };
  -- A saturated binary application needs just the outer closed projection.
  -- Preserve the inner App when either of its operands carries a declaration.
  fileApplicationPair f a b = case f of {
    SlotFree operator -> case a of {
      SlotFree first -> let { partial = SApp operator first } in case b of {
        SlotFree second -> SlotFree (SApp partial second); _ -> App (SlotFree partial) b
      };
      _ -> App (App f a) b
    };
    _ -> App (App f a) b
  };
  fileCallSite name span value = case value of {
    SlotFree body -> SlotFree (SCallSite name span body); _ -> CallSite name span value
  };
  -- Only global leaves (including implicit pattern operations) contribute
  -- declaration edges. Thread the tail to avoid copying application spines.
  references :: forall d. Expr d -> [] (V.Index d);
  references term = exprRefs term [];
  exprRefs :: forall d. Expr d -> [] (V.Index d) -> [] (V.Index d);
  exprRefs term rest = case term of {
    SlotFree _ -> rest; Global i -> (:) i rest;
    Local _ -> rest; CallStack -> rest; Constructor _ -> rest; Prim _ -> rest;
    IntLit _ -> rest; DoubleLit _ -> rest; BoolLit _ -> rest; StringLit _ -> rest;
    Lam _ _ body -> exprRefs body rest;
    App a b -> exprRefs a (exprRefs b rest);
    Let _ a b -> exprRefs a (exprRefs b rest);
    Ann a _ -> exprRefs a rest; Signature a _ -> exprRefs a rest;
    Case a arms -> exprRefs a (foldr (\((,) p b) more -> patternRefs p (exprRefs b more)) rest arms);
    Equations rows -> foldr (\((,) ps b) more -> foldr patternRefs (exprRefs b more) ps) rest rows;
    LetRec defs b -> foldr (\((,,) _ _ x) more -> exprRefs x more) (exprRefs b rest) defs;
    SourceDefinition b -> exprRefs b rest; CallSite _ _ b -> exprRefs b rest;
    SharedBind p a b bind fail -> patternRefs p (exprRefs a (exprRefs b (exprRefs bind (exprRefs fail rest))))
  };
  patternRefs :: forall d. Pattern d -> [] (V.Index d) -> [] (V.Index d);
  patternRefs pattern rest = case pattern of {
    OverloadedStringPattern _ eq from -> (:) eq ((:) from rest);
    AsPattern _ p -> patternRefs p rest; LazyPattern p -> patternRefs p rest;
    NestedPattern _ ps -> foldr patternRefs rest ps;
    ConstructorPattern _ _ -> rest; DefaultPattern _ -> rest; AnnotatedPattern _ _ -> rest;
    IntPattern _ -> rest; StringPattern _ -> rest; BoolPattern _ -> rest
  };

  namedExpr :: forall d. (V.Index d -> String) -> Expr d -> SExpr;
  namedExpr name = projectExpr (compose SVar name) (namedPattern name);
  indexedExpr name = projectExpr (\i -> SGlobal i (name i)) (indexedPattern name);
  -- The global and pattern projections are fixed for the entire traversal.
  projectExpr global pattern = let {
    child term = case term of {
      SlotFree value -> value; Global i -> global i; Local n -> SVar n; CallStack -> SVar "$MLF.Stack.callStack";
      Constructor n -> SConstructor n; Prim p -> SPrimitive p;
      IntLit n -> SIntLit n; DoubleLit n -> SDoubleLit n; BoolLit b -> SBoolLit b; StringLit s -> SStringLit s;
      Lam n annotation b -> SLam n annotation (child b);
      App a b -> SApp (child a) (child b); Let n a b -> SLet n (child a) (child b);
      Ann a t -> SAnn (child a) t; Signature a t -> SSignature (child a) t;
      Case a arms -> SCase (child a) (map (\((,) p b) -> SAlternative (pattern p) (child b)) arms);
      Equations rows -> SEquations (map (\((,) ps b) -> (,) (map pattern ps) (child b)) rows);
      LetRec defs b -> SLetRec (map (\((,,) n mode x) -> (,,) n mode (child x)) defs) (child b);
      SourceDefinition b -> SSourceDefinition (child b); CallSite n loc b -> SCallSite n loc (child b);
      SharedBind p a b bind fail -> SSharedBind (pattern p) (child a) (child b) (child bind) (child fail)
    }
  } in child;
  namedPattern :: forall d. (V.Index d -> String) -> Pattern d -> SPattern;
  namedPattern name = projectPattern (\text eq from -> SOverloadedStringPattern text (name eq) (name from));
  indexedPattern name = projectPattern (\text eq from -> SIndexedStringPattern text (DeclRef eq (name eq)) (DeclRef from (name from)));
  projectPattern overloaded pattern = case pattern of {
    OverloadedStringPattern text eq from -> overloaded text eq from;
    AsPattern n p -> SAsPattern n (projectPattern overloaded p); LazyPattern p -> SLazyPattern (projectPattern overloaded p);
    NestedPattern n ps -> SNestedPattern n (map (projectPattern overloaded) ps);
    ConstructorPattern n fields -> SConstructorPattern n fields; DefaultPattern n -> SDefaultPattern n;
    AnnotatedPattern n a -> SAnnotatedPattern n a; IntPattern n -> SIntPattern n;
    StringPattern s -> SStringPattern s; BoolPattern b -> SBoolPattern b
  };
  namedClass name (Class n parameters supers methods) =
    SClassDecl n parameters supers (map (\((,) i ty) -> (,) (name i) ty) methods);
  namedInstance name (Instance vars context n ty methods) = SInstanceDecl vars context n ty
    (map (\((,) i body) -> (,) (name i) (namedExpr name body)) methods)
}
