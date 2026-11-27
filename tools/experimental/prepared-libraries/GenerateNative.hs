-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.PreparedLibraries as Prepared;
  import qualified Bootstrap.NativeCrate as Native;
  import qualified Bootstrap.LLVM as LLVM;
  import qualified MLF.CrateNativeCommand as Command;
  import qualified MLF.PreparedLibraryData as Data;
  import qualified Package.Json as J;
  fatal :: forall a. String -> IO a;
  fatal message = do { putErr (message ++ "\n"); exitWith 1; panic "exitWith returned" };
  require :: forall a. Either String a -> IO a;
  require result = case result of { Left message -> fatal message; Right value -> ioReturn value };
  emit :: String -> [] Artifact.CrateInterface -> (,) Int ((,) Prepared.LibraryObject Artifact.CrateObject) -> IO J.Json;
  emit directory headers ((,) index ((,) recorded object)) = do {
    let {
          owner = Artifact.crateId (Artifact.objectInterface object);
          identity = Prepared.objectHash recorded;
          filename = "library-" ++ showInt index ++ ".ll" };
    result <- require (Native.emitLibrary identity headers object);
    case result of {
      Left reason -> ioReturn (J.object [(,) "contract" (J.set "status" (J.str "unsupported")
        (J.set "reason" (J.str reason) (Command.nativeContractHeader owner identity))), (,) "llvm" J.Null]);
      Right ((,) chunks contract) -> do {
        writeFile (directory ++ "/" ++ filename) (concatStrings chunks);
        ioReturn (J.object [(,) "contract" (Command.nativeContract contract), (,) "llvm" (J.str filename)])
      }
    }
  };
  main :: IO ();
  main = do {
    count <- getArgCount;
    if count /= 2 then fatal "usage: GenerateNative OUTPUT_DIRECTORY METADATA_OUTPUT" else ioReturn ();
    directory <- getArg 0;
    manifest <- getArg 1;
    raw <- require (case Data.libraries of { [value] -> Right value; _ -> Left "native installation requires one prepared source inventory" });
    objects <- Prepared.readLibraryObjects raw >>= require;
    let { recorded = zip (Prepared.libraryObjects raw) objects;
          headers = map Artifact.objectInterface objects;
          providers = sortBy (\a b -> compareString
            (Artifact.crateId (Prepared.libraryInterface (fst a)))
            (Artifact.crateId (Prepared.libraryInterface (fst b))))
            (filter (\entry -> not (eqString Artifact.builtinCrateIdentity
              (Artifact.crateId (Prepared.libraryInterface (fst entry))))) recorded) };
    rows <- mapM (emit directory headers) (zip (range 0 (length providers - 1)) providers);
    writeFile manifest (J.render (J.object [
      (,) "format" (J.str "MLF-NATIVE-INSTALLATION-1"),
      (,) "identity" (J.str (Prepared.inputIdentity raw)),
      (,) "export_abi" (J.str Native.nativeABI),
      (,) "runtime_abi" (J.str LLVM.runtimeAbi),
      (,) "providers" (J.array rows)]) ++ "\n")
  }
}
