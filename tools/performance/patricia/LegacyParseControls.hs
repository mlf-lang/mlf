module Main(main) where
import Prelude
import Control.Monad(forM_)
import System.Environment(getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Parser as P
import qualified MLF.Host.Base as B
main=do
 files<-getArgs
 forM_ files $ \file->do
  source<-readFile file
  case P.parseModule(B.literal file)(B.literal source)of
   T.Left e->error(file++": "++B.unpack e)
   T.Right _->putStrLn("PASS parse "++file)
