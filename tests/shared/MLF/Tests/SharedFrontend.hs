-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Tests.SharedFrontend where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Parser as P;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.Lexer as L;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Compiler as C;
  import qualified Bootstrap.Constraint as Constraint;
  import qualified Bootstrap.X.Parser as XP;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Type as XT;
  import qualified Bootstrap.Runtime as Runtime;
  import qualified Bootstrap.X.Syntax as X;
  prologue :: String;
  prologue =
    "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\n";
  source body = (prologue ++ ("module Example where\nimport MLF.Primitive\n" ++ (body ++ "\n")));
  parse body = P.parseModule "Example.hs" (source body);
  accept body = isRight (parse body);
  reject body = isLeft (parse body);
  linked text =
    case parse text of {
      Left _ -> False;
      Right m -> isRight (Modules.linkModules ImplicitPrelude (Cons m Nil))
    };
  forwardScope =
    case parse "main = let { x = y; y = 3 } in x" of {
      Right (SourceModule _ _ _ _ _ _ _ (Cons (Triple _ _ (SLet y (SIntLit 3) (SLet x (SVar reference) (SVar result)))) Nil) _ SharedHaskellV1) ->
        (eqString y "y" && (eqString x "x" && (eqString reference "y" && eqString result "x")));
      _ -> False
    };
  fixedDo =
    case parse "main = let { bind = 7 } in do { value <- ioReturn 3; ioReturn value }" of {
      Right (SourceModule _ _ _ _ _ _ _ (Cons (Triple _ _ expression) Nil) _ _) ->
        elem eqString "$MLF.Primitive.>>=" (Surface.freeNames expression);
      _ -> False
    };
  legacyScope =
    case P.parseExpr "legacy.hs" "let x = 1 in let x = x + 1 in x" of {
      Right (SLet _ (SIntLit 1) (SLet _ _ _)) -> True;
      _ -> False
    };
  mixedGraph =
    case parse "main = Support.answer" of {
      Left _ -> False;
      Right (SourceModule path name exports _ ds cs instances values body syntax) ->
        let {
          root =
            SourceModule path name exports
              (Cons (Import "MLF.Primitive" False Nothing Everything)
                 (Cons (Import "Support" False Nothing Everything) Nil))
              ds
              cs
              instances
              values
              body
              syntax
        } in
        case Modules.loadModuleMap
               (M.singleton "Support"
                  (Pair "Support.emlf"
                     "module Support where\nanswer = let x = 1 in let x = x + 1 in x\n"))
               root of {
          Left _ -> False;
          Right graph ->
            ((length graph == 2) && isRight (Modules.linkModules ImplicitPrelude graph))
        }
    };
  importedHook =
    case parse "main = 1" of {
      Left _ -> False;
      Right (SourceModule path name exports _ ds cs instances values body syntax) ->
        let {
          root =
            SourceModule path name exports
              (Cons (Import "MLF.Primitive" False Nothing Everything)
                 (Cons (Import "Bad" False Nothing Everything) Nil))
              ds
              cs
              instances
              values
              body
              syntax
        } in
        case P.parseModule "Bad.emlf" "module Bad where\nfromInteger x = x\n" of {
          Left _ -> False;
          Right bad -> isRight (Modules.linkModules ImplicitPrelude (Cons bad (Cons root Nil)))
        }
    };
  linkRaw text = case P.parseModule "Example.hs" (prologue ++ text) of { Left _ -> False; Right m -> isRight (Modules.linkModules ImplicitPrelude (Cons m Nil)) };

  evaluated :: String -> Either String Runtime.RValue;
  evaluated body = do {
    result <- mapLeft C.prettyError (C.compile "Example.hs" (source body));
    let { term = C.compiledTerm result };
    state <- Runtime.prepare False term;
    Runtime.evaluate (fst state) (Runtime.REnv M.empty) (X.erase term)
  };
  evaluatesInt :: String -> Int -> Bool;
  evaluatesInt body expected = case evaluated body of {
    Right (Runtime.RInteger actual) -> actual == expected;
    _ -> False
  };
  failsWith :: String -> String -> Bool;
  failsWith body expected = case evaluated body of { Left actual -> eqString actual expected; Right _ -> False };
  boxFunctor :: String;
  boxFunctor = "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\nunBox (Box x) = x\n";
  boxApplicative :: String;
  boxApplicative = boxFunctor ++ "instance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\n";
  boxMonad :: String;
  boxMonad = boxApplicative ++ "instance Monad Box where { (>>=) (Box x) f = f x }\n";
  check :: String -> Bool -> IO Unit;
  check name okay =
    if okay
    then ioReturn Unit
    else do {
           putErr ("shared frontend failure: " ++ (name ++ "\n"));
           exitWith 1
         };
  captureDefaults :: String;
  captureDefaults = "data Box a = Box a\ndefaultX f (Box x) = Box (f x)\ninstance Functor Box where { fmap = defaultX }\nunBox (Box x) = x\nmain = let { mlfInternal_36_102 = 40 } in unBox (mlfInternal_36_102 <$ Box 2)\n";
  targetRoundTrip term =
    case XP.parseTerm "<target roundtrip>" (Pretty.prettyTerm term) of {
      Left _ -> False;
      Right decoded ->
        case Check.checkClosed term of {
          Left _ -> False;
          Right before -> case Check.checkClosed decoded of {
            Left _ -> False;
            Right after -> XT.alphaEq before after && X.equalErased (X.erase term) (X.erase decoded)
          }
        }
    };
  hintRoundTrip hint =
    let { n = XName 17 (Constraint.targetNameHint hint) } in
    targetRoundTrip (XAbs n (XCon "Int" Nil) (XVarTerm n));
  sourceRoundTrip body =
    case C.compile "Example.hs" (source body) of {
      Left _ -> False;
      Right compiled -> targetRoundTrip (C.compiledTerm compiled)
    };
  builtinRoundTrip =
    case Artifact.builtinPrelude of {
      Left _ -> False;
      Right object ->
        let { encodedInterface = Artifact.encodeInterface (Artifact.objectInterface object);
              encodedObject = Artifact.encodeObject object } in
        case Artifact.decodeInterface encodedInterface of {
          Left _ -> False;
          Right iface ->
            case Artifact.decodeObject iface encodedObject of {
              Left _ -> False;
              Right decoded ->
                eqString encodedInterface (Artifact.encodeInterface (Artifact.objectInterface decoded)) &&
                eqString encodedObject (Artifact.encodeObject decoded)
            }
        }
    };
  frontendChecks :: IO Unit;
  frontendChecks =
    do {
      check "legacy malformed pragma comment"
        (isRight
           (P.parseModule "Legacy.emlf" "{-# LANGUAGE X, #-}\nmodule Legacy where\nmain = 1\n"));
      check "legacy pragma-shaped ordinary comment"
        (isRight
           (P.parseModule "Legacy.emlf"
              "{-# arbitrary legacy comment -}\nmodule Legacy where\nmain = 1\n"));
      check "shared malformed pragma rejected"
        (isLeft
           (P.parseModule "Example.hs"
              (prologue ++
               "{-# LANGUAGE X, #-}\nmodule Example where\nimport MLF.Primitive\nmain = 1\n")));
      check "module metadata" (accept "main = 42");
      check "forward group scope" forwardScope;
      check "legacy sequential scope" legacyScope;
      check "fixed do identity" fixedDo;
      check "mixed per-file profiles" mixedGraph;
      check "imported hook identity" importedHook;
      check "primitive facade link" (linked "main = do { printInt 42; ioReturn Unit }");
      check "facade implementation host" (linked "main = implementationHost");
      check "ordinary bind binding"
        (case P.parseModule "Example.hs"
                (prologue ++
                 "module Example where\nimport MLF.Primitive hiding (bind)\nbind = 42\nmain = do { ioReturn bind; ioReturn bind }\n") of {
           Left _ -> False;
           Right m -> isRight (Modules.linkModules ImplicitPrelude (Cons m Nil))
         });
      check "closed recursive group"
        (accept "main = let { f :: Int -> Int; f x = g x; g :: Int -> Int; g x = f x } in 1");
      check "unsigned recursive group" (reject "main = let { f x = f x } in 1");
      check "mixed signed cycle"
        (reject "main = let { f :: Int -> Int; f x = g x; g x = f x } in 1");
      check "do let forward scope" (accept "main = do { let { x = y; y = 3 }; ioReturn x }");
      check "refutable do forbidden"
        (reject "main = do { Pair x y <- ioReturn (Pair 1 2); ioReturn x }");
      check "wildcard do bind" (accept "main = do { _ <- ioReturn 1; ioReturn 2 }");
      check "same-indent operator continuation rejected" (reject "main = 1 +\n2");
      check "same-indent RHS rejected" (reject "main =\n1");
      check "indented RHS accepted" (accept "main =\n  1");
      check "explicit separator layout accepted" (accept "a = 1;\nmain = a");
      check "implicit block closed by explicit brace rejected"
        (reject "main = do { ioReturn 1; do\n  ioReturn 2 }");
      check "explicit local braces" (reject "main = let x = 1 in x");
      check "implicit inline do" (reject "main = do ioReturn 1");
      check "implicit inline case" (reject "main = case True of True -> 1; False -> 2");
      check "recursive spelling rejected" (reject "main = let rec { x :: Int; x = x } in 1");
      check "single-colon signature" (reject "main : Int\nmain = 1");
      check "inline signature" (reject "main :: Int = 1");
      check "double-colon kinds" (accept "f :: forall (m :: * -> *) a. m a -> m a\nf x = x");
      check "legacy kind colon rejected" (reject "f :: forall (m : * -> *) a. m a -> m a\nf x = x");
      check "free signature variable" (reject "f :: a -> a\nf x = x");
      check "higher rank arrow" (accept "f :: (forall a. a -> a) -> Int\nf g = g 1");
      check "impredicative argument" (reject "f :: Box (forall a. a -> a)\nf = Box (\\x -> x)");
      check "bounded forall rejected" (reject "f :: forall (a >= Int). a -> a\nf x = x");
      check "rigid forall rejected" (reject "f :: forall (a = Int). a -> a\nf x = x");
      check "existential annotation rejected" (reject "f :: exists a. a -> a\nf x = x");
      check "nested context rejected" (reject "f :: forall a. (Monad IO => IO a) -> IO a\nf x = x");
      check "string patterns rejected" (reject "f \"x\" = 1\nf _ = 2");
      check "typed patterns rejected" (reject "f (x :: Int) = x");
      check "tuple expressions rejected" (reject "main = (1,2)");
      check "unit sugar rejected" (reject "main = ()");
      check "list sugar rejected" (reject "main = [1]");
      check "list-tail rejected" (reject "main = 1 : Nil");
      check "tuple types rejected" (reject "main :: (Int, Int)\nmain = Pair 1 2");
      check "tuple patterns rejected" (reject "f (x,y) = x");
      check "typed negative literal" (accept "main :: Int\nmain = (-1)");
      check "bare negative rejected" (reject "main = -1");
      check "unary plus rejected" (reject "main = +1");
      check "nonfinite floating rejected" (reject "main = 1e999");
      check "malformed numeric adjacency" (reject "main = 1abc");
      check "unicode identifiers rejected" (reject "é = 1");
      check "unicode strings accepted" (accept "main = \"λ\"");
      check "lambda-dot rejected" (reject "main = \\x.x");
      check "compact delimiter-prefix rejected" (reject "main = \\x->-1");
      check "Haskell reserved identifiers" (reject "type = 1");
      check "ordinary contextual identifiers" (accept "pattern x = x\nmain = pattern 1");
      check "ordinary fromInteger binding" (accept "main = let { fromInteger = 1 } in fromInteger");
      check "ordinary negate binding" (accept "main = \\negate -> negate");
      check "ordinary otherwise binding"
        (accept "main = case Unit of { Unit -> \\otherwise -> otherwise }");
      check "ordinary fromString spelling" (accept "main = fromString \"x\"");
      check "qualified ordinary spelling" (accept "main = MLF.Primitive.fromInteger 1");
      check "ordinary ifThenElse use" (linked "main = ifThenElse True 1 2");
      check "otherwise value" (linked "main = otherwise");
      check "guarded equations explicitly excluded" (reject "f x | x == 0 = 1 | otherwise = 2");
      check "partial guard rejected" (reject "f x | x == 0 = 1");
      check "tab rejected" (reject "main =\n\t1");
      check "comment operator ambiguity rejected" (reject "main = 1 --oops");
      check "embedded marker is data" (accept "main = \"-- mlf:syntax unknown\"");
      check "missing marker rejected"
        (isLeft (P.parseModule "Example.hs" "module Example where\nmain = 1\n"));
      check "unknown marker rejected"
        (isLeft
           (P.parseModule "Example.emlf"
              "-- mlf:syntax future-v2\nmodule Example where\nmain = 1\n"));
      check "duplicate marker rejected"
        (isLeft
           (P.parseModule "Example.hs"
              (prologue ++
               "-- mlf:syntax shared-haskell-v1\nmodule Example where\nimport MLF.Primitive\nmain = 1\n")));
      check "missing extensions rejected"
        (isLeft
           (P.parseModule "Example.hs"
              "-- mlf:syntax shared-haskell-v1\nmodule Example where\nimport MLF.Primitive\nmain = 1\n"));
      check "unsupported pragma rejected"
        (isLeft
           (P.parseModule "Example.hs"
              (prologue ++
               "{-# LANGUAGE Strict #-}\nmodule Example where\nimport MLF.Primitive\nmain = 1\n")));
      check "profile mismatch rejected"
        (isLeft (P.parseModuleWithProfile LegacyEmlfV1 "Example.hs" (source "main = 1")));
      check "facade import optional"
        (isRight (P.parseModule "Example.hs" (prologue ++ "module Example where\nmain = 1\n")));
      check "selective facade accepted"
        (isRight
           (P.parseModule "Example.hs"
              (prologue ++ "module Example where\nimport MLF.Primitive (Int)\nmain = 1\n")));
      check "qualified facade accepted"
        (isRight
           (P.parseModule "Example.hs"
              (prologue ++ "module Example where\nimport qualified MLF.Primitive\nmain = 1\n")));
      check "ordinary hook hiding accepted"
        (isRight
           (P.parseModule "Example.hs"
              (prologue ++
               "module Example where\nimport MLF.Primitive hiding (ifThenElse)\nmain = 1\n")));
      check "facade reexport accepted"
        (isRight
           (P.parseModule "Example.hs"
              (prologue ++
               "module Example (module MLF.Primitive) where\nimport MLF.Primitive\nmain = 1\n")));
    check "RebindableSyntax excluded" (isLeft (P.parseModule "Example.hs" (prologue ++ "{-# LANGUAGE RebindableSyntax #-}\nmodule Example where\nmain = 1\n")));
    check "ordinary source True needs scope" (not (linkRaw "module Example where\nmain = True\n"));
    check "ordinary source Unit needs scope" (not (linkRaw "module Example where\nmain = Unit\n"));
    check "ordinary Unit type needs scope" (not (linkRaw "module Example where\nmain :: Unit\nmain = 1\n"));
    check "hidden Bool constructor" (not (linkRaw "module Example where\nimport MLF.Primitive hiding (True)\nmain = True\n"));
    check "qualified canonical operator" (linked "main = 1 MLF.Primitive.+ 2");
    check "operator prefix" (linked "main = (+) 1 2");
    check "ordinary symbolic local prefix" (linked "main = let { (++) x y = subInt x y } in (++) 10 3");
    check "noncanonical infix explicit rejection" (not (linked "main = let { (++) x y = subInt x y } in 10 ++ 3 ++ 1"));
    check "method selective import" (linkRaw "module Example where\nimport MLF.Primitive (IO, Monad((>>=)), ioReturn)\nmain = ioReturn 1 >>= ioReturn\n");
    check "qualified methods visible" (linkRaw "module Example where\nimport qualified MLF.Primitive as P\ndata Box a = Box a\ninstance P.Functor Box where { fmap f (Box x) = Box (f x) }\nmain = Box 1\n");
    check "hidden instance method rejected" (not (linkRaw "module Example where\nimport MLF.Primitive (Functor)\ndata Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\nmain = Box 1\n"));
    check "standard hierarchy defaults" (linked "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nmain = do { Box 1; return 2 }");
    check "standard liftA2 minimum" (linked "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; liftA2 f (Box x) (Box y) = Box (f x y) }\nmain = pure 1");
    check "standard missing minimum rejected" (not (linked "data Box a = Box a\ninstance Functor Box where { (<$) x y = Box x }\nmain = Box 1"));
      check "recursive local infix rejected" (reject "main = let { (+) x y = x + y } in (+) 1 2");
      check "signed recursive local infix rejected" (not (linked "main = let { (+) :: Int -> Int -> Int; (+) x y = x + y } in (+) 1 2"));
      check "qualified operator whitespace rejected" (reject "main = 1 MLF.Primitive . + 2");
      check "legacy Prelude excluded" (isLeft (P.parseModule "Example.hs" (prologue ++ "module Example where\nimport Prelude\nmain = 1\n")));
      check "legacy Prelude identity excluded" (isLeft (P.parseModule "Prelude.hs" (prologue ++ "module Prelude where\nmain = 1\n")));
      check "legacy-only words are ordinary identifiers" (accept "rec = 1\nexists = 2\ntrue = 3\nfalse = 4\nbot = 5\nmain = rec + exists + true + false + bot");
      check "metadata accepts MLF.Primitive" (isRight (Separate.validModuleName "MLF.Primitive"));
      check "metadata accepts Prelude" (isRight (Separate.validModuleName "Prelude"));
      check "metadata accepts Example.Nested" (isRight (Separate.validModuleName "Example.Nested"));
      check "metadata rejects malformed identity 0" (isLeft (Separate.validModuleName ""));
      check "metadata rejects malformed identity 1" (isLeft (Separate.validModuleName "lowercase"));
      check "metadata rejects malformed identity 2" (isLeft (Separate.validModuleName "Example..Nested"));
      check "metadata rejects malformed identity 3" (isLeft (Separate.validModuleName "Example where {}"));
      check "metadata rejects malformed identity 4" (isLeft (Separate.validModuleName " Example"));
      check "metadata rejects malformed identity 5" (isLeft (Separate.validModuleName "Example "));
      check "metadata rejects malformed identity 6" (isLeft (Separate.validModuleName "Example {- comment -}"));
      check "shared builtin source ownership reserved" (isLeft (P.parseModule "Primitive.hs" (prologue ++ "module MLF.Primitive where\nmain = 1\n")));
      check "legacy builtin source ownership reserved" (isLeft (P.parseModule "Primitive.emlf" "module MLF.Primitive where\nmain = 1\n"));
      check "builtin checked artifact round trip" builtinRoundTrip;
      check "unsafe hint roundtrip 0" (hintRoundTrip "$f");
      check "unsafe hint roundtrip 1" (hintRoundTrip "$defaultA");
      check "unsafe hint roundtrip 2" (hintRoundTrip ">>=");
      check "unsafe hint roundtrip 3" (hintRoundTrip "");
      check "unsafe hint roundtrip 4" (hintRoundTrip "_x");
      check "valid hint preserved alpha_2" (eqString (Constraint.targetNameHint "alpha_2") "alpha_2");
      check "valid hint preserved beta'" (eqString (Constraint.targetNameHint "beta'") "beta'");
      check "valid hint preserved λ" (eqString (Constraint.targetNameHint "λ") "λ");
      check "valid hint preserved let" (eqString (Constraint.targetNameHint "let") "let");
      check "valid hint preserved mlfInternal_36_102" (eqString (Constraint.targetNameHint "mlfInternal_36_102") "mlfInternal_36_102");
      check "default and generated-name capture roundtrip" (sourceRoundTrip captureDefaults);

      putStrLn "shared frontend: parser and namespace checks passed"
    };
  nativeFirst :: IO Unit;
  nativeFirst = do {
    check "default and generated-name capture execution" (evaluatesInt captureDefaults 40);
    check "native standard hierarchy inference" (evaluatesInt (boxMonad ++ "main = unBox (do { x <- pure 40; return (x + 2) })") 42);
    check "native Applicative defaults" (evaluatesInt (boxApplicative ++ "main = unBox (liftA2 addInt (Box 30) (Box 12))") 42);
    check "native Applicative liftA2 minimum" (evaluatesInt (boxFunctor ++ "instance Applicative Box where { pure = Box; liftA2 f (Box x) (Box y) = Box (f x y) }\nmain = unBox (Box (addInt 30) <*> Box 12)") 42);
    check "native do preserves overridden sequencing" (failsWith (boxApplicative ++ "instance Monad Box where { (>>=) (Box x) f = f x; (>>) a b = panic \"overridden sequence\" }\nmain = unBox (do { Box 1; Box 2 })") "overridden sequence");
    check "native fmap default partial demand" (failsWith "data Box a = Box a\ninstance Functor Box where { fmap = panic \"fmap bottom\" }\nmain = seq (((<$) 1) :: Box Int -> Box Int) 7" "fmap bottom");
      putStrLn "shared frontend: first native semantics checks passed"
    };
  nativeSecond :: IO Unit;
  nativeSecond = do {
    check "native ap default function demand" (failsWith (boxFunctor ++ "instance Applicative Box where { pure = Box; liftA2 = panic \"liftA2 bottom\" }\nmain = seq ((<*>) :: Box (Int -> Int) -> Box Int -> Box Int) 7") "liftA2 bottom");
    check "native left default function demand" (failsWith (boxFunctor ++ "instance Applicative Box where { pure = Box; liftA2 = panic \"liftA2 bottom\" }\nmain = seq ((<*) :: Box Int -> Box Int -> Box Int) 7") "liftA2 bottom");
    check "native liftA2 default partial demand" (failsWith (boxFunctor ++ "instance Applicative Box where { pure = Box; (<*>) = panic \"ap bottom\" }\nmain = seq (liftA2 addInt (Box 1) :: Box Int -> Box Int) 7") "ap bottom");
    check "native return default function demand" (failsWith (boxFunctor ++ "instance Applicative Box where { pure = panic \"pure bottom\"; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nmain = seq (return :: Int -> Box Int) 7") "pure bottom");
    check "native sequencing default partial WHNF" (evaluatesInt (boxApplicative ++ "instance Monad Box where { (>>=) = panic \"bind bottom\" }\nmain = seq (((>>) (Box 1)) :: Box Int -> Box Int) 7") 7);
      putStrLn "shared frontend: checks passed"
    };

  checkFiles :: Int -> Int -> IO Unit;
  checkFiles i count = if i >= count then putStrLn "shared source files: grammar checks passed" else do {
    file <- getArg i;
    text <- readFile file;
    case P.parseModule file text of {
      Left error -> do { putErr (file ++ (": " ++ (error ++ "\n"))); exitWith 1 };
      Right _ -> checkFiles (i + 1) count
    }
  };
  main :: IO Unit;
  main = do {
    count <- getArgCount;
    if count == 0 then do { frontendChecks; nativeFirst; nativeSecond }
    else do {
      mode <- getArg 0;
      if eqString mode "--frontend" then frontendChecks
      else if eqString mode "--native-first" then nativeFirst
      else if eqString mode "--native-second" then nativeSecond
      else checkFiles 0 count
    }
  }
}
