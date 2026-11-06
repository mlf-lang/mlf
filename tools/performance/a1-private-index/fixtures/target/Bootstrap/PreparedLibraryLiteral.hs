-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.PreparedLibraryLiteral (rawLibrary) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.BuiltinPreludeLiteral as L;
  import qualified Bootstrap.PreparedLibraries as P;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.Separate as Separate;

  -- Lossless constructor serialization; no checked witness is serialized.
  -- Both host compilers consume the same canonical generated source module.
  unitInterface value = case value of {
    Separate.UnitInterface identity dependencies exports declarations classes instances bindings fingerprint ->
      L.application "UnitInterface" [L.string identity, L.list (L.pair L.string L.string) dependencies,
        L.list L.entity exports, L.list L.declaration declarations, L.list L.sourceClass classes,
        L.list (L.pair L.string L.sourceInstance) instances,
        L.list (L.pair L.string L.typeLiteral) bindings, L.string fingerprint]
  };
  fragment value = L.application "UnitObject"
    [unitInterface (Separate.objectInterface value), L.term (Separate.objectTerm value)];
  object value = case value of {
    Artifact.CrateObject iface fragments -> L.application "CrateObject"
      [L.interface iface, L.list fragment fragments];
    Artifact.LegacyCrateObject iface fragments -> L.application "LegacyCrateObject"
      [L.interface iface, L.list fragment fragments]
  };
  source value = case value of {
    P.LibrarySource identity path text digest syntax -> L.application "LibrarySource"
      [L.string identity, L.string path, L.string text, L.string digest, L.sourceSyntax syntax]
  };
  recordedObject value = case value of {
    P.LibraryObject metadata digest body -> L.application "LibraryObject"
      [L.string metadata, L.string digest, object body]
  };
  mode :: PreludeMode -> String;
  mode value = case value of {
    ImplicitPrelude -> "ImplicitPrelude";
    NoImplicitPrelude -> "NoImplicitPrelude"
  };
  rawLibrary value = case value of {
    P.RawLibrary identity schema prelude sources objects witnesses -> L.application "RawLibrary"
      [L.string identity, L.string schema, mode prelude, L.list source sources, L.list recordedObject objects,
       L.list L.sourceModule witnesses]
  }
}
