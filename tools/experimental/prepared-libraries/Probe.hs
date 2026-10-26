-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Compiler as Compiler;
  import qualified Bootstrap.CompilerCore as Core;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.PreparedLibraries as Prepared;
  import qualified MLF.PreparedLibraryData as Data;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.LLVM as LLVM;
  import qualified Bootstrap.Runtime as Runtime;
  import qualified Package.Json as J;

  fatal message = do { putErr (message ++ "\n"); exitWith 1; panic "exitWith returned" };
  require result = case result of { Left message -> fatal message; Right value -> ioReturn value };
  mode request = if J.getBool "no_prelude" False request then NoImplicitPrelude else ImplicitPrelude;
  tag name fields = J.array ((:) (J.str name) fields);
  kind value = case value of { Star -> tag "star" []; KArrow a b -> tag "kind-arrow" [kind a, kind b] };
  xtype value = case value of {
    XVar (XTyVar n) -> tag "var" [J.num n];
    XBot -> tag "bottom" [];
    XBotKind k -> tag "bottom-kind" [kind k];
    XArrow a b -> tag "arrow" [xtype a, xtype b];
    XCon name arguments -> tag "con" [J.str name, J.array (map xtype arguments)];
    XApply a b -> tag "apply" [xtype a, xtype b];
    XForall (XTyVar n) bound body -> tag "forall" [J.num n, xtype bound, xtype body]
  };
  field value = case value of {
    Parameter n -> tag "parameter" [J.str n];
    Function a b -> tag "function" [field a, field b];
    Applied n arguments -> tag "applied" [J.str n, J.array (map field arguments)];
    Application a b -> tag "application" [field a, field b];
    Quantified n k body -> tag "quantified" [J.str n, kind k, field body]
  };
  layout value = J.object [
    (,) "name" (J.str (D.datatypeName value)),
    (,) "parameters" (J.array (map (\((,) n k) -> J.array [J.str n, kind k]) (D.datatypeBinders value))),
    (,) "constructors" (J.array (map (\constructor -> J.object [
      (,) "name" (J.str (D.constructorName constructor)),
      (,) "fields" (J.array (map field (D.constructorFields constructor)))
    ]) (D.datatypeConstructors value)))
  ];
  declarations checked = case Checked.term checked of { XWithData ds _ -> ds; _ -> [] };
  data Result = Result Checked.CheckedTerm Bool (Map Modules.Entity String) (Map String String);
  ordinaryDictionaries preludeMode sources = do {
    linked <- Core.atPhase ModuleResolution (Modules.linkModules preludeMode sources);
    canonical <- Core.atPhase Inference (Classes.canonicalSourceProgram S.empty (Modules.linkedProgram linked));
    lowered <- Core.atPhase Inference (Classes.lowerClassesWithScopes
      (Modules.linkedValueScopes linked) (Modules.linkedInstanceScopes linked) canonical);
    Right (snd lowered)
  };
  ordinaryNames preludeMode sources = do {
    resolution <- Core.atPhase ModuleResolution (Modules.resolveCrateWithAllocator
      preludeMode M.empty Modules.freshNames sources);
    case Modules.resolvedCrateNames resolution of { Modules.Names names -> Right names }
  };
  compile route registry preludeMode loaded = do {
    let { sources = Modules.loadedSources loaded };
    if eqString route "ordinary" then do {
      compiled <- Compiler.compileLinked preludeMode sources;
      names <- ordinaryNames preludeMode sources;
      dictionaries <- ordinaryDictionaries preludeMode sources;
      Right (Result (Core.checkedTerm compiled) False names dictionaries)
    } else if eqString route "prepared" then do {
      compiled <- Prepared.compileLoaded registry preludeMode loaded;
      let { names = Prepared.nameMap compiled; used = Prepared.reused compiled };
      dictionaries <- if used then Right (M.fromList compareString
        (map (\((,) entity actual) -> (,) ("Dict_" ++ actual) actual)
          (filter (\((,) entity _) -> Modules.isRole Modules.Class entity) (M.toList names))))
        else ordinaryDictionaries preludeMode sources;
      Right (Result (Prepared.checkedTerm compiled) used names dictionaries)
    } else Left (CompileError ModuleResolution "unknown qualification route")
  };
  -- Qualification-only corruptions of compiler-owned data. This probe is not
  -- an external registry loader and the production adapter exposes no variant.
  staleWitness value = case value of {
    SourceModule path name exports imports ds cs instances values body syntax ->
      SourceModule (path ++ "-stale-witness") name exports imports ds cs instances values body syntax
  };
  registry request = let { variant = J.getText "registry_variant" "current" request } in
    if eqString variant "current" then Right Data.libraries else
    traverseEither (\raw -> case raw of {
      Prepared.RawLibrary identity schema prelude sources objects witnesses ->
        if eqString variant "stale-builtin-witness" then case witnesses of {
          [] -> Left "registry lacks builtin witnesses before corruption control";
          (:) witness rest -> Right (Prepared.RawLibrary identity schema prelude sources objects
            ((:) (staleWitness witness) rest))
        } else if eqString variant "stale-schema" then Right
          (Prepared.RawLibrary identity (schema ++ "-stale") prelude sources objects witnesses)
        else if eqString variant "invalid-source-hash" then case sources of {
          [] -> Left "registry lacks source records before corruption control";
          (:) (Prepared.LibrarySource name path text _ syntax) rest -> Right
            (Prepared.RawLibrary identity schema prelude
              ((:) (Prepared.LibrarySource name path text "invalid" syntax) rest) objects witnesses)
        } else Left "unknown qualification registry variant"
    }) Data.libraries;
  -- Source Entity identities are the only user nominal correspondence. The
  -- builtin table is explicit, and dictionary correspondence comes from the
  -- actual class planner plus that source Entity map, never a name regex.
  nominalRows checked names dictionaries = do {
    let {
      sourceRows = concatMap (\((,) entity actual) -> case Modules.role entity of {
        Modules.Datatype -> [(,) ((,) "type" actual) (J.stringArray ["entity", Separate.entityEncoding entity])];
        Modules.Constructor _ -> [(,) ((,) "constructor" actual) (J.stringArray ["entity", Separate.entityEncoding entity])];
        _ -> []
      }) (M.toList names);
      builtinRows = append
        (map (\name -> (,) ((,) "type" name) (J.stringArray ["builtin", name]))
          (nubBy eqString (append (M.keys D.primitiveKinds) (map D.datatypeName D.builtinDeclarations))))
        (map (\name -> (,) ((,) "constructor" name) (J.stringArray ["builtin", name]))
          (concatMap (compose (map D.constructorName) D.datatypeConstructors) D.builtinDeclarations));
      classEntities = M.fromList compareString (map (\((,) entity actual) -> (,) actual entity)
        (filter (\((,) entity _) -> Modules.isRole Modules.Class entity) (M.toList names)))
    };
    dictionaryRows <- traverseEither (\((,) dictionary klass) ->
      if eqString dictionary "MLFStackEvidence" then Right [] else do {
        entity <- case M.lookup compareString klass classEntities of {
          Nothing -> Left ("dictionary has no source class identity: " ++ klass);
          Just value -> Right value
        };
        constructor <- case filter (\d -> eqString (D.datatypeName d) dictionary) (declarations checked) of {
          [declaration] -> case D.datatypeConstructors declaration of {
            [value] -> Right (D.constructorName value);
            _ -> Left "class dictionary does not have exactly one constructor"
          };
          _ -> Left ("class dictionary is missing from ordered layouts: " ++ dictionary)
        };
        Right [
          (,) ((,) "type" dictionary) (J.stringArray ["dictionary", Separate.entityEncoding entity]),
          (,) ((,) "constructor" constructor) (J.stringArray ["dictionary-constructor", Separate.entityEncoding entity])]
      }) (M.toList dictionaries);
    let { rows = M.fromList (comparePair compareString compareString)
          (append sourceRows (append builtinRows (concat dictionaryRows))) };
    Right (map (\((,) ((,) namespace name) identity) -> J.object [
      (,) "namespace" (J.str namespace), (,) "name" (J.str name), (,) "identity" identity
    ]) (M.toList rows))
  };
  report outcome = case outcome of {
    Left error -> Right (J.object [
      (,) "format" (J.str "MLF-PREPARED-LIBRARY-PROBE-1"), (,) "accepted" (J.Boolean False),
      (,) "error" (J.object [(,) "phase" (J.str (Core.prettyPhase (Core.phase error))),
        (,) "diagnostic" (J.str (Core.diagnostic error))])]);
    Right (Result checked used names dictionaries) -> do {
      nominals <- nominalRows checked names dictionaries;
      Right (J.object [
        (,) "format" (J.str "MLF-PREPARED-LIBRARY-PROBE-1"), (,) "accepted" (J.Boolean True),
        (,) "reused" (J.Boolean used), (,) "principal_type" (xtype (Checked.typeOf checked)),
        (,) "layouts" (J.array (map layout (declarations checked))), (,) "nominals" (J.array nominals)])
    }
  };
  -- An explicit source map is for owned mutation fixtures only. It uses the
  -- same graph validation and ordinary parser profile, and never edits the
  -- live path whose provenance is under test. File-search controls are separate.
  fetchProvided request name = case filter (\row -> eqString (J.getText "module" "" row) name)
      (J.values (J.get "source_map" request)) of {
    [row] -> do {
      text <- readFile (J.getText "buffer_path" "" row);
      ioReturn (mapEither (\source -> Modules.LoadedModule source text)
        (Parser.parseModule (J.getText "source_path" "" row) text))
    };
    _ -> ioReturn (Left ("cannot find module " ++ name))
  };
  load request = do {
    let { path = J.getText "source_path" "" request };
    text <- readFile (J.getText "buffer_path" path request);
    case Core.atPhase Parsing (Parser.parseModule path text) of {
      Left error -> ioReturn (Left error);
      Right root -> do {
        loaded <- if J.has "source_map" request then do {
          graph <- Modules.loadGraphBy Modules.loadedSource (fetchProvided request)
            (Modules.LoadedModule root text);
          ioReturn (mapEither Modules.LoadedModules graph)
        } else Modules.loadModuleFilesWithEvidence (J.getStrings "include_paths" request) root text;
        ioReturn (Core.atPhase ModuleResolution loaded)
      }
    }
  };
  run operation route request = do {
    selectedRegistry <- require (registry request);
    loaded <- load request;
    let { outcome = bindEither loaded (compile route selectedRegistry (mode request)) };
    if eqString operation "inspect" then do {
      value <- require (report outcome);
      let { reads = case loaded of {
        Left _ -> [];
        Right graph -> map (\entry -> J.object [
          (,) "path" (J.str (Modules.sourcePath (Modules.loadedSource entry))),
          (,) "text" (J.str (Modules.loadedText entry))
        ]) (Modules.loadedEntries graph)
      } };
      putStrLn (J.render (J.set "source_reads" (J.array reads) value))
    }
    else case outcome of {
      Left error -> fatal (Core.prettyError error);
      Right (Result checked _ _ _) -> if eqString operation "emit" then do {
        chunks <- require (LLVM.emitCheckedChunks False checked);
        mapM_ putStr chunks
      } else if eqString operation "run" then do {
        result <- Runtime.runProgramWithArguments (J.getStrings "arguments" request) (Checked.term checked);
        require result
      } else fatal "expected inspect, emit, or run"
    }
  };
  main = do {
    count <- getArgCount;
    if count /= 3 then fatal "usage: prepared-library-probe inspect|emit|run ordinary|prepared REQUEST.json"
    else do {
      operation <- getArg 0; route <- getArg 1; requestFile <- getArg 2;
      request <- J.read requestFile;
      run operation route request
    }
  }
}
