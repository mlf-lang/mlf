{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
module FileMain where
import Prelude
import Control.Monad (unless)
import System.Environment (getArgs)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.Crate as Old
import qualified Bootstrap.CrateSession as New
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.X.Check as Check
import qualified Bootstrap.X.Type as XT
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Parser as XP
import qualified Bootstrap.X.Pretty as Pretty

right :: String -> T.Either B.String a -> IO a
right label answer=case answer of
 T.Left message->errorWithoutStackTrace(label++": "++B.unpack message)
 T.Right value->pure value
assert :: String -> Bool -> IO ()
assert label value=unless value(errorWithoutStackTrace label)
expectedType :: String -> T.XType
expectedType "Int"=T.XCon "Int" []
expectedType "Bool"=T.XCon "Bool" []
expectedType "Bottom"=T.XBot
expectedType _=errorWithoutStackTrace "unknown independent file type oracle"
checkArtifact :: String -> String -> IO ()
checkArtifact prefix wanted=do
 checked<-Artifact.linkCheckedFile(B.literal(prefix++".mlfci")) >>= right "read/link checked artifact"
 let term=Checked.term checked; expected=expectedType wanted
 assert "artifact's checked type differs from handwritten oracle"(XT.alphaEq(Checked.typeOf checked)expected)
 actual<-right "original target recheck"(Check.checkClosed term)
 assert "original target check differs from handwritten oracle"(XT.alphaEq actual expected)
 parsed<-right "target text roundtrip"(XP.parseTerm "<private session control roundtrip>"(Pretty.prettyTerm term))
 again<-right "roundtrip original target recheck"(Check.checkClosed parsed)
 assert "roundtrip type differs from handwritten oracle"(XT.alphaEq again expected)
 assert "roundtrip changed erased term"(X.equalErased(X.erase term)(X.erase parsed))
main :: IO ()
main=do
 args<-getArgs
 case args of
  [implementation,spec,prefix,wanted]->do
   assert "unknown implementation"(implementation=="old"||implementation=="session")
   answer<-(if implementation=="old" then Old.compileSpecFile else New.compileSpecFile)(B.literal spec)(B.literal prefix)
   case answer of
    T.Left message->do
     assert "positive parsed fixture rejected"(wanted=="reject")
     putStrLn("REJECT "++show(B.unpack message))
    T.Right ()->do
     assert "negative parsed fixture accepted"(wanted/="reject")
     checkArtifact prefix wanted
     putStrLn("PASS file checked "++wanted)
  _->errorWithoutStackTrace "usage: file-controls old|session spec prefix Int|Bool|Bottom|reject"
