-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Constraint as C;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.PreparedLibraries as Prepared;
  import qualified Bootstrap.LLVM.Library as Library;
  import qualified MLF.PreparedLibraryData as Data;
  import qualified Package.Json as J;
  fatal :: forall a. String -> IO a;
  fatal message = do { putErr (message ++ "\n"); exitWith 1; panic "exitWith returned" };
  require :: forall a. Either String a -> IO a;
  require result = case result of { Left message -> fatal message; Right value -> ioReturn value };
  text :: String -> J.Json;
  text = J.String;
  metadata :: Library.ExportLayout -> J.Json;
  metadata layout = J.Object [
    (,) "format" (text "MLF-NATIVE-LIBRARY-1"),
    (,) "identity" (text (Library.identity layout)),
    (,) "export_abi" (text "mlf-native-typed-tuple/2"),
    (,) "exports" (J.Array (zipWith (\slot ((,,) key hint ty) -> J.Object [
      (,) "key" (text key), (,) "hint" (text hint),
      (,) "type" (text (Pretty.prettyType ty)), (,) "slot" (J.Number (showInt slot))])
      (range 0 (length (Library.exports layout) - 1)) (Library.exports layout))),
    (,) "declarations" (J.Array (map (\d -> text (D.prettyDeclaration d)) (Library.declarations layout))),
    (,) "reserved_type_names" (J.Array (map text (Library.reservedTypeNames layout))),
    (,) "constructor_tags" (J.Array (map (\((,) name ((,) tag arity)) -> J.Object [
      (,) "name" (text name), (,) "tag" (J.Number (showInt tag)), (,) "arity" (J.Number (showInt arity))])
      (M.toList (Library.constructorTags layout))))
  ];
  main :: IO ();
  main = do {
    count <- getArgCount;
    if count /= 2 then fatal "usage: GenerateNative LLVM_OUTPUT METADATA_OUTPUT" else ioReturn ();
    output <- getArg 0;
    manifest <- getArg 1;
    raw <- require (case Data.libraries of { [value] -> Right value; _ -> Left "native installation requires one fixed library registry" });
    installed <- require (Prepared.nativeLibrary raw);
    ds <- require (Prepared.nativeLibraryDeclarations raw);
    let { linked = case installed of { (,,) value _ _ -> value };
          signatures = Prepared.nativeExportSignatures raw };
    let { entries = map (\((,) key ty) -> (,,) key (C.targetNameHint key) ty) signatures };
    base <- require (Library.prepareLayout (Prepared.inputIdentity raw) entries ds);
    names <- require (Library.libraryTypeNames base linked);
    layout <- require (Library.prepareLayoutWithTypeNames (Prepared.inputIdentity raw) entries ds names);
    generated <- require (Library.emitLibrary layout linked);
    writeFile output (concatStrings generated);
    writeFile manifest (J.render (metadata layout) ++ "\n")
  }
}
