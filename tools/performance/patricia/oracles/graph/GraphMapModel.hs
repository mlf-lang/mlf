{-# LANGUAGE OverloadedStrings #-}
-- The graph oracle shares the compiler's record types. Decode a checked
-- Patricia spine into a library map; preserve its lazy payloads in both directions.
module GraphMapModel where

import Prelude hiding (filter, lookup, map, null)
import qualified Data.Map.Lazy as Map
import Data.Int (Int64)
import qualified OracleTypes as T
import qualified MLF.Host.Base as Host

model :: T.IntMap a -> Map.Map Int64 a
model tree
  | T.validMap tree = Map.fromDistinctAscList (T.mapEntries tree)
  | otherwise = error "oracle bridge: invalid Patricia map"

encode :: Map.Map Int64 a -> T.IntMap a
encode = T.fromMapEntries . Map.toAscList

optional :: Maybe a -> T.Maybe a
optional = maybe T.Nothing T.Just

empty :: T.IntMap a
empty = encode Map.empty

singleton key value = encode (Map.singleton key value)
fromList = encode . Map.fromList
fromDistinctAscList = encode . Map.fromDistinctAscList
toList = Map.toAscList . model
keys = Map.keys . model
elems = Map.elems . model
size :: T.IntMap a -> Int64
size = fromIntegral . Map.size . model
null = Map.null . model
lookup key = optional . Map.lookup key . model
get = findWithDefault (Host.v_panic "map key not found")
findWithDefault fallback key = Map.findWithDefault fallback key . model
member key = Map.member key . model
notMember key = Map.notMember key . model
lookupMin = optional . Map.lookupMin . model
lookupMax = optional . Map.lookupMax . model
insert key value = encode . Map.insert key value . model
insertWith combine key value = encode . Map.insertWith combine key value . model
delete key = encode . Map.delete key . model
union left right = encode (Map.union (model left) (model right))
map f = encode . Map.map f . model
mapWithKey f = encode . Map.mapWithKey f . model
filter predicate = encode . Map.filter predicate . model

eqIntMap equal left right =
  let a = model left
      b = model right
  in Map.size a == Map.size b && Map.isSubmapOfBy equal a b
