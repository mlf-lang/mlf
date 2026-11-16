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
import qualified Bootstrap.IntSet as IS
import qualified Prototype.LocalProblemDigest as C
import qualified Bootstrap.IntRank as Rank

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
maybeInt :: T.Maybe P.Int -> String
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


compText x=case x of {T.Left e->"Left "++P.textToChars e;T.Right (ns,ss)->mapText nodeText ns++"|"++setText ss}
compNew x=case x of {T.Left e->"Left "++P.textToChars e;T.Right (ns,ss,_)->mapText nodeText ns++"|"++setText ss}
counts x=case x of {T.Left _->[];T.Right (_,_,c)->C.countsList c}
expect label a c expected actual=do
 evaluate(force a);evaluate(force c)
 let okay=a==c && expected==actual
 save(label++".A")a;save(label++".C")c
 save(label++".expected")(show expected);save(label++".actual")(show actual)
 save(label++".result")(if okay then "PASS" else "FAIL")
 assert label okay
componentCase label s seeds wanted=do
 let a=S.componentCanonicalNodesVisit s IM.empty IS.empty seeds
     c=S.componentProvenanceVisit s IM.empty IS.empty C.emptyCounts (map (\n->(n,0)) seeds)
 let direct=case c of
       T.Left _->[]
       T.Right(ns,_,cs)->S.projectionProvenance cs ns ns seeds [] [] IM.empty
     expectedDirect=wanted++[4,4,0,0,0,2,0,0,2,0]
 expect label (compText a) (compNew c) (wanted,expectedDirect) (counts c,direct)
probeText text=do
 got<-try(evaluate(force text))::IO(Either Probe ())
 pure(case got of {Left(Probe p)->"Probe "++p;Right()->text})
outcome x=case x of {T.Left e->"Left "++P.textToChars e;T.Right s->"Right "++solverText s}
projText (g,eqs,originals,(Rank.MapIndex tree',scopes,stubs))=
 graphText g++"|"++show eqs++"|"++show[(n,nodeText v)|(n,v)<-originals]++
 "|"++tree nodeText tree'++"|"++mapText maybeInt scopes++"|"++mapText show stubs
strip (g,eqs,os,(rest,_))=(g,eqs,os,rest)
metadata (_,_,_,(_,m))=m
checkSolve label s a c wanted=do
 let before=solverText s; ar=outcome a;cr=outcome c
 evaluate(force before);evaluate(force ar);evaluate(force cr)
 let good=ar==cr && before==solverText s &&
          (case a of {T.Right z->graphText(S.graph z)==graphText wanted;_->False}) &&
          (case c of {T.Right z->graphText(S.graph z)==graphText wanted;_->False})
 save(label++".A")ar;save(label++".C")cr;save(label++".before")before
 save(label++".after-old")(solverText s);save(label++".expected")(graphText wanted)
 save(label++".result")(if good then "PASS" else "FAIL")
 assert label good
main=do
 let g=graph[(0,root 1),(1,node(T.GArr 2 3)(T.Just 0)),(2,bot 0),(3,bot 0)][]4
     s=right(S.prepare g)
 componentCase "late-direct" s [2,3] [1,0,1,1,1,0]
 componentCase "duplicate-direct" s [2,2,3] [1,0,1,1,1,0]
 componentCase "reordered-direct" s [3,2] [1,0,1,1,1,0]
 let missing=99:throw(Probe "pending-tail")
     a=S.componentCanonicalNodesVisit s IM.empty IS.empty missing
     c=S.componentProvenanceVisit s IM.empty IS.empty C.emptyCounts (map(\n->(n,0))missing)
 ma<-probeText(compText a);mc<-probeText(compNew c)
 expect "missing-first" ma mc ("Left missing graph node 99") ma
 left<-evaluate(C.observeMetadata C.UnifyDistinct (throw(Probe "metadata"))
       (\_ _->T.Left "expected-left") (throw(Probe "equations")) (throw(Probe "graph")))
 let leftText=case left of {T.Left e->P.textToChars e;_->"unexpected Right"}
 expect "left-metadata" leftText "expected-left" "expected-left" leftText
 -- These raw identity-action graphs test only observer eligibility, not G.unify.
 let sized n=graph[(fromIntegral i,node T.GBot T.Nothing)|i<-[0..n-1]][] (fromIntegral n)
     boundary label n expected=do
       actual<-probeText(case C.observeMetadata C.PreparedFallback (throw(Probe "metadata"))
            (\_ x->T.Right x) [] (sized n) of {T.Left e->P.textToChars e;T.Right _->"Right"})
       expect label actual expected expected actual
 boundary "metadata-128" (128::Int) "Right"
 boundary "metadata-129" (129::Int) "Probe metadata"
 boundary "metadata-2048" (2048::Int) "Probe metadata"
 boundary "metadata-2049" (2049::Int) "Right"
 let positiveMeta=[129,0,0,0,0,0,129,129,0,0,0,129,0,0,129,0]
 positive<-probeText(case C.observeMetadata C.PreparedFallback positiveMeta
       (\_ x->T.Right x) [(fromIntegral i,fromIntegral i)|i<-[0..128::Int]] (sized 129) of
       {T.Left e->P.textToChars e;T.Right _->"Right"})
 expect "metadata-129-success" positive "Right" "Right" positive
 let merged=graph[(0,root 1),(1,node(T.GArr 2 2)(T.Just 0)),(2,bot 0)][(3,2)]4
 checkSolve "ordinary" s (S.unifyDistinct[(2,3)]s) (S.unifyDistinctObserved[(2,3)]s) merged
 let base=graph[(0,root 1),(1,bot 0),(2,bot 0)][]3
     sb=right(S.prepare base)
     current=graph[(0,root 1),(1,bot 0),(2,bot 0),(3,bot 0)][]4
     fresh=[(3,bot 0)]
     pa=right(S.preparedFallbackProjection sb current 3 fresh [(1,3)])
     pc=right(S.preparedFallbackProjectionObserved sb current 3 fresh [(1,3)])
     fm=[1,0,0,1,0,0,2,2,0,1,0,2,1,1,2,1]
 expect "fresh-projection" (projText pa) (projText(strip pc)) fm (metadata pc)
 checkSolve "fresh-solve" sb (S.unifyPreparedFallback[(1,3)]sb current 3 fresh)
   (S.unifyPreparedFallbackObserved[(1,3)]sb current 3 fresh)
   (graph[(0,root 1),(1,bot 0),(2,bot 0)][(3,1)]4)
 let sa=right(S.preparedFallbackProjection sb base 3 [] [(2,2)])
     sc=right(S.preparedFallbackProjectionObserved sb base 3 [] [(2,2)])
     sm=[1,0,0,1,0,0,2,2,0,0,1,1,0,0,1,0]
 expect "hidden-stub" (projText sa) (projText(strip sc)) sm (metadata sc)
 C.writeCapture "local-problem-digest.tsv"
 cap<-readFile "local-problem-digest.tsv"
 let rows=map words(lines cap)
     nat x=case reads x::[(Integer,String)] of {[(n,"")]|n>=0 && n<=18446744073709551615->n;_->error "bad unsigned scalar"}
 case rows of
  [hd,cols,l,b128,b2049,p129,o,f,ft]->do
   assert "capture schema" (length hd==5 && length ft==5 && head hd=="local-problem-provenance-v1" &&
     head ft=="complete" && tail hd==tail ft && hd!!1=="6" && length cols==25)
   let accepted=[l,b128,b2049,p129,o,f]
       wanted=[["0","UnifyDistinct","0"],["1","PreparedFallback","1"],
               ["2","PreparedFallback","1"],["3","PreparedFallback","1"],["4","UnifyDistinct","1"],["5","PreparedFallback","1"]]
   assert "capture rows" (all((==25).length)accepted && map(take 3)accepted==wanted &&
      all((==replicate 16 "NA").drop 9)[l,b128,b2049,o,f] &&
      drop 9 p129==words "129 0 0 0 0 0 129 129 0 0 0 129 0 0 129 0" && p129!!4=="129" &&
      b128!!4=="128" && b2049!!4=="2049" && o!!4=="4" && f!!4=="3")
   assert "capture sums" (nat(hd!!2)==sum[ nat(x!!3)|x<-accepted] &&
     nat(hd!!3)==sum[nat(x!!7)|x<-accepted] && nat(hd!!4)==sum[nat(x!!8)|x<-accepted])
  _->error "capture complete rows"
 putStrLn "PASS finite closure provenance; first-discovery is not necessity"
