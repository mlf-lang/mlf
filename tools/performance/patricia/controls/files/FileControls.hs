{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
module FileControls where
import Prelude
import Control.Monad (unless)
import System.Environment (getArgs)
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.Crate as Old
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.CrateQuery as Query
import qualified Bootstrap.Map as M
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.X.Check as Check
import qualified Bootstrap.X.Type as XT
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Parser as XP
import qualified Bootstrap.X.Pretty as Pretty

-- Keep the historical closed-object file producer inside its oracle fixture.
-- Production source and specification entry points now use CrateSession.
-- The original preparation, diagnostics, payload publication and report order
-- remain the independent comparison, including the parsed-source encoding mode.
legacyCompileSpecFile :: B.String -> B.String -> IO (T.Either B.String ())
legacyCompileSpecFile file prefix = do
 loaded <- Old.loadSpecFile Artifact.loadInterfaces file
 case loaded of
  T.Left message -> pure (T.Left message)
  T.Right (spec,sources,interfaces) -> do
   dependencies <- Old.withPrelude spec sources interfaces
   case dependencies of
    T.Left message -> pure (T.Left message)
    T.Right (updated,available) -> case Old.prepareCrate updated available sources of
     T.Left message -> pure (T.Left message)
     T.Right prepared -> do
      result <- Old.compilePreparedWithEncoding True
        (\object payload report -> (object,payload,report)) updated available prepared
      case result of
       T.Left message -> do
        let names = Modules.resolvedCrateDisplayNames (Old.preparedResolution prepared)
            diagnostics = M.union B.v_compareString
              (M.map (Modules.displayNames names) (Old.preparedNames prepared)) names
        pure (T.Left (Modules.displayNames diagnostics message))
       T.Right (object,payload,report) -> do
        written <- Artifact.writeObjectWithPayloadEither prefix object payload
        case written of
         T.Left message -> pure (T.Left message)
         T.Right _ -> do
          P.writeFile (B.v_concatString prefix ".queries") (Query.reportJSON
            (Old.specIdentity updated) (Artifact.semanticFingerprint (Artifact.objectInterface object)) report)
          pure (T.Right ())

compileFile :: B.String -> B.String -> IO (T.Either B.String ())
compileFile = legacyCompileSpecFile

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
  [spec,prefix,wanted]->do
   answer<-compileFile(B.literal spec)(B.literal prefix)
   case answer of
    T.Left message->do
     assert "positive parsed fixture rejected"(wanted=="reject")
     putStrLn("REJECT "++show(B.unpack message))
    T.Right ()->do
     assert "negative parsed fixture accepted"(wanted/="reject")
     checkArtifact prefix wanted
     putStrLn("PASS file checked "++wanted)
  _->errorWithoutStackTrace "usage: file-controls spec prefix Int|Bool|Bottom|reject"
