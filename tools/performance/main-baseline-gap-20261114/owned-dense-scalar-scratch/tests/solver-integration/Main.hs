{-# LANGUAGE OverloadedStrings, DeriveDataTypeable #-}
module Main where
import Prelude
import Control.Exception (Exception, evaluate, throw, try)
import Data.Typeable (Typeable)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified Bootstrap.IntMap as IM

data Probe = Probe String deriving (Show,Typeable)
instance Exception Probe
right x=case x of T.Right v->v;T.Left e->error (P.textToChars e)
node t b=T.Node t b T.Flexible
root n=node (T.GGen n) T.Nothing
bot n=node T.GBot (T.Just n)
graph ns ls fresh=T.Graph (IM.fromDistinctAscList ns) (IM.fromDistinctAscList ls) fresh
kind T.Star="Star"
kind (T.KArrow a b)="KArrow("++kind a++","++kind b++")"
tag T.GBot="Bot"
tag (T.GBotK k)="BotK("++kind k++")"
tag (T.GArr a b)="Arr"++show(a,b)
tag (T.GCon n xs)="Con"++show(P.textToChars n,xs)
tag (T.GTyCon n k)="TyCon"++show(P.textToChars n)++kind k
tag (T.GSkolem n k)="Skolem"++show n++kind k
tag (T.GTyApp a b)="App"++show(a,b)
tag (T.GGen n)="Gen"++show n
maybeInt T.Nothing="None"
maybeInt (T.Just n)="Just"++show n
flag T.Flexible="Flexible"
flag T.Rigid="Rigid"
nodeText (T.Node t b f)="Node("++tag t++","++maybeInt b++","++flag f++")"
tree value T.IntMapNil="Nil"
tree value (T.IntMapTip n v)="Tip("++show n++","++value v++")"
tree value (T.IntMapBin p m l r)="Bin("++show(p,m)++","++tree value l++","++tree value r++")"
mapText value (T.IntMap t)=tree value t
setTree T.IntSetNil="SNil"
setTree (T.IntSetTip a b c)="STip"++show(a,b,c)
setTree (T.IntSetBin p m l r)="SBin("++show(p,m)++","++setTree l++","++setTree r++")"
setText (T.IntSet t)=setTree t
graphText (T.Graph ns ls n)="Graph("++mapText nodeText ns++","++mapText show ls++","++show n++")"
scopeText (T.ScopeIndex intervals jumps)="Scopes("++mapText show intervals++","++show(map(mapText show)jumps)++")"
solverText (T.Solver g p d s)=graphText g++"|parents="++mapText setText p++"|children="++mapText setText d++"|"++scopeText s
logical g=show[(n,nodeText v)|(n,v)<-IM.toList(G.nodes g)]++"|"++show(IM.toList(G.links g),G.nextId g)
force []=()
force (x:xs)=x `seq` force xs
save name text=writeFile name (text++"\n")
assert label ok=if ok then pure () else error label
runRoute "ordinary" eq s=S.solverUnify eq s
runRoute "prepared" eq s=S.unifyPreparedFallback eq s (S.graph s) (G.nextId(S.graph s)) []
runRoute _ _ _=error "unknown route"
outcome x=case x of T.Left e->"Left "++show(P.textToChars e);T.Right s->"Right "++solverText s
-- Same Main is independently built against A and C. The controller must compare
-- every sidecar byte across lanes, not just these local hand outcome assertions.
check route label input eq expected = do
 let s=right(S.prepare input);before=solverText s;answer=runRoute route eq s
 evaluate(force before)
 let actual=outcome answer
 evaluate(force actual)
 let after=solverText s
 evaluate(force after)
 let correct=case (expected,answer) of
       (Left message,T.Left e)->P.textToChars e==message
       (Right wanted,T.Right result)->logical(S.graph result)==logical wanted && case S.finish result of T.Right _->True;_->False
       _->False
 let name=route++"-"++label;want=case expected of Left e->"Left "++show e;Right g->"Right graph "++logical g
 save (name++".before") before;save(name++".after-old")after
 save(name++".actual")actual;save(name++".expected")want
 save(name++".result")(if correct&&before==after then "PASS" else "FAIL")
 assert name (correct&&before==after)
probe route label input expected = do
 let s=right(S.prepare input);answer=runRoute route [(1,2)] s
 -- Observe only Either WHNF for unused payload; selected error forces the error
 -- string. Do not serialize an intentionally unused poisoned graph afterwards.
 let observed=case answer of T.Right _->"Right";T.Left e->"Left "++P.textToChars e
 got<-try(evaluate(force observed))::IO(Either Probe ())
 let text=case got of Left(Probe p)->"Probe "++p;Right()->observed
 let name=route++"-"++label
 save(name++".actual")text;save(name++".expected")expected
 save(name++".result")(if text==expected then "PASS" else "FAIL")
 assert name(text==expected)
main=do
 let signed=graph[(-10,root(-3)),(-3,bot(-10)),(4,bot(-10))][] 5
     signedMerged=graph[(-10,root(-3)),(-3,bot(-10))][(4,-3)]5
     hidden=graph[(0,root 1),(1,bot 0),(2,bot 0),(3,bot 0)][]4
     hiddenMerged=graph[(0,root 1),(1,bot 0),(2,bot 0)][(3,2)]4
     mismatch=graph[(0,root 1),(1,node(T.GCon "Int"[])(T.Just 0)),(2,node(T.GCon "Bool"[])(T.Just 0))][]3
     message="type constructor mismatch: Con \"Int\" [] versus Con \"Bool\" []"
 mapM_ (\route->do
   check route "signed-merge" signed [(-3,4)] (Right signedMerged)
   check route "hidden-root-merge" hidden [(2,3)] (Right hiddenMerged)
   check route "constructor-error" mismatch [(1,2)] (Left message)
   check route "missing-before-mismatch" mismatch [(1,2),(9,1)] (Left "missing graph node 9")
   let selected=graph[(0,root 1),(1,node(T.GCon(throw(Probe "selected-name"))[])(T.Just 0)),(2,node(T.GCon "Bool"[])(T.Just 0))][]3
       unused=graph[(0,root 1),(1,bot 0),(2,bot 0),(3,node(T.GGen 4)(T.Just 0)),(4,node(T.GCon(throw(Probe "unused-name"))[])(T.Just 3))][]5
   probe route "selected-name" selected "Probe selected-name"
   probe route "unused-name" unused "Right") ["ordinary","prepared"]
 -- Actual new-node publication on the second modified call path.
 let small=graph[(0,root 1),(1,bot 0),(2,bot 0)][]3;s=right(S.prepare small)
     current=graph[(0,root 1),(1,bot 0),(2,bot 0),(3,bot 0)][]4
     answer=S.unifyPreparedFallback [(1,3)] s current 3 [(3,bot 0)]
     wanted=graph[(0,root 1),(1,bot 0),(2,bot 0)][(3,1)]4
     before=solverText s;actual=outcome answer
 evaluate(force before);evaluate(force actual)
 let good=case answer of
       T.Left _->False
       T.Right v->logical(S.graph v)==logical wanted &&
         (case S.finish v of T.Right _->True;T.Left _->False)
 save "prepared-fresh.before" before;save "prepared-fresh.after-old" (solverText s)
 save "prepared-fresh.actual" actual;save "prepared-fresh.expected" ("Right graph "++logical wanted)
 save "prepared-fresh.result" (if good then "PASS" else "FAIL")
 assert "prepared-fresh" good
 putStrLn "PASS finite owned dense Solver integration contract"
