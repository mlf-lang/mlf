module Main where
import qualified MLF.Primitive as F
import qualified MLF.Host.Base as B
main = do
  count <- F.getArgCount
  args <- mapM (F.getArg) [0..count-1]
  print count
  print (map B.unpack args)
