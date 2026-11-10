-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Model (Token(..), Score(..), Box(..), unbox) where {
  import MLF.Primitive;
  data Token = Token Int;
  class Score a where { score :: a -> Int };
  data Box a = Box a;
  unbox :: forall a. Box a -> a;
  unbox value = case value of { Box item -> item };
  hidden :: Int;
  hidden = 99
}
