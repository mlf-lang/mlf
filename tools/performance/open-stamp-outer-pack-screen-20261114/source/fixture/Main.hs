{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import qualified Control.Exception as E
import Control.Monad (forM_,unless)
import System.Environment (getArgs)
import qualified System.Mem as Mem
import qualified GHC.Clock as Clock
import Data.Char (ord)
import Data.List (foldl',isSuffixOf)
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.OpenFragment as O
import qualified Bootstrap.Separate as S
import qualified Bootstrap.Data as D
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.X.Checked as Checked
import qualified StampReference as Ref
import qualified StampProbe as Probe
import Cases

need :: Bool -> String -> IO ()
need good message=unless good (error message)
right :: T.Either B.String a -> IO a
right (T.Left e)=error (B.unpack e)
right (T.Right x)=pure x
forced :: B.String -> IO String
forced text=E.evaluate (forceText text) >> pure (B.unpack text)
rawRef (Raw ds ps term bs)=Ref.stamp (Ref.Environment ds (poison "unused-data-environment")) ps term bs
rawProbe (Raw ds ps term bs)=Probe.stamp (Probe.Environment ds (poison "unused-data-environment")) ps term bs
rawFields (Raw ds ps term bs)=
 [S.pack (map (D.prettyDeclaration . Ref.canonicalDeclaration) ds),
  S.pack [S.pack [P.showInt (X.nameId n),X.nameHint n,Pretty.prettyType (S.normalType t)] | (n,t)<-ps],
  Pretty.prettyTerm term,
  S.pack [S.pack [X.nameHint n,Pretty.prettyType (S.normalType t)] | (n,t)<-bs]]
frame :: [String] -> String
frame=concatMap (\s->show (length s)++":"++s)
scalarFingerprint :: String -> String
scalarFingerprint text=let (a,b)=foldl' step (0,1) text in show a++"-"++show b where
 step (a,b) c=((a*65599+toInteger(ord c)) `mod` 2147483647,
               (b*131+toInteger(ord c)) `mod` 2147483629)

chooseError :: E.SomeException -> Maybe String
chooseError e=case E.fromException e of
 Just (Sentinel message)->Just ("sentinel:"++message)
 Nothing->case E.fromException e of
  Just (B.HostError message)->Just ("host:"++message)
  Nothing->Nothing -- Async and unexpected failures escape.
outcome :: B.String -> IO (Either String String)
outcome text=E.tryJust chooseError (forced text)
whnfOutcome :: B.String -> IO (Either String ())
whnfOutcome text=E.tryJust chooseError (E.evaluate text >> pure ())
pass :: String -> IO ()
pass label=putStrLn ("PASS\t"++label)

checkFinite :: (String,Raw) -> IO ()
checkFinite (label,raw)=do
 oldWhnf<-whnfOutcome(rawRef raw);newWhnf<-whnfOutcome(rawProbe raw)
 need(oldWhnf==Right () && newWhnf==oldWhnf) ("finite WHNF mismatch: "++label)
 expected<-forced (rawRef raw)
 actual<-forced (rawProbe raw)
 let fields=map B.unpack (rawFields raw)
 need (actual==expected && expected==scalarFingerprint(frame fields)) ("finite stamp mismatch: "++label)
 decoded<-right (S.unpack (S.pack (rawFields raw)))
 need (map B.unpack decoded==fields) ("framing mismatch: "++label)
 pass label
checkPoison :: (String,String,Raw) -> IO ()
checkPoison (label,wanted,raw)=do
 oldWhnf<-whnfOutcome(rawRef raw);newWhnf<-whnfOutcome(rawProbe raw)
 need(oldWhnf==Left("sentinel:"++wanted) && newWhnf==oldWhnf) ("poison WHNF mismatch: "++label)
 expected<-outcome (rawRef raw);actual<-outcome (rawProbe raw)
 need (expected==Left ("sentinel:"++wanted) && actual==expected) ("first error mismatch: "++label)
 pass label
checkFraming :: (Int,[B.String]) -> IO ()
checkFraming (index,fields)=do
 old<-forced (S.fingerprint (S.pack fields))
 eligible<-E.evaluate(Probe.stampFieldsFit guardLimit fields)
 need eligible "small framing unexpectedly fell back"
 new<-forced (Probe.stampFields fields)
 need (old==new && old==scalarFingerprint(frame(map B.unpack fields))) "scalar framing arithmetic mismatch"
 pass ("framing-"++show index)

publicReference :: O.Fragment -> B.String
publicReference f=Ref.stamp (Ref.Environment (O.declarations(O.context f)) (poison "unused-data-environment"))
  (O.parameters f) (O.body f) (O.bindings f)
checkPublicFingerprint label f=do
 a<-forced(O.fingerprint f);b<-forced(publicReference f)
 need (a==b) ("public production mismatch: "++label);pass label
publicControls=do
 env<-right(O.environment [])
 let external=name 3 "external:\x96ea";local=name 4 "result";
     body=T.XLet local (T.XVarTerm external) unit
 f<-right(O.check env [(external,intType)] body)
 checkPublicFingerprint "public-check" f
 audited<-right(O.audit f);checkPublicFingerprint "public-audit" audited
 normalized<-right(O.normalize f body);checkPublicFingerprint "public-normalize" normalized
 let (next,renamed)=O.fresh 1000 f
 need (next>1000) "fresh identity did not advance"
 checkPublicFingerprint "public-fresh" renamed
 old<-forced(O.fingerprint f);new<-forced(O.fingerprint renamed)
 need (old/=new) "fresh retained an old stamp"
 checked<-right(Checked.check (T.XAbs external intType body))
 admitted<-right(O.fromChecked checked);checkPublicFingerprint "public-fromChecked" admitted
 case O.check env [(external,intType),(external,intType)] (poison "unchecked-body") of
  T.Left message->do
   actual<-forced message;need(actual=="duplicate open-fragment parameter") "duplicate parameter first error";pass "public-duplicate-before-body"
  T.Right _->error "duplicate parameter accepted"

checkBoundary :: (String,Bool,Raw) -> IO ()
checkBoundary (label,wanted,raw)=do
 let fields=rawFields raw
 lengths<-mapM (E.evaluate . P.stringLength) fields
 need(lengths==[0,0,if wanted then (if "-at" `isSuffixOf` label then 262124 else 262123) else 262125,0]) "threshold fixture shape changed"
 eligible<-E.evaluate(Probe.stampFieldsFit guardLimit fields)
 need(eligible==wanted) ("threshold branch mismatch: "++label)
 -- At the exact conservative bound, exercise remaining threshold -1/0/+1.
 if "-at" `isSuffixOf` label then do
   below<-E.evaluate(Probe.stampFieldsFit (guardLimit-1) fields)
   at<-E.evaluate(Probe.stampFieldsFit guardLimit fields)
   above<-E.evaluate(Probe.stampFieldsFit (guardLimit+1) fields)
   need(not below && at && above) "remaining threshold boundary mismatch"
  else pure ()
 oldWhnf<-whnfOutcome(rawRef raw);newWhnf<-whnfOutcome(rawProbe raw)
 need(oldWhnf==Right () && newWhnf==oldWhnf) "threshold WHNF mismatch"
 old<-forced(rawRef raw);new<-forced(rawProbe raw)
 need(old==new) ("actual old/candidate threshold stamp mismatch: "++label)
 oldFields<-forced(S.fingerprint(S.pack fields));newFields<-forced(Probe.stampFields fields)
 need(oldFields==old && newFields==old) "actual threshold helper disagrees with real stamp"
 pass label

checkEarlyStop :: Int -> IO ()
checkEarlyStop before=do
 let label="guard-early-stop-"++show(before+1)
     oversized=B.literal(replicate 262140 'x')
     fields=replicate before "" ++ (oversized:poison "after-stop")
 -- Inspect the real private eligibility result separately. An equality of
 -- final exceptions alone would not establish that the guard stops early.
 eligible<-E.tryJust chooseError (E.evaluate(Probe.stampFieldsFit guardLimit fields))
 need(eligible==Right False) "guard demanded after oversized field"
 oldWhnf<-whnfOutcome(S.fingerprint(S.pack fields))
 newWhnf<-whnfOutcome(Probe.stampFields fields)
 old<-outcome(S.fingerprint(S.pack fields));new<-outcome(Probe.stampFields fields)
 need(oldWhnf==Left "sentinel:after-stop" && newWhnf==oldWhnf &&
      old==Left "sentinel:after-stop" && new==old) "fallback changed next error"
 pass label

checkHostError :: (String,String,Raw) -> IO ()
checkHostError (label,wanted,raw)=do
 oldWhnf<-whnfOutcome(rawRef raw);newWhnf<-whnfOutcome(rawProbe raw)
 old<-outcome(rawRef raw);new<-outcome(rawProbe raw)
 need(oldWhnf==Left wanted && newWhnf==oldWhnf && old==Left wanted && new==old) "real HostError order mismatch"
 pass label

checkErrorBeforeLarge :: IO ()
checkErrorBeforeLarge=do
 let fields=[poison "before-large",B.literal(replicate 262140 'x'),"",""]
 guardResult<-E.tryJust chooseError(E.evaluate(Probe.stampFieldsFit guardLimit fields))
 old<-outcome(S.fingerprint(S.pack fields));new<-outcome(Probe.stampFields fields)
 oldWhnf<-whnfOutcome(S.fingerprint(S.pack fields));newWhnf<-whnfOutcome(Probe.stampFields fields)
 need(guardResult==Left "sentinel:before-large" && old==Left "sentinel:before-large" &&
      new==old && oldWhnf==Left "sentinel:before-large" && newWhnf==oldWhnf) "guard skipped first error"
 pass "guard-error-before-large"

controls=do
 forM_ finiteRaw checkFinite
 forM_ poisonRaw checkPoison
 forM_ (zip [1..] framingFields) checkFraming
 -- A binding name's numeric id is not part of this exact stamp field.
 let unusedId=Raw [] [] unit [(T.XName (poison "unused-binding-id") "only-hint",intType)]
 a<-forced(rawRef unusedId);b<-forced(rawProbe unusedId)
 need(a==b) "unused binding identity newly forced";pass "unused-binding-id"
 -- Private Environment's checked-data field is not used by stamp.
 a0<-forced(rawRef baseRaw);b0<-forced(rawProbe baseRaw)
 need(a0==b0) "private data environment newly forced";pass "unused-data-environment"
 publicControls
 forM_ boundaryRaw checkBoundary
 forM_ [0,1,2] checkEarlyStop
 forM_ hostErrorRaw checkHostError
 checkErrorBeforeLarge
 putStrLn "SUMMARY\t58"

-- This is the same allocation/clock window order as the qualified codec
-- fixture. Empty windows are retained raw, never subtracted or called warmup.
{-# NOINLINE observe #-}
observe action=do
 before<-Mem.getAllocationCounter
 t0<-Clock.getMonotonicTimeNSec
 value<-action
 t1<-Clock.getMonotonicTimeNSec
 after<-Mem.getAllocationCounter
 let allocated=before-after;elapsed=t1-t0
 E.evaluate allocated;E.evaluate elapsed
 pure(value,(allocated,elapsed))
{-# NOINLINE prepareFragment #-}
prepareFragment size repetition=do
 let term=benchmarkTerm size repetition
 E.evaluate(forceBenchmark term)
 env<-right(O.environment [])
 fragment<-right(O.check env [] term)
 E.evaluate(O.body fragment)
 E.evaluate(forceBindings(O.bindings fragment))
 -- Never inspect O.fingerprint here. The checked Fragment's stamp remains lazy.
 pure fragment
{-# NOINLINE stampAction #-}
stampAction fragment=do
 let digest=O.fingerprint fragment
 E.evaluate(P.stringLength digest) -- String has strict text and scalar-count fields.
 pure digest
record label size repetition digest (allocated,elapsed)=putStrLn
 (label++"\t"++show size++"\t"++show repetition++"\t"++digest++"\t"++show allocated++"\t"++show elapsed)
measure=forM_ [8,32,128,512] $ \size->forM_ [1,2,3] $ \repetition->do
 fragment<-prepareFragment size repetition
 (_,emptyBefore)<-observe(pure ())
 (digest,stats)<-observe(stampAction fragment)
 (_,emptyAfter)<-observe(pure ())
 record "empty-before" size repetition "-" emptyBefore
 record "stamp" size repetition (B.unpack digest) stats
 record "empty-after" size repetition "-" emptyAfter
main=do
 args<-getArgs
 case args of
  ["controls"]->controls
  ["measure"]->measure
  _->error "expected controls or measure"
