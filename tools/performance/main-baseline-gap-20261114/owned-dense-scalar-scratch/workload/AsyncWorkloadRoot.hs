-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module AsyncWorkloadRoot (main) where {
  import MLF.Primitive;
  import qualified Async.Task as Async;
  main :: Bool;
  main = True
}
