{-# LANGUAGE OverloadedStrings #-}
module Main(main) where
import Prelude
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as G
import qualified Bootstrap.IntMap as IM
import qualified MLF.Host.Base as B

-- The leaf enumeration is sorted, but the last branch sends both 12 and 15
-- left. Dense graph validation does not use this routing to load its nodes.
node n=if n==0 then T.Node(T.GGen 1)T.Nothing T.Flexible else
 if n==8 then T.Node(T.GArr 15 15)(T.Just 0)T.Rigid else
 if n==15 then T.Node T.GBot(T.Just 8)T.Flexible else
 T.Node(T.GCon "Unit" [])(T.Just 0)T.Rigid
leaf n=T.IntMapTip n(node n)
graph=T.Graph(T.IntMap(T.IntMapBin 5 8
 (T.IntMapBin 2 1(leaf 0)(leaf 1))
 (T.IntMapBin 3 12(leaf 8)(T.IntMapBin 2 16(leaf 12)(leaf 15)))))IM.empty 16
main=case G.validateGraph graph of
 T.Left e->error("routing fixture does not reach fast-path boundary: "++B.unpack e)
 T.Right _->do
  if IM.keys(G.nodes graph)==[0,1,8,12,15] && not(IM.valid(G.nodes graph))
   then pure () else error "sorted malformed routing fixture is vacuous"
  case G.kindsAt graph [8,8] of
   T.Left e | B.unpack e=="missing graph node 15"->pure ()
   _->error "independent full kind traversal did not reject missing child"
  case G.checkedFirstOrder [(8,8)] graph of
   T.Left e | B.unpack e=="missing graph node 15"->putStrLn "PASS sorted invalid-prefix graph retains full kind traversal diagnostic"
   T.Left e->error("kind guard changed first error: "++B.unpack e)
   T.Right _->error "kind guard accepted sorted leaves with inconsistent Patricia lookup"
