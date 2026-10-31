-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.PreparedLibraries as Libraries;
  import qualified Bootstrap.CompilerCore as Core;
  import qualified MLF.PreparedLibraryData as Data;
  fatal message = do { putErr (message ++ "\n"); exitWith 1; panic "exit returned" };
  require result = case result of { Left message -> fatal message; Right value -> ioReturn value };
  assertion condition message = if condition then ioReturn () else fatal message;
  fixed = case Data.libraries of { [raw] -> Right raw; _ -> Left "controls require one installed source registry" };
  load directory defaults name text = do {
    parsed <- require (Parser.parseModule (Modules.joinPath directory name) text);
    Modules.loadModuleFilesWithEvidenceUsingFallback Data.parseLibrary [] defaults parsed text >>= require
  };
  compiled raw directory defaults name text = do {
    loaded <- load directory defaults name text;
    require (mapLeft Core.prettyError
      (Libraries.compileNativeRootUsing Data.parseLibrary raw ImplicitPrelude loaded))
  };
  accepted raw directory defaults name text requireImports = do {
    result <- compiled raw directory defaults name text;
    if requireImports then assertion (not (M.null (Libraries.nativeSignatures result)) || Libraries.nativeBuiltinCount result > 0)
      (name ++ ": did not select any installed exports") else ioReturn ();
    putStrLn (name ++ " accepted")
  };
  instanceSource = "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule InstanceControl where { import MLF.Primitive; import Bootstrap.Types; instance Functor Maybe where { fmap f action = case action of { Nothing -> Nothing; Just value -> Just (f value) } }; main = case fmap (\\x -> x + 1) (Just 2) of { Nothing -> printInt 0; Just value -> printInt value } }\n";
  main = do {
    directory <- getArg 0;
    sourceRoot <- getArg 1;
    raw <- require fixed;
    let { defaults = [sourceRoot] };
    accepted raw directory defaults "Implicit.emlf" "main = do { putStrLn \"hello\"; return () }\n" True;
    accepted raw directory defaults "Subset.emlf" "import qualified Bootstrap.Std as S\nmain = printInt (S.length ((:) 1 []))\n" True;
    accepted raw directory defaults "UserDatatype.emlf" "data Local = Local Int\nmain = case Local 3 of { Local n -> printInt n }\n" False;
    accepted raw directory defaults "InstanceControl.hs" instanceSource True;
    returned <- compiled raw directory defaults "Returned.emlf"
      "main = \\x -> do { printInt x; return () }\n";
    assertion (Libraries.nativeBuiltinCount returned > 0 && M.null (Libraries.nativeSignatures returned))
      "builtin-only returned function retained native parameters or failed to materialize";
    assertion (case Libraries.nativeInferredType returned of { XArrow _ _ -> True; _ -> False })
      "builtin materialization removed the user-returned function";
    mixed <- compiled raw directory defaults "Mixed.emlf"
      "import qualified Bootstrap.Std as S\nmain = do { printInt (S.length ((:) 1 [])); return () }\n";
    assertion (Libraries.nativeBuiltinCount mixed > 0 && not (M.null (Libraries.nativeSignatures mixed)))
      "mixed builtin and native imports were not preserved separately";

    subset <- load directory defaults "Mutation.emlf" "import qualified Bootstrap.Std as S\nmain = printInt (S.length ((:) 1 []))\n";
    let { missing = Modules.LoadedModules [last (Modules.loadedEntries subset)];
          duplicate = Modules.LoadedModules (append (Modules.loadedEntries subset) [head (Modules.loadedEntries subset)]) };
    assertion (isLeft (Libraries.compileNativeRootUsing Data.parseLibrary raw ImplicitPrelude missing)) "completion repaired missing actual import";
    assertion (isLeft (Libraries.compileNativeRootUsing Data.parseLibrary raw ImplicitPrelude duplicate)) "completion removed duplicate actual module";
    badQualified <- load directory defaults "Qualified.emlf" "main = Missing.value\n";
    assertion (isLeft (Libraries.compileNativeRootUsing Data.parseLibrary raw ImplicitPrelude badQualified)) "missing qualified namespace became visible";
    let { altered = Modules.LoadedModules (map (\entry -> Modules.LoadedModule
      (Modules.loadedSource entry) (Modules.loadedText entry ++ "\n")) (Modules.loadedEntries subset)) };
    assertion (isLeft (Libraries.compileNativeRootUsing Data.parseLibrary raw ImplicitPrelude altered))
      "changed loaded installed source was silently replaced by completion";
    loaded <- load directory defaults "Invisible.emlf" "main = compile \"a\"\n";
    assertion (isLeft (Libraries.compileNativeRootUsing Data.parseLibrary raw ImplicitPrelude loaded))
      "unimported installed value became visible";
    let { primary = Modules.joinPath directory "primary";
          fallback = Modules.joinPath directory "default";
          file = Modules.joinPath primary "Choice.emlf";
          good = "module Choice where\nvalue = 7\n";
          override = "module Choice where\nvalue = 9\n" };
    -- The caller supplies fresh primary/default directories. Fixture writes
    -- stay entirely outside the immutable installed source inventory.
    writeFile (Modules.joinPath fallback "Choice.emlf") good;
    first <- Modules.fetchFileWithEvidenceUsingFallback Data.parseLibrary [primary] [fallback] "Choice" >>= require;
    assertion (eqString (Modules.loadedText first) good) "default source not loaded";
    writeFile file override;
    second <- Modules.fetchFileWithEvidenceUsingFallback Data.parseLibrary [primary] [fallback] "Choice" >>= require;
    assertion (eqString (Modules.loadedText second) override) "explicit source was replaced";
    writeFile file "module Choice where\nvalue = (\n";
    malformed <- Modules.fetchFileWithEvidenceUsingFallback Data.parseLibrary [primary] [fallback] "Choice";
    assertion (isLeft malformed) "malformed explicit source silently replaced";
    writeFile file override;
    writeFile (Modules.joinPath primary "Choice.hs") "-- mlf:syntax shared-haskell-v1\nmodule Choice where { value = 8 }\n";
    ambiguous <- Modules.fetchFileWithEvidenceUsingFallback Data.parseLibrary [primary] [fallback] "Choice";
    assertion (isLeft ambiguous) "ambiguous explicit source silently replaced";
    putStrLn "native subset, implicit Prelude, instance reach and default loader controls passed"
  }
}
