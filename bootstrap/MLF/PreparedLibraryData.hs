-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.PreparedLibraryData (libraries, parseLibrary) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.PreparedLibraries as Libraries;
  import qualified Bootstrap.Parser as Parser;

  -- Admission remains disabled until ordinary-provenance generation and the
  -- independent source/native controls qualify a fixed library closure.
  libraries :: [] Libraries.RawLibrary;
  libraries = [];
  -- The disabled registry always uses the ordinary parser. Populated compiler
  -- builds independently regenerate the private exact-source parse inventory.
  parseLibrary :: String -> String -> Either String SourceModule;
  parseLibrary = Parser.parseModule
}
