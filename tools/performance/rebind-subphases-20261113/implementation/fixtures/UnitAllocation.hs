{-# LANGUAGE MagicHash, UnboxedTuples #-}
module Main where
import GHC.Exts (Int(I#), newByteArray#, sizeofMutableByteArray#)
import GHC.IO (IO(IO))
import System.Environment (getArgs)
import Control.Exception (evaluate)
allocate n = {-# SCC "UNIT_ALLOCATION" #-} IO $ \s -> case n of
  I# n# -> case newByteArray# n# s of
    (# next, array #) -> (# next, I# (sizeofMutableByteArray# array) #)
main = do
  [size] <- getArgs
  n <- evaluate (read size :: Int)
  actual <- allocate n
  print actual
