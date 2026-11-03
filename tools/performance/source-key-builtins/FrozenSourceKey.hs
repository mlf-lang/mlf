{-# LANGUAGE OverloadedStrings #-}
-- Translate the independently produced v6 oracle, retaining every other field.
module FrozenSourceKey (upgradeV6) where
import Prelude
import qualified Bootstrap.Types as T
import qualified Bootstrap.Separate as U
import qualified MLF.Primitive as P

upgradeV6 :: P.String -> P.String -> P.String
upgradeV6 builtins key = case U.unpack key of
  T.Right fields@["MLF-SOURCE-CRATE-QUERY-6",crate,compiler,members,bindings,context,group,contracts,scopes]
    | key == U.pack fields && n <= P.stringLength context && P.stringSlice context 0 n == builtins ->
        U.pack ["MLF-SOURCE-CRATE-QUERY-7",crate,compiler,members,bindings,
                P.stringSlice context n (P.stringLength context - n),group,contracts,scopes]
  _ -> error "expected a canonical v6 key with the exact independently encoded dictionary"
  where n = P.stringLength builtins
