-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main (main) where {
import MLF.Primitive;
compose :: forall a b c. (b -> c) -> (a -> b) -> a -> c;
compose f g y = f (g y);
step :: Int -> Int;
step y = addInt y 1;
identity :: forall a. a -> a;
identity y = y;
entry :: Int -> Int;
entry x = (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (compose step (identity))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))))) x;

main :: IO ();
main = ioBind (getArg 0) (\text -> printInt (entry (readInt text)))
}
