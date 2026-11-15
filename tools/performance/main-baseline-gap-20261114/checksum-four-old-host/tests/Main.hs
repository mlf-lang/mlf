{-# LANGUAGE DeriveDataTypeable, ScopedTypeVariables #-}
{-# OPTIONS_GHC -fno-cse -fno-full-laziness #-}
module Main where
import Prelude
import qualified MLF.Primitive as F
import qualified MLF.Host.Base as B
import qualified Bootstrap.Bitstream as Bit
import Expected
import Control.Exception (Exception, Handler(..), catches, evaluate, throw)
import Control.Monad (unless, forM_)
import Data.Typeable (Typeable)
import Data.Bits (xor, shiftR, (.&.))
import Data.Word (Word32)
import Data.List (foldl')

data ProbeError = ProbeError String deriving (Show, Typeable)
instance Exception ProbeError
data Fault = Probe String | Host String deriving (Eq, Show)
poison :: String -> a
poison s = throw (ProbeError s)
capture :: IO a -> IO (Either Fault a)
capture action = (Right <$> action) `catches`
  [ Handler (\(ProbeError s) -> pure (Left (Probe s)))
  , Handler (\(B.HostError s) -> pure (Left (Host s))) ]
assertEq :: (Eq a, Show a) => a -> a -> IO ()
assertEq want got = unless (want == got) (error (show (want,got)))
fault :: Fault -> IO a -> IO ()
fault want action = capture action >>= \r -> case r of
  Left actual -> assertEq want actual
  Right _ -> error "expected synchronous fault"
patternAt :: F.Int -> F.Int
patternAt i = (i*37+11) `mod` 256
array :: F.Int -> IO F.ByteArray
array n = do
  a <- F.newByteArray n 0
  forM_ [0..n-1] $ \i -> F.writeByteArray a i (patternAt i)
  pure a
-- Independent bitwise oracle, not crcByte/table recurrence from production.
reference :: F.Int -> F.Int
reference n = fromIntegral (foldl' byte (0xffffffff :: Word32) [0..n-1] `xor` 0xffffffff)
  where
    byte c i = iterate bit (c `xor` fromIntegral (if i>=76 && i<80 then 0 else patternAt i)) !! 8
    bit x = (x `shiftR` 1) `xor` (if x .&. 1 == 1 then 0xedb88320 else 0)
main :: IO ()
main = do
  forM_ expected $ \(n,want) -> do
    assertEq want (reference n)
    a <- array n
    Bit.checksum a n >>= assertEq want
  -- Outer dispatch already demands size at action construction, not the buffer.
  fault (Probe "size") (evaluate (Bit.checksum (poison "buffer") (poison "size")))
  _ <- evaluate (Bit.checksum (poison "cold buffer") 16384)
  _ <- evaluate (Bit.checksum (poison "cold small buffer") 1)
  Bit.checksum (poison "empty buffer") 0 >>= assertEq 0
  fault (Probe "buffer") (Bit.checksum (poison "buffer") 16384)
  fault (Probe "buffer") (Bit.checksum (poison "buffer") (-1))
  a <- array 8
  forM_ [-1,minBound,9,16384,16385,maxBound] $ \n ->
    fault (Host "array index out of bounds") (Bit.checksum a n >> pure ())
  -- Last four declared bytes are checksum-header bytes, so they need no reads.
  shortHeader <- array 76
  Bit.checksum shortHeader 80 >>= assertEq (reference 80)
  fault (Host "array index out of bounds") (Bit.checksum shortHeader 81 >> pure ())
  large <- array 32768
  let action = Bit.checksum large 32768
  action >>= assertEq (reference 32768)
  F.writeByteArray large 77 0
  action >>= assertEq (reference 32768)
  F.writeByteArray large 81 0
  action >>= assertEq mutated
  putStrLn "CHECKSUM_FOUR_SEMANTIC_PASS 22 vectors + demand/header/shared-action checks"
