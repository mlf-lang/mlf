{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module QualifiedCrateHost where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Compiler as Compiler;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Crate as Crate;
  import qualified Bootstrap.CrateQuery as Query;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Parser as XP;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Tests.IndependentCheck as Independent;
  import qualified Tests.IndependentType as IndependentType;
  -- Read the original fixture constructors from Modules.emlf. This deliberately
  -- does not rewrite their library strings, entry programs or expected types.
  data Fixture = Fixture String (List (Pair String String)) String (Maybe XType) String;
  right :: forall a. Either String a -> IO a;
  right result = case result of {
    Left error -> do { putErr (error ++ "\n"); exitWith 1 };
    Right value -> ioReturn value
  };
  assert :: Bool -> String -> IO Unit;
  assert condition message = right (ensure condition message);
  spine :: SExpr -> List SExpr -> Pair SExpr (List SExpr);
  spine expression arguments = case expression of {
    SApp function argument -> spine function (Cons argument arguments);
    _ -> Pair expression arguments
  };
  atom :: SExpr -> String;
  atom expression = case expression of {
    SVar name -> name; SConstructor name -> name; _ -> ""
  };
  collect :: String -> Int -> SExpr -> List (List SExpr);
  collect constructor arity expression =
    let { here = case spine expression Nil of {
      Pair head args -> if eqString (atom head) constructor && length args == arity
                        then Cons args Nil else Nil
    } } in
    let { children = case expression of {
      SApp a b -> append (collect constructor arity a) (collect constructor arity b);
      SLam _ _ b -> collect constructor arity b;
      SAnn a _ -> collect constructor arity a;
      SLet _ a b -> append (collect constructor arity a) (collect constructor arity b);
      SEquations rows -> concatMap (\(Pair _ rhs) -> collect constructor arity rhs) rows;
      SLetRec definitions body -> append (collect constructor arity body)
        (concatMap (\(Triple _ _ rhs) -> collect constructor arity rhs) definitions);
      _ -> Nil
    } } in append here children;
  string :: SExpr -> Either String String;
  string expression = case expression of {
    SStringLit value -> Right value;
    _ -> Left "host fixture: expected an original literal string"
  };
  pair :: SExpr -> Either String (Pair String String);
  pair expression = case spine expression Nil of {
    Pair head (Cons a (Cons b Nil)) -> do {
      ensure (eqString (atom head) "Pair") "host fixture: expected Pair";
      first <- string a; second <- string b; Right (Pair first second)
    };
    _ -> Left "host fixture: malformed library pair"
  };
  list :: forall a. (SExpr -> Either String a) -> SExpr -> Either String (List a);
  list decode expression = case spine expression Nil of {
    Pair head Nil -> do { ensure (eqString (atom head) "Nil") "host fixture: expected Nil"; Right Nil };
    Pair head (Cons a (Cons b Nil)) -> do {
      ensure (eqString (atom head) "Cons") "host fixture: expected Cons";
      first <- decode a; rest <- list decode b; Right (Cons first rest)
    };
    _ -> Left "host fixture: malformed literal list"
  };
  targetType :: SExpr -> Either String XType;
  targetType expression = case spine expression Nil of {
    Pair head Nil -> do { ensure (eqString (atom head) "XBot") "host fixture: unsupported prescribed type"; Right XBot };
    Pair head (Cons name (Cons args Nil)) -> do {
      ensure (eqString (atom head) "XCon") "host fixture: expected XCon";
      n <- string name; types <- list targetType args; Right (XCon n types)
    };
    _ -> Left "host fixture: unsupported prescribed type"
  };
  named :: String -> List SExpr -> Bool;
  named label arguments = case arguments of {
    Cons (SStringLit name) _ -> eqString name label; _ -> False
  };
  findFixture :: List SExpr -> String -> Either String Fixture;
  findFixture expressions label =
    case filter (named label) (concatMap (collect "ModuleTyping" 4) expressions) of {
      Cons (Cons _ (Cons libraries (Cons source (Cons expected Nil)))) Nil -> do {
        libs <- list pair libraries; input <- string source; ty <- targetType expected;
        Right (Fixture label libs input (Just ty) "")
      };
      Nil -> case filter (named label) (concatMap (collect "Quint" 5) expressions) of {
        Cons (Cons _ (Cons mode (Cons libraries (Cons source (Cons _ Nil))))) Nil -> do {
          ensure (eqString (atom mode) "ImplicitPrelude") "host fixture: wrong Prelude mode";
          libs <- list pair libraries; input <- string source;
          -- This is the exact checkModule oracle, not the runtime stdout oracle.
          Right (Fixture label libs input (Just (XCon "IO" (Cons (XCon "Unit" Nil) Nil))) "")
        };
        Nil -> case filter (named label) (concatMap (collect "ModuleRejection" 5) expressions) of {
          Cons (Cons _ (Cons libraries (Cons source (Cons phase (Cons reason Nil))))) Nil -> do {
            ensure (eqString (atom phase) "Resolution") "host fixture: expected resolution rejection";
            libs <- list pair libraries; input <- string source; why <- string reason;
            Right (Fixture label libs input Nothing why)
          };
          _ -> Left ("host fixture: missing or duplicate rejection: " ++ label)
        };
        _ -> Left ("host fixture: duplicate checking fixture: " ++ label)
      };
      _ -> Left ("host fixture: duplicate type-only fixture: " ++ label)
    };
  checked :: XType -> XTerm -> IO Unit;
  checked expected term = do {
    current <- right (Check.checkClosed term);
    frozen <- right (Independent.checkClosed term);
    assert (IndependentType.alphaEq current expected && IndependentType.alphaEq frozen expected)
      "host fixture: original checked type differs from prescribed type";
    decoded <- right (XP.parseTerm "<saved-crate roundtrip>" (Pretty.prettyTerm term));
    current2 <- right (Check.checkClosed decoded);
    frozen2 <- right (Independent.checkClosed decoded);
    assert (IndependentType.alphaEq current2 expected && IndependentType.alphaEq frozen2 expected)
      "host fixture: roundtrip checked type differs from prescribed type";
    assert (X.equalErased (X.erase term) (X.erase decoded)) "host fixture: roundtrip changed erasure"
  };
  contains :: String -> String -> Bool;
  contains needle haystack =
    if stringLength needle > stringLength haystack then False
    else eqString needle (stringSlice haystack 0 (stringLength needle)) ||
         (stringLength haystack > 0 && contains needle (stringSlice haystack 1 (stringLength haystack - 1)));
  runFixture :: String -> Int -> Fixture -> IO Unit;
  runFixture work index (Fixture label libraries source expected reason) = do {
    putStrLn ("CHECK exact saved-crate fixture: " ++ label);
    let { directory = work ++ "/case-" ++ showInt index };
    made <- Query.cacheCommand (Cons "/bin/mkdir" (Cons "-p" (Cons directory Nil)));
    assert (made == 0) "host fixture: cannot create case directory";
    let { inputs = M.fromList compareString
      (map (\(Pair name text) -> Pair name (Pair (directory ++ "/" ++ name ++ ".emlf") text)) libraries) };
    root <- right (Parser.parseModule (directory ++ "/Main.emlf") source);
    loaded <- right (Modules.loadModuleMap inputs root);
    modules <- right (traverseEither Separate.cleanSource loaded);
    let { spec = Crate.CrateSpec "test:crate" "Main" ImplicitPrelude
      (map (\m -> Pair (Modules.moduleIdentity m) (Modules.sourcePath m)) modules)
      Nil (directory ++ "/queries") (work ++ "/builtin/unit") };
    let { prefix = directory ++ "/crate" };
    result <- Crate.compileSources spec modules Nil prefix;
    case expected of {
      Nothing -> case result of {
        Left message -> assert (contains reason message)
          ("host fixture: wrong rejection for " ++ label ++ ": " ++ message);
        Right _ -> assert False ("host fixture: accepted forbidden evidence for " ++ label)
      };
      Just ty -> do {
        right result;
        loadedInterfaces <- Artifact.loadInterfaces (Cons (prefix ++ ".mlfci") Nil);
        interfaces <- right loadedInterfaces;
        objects <- mapM (\(Pair path iface) -> do { object <- Artifact.readObject (Artifact.objectPath path) iface; right object }) interfaces;
        term <- right (Artifact.linkObjects objects "test:crate");
        checked ty term
      }
    };
    putStrLn ("PASS exact saved-crate fixture: " ++ label)
  };
  main :: IO Unit;
  main = do {
    source <- readFile "tests/Tests/Modules.emlf";
    parsed <- right (Parser.parseModule "tests/Tests/Modules.emlf" source);
    let { expressions = map (\(Triple _ _ rhs) -> rhs) (Modules.sourceValues parsed) };
    let { labels = Cons "cyclic empty imports carry defining-module instances"
      (Cons "instance not visible in imported signed definition"
      (Cons "instance not visible in another instance"
      (Cons "downstream orphan cannot leak into an import cycle"
      (Cons "cross-module recursion infers unsigned cycle"
      (Cons "cross-module qualified recursion generalizes shared exports" Nil))))) };
    fixtures <- right (traverseEither (findFixture expressions) labels);
    assert (length fixtures == 6) "host fixture selection is incomplete";
    root <- canonicalPath ".";
    let { work = root ++ "/.mlf-build/qualified-host-crate-work" };
    made <- Query.cacheCommand (Cons "/bin/mkdir" (Cons "-p" (Cons (work ++ "/builtin") Nil)));
    assert (made == 0) "host fixture: cannot create builtin directory";
    foldM (\index fixture -> do { runFixture work index fixture; ioReturn (index + 1) }) 0 fixtures;
    putStrLn "PASS all six exact saved-crate fixtures through GHC host; production/frozen/roundtrip/erasure checks preserved"
  }
}
