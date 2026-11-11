{-# LANGUAGE MagicHash, UnboxedTuples #-}
module Main where
import GHC.Exts (Int(I#), newByteArray#, sizeofMutableByteArray#)
import GHC.IO (IO(IO))
import System.Environment (getArgs)
allocate n = {-# SCC "UNIT_ALLOCATION" #-} IO $ \s -> case n of
  I# n# -> case newByteArray# n# s of
    (# next, array #) -> (# next, I# (sizeofMutableByteArray# array) #)
main = do
  [size] <- getArgs
  actual <- allocate (read size)
  print actual
