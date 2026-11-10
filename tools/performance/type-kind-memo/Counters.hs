{-# LANGUAGE BangPatterns #-}
-- Diagnostic only. One atomic state contains numbers, fixed labels, and sets of
-- variable IDs. The reporter never retains or traverses compiler syntax.
module KindCounters (root, visit, report, boundary, event, startReporting, stopReporting) where
import Prelude
import Control.Concurrent (ThreadId, forkIO, killThread, threadDelay)
import Control.Concurrent.MVar (MVar, newMVar, withMVar)
import Control.Exception (evaluate, finally)
import Control.Monad (forever)
import Data.IORef
import qualified Data.IntSet as Set
import GHC.Clock (getMonotonicTimeNSec)
import System.IO (hPutStrLn, hFlush, stderr)
import System.IO.Unsafe (unsafePerformIO)
import Data.Int (Int64)
import Data.Word (Word64)

data Local = Local !Int !(Set.IntSet)
data Totals = Totals !Int !Int !Int !Int !Int
data State = State ![Local] !Totals !String ![(String,Int)] !Word64
{-# NOINLINE state #-}
state :: IORef State
state = unsafePerformIO (newIORef (State [] (Totals 0 0 0 0 0) "main.not-entered" [] 0))
{-# NOINLINE outputLock #-}
outputLock :: MVar ()
outputLock = unsafePerformIO (newMVar ())

modifyState change = atomicModifyIORef' state $ \old -> let !new = change old in (new,())
closeRoot (State stack totals label events start) = case stack of
  [] -> error "kind diagnostic root stack underflow"
  Local visits identities : rest -> State rest (addLocal visits identities totals) label events start
addLocal visits identities (Totals roots count distinct maximum repeated) =
  let !unique = Set.size identities in
  Totals (roots+1) (count+visits) (distinct+unique) (max maximum visits)
    (repeated + if visits > unique then 1 else 0)

{-# NOINLINE root #-}
root :: a -> a
root value = unsafePerformIO $ do
  modifyState $ \(State stack totals label events start) ->
    State (Local 0 Set.empty : stack) totals label events start
  evaluate value `finally` modifyState closeRoot

{-# NOINLINE visit #-}
visit :: Int64 -> a -> a
visit identity value = unsafePerformIO $ do
  modifyState $ \(State stack totals label events start) -> case stack of
    [] -> error "kind diagnostic visit outside root"
    Local count seen : rest ->
      let !next = Local (count+1) (Set.insert (fromIntegral identity) seen) in
      State (next : rest) totals label events start
  pure value

bump label events = case events of
  [] -> [(label,1)]
  (name,count):rest | name == label -> let !next = count+1 in (name,next):rest
                    | otherwise -> (name,count):bump label rest

-- Call only with fixed diagnostic labels, never a source name or AST payload.
event :: String -> IO ()
event label = modifyState $ \(State stack totals _ events start) ->
  State stack totals label (bump label events) start
boundary :: String -> IO ()
boundary label = do
  modifyState $ \(State stack totals _ events start) ->
    State stack totals label (bump label events) start
  snapshot "boundary"

emit line = withMVar outputLock $ \_ -> hPutStrLn stderr line >> hFlush stderr
fields (Totals roots visits unique maximum repeated) =
  "\"roots\":" ++ show roots ++ ",\"recursive_visits\":" ++ show visits ++
  ",\"unique_variable_roots\":" ++ show unique ++ ",\"max_visits_per_root\":" ++ show maximum ++
  ",\"roots_with_repeats\":" ++ show repeated
liveTotals stack totals = foldr (\(Local visits seen) -> addLocal visits seen) totals stack
join [] = ""
join [value] = value
join (value:rest) = value ++ "," ++ join rest
snapshot reason = do
  State stack totals@(Totals completed _ _ _ _) last events start <- readIORef state
  now <- getMonotonicTimeNSec
  emit ("F1_SNAPSHOT {\"reason\":" ++ show reason ++ ",\"elapsed_ns\":" ++ show (now-start) ++
    ",\"last_boundary\":" ++ show last ++ ",\"completed_roots\":" ++ show completed ++
    ",\"active_roots\":" ++ show (length stack) ++ "," ++ fields (liveTotals stack totals) ++
    ",\"events\":{" ++ join [show name ++ ":" ++ show count | (name,count) <- events] ++ "}}")

startReporting :: IO ThreadId
startReporting = do
  now <- getMonotonicTimeNSec
  modifyState $ \(State stack totals label events _) -> State stack totals label events now
  snapshot "start"
  forkIO (forever (threadDelay 2000000 >> snapshot "periodic"))
stopReporting :: ThreadId -> IO ()
stopReporting thread = killThread thread >> snapshot "stop"

-- Preserve the original finite-control oracle when all roots have closed.
report :: IO ()
report = do
  State stack totals _ _ _ <- readIORef state
  emit ("KIND_DIAGNOSTIC {" ++ fields (liveTotals stack totals) ++ "}")
