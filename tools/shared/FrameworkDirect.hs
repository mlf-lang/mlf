{-# LANGUAGE OverloadedStrings #-}
-- Test-only host entry. Imports maintained framework sources without rewriting.
module Main where
import Control.Exception (SomeException, try)
import Control.Monad (unless)
import Data.IORef
import qualified Bootstrap.Types as T
import qualified MLF.Primitive as P
import qualified Test.Assert as A
import qualified Test.Case as C
import qualified Test.Runner as R
import qualified Test.Registry as Registry

ensure :: Bool -> String -> IO ()
ensure condition label = unless condition (error label)
left :: T.Either A.Failure a -> Bool
left (T.Left _) = True
left _ = False
rightUnit :: T.Either A.Failure () -> Bool
rightUnit (T.Right ()) = True
rightUnit _ = False

main :: IO ()
main = do
  events <- newIORef ([] :: [String])
  let tick label value = A.liftIO (modifyIORef' events (++ [label]) >> pure value)
      failed = A.fail "expected" :: A.Test Integer
  mapped <- A.run (fmap (\_ -> error "fmap forced failed continuation") failed)
  ensure (left mapped) "fmap must short-circuit Left"
  applied <- A.run ((A.fail "expected" :: A.Test (Integer -> Integer)) <*> tick "forbidden" 1)
  ensure (left applied) "Applicative must short-circuit Left"
  bound <- A.run (failed >>= \_ -> tick "forbidden" 2)
  ensure (left bound) "Monad must short-circuit Left"
  trace0 <- readIORef events
  ensure (null trace0) "failed computations ran later IO"
  lazy <- A.run (fmap (\_ -> ()) (pure (error "pure forced payload") :: A.Test Integer))
  ensure (rightUnit lazy) "successful payload must remain lazy"
  value <- A.run (tick "function" (+1) <*> tick "argument" (41 :: Integer))
  case value of
    T.Right n -> ensure (n == 42) "Applicative value changed"
    _ -> error "Applicative unexpectedly failed"
  trace1 <- readIORef events
  ensure (trace1 == ["function", "argument"]) "Applicative IO order or multiplicity changed"
  let repeated = tick "repeat" ()
  _ <- A.run repeated
  _ <- A.run repeated
  trace2 <- readIORef events
  ensure (trace2 == ["function", "argument", "repeat", "repeat"]) "shared IO action was memoized"
  let entries = (:) (C.test "probe/fail" "failure" [] (A.fail "expected"))
              ((:) (C.test "probe/after" "continued" [] (tick "after" ())) [])
  case R.plan ((:) "--list" []) entries of
    T.Right _ -> pure ()
    _ -> error "list planning failed"
  listed <- R.run ((:) "--list" ((:) "--format" ((:) "json" []))) entries
  ensure (listed == 0) "actual discovery failed"
  let duplicate = (:) (C.test "probe/same" "first" [] (tick "forbidden" ()))
                 ((:) (C.test "probe/same" "second" [] (tick "forbidden" ())) [])
  case R.plan [] duplicate of
    T.Left _ -> pure ()
    _ -> error "duplicate IDs accepted"
  case Registry.exactInventory ((:) "expected" []) ((:) "different" []) of
    T.Left _ -> pure ()
    _ -> error "observed IDs substituted for expected inventory"
  trace3 <- readIORef events
  ensure (trace3 == trace2) "discovery executed case actions"
  results <- R.execute entries
  case results of
    (:) first ((:) second []) -> ensure (not (R.passed first) && R.passed second) "runner stopped after value failure"
    _ -> error "runner changed result inventory"
  trace4 <- readIORef events
  ensure (trace4 == trace2 ++ ["after"]) "runner repeated or omitted action"
  crashed <- try (A.run (A.liftIO (ioError (userError "must escape")))) :: IO (Either SomeException (T.Either A.Failure ()))
  case crashed of
    Left _ -> pure ()
    Right _ -> error "framework swallowed IO exception"
  putStrLn "Framework standard-class, demand, IO-order, discovery and continuation controls passed."
