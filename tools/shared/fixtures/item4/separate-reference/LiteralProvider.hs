module LiteralProvider (Key(..), key) where
import Data.String (IsString(..))
data Key = Key Int
instance Eq Key where
  Key a == Key b = a == b
instance IsString Key where
  fromString _ = Key 7
key = Key 7
