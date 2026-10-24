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
  require :: Bool -> String -> A.Test Unit;
  require condition message = if condition then A.succeed Unit else fatal message;
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
  one :: forall a. a -> List a;
  one a = Cons a Nil;
  two :: forall a. a -> a -> List a;
  two a b = Cons a (one b);
  three :: forall a. a -> a -> a -> List a;
  three a b c = Cons a (two b c);
  apply2 :: SExpr -> SExpr -> SExpr -> SExpr;
  apply2 f a b = SApp (SApp f a) b;
  pair :: SExpr -> SExpr -> SExpr;
  pair = apply2 (SConstructor "Pair");
  cons :: SExpr -> SExpr -> SExpr;
  cons = apply2 (SConstructor "Cons");
  nil :: SExpr;
  nil = SConstructor "Nil";
  int :: XType;
  int = XCon "Int" Nil;
  bool :: XType;
  bool = XCon "Bool" Nil;
  intType :: SType;
  intType = SCon "Int" Nil;
  boolType :: SType;
  boolType = SCon "Bool" Nil;
  sameExpression :: String -> String -> SExpr -> A.Test Unit;
  sameExpression label source expected =
    do {
      actual <- right (Parser.parseExpr "tuple-list.emlf" source);
      require (Equality.eqExpr actual expected) (label ++ ": unexpected expression AST")
    };
  sameBoundary :: String -> String -> String -> SExpr -> A.Test Unit;
  sameBoundary label delimiter source expected =
    do {
      actual <-
        right
          (Parser.parseLayout False (Parsec.pBefore Parser.expr (Parsec.pToken delimiter))
             "tuple-list-boundary.emlf"
             source);
      require (Equality.eqExpr actual expected)
        (label ++ ": unexpected expression before delimiter")
    };
  sameAnnotation :: String -> String -> SType -> A.Test Unit;
  sameAnnotation label source expected =
    do {
      actual <- right (Parser.parseAnnotation source);
      require (Equality.eqAnnotation actual (SAnnotation Nil expected))
        (label ++ ": unexpected type AST")
    };
  sameFields :: A.Test Unit;
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
        i = Applied "Int" Nil
      };
      let {
        b = Applied "Bool" Nil
      };
      let {
        fields =
          Cons (Applied "List" (one a))
            (Cons (Applied "Pair" (two a i))
               (Cons (Applied "Triple" (three a i b))
                  (one (Applied "Quad" (Cons a (three i b (Applied "String" Nil)))))))
      };
      let {
        expected = DataDecl "Box" (one "a") (one (ConstructorDecl "Box" fields))
      };
      case actual of {
        SourceModule _ _ _ _ (Cons declaration Nil) _ _ _ _ _ ->
          require (Equality.eqDataDecl declaration expected) "tuple/list datatype fields";
        _ -> fatal "missing datatype fields"
      }
    };
  checkResult :: String -> XType -> Compiler.Compilation -> A.Test Unit;
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
  accepted :: String -> String -> XType -> A.Test Unit;
  accepted label source expected =
    do {
      result <- compiled (Compiler.compile "tuple-list.emlf" source);
      checkResult label expected result
    };
  evaluates :: String -> String -> Int -> A.Test Unit;
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
            Pair dataEnvironment _ -> dataEnvironment
          }
      };
      value <- right (Runtime.evaluate environment (Runtime.REnv M.empty) (X.erase term));
      case value of {
        Runtime.RInteger actual ->
          require (actual == expected) (label ++ (": runtime value was " ++ showInt actual));
        _ -> fatal (label ++ ": runtime value was not an integer")
      }
    };
  parseRejected :: String -> String -> A.Test Unit;
  parseRejected label source =
    do {
      case Parser.parseExpr "tuple-list.emlf" source of {
        Left error ->
          require (contains "tuple-list.emlf:" error) (label ++ ": source location missing");
        Right _ -> fatal (label ++ ": malformed syntax accepted")
      }
    };
  parseDiagnostic :: String -> String -> String -> A.Test Unit;
  parseDiagnostic label source expected =
    do {
      case Parser.parseExpr "tuple-list.emlf" source of {
        Left error -> require (contains expected error) (label ++ (": " ++ error));
        Right _ -> fatal (label ++ ": malformed syntax accepted")
      }
    };
  rejected :: String -> String -> Phase -> String -> A.Test Unit;
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
  shapes :: Map String (Pair String String);
  shapes = M.singleton "Shapes" (Pair "Shapes.emlf" ("module Shapes where\n" ++ declarations));
  moduleAccepted :: String -> String -> A.Test Unit;
  moduleAccepted label source =
    do {
      result <- compiled (Compiler.compileModules shapes "Main.emlf" source);
      checkResult label int result
    };
  moduleRejected :: String -> Map String (Pair String String) -> String -> String -> A.Test Unit;
  moduleRejected label libraries source reason =
    do {
      case Compiler.compileModules libraries "Main.emlf" source of {
        Left error ->
          require (contains reason (Compiler.diagnostic error))
            (label ++ (": " ++ Compiler.prettyError error));
        Right _ -> fatal (label ++ ": scope failure accepted")
      }
    };
  -- Stable IDs are frozen from the reviewed authored observation inventory.
  -- Assertion failures are values, so one failed leaf cannot hide later leaves.
  leaf :: String -> String -> String -> A.Test Unit -> C.Case;
  leaf identity label oracle body =
    C.described "language" "integration" (Cons "fixed" Nil) (Cons oracle Nil)
      (Cons "regression" (Cons "conformance" Nil))
      (C.test identity label (Cons "tuple-list" Nil) body);
  withoutPrelude :: A.Test Unit;
  withoutPrelude =
    do {
      result <-
        compiled
          (Compiler.compileWithPrelude NoImplicitPrelude "tuple-list.emlf"
             (declarations ++ "case [42] of {[x] -> x; _ -> 0}"));
      checkResult "list sugar works without implicit Prelude" int result
    };
  parserCases :: List C.Case;
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
    Cons
      (leaf "tuple-list/focused/pair-ast" "pair AST" "fixed-ast"
         (sameExpression "pair AST" "(a,b)" (pair a b)))
      (Cons
         (leaf "tuple-list/focused/triple-ast" "triple AST" "fixed-ast"
            (sameExpression "triple AST" "(a,b,c)" (SApp (apply2 (SConstructor "Triple") a b) c)))
         (Cons
            (leaf "tuple-list/focused/quad-ast" "quad AST" "fixed-ast"
               (sameExpression "quad AST" "(a,b,c,d)"
                  (SApp (SApp (apply2 (SConstructor "Quad") a b) c) d)))
            (Cons
               (leaf "tuple-list/focused/grouping-remains-grouping" "grouping remains grouping"
                  "fixed-ast"
                  (sameExpression "grouping remains grouping" "(a)" a))
               (Cons
                  (leaf "tuple-list/focused/unit-remains-intrinsic" "unit remains intrinsic"
                     "fixed-ast"
                     (sameExpression "unit remains intrinsic" "()" (SConstructor "Unit")))
                  (Cons
                     (leaf "tuple-list/focused/empty-list-ast" "empty list AST" "fixed-ast"
                        (sameExpression "empty list AST" "[]" nil))
                     (Cons
                        (leaf "tuple-list/focused/singleton-list-ast" "singleton list AST"
                           "fixed-ast"
                           (sameExpression "singleton list AST" "[a]" (cons a nil)))
                        (Cons
                           (leaf "tuple-list/focused/nested-list-and-tuple-ast"
                              "nested list and tuple AST"
                              "fixed-ast"
                              (sameExpression "nested list and tuple AST" "[(a,b), (c,d)]"
                                 (cons (pair a b) (cons (pair c d) nil))))
                           (Cons
                              (leaf "tuple-list/focused/cons-associates-right"
                                 "cons associates right"
                                 "fixed-ast"
                                 (sameExpression "cons associates right" "a : b : c"
                                    (cons a (cons b c))))
                              (Cons
                                 (leaf "tuple-list/focused/cons-follows-addition"
                                    "cons follows addition"
                                    "fixed-ast"
                                    (sameExpression "cons follows addition" "a + b : c"
                                       (cons (apply2 (SPrimitive PAddInt) a b) c)))
                                 (Cons
                                    (leaf
                                       "tuple-list/focused/cons-and-concatenation-share-right-precedence"
                                       "cons and concatenation share right precedence"
                                       "fixed-ast"
                                       (sameExpression
                                          "cons and concatenation share right precedence"
                                          "a : b ++ c"
                                          (cons a (apply2 (SPrimitive PConcatString) b c))))
                                    (Cons
                                       (leaf
                                          "tuple-list/focused/concatenation-and-cons-share-right-precedence"
                                          "concatenation and cons share right precedence"
                                          "fixed-ast"
                                          (sameExpression
                                             "concatenation and cons share right precedence"
                                             "a ++ b : c"
                                             (apply2 (SPrimitive PConcatString) a (cons b c))))
                                       (Cons
                                          (leaf
                                             "tuple-list/focused/legacy-annotation-covers-addition"
                                             "legacy annotation covers addition"
                                             "fixed-ast"
                                             (sameExpression "legacy annotation covers addition"
                                                "a + b : Int"
                                                (SAnn (apply2 (SPrimitive PAddInt) a b)
                                                   (SAnnotation Nil intType))))
                                          (Cons
                                             (leaf
                                                "tuple-list/focused/legacy-uppercase-tail-is-an-annotation"
                                                "legacy uppercase tail is an annotation"
                                                "fixed-ast"
                                                (sameExpression
                                                   "legacy uppercase tail is an annotation"
                                                   "a : Nil"
                                                   (SAnn a (SAnnotation Nil (SCon "Nil" Nil)))))
                                             (Cons
                                                (leaf "tuple-list/focused/explicit-annotation"
                                                   "explicit annotation"
                                                   "fixed-ast"
                                                   (sameExpression "explicit annotation"
                                                      "[a] :: [Int]"
                                                      (SAnn (cons a nil)
                                                         (SAnnotation Nil
                                                            (SCon "List" (one intType))))))
                                                (Cons
                                                   (leaf
                                                      "tuple-list/focused/explicit-free-annotation-still-parses"
                                                      "explicit free annotation still parses"
                                                      "fixed-ast"
                                                      (sameExpression
                                                         "explicit free annotation still parses"
                                                         "a :: b"
                                                         (SAnn a (SAnnotation Nil (STVar "b")))))
                                                   (Cons
                                                      (leaf
                                                         "tuple-list/focused/case-tuple-pattern-ast"
                                                         "case tuple pattern AST"
                                                         "fixed-ast"
                                                         (sameExpression "case tuple pattern AST"
                                                            "case a of {(x,y) -> x}"
                                                            (SCase a
                                                               (one
                                                                  (SAlternative
                                                                     (SConstructorPattern "Pair"
                                                                        (two (Just "x") (Just "y")))
                                                                     (SVar "x"))))))
                                                      (Cons
                                                         (leaf
                                                            "tuple-list/focused/case-cons-pattern-ast"
                                                            "case cons pattern AST"
                                                            "fixed-ast"
                                                            (sameExpression "case cons pattern AST"
                                                               "case a of {x : xs -> x}"
                                                               (SCase a
                                                                  (one
                                                                     (SAlternative
                                                                        (SConstructorPattern "Cons"
                                                                           (two (Just "x")
                                                                              (Just "xs")))
                                                                        (SVar "x"))))))
                                                         (Cons
                                                            (leaf
                                                               "tuple-list/focused/empty-pattern-ast"
                                                               "empty pattern AST"
                                                               "fixed-ast"
                                                               (sameExpression "empty pattern AST"
                                                                  "case a of {[] -> b}"
                                                                  (SCase a
                                                                     (one
                                                                        (SAlternative
                                                                           (SConstructorPattern
                                                                              "Nil"
                                                                              Nil)
                                                                           b)))))
                                                            (Cons
                                                               (leaf
                                                                  "tuple-list/focused/list-pattern-ast"
                                                                  "list pattern AST"
                                                                  "fixed-ast"
                                                                  (sameExpression "list pattern AST"
                                                                     "case a of {[x,y] -> x}"
                                                                     (SCase a
                                                                        (one
                                                                           (SAlternative
                                                                              (SNestedPattern "Cons"
                                                                                 (two
                                                                                    (SDefaultPattern
                                                                                       (Just "x"))
                                                                                    (SNestedPattern
                                                                                       "Cons"
                                                                                       (two
                                                                                          (SDefaultPattern
                                                                                             (Just
                                                                                                "y"))
                                                                                          (SConstructorPattern
                                                                                             "Nil"
                                                                                             Nil)))))
                                                                              (SVar "x"))))))
                                                               (Cons
                                                                  (leaf
                                                                     "tuple-list/focused/pair-type-ast"
                                                                     "pair type AST"
                                                                     "fixed-ast"
                                                                     (sameAnnotation "pair type AST"
                                                                        "(Int,Bool)"
                                                                        (SCon "Pair"
                                                                           (two intType boolType))))
                                                                  (Cons
                                                                     (leaf
                                                                        "tuple-list/focused/triple-type-ast"
                                                                        "triple type AST"
                                                                        "fixed-ast"
                                                                        (sameAnnotation
                                                                           "triple type AST"
                                                                           "(Int,Bool,Int)"
                                                                           (SCon "Triple"
                                                                              (three intType
                                                                                 boolType
                                                                                 intType))))
                                                                     (Cons
                                                                        (leaf
                                                                           "tuple-list/focused/list-type-ast"
                                                                           "list type AST"
                                                                           "fixed-ast"
                                                                           (sameAnnotation
                                                                              "list type AST"
                                                                              "[(Int,Bool)]"
                                                                              (SCon "List"
                                                                                 (one
                                                                                    (SCon "Pair"
                                                                                       (two intType
                                                                                          boolType))))))
                                                                        (Cons
                                                                           (leaf
                                                                              "tuple-list/focused/function-tuple-component"
                                                                              "function tuple component"
                                                                              "fixed-ast"
                                                                              (sameAnnotation
                                                                                 "function tuple component"
                                                                                 "(Int -> Bool, [Int])"
                                                                                 (SCon "Pair"
                                                                                    (two
                                                                                       (SArrow
                                                                                          intType
                                                                                          boolType)
                                                                                       (SCon "List"
                                                                                          (one
                                                                                             intType))))))
                                                                           (Cons
                                                                              (leaf
                                                                                 "tuple-list/focused/datatype-field-asts"
                                                                                 "datatype field ASTs"
                                                                                 "fixed-ast"
                                                                                 sameFields)
                                                                              (Cons
                                                                                 (leaf
                                                                                    "tuple-list/focused/malformed-28612c29"
                                                                                    "malformed (a,)"
                                                                                    "parse-rejection"
                                                                                    (parseRejected
                                                                                       "malformed (a,)"
                                                                                       "(a,)"))
                                                                                 (Cons
                                                                                    (leaf
                                                                                       "tuple-list/focused/malformed-282c6129"
                                                                                       "malformed (,a)"
                                                                                       "parse-rejection"
                                                                                       (parseRejected
                                                                                          "malformed (,a)"
                                                                                          "(,a)"))
                                                                                    (Cons
                                                                                       (leaf
                                                                                          "tuple-list/focused/malformed-28612c622c632c642c6529"
                                                                                          "malformed (a,b,c,d,e)"
                                                                                          "parse-rejection"
                                                                                          (parseRejected
                                                                                             "malformed (a,b,c,d,e)"
                                                                                             "(a,b,c,d,e)"))
                                                                                       (Cons
                                                                                          (leaf
                                                                                             "tuple-list/focused/malformed-5b612c5d"
                                                                                             "malformed [a,]"
                                                                                             "parse-rejection"
                                                                                             (parseRejected
                                                                                                "malformed [a,]"
                                                                                                "[a,]"))
                                                                                          (Cons
                                                                                             (leaf
                                                                                                "tuple-list/focused/malformed-5b2c615d"
                                                                                                "malformed [,a]"
                                                                                                "parse-rejection"
                                                                                                (parseRejected
                                                                                                   "malformed [,a]"
                                                                                                   "[,a]"))
                                                                                             (Cons
                                                                                                (leaf
                                                                                                   "tuple-list/focused/malformed-5b61"
                                                                                                   "malformed [a"
                                                                                                   "parse-rejection"
                                                                                                   (parseRejected
                                                                                                      "malformed [a"
                                                                                                      "[a"))
                                                                                                (Cons
                                                                                                   (leaf
                                                                                                      "tuple-list/focused/malformed-5b312e2e335d"
                                                                                                      "malformed [1..3]"
                                                                                                      "parse-rejection"
                                                                                                      (parseRejected
                                                                                                         "malformed [1..3]"
                                                                                                         "[1..3]"))
                                                                                                   (Cons
                                                                                                      (leaf
                                                                                                         "tuple-list/focused/malformed-5b61207c2061203c2d20625d"
                                                                                                         "malformed [a | a <- b]"
                                                                                                         "parse-rejection"
                                                                                                         (parseRejected
                                                                                                            "malformed [a | a <- b]"
                                                                                                            "[a | a <- b]"))
                                                                                                      (Cons
                                                                                                         (leaf
                                                                                                            "tuple-list/focused/malformed-61203a"
                                                                                                            "malformed a :"
                                                                                                            "parse-rejection"
                                                                                                            (parseRejected
                                                                                                               "malformed a :"
                                                                                                               "a :"))
                                                                                                         (Cons
                                                                                                            (leaf
                                                                                                               "tuple-list/focused/ranges-have-a-targeted-diagnostic"
                                                                                                               "ranges have a targeted diagnostic"
                                                                                                               "diagnostic"
                                                                                                               (parseDiagnostic
                                                                                                                  "ranges have a targeted diagnostic"
                                                                                                                  "[1..3]"
                                                                                                                  "list ranges are not supported"))
                                                                                                            (Cons
                                                                                                               (leaf
                                                                                                                  "tuple-list/focused/comprehensions-have-a-targeted-diagnostic"
                                                                                                                  "comprehensions have a targeted diagnostic"
                                                                                                                  "diagnostic"
                                                                                                                  (parseDiagnostic
                                                                                                                     "comprehensions have a targeted diagnostic"
                                                                                                                     "[a | a <- b]"
                                                                                                                     "list comprehensions are not supported"))
                                                                                                               (Cons
                                                                                                                  (leaf
                                                                                                                     "tuple-list/focused/tuple-arity-has-a-targeted-diagnostic"
                                                                                                                     "tuple arity has a targeted diagnostic"
                                                                                                                     "diagnostic"
                                                                                                                     (parseDiagnostic
                                                                                                                        "tuple arity has a targeted diagnostic"
                                                                                                                        "(a,b,c,d,e)"
                                                                                                                        "tuple syntax supports two, three or four components"))
                                                                                                                  (Cons
                                                                                                                     (leaf
                                                                                                                        "tuple-list/focused/malformed-list-retains-exact-source-position"
                                                                                                                        "malformed list retains exact source position"
                                                                                                                        "diagnostic"
                                                                                                                        (parseDiagnostic
                                                                                                                           "malformed list retains exact source position"
                                                                                                                           "[1,\n ]"
                                                                                                                           "tuple-list.emlf:2:2:"))
                                                                                                                     Nil)))))))))))))))))))))))))))))))))))));
  boundaryCases :: List C.Case;
  boundaryCases =
    Cons
      (leaf "tuple-list/focused/colon-annotation-before-bar" "colon annotation before bar"
         "fixed-ast"
         (sameBoundary "colon annotation before bar" "|" "x : Int |"
            (SAnn (SVar "x") (SAnnotation Nil intType))))
      (Cons
         (leaf "tuple-list/focused/colon-annotation-before-equals" "colon annotation before equals"
            "fixed-ast"
            (sameBoundary "colon annotation before equals" "=" "flag : Bool ="
               (SAnn (SVar "flag") (SAnnotation Nil boolType))))
         (Cons
            (leaf "tuple-list/focused/explicit-annotation-before-bar"
               "explicit annotation before bar"
               "fixed-ast"
               (sameBoundary "explicit annotation before bar" "|" "x :: Int |"
                  (SAnn (SVar "x") (SAnnotation Nil intType))))
            (Cons
               (leaf "tuple-list/focused/explicit-annotation-before-equals"
                  "explicit annotation before equals"
                  "fixed-ast"
                  (sameBoundary "explicit annotation before equals" "=" "flag :: Bool ="
                     (SAnn (SVar "flag") (SAnnotation Nil boolType))))
               (Cons
                  (leaf "tuple-list/focused/lowercase-tail-remains-cons-before-bar"
                     "lowercase tail remains cons before bar"
                     "fixed-ast"
                     (sameBoundary "lowercase tail remains cons before bar" "|" "x : xs |"
                        (cons (SVar "x") (SVar "xs"))))
                  (Cons
                     (leaf "tuple-list/focused/empty-tail-remains-cons-before-equals"
                        "empty tail remains cons before equals"
                        "fixed-ast"
                        (sameBoundary "empty tail remains cons before equals" "=" "1 : [] ="
                           (cons (SIntLit 1) nil)))
                     (Cons
                        (leaf "tuple-list/focused/closed-constructor-annotation-before-bar"
                           "closed constructor annotation before bar"
                           "fixed-ast"
                           (sameBoundary "closed constructor annotation before bar" "|" "x : Nil |"
                              (SAnn (SVar "x") (SAnnotation Nil (SCon "Nil" Nil)))))
                        Nil))))));
  checkingCases :: List C.Case;
  checkingCases =
    Cons
      (leaf "tuple-list/focused/pair-inferred-and-independently-checked"
         "pair inferred and independently checked"
         "independent-reference"
         (accepted "pair inferred and independently checked" (declarations ++ "(42,true)")
            (XCon "Pair" (two int bool))))
      (Cons
         (leaf "tuple-list/focused/triple-inferred-and-independently-checked"
            "triple inferred and independently checked"
            "independent-reference"
            (accepted "triple inferred and independently checked" (declarations ++ "(42,true,42)")
               (XCon "Triple" (three int bool int))))
         (Cons
            (leaf "tuple-list/focused/quad-inferred-and-independently-checked"
               "quad inferred and independently checked"
               "independent-reference"
               (accepted "quad inferred and independently checked"
                  (declarations ++ "(42,true,42,true)")
                  (XCon "Quad" (Cons int (three bool int bool)))))
            (Cons
               (leaf "tuple-list/focused/homogeneous-list" "homogeneous list"
                  "independent-reference"
                  (accepted "homogeneous list" (declarations ++ "[40,41,42]")
                     (XCon "List" (one int))))
               (Cons
                  (leaf "tuple-list/focused/empty-list-annotation" "empty list annotation"
                     "independent-reference"
                     (accepted "empty list annotation" (declarations ++ "[] : [Int]")
                        (XCon "List" (one int))))
                  (Cons
                     (leaf "tuple-list/focused/cons-spine" "cons spine" "independent-reference"
                        (accepted "cons spine" (declarations ++ "40 : 41 : [42]")
                           (XCon "List" (one int))))
                     (Cons
                        (leaf "tuple-list/focused/nested-pair-list-patterns"
                           "nested pair/list patterns"
                           "independent-reference"
                           (accepted "nested pair/list patterns"
                              (declarations ++ "case [(40,2)] of {[(x,y)] -> x+y; _ -> 0}")
                              int))
                        (Cons
                           (leaf "tuple-list/focused/equations-and-cons-parameters"
                              "equations and cons parameters"
                              "independent-reference"
                              (accepted "equations and cons parameters"
                                 (declarations ++
                                  "head [] = 0; head (x : xs) = x; main = head [42];")
                                 int))
                           (Cons
                              (leaf "tuple-list/focused/tuple-lambda" "tuple lambda"
                                 "independent-reference"
                                 (accepted "tuple lambda"
                                    (declarations ++ "(\\(x,y) -> x+y) (40,2)")
                                    int))
                              (Cons
                                 (leaf "tuple-list/focused/legacy-annotated-parameter"
                                    "legacy annotated parameter"
                                    "independent-reference"
                                    (accepted "legacy annotated parameter" "(\\(x : Int) -> x+1) 41"
                                       int))
                                 (Cons
                                    (leaf "tuple-list/focused/legacy-grouped-annotated-parameter"
                                       "legacy grouped annotated parameter"
                                       "independent-reference"
                                       (accepted "legacy grouped annotated parameter"
                                          "(\\((x) : Int) -> x+1) 41"
                                          int))
                                    (Cons
                                       (leaf "tuple-list/focused/explicit-annotated-parameter"
                                          "explicit annotated parameter"
                                          "independent-reference"
                                          (accepted "explicit annotated parameter"
                                             "(\\(x :: Int) -> x+1) 41"
                                             int))
                                       (Cons
                                          (leaf
                                             "tuple-list/focused/explicit-grouped-annotated-parameter"
                                             "explicit grouped annotated parameter"
                                             "independent-reference"
                                             (accepted "explicit grouped annotated parameter"
                                                "(\\((x) :: Int) -> x+1) 41"
                                                int))
                                          (Cons
                                             (leaf
                                                "tuple-list/focused/explicit-declaration-signature"
                                                "explicit declaration signature"
                                                "independent-reference"
                                                (accepted "explicit declaration signature"
                                                   (declarations ++
                                                    "head :: [Int] -> Int; head [] = 0; head (x : xs) = x; main = head [42];")
                                                   int))
                                             (Cons
                                                (leaf
                                                   "tuple-list/focused/type-sugar-in-datatype-fields"
                                                   "type sugar in datatype fields"
                                                   "independent-reference"
                                                   (accepted "type sugar in datatype fields"
                                                      (declarations ++
                                                       "data Box = Box [Int] (Int,Int); case Box [42] (40,2) of {Box [x] (y,z) -> x+y+z; _ -> 0}")
                                                      int))
                                                (Cons
                                                   (leaf "tuple-list/focused/do-tuple-pattern"
                                                      "do tuple pattern"
                                                      "independent-reference"
                                                      (accepted "do tuple pattern"
                                                         (declarations ++
                                                          "do {(x,y) <- (return (40,2) :: IO (Int,Int)); return (x+y)}")
                                                         (XCon "IO" (one int))))
                                                   (Cons
                                                      (leaf
                                                         "tuple-list/focused/multiline-list-closes-inner-case-layout"
                                                         "multiline list closes inner case layout"
                                                         "independent-reference"
                                                         (accepted
                                                            "multiline list closes inner case layout"
                                                            (declarations ++
                                                             "\nmain = case [case true of\n  true -> 42\n  false -> 0\n  , 1] of\n  [x,y] -> x+y\n  _ -> 0\n")
                                                            int))
                                                      (Cons
                                                         (leaf
                                                            "tuple-list/focused/multiline-list-and-tuple"
                                                            "multiline list and tuple"
                                                            "independent-reference"
                                                            (accepted "multiline list and tuple"
                                                               (declarations ++
                                                                "\nmain = case [\n (40,\n  2)\n ] of\n [(x,y)] -> x+y\n _ -> 0\n")
                                                               int))
                                                         (Cons
                                                            (leaf
                                                               "tuple-list/focused/list-sugar-works-without-implicit-prelude"
                                                               "list sugar works without implicit Prelude"
                                                               "independent-reference"
                                                               withoutPrelude)
                                                            (Cons
                                                               (leaf
                                                                  "tuple-list/focused/heterogeneous-list"
                                                                  "heterogeneous list"
                                                                  "phase-diagnostic"
                                                                  (rejected "heterogeneous list"
                                                                     (declarations ++ "[42,true]")
                                                                     Inference
                                                                     "type constructor mismatch"))
                                                               (Cons
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
                                                                  (Cons
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
                                                                     (Cons
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
                                                                        (Cons
                                                                           (leaf
                                                                              "tuple-list/focused/missing-tuple-declaration"
                                                                              "missing tuple declaration"
                                                                              "phase-diagnostic"
                                                                              (rejected
                                                                                 "missing tuple declaration"
                                                                                 "(1,2)"
                                                                                 Inference
                                                                                 "unknown data constructor"))
                                                                           (Cons
                                                                              (leaf
                                                                                 "tuple-list/focused/legacy-free-arrow-annotation-stays-rejected"
                                                                                 "legacy free arrow annotation stays rejected"
                                                                                 "phase-diagnostic"
                                                                                 (rejected
                                                                                    "legacy free arrow annotation stays rejected"
                                                                                    "(\\x -> x) : a -> a"
                                                                                    Inference
                                                                                    "unbound annotation type variable"))
                                                                              Nil))))))))))))))))))))))));
  runtimeCases :: List C.Case;
  runtimeCases =
    Cons
      (leaf "tuple-list/focused/tuple-projection" "tuple projection" "independent-reference"
         (accepted "tuple projection" (declarations ++ "case (40,2) of {(x,y) -> x+y}") int))
      (Cons
         (leaf "tuple-list/focused/tuple-projection-runtime" "tuple projection runtime"
            "runtime-value"
            (evaluates "tuple projection" (declarations ++ "case (40,2) of {(x,y) -> x+y}") 42))
         (Cons
            (leaf "tuple-list/focused/list-pattern-result" "list pattern result"
               "independent-reference"
               (accepted "list pattern result"
                  (declarations ++ "case [20,22] of {[x,y] -> x+y; _ -> 0}")
                  int))
            (Cons
               (leaf "tuple-list/focused/list-pattern-result-runtime" "list pattern result runtime"
                  "runtime-value"
                  (evaluates "list pattern result"
                     (declarations ++ "case [20,22] of {[x,y] -> x+y; _ -> 0}")
                     42))
               (Cons
                  (leaf "tuple-list/focused/cons-associativity-result" "cons associativity result"
                     "independent-reference"
                     (accepted "cons associativity result"
                        (declarations ++ "case 20 : 22 : [] of {[x,y] -> x+y; _ -> 0}")
                        int))
                  (Cons
                     (leaf "tuple-list/focused/cons-associativity-result-runtime"
                        "cons associativity result runtime"
                        "runtime-value"
                        (evaluates "cons associativity result"
                           (declarations ++ "case 20 : 22 : [] of {[x,y] -> x+y; _ -> 0}")
                           42))
                     (Cons
                        (leaf "tuple-list/focused/tuple-ignored-field-stays-lazy"
                           "tuple ignored field stays lazy"
                           "independent-reference"
                           (accepted "tuple ignored field stays lazy"
                              (declarations ++
                               "case (42, panic \"tuple field forced\") of {(x,_) -> x}")
                              int))
                        (Cons
                           (leaf "tuple-list/focused/tuple-ignored-field-stays-lazy-runtime"
                              "tuple ignored field stays lazy runtime"
                              "runtime-value"
                              (evaluates "tuple ignored field stays lazy"
                                 (declarations ++
                                  "case (42, panic \"tuple field forced\") of {(x,_) -> x}")
                                 42))
                           (Cons
                              (leaf "tuple-list/focused/list-ignored-head-stays-lazy"
                                 "list ignored head stays lazy"
                                 "independent-reference"
                                 (accepted "list ignored head stays lazy"
                                    (declarations ++
                                     "case [panic \"list head forced\",42] of {[_,x] -> x; _ -> 0}")
                                    int))
                              (Cons
                                 (leaf "tuple-list/focused/list-ignored-head-stays-lazy-runtime"
                                    "list ignored head stays lazy runtime"
                                    "runtime-value"
                                    (evaluates "list ignored head stays lazy"
                                       (declarations ++
                                        "case [panic \"list head forced\",42] of {[_,x] -> x; _ -> 0}")
                                       42))
                                 (Cons
                                    (leaf "tuple-list/focused/cons-ignored-tail-stays-lazy"
                                       "cons ignored tail stays lazy"
                                       "independent-reference"
                                       (accepted "cons ignored tail stays lazy"
                                          (declarations ++
                                           "case 42 : (panic \"list tail forced\") of {x : _ -> x; [] -> 0}")
                                          int))
                                    (Cons
                                       (leaf
                                          "tuple-list/focused/cons-ignored-tail-stays-lazy-runtime"
                                          "cons ignored tail stays lazy runtime"
                                          "runtime-value"
                                          (evaluates "cons ignored tail stays lazy"
                                             (declarations ++
                                              "case 42 : (panic \"list tail forced\") of {x : _ -> x; [] -> 0}")
                                             42))
                                       (Cons
                                          (leaf "tuple-list/focused/typed-recursive-list-traversal"
                                             "typed recursive list traversal"
                                             "independent-reference"
                                             (accepted "typed recursive list traversal"
                                                (declarations ++
                                                 "sum : [Int] -> Int; sum [] = 0; sum (x : xs) = x + sum xs; main = sum [10,12,20];")
                                                int))
                                          (Cons
                                             (leaf
                                                "tuple-list/focused/typed-recursive-list-traversal-runtime"
                                                "typed recursive list traversal runtime"
                                                "runtime-value"
                                                (evaluates "typed recursive list traversal"
                                                   (declarations ++
                                                    "sum : [Int] -> Int; sum [] = 0; sum (x : xs) = x + sum xs; main = sum [10,12,20];")
                                                   42))
                                             Nil)))))))))))));
  scopeCases :: List C.Case;
  scopeCases =
    let {
      ambiguous =
        M.insert compareString "Other"
          (Pair "Other.emlf" "module Other where\ndata Pair a b = Pair a b\n")
          shapes
    } in
    Cons
      (leaf "tuple-list/focused/imported-ordinary-constructors" "imported ordinary constructors"
         "independent-reference"
         (moduleAccepted "imported ordinary constructors"
            "module Main where\nimport Shapes\nmain = case [(40,2)] of {[(x,y)] -> x+y; _ -> 0}\n"))
      (Cons
         (leaf "tuple-list/focused/qualified-explicit-constructors-interoperate"
            "qualified explicit constructors interoperate"
            "independent-reference"
            (moduleAccepted "qualified explicit constructors interoperate"
               "module Main where\nimport Shapes\nmain = case Shapes.Cons (Shapes.Pair 40 2) Shapes.Nil of {[(x,y)] -> x+y; _ -> 0}\n"))
         (Cons
            (leaf "tuple-list/focused/qualified-only-import-does-not-supply-sugar-names"
               "qualified-only import does not supply sugar names"
               "diagnostic"
               (moduleRejected "qualified-only import does not supply sugar names" shapes
                  "module Main where\nimport qualified Shapes\nmain = []\n"
                  "not in scope: Nil"))
            (Cons
               (leaf "tuple-list/focused/hidden-constructor-stays-hidden"
                  "hidden constructor stays hidden"
                  "diagnostic"
                  (moduleRejected "hidden constructor stays hidden" shapes
                     "module Main where\nimport Shapes hiding (List(Nil))\nmain = []\n"
                     "not in scope: Nil"))
               (Cons
                  (leaf "tuple-list/focused/abstract-tuple-import-stays-abstract"
                     "abstract tuple import stays abstract"
                     "diagnostic"
                     (moduleRejected "abstract tuple import stays abstract" shapes
                        "module Main where\nimport Shapes (Pair)\nmain = (1,2)\n"
                        "not in scope: Pair"))
                  (Cons
                     (leaf "tuple-list/focused/ambiguous-tuple-constructor-stays-ambiguous"
                        "ambiguous tuple constructor stays ambiguous"
                        "diagnostic"
                        (moduleRejected "ambiguous tuple constructor stays ambiguous" ambiguous
                           "module Main where\nimport Shapes\nimport Other\nmain = (1,2)\n"
                           "ambiguous name Pair"))
                     Nil)))));
  cases :: List C.Case;
  cases =
    S.concat
      (Cons parserCases
         (Cons boundaryCases (Cons checkingCases (Cons runtimeCases (Cons scopeCases Nil)))))
}
