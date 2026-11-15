-- Independent boxed-array model and literal primitive demand-order controls.
module Main where
import Prelude
import Control.Exception
import Control.Monad
import Data.Int (Int64)
import Data.List (isInfixOf)
import qualified Data.Array.IO as A
import qualified MLF.Primitive as P

need label ok = unless ok (fail label)
fails label action wanted = do
 result <- try (action >> pure ()) :: IO (Either SomeException ())
 case result of
  Left e -> need label (wanted `isInfixOf` displayException e)
  Right _ -> fail ("accepted " ++ label)
main = do
 forM_ [0,1,3,257] $ \size -> do
  actual <- P.newIntArray (fromIntegral size) minBound
  reference <- A.newArray (0,size-1) minBound :: IO (A.IOArray Int Int64)
  count <- P.lengthIntArray actual
  need "fixed length" (count == fromIntegral size)
  forM_ [0..size-1] $ \i -> do
   value <- P.readIntArray actual (fromIntegral i)
   need "initial machine value" (value == minBound)
  when (size > 0) $ forM_ [0..1023::Int] $ \step -> do
   let i = (step*37+11) `mod` size
       value = fromIntegral step * 6364136223846793005 + 1442695040888963407 :: Int64
   old <- P.readIntArray actual (fromIntegral i)
   prior <- A.readArray reference i
   P.writeIntArray actual (fromIntegral i) value
   A.writeArray reference i value
   need "read observes its action, not a later write" (old == prior)
  forM_ [0..size-1] $ \i -> do
   value <- P.readIntArray actual (fromIntegral i)
   wanted <- A.readArray reference i
   need "independent array history" (value == wanted)
  forM_ [-1,fromIntegral size,maxBound] $ \i -> do
   fails "read bounds" (P.readIntArray actual i) "array index out of bounds"
   fails "write checks index before value" (P.writeIntArray actual i (error "late value")) "array index out of bounds"
 fails "size before initial value" (P.newIntArray (-1) (error "late initial")) "invalid array length"
 fails "physical allocation bound" (P.newIntArray maxBound 0) "invalid array length"
 fails "zero-sized array still demands initial value" (P.newIntArray 0 (error "initial")) "initial"
 fails "array before index" (P.readIntArray (error "array") (error "index")) "array"
 fails "write array before index" (P.writeIntArray (error "array") (error "index") (error "value")) "array"
 a <- P.newIntArray 1 0
 fails "valid write demands value" (P.writeIntArray a 0 (error "value")) "value"
 P.writeIntArray a 0 maxBound
 P.readIntArray a 0 >>= need "extreme value" . (== maxBound)
 b <- P.newIntArray 1 0
 P.readIntArray b 0 >>= need "independent owners" . (== 0)
 putStrLn "PASS IntArray storage, snapshots, bounds and demand order"
