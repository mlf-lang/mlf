-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  emit value = printInt (if value then 1 else 0);
  load file = do {
    result <- readByteFileOrError file 2097152;
    case result of { (,) message input ->
      if eqString message "" then ioReturn input else panic message
    }
  };
  compareFiles leftFile rightFile = do {
    left <- load leftFile; right <- load rightFile;
    let { action = byteArrayEqual left right };
    first <- action;
    size <- lengthByteArray left;
    original <- if size == 0 then ioReturn 0 else readByteArray left 0;
    if size == 0 then ioReturn () else writeByteArray left 0 (xorInt original 255);
    second <- action;
    if size == 0 then ioReturn () else writeByteArray left 0 original;
    third <- action;
    -- Force only the action's constructor, then mutate before its first run.
    let { delayed = byteArrayEqual left right };
    seq delayed (ioReturn ());
    if size == 0 then ioReturn () else writeByteArray left 0 (xorInt original 255);
    late <- delayed;
    selfLeft <- byteArrayEqual left left; selfRight <- byteArrayEqual right right;
    emit first; emit second; emit third; emit late; emit selfLeft; emit selfRight
  };
  main = do {
    mode <- getArg 0;
    if eqString mode "defer" then seq
      (byteArrayEqual (panic "left-demand") (panic "right-demand")) (printInt 42)
    else if eqString mode "unused" then
      (if True then printInt 42 else byteArrayEqual (panic "unused-left") (panic "unused-right") >>= emit)
    else if eqString mode "left" then
      byteArrayEqual (panic "left-demand") (panic "right-demand") >>= emit
    else if eqString mode "right" then do {
      left <- newByteArray 0 0; byteArrayEqual left (panic "right-demand") >>= emit
    } else do {
      left <- getArg 1; right <- getArg 2; compareFiles left right
    }
  }
}
