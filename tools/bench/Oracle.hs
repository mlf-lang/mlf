-- Independent benchmark oracle adapter for native-default.py. Compile this
-- against the same authenticated mlf-shared package as the benchmark tools.
module Main where
import Prelude hiding (String)
import qualified Prelude as H
import qualified Package.Benchmark as B
import qualified MLF.Primitive as P
import qualified Data.ByteString as BS
import System.Environment (getArgs)
import System.Exit (exitFailure)
main = do
 args <- getArgs
 case args of
  [name,size,path] -> do
   bytes <- BS.readFile path
   if B.validateOutput (P.textFromChars name) (H.read size) (H.map fromIntegral (BS.unpack bytes))
    then H.putStrLn "oracle passed" else exitFailure
  _ -> exitFailure
