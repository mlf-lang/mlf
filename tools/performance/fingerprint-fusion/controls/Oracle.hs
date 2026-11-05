{-# OPTIONS_GHC -O0 #-}
-- Independent literal old arbitrary-Integer arithmetic, not candidate helpers.
module Oracle (strict2, addInt, mulInt, quotInt, remInt, step, checksum) where
import Prelude
import Control.Exception (throw)
import GHC.Conc (pseq)
import qualified MLF.Host.Base as Base (HostError(..))

strict2 :: (a -> b -> c) -> a -> b -> c
strict2 f a b = a `pseq` b `pseq` f a b
addInt, mulInt, quotInt, remInt :: Integer -> Integer -> Integer
addInt = strict2 (+)
mulInt = strict2 (*)
quotInt = strict2 (\a b -> if b == 0
  then throw (Base.HostError "integer division by zero") else quot a b)
remInt = strict2 (\a b -> if b == 0
  then throw (Base.HostError "integer division by zero") else rem a b)
step :: Integer -> Integer -> Integer -> Integer -> Integer
step multiplier modulus state code =
  remInt (addInt (mulInt state multiplier) code) modulus
checksum :: Integer -> Integer -> Integer -> [Integer] -> [Integer]
checksum multiplier modulus = scanl (step multiplier modulus)
