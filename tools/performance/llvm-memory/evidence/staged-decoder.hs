module Main where
import Prelude
import Control.Exception(evaluate)
import Control.Monad(forM)
import System.Environment(getArgs)
import System.IO(hPutStrLn,stderr)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.LLVM as LLVM
import qualified Bootstrap.X.Checked as C
ok label value=case value of T.Left e->error(B.unpack e);T.Right x->hPutStrLn stderr label>>pure x
main=do
 [path]<-getArgs
 interfaces<-A.loadInterfaces[B.literal path]>>=ok "INTERFACES"
 objects<-forM interfaces $ \(metadata,iface)->do
  hPutStrLn stderr("READ OBJECT "++B.unpack metadata)
  obj<-A.readObject(A.objectPath metadata)iface>>=ok "DECODED OBJECT"
  pure obj
 let root=snd(last interfaces)
 term<-ok "LINKED CHECKED" (A.linkCheckedObjects objects(A.crateId root))
 chunks<-ok "LLVM GENERATED" (LLVM.emitCheckedChunks False term)
 mapM_ (putStr.B.unpack) chunks
