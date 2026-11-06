-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.PreparedNativeData
  (enabled, identity, manifestPath, manifestSHA, objectPaths,
   targetTriple, dataLayout, primitiveABI, exportABI, reservedTypeNames) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  -- Installation replaces only this sealed consumer registry after independent
  -- regeneration of the fixed library, runtime and complete native manifest.
  enabled :: Bool;
  enabled = False;
  identity :: String;
  identity = "";
  manifestPath :: String;
  manifestPath = "";
  manifestSHA :: String;
  manifestSHA = "";
  objectPaths :: [] ((,) String String);
  objectPaths = [];
  targetTriple :: String;
  targetTriple = "";
  dataLayout :: String;
  dataLayout = "";
  primitiveABI :: String;
  primitiveABI = "";
  exportABI :: String;
  exportABI = "";
  reservedTypeNames :: [] String;
  reservedTypeNames = []
}
