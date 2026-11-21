-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  emit text = do { printInt (stringUtf8Length text); printInt (stringLength text) };
  main = do {
    mode <- getArg 0;
    if eqString mode "argument" then emit (panic "text-first")
    else if eqString mode "invalid" then emit (stringFromCode 55296)
    else if eqString mode "unused" then printInt (if True then 42 else stringUtf8Length (panic "unused"))
    else if eqString mode "scalar" then do { value <- getArg 1; emit (stringFromCode (readInt value)) }
    else do {
      value <- getArg 1;
      let { text = S.concatStrings (S.replicate (readInt value) ("aα中😀" ++ stringFromCode 0)) };
      if eqString mode "slice" then do {
        start <- getArg 2; count <- getArg 3;
        emit (stringSlice text (readInt start) (readInt count))
      } else emit text
    }
  }
}
