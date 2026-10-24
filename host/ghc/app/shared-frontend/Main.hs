module Main where
import qualified MLF.Tests.SharedFrontend as Entry
import MLF.Host.IO (runEntry)
main :: IO ()
main = runEntry Entry.main
