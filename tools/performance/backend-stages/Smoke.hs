-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main (main) where {
  import MLF.Primitive;
  data Box a = Box a;
  unbox :: forall a. Box a -> a;
  unbox value = case value of { Box item -> item };
  twice :: (Int -> Int) -> Int -> Int;
  twice f value = f (f value);
  step :: Int -> Int;
  step value = addInt value 1;
  main :: IO ();
  main = ioBind (putStrLn "backend λ")
    (\ignored -> printInt (unbox (Box (twice step 40))))
}
