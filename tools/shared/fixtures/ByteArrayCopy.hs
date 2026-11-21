{-# LANGUAGE OverloadedStrings #-}
module Main where

import Prelude
import Control.Exception
import Control.Monad
import qualified Data.ByteString as BS
import Foreign (castPtr)
import System.Mem (performGC)
import qualified MLF.Host.Base as B
import qualified MLF.Host.IO as C
import qualified CopyGC as G

need :: String -> Bool -> IO ()
need label okay = unless okay (fail label)

snapshotC :: C.ByteArray -> IO BS.ByteString
snapshotC (C.ByteArray size cells) = C.withByteStorage cells $ \pointer ->
  BS.packCStringLen (castPtr pointer,size)
snapshotG :: G.ByteArray -> IO BS.ByteString
snapshotG (G.ByteArray size cells) = G.withByteStorage cells $ \pointer ->
  BS.packCStringLen (castPtr pointer,size)

-- Golden byte pattern is independent of the copy implementation. A sliced
-- input includes inaccessible prefix/suffix bytes and may contain no NUL.
patternAt :: Int -> Word
patternAt i = fromIntegral ((i * 37 + 19) `mod` 256)
checkCopy make readBack writeAt size offset = do
  let bytes = BS.pack [fromIntegral (patternAt i) | i <- [0..size+offset+15]]
      input = BS.take size (BS.drop offset bytes)
      expected = BS.pack [fromIntegral (patternAt i) | i <- [offset..offset+size-1]]
  first <- make input
  second <- make input
  performGC
  original <- readBack first
  need "copy respects offset and exact length" (original == expected)
  when (size > 0) $ do
    writeAt first 0 (fromIntegral ((fromIntegral (BS.head expected) + 1) `mod` (256 :: Int)))
    writeAt first (fromIntegral size - 1) 173
  untouched <- readBack second
  need "copies have independent mutable storage" (untouched == expected)
  need "writing a copy leaves immutable input unchanged" (input == expected)
  third <- make input
  performGC
  restored <- readBack third
  need "input remains valid after copies and GC" (restored == expected)

observe :: IO () -> IO (Either String ())
observe action = do
  result <- try action :: IO (Either SomeException ())
  pure (either (Left . takeWhile (/='\n') . displayException) Right result)

-- Nothing outside the adapter keeps this input alive during the injected GC.
-- Keep construction out of the caller so its independently built expectation
-- cannot incidentally retain the source ByteString.
{-# NOINLINE transientCopy #-}
transientCopy :: Int -> IO G.ByteArray
transientCopy size = G.bytesArray (BS.pack (take size (cycle [17,39,255,0])))

-- Preserve the former adapter's IO construction and exception behavior.
legacy bytes = BS.useAsCStringLen bytes $ \(pointer,size) -> C.copyByteArray (castPtr pointer) size
demandControls = do
  let bad = error "byte-copy-input" :: BS.ByteString
      badText = B.failure "byte-copy-text" :: B.String
      actions = [("raw", C.bytesArray bad, legacy bad),
                 ("UTF-8", C.v_byteArrayFromString badText, legacy (B.utf8 badText))]
  forM_ actions $ \(label,current,old) -> do
    built <- observe (evaluate current >> pure ())
    oldBuilt <- observe (evaluate old >> pure ())
    need (label ++ " IO construction demand") (built == oldBuilt)
    executed <- observe (current >> pure ())
    oldExecuted <- observe (old >> pure ())
    need (label ++ " execution demand") (executed == oldExecuted && either (const True) (const False) executed)

main :: IO ()
main = do
  let sizes = [0,1,2,7,8,31,32,63,64,255,256,4095,4096,4097,65537,1048583]
      offsets = [0,1,7,31]
  forM_ sizes $ \size -> forM_ offsets $ \offset -> do
    checkCopy C.bytesArray snapshotC C.v_writeByteArray size offset
    checkCopy G.bytesArray snapshotG G.v_writeByteArray size offset
  let unicode = [("",[]),("\NUL",[0]),("α😀\NUL",[206,177,240,159,152,128,0]),
                 ("\x7f\x80\x7ff\x800\xffff\x10000\x10ffff",
                   [127,194,128,223,191,224,160,128,239,191,191,240,144,128,128,244,143,191,191])]
  forM_ unicode $ \(text,expected) -> do
    first <- C.v_byteArrayFromString text >>= snapshotC
    second <- G.v_byteArrayFromString text >>= snapshotG
    need "scalar boundaries and embedded NUL" (first == BS.pack expected && second == BS.pack expected)
  forM_ [1,65537,1048583] $ \size -> do
    actual <- transientCopy size >>= snapshotG
    need "temporary input survives GC inside its sole borrower"
      (BS.unpack actual == take size (cycle [17,39,255,0]))
  demandControls
  putStrLn "PASS byte copies: 128 sliced ownership/GC cases, 8 UTF-8 vectors, 3 transient-owner cases, 4 demand comparisons"
