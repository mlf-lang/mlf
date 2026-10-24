{-# LANGUAGE ForeignFunctionInterface, ScopedTypeVariables #-}
module Main where
import qualified MLF.Host.IO as H
import qualified MLF.Host.Base as B
import Control.Concurrent
import Control.Exception
import Foreign.C
import Control.Monad
import System.Exit
foreign import ccall unsafe "mlf_probe_ready" ready :: IO CInt
foreign import ccall unsafe "mlf_probe_freed" freed :: IO CInt
main = do
  done <- newEmptyMVar
  worker <- forkFinally (H.v_getEnv (B.literal "MLF_HOST_REVIEW_NO_SUCH_VAR")) (putMVar done)
  let await = ready >>= \r -> when (r==0) (threadDelay 1000 >> await)
  await
  throwTo worker ThreadKilled
  result <- takeMVar done
  case result of
    Left e -> putStrLn ("worker exception="++displayException e)
    Right _ -> error "worker was not cancelled"
  f <- freed
  putStrLn ("returned C buffer freed="++show (f/=0))
  unless (f/=0) exitFailure
