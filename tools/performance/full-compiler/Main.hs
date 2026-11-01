{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad(forM_,unless)
import Control.Exception(SomeException,try,evaluate,displayException)
import Data.List(isInfixOf)
import qualified Data.Map.Lazy as M
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as G
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.Std as L
import qualified CandidateSession as C
import qualified LegacySession as F
import qualified SessionOracle as O
import qualified RetainedSurvivors as Retained

assert label ok=unless ok(errorWithoutStackTrace label)
node label=G.mkNode(T.GCon label[])T.Nothing T.Flexible
sameEntries a b=length a==length b&&and[n==m&&O.sameNode v w|((n,v),(m,w))<-zip a b]

viewControls=do
 let cases=[(offset,stride,count,cut)|offset<-[-(2^60),-128,0,128,2^60]::[B.Int],stride<-[1,7],count<-[0,1,2,7,8,9,16,32,128],cut<-[-1,0,1,2,7,8,16,129]]
 assert "fixed projection-view model inventory"(length cases==720)
 forM_ cases $ \(offset,stride,count,cut)->do
  let pairs=[(offset+stride*fromIntegral i,node "payload")|i<-[0..count-1]]
      before=IM.fromList pairs;limit=offset+stride*cut
      actual=C.projectedOriginalNodes limit before
      expected=M.toAscList(M.filterWithKey(\key _->key<limit)(M.fromList pairs))
  assert "independent Data.Map filtered values and signed order"(sameEntries actual expected)
  assert "cached cardinality equals independent authored entry count"(IM.size before==fromIntegral count)
 putStrLn "PASS 720 independent projection views and cached cardinalities"

legacy count nodes=L.filter(\(n,_)->n<count)(IM.toList nodes)
capture value=do
 answer<-try(evaluate value)::IO(Either SomeException B.Int)
 pure(case answer of Left e->Left(displayException e);Right n->Right n)
metadata pairs=fromIntegral(length pairs)+sum(map fst pairs)
demandControls=do
 let maps=[IM.fromList[(-2,errorWithoutStackTrace "unused selected Node"),(0,node "used"),(9,errorWithoutStackTrace "unused excluded Node")],
           IM.fromList[(-2,T.Node(T.GCon(errorWithoutStackTrace "unused name")[])T.Nothing T.Flexible),(0,node "used"),(9,node "excluded")]]
 forM_ maps $ \nodes->forM_ [-3,0,1,10] $ \limit->do
  a<-capture(metadata(legacy limit nodes));b<-capture(metadata(C.projectedOriginalNodes limit nodes))
  assert "Node payload remains unobserved in view metadata"(a==b&&case a of Right _->True;_->False)
 -- Private callers supply finite cached counts and strict keys from canonical
 -- maps. Node payloads remain partial; observe their original ascending demand.
 let nodes=IM.fromList[(-2,errorWithoutStackTrace "first selected Node"),(0,errorWithoutStackTrace "later selected Node"),(9,errorWithoutStackTrace "excluded Node")]
     observe pairs=sum[seq(G.flag value)key|(key,value)<-pairs]
 a<-capture(observe(legacy 1 nodes))
 b<-capture(observe(C.projectedOriginalNodes 1 nodes))
 assert "same first selected payload exception"(a==b&&case a of Left e->"first selected Node" `isInfixOf` e;_->False)
 putStrLn "PASS 9 projection view payload-demand and first-error observations"

main=Retained.main>>viewControls>>demandControls
