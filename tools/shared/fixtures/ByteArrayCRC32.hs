-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std (not);
  -- Constructing an IO value cannot force any of its three arguments.
  deferred = seq (byteArrayCRC32 (panic "array-demand")
    (panic "start-demand") (panic "count-demand")) (putStrLn "deferred");
  main = do {
    mode <- getArg 0;
    if eqString mode "defer" then deferred else do {
      bytes <- newByteArray 1 31;
      if eqString mode "array" then byteArrayCRC32 (panic "array-demand")
        (panic "start-demand") (panic "count-demand") >>= printInt
      else if eqString mode "start" then byteArrayCRC32 bytes
        (panic "start-demand") (panic "count-demand") >>= printInt
      else if eqString mode "bad-start" then byteArrayCRC32 bytes 2 (panic "count-demand") >>= printInt
      else if eqString mode "count" then byteArrayCRC32 bytes 0 (panic "count-demand") >>= printInt
      else if eqString mode "negative-start" then byteArrayCRC32 bytes (0 - 1) 0 >>= printInt
      else if eqString mode "negative-count" then byteArrayCRC32 bytes 0 (0 - 1) >>= printInt
      else if eqString mode "overflow-count" then byteArrayCRC32 bytes 1 9223372036854775807 >>= printInt
      else do {
        file <- getArg 1; start <- getArg 2; count <- getArg 3;
        result <- readByteFileOrError file 2097152;
        case result of { (,) message input ->
          if not (eqString message "") then panic message else do {
            let { action = byteArrayCRC32 input (readInt start) (readInt count) };
            first <- action;
            length <- lengthByteArray input;
            if length == 0 then ioReturn () else do {
              byte <- readByteArray input 0; writeByteArray input 0 (xorInt byte 255)
            };
            second <- action;
            digest <- byteArrayDigest input;
            putStrLn (showInt first ++ "," ++ showInt second ++ "," ++ digest)
          }
        }
      }
    }
  }
}
