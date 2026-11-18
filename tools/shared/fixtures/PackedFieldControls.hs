module Main where
import Prelude
import Control.Monad (forM_,unless)
import qualified CandidateWire as C
import qualified MLF.Primitive as P

need label ok = unless ok (fail label)
-- The public writer appends each wire field to a zero-filled buffer.
-- Compare the owned writer at all pending offsets, including its wide fallbacks.
checkNodeEntries = do
  let shapes = [(0,0), (127,1), (128,2), (16383,3), (16384,2),
                (0,127), (128,128), (-1,2)]
  forM_ [0..7] $ \used ->
    forM_ [1,14,28,29] $ \width ->
      forM_ shapes $ \(tag,arity) -> do
        let capacity = 24 + fromIntegral arity * width `div` 8
            children = take arity (cycle [0, -1, 37, 4097])
            entry = C.ENode tag children
            pending = 2^used - 1
        reference <- P.newByteArray capacity 0
        packed <- P.newByteArray capacity 0
        forM_ [reference,packed] $ \bytes -> do
          P.writeByteArray bytes 0 73
          P.writeByteArray bytes (capacity - 1) 211
        P.writeByteArray reference 1 pending
        expectedEnd <- C.putEntry reference (8 + used) width 1 entry
        actualEnd <- C.packedEntry packed width 1 entry 1 used pending (C.packedFinish packed)
        let contents bytes = mapM (P.readByteArray bytes) [0..capacity-1]
        expected <- contents reference
        actual <- contents packed
        need ("node header, references and padding " ++ show (used,width,tag,arity))
          (actualEnd == expectedEnd && actual == expected)

main = do
  checkNodeEntries
  let patterns=[0,1,-1,-(2^63),2^63-1,0x55AA55AA55AA55AA,0x123456789ABCDEF :: Integer]
  forM_ [0..7 :: Int] $ \used ->
    forM_ [0,2^used-1,(2^used-1) `div` 3 :: Integer] $ \pending ->
      forM_ [0..64 :: Int] $ \width ->
        forM_ patterns $ \value -> do
          array <- P.newByteArray 16 211
          let state i u carry = pure (i,u,carry)
              total = pending + (value `mod` 2^width) * 2^used
              (count,remaining) = (used+width) `divMod` 8
              carry = total `div` 256^count
              label = show (used,pending,width,value)
          got <- C.packedBits array 1 (fromIntegral used) (fromIntegral pending)
                   (fromIntegral width) (fromIntegral value) state
          need ("continuation "++label)
            (got==(fromIntegral(1+count),fromIntegral remaining,fromIntegral carry))
          bytes <- mapM (P.readByteArray array) [0..15]
          let before=[if i>=1 && i<=count then fromIntegral((total `div` 256^(i-1)) `mod` 256) else 211 | i<-[0..15]]
          need ("written bytes "++label) (bytes==before)
          let (i,u,c)=got
          end <- C.packedFinish array i u c
          need ("finish position "++label) (end==8+fromIntegral(used+width))
          finished <- mapM (P.readByteArray array) [0..15]
          let after=[if remaining>0 && j==1+count then fromIntegral carry else old | (j,old)<-zip [0..] before]
          need ("finish padding "++label) (finished==after)
  putStrLn "PASS packed fields: 10920 states, all widths 0..64, offsets, signed patterns, continuation and sentinels"
