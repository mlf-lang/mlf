-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.PreparedLibraries as Libraries;
  import qualified Bootstrap.SourceEquality as Equality;
  import qualified MLF.PreparedLibraryData as Data;

  fatal message = do { putErr (message ++ "\n"); exitWith 1; panic "exitWith returned" };
  check ((,) path input) = case (,) (Parser.parseModule path input) (Data.parseLibrary path input) of {
    (,) (Left expected) (Left actual) -> if eqString expected actual then ioReturn () else fatal "parser memo changed error";
    (,) (Right expected) (Right actual) -> if Equality.eqSourceModule expected actual then ioReturn () else fatal "parser memo changed AST";
    _ -> fatal "parser memo changed acceptance"
  };
  controls entry = let { path = Libraries.sourcePath entry; text = Libraries.sourceText entry } in
    mapM_ check [
      (,) path text,
      (,) path (text ++ "\n"),
      (,) path "module Wrong where\nx = 3\n",
      (,) path "λ😀 invalid",
      (,) path (stringSlice text 0 (stringLength text - 1)),
      (,) (path ++ ".emlf") text,
      (,) "changed.hs" text,
      (,) path ""
    ];
  main = do {
    let { entries = concatMap Libraries.librarySources Data.libraries };
    if null entries then fatal "parser memo controls require a populated authenticated compiler registry" else do {
      mapM_ controls entries;
      putStrLn (showInt (8 * length entries) ++ " exact-source/path/syntax/Unicode/malformed parser controls passed")
    }
  }
}
