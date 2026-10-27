-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Entry.CompilerTests where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Package.OS as O;
  import qualified Tests.CompilerTests as Tests;
  main :: IO ();
  main =
    do {
      O.setupWindows;
      args <- O.allArguments;
      Tests.main args
    }
}
