-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.TupleListLegacy where {
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
  -- Keep the harness itself in the released syntax. The strings below exercise
  -- the checkout parser; fixed ASTs and types are independent expectations.
  fatal :: forall a. String -> IO a;
  fatal message =
    do {
      putErr ("Tuple/list failure: " ++ (message ++ "\n"));
      exitWith 1
    };
  require :: Bool -> String -> IO ();
  require condition message = if condition then ioReturn () else fatal message;
  right :: forall a. Either String a -> IO a;
  right result =
    case result of {
      Left error -> fatal error;
      Right value -> ioReturn value
    };
  compiled :: Either CompileError Compiler.Compilation -> IO Compiler.Compilation;
  compiled result =
    case result of {
      Left error -> fatal (Compiler.prettyError error);
      Right value -> ioReturn value
    };
  passed :: String -> IO ();
  passed label = putStrLn ("PASS tuple/list " ++ label);
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
  provenanceProjection :: IO ();
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
        "provenance observer changed an unhandled expression form";
      passed "parser provenance projection"
    };
  sameExpression :: String -> String -> SExpr -> IO ();
  sameExpression label source expected =
    do {
      actual <- right (Parser.parseExpr "tuple-list.emlf" source);
      require (Equality.eqExpr (syntaxShape actual) expected) (label ++ ": unexpected expression AST");
      passed label
    };
  sameBoundary :: String -> String -> String -> SExpr -> IO ();
  sameBoundary label delimiter source expected =
    do {
      actual <-
        right
          (Parser.parseLayout False (Parsec.pBefore Parser.expr (Parsec.pToken delimiter))
             "tuple-list-boundary.emlf"
             source);
      require (Equality.eqExpr (syntaxShape actual) expected)
        (label ++ ": unexpected expression before delimiter");
      passed label
    };
  -- A surrounding parser owns these delimiters; no guards grammar is needed.
  boundaryChecks :: IO ();
  boundaryChecks =
    do {
      sameBoundary "constructor cons before bar" "|" "x : Int |"
        (cons (SVar "x") (SConstructor "Int"));
      sameBoundary "constructor cons before equals" "=" "flag : Bool ="
        (cons (SVar "flag") (SConstructor "Bool"));
      sameBoundary "explicit annotation before bar" "|" "x :: Int |"
        (SAnn (SVar "x") (SAnnotation [] intType));
      sameBoundary "explicit annotation before equals" "=" "flag :: Bool ="
        (SAnn (SVar "flag") (SAnnotation [] boolType));
      sameBoundary "lowercase tail remains cons before bar" "|" "x : xs |"
        (cons (SVar "x") (SVar "xs"));
      sameBoundary "empty tail remains cons before equals" "=" "1 : [] =" (cons (SIntLit 1) nil);
      sameBoundary "custom constructor cons before bar" "|" "x : Nil |"
        (cons (SVar "x") (SConstructor "Nil"))
    };
  sameAnnotation :: String -> String -> SType -> IO ();
  sameAnnotation label source expected =
    do {
      actual <- right (Parser.parseAnnotation source);
      require (Equality.eqAnnotation actual (SAnnotation [] expected))
        (label ++ ": unexpected type AST");
      passed label
    };
  sameFields :: IO ();
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
      };
      passed "datatype field ASTs"
    };
  checkResult :: String -> XType -> Compiler.Compilation -> IO ();
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
        (label ++ ": target round trip changed erasure");
      passed label
    };
  accepted :: String -> String -> XType -> IO ();
  accepted label source expected =
    do {
      result <- compiled (Compiler.compile "tuple-list.emlf" source);
      checkResult label expected result
    };
  evaluates :: String -> String -> Int -> IO ();
  evaluates label source expected =
    do {
      result <- compiled (Compiler.compile "tuple-list.emlf" source);
      checkResult label int result;
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
      };
      passed (label ++ " runtime")
    };
  parseRejected :: String -> String -> IO ();
  parseRejected label source =
    do {
      case Parser.parseExpr "tuple-list.emlf" source of {
        Left error ->
          require (contains "tuple-list.emlf:" error) (label ++ ": source location missing");
        Right _ -> fatal (label ++ ": malformed syntax accepted")
      };
      passed label
    };
  parseDiagnostic :: String -> String -> String -> IO ();
  parseDiagnostic label source expected =
    do {
      case Parser.parseExpr "tuple-list.emlf" source of {
        Left error -> require (contains expected error) (label ++ (": " ++ error));
        Right _ -> fatal (label ++ ": malformed syntax accepted")
      };
      passed label
    };
  rejected :: String -> String -> Phase -> String -> IO ();
  rejected label source phase reason =
    do {
      case Compiler.compile "tuple-list.emlf" source of {
        Left error ->
          require
            (eqString (Compiler.prettyPhase (Compiler.phase error)) (Compiler.prettyPhase phase) &&
             contains reason (Compiler.diagnostic error))
            (label ++ (": " ++ Compiler.prettyError error));
        Right _ -> fatal (label ++ ": invalid program accepted")
      };
      passed label
    };
  declarations :: String;
  declarations =
    "data List a = Nil | Cons a (List a); data Pair a b = Pair a b; data Triple a b c = Triple a b c; data Quad a b c d = Quad a b c d; ";
  -- Independent Haskell tuple identities: n components use n-1 commas.
  -- Neither names nor expected fields come from the parser or compiler result.
  tupleName :: Int -> String;
  tupleName arity = "(" ++ (S.concatStrings (S.replicate (arity - 1) ",") ++ ")");
  tupleSource :: Int -> String -> String;
  tupleSource arity component = "(" ++ (S.intercalate "," (S.replicate arity component) ++ ")");
  tupleArityChecks :: IO ();
  tupleArityChecks = S.mapM_ tupleArityCheck (S.range 2 64);
  tupleArityCheck :: Int -> IO ();
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
      else ioReturn ()
    };
  parserChecks :: IO ();
  parserChecks =
    do {
      let {
        a = SVar "a"
      };
      let {
        b = SVar "b"
      };
      let {
        c = SVar "c"
      };
      let {
        d = SVar "d"
      };
      sameExpression "pair AST" "(a,b)" (pair a b);
      sameExpression "triple AST" "(a,b,c)" (SApp (apply2 (SConstructor "(,,)") a b) c);
      sameExpression "quad AST" "(a,b,c,d)" (SApp (SApp (apply2 (SConstructor "(,,,)") a b) c) d);
      sameExpression "grouping remains grouping" "(a)" a;
      sameExpression "unit remains intrinsic" "()" (SConstructor "()");
      sameExpression "empty list AST" "[]" nil;
      sameExpression "singleton list AST" "[a]" (cons a nil);
      sameExpression "nested list and tuple AST" "[(a,b), (c,d)]"
        (cons (pair a b) (cons (pair c d) nil));
      sameExpression "cons associates right" "a : b : c" (cons a (cons b c));
      sameExpression "cons follows addition" "a + b : c" (cons (apply2 (SPrimitive PAddInt) a b) c);
      sameExpression "cons and concatenation share right precedence" "a : b ++ c"
        (cons a (apply2 (SPrimitive PConcatString) b c));
      sameExpression "concatenation and cons share right precedence" "a ++ b : c"
        (apply2 (SPrimitive PConcatString) a (cons b c));
      sameExpression "legacy annotation covers addition" "a + b :: Int"
        (SAnn (apply2 (SPrimitive PAddInt) a b) (SAnnotation [] intType));
      sameExpression "explicit custom type annotation" "a :: Nil"
        (SAnn a (SAnnotation [] (SCon "Nil" [])));
      sameExpression "explicit annotation" "[a] :: [Int]"
        (SAnn (cons a nil) (SAnnotation [] (SCon "[]" (one intType))));
      sameExpression "explicit free annotation still parses" "a :: b"
        (SAnn a (SAnnotation [] (STVar "b")));
      sameExpression "case tuple pattern AST" "case a of {(x,y) -> x}"
        (SCase a
           (one
              (SAlternative (SConstructorPattern "(,)" (two (Just "x") (Just "y"))) (SVar "x"))));
      sameExpression "case cons pattern AST" "case a of {x : xs -> x}"
        (SCase a
           (one
              (SAlternative (SConstructorPattern ":" (two (Just "x") (Just "xs"))) (SVar "x"))));
      sameExpression "empty pattern AST" "case a of {[] -> b}"
        (SCase a (one (SAlternative (SConstructorPattern "[]" []) b)));
      sameExpression "list pattern AST" "case a of {[x,y] -> x}"
        (SCase a
           (one
              (SAlternative
                 (SNestedPattern ":"
                    (two (SDefaultPattern (Just "x"))
                       (SNestedPattern ":"
                          (two (SDefaultPattern (Just "y")) (SConstructorPattern "[]" [])))))
                 (SVar "x"))));
      sameAnnotation "pair type AST" "(Int,Bool)" (SCon "(,)" (two intType boolType));
      sameAnnotation "triple type AST" "(Int,Bool,Int)"
        (SCon "(,,)" (three intType boolType intType));
      sameAnnotation "list type AST" "[(Int,Bool)]"
        (SCon "[]" (one (SCon "(,)" (two intType boolType))));
      sameAnnotation "function tuple component" "(Int -> Bool, [Int])"
        (SCon "(,)" (two (SArrow intType boolType) (SCon "[]" (one intType))));
      sameFields;
      tupleArityChecks;
      S.mapM_ (\source -> parseRejected ("malformed " ++ source) source)
        ((:) "(a,)"
           ((:) "(,a)"
              ((:) "[a,]"
                    ((:) "[,a]"
                       ((:) "[a" ((:) "[1..3]" ((:) "[a | a <- b]" ((:) "a :" []))))))));
      parseDiagnostic "ranges have a targeted diagnostic" "[1..3]" "list ranges are not supported";
      parseDiagnostic "comprehensions have a targeted diagnostic" "[a | a <- b]"
        "list comprehensions are not supported";
      parseDiagnostic "tuple arity has a targeted diagnostic" (tupleSource 65 "a")
        "tuple arity must be between 2 and 64";
      parseDiagnostic "malformed list retains exact source position" "[1,\n ]"
        "tuple-list.emlf:2:2:"
    };
  checkingChecks :: IO ();
  checkingChecks =
    do {
      accepted "pair inferred and independently checked" (declarations ++ "(42,true)")
        (XCon "(,)" (two int bool));
      accepted "triple inferred and independently checked" (declarations ++ "(42,true,42)")
        (XCon "(,,)" (three int bool int));
      accepted "quad inferred and independently checked" (declarations ++ "(42,true,42,true)")
        (XCon "(,,,)" ((:) int (three bool int bool)));
      accepted "homogeneous list" (declarations ++ "[40,41,42]") (XCon "[]" (one int));
      accepted "empty list annotation" (declarations ++ "[] :: [Int]") (XCon "[]" (one int));
      accepted "cons spine" (declarations ++ "40 : 41 : [42]") (XCon "[]" (one int));
      accepted "nested pair/list patterns"
        (declarations ++ "case [(40,2)] of {[(x,y)] -> x+y; _ -> 0}")
        int;
      accepted "equations and cons parameters"
        (declarations ++ "head [] = 0; head (x : xs) = x; main = head [42];")
        int;
      accepted "tuple lambda" (declarations ++ "(\\(x,y) -> x+y) (40,2)") int;
      accepted "legacy annotated parameter" "(\\(x :: Int) -> x+1) 41" int;
      accepted "legacy grouped annotated parameter" "(\\((x) :: Int) -> x+1) 41" int;
      accepted "explicit annotated parameter" "(\\(x :: Int) -> x+1) 41" int;
      accepted "explicit grouped annotated parameter" "(\\((x) :: Int) -> x+1) 41" int;
      accepted "explicit declaration signature"
        (declarations ++ "head :: [Int] -> Int; head [] = 0; head (x : xs) = x; main = head [42];")
        int;
      accepted "type sugar in datatype fields"
        (declarations ++
         "data Box = Box [Int] (Int,Int); case Box [42] (40,2) of {Box [x] (y,z) -> x+y+z; _ -> 0}")
        int;
      accepted "do tuple pattern"
        (declarations ++ "do {(x,y) <- (return (40,2) :: IO (Int,Int)); return (x+y)}")
        (XCon "IO" (one int));
      accepted "multiline list closes inner case layout"
        (declarations ++
         "\nmain = case [case true of\n  true -> 42\n  false -> 0\n  , 1] of\n  [x,y] -> x+y\n  _ -> 0\n")
        int;
      accepted "multiline list and tuple"
        (declarations ++ "\nmain = case [\n (40,\n  2)\n ] of\n [(x,y)] -> x+y\n _ -> 0\n")
        int;
      withoutPrelude <-
        compiled
          (Compiler.compileWithPrelude NoImplicitPrelude "tuple-list.emlf"
             "case [42] of {[x] -> x; _ -> 0}");
      checkResult "list sugar works without implicit Prelude" int withoutPrelude;
      rejected "heterogeneous list" (declarations ++ "[42,true]") Inference
        "type constructor mismatch";
      rejected "duplicate tuple variable" (declarations ++ "f (x,x) = x; main = f (1,2);") Parsing
        "duplicate function parameter";
      rejected "nonexhaustive cons pattern" (declarations ++ "case [42] of {x : xs -> x}") Inference
        "non-exhaustive";
      rejected "duplicate list pattern variable"
        (declarations ++ "case [1,2] of {[x,x] -> x; _ -> 0}")
        Inference
        "duplicate pattern variable";
      accepted "tuple needs no custom declaration" "(1,2)" (XCon "(,)" (two int int));
      rejected "legacy free arrow annotation stays rejected" "(\\x -> x) : a -> a" Inference
        "unbound annotation type variable"
    };
  runtimeChecks :: IO ();
  runtimeChecks =
    do {
      evaluates "tuple projection" (declarations ++ "case (40,2) of {(x,y) -> x+y}") 42;
      evaluates "list pattern result" (declarations ++ "case [20,22] of {[x,y] -> x+y; _ -> 0}") 42;
      evaluates "cons associativity result"
        (declarations ++ "case 20 : 22 : [] of {[x,y] -> x+y; _ -> 0}")
        42;
      evaluates "tuple ignored field stays lazy"
        (declarations ++ "case (42, panic \"tuple field forced\") of {(x,_) -> x}")
        42;
      evaluates "list ignored head stays lazy"
        (declarations ++ "case [panic \"list head forced\",42] of {[_,x] -> x; _ -> 0}")
        42;
      evaluates "cons ignored tail stays lazy"
        (declarations ++ "case 42 : (panic \"list tail forced\") of {x : _ -> x; [] -> 0}")
        42;
      evaluates "typed recursive list traversal"
        (declarations ++
         "sum : [Int] -> Int; sum [] = 0; sum (x : xs) = x + sum xs; main = sum [10,12,20];")
        42
    };
  shapes :: Map String ((,) String String);
  shapes = M.singleton "Shapes" ((,) "Shapes.emlf" ("module Shapes where\n" ++ declarations));
  moduleAccepted :: String -> String -> IO ();
  moduleAccepted label source =
    do {
      result <- compiled (Compiler.compileModules shapes "Main.emlf" source);
      checkResult label int result
    };
  moduleRejected :: String -> Map String ((,) String String) -> String -> String -> IO ();
  moduleRejected label libraries source reason =
    do {
      case Compiler.compileModules libraries "Main.emlf" source of {
        Left error ->
          require (contains reason (Compiler.diagnostic error))
            (label ++ (": " ++ Compiler.prettyError error));
        Right _ -> fatal (label ++ ": scope failure accepted")
      };
      passed label
    };
  scopeChecks :: IO ();
  scopeChecks =
    do {
      moduleAccepted "imported ordinary constructors"
        "module Main where\nimport Shapes\nmain = case Cons (Pair 40 2) Nil of {Cons (Pair x y) Nil -> x+y; _ -> 0}\n";
      moduleAccepted "qualified explicit constructors interoperate"
        "module Main where\nimport Shapes\nmain = case Shapes.Cons (Shapes.Pair 40 2) Shapes.Nil of {Shapes.Cons (Shapes.Pair x y) Shapes.Nil -> x+y; _ -> 0}\n";
      moduleRejected "qualified-only import does not supply custom Nil" shapes
        "module Main where\nimport qualified Shapes\nmain = Nil\n"
        "not in scope: Nil";
      moduleRejected "hidden constructor stays hidden" shapes
        "module Main where\nimport Shapes hiding (List(Nil))\nmain = Nil\n"
        "not in scope: Nil";
      moduleRejected "abstract tuple import stays abstract" shapes
        "module Main where\nimport Shapes (Pair)\nmain = Pair 1 2\n"
        "not in scope: Pair";
      let {
        ambiguous =
          M.insert compareString "Other"
            ((,) "Other.emlf" "module Other where\ndata Pair a b = Pair a b\n")
            shapes
      };
      moduleRejected "ambiguous tuple constructor stays ambiguous" ambiguous
        "module Main where\nimport Shapes\nimport Other\nmain = Pair 1 2\n"
        "ambiguous name Pair"
    };
  ambiguousShapes :: Map String ((,) String String);
  ambiguousShapes =
    M.insert compareString "Other"
      ((,) "Other.emlf" "module Other where\ndata Pair a b = Pair a b\n") shapes;
  moduleAcceptedWith :: String -> Map String ((,) String String) -> String -> IO ();
  moduleAcceptedWith label libraries source =
    do {
      result <- compiled (Compiler.compileModules libraries "Main.emlf" source);
      checkResult label int result
    };
  moduleRejectedAt :: String -> Map String ((,) String String) -> String -> Phase -> String -> IO ();
  moduleRejectedAt label libraries source phase reason =
    do {
      case Compiler.compileModules libraries "Main.emlf" source of {
        Left error ->
          require
            (eqString (Compiler.prettyPhase (Compiler.phase error)) (Compiler.prettyPhase phase) &&
             contains reason (Compiler.diagnostic error))
            (label ++ (": " ++ Compiler.prettyError error));
        Right _ -> fatal (label ++ ": nominally distinct datatypes accepted")
      };
      passed label
    };
  canonicalChecks :: IO ();
  canonicalChecks =
    do {
      provenanceProjection;
      moduleAcceptedWith "qualified-only import does not affect syntax" shapes
            "module Main where\nimport qualified Shapes\nmain = case [(40,2)] of {[(x,y)] -> x+y; _ -> 0}\n";
      moduleAcceptedWith "hidden custom Nil does not affect syntax" shapes
            "module Main where\nimport Shapes hiding (List(Nil))\nmain = case [(40,2)] of {[(x,y)] -> x+y; _ -> 0}\n";
      moduleAcceptedWith "abstract custom Pair does not affect syntax" shapes
            "module Main where\nimport Shapes (Pair)\nmain = case [(40,2)] of {[(x,y)] -> x+y; _ -> 0}\n";
      moduleAcceptedWith "ambiguous custom Pair does not affect syntax" ambiguousShapes
            "module Main where\nimport Shapes\nimport Other\nmain = case [(40,2)] of {[(x,y)] -> x+y; _ -> 0}\n";
      rejected "standard list is not custom List" (declarations ++ "([] :: List Int)") Inference "type constructor mismatch";
      rejected "custom List is not standard list" (declarations ++ "(Cons 42 Nil :: [Int])") Inference "type constructor mismatch";
      rejected "standard tuple is not custom Pair" (declarations ++ "((40,2) :: Pair Int Int)") Inference "type constructor mismatch";
      rejected "custom Pair is not standard tuple" (declarations ++ "(Pair 40 2 :: (Int,Int))") Inference "type constructor mismatch";
      rejected "standard unit is not custom Unit" ("data Unit = Unit; (() :: Unit)") Inference "type constructor mismatch";
      rejected "custom Unit is not standard unit" ("data Unit = Unit; (Unit :: ())") Inference "type constructor mismatch";
      moduleRejectedAt "qualified custom List rejects standard pattern" shapes
            "module Main where\nimport Shapes\nmain = case Shapes.Cons (Shapes.Pair 40 2) Shapes.Nil of {[(x,y)] -> x+y; _ -> 0}\n" Inference "type constructor mismatch";
      moduleRejectedAt "qualified custom Pair rejects standard pattern" shapes
            "module Main where\nimport Shapes\nmain = case Shapes.Pair 40 2 of {(x,y) -> x+y}\n" Inference "type constructor mismatch";
      accepted "standard unit with custom declaration" "data Unit = Unit; (() :: ())" (XCon "()" []);
      accepted "explicit custom Unit remains available" "data Unit = Unit; (Unit :: Unit)" (XCon "Unit" [])
    };
  main :: IO ();
  main =
    do {
      parserChecks;
      boundaryChecks;
      checkingChecks;
      runtimeChecks;
      scopeChecks;
      canonicalChecks;
      putStrLn "Tuple/list focused checks passed."
    }
}
