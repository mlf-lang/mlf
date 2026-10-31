-- Independent reference: imports only the pinned GHC base package.
module Main(main) where
import Prelude
import Data.Int(Int64)
import Data.Word(Word64)
import Data.Bits
import GHC.Float(castDoubleToWord64)
import Control.Monad(forM_)
values :: [Int64]
values = [-64..64] ++ [minBound,minBound+1,minBound+2,maxBound-2,maxBound-1,maxBound,2^62,-(2^62),2^32,-(2^32)]
bigs :: [Integer]
bigs = [-(2^1024),-(2^127)-1,-(2^64)-1,-(2^63)-1,-(2^63),-(2^62),-1,0,1,2^62,2^63-1,2^63,2^64-1,2^64,2^127+1,2^1024]
row p x y result = putStrLn(show (p::Int)++"\t"++show x++"\t"++show y++"\t"++result)
number p x y result = row p x y (show result)
bitDouble x = fromIntegral (castDoubleToWord64 x)::Int64
main = do
  forM_ values $ \x -> do
    forM_ values $ \y -> do
      forM_ [(8,(+)),(9,(-)),(14,(*)),(45,(.&.)),(108,(.|.)),(109,xor)] $ \(p,f) -> number p x y (f x y)
      number 10 x y (if x==y then 1 else 0::Int)
      number 11 x y (if x<y then 1 else 0::Int)
      number 128 x y (if (fromIntegral x::Word64)<fromIntegral y then 1 else 0::Int)
      if y==0 then pure () else do
        if x==minBound && y== -1 then pure () else number 15 x y (x `quot` y)
        number 16 x y (x `rem` y)
    forM_ [0,1,31,32,62,63,64,65,127,maxBound::Int64] $ \n -> do
      number 110 x n (shiftL x (fromIntegral n))
      number 111 x n (shiftR x (fromIntegral n))
      number 112 x n (fromIntegral(shiftR (fromIntegral x::Word64) (fromIntegral n))::Int64)
    number 7 x (0::Int) x
    number 25 x (0::Int) (bitDouble(fromIntegral x))
    number 113 x (0::Int) (countLeadingZeros x)
    number 114 x (0::Int) (countTrailingZeros x)
    number 115 x (0::Int) (popCount x)
    number 116 x (0::Int) (toInteger x)
    number 1000 x (0::Int) x
  forM_ bigs $ \x -> do
    number 7 x (0::Int) (fromInteger x::Int64)
    number 17 x (0::Int) (read(show x)::Int64)
    number 117 x (0::Int) (fromInteger x::Int64)
    number 125 x (0::Int) x
    number 126 x (0::Int) x
    number 127 x (0::Int) (bitDouble(fromInteger x))
    forM_ bigs $ \y -> do
      forM_ [(118,(+)),(119,(-)),(120,(*))] $ \(p,f) -> number p x y (f x y)
      number 123 x y (if x==y then 1 else 0::Int)
      number 124 x y (if x<y then 1 else 0::Int)
      if y==0 then pure () else do
        number 121 x y (x `quot` y)
        number 122 x y (x `rem` y)
  let keys = [minBound,minBound+1,-(2^62)-1,-(2^62),-1,0,1,2^62-1,2^62,maxBound-1,maxBound]::[Int64]
  forM_ keys $ \k -> number 1002 k (k+1) (k+1)
  forM_ (reverse keys) $ \k -> number 1003 k (0::Int) (k+1)
  forM_ keys $ \k -> number 1004 k (maxBound::Int64) ((k+1)+maxBound)
