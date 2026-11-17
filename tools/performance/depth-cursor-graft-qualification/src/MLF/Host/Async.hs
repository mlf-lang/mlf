module MLF.Host.Async
  ( AsyncScope, Completion, AsyncSubscription
  , v_asyncScopeNew, v_asyncScopeClose, v_asyncNewCompletion
  , v_asyncResolveCompletion, v_asyncReadCompletion, v_asyncSubscribeCompletion
  , v_asyncSubscriptionStatus, v_asyncCancelSubscription, v_asyncStep
  , v_asyncEnqueue, v_asyncDelay, v_asyncWait ) where

import Prelude hiding (Int, String)
import qualified Prelude as P
import MLF.Host.Base
import Data.IORef
import qualified Data.Sequence as Q
import Data.Foldable (toList)
import Control.Monad (when, forM_)
import Control.Exception (evaluate, finally)
import Control.Concurrent (threadDelay)
import GHC.Clock (getMonotonicTimeNSec)

-- Cells retain their own payload type. Only IO () closures enter the queue;
-- there is no heterogeneous value table, cast, StablePtr, or erased resolver.
data AsyncScope = Scope
  { closed :: IORef Bool, dispatching :: IORef Bool
  , cellLimit :: Int, callbackLimit :: Int, cellCount :: IORef Int
  , callbackCount :: IORef Int, closeCells :: IORef [IO ()]
  , callbacks :: IORef [Resume], ready :: IORef (Q.Seq Resume)
  , timers :: IORef [(Int,Resume)] }
data Completion a = Completion AsyncScope (IORef (Maybe a)) (IORef [Resume])
data Resume = Resume AsyncScope (IORef Bool) (IORef (Maybe (IO ()))) (IO ())
data AsyncSubscription = Rejected Int | Accepted Resume

clock :: IO Int
-- Divide the unsigned nanosecond clock before narrowing. The entire Word64
-- millisecond range, plus the checked 32-bit delay, fits signed Int64.
clock = fromIntegral . (`quot` 1000000) <$> getMonotonicTimeNSec
v_asyncScopeNew :: Int -> Int -> IO AsyncScope
v_asyncScopeNew cells slots = do
  _ <- evaluate (bounded "invalid async cell limit" (9223372036854775807 `quot` 8) cells)
  _ <- evaluate (bounded "invalid async callback limit" (9223372036854775807 `quot` 8) slots)
  Scope <$> newIORef False <*> newIORef False <*> pure cells <*> pure slots
    <*> newIORef 0 <*> newIORef 0 <*> newIORef [] <*> newIORef []
    <*> newIORef Q.empty <*> newIORef []
v_asyncScopeClose :: AsyncScope -> IO ()
v_asyncScopeClose scope = do
  isClosed <- readIORef (closed scope)
  when (not isClosed) $ do
    writeIORef (closed scope) True
    readIORef (closeCells scope) >>= sequence_
    rs <- readIORef (callbacks scope)
    forM_ rs $ \(Resume _ active action _) -> writeIORef active False >> writeIORef action Nothing
    writeIORef (closeCells scope) []
    writeIORef (callbacks scope) []
    writeIORef (ready scope) Q.empty
    writeIORef (timers scope) []
    writeIORef (cellCount scope) 0
    writeIORef (callbackCount scope) 0
  pure ()
v_asyncNewCompletion :: AsyncScope -> (Completion a -> IO b) -> IO b -> IO b
v_asyncNewCompletion scope success rejected = do
  isClosed <- readIORef (closed scope)
  count <- readIORef (cellCount scope)
  if isClosed || count>=cellLimit scope then rejected else do
    value <- newIORef Nothing
    waiting <- newIORef []
    modifyIORef' (closeCells scope) ((writeIORef value Nothing >> writeIORef waiting []):)
    writeIORef (cellCount scope) (count+1)
    success (Completion scope value waiting)
v_asyncResolveCompletion :: Completion a -> a -> IO Int
v_asyncResolveCompletion cell payload = do
  forced <- evaluate cell
  case forced of
    Completion scope value waiting -> do
      isClosed <- readIORef (closed scope)
      current <- readIORef value
      if isClosed then pure 3 else case current of
        Just _ -> pure 2
        Nothing -> do
          writeIORef value (Just payload)
          rs <- readIORef waiting
          writeIORef waiting []
          modifyIORef' (ready scope) (Q.>< Q.fromList rs)
          pure 0
v_asyncReadCompletion :: Completion a -> (a -> IO b) -> IO b -> IO b
v_asyncReadCompletion cell success pending = do
  forced <- evaluate cell
  case forced of
    Completion scope value _ -> do
      isClosed <- readIORef (closed scope)
      current <- readIORef value
      if isClosed then pending else case current of
        Nothing -> pending
        Just payload -> success payload

same :: Resume -> Resume -> Bool
same (Resume _ a _ _) (Resume _ b _ _) = a==b
reserve :: AsyncScope -> IO () -> (Resume -> IO ()) -> (Resume -> IO ()) -> IO AsyncSubscription
reserve scope action remove register = do
  isClosed <- readIORef (closed scope)
  count <- readIORef (callbackCount scope)
  if isClosed then pure (Rejected 3) else if count>=callbackLimit scope then pure (Rejected 4) else do
    active <- newIORef True
    stored <- newIORef (Just action)
    let resume=Resume scope active stored (remove resume)
    writeIORef (callbackCount scope) (count+1)
    modifyIORef' (callbacks scope) (resume:)
    register resume
    pure (Accepted resume)
v_asyncSubscribeCompletion :: Completion a -> (a -> IO ()) -> IO AsyncSubscription
v_asyncSubscribeCompletion cell callback = do
  forced <- evaluate cell
  case forced of
    Completion scope value waiting -> do
      current <- readIORef value
      reserve scope (v_asyncReadCompletion cell callback (pure ())) (\r -> modifyIORef' waiting (filter (not . same r))) $ \resume ->
        case current of
          Just _ -> modifyIORef' (ready scope) (Q.|> resume)
          Nothing -> modifyIORef' waiting (++[resume])

v_asyncSubscriptionStatus :: AsyncSubscription -> IO Int
v_asyncSubscriptionStatus subscription = do
  forced <- evaluate subscription
  case forced of
    Rejected n -> pure n
    Accepted (Resume scope active _ _) -> do
      isClosed <- readIORef (closed scope)
      isActive <- readIORef active
      pure (if isClosed then 3 else if isActive then 0 else 6)
retire :: Resume -> IO ()
retire resume@(Resume scope active action unlink) = do
  writeIORef active False
  writeIORef action Nothing
  modifyIORef' (callbackCount scope) (subtract 1)
  modifyIORef' (callbacks scope) (filter (not . same resume))
  unlink
v_asyncCancelSubscription :: AsyncSubscription -> IO Int
v_asyncCancelSubscription subscription = do
  status <- v_asyncSubscriptionStatus subscription
  case subscription of
    Accepted resume@(Resume scope _ _ _) | status==0 -> do
      retire resume
      modifyIORef' (ready scope) (Q.filter (not . same resume))
      modifyIORef' (timers scope) (filter (not . same resume . snd))
      pure 0
    _ -> pure status
v_asyncEnqueue :: AsyncScope -> IO () -> IO AsyncSubscription
v_asyncEnqueue scope action = reserve scope action (\_ -> pure ()) (\r -> modifyIORef' (ready scope) (Q.|> r))
v_asyncDelay :: AsyncScope -> Int -> IO () -> IO AsyncSubscription
v_asyncDelay scope milliseconds action = do
  _ <- readIORef (closed scope) -- Force the scope before the delay operand.
  _ <- evaluate (bounded "invalid async delay" 4294967295 milliseconds)
  now <- clock
  reserve scope action (\_ -> pure ()) $ \r -> modifyIORef' (timers scope) (insertTimer (now+milliseconds,r))
  where insertTimer x [] = [x]
        insertTimer x (y:ys) = if fst x<fst y then x:y:ys else y:insertTimer x ys
mature :: AsyncScope -> Int -> IO ()
mature scope now = do
  queue <- readIORef (timers scope)
  let (due,rest)=span ((<=now).fst) queue
  writeIORef (timers scope) rest
  modifyIORef' (ready scope) (Q.>< Q.fromList (map snd due))
v_asyncStep :: AsyncScope -> IO Int
v_asyncStep scope = do
  isClosed <- readIORef (closed scope)
  busy <- readIORef (dispatching scope)
  if isClosed then pure 3 else if busy then pure 8 else do
    clock >>= mature scope
    queue <- readIORef (ready scope)
    case Q.viewl queue of
      Q.EmptyL -> pure 1
      resume@(Resume _ active action _ ) Q.:< rest -> do
        writeIORef (ready scope) rest
        isActive <- readIORef active
        if not isActive then v_asyncStep scope else do
          stored <- readIORef action
          retire resume
          case stored of
            Nothing -> pure 6
            Just callback -> do
              writeIORef (dispatching scope) True
              callback `finally` writeIORef (dispatching scope) False
              pure 0
v_asyncWait :: AsyncScope -> Int -> IO Int
v_asyncWait scope limit = do
  _ <- readIORef (closed scope)
  when (limit/=(-1)) (evaluate (bounded "invalid async wait" 4294967295 limit) >> pure ())
  start <- clock
  loop start
  where loop start = do
          isClosed <- readIORef (closed scope)
          busy <- readIORef (dispatching scope)
          if isClosed then pure 3 else if busy then pure 8 else do
            now <- clock
            mature scope now
            queue <- readIORef (ready scope)
            later <- readIORef (timers scope)
            if not (Q.null queue) then pure 0 else case later of
              [] -> pure 1
              (deadline,_):_ -> if limit/=(-1) && now-start>=limit then pure 1 else do
                let pause=min 1000 (min (deadline-now) (if limit==(-1) then deadline-now else limit-(now-start)))
                threadDelay (fromIntegral (max 0 pause)*1000)
                loop start
