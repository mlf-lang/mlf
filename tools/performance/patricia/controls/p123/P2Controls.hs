{-# LANGUAGE OverloadedStrings #-}
module P2Controls where

import Control.Exception (evaluate, try)
import Control.Monad (forM_, unless)
import Data.Char (chr)
import Data.Word (Word32)
import qualified BinaryP2WriterControls as Binary
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.Separate as S
import qualified Bootstrap.Types as T
import qualified FingerprintReference as Reference
import qualified MLF.Host.Base as H

check label ok = unless ok (fail label)

fingerprints :: IO ()
fingerprints = do
  forM_ [("", "0-1"), ("a", "97-228"), ("abc", "807794980-3925645"),
         ("λ🙂", "62775623-270844"), ("\0\n", "10-17171")] $ \(text, expected) -> do
    check "literal digest" (H.unpack (S.fingerprint (H.literal text)) == expected)
    check "reference digest" (Reference.fingerprint text == expected)
  let alphabet = map chr [0, 10, 127, 128, 2047, 2048, 0xd7ff, 0xe000, 0xffff, 0x10000, 0x10ffff]
      stream :: Word32 -> [Word32]
      stream = iterate (\x -> 1664525 * x + 1013904223)
      generated seed = take (fromIntegral seed * 3) [alphabet !! fromIntegral (x `mod` 11) | x <- stream seed]
      bounds = [3, 4, 5, 31, 32, 33, 255, 256, 257, 1023, 1024, 1025, 4095, 4096, 4097]
      cases = ["", alphabet, "e\x0301", "nul\0\n"] ++ map generated [1..48]
              ++ [replicate n 'x' ++ end | n <- bounds, end <- ["", "🙂"]]
      seeds = [(0,1), (0,0), (17,29), (-17,-29), (2147483647,2147483629), (minBound,maxBound)]
  forM_ cases $ \chars -> do
    let value = H.literal chars
        size = length chars
        expected = Reference.fingerprint chars
    check "complete digest" (H.unpack (S.fingerprint value) == expected)
    forM_ seeds $ \seed@(a,b) ->
      forM_ [0, 1, size `div` 2, size, size+3] $ \offset -> do
        let state = Reference.state seed (drop offset chars)
        check "seeded suffix state" (S.fingerprintStateFrom value (fromIntegral offset) a b == state)
        check "seeded suffix digest" (H.unpack (S.fingerprintFrom value (fromIntegral offset) a b) == Reference.render state)
    let (left,right) = splitAt (size `div` 2) chars
        state = Reference.state (0,1) left
        suffix = H.literal right
    check "digest after prefix" (H.unpack (S.fingerprintAfter state suffix) == expected)
    check "composed suffix" (S.fingerprintAppend state (S.fingerprintPart suffix) == Reference.state state right)

  let fails label expected action = do
        result <- try action
        case result of
          Left (H.HostError message) -> check label (expected == message)
          Right _ -> fail label
  forM_ [("A", -1, 0, 1, "string index out of bounds"),
         ("A", 0, H.failure "seed a", H.failure "seed b", "seed a"),
         ("A", 0, 7, H.failure "seed b", "seed b"),
         (H.literal ['\xd800'], 0, 0, 1, "invalid Unicode scalar")] $ \(value,offset,a,b,message) -> do
    let state = S.fingerprintStateFrom value offset a b
    fails "state demand" message (evaluate (fst state + snd state))
    fails "digest demand" message (evaluate (length (H.unpack (S.fingerprintFrom value offset a b))))
  forM_ [("",0), ("A",1), ("A",3)] $ \(value,offset) -> do
    let state = S.fingerprintStateFrom value offset 43 (H.failure "unused")
    check "terminal state" (fst state == 43 && snd (S.fingerprintStateFrom value offset (H.failure "unused") 59) == 59)

admission :: IO ()
admission = do
  let iface = Binary.base "metadata"
      object = A.makeObject iface []
      replaceAt slot value values = take slot values ++ [value] ++ drop (slot+1) values
      fields = unpack (A.encodeInterface (A.objectInterface object))
      unpack value = case S.unpack value of
        T.Left message -> error (H.unpack message)
        T.Right values -> values
      withChecksum prefix = S.pack (prefix ++ [H.literal (Reference.fingerprint (H.unpack (S.pack prefix)))])
      changed slot value = withChecksum (replaceAt slot value (init fields))
      invalid = [S.pack (init fields ++ ["wrong-checksum"]), H.literal ("0" ++ H.unpack (S.pack fields)),
                 H.literal (init (H.unpack (S.pack fields))), S.pack (fields ++ ["extra"]),
                 changed 0 "MLFCI-4", changed 1 "", changed 11 "", changed 3 "07:Fixture",
                 changed 3 (S.pack ["Fixture","Fixture"]), changed 4 "", changed 5 "",
                 changed 6 "injected = 1", changed 12 (S.pack [S.pack ["x","maybe"]]),
                 changed 12 (S.pack [S.pack ["x","true"]])]
  forM_ invalid $ \value -> check "reject malformed metadata" (case A.decodeInterface value of T.Left _ -> True; T.Right _ -> False)
  let sortedIface = A.CrateInterface "sorting" [] ["Zeta","Alpha"] [("Zeta",[]),("Alpha",[])]
        [("Zeta",[]),("Alpha",[])] [] [] [] [] [("z",T.XCon "Int" []),("a",T.XCon "String" [])] "" "body"
        [("z",True),("a",False)]
      sorted = init (unpack (A.encodeInterface sortedIface))
  forM_ [3,9,12] $ \slot -> do
    let bad = withChecksum (replaceAt slot (S.pack (reverse (unpack (sorted !! slot)))) sorted)
    check "noncanonical metadata" (case A.decodeInterface bad of
      T.Left message -> H.unpack message == "noncanonical crate metadata"
      T.Right _ -> False)
  let actualIface = A.objectInterface object
      encoded = A.encodeObject object
      parts = unpack encoded
      invalidObjects = H.literal ("0" ++ H.unpack encoded) :
        [S.pack (replaceAt i value parts) | (i,value) <- [(0,"MLFCO-0"),(1,"other"),(2,"bad-meta"),(3,"bad-payload")]]
  forM_ invalidObjects $ \raw -> check "reject malformed object" (case A.decodeObject actualIface raw of T.Left _ -> True; T.Right _ -> False)
  check "unpaired checksum" (case A.decodeObject actualIface (A.encodePooledObject actualIface (A.encodeInterface actualIface) "different payload") of
    T.Left message -> H.unpack message == "crate object checksum mismatch"
    T.Right _ -> False)
  check "object leaves fragments lazy" (H.unpack (A.crateId (A.objectInterface (A.makeObject iface (error "unused fragments")))) == "metadata")
  check "paired object leaves fragments lazy" (H.unpack (A.crateId (A.objectInterface (fst (A.makeObjectWithPayload iface (error "unused fragments"))))) == "metadata")
  check "payload leaves metadata lazy" (H.unpack (snd (A.makeObjectWithPayload (error "unused metadata") [])) == H.unpack (A.encodePooledPayload []))

main :: IO ()
main = do
  fingerprints
  admission
  Binary.main
  putStrLn "PASS fingerprint literals, boundaries, seeded scalar streams, artifact admission and binary publication"
