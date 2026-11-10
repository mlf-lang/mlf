-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main (main) where {
  import MLF.Primitive;
  import Model;
  import Facade;
  main :: IO ();
  main = ioBind (putStrLn "split λ")
    (\ignored -> ioBind (printInt answer) (\ignored2 -> printInt (score (Token 40))))
}
