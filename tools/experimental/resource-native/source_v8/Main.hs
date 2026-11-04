module Main where
import MLF.Host.IO (runEntry)
import qualified ResourceSharedExport as Capture
main :: IO ()
main = runEntry Capture.main
