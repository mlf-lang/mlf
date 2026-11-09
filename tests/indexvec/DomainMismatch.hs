-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import qualified Bootstrap.IndexVec as V;
  data Declaration = Declaration;
  data Package = Package;
  wrong :: V.IndexVec Declaration Int -> V.Index Package -> Int;
  wrong nodes package = V.at nodes package;
  main :: IO ();
  main = printInt (wrong (V.fromList [1]) (V.fromInt 0))
}
