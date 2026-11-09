module Main where
import qualified MLF.Primitive as F
import qualified MLF.Host.Base as B
import qualified MLF.Host.IO as H
import System.Environment
main = do
  args <- getArgs
  case args of
    ["nested"] -> H.runEntry (F.panic (F.panic (B.literal "inner")))
    ["unicode"] -> H.runEntry (F.panic (B.literal "😀"))
    _ -> error "unknown panic probe"
