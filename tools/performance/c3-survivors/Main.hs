{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad(forM_,unless)
import Control.Exception(evaluate)
import System.Mem.StableName(makeStableName,eqStableName)
import qualified Data.Map.Lazy as M
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified Bootstrap.IntMap as IM
import qualified MLF.Host.Base as B
import qualified CandidateSession as C
import qualified SessionOracle as O
import qualified RetainedC3 as R

assert label ok=unless ok(errorWithoutStackTrace label)
choices 0=[[]]
choices n=[c:cs|c<-[0,1,2],cs<-choices(n-1)]
original root=G.mkNode(T.GCon "original"[])(T.Just root)T.Flexible
replacement root=G.mkNode(T.GCon "changed"[])(T.Just root)T.Rigid
oldRoot=G.mkNode T.GBot T.Nothing T.Flexible
changedRoot=G.mkNode(T.GCon "old change"[])T.Nothing T.Rigid
sameEntries a b=length a==length b&&and[n==m&&O.sameNode v w|((n,v),(m,w))<-zip a b]

modelControls=do
 let offsets=[-(2^60),-512,0,512,2^60]::[B.Int]
     layouts=[[0,1,2,3,4,5],[0,2,3,9,14,27]]::[[B.Int]]
     cases=[(offset,layout,mode,cs)|offset<-offsets,layout<-layouts,mode<-[0,1,2,3],cs<-choices 6]
 assert "fixed full independent model inventory"(length cases==29160)
 forM_ cases $ \(offset,layout,mode,cs)->do
  let ids=map(+offset)layout;stop=last ids+1
      fresh=[(key,original(offset-1))|key<-ids]
      old=[(offset-2,oldRoot),(offset-1,oldRoot)]
      changes=zip ids cs
      oldRemoved=[(offset-2,oldRoot)|mode==1||mode==3]++[(offset-1,oldRoot)|mode==2||mode==3]
      oldChanged=[(offset-1,changedRoot)|mode==2||mode==3]
      removed=oldRemoved++[(key,original(offset-1))|(key,c)<-changes,c/=0]
      changed=oldChanged++[(key,replacement(offset-1))|(key,c)<-changes,c==2]
      -- Independent standard-library model: delete the before domain, then
      -- install the replacements. No candidate helper computes expectations.
      initial=M.fromList(old++fresh)
      retained=foldr M.delete initial(map fst removed)
      final=M.union(M.fromList changed)retained
      wanted=[entry|entry@(key,_)<-M.toAscList final,key>=offset&&key<stop]
      actual=C.survivingFreshFromDelta fresh removed changed
      previous=S.allocatedNodes offset stop(IM.fromList(M.toAscList final))
  assert "independent full output, including unchanged descendants"(sameEntries wanted actual)
  assert "original interval-lookup result independently agrees"(sameEntries wanted previous)
 putStrLn "PASS 29160 independent sparse/wide signed fresh-delta models"

nodeReuseControls=do
 let a=original 1;b=original 2;c=original 3;next=replacement 1
     actual=C.survivingFreshFromDelta [(10,a),(11,b),(12,c)] [(11,b),(12,c)] [(11,next)]
 case actual of
  [(10,x),(11,y)]->do
   a'<-evaluate a;x'<-evaluate x;next'<-evaluate next;y'<-evaluate y
   aa<-makeStableName a';xx<-makeStableName x';nn<-makeStableName next';yy<-makeStableName y'
   assert "reuse exact original unchanged Node"(eqStableName aa xx)
   assert "reuse exact restored changed Node"(eqStableName nn yy)
  _->errorWithoutStackTrace "changed/deleted survivor inventory"
 let opaque=errorWithoutStackTrace "unused delta Node payload"::T.Node
     keys=map fst(C.survivingFreshFromDelta [(1,opaque),(3,opaque),(5,opaque),(7,opaque)]
       [(-1,opaque),(3,opaque),(5,opaque)] [(-1,opaque),(5,opaque)])
 assert "merge never inspects opaque Node payloads"(keys==[1,5,7])
 putStrLn "PASS exact unchanged/changed Node reuse and opaque delta payloads"

main=R.main>>modelControls>>nodeReuseControls
