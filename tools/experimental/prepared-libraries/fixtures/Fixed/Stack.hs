-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Fixed.Stack (stackText, unsignedText) where {
  import MLF.Primitive;
  leaf :: HasCallStack => Int -> CallStack;
  leaf x = callStack;
  forward :: HasCallStack => Int -> CallStack;
  forward x = leaf x;
  stackText :: HasCallStack => Int -> String;
  stackText x = textFromChars (prettyCallStack (forward x));
  unsignedText x = textFromChars (prettyCallStack (leaf x))
}
