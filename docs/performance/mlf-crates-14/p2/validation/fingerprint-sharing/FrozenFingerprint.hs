-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module FrozenFingerprint where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Host as Host;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Fresh as Fresh;
  import qualified Bootstrap.CompilerCore as Compiler;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.SourceEquality as Equality;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Parser as XP;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.Separate as Separate;
  import Bootstrap.CrateArtifact hiding (encodeInterface, decodeInterface, makeObject, encodeObject, writeObject);
  oldEncodeInterface iface =
    let {
      fields = interfaceFields iface
    } in
    Separate.pack (snoc fields (oldFingerprint (Separate.pack fields)));

  oldDecodeInterface :: String -> Either String CrateInterface;
  oldDecodeInterface input = do {
    fields <- Separate.unpack input;
    case fields of {
      [tag, identity, deps, modules, exports, imports, metadata, instanceNames,
       layouts, bindings, entry, bodyHash, protectionField, checksum] -> do {
        ensure (eqString tag "MLFCI-5") "unsupported crate metadata epoch (expected MLFCI-5)";
        ensure (eqString checksum (oldFingerprint (Separate.pack (interfacePrefix fields))))
          "crate metadata checksum mismatch";
        dependencies <- bindEither (Separate.unpack deps) (traverseEither decodeDependency);
        owned <- Separate.unpack modules;
        exported <- decodeExports exports;
        reach <- decodeImports imports;
        source <- Parser.parseMetadataModule "<crate metadata>"
          ("module CrateMetadata where {\n" ++ metadata ++ "\n}");
        lowered <- Parser.parseMetadataModule "<crate layout metadata>"
          ("module CrateLayouts where {\n" ++ layouts ++ "\n}");
        names <- Separate.unpack instanceNames;
        schemes <- decodeBindings bindings;
        protection <- decodeProtection protectionField;
        ensure (length names == length (Modules.sourceInstances source))
          "crate instance metadata count mismatch";
        ensure (null (Modules.sourceValues source) && null (Modules.sourceImports source) &&
          null (Modules.sourceValues lowered) && null (Modules.sourceImports lowered) &&
          null (Modules.sourceClasses lowered) && null (Modules.sourceInstances lowered))
          "crate metadata contains executable declarations";
        let { iface = CrateInterface identity dependencies owned exported reach
          (Modules.sourceDatatypes source) (Modules.sourceClasses source)
          (zip names (map Separate.stripInstance (Modules.sourceInstances source)))
          (Modules.sourceDatatypes lowered) schemes entry bodyHash protection };
        validateInterface iface;
        ensure (eqString input (oldEncodeInterface iface)) "noncanonical crate metadata";
        Right iface
      };
      _ -> Left "unsupported or malformed crate metadata (expected MLFCI-5)"
    }
  };

  oldMakeObject iface fragments =
    CrateObject (withObjectFingerprint iface (oldFingerprint (oldEncodePooledPayload fragments))) fragments;

  oldEncodeObject object =
    case object of {
      CrateObject iface fragments ->
        Separate.pack
          ((:) "MLFCO-2"
             ((:) (crateId iface)
                ((:) (oldFingerprint (oldEncodeInterface iface))
                   ((:) (oldEncodePooledPayload fragments) []))));
      LegacyCrateObject iface fragments ->
        Separate.pack
          ((:) "MLFCO-1"
             ((:) (crateId iface)
                ((:) (oldFingerprint (oldEncodeInterface iface))
                   ((:) (Separate.pack (map oldEncodeFragment fragments)) []))))
    };

  oldWriteObject prefix object =
    do {
      writeFile (prefix ++ ".mlfco") (oldEncodeObject object);
      writeFile (prefix ++ ".mlfci") (oldEncodeInterface (objectInterface object));
      ioReturn ()
    };
  oldFingerprintFrom :: String -> Int -> Int -> Int -> String;
  oldFingerprintFrom text i a b =
    if (i >= stringLength text)
    then (showInt a ++ ("-" ++ showInt b))
    else let {
           code = stringCodeAt text i
         } in
         let {
           nextA = (((a * 65599) + code) % 2147483647)
         } in
         let {
           nextB = (((b * 131) + code) % 2147483629)
         } in
         seq nextA (seq nextB (oldFingerprintFrom text (i + 1) nextA nextB));
  oldFingerprint text = oldFingerprintFrom text 0 0 1;
  -- Exact summaries of the two existing rolling checksums. A summary composes
  -- with any initial state, so shared datatype prefixes need not be rescanned
  -- for every independently checked fragment. The serialized digest is unchanged.
  oldFingerprintStateFrom :: String -> Int -> Int -> Int -> (,) Int Int;
  oldFingerprintStateFrom text i a b =
    if (i >= stringLength text)
    then (,) a b
    else let {
           code = stringCodeAt text i
         } in
         let {
           nextA = (((a * 65599) + code) % 2147483647)
         } in
         let {
           nextB = (((b * 131) + code) % 2147483629)
         } in
         seq nextA (seq nextB (oldFingerprintStateFrom text (i + 1) nextA nextB));
  oldFingerprintPower :: Int -> Int -> Int -> Int;
  oldFingerprintPower base count modulus =
    if (count == 0)
    then 1
    else let {
           half = oldFingerprintPower base (quotInt count 2) modulus
         } in
         let {
           squared = ((half * half) % modulus)
         } in
         if ((count % 2) == 0) then squared else ((squared * base) % modulus);
  oldFingerprintPart :: String -> (,,,) Int Int Int Int;
  oldFingerprintPart text =
    case oldFingerprintStateFrom text 0 0 0 of {
      (,) a b ->
        (,,,) (oldFingerprintPower 65599 (stringLength text) 2147483647)
          (oldFingerprintPower 131 (stringLength text) 2147483629)
          a
          b
    };
  oldFingerprintAppend :: (,) Int Int -> (,,,) Int Int Int Int -> (,) Int Int;
  oldFingerprintAppend ((,) a b) ((,,,) powerA powerB partA partB) =
    let {
      nextA = (((a * powerA) + partA) % 2147483647)
    } in
    let {
      nextB = (((b * powerB) + partB) % 2147483629)
    } in
    seq nextA (seq nextB ((,) nextA nextB));
  oldFingerprintAfter :: (,) Int Int -> String -> String;
  oldFingerprintAfter ((,) a b) text = oldFingerprintFrom text 0 a b;

  oldEncodeContextualObject :: Separate.UnitObject -> String;
  oldEncodeContextualObject object =
    let {
      body = Pretty.prettyTerm (Separate.objectBody object)
    } in
    let {
      header = Separate.withInterfaceData (Separate.objectInterface object) [] (oldFingerprint body)
    } in
    Separate.pack ((:) "MLFF-2" ((:) (Separate.encodeInterface header) ((:) body [])));
  oldUnitEncodeObject object =
    let {
      i = Separate.objectInterface object
    } in
    Separate.pack
      ((:) "MLFO-1"
         ((:) (Separate.unitName i)
            ((:) (oldFingerprint (Separate.pack (Separate.interfaceFields i))) ((:) (Pretty.prettyTerm (Separate.objectTerm object)) []))));
  oldEncodeFragment fragment =
    Separate.pairEncoding
      ((,) (Separate.encodeInterface (Separate.objectInterface fragment))
         (oldUnitEncodeObject fragment));
  oldPoolRecords :: Map String ([] ((,) DataDecl String)) ->
                 [] Separate.UnitObject ->
                 [] PoolRecord ->
                 (,) (Map String ([] ((,) DataDecl String))) ([] PoolRecord);
  oldPoolRecords pool fragments done =
    case fragments of {
      [] -> (,) pool (reverse done);
      (:) fragment rest ->
        case rememberTypes pool (Separate.unitData (Separate.objectInterface fragment)) of {
          (,) afterHeader header ->
            case rememberTypes afterHeader (Separate.objectContext fragment) of {
              (,) afterBody body ->
                oldPoolRecords afterBody rest
                  ((:) (PoolRecord header body (oldEncodeContextualObject fragment)) done)
            }
        }
    };
  oldEncodePooledPayload :: [] Separate.UnitObject -> String;
  oldEncodePooledPayload fragments =
    case oldPoolRecords M.empty fragments [] of {
      (,) inventory records ->
        let {
          declarations =
            Set.toList (Set.fromList compareString (concatMap (map snd) (M.elems inventory)))
        } in
        let {
          numbers = M.fromList compareString (zip declarations (range 0 (length declarations - 1)))
        } in
        Separate.pack
          ((:) (Separate.pack declarations)
             ((:) (Separate.pack (map (encodePoolRecord numbers) records)) []))
    };
}
