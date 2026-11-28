{-# LANGUAGE ScopedTypeVariables #-}
module Main where
import qualified MLF.Primitive as F
import qualified MLF.Host.Base as B
import Control.Exception
main = do
  result <- try (F.getArg 0 >>= evaluate . F.stringLength)
  print (result :: Either SomeException B.Int)
