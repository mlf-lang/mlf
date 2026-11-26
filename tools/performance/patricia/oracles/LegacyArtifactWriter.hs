{-# LANGUAGE NoImplicitPrelude, OverloadedStrings #-}
module LegacyArtifactWriter (module A, writeObject, writeObjectWithPayload) where {
  import MLF.Primitive;
  import qualified Prelude as Host;
  import Bootstrap.CrateArtifact as A hiding (writeObject, writeObjectWithPayload);
  legacyOnly object = case object of {
    CrateObject _ _ -> object; LegacyCrateObject _ _ -> object;
    EnvelopeCrateObject _ _ _ -> Host.errorWithoutStackTrace "legacy writer projection excludes envelope objects"
  };
  writeObject prefix object =
    let {
      interfaceText = encodeInterface (objectInterface object)
    } in
    do {
      writeFile (prefix ++ ".mlfco") (encodeObjectWithInterface (legacyOnly object) interfaceText);
      writeFile (prefix ++ ".mlfci") interfaceText;
      ioReturn ()
    };
  -- Only the new-object producer passes the exact paired payload obtained from
  -- makeObjectWithPayload. Loaded/legacy objects keep the general writer; no
  -- inference result or independently supplied checksum licenses text reuse.
  writeObjectWithPayload :: String -> CrateObject -> String -> IO ();
  writeObjectWithPayload prefix object payload =
    let {
      interfaceText = encodeInterface (objectInterface object);
      objectText = case object of {
        CrateObject iface _ -> encodePooledObject iface interfaceText payload;
        LegacyCrateObject _ _ -> encodeObjectWithInterface (legacyOnly object) interfaceText;
        EnvelopeCrateObject _ _ _ -> Host.errorWithoutStackTrace "legacy writer projection excludes envelope objects"
      }
    } in
    do {
      -- Keep the constructor case inside the lazy contents: filename checks
      -- must still precede demand of the object or its paired payload.
      writeFile (prefix ++ ".mlfco") objectText;
      writeFile (prefix ++ ".mlfci") interfaceText;
      ioReturn ()
    };
}
