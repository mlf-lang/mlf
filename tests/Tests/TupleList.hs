-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.TupleList where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Parsec as Parsec;
  import qualified Bootstrap.SourceEquality as Equality;
  import qualified Bootstrap.Compiler as Compiler;
  import qualified Bootstrap.Runtime as Runtime;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Parser as TargetParser;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Tests.IndependentCheck as Independent;
  import qualified Tests.IndependentType as IndependentType;
  import qualified Test.Assert as A;
  import qualified Test.Case as C;
  -- Keep the harness itself in the released syntax. The strings below exercise
  -- the checkout parser; fixed ASTs and types are independent expectations.
  fatal :: forall a. String -> A.Test a;
  fatal message = A.fail ("Tuple/list failure: " ++ message);
  require :: Bool -> String -> A.Test ();
  require condition message = if condition then A.succeed () else fatal message;
  right :: forall a. Either String a -> A.Test a;
  right result =
    case result of {
      Left error -> fatal error;
      Right value -> A.succeed value
    };
  compiled :: Either CompileError Compiler.Compilation -> A.Test Compiler.Compilation;
  compiled result =
    case result of {
      Left error -> fatal (Compiler.prettyError error);
      Right value -> A.succeed value
    };
  contains :: String -> String -> Bool;
  contains needle text = containsAt needle text 0;
  containsAt :: String -> String -> Int -> Bool;
  containsAt needle text offset =
    (((offset + stringLength needle) <= stringLength text) &&
     (eqString needle (stringSlice text offset (stringLength needle)) ||
      containsAt needle text (offset + 1)));
  one :: forall a. a -> [] a;
  one a = (:) a [];
  two :: forall a. a -> a -> [] a;
  two a b = (:) a (one b);
  three :: forall a. a -> a -> a -> [] a;
  three a b c = (:) a (two b c);
  apply2 :: SExpr -> SExpr -> SExpr -> SExpr;
  apply2 f a b = SApp (SApp f a) b;
  pair :: SExpr -> SExpr -> SExpr;
  pair = apply2 (SConstructor "(,)");
  cons :: SExpr -> SExpr -> SExpr;
  cons = apply2 (SConstructor ":");
  nil :: SExpr;
  nil = SConstructor "[]";
  int :: XType;
  int = XCon "Int" [];
  bool :: XType;
  bool = XCon "Bool" [];
  intType :: SType;
  intType = SCon "Int" [];
  boolType :: SType;
  boolType = SCon "Bool" [];
  -- Parser shape observations ignore call-site provenance, not syntax.
  -- Only the expression forms used below are traversed. Other forms remain
  -- unchanged, so a new syntax form cannot silently disappear from the oracle.
  syntaxShape :: SExpr -> SExpr;
  syntaxShape expression =
    case expression of {
      SCallSite _ _ body -> syntaxShape body;
      SApp function argument -> SApp (syntaxShape function) (syntaxShape argument);
      SAnn body annotation -> SAnn (syntaxShape body) annotation;
      SCase value alternatives ->
        SCase (syntaxShape value)
          (S.map (\(SAlternative pattern body) -> SAlternative pattern (syntaxShape body)) alternatives);
      _ -> expression
    };
  provenanceProjection :: A.Test ();
  provenanceProjection =
    do {
      let { location = SourceSpan "probe" "Observer" "observer.emlf" 1 1 1 8 };
      let { pattern = SConstructorPattern "(,)" (two (Just "x") Nothing) };
      let { annotation = SAnnotation [] (SCon "[]" (one intType)) };
      let { located = \function argument selected ty ->
        SCallSite "outer" location
          (SAnn
            (SCallSite "case" location
              (SCase (SApp (SCallSite "function" location function)
                           (SCallSite "argument" location argument))
                (one (SAlternative selected (SCallSite "result" location (SVar "x")))))) ty)
      };
      let { expected =
        SAnn (SCase (SApp (SConstructor "Just") (SVar "argument"))
          (one (SAlternative pattern (SVar "x")))) annotation
      };
      require
        (Equality.eqExpr (syntaxShape (located (SConstructor "Just") (SVar "argument") pattern annotation)) expected)
        "provenance observer changed expression shape";
      require
        (S.not (Equality.eqExpr (syntaxShape (located (SConstructor "Nothing") (SVar "argument") pattern annotation)) expected))
        "provenance observer erased a constructor distinction";
      require
        (S.not (Equality.eqExpr (syntaxShape (located (SVar "argument") (SConstructor "Just") pattern annotation)) expected))
        "provenance observer erased application order";
      require
        (S.not (Equality.eqExpr
          (syntaxShape (located (SConstructor "Just") (SVar "argument")
            (SConstructorPattern "(,)" (two (Just "y") Nothing)) annotation)) expected))
        "provenance observer erased pattern binders";
      require
        (S.not (Equality.eqExpr
          (syntaxShape (located (SConstructor "Just") (SVar "argument") pattern (SAnnotation [] boolType))) expected))
        "provenance observer erased type annotations";
      let { unsupported = SLam "x" Nothing (SCallSite "body" location (SVar "x")) };
      require (Equality.eqExpr (syntaxShape unsupported) unsupported)
        "provenance observer changed an unhandled expression form"
    };
  sameExpression :: String -> String -> SExpr -> A.Test ();
  sameExpression label source expected =
    do {
      actual <- right (Parser.parseExpr "tuple-list.emlf" source);
      require (Equality.eqExpr (syntaxShape actual) expected) (label ++ ": unexpected expression AST")
    };
  sameBoundary :: String -> String -> String -> SExpr -> A.Test ();
  sameBoundary label delimiter source expected =
    do {
      actual <-
        right
          (Parser.parseLayout False (Parsec.pBefore Parser.expr (Parsec.pToken delimiter))
             "tuple-list-boundary.emlf"
             source);
      require (Equality.eqExpr (syntaxShape actual) expected)
        (label ++ ": unexpected expression before delimiter")
    };
  sameAnnotation :: String -> String -> SType -> A.Test ();
  sameAnnotation label source expected =
    do {
      actual <- right (Parser.parseAnnotation source);
      require (Equality.eqAnnotation actual (SAnnotation [] expected))
        (label ++ ": unexpected type AST")
    };
  sameFields :: A.Test ();
  sameFields =
    do {
      actual <-
        right
          (Parser.parseModule "fields.emlf"
             "data Box a = Box [a] (a, Int) (a, Int, Bool) (a, Int, Bool, String); main = 42;");
      let {
        a = Parameter "a"
      };
      let {
        i = Applied "Int" []
      };
      let {
        b = Applied "Bool" []
      };
      let {
        fields =
          (:) (Applied "[]" (one a))
            ((:) (Applied "(,)" (two a i))
               ((:) (Applied "(,,)" (three a i b))
                  (one (Applied "(,,,)" ((:) a (three i b (Applied "String" [])))))))
      };
      let {
        expected = DataDecl "Box" (one "a") (one (ConstructorDecl "Box" fields))
      };
      case actual of {
        SourceModule _ _ _ _ ((:) declaration []) _ _ _ _ _ ->
          require (Equality.eqDataDecl declaration expected) "tuple/list datatype fields";
        _ -> fatal "missing datatype fields"
      }
    };
  checkResult :: String -> XType -> Compiler.Compilation -> A.Test ();
  checkResult label expected result =
    do {
      require (IndependentType.alphaEq (Compiler.inferredType result) expected)
        (label ++ (": inferred " ++ Compiler.sourceType result));
      let {
        original = Compiler.compiledTerm result
      };
      term <- right (TargetParser.parseTerm "tuple-list.xmlf" (Pretty.prettyTerm original));
      current <- right (Check.checkClosed term);
      independent <- right (Independent.checkClosed term);
      require
        (IndependentType.alphaEq current expected && IndependentType.alphaEq independent expected)
        (label ++ ": checked type mismatch");
      require (X.equalErased (X.erase term) (X.erase original))
        (label ++ ": target round trip changed erasure")
    };
  accepted :: String -> String -> XType -> A.Test ();
  accepted label source expected =
    do {
      result <- compiled (Compiler.compile "tuple-list.emlf" source);
      checkResult label expected result
    };
  evaluates :: String -> String -> Int -> A.Test ();
  evaluates label source expected =
    do {
      result <- compiled (Compiler.compile "tuple-list.emlf" source);
      let {
        term = Compiler.compiledTerm result
      };
      prepared <- right (Runtime.prepare False term);
      let {
        environment =
          case prepared of {
            (,) dataEnvironment _ -> dataEnvironment
          }
      };
      value <- right (Runtime.evaluate environment (Runtime.REnv M.empty) (X.erase term));
      case value of {
        Runtime.RInteger actual ->
          require (actual == expected) (label ++ (": runtime value was " ++ showInt actual));
        _ -> fatal (label ++ ": runtime value was not an integer")
      }
    };
  parseRejected :: String -> String -> A.Test ();
  parseRejected label source =
    do {
      case Parser.parseExpr "tuple-list.emlf" source of {
        Left error ->
          require (contains "tuple-list.emlf:" error) (label ++ ": source location missing");
        Right _ -> fatal (label ++ ": malformed syntax accepted")
      }
    };
  parseDiagnostic :: String -> String -> String -> A.Test ();
  parseDiagnostic label source expected =
    do {
      case Parser.parseExpr "tuple-list.emlf" source of {
        Left error -> require (contains expected error) (label ++ (": " ++ error));
        Right _ -> fatal (label ++ ": malformed syntax accepted")
      }
    };
  rejected :: String -> String -> Phase -> String -> A.Test ();
  rejected label source phase reason =
    do {
      case Compiler.compile "tuple-list.emlf" source of {
        Left error ->
          require
            (eqString (Compiler.prettyPhase (Compiler.phase error)) (Compiler.prettyPhase phase) &&
             contains reason (Compiler.diagnostic error))
            (label ++ (": " ++ Compiler.prettyError error));
        Right _ -> fatal (label ++ ": invalid program accepted")
      }
    };
  declarations :: String;
  declarations =
    "data List a = Nil | Cons a (List a); data Pair a b = Pair a b; data Triple a b c = Triple a b c; data Quad a b c d = Quad a b c d; ";
  shapes :: Map String ((,) String String);
  shapes = M.singleton "Shapes" ((,) "Shapes.emlf" ("module Shapes where\n" ++ declarations));
  moduleAccepted :: String -> String -> A.Test ();
  moduleAccepted label source =
    do {
      result <- compiled (Compiler.compileModules shapes "Main.emlf" source);
      checkResult label int result
    };
  moduleRejected :: String -> Map String ((,) String String) -> String -> String -> A.Test ();
  moduleRejected label libraries source reason =
    do {
      case Compiler.compileModules libraries "Main.emlf" source of {
        Left error ->
          require (contains reason (Compiler.diagnostic error))
            (label ++ (": " ++ Compiler.prettyError error));
        Right _ -> fatal (label ++ ": scope failure accepted")
      }
    };
  -- Unchanged contracts retain their reviewed IDs; semantic replacements use new IDs.
  -- Historical observation ledgers remain unchanged.
  -- Assertion failures are values, so one failed leaf cannot hide later leaves.
  leaf :: String -> String -> String -> A.Test () -> C.Case;
  leaf identity label oracle body =
    C.described "language" "integration" ((:) "fixed" []) ((:) oracle [])
      ((:) "regression" ((:) "conformance" []))
      (C.test identity label ((:) "tuple-list" []) body);
  withoutPrelude :: A.Test ();
  withoutPrelude =
    do {
      result <-
        compiled
          (Compiler.compileWithPrelude NoImplicitPrelude "tuple-list.emlf"
             "case [42] of {[x] -> x; _ -> 0}");
      checkResult "list sugar works without implicit Prelude" int result
    };
  -- Independent Haskell tuple identities: n components use n-1 commas.
  -- Neither names nor expected fields come from the parser or compiler result.
  tupleName :: Int -> String;
  tupleName arity = "(" ++ (S.concatStrings (S.replicate (arity - 1) ",") ++ ")");
  tupleSource :: Int -> String -> String;
  tupleSource arity component = "(" ++ (S.intercalate "," (S.replicate arity component) ++ ")");
  tupleArityChecks :: A.Test ();
  tupleArityChecks = S.mapM_ tupleArityCheck (S.range 2 64);
  tupleArityCheck :: Int -> A.Test ();
  tupleArityCheck arity =
    do {
      let { label = "standard tuple arity " ++ showInt arity };
      let { name = tupleName arity };
      let { expression = tupleSource arity "42" };
      let { expected = XCon name (S.replicate arity int) };
      sameExpression (label ++ " expression") expression
        (S.foldl SApp (SConstructor name) (S.replicate arity (SIntLit 42)));
      sameAnnotation (label ++ " type") (tupleSource arity "Int")
        (SCon name (S.replicate arity intType));
      sameExpression (label ++ " pattern")
        ("case value of {" ++ (tupleSource arity "_" ++ " -> 42}"))
        (SCase (SVar "value")
          (one (SAlternative (SConstructorPattern name (S.replicate arity Nothing)) (SIntLit 42))));
      -- Exhaustive parsing is cheap; independently checked targets cover boundaries.
      if arity == 2 || arity == 3 || arity == 15 || arity == 16 || arity == 63 || arity == 64
      then do {
        accepted (label ++ " legacy profile") expression expected;
        accepted (label ++ " shared profile")
          ("-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule TupleArity where { import MLF.Primitive; main = " ++ (expression ++ "; }"))
          expected
      }
      else A.succeed ()
    };
  parserCases :: [] C.Case;
  parserCases =
    let {
      a = SVar "a"
    } in
    let {
      b = SVar "b"
    } in
    let {
      c = SVar "c"
    } in
    let {
      d = SVar "d"
    } in
    (:)
      (leaf "tuple-list/focused/pair-ast" "pair AST" "fixed-ast"
         (sameExpression "pair AST" "(a,b)" (pair a b)))
      ((:)
         (leaf "tuple-list/focused/triple-ast" "triple AST" "fixed-ast"
            (sameExpression "triple AST" "(a,b,c)" (SApp (apply2 (SConstructor "(,,)") a b) c)))
         ((:)
            (leaf "tuple-list/focused/quad-ast" "quad AST" "fixed-ast"
               (sameExpression "quad AST" "(a,b,c,d)"
                  (SApp (SApp (apply2 (SConstructor "(,,,)") a b) c) d)))
            ((:)
               (leaf "tuple-list/focused/grouping-remains-grouping" "grouping remains grouping"
                  "fixed-ast"
                  (sameExpression "grouping remains grouping" "(a)" a))
               ((:)
                  (leaf "tuple-list/focused/unit-remains-intrinsic" "unit remains intrinsic"
                     "fixed-ast"
                     (sameExpression "unit remains intrinsic" "()" (SConstructor "()")))
                  ((:)
                     (leaf "tuple-list/focused/empty-list-ast" "empty list AST" "fixed-ast"
                        (sameExpression "empty list AST" "[]" nil))
                     ((:)
                        (leaf "tuple-list/focused/singleton-list-ast" "singleton list AST"
                           "fixed-ast"
                           (sameExpression "singleton list AST" "[a]" (cons a nil)))
                        ((:)
                           (leaf "tuple-list/focused/nested-list-and-tuple-ast"
                              "nested list and tuple AST"
                              "fixed-ast"
                              (sameExpression "nested list and tuple AST" "[(a,b), (c,d)]"
                                 (cons (pair a b) (cons (pair c d) nil))))
                           ((:)
                              (leaf "tuple-list/focused/cons-associates-right"
                                 "cons associates right"
                                 "fixed-ast"
                                 (sameExpression "cons associates right" "a : b : c"
                                    (cons a (cons b c))))
                              ((:)
                                 (leaf "tuple-list/focused/cons-follows-addition"
                                    "cons follows addition"
                                    "fixed-ast"
                                    (sameExpression "cons follows addition" "a + b : c"
                                       (cons (apply2 (SPrimitive PAddInt) a b) c)))
                                 ((:)
                                    (leaf
                                       "tuple-list/focused/cons-and-concatenation-share-right-precedence"
                                       "cons and concatenation share right precedence"
                                       "fixed-ast"
                                       (sameExpression
                                          "cons and concatenation share right precedence"
                                          "a : b ++ c"
                                          (cons a (apply2 (SPrimitive PConcatString) b c))))
                                    ((:)
                                       (leaf
                                          "tuple-list/focused/concatenation-and-cons-share-right-precedence"
                                          "concatenation and cons share right precedence"
                                          "fixed-ast"
                                          (sameExpression
                                             "concatenation and cons share right precedence"
                                             "a ++ b : c"
                                             (apply2 (SPrimitive PConcatString) a (cons b c))))
                                       ((:)
                                          (leaf
                                             "tuple-list/focused/legacy-annotation-covers-addition"
                                             "legacy annotation covers addition"
                                             "fixed-ast"
                                             (sameExpression "legacy annotation covers addition"
                                                "a + b :: Int"
                                                (SAnn (apply2 (SPrimitive PAddInt) a b)
                                                   (SAnnotation [] intType))))
                                          ((:)
                                             (leaf
                                                "tuple-list/focused/legacy-uppercase-tail-is-an-annotation"
                                                "explicit custom type annotation"
                                                "fixed-ast"
                                                (sameExpression
                                                   "explicit custom type annotation"
                                                   "a :: Nil"
                                                   (SAnn a (SAnnotation [] (SCon "Nil" [])))))
                                             ((:)
                                                (leaf "tuple-list/focused/explicit-annotation"
                                                   "explicit annotation"
                                                   "fixed-ast"
                                                   (sameExpression "explicit annotation"
                                                      "[a] :: [Int]"
                                                      (SAnn (cons a nil)
                                                         (SAnnotation []
                                                            (SCon "[]" (one intType))))))
                                                ((:)
                                                   (leaf
                                                      "tuple-list/focused/explicit-free-annotation-still-parses"
                                                      "explicit free annotation still parses"
                                                      "fixed-ast"
                                                      (sameExpression
                                                         "explicit free annotation still parses"
                                                         "a :: b"
                                                         (SAnn a (SAnnotation [] (STVar "b")))))
                                                   ((:)
                                                      (leaf
                                                         "tuple-list/focused/case-tuple-pattern-ast"
                                                         "case tuple pattern AST"
                                                         "fixed-ast"
                                                         (sameExpression "case tuple pattern AST"
                                                            "case a of {(x,y) -> x}"
                                                            (SCase a
                                                               (one
                                                                  (SAlternative
                                                                     (SConstructorPattern "(,)"
                                                                        (two (Just "x") (Just "y")))
                                                                     (SVar "x"))))))
                                                      ((:)
                                                         (leaf
                                                            "tuple-list/focused/case-cons-pattern-ast"
                                                            "case cons pattern AST"
                                                            "fixed-ast"
                                                            (sameExpression "case cons pattern AST"
                                                               "case a of {x : xs -> x}"
                                                               (SCase a
                                                                  (one
                                                                     (SAlternative
                                                                        (SConstructorPattern ":"
                                                                           (two (Just "x")
                                                                              (Just "xs")))
                                                                        (SVar "x"))))))
                                                         ((:)
                                                            (leaf
                                                               "tuple-list/focused/empty-pattern-ast"
                                                               "empty pattern AST"
                                                               "fixed-ast"
                                                               (sameExpression "empty pattern AST"
                                                                  "case a of {[] -> b}"
                                                                  (SCase a
                                                                     (one
                                                                        (SAlternative
                                                                           (SConstructorPattern "[]"
                                                                              [])
                                                                           b)))))
                                                            ((:)
                                                               (leaf
                                                                  "tuple-list/focused/list-pattern-ast"
                                                                  "list pattern AST"
                                                                  "fixed-ast"
                                                                  (sameExpression "list pattern AST"
                                                                     "case a of {[x,y] -> x}"
                                                                     (SCase a
                                                                        (one
                                                                           (SAlternative
                                                                              (SNestedPattern ":"
                                                                                 (two
                                                                                    (SDefaultPattern
                                                                                       (Just "x"))
                                                                                    (SNestedPattern ":"
                                                                                       (two
                                                                                          (SDefaultPattern
                                                                                             (Just
                                                                                                "y"))
                                                                                          (SConstructorPattern "[]"
                                                                                             [])))))
                                                                              (SVar "x"))))))
                                                               ((:)
                                                                  (leaf
                                                                     "tuple-list/focused/pair-type-ast"
                                                                     "pair type AST"
                                                                     "fixed-ast"
                                                                     (sameAnnotation "pair type AST"
                                                                        "(Int,Bool)"
                                                                        (SCon "(,)"
                                                                           (two intType boolType))))
                                                                  ((:)
                                                                     (leaf
                                                                        "tuple-list/focused/triple-type-ast"
                                                                        "triple type AST"
                                                                        "fixed-ast"
                                                                        (sameAnnotation
                                                                           "triple type AST"
                                                                           "(Int,Bool,Int)"
                                                                           (SCon "(,,)"
                                                                              (three intType
                                                                                 boolType
                                                                                 intType))))
                                                                     ((:)
                                                                        (leaf
                                                                           "tuple-list/focused/list-type-ast"
                                                                           "list type AST"
                                                                           "fixed-ast"
                                                                           (sameAnnotation
                                                                              "list type AST"
                                                                              "[(Int,Bool)]"
                                                                              (SCon "[]"
                                                                                 (one
                                                                                    (SCon "(,)"
                                                                                       (two intType
                                                                                          boolType))))))
                                                                        ((:)
                                                                           (leaf
                                                                              "tuple-list/focused/function-tuple-component"
                                                                              "function tuple component"
                                                                              "fixed-ast"
                                                                              (sameAnnotation
                                                                                 "function tuple component"
                                                                                 "(Int -> Bool, [Int])"
                                                                                 (SCon "(,)"
                                                                                    (two
                                                                                       (SArrow
                                                                                          intType
                                                                                          boolType)
                                                                                       (SCon "[]"
                                                                                          (one
                                                                                             intType))))))
                                                                           ((:)
                                                                              (leaf
                                                                                 "tuple-list/focused/datatype-field-asts"
                                                                                 "datatype field ASTs"
                                                                                 "fixed-ast"
                                                                                 sameFields)
                                                                              ((:)
                                                                                 (leaf
                                                                                    "tuple-list/focused/malformed-28612c29"
                                                                                    "malformed (a,)"
                                                                                    "parse-rejection"
                                                                                    (parseRejected
                                                                                       "malformed (a,)"
                                                                                       "(a,)"))
                                                                                 ((:)
                                                                                    (leaf
                                                                                       "tuple-list/focused/malformed-282c6129"
                                                                                       "malformed (,a)"
                                                                                       "parse-rejection"
                                                                                       (parseRejected
                                                                                          "malformed (,a)"
                                                                                          "(,a)"))
                                                                                    ((:)
                                                                                       (leaf "tuple-list/focused/tuple-arities-2-through-64" "tuple arities 2 through 64"
         "independent-reference"
         (tupleArityChecks))
                                                                                       ((:)
                                                                                          (leaf
                                                                                             "tuple-list/focused/malformed-5b612c5d"
                                                                                             "malformed [a,]"
                                                                                             "parse-rejection"
                                                                                             (parseRejected
                                                                                                "malformed [a,]"
                                                                                                "[a,]"))
                                                                                          ((:)
                                                                                             (leaf
                                                                                                "tuple-list/focused/malformed-5b2c615d"
                                                                                                "malformed [,a]"
                                                                                                "parse-rejection"
                                                                                                (parseRejected
                                                                                                   "malformed [,a]"
                                                                                                   "[,a]"))
                                                                                             ((:)
                                                                                                (leaf
                                                                                                   "tuple-list/focused/malformed-5b61"
                                                                                                   "malformed [a"
                                                                                                   "parse-rejection"
                                                                                                   (parseRejected
                                                                                                      "malformed [a"
                                                                                                      "[a"))
                                                                                                ((:)
                                                                                                   (leaf
                                                                                                      "tuple-list/focused/malformed-5b312e2e335d"
                                                                                                      "malformed [1..3]"
                                                                                                      "parse-rejection"
                                                                                                      (parseRejected
                                                                                                         "malformed [1..3]"
                                                                                                         "[1..3]"))
                                                                                                   ((:)
                                                                                                      (leaf
                                                                                                         "tuple-list/focused/malformed-5b61207c2061203c2d20625d"
                                                                                                         "malformed [a | a <- b]"
                                                                                                         "parse-rejection"
                                                                                                         (parseRejected
                                                                                                            "malformed [a | a <- b]"
                                                                                                            "[a | a <- b]"))
                                                                                                      ((:)
                                                                                                         (leaf
                                                                                                            "tuple-list/focused/malformed-61203a"
                                                                                                            "malformed a :"
                                                                                                            "parse-rejection"
                                                                                                            (parseRejected
                                                                                                               "malformed a :"
                                                                                                               "a :"))
                                                                                                         ((:)
                                                                                                            (leaf
                                                                                                               "tuple-list/focused/ranges-have-a-targeted-diagnostic"
                                                                                                               "ranges have a targeted diagnostic"
                                                                                                               "diagnostic"
                                                                                                               (parseDiagnostic
                                                                                                                  "ranges have a targeted diagnostic"
                                                                                                                  "[1..3]"
                                                                                                                  "list ranges are not supported"))
                                                                                                            ((:)
                                                                                                               (leaf
                                                                                                                  "tuple-list/focused/comprehensions-have-a-targeted-diagnostic"
                                                                                                                  "comprehensions have a targeted diagnostic"
                                                                                                                  "diagnostic"
                                                                                                                  (parseDiagnostic
                                                                                                                     "comprehensions have a targeted diagnostic"
                                                                                                                     "[a | a <- b]"
                                                                                                                     "list comprehensions are not supported"))
                                                                                                               ((:)
                                                                                                                  (leaf
                                                                                                                     "tuple-list/focused/tuple-arity-has-a-targeted-diagnostic"
                                                                                                                     "tuple arity has a targeted diagnostic"
                                                                                                                     "diagnostic"
                                                                                                                     (parseDiagnostic
                                                                                                                        "tuple arity has a targeted diagnostic"
                                                                                                                        (tupleSource 65 "a")
                                                                                                                        "tuple arity must be between 2 and 64"))
                                                                                                                  ((:)
                                                                                                                     (leaf
                                                                                                                        "tuple-list/focused/malformed-list-retains-exact-source-position"
                                                                                                                        "malformed list retains exact source position"
                                                                                                                        "diagnostic"
                                                                                                                        (parseDiagnostic
                                                                                                                           "malformed list retains exact source position"
                                                                                                                           "[1,\n ]"
                                                                                                                           "tuple-list.emlf:2:2:"))
                                                                                                                     [])))))))))))))))))))))))))))))))))))));
  boundaryCases :: [] C.Case;
  boundaryCases =
    (:)
      (leaf "tuple-list/focused/constructor-cons-before-bar" "constructor cons before bar"
         "fixed-ast"
         (sameBoundary "constructor cons before bar" "|" "x : Int |"
            (cons (SVar "x") (SConstructor "Int"))))
      ((:)
         (leaf "tuple-list/focused/constructor-cons-before-equals" "constructor cons before equals"
            "fixed-ast"
            (sameBoundary "constructor cons before equals" "=" "flag : Bool ="
               (cons (SVar "flag") (SConstructor "Bool"))))
         ((:)
            (leaf "tuple-list/focused/explicit-annotation-before-bar"
               "explicit annotation before bar"
               "fixed-ast"
               (sameBoundary "explicit annotation before bar" "|" "x :: Int |"
                  (SAnn (SVar "x") (SAnnotation [] intType))))
            ((:)
               (leaf "tuple-list/focused/explicit-annotation-before-equals"
                  "explicit annotation before equals"
                  "fixed-ast"
                  (sameBoundary "explicit annotation before equals" "=" "flag :: Bool ="
                     (SAnn (SVar "flag") (SAnnotation [] boolType))))
               ((:)
                  (leaf "tuple-list/focused/lowercase-tail-remains-cons-before-bar"
                     "lowercase tail remains cons before bar"
                     "fixed-ast"
                     (sameBoundary "lowercase tail remains cons before bar" "|" "x : xs |"
                        (cons (SVar "x") (SVar "xs"))))
                  ((:)
                     (leaf "tuple-list/focused/empty-tail-remains-cons-before-equals"
                        "empty tail remains cons before equals"
                        "fixed-ast"
                        (sameBoundary "empty tail remains cons before equals" "=" "1 : [] ="
                           (cons (SIntLit 1) nil)))
                     ((:)
                        (leaf "tuple-list/focused/custom-constructor-cons-before-bar"
                           "custom constructor cons before bar"
                           "fixed-ast"
                           (sameBoundary "custom constructor cons before bar" "|" "x : Nil |"
                              (cons (SVar "x") (SConstructor "Nil"))))
                        []))))));
  checkingCases :: [] C.Case;
  checkingCases =
    (:)
      (leaf "tuple-list/focused/pair-inferred-and-independently-checked"
         "pair inferred and independently checked"
         "independent-reference"
         (accepted "pair inferred and independently checked" (declarations ++ "(42,true)")
            (XCon "(,)" (two int bool))))
      ((:)
         (leaf "tuple-list/focused/triple-inferred-and-independently-checked"
            "triple inferred and independently checked"
            "independent-reference"
            (accepted "triple inferred and independently checked" (declarations ++ "(42,true,42)")
               (XCon "(,,)" (three int bool int))))
         ((:)
            (leaf "tuple-list/focused/quad-inferred-and-independently-checked"
               "quad inferred and independently checked"
               "independent-reference"
               (accepted "quad inferred and independently checked"
                  (declarations ++ "(42,true,42,true)")
                  (XCon "(,,,)" ((:) int (three bool int bool)))))
            ((:)
               (leaf "tuple-list/focused/homogeneous-list" "homogeneous list"
                  "independent-reference"
                  (accepted "homogeneous list" (declarations ++ "[40,41,42]")
                     (XCon "[]" (one int))))
               ((:)
                  (leaf "tuple-list/focused/empty-list-annotation" "empty list annotation"
                     "independent-reference"
                     (accepted "empty list annotation" (declarations ++ "[] :: [Int]")
                        (XCon "[]" (one int))))
                  ((:)
                     (leaf "tuple-list/focused/cons-spine" "cons spine" "independent-reference"
                        (accepted "cons spine" (declarations ++ "40 : 41 : [42]")
                           (XCon "[]" (one int))))
                     ((:)
                        (leaf "tuple-list/focused/nested-pair-list-patterns"
                           "nested pair/list patterns"
                           "independent-reference"
                           (accepted "nested pair/list patterns"
                              (declarations ++ "case [(40,2)] of {[(x,y)] -> x+y; _ -> 0}")
                              int))
                        ((:)
                           (leaf "tuple-list/focused/equations-and-cons-parameters"
                              "equations and cons parameters"
                              "independent-reference"
                              (accepted "equations and cons parameters"
                                 (declarations ++
                                  "head [] = 0; head (x : xs) = x; main = head [42];")
                                 int))
                           ((:)
                              (leaf "tuple-list/focused/tuple-lambda" "tuple lambda"
                                 "independent-reference"
                                 (accepted "tuple lambda"
                                    (declarations ++ "(\\(x,y) -> x+y) (40,2)")
                                    int))
                              ((:)
                                 (leaf "tuple-list/focused/legacy-annotated-parameter"
                                    "legacy annotated parameter"
                                    "independent-reference"
                                    (accepted "legacy annotated parameter" "(\\(x :: Int) -> x+1) 41"
                                       int))
                                 ((:)
                                    (leaf "tuple-list/focused/legacy-grouped-annotated-parameter"
                                       "legacy grouped annotated parameter"
                                       "independent-reference"
                                       (accepted "legacy grouped annotated parameter"
                                          "(\\((x) :: Int) -> x+1) 41"
                                          int))
                                    ((:)
                                       (leaf "tuple-list/focused/explicit-annotated-parameter"
                                          "explicit annotated parameter"
                                          "independent-reference"
                                          (accepted "explicit annotated parameter"
                                             "(\\(x :: Int) -> x+1) 41"
                                             int))
                                       ((:)
                                          (leaf
                                             "tuple-list/focused/explicit-grouped-annotated-parameter"
                                             "explicit grouped annotated parameter"
                                             "independent-reference"
                                             (accepted "explicit grouped annotated parameter"
                                                "(\\((x) :: Int) -> x+1) 41"
                                                int))
                                          ((:)
                                             (leaf
                                                "tuple-list/focused/explicit-declaration-signature"
                                                "explicit declaration signature"
                                                "independent-reference"
                                                (accepted "explicit declaration signature"
                                                   (declarations ++
                                                    "head :: [Int] -> Int; head [] = 0; head (x : xs) = x; main = head [42];")
                                                   int))
                                             ((:)
                                                (leaf
                                                   "tuple-list/focused/type-sugar-in-datatype-fields"
                                                   "type sugar in datatype fields"
                                                   "independent-reference"
                                                   (accepted "type sugar in datatype fields"
                                                      (declarations ++
                                                       "data Box = Box [Int] (Int,Int); case Box [42] (40,2) of {Box [x] (y,z) -> x+y+z; _ -> 0}")
                                                      int))
                                                ((:)
                                                   (leaf "tuple-list/focused/do-tuple-pattern"
                                                      "do tuple pattern"
                                                      "independent-reference"
                                                      (accepted "do tuple pattern"
                                                         (declarations ++
                                                          "do {(x,y) <- (return (40,2) :: IO (Int,Int)); return (x+y)}")
                                                         (XCon "IO" (one int))))
                                                   ((:)
                                                      (leaf
                                                         "tuple-list/focused/multiline-list-closes-inner-case-layout"
                                                         "multiline list closes inner case layout"
                                                         "independent-reference"
                                                         (accepted
                                                            "multiline list closes inner case layout"
                                                            (declarations ++
                                                             "\nmain = case [case true of\n  true -> 42\n  false -> 0\n  , 1] of\n  [x,y] -> x+y\n  _ -> 0\n")
                                                            int))
                                                      ((:)
                                                         (leaf
                                                            "tuple-list/focused/multiline-list-and-tuple"
                                                            "multiline list and tuple"
                                                            "independent-reference"
                                                            (accepted "multiline list and tuple"
                                                               (declarations ++
                                                                "\nmain = case [\n (40,\n  2)\n ] of\n [(x,y)] -> x+y\n _ -> 0\n")
                                                               int))
                                                         ((:)
                                                            (leaf
                                                               "tuple-list/focused/list-sugar-works-without-implicit-prelude"
                                                               "list sugar works without implicit Prelude"
                                                               "independent-reference"
                                                               withoutPrelude)
                                                            ((:)
                                                               (leaf
                                                                  "tuple-list/focused/heterogeneous-list"
                                                                  "heterogeneous list"
                                                                  "phase-diagnostic"
                                                                  (rejected "heterogeneous list"
                                                                     (declarations ++ "[42,true]")
                                                                     Inference
                                                                     "type constructor mismatch"))
                                                               ((:)
                                                                  (leaf
                                                                     "tuple-list/focused/duplicate-tuple-variable"
                                                                     "duplicate tuple variable"
                                                                     "phase-diagnostic"
                                                                     (rejected
                                                                        "duplicate tuple variable"
                                                                        (declarations ++
                                                                         "f (x,x) = x; main = f (1,2);")
                                                                        Parsing
                                                                        "duplicate function parameter"))
                                                                  ((:)
                                                                     (leaf
                                                                        "tuple-list/focused/nonexhaustive-cons-pattern"
                                                                        "nonexhaustive cons pattern"
                                                                        "phase-diagnostic"
                                                                        (rejected
                                                                           "nonexhaustive cons pattern"
                                                                           (declarations ++
                                                                            "case [42] of {x : xs -> x}")
                                                                           Inference
                                                                           "non-exhaustive"))
                                                                     ((:)
                                                                        (leaf
                                                                           "tuple-list/focused/duplicate-list-pattern-variable"
                                                                           "duplicate list pattern variable"
                                                                           "phase-diagnostic"
                                                                           (rejected
                                                                              "duplicate list pattern variable"
                                                                              (declarations ++
                                                                               "case [1,2] of {[x,x] -> x; _ -> 0}")
                                                                              Inference
                                                                              "duplicate pattern variable"))
                                                                        ((:)
                                                                           (leaf "tuple-list/focused/tuple-needs-no-custom-declaration" "tuple needs no custom declaration"
         "independent-reference"
         (accepted "tuple needs no custom declaration" "(1,2)" (XCon "(,)" (two int int))))
                                                                           ((:)
                                                                              (leaf
                                                                                 "tuple-list/focused/legacy-free-arrow-annotation-stays-rejected"
                                                                                 "legacy free arrow annotation stays rejected"
                                                                                 "phase-diagnostic"
                                                                                 (rejected
                                                                                    "legacy free arrow annotation stays rejected"
                                                                                    "(\\x -> x) : a -> a"
                                                                                    Inference
                                                                                    "unbound annotation type variable"))
                                                                              []))))))))))))))))))))))));
  runtimeCases :: [] C.Case;
  runtimeCases =
    (:)
      (leaf "tuple-list/focused/tuple-projection" "tuple projection" "independent-reference"
         (accepted "tuple projection" (declarations ++ "case (40,2) of {(x,y) -> x+y}") int))
      ((:)
         (leaf "tuple-list/focused/tuple-projection-runtime" "tuple projection runtime"
            "runtime-value"
            (evaluates "tuple projection" (declarations ++ "case (40,2) of {(x,y) -> x+y}") 42))
         ((:)
            (leaf "tuple-list/focused/list-pattern-result" "list pattern result"
               "independent-reference"
               (accepted "list pattern result"
                  (declarations ++ "case [20,22] of {[x,y] -> x+y; _ -> 0}")
                  int))
            ((:)
               (leaf "tuple-list/focused/list-pattern-result-runtime" "list pattern result runtime"
                  "runtime-value"
                  (evaluates "list pattern result"
                     (declarations ++ "case [20,22] of {[x,y] -> x+y; _ -> 0}")
                     42))
               ((:)
                  (leaf "tuple-list/focused/cons-associativity-result" "cons associativity result"
                     "independent-reference"
                     (accepted "cons associativity result"
                        (declarations ++ "case 20 : 22 : [] of {[x,y] -> x+y; _ -> 0}")
                        int))
                  ((:)
                     (leaf "tuple-list/focused/cons-associativity-result-runtime"
                        "cons associativity result runtime"
                        "runtime-value"
                        (evaluates "cons associativity result"
                           (declarations ++ "case 20 : 22 : [] of {[x,y] -> x+y; _ -> 0}")
                           42))
                     ((:)
                        (leaf "tuple-list/focused/tuple-ignored-field-stays-lazy"
                           "tuple ignored field stays lazy"
                           "independent-reference"
                           (accepted "tuple ignored field stays lazy"
                              (declarations ++
                               "case (42, panic \"tuple field forced\") of {(x,_) -> x}")
                              int))
                        ((:)
                           (leaf "tuple-list/focused/tuple-ignored-field-stays-lazy-runtime"
                              "tuple ignored field stays lazy runtime"
                              "runtime-value"
                              (evaluates "tuple ignored field stays lazy"
                                 (declarations ++
                                  "case (42, panic \"tuple field forced\") of {(x,_) -> x}")
                                 42))
                           ((:)
                              (leaf "tuple-list/focused/list-ignored-head-stays-lazy"
                                 "list ignored head stays lazy"
                                 "independent-reference"
                                 (accepted "list ignored head stays lazy"
                                    (declarations ++
                                     "case [panic \"list head forced\",42] of {[_,x] -> x; _ -> 0}")
                                    int))
                              ((:)
                                 (leaf "tuple-list/focused/list-ignored-head-stays-lazy-runtime"
                                    "list ignored head stays lazy runtime"
                                    "runtime-value"
                                    (evaluates "list ignored head stays lazy"
                                       (declarations ++
                                        "case [panic \"list head forced\",42] of {[_,x] -> x; _ -> 0}")
                                       42))
                                 ((:)
                                    (leaf "tuple-list/focused/cons-ignored-tail-stays-lazy"
                                       "cons ignored tail stays lazy"
                                       "independent-reference"
                                       (accepted "cons ignored tail stays lazy"
                                          (declarations ++
                                           "case 42 : (panic \"list tail forced\") of {x : _ -> x; [] -> 0}")
                                          int))
                                    ((:)
                                       (leaf
                                          "tuple-list/focused/cons-ignored-tail-stays-lazy-runtime"
                                          "cons ignored tail stays lazy runtime"
                                          "runtime-value"
                                          (evaluates "cons ignored tail stays lazy"
                                             (declarations ++
                                              "case 42 : (panic \"list tail forced\") of {x : _ -> x; [] -> 0}")
                                             42))
                                       ((:)
                                          (leaf "tuple-list/focused/typed-recursive-list-traversal"
                                             "typed recursive list traversal"
                                             "independent-reference"
                                             (accepted "typed recursive list traversal"
                                                (declarations ++
                                                 "sum : [Int] -> Int; sum [] = 0; sum (x : xs) = x + sum xs; main = sum [10,12,20];")
                                                int))
                                          ((:)
                                             (leaf
                                                "tuple-list/focused/typed-recursive-list-traversal-runtime"
                                                "typed recursive list traversal runtime"
                                                "runtime-value"
                                                (evaluates "typed recursive list traversal"
                                                   (declarations ++
                                                    "sum : [Int] -> Int; sum [] = 0; sum (x : xs) = x + sum xs; main = sum [10,12,20];")
                                                   42))
                                             [])))))))))))));
  scopeCases :: [] C.Case;
  scopeCases =
    let {
      ambiguous =
        M.insert compareString "Other"
          ((,) "Other.emlf" "module Other where\ndata Pair a b = Pair a b\n")
          shapes
    } in
    (:)
      (leaf "tuple-list/focused/imported-ordinary-constructors" "imported ordinary constructors"
         "independent-reference"
         (moduleAccepted "imported ordinary constructors"
            "module Main where\nimport Shapes\nmain = case Cons (Pair 40 2) Nil of {Cons (Pair x y) Nil -> x+y; _ -> 0}\n"))
      ((:)
         (leaf "tuple-list/focused/qualified-explicit-constructors-interoperate" "qualified explicit constructors interoperate"
         "independent-reference"
         (moduleAccepted "qualified explicit constructors interoperate"
            "module Main where\nimport Shapes\nmain = case Shapes.Cons (Shapes.Pair 40 2) Shapes.Nil of {Shapes.Cons (Shapes.Pair x y) Shapes.Nil -> x+y; _ -> 0}\n"))
         ((:)
            (leaf "tuple-list/focused/qualified-only-import-does-not-supply-sugar-names" "qualified-only import does not supply custom Nil"
         "diagnostic"
         (moduleRejected "qualified-only import does not supply custom Nil" shapes
            "module Main where\nimport qualified Shapes\nmain = Nil\n"
            "not in scope: Nil"))
            ((:)
               (leaf "tuple-list/focused/hidden-constructor-stays-hidden"
                  "hidden constructor stays hidden"
                  "diagnostic"
                  (moduleRejected "hidden constructor stays hidden" shapes
                     "module Main where\nimport Shapes hiding (List(Nil))\nmain = Nil\n"
                     "not in scope: Nil"))
               ((:)
                  (leaf "tuple-list/focused/abstract-tuple-import-stays-abstract"
                     "abstract tuple import stays abstract"
                     "diagnostic"
                     (moduleRejected "abstract tuple import stays abstract" shapes
                        "module Main where\nimport Shapes (Pair)\nmain = Pair 1 2\n"
                        "not in scope: Pair"))
                  ((:)
                     (leaf "tuple-list/focused/ambiguous-tuple-constructor-stays-ambiguous"
                        "ambiguous tuple constructor stays ambiguous"
                        "diagnostic"
                        (moduleRejected "ambiguous tuple constructor stays ambiguous" ambiguous
                           "module Main where\nimport Shapes\nimport Other\nmain = Pair 1 2\n"
                           "ambiguous name Pair"))
                     [])))));
  ambiguousShapes :: Map String ((,) String String);
  ambiguousShapes =
    M.insert compareString "Other"
      ((,) "Other.emlf" "module Other where\ndata Pair a b = Pair a b\n") shapes;
  moduleAcceptedWith :: String -> Map String ((,) String String) -> String -> A.Test ();
  moduleAcceptedWith label libraries source =
    do {
      result <- compiled (Compiler.compileModules libraries "Main.emlf" source);
      checkResult label int result
    };
  moduleRejectedAt :: String -> Map String ((,) String String) -> String -> Phase -> String -> A.Test ();
  moduleRejectedAt label libraries source phase reason =
    do {
      case Compiler.compileModules libraries "Main.emlf" source of {
        Left error ->
          require
            (eqString (Compiler.prettyPhase (Compiler.phase error)) (Compiler.prettyPhase phase) &&
             contains reason (Compiler.diagnostic error))
            (label ++ (": " ++ Compiler.prettyError error));
        Right _ -> fatal (label ++ ": nominally distinct datatypes accepted")
      }
    };
  canonicalCases :: [] C.Case;
  canonicalCases =
    (:) (leaf "tuple-list/focused/parser-provenance-projection" "parser provenance projection"
      "fixed-ast" provenanceProjection) (
    (:) (leaf "tuple-list/focused/qualified-only-import-does-not-affect-syntax" "qualified-only import does not affect syntax"
         "independent-reference"
         (moduleAcceptedWith "qualified-only import does not affect syntax" shapes
            "module Main where\nimport qualified Shapes\nmain = case [(40,2)] of {[(x,y)] -> x+y; _ -> 0}\n")) (
    (:) (leaf "tuple-list/focused/hidden-custom-nil-does-not-affect-syntax" "hidden custom Nil does not affect syntax"
         "independent-reference"
         (moduleAcceptedWith "hidden custom Nil does not affect syntax" shapes
            "module Main where\nimport Shapes hiding (List(Nil))\nmain = case [(40,2)] of {[(x,y)] -> x+y; _ -> 0}\n")) (
    (:) (leaf "tuple-list/focused/abstract-custom-pair-does-not-affect-syntax" "abstract custom Pair does not affect syntax"
         "independent-reference"
         (moduleAcceptedWith "abstract custom Pair does not affect syntax" shapes
            "module Main where\nimport Shapes (Pair)\nmain = case [(40,2)] of {[(x,y)] -> x+y; _ -> 0}\n")) (
    (:) (leaf "tuple-list/focused/ambiguous-custom-pair-does-not-affect-syntax" "ambiguous custom Pair does not affect syntax"
         "independent-reference"
         (moduleAcceptedWith "ambiguous custom Pair does not affect syntax" ambiguousShapes
            "module Main where\nimport Shapes\nimport Other\nmain = case [(40,2)] of {[(x,y)] -> x+y; _ -> 0}\n")) (
    (:) (leaf "tuple-list/focused/standard-list-is-not-custom-list" "standard list is not custom List"
         "phase-diagnostic"
         (rejected "standard list is not custom List" (declarations ++ "([] :: List Int)") Inference "type constructor mismatch")) (
    (:) (leaf "tuple-list/focused/custom-list-is-not-standard-list" "custom List is not standard list"
         "phase-diagnostic"
         (rejected "custom List is not standard list" (declarations ++ "(Cons 42 Nil :: [Int])") Inference "type constructor mismatch")) (
    (:) (leaf "tuple-list/focused/standard-tuple-is-not-custom-pair" "standard tuple is not custom Pair"
         "phase-diagnostic"
         (rejected "standard tuple is not custom Pair" (declarations ++ "((40,2) :: Pair Int Int)") Inference "type constructor mismatch")) (
    (:) (leaf "tuple-list/focused/custom-pair-is-not-standard-tuple" "custom Pair is not standard tuple"
         "phase-diagnostic"
         (rejected "custom Pair is not standard tuple" (declarations ++ "(Pair 40 2 :: (Int,Int))") Inference "type constructor mismatch")) (
    (:) (leaf "tuple-list/focused/standard-unit-is-not-custom-unit" "standard unit is not custom Unit"
         "phase-diagnostic"
         (rejected "standard unit is not custom Unit" ("data Unit = Unit; (() :: Unit)") Inference "type constructor mismatch")) (
    (:) (leaf "tuple-list/focused/custom-unit-is-not-standard-unit" "custom Unit is not standard unit"
         "phase-diagnostic"
         (rejected "custom Unit is not standard unit" ("data Unit = Unit; (Unit :: ())") Inference "type constructor mismatch")) (
    (:) (leaf "tuple-list/focused/qualified-custom-list-rejects-standard-pattern" "qualified custom List rejects standard pattern"
         "phase-diagnostic"
         (moduleRejectedAt "qualified custom List rejects standard pattern" shapes
            "module Main where\nimport Shapes\nmain = case Shapes.Cons (Shapes.Pair 40 2) Shapes.Nil of {[(x,y)] -> x+y; _ -> 0}\n" Inference "type constructor mismatch")) (
    (:) (leaf "tuple-list/focused/qualified-custom-pair-rejects-standard-pattern" "qualified custom Pair rejects standard pattern"
         "phase-diagnostic"
         (moduleRejectedAt "qualified custom Pair rejects standard pattern" shapes
            "module Main where\nimport Shapes\nmain = case Shapes.Pair 40 2 of {(x,y) -> x+y}\n" Inference "type constructor mismatch")) (
    (:) (leaf "tuple-list/focused/standard-unit-with-custom-declaration" "standard unit with custom declaration"
         "independent-reference"
         (accepted "standard unit with custom declaration" "data Unit = Unit; (() :: ())" (XCon "()" []))) (
    (:) (leaf "tuple-list/focused/explicit-custom-unit-remains-available" "explicit custom Unit remains available"
         "independent-reference"
         (accepted "explicit custom Unit remains available" "data Unit = Unit; (Unit :: Unit)" (XCon "Unit" []))) (
      [])))))))))))))));
  cases :: [] C.Case;
  cases =
    S.concat
      ((:) parserCases
         ((:) boundaryCases ((:) checkingCases ((:) runtimeCases ((:) scopeCases ((:) canonicalCases []))))))
}
