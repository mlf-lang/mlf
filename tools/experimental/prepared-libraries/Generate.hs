-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Lexer as Lexer;
  import qualified Bootstrap.Crate as Crate;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.PreparedLibraries as Prepared;
  import qualified Bootstrap.PreparedLibraryLiteral as Literal;
  import qualified Package.Json as J;

  fatal message = do { putErr (message ++ "\n"); exitWith 1; panic "exitWith returned" };
  require result = case result of { Left message -> fatal message; Right value -> ioReturn value };
  mode request = if eqString (J.getText "mode" "" request) "ImplicitPrelude"
    then Right ImplicitPrelude else if eqString (J.getText "mode" "" request) "NoImplicitPrelude"
    then Right NoImplicitPrelude else Left "invalid library preparation Prelude mode";
  rowFor request name = case filter (\row -> eqString (J.getText "module" "" row) name)
      (J.values (J.get "library_inventory" request)) of {
    [row] -> Right row;
    _ -> Left ("requested library dependency is outside its exact manifest: " ++ name)
  };
  fetch request name = case rowFor request name of {
    Left message -> ioReturn (Left message);
    Right row -> do {
      let { frozen = J.getText "buffer_path" "" row; path = J.getText "path" "" row };
      text <- readFile frozen;
      digest <- fileDigest frozen;
      ioReturn (do {
        ensure (eqString digest (J.getText "sha256" "" row)) "frozen library source SHA256 mismatch";
        parsed <- Parser.parseModule path text;
        ensure (eqString (Modules.moduleIdentity parsed) name) "manifest library module identity mismatch";
        ensure (case Modules.sourceBody parsed of { Nothing -> True; _ -> False })
          "prepared libraries cannot contain an executable root";
        Right (Modules.LoadedModule parsed text)
      })
    }
  };
  closure request roots = foldM (\done name -> do {
    root <- fetch request name >>= require;
    sources <- Modules.loadGraphBy Modules.loadedSource (fetch request) root >>= require;
    ioReturn (append done (filter (\source -> not (any (\prior ->
      eqString (Modules.moduleIdentity (Modules.loadedSource source))
        (Modules.moduleIdentity (Modules.loadedSource prior))) done)) sources))
  }) [] roots;
  sourceRecord request entry = do {
    let { source = Modules.loadedSource entry; text = Modules.loadedText entry };
    row <- require (rowFor request (Modules.moduleIdentity source));
    after <- readFile (J.getText "buffer_path" "" row);
    digest <- fileDigest (J.getText "buffer_path" "" row);
    require (ensure (eqString text after && eqString digest (J.getText "sha256" "" row))
      "library source changed after its parser read");
    ioReturn (Prepared.LibrarySource (Modules.moduleIdentity source) (Modules.sourcePath source)
      text digest (Modules.sourceSyntax source))
  };
  readObject prefix = do {
    iface <- Artifact.readInterface (prefix ++ ".mlfci") >>= require;
    object <- Artifact.readObject (prefix ++ ".mlfco") iface >>= require;
    metadataHash <- fileDigest (prefix ++ ".mlfci");
    objectHash <- fileDigest (prefix ++ ".mlfco");
    ioReturn (Prepared.LibraryObject metadataHash objectHash object)
  };
  generated raw = unlines [
    "-- mlf:syntax shared-haskell-v1",
    "{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}",
    "-- Generated from the ordinary parser profile and authenticated checked artifacts.",
    "-- Raw data only; every consumer retains independent artifact/graft checks.",
    "module MLF.PreparedLibraryData (libraries) where {",
    "import MLF.Primitive; import Bootstrap.Types;",
    "import Bootstrap.PreparedLibraries (RawLibrary(..), LibrarySource(..), LibraryObject(..));",
    "import Bootstrap.CrateArtifact (CrateObject(..), CrateInterface(..));",
    "import Bootstrap.Separate (UnitObject(..), UnitInterface(..));",
    "import Bootstrap.Module (Entity(..), Role(..), Interface(..), Names(..), ModuleSpace(..));",
    "libraries :: [] RawLibrary;",
    "libraries = [" ++ Literal.rawLibrary raw ++ "]",
    "}"
  ];
  artifactRecord prefix object = J.object [
    (,) "identity" (J.str (Artifact.crateId (Artifact.objectInterface (Prepared.libraryObject object)))),
    (,) "metadata_path" (J.str (prefix ++ ".mlfci")),
    (,) "metadata_sha256" (J.str (Prepared.metadataHash object)),
    (,) "object_path" (J.str (prefix ++ ".mlfco")),
    (,) "object_sha256" (J.str (Prepared.objectHash object))
  ];
  run request = do {
    require (ensure (eqString (J.getText "format" "" request) "MLF-PREPARED-LIBRARY-JOB-1" &&
      eqString (J.getText "source_package" "" request) "main") "invalid library generation request");
    preludeMode <- require (mode request);
    entries <- closure request (J.getStrings "roots" request);
    let { sources = map Modules.loadedSource entries };
    require (ensure (not (null sources)) "requested library closure is empty");
    recorded <- mapM (sourceRecord request) entries;
    cleaned <- require (traverseEither Separate.cleanSource sources);
    let { directory = J.getText "output_directory" "" request;
          builtinPrefix = directory ++ "/builtin";
          libraryPrefix = directory ++ "/library";
          identity = J.getText "input_identity" "" request;
          libraryIdentity = J.getText "library_identity" "" request };
    builtin <- require Artifact.builtinPrelude;
    Artifact.writeObject builtinPrefix builtin;
    let { metadata = builtinPrefix ++ ".mlfci";
          spec = Crate.CrateSpec libraryIdentity "" preludeMode
            (map (\source -> (,) (Modules.moduleIdentity source) (Modules.sourcePath source)) sources)
            [metadata] (J.getText "query_directory" (directory ++ "/queries") request) builtinPrefix };
    Crate.compileSources spec cleaned [(,) metadata (Artifact.objectInterface builtin)] libraryPrefix >>= require;
    builtinObject <- readObject builtinPrefix;
    libraryObject <- readObject libraryPrefix;
    raw <- require (Prepared.prepareFresh identity preludeMode recorded [builtinObject, libraryObject]);
    let { destination = J.getText "generated_source" "" request };
    writeFile destination (generated raw);
    digest <- fileDigest destination;
    writeFile (directory ++ "/generation.json") (J.render (J.object [
      (,) "format" (J.str "MLF-PREPARED-LIBRARY-GENERATION-1"),
      (,) "input_identity" (J.str identity), (,) "schema" (J.str Prepared.librarySchema),
      (,) "source_package" (J.str "main"),
      (,) "modules" (J.stringArray (map Modules.moduleIdentity sources)),
      (,) "source_paths" (J.stringArray (map Modules.sourcePath sources)),
      (,) "source_sha256" (J.stringArray (map Prepared.sourceHash recorded)),
      (,) "binding_names" (J.stringArray (map fst (Artifact.crateBindings
        (Artifact.objectInterface (Prepared.libraryObject libraryObject))))),
      (,) "class_names" (J.stringArray (map Modules.className (Artifact.crateClasses
        (Artifact.objectInterface (Prepared.libraryObject libraryObject))))),
      (,) "artifacts" (J.array [artifactRecord builtinPrefix builtinObject, artifactRecord libraryPrefix libraryObject]),
      (,) "generated_source" (J.str destination), (,) "generated_sha256" (J.str digest),
      (,) "user_program_cache" (J.Boolean False), (,) "native_object_reuse" (J.Boolean False)
    ]));
    putStrLn destination
  };
  main = do {
    count <- getArgCount;
    if count /= 1 then fatal "usage: generate-prepared-libraries REQUEST.json" else do {
      path <- getArg 0;
      request <- J.read path;
      run request
    }
  }
}
