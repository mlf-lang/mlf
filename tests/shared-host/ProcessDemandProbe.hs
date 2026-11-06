{-# LANGUAGE ScopedTypeVariables #-}
module Main where
import qualified MLF.Primitive as F
import qualified MLF.Host.Base as B
import Control.Exception
main = do
  result <- try (F.runProcess (B.literal "bad\0cwd") (B.failure "specification forced"))
  print (result :: Either SomeException Integer)
