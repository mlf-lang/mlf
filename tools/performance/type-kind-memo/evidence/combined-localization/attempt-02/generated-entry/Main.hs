module Main where
import Control.Exception(bracket)
import MLF.Host.IO(runEntry)
import qualified MLF.Entry.Emlf as Entry
import qualified KindCounters
main = bracket KindCounters.startReporting KindCounters.stopReporting $ \_ -> do
  KindCounters.boundary "entry.main.enter"
  runEntry Entry.main
