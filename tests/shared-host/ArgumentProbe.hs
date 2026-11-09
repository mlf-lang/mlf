{-# LANGUAGE ScopedTypeVariables #-}
module Main where
import qualified MLF.Primitive as F
import Control.Exception
main = do
  result <- try (F.getArg 0 >>= evaluate . F.stringLength)
  print (result :: Either SomeException Integer)
