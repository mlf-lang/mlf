-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Parser as Parser;

  fatal message = do { putErr (message ++ "\n"); exitWith 1; panic "exitWith returned" };
  require result = case result of { Left message -> fatal message; Right value -> ioReturn value };
  assertion value message = if value then ioReturn () else fatal message;
  source name imports = "module " ++ name ++ " where\n" ++
    concatMapString (\dependency -> "import " ++ dependency ++ "\n") imports ++ "value = 1\n";
  payload name text = mapEither (\parsed -> Modules.LoadedModule parsed text)
    (Parser.parseModule (name ++ ".emlf") text);
  graph rows rootText = do {
    root <- require (payload "Root" rootText);
    Modules.loadGraphBy Modules.loadedSource (\name -> ioReturn (case lookup eqString name rows of {
      Nothing -> Left ("missing:" ++ name);
      Just text -> payload name text
    })) root
  };
  expectOrder label rows rootText expected = do {
    actual <- graph rows rootText >>= require;
    assertion (eqList eqString expected (map (compose Modules.moduleIdentity Modules.loadedSource) actual))
      (label ++ ": graph order mismatch");
    mapM_ (\entry -> let { name = Modules.moduleIdentity (Modules.loadedSource entry);
      expectedText = if eqString name "Root" then Just rootText else lookup eqString name rows } in
      assertion (eqMaybe eqString expectedText (Just (Modules.loadedText entry)))
        (label ++ ": parser evidence changed")) actual
  };
  expectError label rows rootText expected = do {
    result <- graph rows rootText;
    case result of {
      Left actual -> assertion (eqString actual expected) (label ++ ": wrong first error: " ++ actual);
      Right _ -> fatal (label ++ ": invalid graph accepted")
    }
  };
  withBody (SourceModule path name exports imports datatypes classes instances values _ syntax) =
    SourceModule path name exports imports datatypes classes instances values (Just (SIntLit 1)) syntax;
  syntheticBodyControl = do {
    root <- require (payload "Root" (source "Root" ["A"]));
    parsed <- require (Parser.parseModule "A.emlf" (source "A" []));
    let { child = Modules.LoadedModule (withBody parsed) "synthetic-body-control" };
    result <- Modules.loadGraphBy Modules.loadedSource (\_ -> ioReturn (Right child)) root;
    case result of {
      Left actual -> assertion (eqString actual "A.emlf: imported modules must contain declarations only")
        ("synthetic imported body: wrong graph-validator error: " ++ actual);
      Right _ -> fatal "graph validator accepted a synthetic imported expression"
    }
  };
  memoryControls = do {
    expectOrder "multi-dependency/root-last"
      [(,) "A" (source "A" ["C"]), (,) "B" (source "B" []), (,) "C" (source "C" [])]
      (source "Root" ["A", "B"]) ["C", "A", "B", "Root"];
    expectOrder "diamond/dedup"
      [(,) "A" (source "A" ["C"]), (,) "B" (source "B" ["C"]), (,) "C" (source "C" [])]
      (source "Root" ["A", "B", "A"]) ["C", "A", "B", "Root"];
    expectOrder "cycle/root-backedge"
      [(,) "A" (source "A" ["Root"])] (source "Root" ["A"]) ["A", "Root"];
    expectOrder "cycle/child-backedge"
      [(,) "A" (source "A" ["B"]), (,) "B" (source "B" ["A"])]
      (source "Root" ["A"]) ["B", "A", "Root"];
    expectError "first-missing" [] (source "Root" ["First", "Second"]) "missing:First";
    expectError "wrong-module" [(,) "A" (source "Wrong" [])] (source "Root" ["A"])
      "A.emlf: expected module A, found Wrong";
    expectError "imported-expression" [(,) "A" "module A where\n1\n"] (source "Root" ["A"])
      "A.emlf:3:1: named modules contain declarations only; define main for the entry point";
    syntheticBodyControl
  };
  -- Caller supplies a newly created tool-owned directory. No existing library
  -- or production input is modified by these filesystem controls.
  fileControls directory = do {
    let { first = directory ++ "/first"; second = directory ++ "/second";
          rootPath = directory ++ "/Root.emlf"; rootText = source "Root" ["A"] };
    root <- require (Parser.parseModule rootPath rootText);
    writeFile (first ++ "/A.emlf") (source "A" []);
    writeFile (second ++ "/A.emlf") "module A where\nvalue = 2\n";
    loaded <- Modules.loadModuleFilesWithEvidence [first, second] root rootText >>= require;
    assertion (eqList eqString (map (compose Modules.sourcePath Modules.loadedSource) (Modules.loadedEntries loaded))
      [first ++ "/A.emlf", rootPath]) "file path precedence changed";
    assertion (eqString (Modules.loadedText (head (Modules.loadedEntries loaded))) (source "A" []))
      "file parser evidence did not match first selected file";
    writeFile (second ++ "/A.hs") "-- mlf:syntax shared-haskell-v1\nmodule A where { value = 3 }\n";
    ambiguity <- Modules.loadModuleFilesWithEvidence [first, second] root rootText;
    let { expected = "ambiguous source module A: both .emlf and .hs candidates exist: " ++
          first ++ "/A.emlf, " ++ second ++ "/A.emlf, " ++ second ++
          "/A.hs; use an explicit manifest mapping" };
    case ambiguity of {
      Left actual -> assertion (eqString actual expected) ("wrong ambiguity diagnostic: " ++ actual);
      Right _ -> fatal "mixed source suffix ambiguity was hidden"
    }
  };
  main = do {
    count <- getArgCount;
    if count /= 1 then fatal "usage: loader-controls FRESH_DIRECTORY_WITH_first_AND_second_SUBDIRECTORIES" else do {
      directory <- getArg 0;
      memoryControls;
      fileControls directory;
      putStrLn "PASS loader order, cycles, diamonds, exact errors, ambiguity and evidence"
    }
  }
}
