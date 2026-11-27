{-# OPTIONS_GHC -O0 #-}
module FingerprintReference (state, render, fingerprint) where

import Data.Char (ord)
import Data.Int (Int64)
import Data.List (foldl')

-- The public seeded path performs signed 64-bit arithmetic before rem.
-- Express that arithmetic in Integer so the oracle is independent of MLF.
state :: (Int64, Int64) -> String -> (Int64, Int64)
state = foldl' step
  where
    step (a, b) c = (advance a 65599 2147483647 c, advance b 131 2147483629 c)
    advance previous multiplier modulus c =
      let wrapped = fromInteger (toInteger previous * multiplier + toInteger (ord c)) :: Int64
      in wrapped `rem` modulus

render :: (Int64, Int64) -> String
render (a, b) = show a ++ "-" ++ show b

fingerprint :: String -> String
fingerprint = render . state (0, 1)
