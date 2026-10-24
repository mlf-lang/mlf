module Main where
import qualified MLF.Tests.Async.TaskProcesses as Entry
import MLF.Host.IO (runEntry)
main :: IO ()
main = runEntry Entry.main
