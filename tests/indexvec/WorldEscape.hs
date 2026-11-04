-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  invalid :: STArray IOWorld Int -> Int;
  invalid array = runST (readSTArray array 0);
  main :: IO ();
  main = printInt 0
}
