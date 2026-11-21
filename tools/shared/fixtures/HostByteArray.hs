{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Exception
import Control.Monad
import System.Environment (getArgs)
import System.Mem (performGC)
import Foreign (peekElemOff)
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B
import qualified MLF.Host.IO as C
import qualified LegacyIO as L

need label ok = unless ok (fail label)
contents lengthOf readAt array = lengthOf array >>= \n -> mapM (readAt array) [0..n-1]
observe :: IO P.Int -> IO (Either String P.Int)
observe action = do
 result <- try (action >>= evaluate) :: IO (Either SomeException P.Int)
 pure (either (Left . takeWhile (/='\n') . displayException) Right result)
same label current legacy = do
 a <- observe current; b <- observe legacy
 need label (a == b)
patternAt :: P.Int -> P.Int
patternAt i = (37 * i + 11) `mod` 256
pointerSurvivesGC :: C.ByteArray -> IO P.Int
pointerSurvivesGC (C.ByteArray size storage) = C.withByteStorage storage $ \pointer -> do
 performGC
 if size == 0 then pure 0 else fromIntegral <$> peekElemOff pointer (size-1)
main = do
 [directory] <- getArgs
 forM_ [0,1,7,4095,4096,4097,65537] $ \n -> do
  a <- C.v_newByteArray n 173
  b <- L.v_newByteArray n 173
  xs <- contents C.v_lengthByteArray C.v_readByteArray a
  ys <- contents L.v_lengthByteArray L.v_readByteArray b
  need "initialization and zero length match frozen storage" (xs==ys && xs==replicate (fromIntegral n) 173)
  forM_ [0..n-1] $ \i -> do
   C.v_writeByteArray a i (patternAt i)
   L.v_writeByteArray b i (patternAt i)
  performGC
  xs <- contents C.v_lengthByteArray C.v_readByteArray a
  ys <- contents L.v_lengthByteArray L.v_readByteArray b
  need "mutable cells survive GC and preserve byte values" (xs==ys && xs==map patternAt [0..n-1])
  ca <- C.v_byteArrayDigest a; cb <- L.v_byteArrayDigest b
  need "snapshot digests agree with frozen storage" (B.unpack ca==B.unpack cb)
  forM_ [-1,n,n+1] $ \i -> do
   same "read bounds" (C.v_readByteArray a i) (L.v_readByteArray b i)
   same "index failure precedes value failure"
    (C.v_writeByteArray a i (B.failure "later value") >> pure 0)
    (L.v_writeByteArray b i (B.failure "later value") >> pure 0)
  let path=B.literal (directory++"-"++show n)
  err <- C.v_writeByteFileOrError path a
  need "binary snapshot writes" (B.unpack err=="")
  (msg,copy) <- C.v_readByteFileOrError path n
  copied <- contents C.v_lengthByteArray C.v_readByteArray copy
  need "binary snapshot reads" (B.unpack msg=="" && copied==xs)
 forM_ [-1,0,1] $ \n ->
  forM_ [-1,256] $ \value -> same "length and byte-range error priority"
   (C.v_newByteArray n value >>= C.v_lengthByteArray)
   (L.v_newByteArray n value >>= L.v_lengthByteArray)
 same "array demand precedes index demand"
  (C.v_readByteArray (B.failure "first array") (B.failure "later index"))
  (L.v_readByteArray (B.failure "first array") (B.failure "later index"))
 a <- C.v_newByteArray 1 9; b <- L.v_newByteArray 1 9
 same "valid-index write still demands the value"
  (C.v_writeByteArray a 0 (B.failure "value") >> pure 0)
  (L.v_writeByteArray b 0 (B.failure "value") >> pure 0)
 same "a failed write leaves the cell unchanged" (C.v_readByteArray a 0) (L.v_readByteArray b 0)
 -- Constructing or sequencing an IO action must not execute its checks.
 _ <- evaluate (C.v_newByteArray (B.failure "unused size") 0)
 _ <- evaluate (C.v_writeByteArray (B.failure "unused array") 0 0)
 forM_ [0,1,4096,65537] $ \n -> do
  result <- C.v_newByteArray n 219 >>= pointerSurvivesGC
  need "owner stays live through a pointer callback and GC" (result==if n==0 then 0 else 219)
 unicode <- C.v_byteArrayFromString "α😀\NUL"
 actual <- contents C.v_lengthByteArray C.v_readByteArray unicode
 need "UTF-8 snapshot preserves NUL and non-ASCII" (actual==[206,177,240,159,152,128,0])
 aError <- C.v_writeByteFileOrError "bad\NULpath" (B.failure "unused array")
 bError <- L.v_writeByteFileOrError "bad\NULpath" (B.failure "unused array")
 need "path-NUL error precedes array demand" (B.unpack aError==B.unpack bError)
 putStrLn "PASS frozen byte-array values, errors, lazy actions, GC ownership and binary snapshots"
