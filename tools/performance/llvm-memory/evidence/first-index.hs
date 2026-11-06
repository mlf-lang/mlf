module Main where
import Prelude
import Control.Exception(evaluate)
import System.Environment(getArgs)
import System.IO(hPutStrLn,stderr)
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P
main=do
 [path]<-getArgs
 hPutStrLn stderr "START read"
 value<-P.readFile(B.literal path)
 n<-evaluate(P.stringLength value)
 hPutStrLn stderr("READ scalars="++show n)
 x<-evaluate(P.stringCodeAt value 0)
 hPutStrLn stderr("INDEX first="++show x)
