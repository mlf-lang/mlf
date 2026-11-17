module Main where
import System.Environment (getArgs)
import MLF.Host.IO (runEntry)
import qualified MLF.Entry.Emlf as Entry
import qualified Prototype.ProjectionIdentityCapture as Capture
main :: IO ()
main=do
  args<-getArgs
  if args==["--self-test"]
    then Capture.selfTest
    else do
      runEntry Entry.main
      Capture.writeCapture "projection-identity"
