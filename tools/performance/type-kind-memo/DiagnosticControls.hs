{-# LANGUAGE OverloadedStrings #-}
module DiagnosticControls where
import Prelude
import Control.Concurrent (threadDelay)
import Control.Exception (bracket)
import System.Environment (getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.X.Type as X
import qualified Bootstrap.Data as D
import qualified Bootstrap.Map as M
import qualified KindCounters as C
v n = T.XTyVar n
check value expected = case value of
 T.Right T.Star | expected -> pure ()
 T.Left _ | not expected -> pure ()
 _ -> error "diagnostic changed result"
controls = do
 let env = M.fromList X.compareTyVar [(v n, if n < 2 then T.XBot else T.XArrow (T.XVar(v(n-1))) (T.XVar(v(n-2)))) | n <- [0..4]]
 check (X.kindOf D.emptyDataEnv env (T.XVar(v 4))) True
 check (X.kindOf D.emptyDataEnv (M.singleton (v 0) (T.XVar(v 0))) (T.XVar(v 0))) False
 check (X.kindOf D.emptyDataEnv M.empty (T.XArrow (T.XVar(v 0)) (T.XVar(v 1)))) False
 check (X.kindOf D.emptyDataEnv (error "unused") T.XBot) True
main = do
 args <- getArgs
 case args of
  [] -> do
   controls
   C.report
   putStrLn "PASS diagnostic value and demand controls"
  ["--reporter-control"] -> bracket C.startReporting C.stopReporting $ \_ -> do
   C.boundary "controls.begin"
   controls
   C.event "controls.complete"
   threadDelay 2100000
   putStrLn "PASS live diagnostic snapshots"
  _ -> error "unknown diagnostic control mode"
