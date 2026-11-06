-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.TestSources where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Module as Modules;
  import qualified Package.Json as J;
  import qualified Package.OS as O;
  import qualified Package.Manifest as M;
  -- Keep discovery and source compilation on the same ordered package roots.
  -- Compiler libraries may live in separate packages rather than bootstrap/.
  packageRoots :: M.PackageGraph -> [] String;
  packageRoots graph = S.map M.packageRoot (M.packages graph);
  portRoots :: M.PackageGraph -> [] String;
  portRoots graph = (:) (M.packageRoot (M.rootPackage graph) ++ "/tests") (packageRoots graph);
  portStateTypesMode :: String;
  portStateTypesMode = "state-types-split-v1";
  portStateTypesSource :: String;
  portStateTypesSource = "bootstrap/tests/StateTypes.emlf";
  portStateTypesIdentity :: M.PackageGraph -> String;
  portStateTypesIdentity graph = M.crateIdentity (M.rootPackage graph) "port-prepared-StateTypes";
  portStateTypesInputs :: M.PackageGraph -> IO J.Json;
  portStateTypesInputs graph = portDiscoveredInputs graph portStateTypesSource;
  portInferenceMode :: String;
  portInferenceMode = "inference-discovered-split-v1";
  portInferenceSource :: String;
  portInferenceSource = "bootstrap/tests/InferenceConformance.emlf";
  portInferenceIdentity :: M.PackageGraph -> String;
  portInferenceIdentity graph = M.crateIdentity (M.rootPackage graph) "port-prepared-InferenceConformance";
  portInferenceInputs :: M.PackageGraph -> IO J.Json;
  portInferenceInputs graph = portDiscoveredInputs graph portInferenceSource;
  portDiscoveredInputs :: M.PackageGraph -> String -> IO J.Json;
  portDiscoveredInputs graph entry = do {
    let { includes = portRoots graph };
    working <- canonicalPath ".";
    text <- readFile entry;
    source <- case Parser.parseModule entry text of {
      Left message -> O.fatal message; Right value -> ioReturn value
    };
    discovered <- Modules.loadModuleFilesWithEvidence includes source text;
    loaded <- case discovered of {
      Left message -> O.fatal message; Right value -> ioReturn value
    };
    -- The producer compares this order, spelling and captured parser text to
    -- the rows it actually compiles. Canonical paths are filesystem owners.
    rows <- S.mapM (\item -> do {
      let { parsed = Modules.loadedSource item; spelling = Modules.sourcePath parsed };
      canonical <- canonicalPath spelling;
      bytes <- byteArrayFromString (Modules.loadedText item);
      digest <- byteArrayDigest bytes;
      ioReturn ((,,,) (Modules.moduleIdentity parsed) spelling canonical digest)
    }) (Modules.loadedEntries loaded);
    ioReturn (J.Object [
      ((,) "cwd" (J.str working)), ((,) "entry" (J.str entry)),
      ((,) "includes" (J.stringArray includes)),
      ((,) "files" (J.Object (S.map (\((,,,) _ _ canonical digest) -> (,) canonical (J.str digest)) rows))),
      ((,) "loader_rows" (J.Array (S.map (\((,,,) name spelling canonical digest) ->
        J.stringArray [name, spelling, canonical, digest]) rows)))])
  };
  -- Re-run the compiler's module discovery before every cache lookup. Hashing a
  -- previously saved dependency list would miss a newly introduced shadow module.
  -- Prelude is built in: loadModuleFiles skips it, and the compiler identity
  -- supplied by the caller accounts for its semantics.
  sourceInputs :: [] String -> String -> IO J.Json;
  sourceInputs includes entry =
    do {
      working <- canonicalPath ".";
      text <- readFile entry;
      source <-
        case Parser.parseModule entry text of {
          Left message -> O.fatal message;
          Right value -> ioReturn value
        };
      discovered <- Modules.loadModuleFiles includes source;
      modules <-
        case discovered of {
          Left message -> O.fatal message;
          Right values -> ioReturn values
        };
      files <-
        S.mapM
          (\loaded ->
             do {
               path <- canonicalPath (Modules.sourcePath loaded);
               hash <- fileDigest path;
               ioReturn ((,) path (J.str hash))
             })
          modules;
      ioReturn
        (J.Object
           ((:) ((,) "cwd" (J.str working))
              ((:) ((,) "entry" (J.str entry))
                 ((:) ((,) "includes" (J.stringArray includes))
                    ((:) ((,) "files" (J.Object files)) [])))))
    }
}
