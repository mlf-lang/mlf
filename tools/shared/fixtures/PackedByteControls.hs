module Main where
import Prelude
import Control.Monad (forM_,unless)
import qualified CandidateWire as C
import qualified MLF.Primitive as P

need label ok = unless ok (fail label)
main = do
  -- Exhaust every valid pending-byte state and every appended byte. The
  -- oracle uses arbitrary-precision arithmetic, independently of bit masks.
  forM_ [0..7 :: Int] $ \used ->
    forM_ [0..2^used-1 :: Integer] $ \pending ->
      forM_ [0..255 :: Integer] $ \value -> do
        array <- P.newByteArray 4 211
        old <- P.newByteArray 4 211
        let state i u carry = pure (i,u,carry)
            total = pending + value * 2^used
            label = show (used,pending,value)
        got <- C.packedByte array 1 (fromIntegral used) (fromIntegral pending) (fromIntegral value) state
        frozen <- C.packedBits old 1 (fromIntegral used) (fromIntegral pending) 8 (fromIntegral value) state
        need ("continuation state "++label) (got==(2,fromIntegral used,fromIntegral(total `div` 256)) && got==frozen)
        bytes <- mapM (P.readByteArray array) [0..3]
        oldBytes <- mapM (P.readByteArray old) [0..3]
        need ("only one bounded byte written "++label) (bytes==[211,fromIntegral(total `mod` 256),211,211] && bytes==oldBytes)
        let (i,u,carry)=got
        end <- C.packedFinish array i u carry
        need ("finish bit position "++label) (end==16+fromIntegral used)
        tailByte <- P.readByteArray array 2
        need ("finish padding "++label) (tailByte==(if used==0 then 211 else fromIntegral(total `div` 256)))
  putStrLn "PASS packed byte: 65280 states, independent arithmetic, general writer, sentinels and finish padding"
