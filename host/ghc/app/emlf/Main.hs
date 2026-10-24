module Main where
import MLF.Host.IO (runEntry)
import qualified MLF.Entry.Emlf as Entry
main :: IO ()
main = runEntry Entry.main
