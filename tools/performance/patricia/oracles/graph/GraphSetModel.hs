module GraphSetModel where

import Prelude hiding (null)
import qualified Data.Set as Set
import Data.Int (Int64)
import qualified OracleTypes as T

model :: T.IntSet -> Set.Set Int64
model tree
  | T.validSet tree = Set.fromDistinctAscList (T.setEntries tree)
  | otherwise = error "oracle bridge: invalid Patricia set"

encode :: Set.Set Int64 -> T.IntSet
encode = T.fromSetEntries . Set.toAscList

empty = encode Set.empty
singleton = encode . Set.singleton
fromList = encode . Set.fromList
toList = Set.toAscList . model
size :: T.IntSet -> Int64
size = fromIntegral . Set.size . model
null = Set.null . model
member key = Set.member key . model
notMember key = Set.notMember key . model
insert key = encode . Set.insert key . model
delete key = encode . Set.delete key . model
union left right = encode (Set.union (model left) (model right))
minView tree = case Set.minView (model tree) of
  Nothing -> T.Nothing
  Just (key, rest) -> T.Just (key, encode rest)
