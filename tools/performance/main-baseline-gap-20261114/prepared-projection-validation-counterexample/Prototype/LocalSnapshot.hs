{-# LANGUAGE OverloadedStrings #-}
-- Research-only pure representation adapter. No production module is replaced.
module Prototype.LocalSnapshot
  (Layout, LocalRank, LocalSnapshot, SlotOrigin(..), layout, capacity,
   localRank, rankValue, origin, originalId, capture, rebuild,
   forkReplace, solve) where
import Prelude hiding (Int, String, Maybe(..), Either(..), seq)
import MLF.Primitive (Int, String, seq)
import qualified MLF.Primitive as P
import Bootstrap.Types (Maybe(..), Either(..), Graph(..), Node)
import qualified Bootstrap.Graph as G
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IndexVec as V

-- This is a slot-domain type, NOT a replacement typed graph tag language.
data LocalDomain = LocalDomain
newtype LocalRank = LocalRank Int
data SlotOrigin = Old Int | Fresh Int | Stub Int
-- first/stop are persistent global bounds, never the local nextId.
data Layout = Layout (V.IndexVec LocalDomain Int) Int Int
                     (V.IndexVec LocalDomain Int) Int
data Cell = Live Node | Alias LocalRank | Vacant
data LocalSnapshot = Snapshot Layout (V.IndexVec LocalDomain Cell)

capacity :: Layout -> Int
capacity (Layout _ _ _ _ n) = n
rankValue :: LocalRank -> Int
rankValue (LocalRank n) = n
localRank :: Layout -> Int -> Either String LocalRank
localRank l i = if i < 0 || i >= capacity l
  then Left "local snapshot: rank out of bounds" else Right (LocalRank i)

-- Explicit small research domain, not a production capacity proposal.
smallLength :: [a] -> Either String Int
smallLength = go 0 where
  go n xs = case xs of
    [] -> Right n
    _:rest -> if n == 4096 then Left "local snapshot: capacity limit"
              else let next=n+1 in seq next (go next rest)
ascending :: [Int] -> Bool
ascending xs = case xs of
  [] -> True
  a:rest -> go a rest where
    go _ [] = True
    go previous (b:bs) = previous < b && go b bs
layout :: [Int] -> Int -> Int -> [Int] -> Either String Layout
layout old first stop hidden =
  if first < 0 || stop < first then Left "local snapshot: invalid fresh interval"
  else if stop-first > 4096 then Left "local snapshot: capacity limit"
  else G.bindE (smallLength old) $ \oldN ->
    G.bindE (smallLength hidden) $ \stubN ->
    if oldN + (stop-first) + stubN > 4096 then Left "local snapshot: capacity limit"
    else if not (ascending old && all (<first) old)
         then Left "local snapshot: old identities not strictly ascending below first"
    else if not (ascending hidden && all (`elem` old) hidden)
         then Left "local snapshot: invalid hidden owners"
    else Right (Layout (V.fromList old) first stop (V.fromList hidden)
                  (oldN + (stop-first) + stubN))

origin :: Layout -> LocalRank -> Either String SlotOrigin
origin l@(Layout old first stop hidden _) (LocalRank i) =
  G.bindE (localRank l i) $ \_ ->
  let m=V.count old; end=m+(stop-first) in
  if i<m then Right (Old (V.at old (V.fromInt i)))
  else if i<end then Right (Fresh (first+(i-m)))
  else Right (Stub (V.at hidden (V.fromInt (i-end))))
originalId :: Layout -> LocalRank -> Either String Int
originalId l i = G.bindE (origin l i) $ \entry -> case entry of
  Old n -> Right n
  Fresh n -> Right n
  Stub _ -> Left "scope placeholder escaped local unification"

-- New admission order is deliberate and narrower than arbitrary raw Graph.
-- IM.valid checks Patricia shape/routing/counts without demanding values.
capture :: Layout -> Graph -> Either String LocalSnapshot
capture l graph =
  let ns=G.nodes graph; ls=G.links graph; n=capacity l
      inside k = k>=0 && k<n
      keys = IM.keys ns
      aliases = IM.toList ls
      endsLive fuel k =
        if IM.member k ns then True else if fuel==0 then False
        else case IM.lookup k ls of
          Nothing -> False
          Just target -> inside target && endsLive (fuel-1) target
  in if G.nextId graph /= n then Left "local snapshot: nextId mismatch"
     else if not (IM.valid ns) then Left "local snapshot: noncanonical node map"
     else if not (IM.valid ls) then Left "local snapshot: noncanonical alias map"
     else if not (all inside keys && all (inside . fst) aliases)
          then Left "local snapshot: key out of bounds"
     else if any (\(k,_) -> IM.member k ns) aliases
          then Left "local snapshot: live identity also alias"
     else if not (all (\(_,target) -> inside target) aliases)
          then Left "local snapshot: alias target out of bounds"
     else if not (all (\(k,_) -> endsLive n k) aliases)
          then Left "local snapshot: alias chain does not end live"
     else seq (forceNodes (IM.toList ns))
          (let cells=map (cell ns ls) [0..n-1]
           in seq (forceCells cells) (Right (Snapshot l (V.fromList cells))))
  where
    forceNodes [] = ()
    forceNodes ((_,node):rest) = seq (G.strictNode node) (forceNodes rest)
    cell ns ls i = case IM.lookup i ns of
      Just node -> Live node
      Nothing -> case IM.lookup i ls of
        Nothing -> Vacant
        Just target -> seq target (Alias (LocalRank target))
    forceCells [] = ()
    forceCells (c:cs) = seq c (forceCells cs)

-- Reconstruct NEW maps from cells, never return or retain a source Graph field.
-- Payload sharing is permitted; no deep forcing of Node internals is added.
rebuild :: LocalSnapshot -> Graph
rebuild (Snapshot l cells) =
  let ranks=[0..capacity l-1]
      ns=concatMap (\i -> case V.at cells (V.fromInt i) of
            Live node -> [(i,node)]; _ -> []) ranks
      ls=concatMap (\i -> case V.at cells (V.fromInt i) of
            Alias (LocalRank target) -> [(i,target)]; _ -> []) ranks
  in G.mkGraph (G.nodesFromDistinctAscList ns) (IM.fromDistinctAscList ls) (capacity l)

-- Both snapshots are frozen from ONE new builder, before/after a real write.
-- Rank/live-slot rejection happens before replacement value demand.
forkReplace :: LocalRank -> Node -> LocalSnapshot -> Either String (LocalSnapshot,LocalSnapshot)
forkReplace (LocalRank rank) value (Snapshot l cells) =
  G.bindE (localRank l rank) $ \_ ->
    case V.at cells (V.fromInt rank) of
      Live _ -> let strict=G.strictNode value in seq strict (Right (P.runST (
        P.stBind (V.fixedFilled (capacity l) Vacant) $ \builder ->
        let copy i = if i==capacity l then P.stReturn ()
              else P.stBind (V.fixedSet builder (V.fromInt i) (V.at cells (V.fromInt i)))
                           (\_ -> copy (i+1))
        in P.stBind (copy 0) $ \_ ->
           P.stBind (V.fixedFreeze builder) $ \before ->
           P.stBind (V.fixedSet builder (V.fromInt rank) (Live strict)) $ \_ ->
           P.stBind (V.fixedFreeze builder) $ \after ->
           P.stReturn (Snapshot l before,Snapshot l after))))
      _ -> Left "local snapshot: replacement needs a live slot"

-- G.unify is deliberately unchanged: this is NOT a dense unifier.
-- Exact old Either errors are forwarded before the post-result storage checks.
solve :: [(Int,Int)] -> LocalSnapshot -> Either String LocalSnapshot
solve equations before@(Snapshot l@(Layout old first stop hidden _) cells) =
  G.bindE (G.unify equations (rebuild before)) $ \solved ->
    G.bindE (checkStubs solved [V.count old+(stop-first)..capacity l-1]) $ \_ ->
      capture l solved
  where
    checkStubs _ [] = Right ()
    checkStubs solved (i:rest) = case (V.at cells (V.fromInt i), IM.lookup i (G.nodes solved)) of
      (Live a,Just b) | G.equalNode a b && G.resolve solved i==i -> checkStubs solved rest
      _ -> Left "local unification changed a hidden scope root"
