{-# OPTIONS_GHC -O0 -fno-enable-rewrite-rules -fomit-interface-pragmas #-}
-- Independent Prelude Integer specification. No candidate arithmetic helper.
module Oracle (lt, gt, le, ge, lookupTree) where
import Prelude
import GHC.Conc (pseq)
import Bootstrap.Types (Map(..))

lt, gt, le, ge :: Integer -> Integer -> Bool
lt a b = a `pseq` b `pseq` (a < b)
gt a b = lt b a
le a b = not (lt b a)
ge a b = not (lt a b)
lookupTree :: Integer -> Map Integer a -> Maybe a
lookupTree wanted tree = case tree of
  MapEmpty -> Nothing
  MapNode _ key value left right ->
    if lt wanted key then lookupTree wanted left
    else if gt wanted key then lookupTree wanted right else Just value
