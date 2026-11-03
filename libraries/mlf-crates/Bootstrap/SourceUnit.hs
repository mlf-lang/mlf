-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.SourceUnit (SourceUnit, pending, object, contextual, admit) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.ArtifactStorage as Storage;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Pretty as Pretty;

  -- This receipt belongs to one immutable interface and its physically paired
  -- checked term. No deserializer, caller-supplied digest or separate flag
  -- can manufacture it. Ordinary input still follows full formal admission.
  data SourceUnit = Pending Separate.UnitObject | Admitted Separate.UnitInterface Checked.CheckedTerm;
  pending = Pending;
  object unit = case unit of {
    Pending raw -> raw; Admitted iface checked -> Separate.CheckedUnitObject iface checked
  };
  admit unit = case unit of {
    Admitted _ _ -> Right (object unit);
    Pending raw -> do {
      let { iface = Separate.objectInterface raw; term = Separate.objectTerm raw };
      Storage.validateUnitInterface iface;
      Storage.admit [Storage.AdmitTerm term];
      ensure (eqString (Separate.fingerprint (Pretty.prettyTerm term))
        (Separate.unitObjectFingerprint iface)) "module object checksum mismatch";
      checked <- Separate.objectChecked raw;
      Right (Separate.CheckedUnitObject iface checked)
    }
  };

  -- The stored checksum covers the body alone. The complete interface and
  -- XWithData term both acquire the same declarations; Pretty.termChunks
  -- prints each declaration followed by a newline and then the exact body.
  contextual header datatypes body = do {
    ensure (null (Separate.unitData header)) "contextual fragment contains an inline datatype header";
    Storage.admit [Storage.AdmitTerm body];
    let { encoded = Separate.encodingText (Pretty.prettyTerm body) };
    ensure (eqString (Separate.encodingFingerprint encoded) (Separate.unitObjectFingerprint header))
      "contextual fragment body checksum mismatch";
    let { prefix = Separate.fingerprintStateFrom (unlines (map D.prettyDeclaration datatypes)) 0 0 1;
          iface = Separate.withInterfaceData header datatypes (Separate.encodingAfter prefix encoded) };
    Storage.validateUnitInterface iface;
    Storage.admit [Storage.AdmitData False datatypes];
    checked <- Checked.check (XWithData datatypes body);
    Right (Admitted iface checked)
  }
}
