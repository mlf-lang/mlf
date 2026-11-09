{-# LANGUAGE OverloadedStrings #-}
-- Focused authored graph controls. The expected copies and nodes are specified
-- independently, not recorded from the compiler under test.
module Main where
import Prelude
import Control.Monad (unless, void)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified Bootstrap.Constraint as C

right label answer = case answer of
  T.Left message -> error (label ++ ": " ++ B.unpack message)
  T.Right value -> pure value
check label condition = unless condition (error label) >> putStrLn ("PASS " ++ label)
rejects result = case result of { T.Left _ -> True; T.Right _ -> False }
sameGraph a b = G.nextId a == G.nextId b &&
  IM.eqIntMap G.equalNode (G.nodes a) (G.nodes b) &&
  IM.eqIntMap (==) (G.links a) (G.links b)
sameIndexes a b = IM.eqIntMap IS.eqIntSet (S.structuralParents a) (S.structuralParents b) &&
  IM.eqIntMap IS.eqIntSet (S.bindingChildren a) (S.bindingChildren b) &&
  S.equalScopes (S.scopeIndex a) (S.scopeIndex b)
base = T.Graph (IM.fromList
  [(0,T.Node (T.GGen 1) T.Nothing T.Flexible),
   (1,T.Node (T.GCon "Unit" []) (T.Just 0) T.Rigid),
   (2,T.Node (T.GArr 3 5) (T.Just 0) T.Rigid),
   (3,T.Node T.GBot (T.Just 2) T.Flexible),
   (4,T.Node (T.GGen 2) (T.Just 0) T.Flexible),
   (5,T.Node (T.GSkolem 99 T.Star) (T.Just 0) T.Rigid)]) IM.empty 6
expected = T.Graph
  (IM.insert 4 (T.Node (T.GGen 6) (T.Just 0) T.Flexible)
  (IM.insert 6 (T.Node (T.GArr 7 5) (T.Just 4) T.Flexible)
  (IM.insert 7 (T.Node T.GBot (T.Just 6) T.Flexible) (G.nodes base)))) IM.empty 8
receipt = IM.fromList [(2,6),(3,7)]
fields = [(2,4)]
replaceRoot node = T.Graph (IM.insert 2 node (IM.delete 3 (G.nodes base))) IM.empty 6
unknown label graph = do
  initial <- right label (S.prepare graph)
  known <- right label (G.knownFieldInterface graph 2)
  projected <- right label (S.projectCaseFields fields initial)
  finished <- right label (S.finish projected)
  check label (not known && sameGraph graph finished && sameIndexes initial projected &&
    rejects (G.materializeField 2 4 graph))
main = do
  initial <- right "base" (S.prepare base)
  known <- right "known" (G.knownFieldInterface base 2)
  check "rigid root-local quantifier is eligible" known
  (copies,materialized) <- right "copy" (G.materializeField 2 4 base)
  check "authored copy map and full expected graph" (IM.eqIntMap (==) copies receipt && sameGraph materialized expected)
  check "original nodes and captured skolem remain unchanged" (all (\n -> G.equalNode (G.nodeAt base n) (G.nodeAt materialized n)) [0,1,2,3,5])
  (indexedCopies,indexed) <- right "indexed copy" (S.projectField 2 4 initial)
  indexedGraph <- right "indexed finish" (S.finish indexed)
  rebuilt <- right "independent rebuild" (S.prepare materialized)
  check "indexed materialization matches authored graph and rebuilt indexes" (IM.eqIntMap (==) indexedCopies receipt && sameGraph indexedGraph expected && sameIndexes indexed rebuilt)
  projected <- right "case" (S.projectCaseFields fields initial)
  dispatched <- right "dispatch" (C.evaluateStep initial (T.ProjectCase fields))
  check "sealed case and shared step evaluator agree" (sameGraph (S.graph projected) expected && sameGraph (S.graph dispatched) expected && sameIndexes projected rebuilt && sameIndexes dispatched rebuilt)
  unknown "flexible same-shape lower bound remains shared" (G.setNode 2 (T.Node (T.GArr 3 5) (T.Just 0) T.Flexible) base)
  unknown "abstract rigid skolem remains shared" (replaceRoot (T.Node (T.GSkolem 100 T.Star) (T.Just 0) T.Rigid))
  unknown "inert constant-bound prefix remains shared" (G.setNode 3 (T.Node (T.GCon "Int" []) (T.Just 2) T.Flexible) base)
  unknown "nested-rank-only quantifier remains shared" (T.Graph (IM.insert 3 (T.Node (T.GArr 6 6) (T.Just 2) T.Rigid) (IM.insert 6 (T.Node T.GBot (T.Just 3) T.Flexible) (G.nodes base))) IM.empty 7)
  unknown "flexible bottom remains shared" (replaceRoot (T.Node T.GBot (T.Just 0) T.Flexible))
  let bottom = replaceRoot (T.Node T.GBot (T.Just 0) T.Rigid)
      bottomExpected = T.Graph (IM.insert 4 (T.Node (T.GGen 6) (T.Just 0) T.Flexible) (IM.insert 6 (T.Node T.GBot (T.Just 4) T.Flexible) (G.nodes bottom))) IM.empty 7
  (bottomCopies,bottomResult) <- right "bottom" (G.materializeField 2 4 bottom)
  check "rigid bottom copies exactly its root" (IM.eqIntMap (==) bottomCopies (IM.singleton 2 6) && sameGraph bottomResult bottomExpected)
  check "missing non-Gen and replayed destinations reject" (rejects (G.materializeField 2 999 base) && rejects (G.materializeField 2 3 base) && rejects (G.materializeField 2 4 materialized) && rejects (S.projectField 2 999 initial))
  let captured = G.setNode 5 (T.Node (T.GSkolem 99 T.Star) (T.Just 2) T.Rigid) base
  capturedSolver <- right "captured" (S.prepare captured)
  check "internally captured nominal skolem is never copied" (rejects (G.materializeField 2 4 captured) && rejects (S.projectCaseFields fields capturedSolver))
  check "invalid later descriptor rejects the whole case" (rejects (S.projectCaseFields [(2,4),(2,999)] initial) && sameGraph (S.graph initial) base)
  check "malformed binder cycle rejects before traversal" (rejects (G.materializeField 2 4 (G.setNode 0 (T.Node (T.GGen 1) (T.Just 4) T.Flexible) base)))
  check "high alias fresh-counter forgery rejects" (rejects (G.materializeField 2 4 (T.Graph (G.nodes base) (IM.singleton 1000 0) 6)))
  let forged = T.Solver base IM.empty (S.bindingChildren initial) (S.scopeIndex initial)
  noOp <- right "no-op" (S.projectCaseFields [] forged)
  check "no-op case does not conceal malformed indexes" (rejects (S.finish forged) && rejects (S.finish noOp))
  let higher = T.Graph (IM.insert 2 (T.Node (T.GArr 6 6) (T.Just 0) T.Rigid)
        (IM.insert 6 (T.Node (T.GTyApp 7 3) (T.Just 2) T.Rigid)
        (IM.insert 7 (T.Node (T.GBotK (T.KArrow T.Star T.Star)) (T.Just 2) T.Flexible) (G.nodes base)))) IM.empty 8
      higherCopies = IM.fromList [(2,8),(3,9),(6,10),(7,11)]
  higherInitial <- right "higher" (S.prepare higher)
  (actualHigher,higherResult) <- right "higher copy" (S.projectField 2 4 higherInitial)
  void (right "higher finish" (S.finish higherResult))
  check "higher-kinded local variables preserve kind and identity sharing" (IM.eqIntMap (==) actualHigher higherCopies && G.equalTag (G.tag (G.nodeAt (S.graph higherResult) 11)) (T.GBotK (T.KArrow T.Star T.Star)) && G.equalTag (G.tag (G.nodeAt (S.graph higherResult) 10)) (T.GTyApp 11 9))
  putStrLn "field projection graph: passed (18 authored checks)"
