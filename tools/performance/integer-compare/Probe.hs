module Probe (routes, lookupTree, smallOperands, mixedOperands) where
import Prelude
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P
import qualified Bootstrap.IntMap as IM
import Bootstrap.Types (Map)
import qualified Bootstrap.Types as T

routes :: [(String, Integer -> Integer -> Bool, String)]
routes = [("host-lt",B.v_ltInt,"lt"),("public-lt",P.ltInt,"lt"),
          ("operator-lt",(P.<),"lt"),("host-gt",B.gtInt,"gt"),
          ("operator-gt",(P.>),"gt"),("host-le",B.leInt,"le"),
          ("operator-le",(P.<=),"le"),("host-ge",B.geInt,"ge"),
          ("operator-ge",(P.>=),"ge")]
{-# NOINLINE routes #-}
lookupTree :: Integer -> Map Integer a -> Maybe a
lookupTree wanted tree = case IM.lookupTree wanted tree of
  T.Nothing -> Nothing
  T.Just value -> Just value
{-# NOINLINE lookupTree #-}
smallOperands :: Int -> Int -> Bool
smallOperands a b = B.v_ltInt (toInteger a) (toInteger b)
{-# NOINLINE smallOperands #-}
mixedOperands :: Integer -> Integer -> Bool
mixedOperands = B.v_ltInt
{-# NOINLINE mixedOperands #-}
