{-# LANGUAGE OverloadedStrings #-}
-- Private renamed codecs compare against the immutable checkpoint source.
module Main where
import Prelude
import qualified Control.Exception as E
import Control.Monad (forM_, unless, foldM)
import qualified Bootstrap.Types as T
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B
import qualified CandidateWire as C
import qualified LegacyWire as L

need label ok = unless ok (fail label)
expect label (T.Left e) = fail (label ++ ": " ++ B.unpack e)
expect _ (T.Right a) = pure a
old value = case value of
 C.VInt x -> L.VInt x
 C.VBits x -> L.VBits x
 C.VText x -> L.VText x
 C.VNode t xs -> L.VNode t (map old xs)
bytes array = P.lengthByteArray array >>= \n -> mapM (P.readByteArray array) [0..n-1]
-- Independent CRC32/ISO-HDLC vectors generated with Python zlib.crc32.
-- The input byte at i is (37*i+seed) mod 256, with header bytes 76..79 zero.
crcVectors :: [(P.Int,P.Int,P.Int)]
crcVectors = [
 (0,11,0),
 (0,53,0),
 (1,11,1171273221),
 (1,53,2226203566),
 (7,11,4017044273),
 (7,53,2845095205),
 (75,11,1054614140),
 (75,53,2823205938),
 (76,11,3314257388),
 (76,53,332117138),
 (77,11,2071710291),
 (77,53,3423655505),
 (79,11,2885569725),
 (79,53,2378810651),
 (80,11,1736040176),
 (80,53,1491791780),
 (81,11,134557315),
 (81,53,3907998892),
 (1023,11,4291182421),
 (1023,53,1854776408),
 (1024,11,2157300612),
 (1024,53,2859182987),
 (1025,11,2944787703),
 (1025,53,4268825261),
 (16383,11,4105262987),
 (16383,53,3673467443),
 (16384,11,3790947135),
 (16384,53,1891592789),
 (16385,11,4082626171),
 (16385,53,2680172991),
 (16386,11,872358011),
 (16386,53,50149707),
 (16387,11,250027362),
 (16387,53,4088718849),
 (16388,11,3244331206),
 (16388,53,1951206412),
 (32769,11,417468052),
 (32769,53,3546315975),
 (65537,11,1141312188),
 (65537,53,2530153874),
 (131075,11,3768389109),
 (131075,53,2350599702)]
observeChecksum :: IO P.Int -> IO (Either String P.Int)
observeChecksum action = do
 result <- E.try (action >>= E.evaluate) :: IO (Either E.SomeException P.Int)
 pure (either (Left . takeWhile (/='\n') . E.displayException) Right result)
crcControls = forM_ crcVectors $ \(size,seed,wanted) -> do
 array <- P.newByteArray size 0
 forM_ [0..size-1] $ \i -> P.writeByteArray array i ((37*i+seed) `mod` 256)
 actual <- C.checksum array size
 frozen <- L.checksum array size
 need "CRC agrees with independent vectors and frozen recurrence" (actual==wanted && frozen==wanted)
 forM_ [76..min 79 (size-1)] $ \i -> P.writeByteArray array i 255
 changed <- C.checksum array size
 need "checksum field is logically zero" (changed==wanted)
 a <- observeChecksum (C.checksum array (size+7))
 b <- observeChecksum (L.checksum array (size+7))
 need "CRC keeps frozen short-buffer failure behavior" (a==b)

main = do
 crcControls
 let scalars = [C.VInt x | x <- [minBound,-129,-128,-1,0,1,63,64,127,128,maxBound]] ++
       [C.VBits x | x <- [minBound,-1,0,1,0x7ff0000000000000,0x7ff8000000000001,maxBound]] ++
       [C.VText x | x <- ["","ascii","α😀\NUL","\x7f\x80\x7ff\x800\xd7ff\xe000\x10000\x10ffff"]]
     sets = [[],scalars] ++
       [[C.VNode (fromIntegral i) [C.VText (B.literal (show i)),C.VInt (fromIntegral i)] | i <- [1..n]]
          | n <- [1,2,3,4,7,8,9,15,16,17,255,256,257,512]] ++
       [[C.VNode 2147483647 (replicate n (C.VNode 17 scalars))] | n <- [0,1,7,128]]
 forM_ sets $ \values -> do
  current <- C.encode C.defaultLimits 7 values >>= expect "current encoder"
  baseline <- L.encode L.defaultLimits 7 (map old values) >>= expect "frozen encoder"
  x <- bytes current; y <- bytes baseline
  need "packed sections preserve every wire byte" (x == y)
  graph <- C.decodeGraph C.defaultLimits 7 current >>= expect "indexed decoder"
  full <- expect "independent full resource inventory" (C.graphResourceStats graph)
  work <- expect "root summary" (C.graphExpandedWork graph)
  need "summary retains expanded root charging" (work == C.resourceExpandedWork full)
 -- Force collisions independently of the hash function, including equal
 -- prefixes and all four entry kinds. Then check the ordinary hash route too.
 let entries = [C.EInt (-1),C.EBits (-1),C.EText 0,C.ENode 0 [],C.ENode 0 [0],C.ENode 0 [0,1]] ++
       [C.ENode 9 [0,fromIntegral i] | i <- [1..128::Int]]
     insert index (key,entry) = case C.internIndexedAt 0 entry index of
      C.ExistingEntry _ -> fail "unexpected equal collision entry"
      C.MissingEntry fill -> pure (fill key)
 collisions <- foldM insert C.emptyEntryIndex (zip [0..] entries)
 forM_ (zip [0..] entries) $ \(wanted,entry) -> case C.internIndexedAt 0 entry collisions of
  C.ExistingEntry actual -> need "exact equality in balanced collision bucket" (actual == wanted)
  _ -> fail "lost colliding entry"
 let sameHash = [C.EInt (C.mixEntry 1 0),C.EBits (C.mixEntry 2 0),C.EText (C.mixEntry 3 0)]
 need "authored hash collision" (all ((== 0) . C.entryHash) sameHash)
 natural <- foldM (\index (key,entry) -> case C.internIndexed entry index of
    C.MissingEntry fill -> pure (fill key)
    _ -> fail "hash used as equality") C.emptyEntryIndex (zip [0..] sameHash)
 forM_ (zip [0..] sameHash) $ \(wanted,entry) -> case C.internIndexed entry natural of
  C.ExistingEntry actual -> need "ordinary hash collision lookup" (actual == wanted)
  _ -> fail "lost natural collision"
 putStrLn "PASS frozen wire bytes, reference widths, expanded work and exact hash collisions"
