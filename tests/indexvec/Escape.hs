-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import qualified Bootstrap.IndexVec as V;
  data Row = Row;
  escape :: forall s. V.Builder s Row Int;
  escape = runST V.new;
  main :: IO ();
  main = printInt (runST (V.size escape))
}
