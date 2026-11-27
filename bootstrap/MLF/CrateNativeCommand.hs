-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.CrateNativeCommand
  (Plan, arguments, emitLibrary, emitFile, emitRetained, nativeContract, nativeContractHeader,
   Program, programChunks, programObjects, programDecisions, emitDependencies) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as SourceMap;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.CrateCodegen as CrateCodegen;
  import qualified Bootstrap.NativeCrate as NativeCrate;
  import qualified Bootstrap.LLVM as LLVM;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Package.DependencyMode as DependencyMode;
  import qualified Package.NativeArtifact as NativeArtifact;
  import qualified Package.Json as J;

  fatal message = ioBind (putErr (message ++ "\n")) (\_ -> exitWith 1);
  requireResult :: forall a. Either String a -> IO a;
  requireResult result = case result of { Left message -> fatal message; Right value -> ioReturn value };
  data Plan = Plan String String String;
  arguments options = case options of {
    ["--native-dependencies", path, "--native-plan-sha256", digest, "--native-target", target, "--native-report", report] ->
      Just ((,) (Plan path digest target) report);
    _ -> Nothing
  };
  nativeContractHeader owner identity = J.object [
    (,) "format" (J.str NativeArtifact.crateFormat), (,) "export_abi" (J.str NativeCrate.nativeABI),
    (,) "runtime_abi" (J.str LLVM.runtimeAbi), (,) "crate_id" (J.str owner), (,) "identity" (J.str identity)];
  nativeContract contract = let {
    binding slot ((,) key ty) = J.object [
      (,) "slot" (J.num slot), (,) "key" (J.str key), (,) "type" (J.str (Pretty.prettyType ty))];
    bindings rows = J.array (L.mapIndexed binding rows);
    tag ((,) name ((,) index arity)) = J.object [
      (,) "name" (J.str name), (,) "tag" (J.num index), (,) "arity" (J.num arity)];
    header = nativeContractHeader (NativeCrate.contractCrate contract) (NativeCrate.contractIdentity contract)
  } in J.set "status" (J.str "eligible")
    (J.set "constructor_tags" (J.array (L.map tag (NativeCrate.contractTags contract)))
      (J.set "imports" (bindings (NativeCrate.contractImports contract))
        (J.set "exports" (bindings (NativeCrate.contractExports contract)) header)));
  emitLibrary file identity report = do {
    if CrateCodegen.validDigest identity then ioReturn () else fatal "invalid native crate identity";
    (,) rows root <- ioBind (CrateCodegen.loadNativeFile file) requireResult;
    let { owner = Artifact.crateId (Artifact.objectInterface root) };
    result <- requireResult (NativeCrate.emitLibrary identity (L.map L.snd rows) root);
    case result of {
      Left reason -> do {
        J.write report (J.set "status" (J.str "unsupported")
          (J.set "reason" (J.str reason) (nativeContractHeader owner identity)));
        ioReturn []
      };
      Right ((,) chunks contract) -> do {
        J.write report (nativeContract contract);
        ioReturn chunks
      }
    }
  };
  data Program = Program ([] String) ([] J.Json) ([] DependencyMode.Decision);
  programChunks (Program chunks _ _) = chunks;
  programObjects (Program _ objects _) = objects;
  programDecisions (Program _ _ rows) = rows;
  decision :: (,,) String String String -> DependencyMode.Decision;
  decision ((,,) crate mode reason) = DependencyMode.Decision crate
    (case mode of { "native" -> DependencyMode.Native; "unused" -> DependencyMode.Unused; _ -> DependencyMode.CheckedIR }) reason;
  saveProgram report (Program chunks objects choices) = do {
    let { selected = L.mapMaybe (\row -> case row of {
            DependencyMode.Decision crate DependencyMode.Native _ -> Just crate; _ -> Nothing }) choices;
          modes = J.object [(,) "format" (J.str NativeArtifact.reportFormat), (,) "selected" (J.stringArray selected),
            (,) "dependency_modes" (J.array (L.map DependencyMode.json choices))] };
    J.write report (J.set "objects" (J.array objects) modes);
    ioReturn chunks
  };
  emitFile plan report file = do {
    (,) rows root <- ioBind (CrateCodegen.loadNativeFile file) requireResult;
    emitPinned plan report SourceMap.empty rows root
  };
  emitRetained plan report prefix retained interfaces root = do {
    metadata <- canonicalPath (prefix ++ ".mlfci");
    let { iface = Artifact.objectInterface root };
    emitPinned plan report retained (L.snoc interfaces ((,) metadata iface)) root
  };
  -- Checking a root initially needs only its own checked object. The linker
  -- identifies reachable implementors from declaration references and native
  -- factory arguments, and requests checked bodies only when it needs them.
  emitPinned (Plan path digest target) report retained rows initial = do {
    pins <- ioBind (NativeArtifact.readPinnedPlan path digest target rows) requireResult;
    let { byCrate = SourceMap.fromList compareString (L.map (\pin -> (,) (NativeArtifact.pinnedCrate pin) pin) pins);
          findPin crate = SourceMap.lookup compareString crate byCrate;
          headers = L.map L.snd rows;
          locations = SourceMap.fromList compareString (L.map (\row -> (,) (Artifact.crateId (L.snd row)) row) rows);
          load ((,) crate why) = case SourceMap.lookup compareString crate locations of {
            Nothing -> ioReturn (Left ("unknown implementation: " ++ crate));
            Just row -> do {
              result <- case findPin crate of {
                Nothing -> Artifact.readClosureObject Nothing retained headers row;
                Just pin -> case NativeArtifact.pinnedChecked pin of {
                  Nothing -> ioReturn (Left "no checked fallback is pinned");
                  Just ((,) file expected) -> Artifact.readPinnedObjectWithInterfaces headers file expected (L.snd row)
                }
              };
              ioReturn (L.mapLeft (\message -> crate ++ ": " ++ why ++ "; " ++ message) result)
            }
          }
    };
    result <- ioBind (emitDependencies pins headers load initial) requireResult;
    saveProgram report result
  };
  -- Disk package plans and installed compiler registries differ only in how
  -- they authenticate providers and obtain a requested checked body. Selection,
  -- mixed linking, fallback and final object revalidation are shared here.
  emitDependencies :: [] NativeArtifact.Pinned -> [] Artifact.CrateInterface ->
    ((,) String String -> IO (Either String Artifact.CrateObject)) -> Artifact.CrateObject ->
    IO (Either String Program);
  emitDependencies pins headers load initial = let {
          root = Artifact.crateId (Artifact.objectInterface initial);
          byCrate = SourceMap.fromList compareString (L.map (\pin -> (,) (NativeArtifact.pinnedCrate pin) pin) pins);
          findPin crate = SourceMap.lookup compareString crate byCrate;
          request pin = let { contract = NativeArtifact.pinnedContract pin;
                              keys = L.either (\_ -> []) (\saved -> L.map (J.getText "key" "")
                                (J.values (J.get "imports" saved))) contract } in
            (,,) (NativeArtifact.pinnedCrate pin) (NativeArtifact.pinnedIdentity pin) keys;
          requests = L.map request pins;
          verify expected = case findPin (NativeCrate.contractCrate expected) of {
            Nothing -> Left "missing native provider pin";
            Just pin -> do {
              contract <- NativeArtifact.pinnedContract pin;
              L.ensure (J.equal contract (nativeContract expected)) "native producer contract differs from checked interface layouts"
            }
          };
          -- A combined ABI failure may admit several fallback choices. Load
          -- one available body, then let reachability and compatibility settle
          -- again before requiring another native-only provider to fall back.
          available pending failure = case pending of {
            [] -> ioReturn (Left failure);
            (:) row rest -> do {
              result <- load row;
              case result of {
                Right body -> ioReturn (Right [(,) row body]);
                Left message -> available rest (if eqString failure "" then message else failure)
              }
            }
          };
          allBodies pending = case pending of {
            [] -> ioReturn (Right []);
            (:) row rest -> do {
              result <- load row;
              case result of {
                Left message -> ioReturn (Left message);
                Right body -> do {
                  later <- allBodies rest;
                  ioReturn (L.mapEither ((:) ((,) row body)) later)
                }
              }
            }
          };
          run bodies loadedCrates = do {
            case NativeCrate.emitProgramFromInterfaces verify requests headers bodies root of {
              Left message -> ioReturn (Left message);
              Right step -> case step of {
              Right ((,) chunks decisions) -> do {
                let { used = L.mapMaybe (\((,,) crate mode _) -> if eqString mode "native" then findPin crate else Nothing) decisions };
                files <- L.mapM selectedObject used;
                ioReturn (L.mapEither (\objects -> Program chunks objects (L.map decision decisions))
                  (L.traverseEither (\value -> value) files))
              };
              Left [] -> ioReturn (Left "native dependency resolution made no progress");
              Left wanted -> do {
                let { fresh = L.filter (\row -> L.not (SourceMap.member compareString (L.fst row) loadedCrates)) wanted;
                      ordinary = L.filter (L.compose L.isNothing (L.compose findPin L.fst)) fresh };
                if L.null fresh then ioReturn (Left ("native dependency fallback made no progress: " ++ L.fst (L.head wanted))) else do {
                  loaded <- if L.null ordinary then available fresh "" else allBodies ordinary;
                  case loaded of {
                    Left message -> ioReturn (Left message);
                    Right entries -> run (L.append (L.map L.snd entries) bodies)
                      (SourceMap.union compareString (SourceMap.fromList compareString (L.map L.fst entries)) loadedCrates)
                  }
                }
              }
            } }
          }
    } in run [initial] SourceMap.empty;
  selectedObject pin = do {
    let { crate = NativeArtifact.pinnedCrate pin; object = NativeArtifact.pinnedObject pin;
          path = L.fst object; digest = L.snd object };
    current <- NativeArtifact.digestFile path;
    ioReturn (do {
      actual <- current;
      L.ensure (eqString actual digest) (crate ++ ": native object changed during code generation");
      Right (J.object [(,) "dependency" (J.str crate), (,) "path" (J.str path), (,) "sha256" (J.str digest)])
    })
  }
}
