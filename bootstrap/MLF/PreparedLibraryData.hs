-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.PreparedLibraryData (libraries) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.PreparedLibraries as Libraries;

  -- Admission remains disabled until ordinary-provenance generation and the
  -- independent source/native controls qualify a fixed library closure.
  libraries :: [] Libraries.RawLibrary;
  libraries = []
}
