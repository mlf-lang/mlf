-- SOURCE ONLY: uncompiled correctness fixture, NOT a timing measurement.
{-# LANGUAGE NoImplicitPrelude, OverloadedStrings #-}
module Main where
import MLF.Primitive
import Bootstrap.Types
import qualified Bootstrap.Bitstream as W

right x = case x of { Left e -> panic e; Right v -> ioReturn v }
check ok = if ok then ioReturn () else panic "codec control failed"
forceValues xs = case xs of
  [] -> ()
  v:vs -> forceValue v `seq` forceValues vs
forceValue v = case v of
  W.VInt n -> n `seq` ()
  W.VBits n -> n `seq` ()
  W.VText t -> forceText t 0
  W.VNode tag children -> tag `seq` forceValues children
forceText t i = if i == stringLength t then () else stringCodeAt t i `seq` forceText t (i+1)
equalBytes a b = do
  na <- lengthByteArray a
  nb <- lengthByteArray b
  check (na == nb)
  let loop i = if i == na then ioReturn () else do
        x <- readByteArray a i
        y <- readByteArray b i
        check (x == y)
        loop (i+1)
  loop 0
roundtrip bytes = do
  values <- W.decode W.defaultLimits 6 bytes >>= right
  forceValues values `seq` ioReturn ()
  -- Future measured encode interval starts only AFTER this forcing.
  blob <- W.encode W.defaultLimits 6 values >>= right
  -- Interval ends BEFORE comparison/decoding/digest or printing.
  equalBytes bytes blob
reject x = case x of { Left _ -> ioReturn (); Right _ -> panic "expected rejection" }
finite = do
  let values = [W.VInt (-1),W.VBits (-1),W.VText "",W.VText "aé中😀",W.VNode 7 [W.VText "shared",W.VText "shared"],W.VNode 8 []]
  forceValues values `seq` ioReturn ()
  bytes <- W.encode W.defaultLimits 6 values >>= right
  roundtrip bytes
  W.decode W.defaultLimits 5 bytes >>= reject
  blank <- newByteArray 0 0
  W.decode W.defaultLimits 6 blank >>= reject
  W.encode W.defaultLimits (-1) values >>= reject
  -- Mutate only fixture-owned output, never corpus bytes.
  crc <- readByteArray bytes 76
  writeByteArray bytes 76 (xorInt crc 1)
  W.decode W.defaultLimits 6 bytes >>= reject
main = do
  finite
  count <- getArgCount
  let loop i = if i == count then ioReturn () else do
        path <- getArg i
        (err,bytes) <- readByteFileOrError path 268435456
        check (err == "")
        roundtrip bytes
        loop (i+1)
  loop 0
  putStrLn "PASS codec-control"
