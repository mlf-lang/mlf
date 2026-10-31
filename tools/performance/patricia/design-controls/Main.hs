{-# LANGUAGE ScopedTypeVariables #-}
module Main(main) where
import Prelude
import Control.Exception (try, evaluate, SomeException, throw)
import Control.Monad (forM_, unless)
import Data.Int (Int64)
import qualified Data.List as List
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.IntRank as Rank
import qualified Bootstrap.ClassDemand as Q
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.Separate as Separate
import qualified Bootstrap.Std as Std
import qualified Bootstrap.Map as Map
import qualified Bootstrap.Set as Set
import qualified FrozenIdentityInventory as FI
import qualified FrozenClassDemand as F
import qualified Bootstrap.Runtime as R
import qualified MLF.Tests.ClassDemand as QT
import qualified MLF.Host.Base as B
import qualified MLF.Host.IO as H

check label good = unless good (errorWithoutStackTrace ("FAIL " ++ label))
right (T.Right x) = x
right (T.Left e) = errorWithoutStackTrace (B.unpack e)
optional T.Nothing = Nothing
optional (T.Just x) = Just x
keys = [minBound, minBound+1, -(2^62), -(2^32), -65,-64,-1,0,1,63,64,65,2^32,2^62,maxBound-1,maxBound] :: [Int64]
rankControls = do
  let shapes = [[],keys,reverse keys,keys++keys] ++ map (flip take keys) [1..length keys]
  forM_ shapes $ \xs -> do
    let ordered=List.nub(List.sort xs)
        values=IM.fromList [(x,error "unused payload"::Int64)|x<-xs]
        mi=Rank.indexMap values;si=Rank.indexSet(IS.fromList xs)
    check "index cardinality" (Rank.mapSize mi==fromIntegral(length ordered))
    forM_ (keys++[-100,100]) $ \key -> do
      let expected=fromIntegral <$> List.elemIndex key ordered
      check "signed map rank" (optional(Rank.mapRank key 0 mi)==expected)
      check "signed set rank" (optional(Rank.setRank key si)==expected)
      check "rank offset" (optional(Rank.mapRank key 17 mi)==((+17) <$> expected))
    forM_ [-1..fromIntegral(length ordered)] $ \i -> do
      let expected=if i<0 || i>=fromIntegral(length ordered) then Nothing else Just(ordered!!fromIntegral i)
      check "map rank inverse and bounds" (optional(Rank.mapSelect i mi)==expected)
      check "set rank inverse and bounds" (optional(Rank.setSelect i si)==expected)

originQ x=case x of Q.SeedOrigin n->(0,n,0);Q.InstantiatedOrigin u n->(1,u,n)
originF x=case x of F.SeedOrigin n->(0,n,0);F.InstantiatedOrigin u n->(1,u,n)
observeQ result=case result of
 T.Left e->Left(B.unpack e)
 T.Right p->let u=Q.planUniverse p in Right(show
   ([(k,Q.slotId s,B.unpack(Q.classOf s),Q.ownerOf s,originQ(Q.originOf s))|(k,s)<-IM.toList(Q.universeSlots u)],
    IM.toList(Q.universeSeeds u),[(k,IM.toList v)|(k,v)<-IM.toList(Q.universeTransitions u)],
    [(k,IS.toList v)|(k,v)<-IM.toList(Q.nodeSets p)],Q.saturationUpdates p))
observeF result=case result of
 T.Left e->Left(B.unpack e)
 T.Right p->let u=F.planUniverse p in Right(show
   ([(k,F.slotId s,B.unpack(F.classOf s),F.ownerOf s,originF(F.originOf s))|(k,s)<-IM.toList(F.universeSlots u)],
    IM.toList(F.universeSeeds u),[(k,IM.toList v)|(k,v)<-IM.toList(F.universeTransitions u)],
    [(k,IS.toList v)|(k,v)<-IM.toList(F.nodeSets p)],F.saturationUpdates p))
copyFrame(Q.Frame a b c)=F.Frame a b c
copySeed(Q.Seed a b c)=F.Seed a b c
copyUse(Q.Use a b c)=F.Use a b c
copyDemand d=case d of Q.Empty->F.Empty;Q.SeedNode x->F.SeedNode x;Q.UnionNodes xs->F.UnionNodes xs;Q.RefNode x->F.RefNode x;Q.InstantiateNode u x->F.InstantiateNode u x
plannerControls = do
  check "maintained shared planner suite" (case QT.checkAll of T.Right ()->True;T.Left _->False)
  let compareCase frames seeds uses nodes=do
       let current=Q.solve frames seeds uses nodes
           frozen=F.solve(map copyFrame frames)(map copySeed seeds)(map copyUse uses)(IM.map copyDemand nodes)
       check "frozen planner state and first error" (observeQ current==observeF frozen)
       case current of
        T.Left _->pure ()
        T.Right p->check "fresh dense supply" (Q.nextSlot(Q.planUniverse p)==Q.universeSize p)
  forM_ [0..5] $ \n -> forM_ [0..4] $ \owner -> forM_ [0..4] $ \variant -> do
    let seeds=[Q.Seed i (B.literal "Inspect") owner|i<-[0..n-1]]
        uses=[Q.Use 100 2 1,Q.Use 101 2 3,Q.Use 102 3 1]
        initial=[(i,Q.SeedNode i)|i<-[0..n-1]]
        nodes=IM.fromList(initial++[(10,Q.UnionNodes[0..n-1]),(11,Q.InstantiateNode 101 10),
               (12,Q.InstantiateNode 102 11),(13,case variant of
                  0->Q.RefNode 12;1->Q.UnionNodes[10,11,12];2->Q.RefNode 99;
                  3->Q.InstantiateNode 999 10;_->Q.UnionNodes[13,12])])
    compareCase QT.frames seeds uses nodes
  let fm=IM.fromList[(Q.frameId f,f)|f<-QT.frames]
      slot=Q.Slot 0 (B.literal "Inspect") 2 (Q.SeedOrigin 10)
      universe next=Q.Universe next (IM.singleton 0 slot) IM.empty IM.empty
  forM_ [minBound,-1,maxBound] $ \next -> do
    result<-try(evaluate(Q.allocateAt fm (Q.Use 100 2 1) 0 (universe next)))
    case result of Left(B.HostError e)->check "supply exhaustion" (e=="identity supply exhausted");_->check "invalid supply accepted" False
    -- A missing input still wins before an exhausted supply is inspected.
    check "allocation validation precedence" (case Q.allocateAt fm (Q.Use 100 2 1) 99 (universe next) of
      T.Left e->B.unpack e=="class demand: unknown discovery slot 99";_->False)
  let (lastId,lastU)=right(Q.allocateAt fm (Q.Use 100 2 1) 0 (universe(maxBound-1)))
  check "last representable next counter" (lastId==maxBound-1 && Q.nextSlot lastU==maxBound)
  let cached=Q.Universe (error "unused supply") (Q.universeSlots lastU) (Q.universeSeeds lastU) (Q.universeTransitions lastU)
  check "cached transition leaves supply lazy" (fst(right(Q.allocateAt fm(Q.Use 100 2 1)0 cached))==lastId)

hostControls = do
  table<-H.v_newIntTable
  forM_ keys $ \k -> H.v_readIntTable table k >>= check "absent full-width table key" . (==0)
  forM_ (zip keys [1..]) $ \(k,v)->H.v_writeIntTable table k v
  forM_ (zip keys [1..]) $ \(k,v)->H.v_readIntTable table k >>= check "full-width distinct table key" . (==v)
  forM_ keys $ \k->H.v_writeIntTable table k (negate k)
  forM_ keys $ \k->H.v_readIntTable table k >>= check "table overwrite" . (==negate k)
  let key=throw(B.HostError "key");value=throw(B.HostError "value")
  result<-try(H.v_writeIntTable table key value)
  case result of Left(B.HostError e)->check "table key before value" (e=="key");_->check "write demand" False
  result2<-try(H.v_writeIntTable table 0 value)
  case result2 of Left(B.HostError e)->check "table strict value" (e=="value");_->check "write demand" False
  H.v_readIntTable table 0 >>= check "failed write leaves table unchanged" . (==0)

runtimeControls = do
  let array=R.stateArray 3 (error "unused array default") (IM.singleton 0 (error "unused cell"))
  case R.stateArrayLookup minBound (IM.singleton minBound array) of
    T.Right(R.RSTArrayState n _ cells)->check "lazy sparse array state" (n==3 && IM.size cells==1)
    _->check "wide array handle" False
  check "missing array error" (case R.stateArrayLookup maxBound (IM.singleton minBound array) of
    T.Left e->B.unpack e=="STArray does not belong to this region";_->False)
  let cell=R.RAsyncCellState 0 T.Nothing [1,2]
      store=R.rAsyncSetCell R.rAsyncEmpty minBound cell
      stored=R.rAsyncSetCell store maxBound (error "unused async cell")
  case R.rAsyncLookupCell stored minBound of
    T.Right(R.RAsyncCellState owner _ waiting)->check "async key separation and lazy neighbor" (owner==0 && waiting==[1,2])
    _->check "async cell present" False
  check "missing async error" (case R.rAsyncLookupCell stored 0 of T.Left e->B.unpack e=="unknown completion cell";_->False)

poolControls = do
  let pack xs=B.literal(concatMap (\x->show(length x)++":"++x) xs)
      pool=IM.singleton 0 (error "unused datatype payload")
  check "datatype reference payload stays lazy"
    (length(right(Artifact.decodeTypeReferences pool (pack ["0"])))==1)
  forM_ [("", "invalid crate datatype pool reference"),
         ("-1", "invalid crate datatype pool reference"),
         ("1000000000", "invalid crate datatype pool reference"),
         ("00", "noncanonical crate datatype pool reference"),
         ("1", "crate datatype pool reference is out of bounds")] $ \(input,expected)->
    check "datatype reference first error" (case Artifact.decodeTypeReferences pool (pack [input]) of
      T.Left message->B.unpack message==expected;_->False)
  check "invalid reference precedes pool demand" (case Artifact.decodeTypeReferences
      (error "unused pool") (pack ["-1"]) of
      T.Left message->B.unpack message=="invalid crate datatype pool reference";_->False)

nameDemandControls = do
  let badId=throw(B.HostError "stored identity")
      query=throw(B.HostError "query identity")
      term=T.XVarTerm(T.XName badId (error "unused hint"))
  inventory<-try(evaluate(fst(Separate.freshObject 0 term)))
  case inventory of Left(B.HostError e)->check "identity inventory forces integer identity" (e=="stored identity")
                    _->check "identity inventory demand" False
  check "Name fields stay lazy in Name-keyed maps"
    (Map.size(Map.singleton (T.XName badId (error "unused hint")) ())==1)
  check "identity inventory does not demand name hint"
    (fst(Separate.freshObject 0 (T.XVarTerm(T.XName 1 (error "unused hint"))))==1)
  old<-try(evaluate(Map.findWithDefault Std.compareInt 0 query (Map.singleton badId (1::Int64))))
  new<-try(evaluate(IM.findWithDefault 0 query (IM.singleton badId (1::Int64))))
  case (old,new) of
    (Left(B.HostError a),Left(B.HostError b))->check "integer table key demand preserved"
      (a=="stored identity" && b==a)
    _->check "Name index demand evidence" False
  let names=[T.XName k (error "unused hint")|k<-keys]
      vars=map T.XVarTerm names
      terms=vars++[T.XApp a b|a<-vars,b<-vars]++
        [T.XLet name rhs body|(name,rhs)<-zip names vars,body<-vars]
      observe xs=do
        result<-try(evaluate(sum xs `seq` xs))::IO(Either B.HostError [Int64])
        pure(case result of Left(B.HostError e)->Left e;Right ys->Right ys)
  forM_ (term:terms) $ \value -> do
    expected<-observe(Set.toList(FI.termIdentities value Set.empty))
    actual<-observe(IS.toList(Separate.termIdentities value IS.empty))
    check "frozen identity inventory and demand" (expected==actual)

main = do
 rankControls;plannerControls;hostControls;runtimeControls;poolControls;nameDemandControls
 putStrLn "PASS index design: 20 signed index shapes; 150 frozen planner cases; 529 frozen identity cases; independent supply, exhaustion, demand order; host IntTable; interpreter stores; datatype pool"
