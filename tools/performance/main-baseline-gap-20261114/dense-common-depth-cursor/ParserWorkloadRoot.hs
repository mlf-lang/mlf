-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module ParserWorkloadRoot (main) where {
  import MLF.Primitive;
  import qualified Bootstrap.Parser as Parser;
  main :: Bool;
  main = True
}
