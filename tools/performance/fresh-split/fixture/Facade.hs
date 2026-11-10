-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Facade (answer) where {
  import MLF.Primitive;
  import Model;
  instance Score Token where { score value = case value of { Token n -> addInt n 2 } };
  answer :: Int;
  answer = score (Token (unbox (Box 40)))
}
