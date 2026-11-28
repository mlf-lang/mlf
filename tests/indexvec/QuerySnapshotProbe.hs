-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Bitstream as W;
  import qualified Bootstrap.QueryGraph as Q;
  import qualified Bootstrap.Map as M;
  saveColumns path nodes = case Q.encodeIndex "cfg" nodes of {
    Left e -> putStrLn ("W " ++ e);
    Right value -> do {
      encoded <- W.encode W.defaultLimits 6 [value];
      case encoded of {
        Left e -> panic e;
        Right bytes -> do {
          message <- writeByteFileOrError path bytes;
          if message == "" then byteArrayDigest bytes >>= putStrLn else panic message
        }
      }
    }
  };
  inspect path destination = do {
    (message,bytes) <- readByteFileOrError path 268435456;
    if message == "" then ioReturn () else panic message;
    do {
      decoded <- W.decodeGraph W.defaultLimits 6 bytes;
      case decoded of {
        Left e -> putStrLn ("E " ++ e);
        Right graph -> case Q.admitIndex "cfg" graph of {
          Left e -> putStrLn ("E " ++ e);
          Right ((,) nodes _) -> do {
            putStrLn "OK";
            printInt (M.size nodes);
            saveColumns destination nodes
          }
        }
      }
    }
  };
  main :: IO ();
  main = do { path <- getArg 0; destination <- getArg 1; inspect path destination }
}
