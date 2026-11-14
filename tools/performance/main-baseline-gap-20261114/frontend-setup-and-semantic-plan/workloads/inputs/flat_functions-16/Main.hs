-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main (main) where {
import MLF.Primitive;
f0 :: Int -> Int;
f0 x = addInt x 0;
f1 :: Int -> Int;
f1 x = addInt x 1;
f2 :: Int -> Int;
f2 x = addInt x 2;
f3 :: Int -> Int;
f3 x = addInt x 3;
f4 :: Int -> Int;
f4 x = addInt x 4;
f5 :: Int -> Int;
f5 x = addInt x 5;
f6 :: Int -> Int;
f6 x = addInt x 6;
f7 :: Int -> Int;
f7 x = addInt x 7;
f8 :: Int -> Int;
f8 x = addInt x 8;
f9 :: Int -> Int;
f9 x = addInt x 9;
f10 :: Int -> Int;
f10 x = addInt x 10;
f11 :: Int -> Int;
f11 x = addInt x 11;
f12 :: Int -> Int;
f12 x = addInt x 12;
f13 :: Int -> Int;
f13 x = addInt x 13;
f14 :: Int -> Int;
f14 x = addInt x 14;
f15 :: Int -> Int;
f15 x = addInt x 15;
entry :: Int -> Int;
entry x = addInt (addInt (addInt (addInt (f0 x) (f1 x)) (addInt (f2 x) (f3 x))) (addInt (addInt (f4 x) (f5 x)) (addInt (f6 x) (f7 x)))) (addInt (addInt (addInt (f8 x) (f9 x)) (addInt (f10 x) (f11 x))) (addInt (addInt (f12 x) (f13 x)) (addInt (f14 x) (f15 x))));

main :: IO ();
main = ioBind (getArg 0) (\text -> printInt (entry (readInt text)))
}
