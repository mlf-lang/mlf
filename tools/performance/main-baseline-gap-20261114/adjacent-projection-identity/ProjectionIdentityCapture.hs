{-# LANGUAGE BangPatterns, DeriveDataTypeable #-}
{-# OPTIONS_GHC -fno-cse -fno-full-laziness #-}
module Prototype.ProjectionIdentityCapture
  (Token, Site(..), withEpoch, runStep, resolved, ordinary, prepared, committed, writeCapture, selfTest) where
import Prelude
import qualified Bootstrap.Types as T
import qualified MLF.Primitive as P
import Data.Int (Int64)
import Data.IORef
import qualified Data.ByteString.Char8 as B
import qualified Data.Set as Set
import Control.Exception
import Control.Monad (unless,when)
import Data.Typeable (Typeable)
import System.IO.Unsafe (unsafePerformIO)
import System.IO (withFile,IOMode(WriteMode))
data Site=Initial | Instantiate | ProjectCase | Finish | UnifyDistinct | PreparedFallback deriving (Eq,Show)
data Token=Token !Int !Int64 !Site (Maybe (Int64,Int64))
data Sample=Sample !Int !Int !Int64 !Site !(Maybe (Int64,Int64)) !Int64
  ![Int64] ![Int64] ![Int64] ![Int64] ![Int64] deriving Show
data State=State { epochs:: !Int, eventNo:: !Int, bytes:: !Int, halted:: !Bool
  , events:: ![B.ByteString], sampleRows:: ![B.ByteString], pairRows:: ![B.ByteString]
  , lastSample:: !(Maybe Sample), pendingCandidate:: !(Maybe Sample), nextSample:: !Int, pairCount:: !Int
  , emitted:: !(Set.Set Int) }
emptyState :: State
emptyState=State 0 0 0 False [] [] [] Nothing Nothing 0 0 Set.empty
{-# NOINLINE state #-}
state :: IORef State
state=unsafePerformIO(newIORef emptyState)
maxBytes :: Int
maxBytes=32*1024*1024-4096
emit :: String -> State -> State
emit message s
 | halted s=s
 | eventNo s>=65536 || bytes s+B.length line>maxBytes=s{halted=True,lastSample=Nothing,pendingCandidate=Nothing}
 | otherwise=s{eventNo=eventNo s+1,bytes=bytes s+B.length line,events=line:events s}
 where line=B.pack(show(eventNo s)++"\t"++message++"\n")
tokenText :: Token -> String
tokenText(Token e op site _) = show e++"\t"++show op++"\t"++show site
event :: Token -> String -> IO ()
event token phase=atomicModifyIORef' state(\s->(emit(tokenText token++"\t"++phase)s,()))
{-# NOINLINE withEpoch #-}
withEpoch :: (Token -> a) -> a
withEpoch action=unsafePerformIO $ do
 e<-atomicModifyIORef' state $ \s ->
   let n=epochs s
       s'=if n>=4096 then s{halted=True,lastSample=Nothing,pendingCandidate=Nothing} else s{epochs=n+1,lastSample=Nothing,pendingCandidate=Nothing}
   in (s',n)
 let token=Token e (-1) Initial Nothing
 event token "EPOCH_BEGIN"
 answer<-evaluate(action token)
 event token "EPOCH_RETURN_WHNF"
 pure answer
{-# NOINLINE runStep #-}
runStep :: Token -> Int64 -> Site -> (Token -> T.Either P.String T.Solver) -> T.Either P.String T.Solver
runStep(Token e _ _ _) op site action=unsafePerformIO $ do
 let token=Token e op site Nothing
 event token "BEGIN"
 answer<-evaluate(action token)
 case answer of
  T.Left _ -> event token "LEFT_SHELL" >> pure answer
  T.Right value -> do
   event token "RIGHT_SHELL"
   pure(T.Right(stepCommit token value))
{-# NOINLINE stepCommit #-}
stepCommit :: Token -> T.Solver -> T.Solver
stepCommit token value=unsafePerformIO $ do
 result<-evaluate value
 atomicModifyIORef' state(\s->(commitEvent token s,()))
 pure result
resolved :: Token -> Int64 -> Int64 -> Token
resolved(Token e op site _) a b=Token e op site (Just(a,b))
ordinary :: Token -> Token
ordinary(Token e op _ ctx)=Token e op UnifyDistinct ctx
prepared :: Token -> Token
prepared(Token e op _ ctx)=Token e op PreparedFallback ctx
boundedIds :: [Int64] -> IO [Int64]
boundedIds=go 0 []
 where
  go !n acc xs=case xs of
   [] -> do
    let output=reverse acc
    _<-evaluate(length output)
    pure output
   x:rest -> if n>=2048 then throwIO(userError "projection identity ID-list cap")
             else do y<-evaluate x;go(n+1)(y:acc)rest
sampleId :: Sample -> Int
sampleId(Sample n _ _ _ _ _ _ _ _ _ _)=n
sampleEpoch :: Sample -> Int
sampleEpoch(Sample _ e _ _ _ _ _ _ _ _ _)=e
sampleOp :: Sample -> Int64
sampleOp(Sample _ _ op _ _ _ _ _ _ _ _)=op
-- Logical operation adjacency, not delivery-time adjacency. All operations in
-- the explicit chain have ordinals, including steps with no projection.
adjacent :: Sample -> Sample -> Bool
adjacent a b=sampleEpoch a==sampleEpoch b && sampleOp b==sampleOp a+1
sampleLine :: Sample -> B.ByteString
sampleLine(Sample n e op site context count selected removed changed deleted aliases)=B.pack $
 show n++"\t"++show e++"\t"++show op++"\t"++show site++"\t"++show context++"\t"++
 show count++"\t"++show selected++"\t"++show removed++"\t"++show changed++"\t"++
 show deleted++"\t"++show aliases++"\n"
addPair :: Sample -> Sample -> State -> State
addPair a b s
 | halted s || pairCount s>=32=s
 | otherwise=
  let fresh=filter(\x->not(Set.member(sampleId x)(emitted s)))[a,b]
      lines'=map sampleLine fresh
      pair=B.pack(show(sampleId a)++"\t"++show(sampleId b)++"\n")
      extra=sum(map B.length lines')+B.length pair
  in if bytes s+extra>maxBytes || Set.size(emitted s)+length fresh>64
     then s{halted=True,lastSample=Nothing,pendingCandidate=Nothing}
     else s{bytes=bytes s+extra,sampleRows=reverse lines'++sampleRows s,
            pairRows=pair:pairRows s,pairCount=pairCount s+1,
            emitted=foldr(Set.insert . sampleId)(emitted s)fresh}
-- Publish only after the enclosing operation's commit evidence is retained.
commitEvent :: Token -> State -> State
commitEvent token@(Token e op _ _) s=
 let logged=emit(tokenText token++"\tSOLVER_COMMIT")s
 in case pendingCandidate logged of
  Just candidate | sampleEpoch candidate==e && sampleOp candidate==op ->
   if halted logged then logged{pendingCandidate=Nothing,lastSample=Nothing} else
    let paired=case lastSample logged of
          Just previous | adjacent previous candidate -> addPair previous candidate logged
          _ -> logged
    in paired{lastSample=if halted paired then Nothing else Just candidate,pendingCandidate=Nothing}
  _ -> logged{pendingCandidate=Nothing,lastSample=Nothing}
{-# NOINLINE committed #-}
committed :: Token -> Int64 -> [Int64] -> [Int64] -> [Int64] -> [Int64] -> [Int64] -> T.Solver -> T.Solver
committed token@(Token e op site context) count selected removed changed deleted aliases value=unsafePerformIO $ do
 -- This observer is a replacement VALUE inside Right, not an eager Right hook.
 -- Original result failure precedes any captured-ID evaluation.
 result<-evaluate value
 event token "PROJECTION_COMMIT"
 s<-readIORef state
 if halted s || pairCount s>=32 then pure result else do
  size<-evaluate count
  if size<129 || size>2048 then do
   atomicModifyIORef' state(\x->(emit(tokenText token++"\tPROJECTION_SIZE_GAP")x{lastSample=Nothing,pendingCandidate=Nothing},()))
   pure result
  else do
   a<-boundedIds selected;b<-boundedIds removed;c<-boundedIds changed
   d<-boundedIds deleted;f<-boundedIds aliases
   ctx<-case context of
    Nothing -> pure Nothing
    Just(x,y) -> do
     x'<-evaluate x
     y'<-evaluate y
     pure(Just(x',y'))
   atomicModifyIORef' state $ \x ->
    let sample=Sample(nextSample x)e op site ctx size a b c d f
        after=emit(tokenText token++"\tELIGIBLE_ID_SAMPLE "++show(sampleId sample))x
    in (after{pendingCandidate=if halted after then Nothing else Just sample,nextSample=nextSample x+1},())
   pure result
writeCapture :: FilePath -> IO ()
writeCapture base=do
 s<-readIORef state
 let header="projection-identity-v1; explicit solvePrepared chains only; no timing or reuse certificate\n"
     write suffix pre rows=withFile(base++suffix)WriteMode(\h->B.hPut h(B.pack pre)>>mapM_(B.hPut h)(reverse rows))
 write ".events.tsv" (header++"seq\tepoch\toperation\tsite\tphase\n") (events s)
 write ".samples.tsv" "id\tepoch\toperation\tsite\tresolved_pair\tlocal_count\tselected_old\tremoved\tchanged\tdeleted\talias_left\n" (sampleRows s)
 write ".pairs.tsv" "left_sample\tright_sample\n" (pairRows s)
 let summary="{\"schema\":\"projection-identity-v1\",\"epochs\":"++show(epochs s)++
       ",\"events\":"++show(eventNo s)++",\"pairs\":"++show(pairCount s)++
       ",\"sample_records\":"++show(Set.size(emitted s))++
       ",\"truncated\":"++(if halted s then "true" else "false")++
       ",\"complete\":true,\"performance\":false,\"reuse_qualified\":false}\n"
 B.writeFile(base++".summary.json")(B.pack summary)
data Probe=SolverProbe | IdProbe | ErrorProbe deriving (Eq,Show,Typeable)
instance Exception Probe
selfTest :: IO ()
selfTest=do
 writeIORef state emptyState
 let tok=Token 0 0 Initial Nothing
     bad=committed tok 129 (throw IdProbe) [] [] [] [] (throw SolverProbe)
 -- Right-shell inspection must not enter the observer or its payload.
 shell<-evaluate(T.Right bad :: T.Either P.String T.Solver)
 case shell of T.Right _->pure();_ ->throwIO(userError "selftest right shell")
 first<-try(evaluate bad)::IO(Either Probe T.Solver)
 case first of Left SolverProbe->pure();_ ->throwIO(userError "selftest original failure order")
 let left=runStep tok 0 Initial(\_->T.Left(throw ErrorProbe))
 originalLeft<-evaluate left
 case originalLeft of T.Left _->pure();_ ->throwIO(userError "selftest Left payload")
 let sm n e op=Sample n e op Initial Nothing 129 [1] [2] [2] [] []
 unless(adjacent(sm 0 0 1)(sm 1 0 2) &&
        not(adjacent(sm 0 0 1)(sm 1 0 3)) &&
        not(adjacent(sm 0 0 1)(sm 1 1 2)))
   (throwIO(userError "selftest logical adjacency"))
 let filled=foldl(\s n->addPair(sm(2*n)0(fromIntegral(2*n)))(sm(2*n+1)0(fromIntegral(2*n+1)))s)emptyState[0..40]
 unless(pairCount filled==32 && Set.size(emitted filled)==64)
   (throwIO(userError "selftest pair cap"))
 let pending=emptyState{lastSample=Just(sm 0 0 0),pendingCandidate=Just(sm 1 0 1)}
     token1=Token 0 1 Instantiate Nothing
     normal=commitEvent token1 pending
     eventCap=commitEvent token1 pending{eventNo=65536}
     byteCap=commitEvent token1 pending{bytes=maxBytes-1}
     lastSlot=commitEvent token1 pending{eventNo=65535}
     previous=addPair(sm 0 0 0)(sm 1 0 1)emptyState
     tok3=Token 0 3 Instantiate Nothing
     commitBytes=B.length(B.pack(show(eventNo previous)++"\t"++tokenText tok3++"\tSOLVER_COMMIT\n"))
     pairByteCap=commitEvent tok3 previous{lastSample=Just(sm 2 0 2),pendingCandidate=Just(sm 3 0 3),
       bytes=maxBytes-commitBytes-1}
 unless(pairCount normal==1 && eventNo normal==1 &&
        halted eventCap && pairCount eventCap==0 &&
        halted byteCap && pairCount byteCap==0 &&
        pairCount lastSlot==1 && eventNo lastSlot==65536 &&
        halted pairByteCap && pairCount pairByteCap==pairCount previous &&
        sampleRows pairByteCap==sampleRows previous && pairRows pairByteCap==pairRows previous)
   (throwIO(userError "selftest atomic commit publication caps"))
 writeIORef state emptyState
 putStrLn "PASS projection identity diagnostic self-test"
