{-# LANGUAGE BangPatterns #-}
-- Private diagnostic. The reporter owns no compiler syntax or scope closures.
module GraphProgress where
import Prelude
import Control.Concurrent (ThreadId, forkIO, killThread, threadDelay)
import Control.Concurrent.MVar (MVar, newMVar, withMVar)
import Control.Exception (evaluate)
import Control.Monad (forever, unless)
import Data.Char (ord)
import Data.Int (Int64)
import Data.IORef
import Data.List (sortBy)
import Data.Word (Word64)
import GHC.Clock (getMonotonicTimeNSec)
import Numeric (showHex)
import System.IO (stderr, hPutStrLn, hFlush)
import System.IO.Unsafe (unsafePerformIO)

data Identity = Identity !Int64 ![(Int64,String)] deriving (Eq,Show)
data Total = Total !String !Word64 !Int deriving (Eq,Show)
data Completed = Completed !Int !(Maybe Identity) !Word64 ![Total] deriving (Eq,Show)
data State = State {
  startedAt :: !Word64, lastLabel :: !String, eventCounts :: ![(String,Int)],
  started :: !Int, fresh :: !Int, reused :: !Int, totalGroups :: !(Maybe Int),
  currentIdentity :: !(Maybe Identity), groupStart :: !(Maybe Word64),
  openWindow :: !(Maybe (String,Word64)), closedTotals :: ![Total],
  groupTotals :: ![Total], lastCompleted :: !(Maybe Completed), slowest :: ![Completed]
} deriving (Eq,Show)
zeroTotals = [Total n 0 0 | n <- ["prepared_record","raw_demand","raw_record","finish"]]
zero = State 0 "main.not-entered" [] 0 0 0 Nothing Nothing Nothing Nothing zeroTotals zeroTotals Nothing []
{-# NOINLINE state #-}
state :: IORef State
state = unsafePerformIO (newIORef zero)
{-# NOINLINE outputLock #-}
outputLock :: MVar ()
outputLock = unsafePerformIO (newMVar ())
forceTotals [] = ()
forceTotals (Total name value count:rest) = forceText name `seq` value `seq` count `seq` forceTotals rest
forceIdentity Nothing = ()
forceIdentity (Just (Identity count members)) = count `seq` forceMembers members
forceCompleted (Completed ordinal members span totals) = ordinal `seq` forceIdentity members `seq` span `seq` forceTotals totals
forceTop [] = ()
forceTop (record:rest) = forceCompleted record `seq` forceTop rest
forceEvents [] = ()
forceEvents ((label,count):rest) = forceText label `seq` count `seq` forceEvents rest
forceState s = forceText (lastLabel s) `seq` forceEvents (eventCounts s) `seq`
  forceIdentity (currentIdentity s) `seq` forceTotals (closedTotals s) `seq`
  forceTotals (groupTotals s) `seq` forceTop (slowest s) `seq`
  (case lastCompleted s of Nothing -> (); Just r -> forceCompleted r) `seq`
  (case openWindow s of Nothing -> (); Just (label,now) -> forceText label `seq` now `seq` ()) `seq`
  (case groupStart s of Nothing -> (); Just now -> now `seq` ()) `seq`
  (case totalGroups s of Nothing -> (); Just n -> n `seq` ())
modifyState change = atomicModifyIORef' state $ \old ->
  let !new = change old in forceState new `seq` (new,())
bump label [] = [(label,1)]
bump label ((name,count):rest)
  | label == name = let !next = count+1 in (name,next):rest
  | otherwise = (name,count):bump label rest
addTime label amount = map (\t@(Total name value count) ->
  if name == label then Total name (value+amount) (count+1) else t)
startWindow label now s = case openWindow s of
  Nothing -> s { openWindow = Just (label,now) }
  _ -> error "marker window already open"
closeWindow label now s = case openWindow s of
  Just (name,begin) | name == label && now >= begin ->
    let !duration = now-begin in s {openWindow=Nothing,
      closedTotals=addTime label duration (closedTotals s),
      groupTotals=addTime label duration (groupTotals s)}
  _ -> error "marker window closing mismatch"
completeGroup wasReused now s = case groupStart s of
  Just begin | now >= begin ->
    let record = Completed (started s) (currentIdentity s) (now-begin) (groupTotals s)
        rank (Completed _ _ a _) (Completed _ _ b _) = compare b a
        top = take 5 (sortBy rank (record:slowest s))
    in s {fresh=fresh s + if wasReused then 0 else 1,
          reused=reused s + if wasReused then 1 else 0,
          groupStart=Nothing,currentIdentity=Nothing,groupTotals=zeroTotals,lastCompleted=Just record,slowest=top}
  _ -> error "marker completion outside active SCC"
advance now label original =
  let s = original {lastLabel=label,eventCounts=bump label (eventCounts original)}
  in case label of
    "scc.begin" -> case groupStart s of
      Nothing -> s {started=started s+1,currentIdentity=Nothing,
                    groupStart=Just now,groupTotals=zeroTotals}
      _ -> error "marker SCC already active"
    "scc.prepared-record.enter" -> startWindow "prepared_record" now s
    "scc.scope-inventory.enter" -> closeWindow "prepared_record" now s
    "scc.raw-infer.await-whnf" -> startWindow "raw_demand" now s
    "scc.raw-record.enter" -> startWindow "raw_record" now (closeWindow "raw_demand" now s)
    "scc.finish.enter" -> startWindow "finish" now (closeWindow "raw_record" now s)
    "scc.finished.fresh" -> completeGroup False now (closeWindow "finish" now s)
    "scc.finished.reused" -> completeGroup True now (closeWindow "finish" now s)
    "groups.complete" -> if groupStart s == Nothing && started s == fresh s + reused s
      then s {totalGroups=Just (started s)} else error "marker incomplete SCC inventory"
    _ -> s

event label = do now <- getMonotonicTimeNSec; modifyState (advance now label)
boundary label = event label >> snapshot "boundary"
copyPrefix 0 _ = []
copyPrefix _ [] = []
copyPrefix n (c:rest) = c:copyPrefix (n-1) rest
forceText [] = ()
forceText (c:rest) = c `seq` forceText rest
forceMembers [] = ()
forceMembers ((i,name):rest) = i `seq` forceText name `seq` forceMembers rest
-- Called after the existing Prepared encoding/digest consumed these owner IDs.
-- Copy only bounded host values, and force them here, never in the reporter.
identity :: Int64 -> [(Int64,String)] -> IO ()
identity count values = do
  let copied = [(i,copyPrefix 96 name) | (i,name) <- take 4 values]
  evaluate (count `seq` forceMembers copied)
  unless (count >= 0) (error "negative marker member count")
  modifyState $ \s -> case groupStart s of
    Nothing -> error "marker identity outside active SCC"
    Just _ -> s {currentIdentity=Just (Identity count copied)}

jsonString value = '"' : foldr (\c rest -> escape c ++ rest) "\"" value
  where escape '"' = "\\\""
        escape '\\' = "\\\\"
        escape c | ord c < 32 = let h=showHex (ord c) "" in "\\u" ++ replicate (4-length h) '0' ++ h
                 | otherwise = [c]
join [] = ""
join [x] = x
join (x:xs) = x ++ "," ++ join xs
obj fields = "{" ++ join [jsonString k ++ ":" ++ v | (k,v) <- fields] ++ "}"
arr values = "[" ++ join values ++ "]"
optional _ Nothing = "null"
optional render (Just value) = render value
identityJSON (Identity count members) = obj [("member_count",show count),
  ("members",arr [obj [("id",show i),("stable_prefix",jsonString name)] | (i,name)<-members])]
totalsJSON values = obj [(name,obj [("closed_ns",show ns),("closed_count",show count)]) | Total name ns count <- values]
completedJSON (Completed ordinal members span totals) = obj [("ordinal",show ordinal),
  ("identity",optional identityJSON members),("span_ns",show span),("windows",totalsJSON totals)]
snapshotJSON reason now s = obj [("reason",jsonString reason),("elapsed_ns",show (now-startedAt s)),
  ("last_boundary",jsonString (lastLabel s)),("scc_started",show (started s)),
  ("scc_finished_fresh",show (fresh s)),("scc_finished_reused",show (reused s)),
  ("total_scc",optional show (totalGroups s)),("current_identity",optional identityJSON (currentIdentity s)),
  ("current_group_age_ns",optional (show . (now-)) (groupStart s)),
  ("open_window",optional (\(name,begin)->obj [("name",jsonString name),("age_ns",show (now-begin))]) (openWindow s)),
  ("closed_windows",totalsJSON (closedTotals s)),("last_completed",optional completedJSON (lastCompleted s)),
  ("slowest_completed",arr (map completedJSON (slowest s))),
  ("events",obj [(name,show count) | (name,count)<-eventCounts s])]
snapshot reason = do
  s <- readIORef state
  now <- getMonotonicTimeNSec
  withMVar outputLock $ \_ -> hPutStrLn stderr ("GRAPH_SNAPSHOT " ++ snapshotJSON reason now s) >> hFlush stderr
startReporting = do
  now <- getMonotonicTimeNSec
  modifyState (\s -> s {startedAt=now})
  snapshot "start"
  forkIO (forever (threadDelay 2000000 >> snapshot "periodic"))
stopReporting thread = killThread thread >> snapshot "stop"
