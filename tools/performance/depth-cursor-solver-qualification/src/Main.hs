{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Exception (SomeException, evaluate, try, displayException)
import System.Exit (exitFailure)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as A
import qualified Bootstrap.Graph.Solver as S
import qualified Candidate.Graph.Solver as CS
import qualified Bootstrap.IntMap as IM
node t b = A.mkNode t b T.Flexible
graph ps ls n = A.mkGraph (A.nodesFromDistinctAscList ps) (IM.fromDistinctAscList ls) n
bind T.Nothing=Nothing
bind (T.Just n)=Just n
tree f T.IntMapNil="Nil"
tree f (T.IntMapTip k v)="Tip "++show k++" "++f v
tree f (T.IntMapBin count prefix l r)="Bin "++show(count,prefix)++" ("++tree f l++") ("++tree f r++")"
mapTree f (T.IntMap t)=tree f t
renderNode n=show(P.textToChars(A.tagDescription(A.tag n)),bind(A.binder n),case A.flag n of T.Flexible->"F";T.Rigid->"R")
render g=mapTree renderNode(A.nodes g)++"|"++mapTree show(A.links g)++"|"++show(A.nextId g)
out x = case x of T.Left e -> "Left "++show(P.textToChars e); T.Right g -> "Right "++render g
graftInput = graph
  [(0,root 1),(1,arr 2 3 0),(2,arr 4 5 1),(3,arr 6 7 1),
   (4,arr 8 9 2),(5,bot 2),(6,arr 10 11 3),(7,bot 3),
   (8,bot 4),(9,bot 4),(10,arr 12 13 6),(11,bot 6),
   (12,bot 10),(13,bot 10)] [] 14
-- Hand-written result: class8 has original binders6,4 ->3,2 ->1.
-- Grafted children12/13 inherit image8 of old binder10.
graftExpected = graph
  [(0,root 1),(1,arr 2 3 0),(2,arr 4 5 1),(3,arr 6 7 1),
   (4,arr 8 9 2),(5,bot 2),(6,arr 8 11 3),(7,bot 3),
   (8,arr 12 13 1),(9,bot 4),(11,bot 6),
   (12,bot 8),(13,bot 8)] [(10,8)] 14
renameTag f t = case t of
  T.GBot -> T.GBot
  T.GArr a b -> T.GArr (f a) (f b)
  T.GGen n -> T.GGen (f n)
  _ -> error "renameTag fixture outside closed tag vocabulary"
renameBinder f b = case b of T.Nothing -> T.Nothing; T.Just n -> T.Just (f n)
renameFixture f g = graph
  [(f k,A.mkNode (renameTag f (A.tag v)) (renameBinder f (A.binder v)) (A.flag v))
    | (k,v) <- IM.toList (A.nodes g)]
  [(f k,f v) | (k,v) <- IM.toList (A.links g)] (f (A.nextId g))
withAliases g aliases fresh = A.mkGraph (A.nodes g) (IM.fromDistinctAscList aliases) fresh

root n=node (T.GGen n) T.Nothing
bot b=node T.GBot (T.Just b)
arr a b p=node (T.GArr a b) (T.Just p)
setTree T.IntSetNil="Nil"
setTree (T.IntSetTip count prefix bits)="Tip "++show(count,prefix,bits)
setTree (T.IntSetBin count prefix l r)="Bin "++show(count,prefix)++" ("++setTree l++") ("++setTree r++")"
setRaw (T.IntSet t)=setTree t
solverRaw (T.Solver g parents children (T.ScopeIndex intervals jumps))=
  render g++"|parents="++mapTree setRaw parents++"|children="++mapTree setRaw children
  ++"|intervals="++mapTree show intervals++"|jumps="++show(map(mapTree show)jumps)
prepareF False=S.prepare
prepareF True=CS.prepare
unifyF False=S.solverUnify
unifyF True=CS.solverUnify
finishF False=S.finish
finishF True=CS.finish
resultF c value=case value of
  T.Left e -> "Left "++show(P.textToChars e)
  T.Right s -> out(finishF c s)
forceText s=do _<-evaluate(foldr (\c rest -> c `seq` rest) () s);pure s
-- Force the entire original immutable state BEFORE running the transaction.
-- This gate deliberately does not claim arbitrary unforced graph-payload demand.
runSuccess c input equations=case prepareF c input of
  T.Left e -> pure("prepare="++show(P.textToChars e),"PREPARE_FAILED","PREPARE_FAILED")
  T.Right s -> do
    before<-forceText(solverRaw s)
    initial<-forceText(out(finishF c s))
    answer<-forceText(resultF c(unifyF c equations s))
    after<-forceText(solverRaw s)
    final<-forceText(out(finishF c s))
    pure("initial="++initial++"\nanswer="++answer++"\nsnapshot="++final,before,after)
runFailureReuse c input bad good=case prepareF c input of
  T.Left e -> pure("prepare="++show(P.textToChars e),"PREPARE_FAILED","PREPARE_FAILED")
  T.Right s -> do
    before<-forceText(solverRaw s)
    initial<-forceText(out(finishF c s))
    failed<-forceText(resultF c(unifyF c bad s))
    afterFailure<-forceText(solverRaw s)
    reused<-forceText(resultF c(unifyF c good s))
    afterReuse<-forceText(solverRaw s)
    final<-forceText(out(finishF c s))
    pure("initial="++initial++"\nfailed="++failed++"\nreused="++reused++"\nsnapshot="++final,
         "afterFailure="++before++"\nafterReuse="++before,
         "afterFailure="++afterFailure++"\nafterReuse="++afterReuse)
expectedSuccess input expected="initial=Right "++render input++"\nanswer=Right "++render expected++"\nsnapshot=Right "++render input
expectedFailure input err expected="initial=Right "++render input++"\nfailed=Left "++show err++"\nreused=Right "++render expected++"\nsnapshot=Right "++render input
capture :: IO (String,String,String) -> IO (String,String,String)
capture action=do
  value<-try(action >>= \(s,b,a)->do _<-forceText(s++b++a);pure(s,b,a)) :: IO(Either SomeException (String,String,String))
  pure(case value of Left e -> ("UNEXPECTED_EXCEPTION "++displayException e,"EXCEPTION","EXCEPTION");Right x -> x)
check label expected aa cc=do
  (a,ab,af)<-capture aa
  (c,cb,cf)<-capture cc
  let ok=a==expected && c==expected && ab==af && cb==cf && ab==cb && af==cf
  mapM_ (\(suffix,value)->writeFile(label++suffix)(value++"\n"))
    [(".A",a),(".C",c),(".expected",expected),(".snapshot-A-before",ab),(".snapshot-A-after",af),
     (".snapshot-C-before",cb),(".snapshot-C-after",cf),(".result",if ok then "PASS" else "FAIL")]
  pure ok
rigidInput=A.setNode 8 (A.mkNode T.GBot (T.Just 4) T.Rigid) graftInput
errorsRun c=do
  (r,rb,ra)<-runFailureReuse c rigidInput [(8,10)] []
  (m,mb,ma)<-runFailureReuse c graftInput [(0,1),(999,1)] [(8,10)]
  pure("rigid\n"++r++"\nmissing\n"++m,"rigid\n"++rb++"\nmissing\n"++mb,"rigid\n"++ra++"\nmissing\n"++ma)
errorsExpected="rigid\n"++expectedFailure rigidInput "cannot instantiate a rigid or protected type variable" rigidInput
  ++"\nmissing\n"++expectedFailure graftInput "missing graph node 999" graftExpected
main=do
  dense<-check "solver-graft" (expectedSuccess graftInput graftExpected)
    (runSuccess False graftInput [(8,10)]) (runSuccess True graftInput [(8,10)])
  let f i=2*i-17
      signed=renameFixture f graftInput
      signedExpected=renameFixture f graftExpected
  signedOK<-check "solver-signed" (expectedSuccess signed signedExpected)
    (runSuccess False signed [(f 8,f 10)]) (runSuccess True signed [(f 8,f 10)])
  let aliasInput=withAliases graftInput [(20,10)] 21
      aliasExpected=withAliases graftExpected [(10,8),(20,10)] 21
  aliasOK<-check "solver-alias" (expectedSuccess aliasInput aliasExpected)
    (runSuccess False aliasInput [(8,20)]) (runSuccess True aliasInput [(8,20)])
  errorsOK<-check "solver-errors-and-reuse" errorsExpected (errorsRun False) (errorsRun True)
  if and[dense,signedOK,aliasOK,errorsOK]
    then putStrLn "COMPLETE finite Solver depth-cursor transactions"
    else exitFailure
