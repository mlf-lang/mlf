-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main (main) where {
import MLF.Primitive;
entry :: Int -> Int;
entry x = x;

main :: IO ();
main = ioBind (getArg 0) (\text -> printInt (entry (readInt text)))
}
