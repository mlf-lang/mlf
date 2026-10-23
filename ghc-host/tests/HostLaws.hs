{-# LANGUAGE ScopedTypeVariables #-}
module Main where

import Prelude
import qualified MLF.Host.Base as B
import qualified MLF.Host.IO as H
import qualified MLF.Host.Async as A
import Control.Exception
import Data.IORef
import Control.Monad (unless)

assertEqual :: (Eq a, Show a) => String -> a -> a -> IO ()
assertEqual label expected actual = unless (expected==actual) (error (label++": expected "++show expected++", got "++show actual))
failureIs :: String -> String -> a -> IO ()
failureIs label expected value = do
  result <- try (evaluate value)
  case result of
    Left (B.HostError message) -> assertEqual label expected message
    Right _ -> error (label++": expected failure")
main :: IO ()
main = do
  failureIs "integer argument order" "left" (B.v_addInt (B.failure "left") (B.failure "right"))
  failureIs "formatDouble forces value before range check" "value" (B.v_formatDouble 99 (B.failure "value"))
  failureIs "formatDouble left operand" "precision" (B.v_formatDouble (B.failure "precision") (B.failure "value"))
  assertEqual "ties-to-even formatting" "2" (B.unpack (B.v_formatDouble 0 2.5))
  assertEqual "negative zero formatting" "-0.000" (B.unpack (B.v_formatDouble 3 (-0.0)))
  failureIs "surrogate rejected" "invalid Unicode scalar" (B.v_stringFromCode 0xd800)
  failureIs "UTF8 String index" "string index out of bounds" (B.v_stringCodeAt (B.literal "😀") 1)
  mapM_ (\s -> failureIs ("readDouble "++s) "invalid Double input" (B.v_readDouble (B.literal s))) ["NaN","Infinity"," 1","1 ",".1","1.","1e",""]
  assertEqual "large integer rounding" 9007199254740992 (B.v_intToDouble 9007199254740993)
  -- Merely forcing an action must not execute it or force stored operands.
  evaluate (B.v_newSTArray (B.failure "size forced early") (B.failure "initial forced early"))
  assertEqual "ST read snapshot and repeated action" (10,20) (B.v_runST $ do
    a <- B.v_newSTArray 1 (10::Integer)
    let readAgain=B.v_readSTArray a 0
    before <- readAgain
    B.v_writeSTArray a 0 20
    after <- readAgain
    pure (before,after))
  assertEqual "empty lazy ST cell" 0 (B.v_runST $ B.v_newSTArray 0 (B.failure "poison") >>= B.v_lengthSTArray)
  scope <- A.v_asyncScopeNew 8 2
  order <- newIORef ([]::[Integer])
  A.v_asyncNewCompletion scope (\cell -> do
    r <- A.v_asyncSubscribeCompletion cell (\n -> modifyIORef' order (++[n]) >> pure B.Unit)
    cancelled <- A.v_asyncSubscribeCompletion cell (\_ -> error "cancelled callback ran")
    A.v_asyncCancelSubscription cancelled >>= assertEqual "cancel pending" 0
    A.v_asyncResolveCompletion cell 7 >>= assertEqual "first resolve" 0
    A.v_asyncResolveCompletion cell (B.failure "second payload forced") >>= assertEqual "one shot" 2
    readIORef order >>= assertEqual "resolve is cold" []
    A.v_asyncStep scope >>= assertEqual "step callback" 0
    readIORef order >>= assertEqual "typed payload" [7]
    A.v_asyncWait scope 0 >>= assertEqual "cancelled waiter never ready" 1
    A.v_asyncSubscriptionStatus r >>= assertEqual "consumed" 6
    pure B.Unit) (error "unexpected cell rejection")
  _ <- A.v_asyncEnqueue scope (do
    A.v_asyncStep scope >>= assertEqual "reentrant step" 8
    A.v_asyncWait scope 0 >>= assertEqual "reentrant wait" 8
    pure B.Unit)
  A.v_asyncStep scope >>= assertEqual "outer step" 0
  _ <- A.v_asyncDelay scope 0 (modifyIORef' order (++[8]) >> pure B.Unit)
  _ <- A.v_asyncDelay scope 0 (modifyIORef' order (++[9]) >> pure B.Unit)
  A.v_asyncWait scope 0 >>= assertEqual "timer maturity" 0
  A.v_asyncStep scope >>= assertEqual "timer first" 0
  A.v_asyncStep scope >>= assertEqual "timer second" 0
  readIORef order >>= assertEqual "timer FIFO" [7,8,9]
  A.v_asyncScopeClose scope
  A.v_asyncStep scope >>= assertEqual "closed scope" 3
  reply <- H.v_processSupervisor (B.literal "MLF-PROCESS-1\0version\0")
  assertEqual "same native process protocol" "0\0" (take 2 (B.unpack reply))
  putStrLn "Host adapter laws passed."
