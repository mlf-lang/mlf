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
  import qualified Bootstrap.Compiler as Compiler;
  import qualified Bootstrap.CompilerCore as Core;
  import qualified Bootstrap.Runtime as Runtime;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as Type;
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
  checkedType :: String -> XType -> Checked.CheckedTerm -> IO ();
  checkedType label expected checked = do {
    actual <- require (Check.checkClosed (Checked.term checked));
    assertion (Type.alphaEq actual expected && Type.alphaEq (Checked.typeOf checked) expected)
      (label ++ ": checked type differs from the independent oracle")
  };
  nativeType :: String -> XType -> Libraries.NativeRoot -> IO ();
  nativeType label expected compiled = do {
    assertion (Type.alphaEq (Libraries.nativeInferredType compiled) expected)
      (label ++ ": native root type differs from the independent oracle");
    let { wrapper = Libraries.nativeCheckedWrapper compiled };
    checkedType label (Checked.typeOf wrapper) wrapper
  };
  sharedRoot :: Libraries.RawLibrary -> String -> Modules.LoadedModules -> XType -> IO Checked.CheckedTerm;
  sharedRoot raw label loaded expected = do {
    ordinary <- require (mapLeft Core.prettyError
      (Compiler.compileLinked ImplicitPrelude (Modules.loadedSources loaded)));
    fallback <- require (mapLeft Core.prettyError (Libraries.compileLoaded [] ImplicitPrelude loaded));
    native <- require (mapLeft Core.prettyError
      (Libraries.compileNativeRootUsing Data.parseLibrary raw ImplicitPrelude loaded));
    checkedType (label ++ " ordinary") expected (Core.checkedTerm ordinary);
    checkedType (label ++ " fallback") expected (Libraries.checkedTerm fallback);
    nativeType label expected native;
    assertion (not (Libraries.reused fallback) &&
      eqString (Core.sourceType ordinary) (Libraries.sourceType fallback) &&
      X.equalErased (X.erase (Core.compiledTerm ordinary))
        (X.erase (Checked.term (Libraries.checkedTerm fallback))))
      (label ++ ": empty-registry fallback changed the ordinary checked root");
    ioReturn (Core.checkedTerm ordinary)
  };
  -- Prepared grafting requires the entire recorded library inventory. Keep
  -- every actual parser read and import edge, and supply exact missing records
  -- only in this qualification fixture. A subset would silently test fallback.
  completeFixture :: Libraries.RawLibrary -> Modules.LoadedModules -> IO Modules.LoadedModules;
  completeFixture raw loaded = do {
    let { actual = Modules.loadedEntries loaded;
          recorded = Libraries.librarySources raw;
          selected = map Libraries.sourceName recorded };
    installed <- mapM (\source -> case find (\entry ->
      eqString (Modules.moduleIdentity (Modules.loadedSource entry)) (Libraries.sourceName source)) actual of {
      Just entry -> ioReturn entry;
      Nothing -> do {
        parsed <- require (Data.parseLibrary (Libraries.sourcePath source) (Libraries.sourceText source));
        ioReturn (Modules.LoadedModule parsed (Libraries.sourceText source))
      }
    }) recorded;
    ioReturn (Modules.LoadedModules (append installed (filter (\entry ->
      not (elem eqString (Modules.moduleIdentity (Modules.loadedSource entry)) selected)) actual)))
  };
  integerResult :: String -> Checked.CheckedTerm -> IO ();
  integerResult label checked = do {
    (,) environment _ <- require (Runtime.prepare False (Checked.term checked));
    value <- require (Runtime.evaluate environment (Runtime.REnv M.empty) (X.erase (Checked.term checked)));
    assertion (case value of { Runtime.RInteger number -> number == 42; _ -> False })
      (label ++ ": datatype, import or local scope changed the result 42")
  };
  rejected :: forall a. String -> Phase -> Either CompileError a -> IO CompileError;
  rejected label phase result = case result of {
    Right _ -> fatal (label ++ ": invalid root was accepted");
    Left error -> do {
      assertion (eqString (Core.prettyPhase (Core.phase error)) (Core.prettyPhase phase))
        (label ++ ": rejection phase changed: " ++ Core.prettyError error);
      ioReturn error
    }
  };
  sharedRejection raw label loaded phase exactNative = do {
    ordinary <- rejected (label ++ " ordinary") phase
      (Compiler.compileLinked ImplicitPrelude (Modules.loadedSources loaded));
    fallback <- rejected (label ++ " fallback") phase (Libraries.compileLoaded [] ImplicitPrelude loaded);
    complete <- completeFixture raw loaded;
    prepared <- rejected (label ++ " prepared") phase (Libraries.compileLoaded [raw] ImplicitPrelude complete);
    native <- rejected (label ++ " native") phase
      (Libraries.compileNativeRootUsing Data.parseLibrary raw ImplicitPrelude complete);
    assertion (eqString (Core.diagnostic ordinary) (Core.diagnostic fallback))
      (label ++ ": fallback changed the exact ordinary diagnostic");
    if exactNative then assertion
      (eqString (Core.diagnostic ordinary) (Core.diagnostic prepared) &&
       eqString (Core.diagnostic ordinary) (Core.diagnostic native))
      (label ++ ": module diagnostic changed across routes") else ioReturn ()
  };
  sharedRoots raw directory defaults = do {
    polymorphic <- load directory defaults "SharedPolymorphism.emlf" "main = \\value -> value\n";
    let { variable = XTyVar 0;
          identity = XForall variable XBot (XArrow (XVar variable) (XVar variable)) };
    sharedRoot raw "polymorphic identity" polymorphic identity;
    action <- load directory defaults "SharedIO.emlf"
      "main = do { value <- ioReturn 42; printInt value }\n";
    sharedRoot raw "IO root" action (XCon "IO" [XCon "()" []]);
    scoped <- load directory defaults "SharedScope.emlf"
      "import qualified Bootstrap.Std as S\ndata Local = Local Int\nmain = let { identity = \\value -> value; length = \\values -> 7 } in case Local (S.length ((:) 1 ((:) 2 []))) of { Local n -> if identity true then addInt (length []) (addInt n 33) else identity 0 }\n";
    ordinary <- sharedRoot raw "imported and local scopes" scoped (XCon "Int" []);
    integerResult "ordinary scope" ordinary;
    complete <- completeFixture raw scoped;
    prepared <- require (mapLeft Core.prettyError (Libraries.compileLoaded [raw] ImplicitPrelude complete));
    assertion (Libraries.reused prepared) "shared-root control fell back instead of checking prepared imports";
    checkedType "prepared scope" (XCon "Int" []) (Libraries.checkedTerm prepared);
    integerResult "prepared scope" (Libraries.checkedTerm prepared);
    native <- require (mapLeft Core.prettyError
      (Libraries.compileNativeRootUsing Data.parseLibrary raw ImplicitPrelude complete));
    nativeType "complete native scope" (XCon "Int" []) native;
    assertion (not (M.null (Libraries.nativeSignatures native)))
      "shared-root native control did not retain its installed import";
    missing <- load directory defaults "SharedMissing.emlf" "main = Missing.value\n";
    sharedRejection raw "unresolved namespace" missing ModuleResolution True;
    invalid <- load directory defaults "SharedInvalid.emlf" "main = putStrLn 1\n";
    sharedRejection raw "invalid argument type" invalid Inference False;
    putStrLn "shared roots preserve polymorphism, IO, imported/local scopes, checked results and rejection phases"
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
    sharedRoots raw directory defaults;
    putStrLn "native subset, implicit Prelude, instance reach and default loader controls passed"
  }
}
