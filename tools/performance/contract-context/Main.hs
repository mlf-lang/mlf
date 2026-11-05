{-# LANGUAGE OverloadedStrings #-}
module Main where
import FrozenSourceKey (upgradeV6)
import Prelude
import Control.Exception (SomeException, evaluate, try, displayException)
import Control.Monad (forM_, unless)
import Data.IORef
import System.Mem.StableName (makeStableName)
import qualified Bootstrap.InferenceUnit as I
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.CrateQuery as Q
import qualified FrozenCrateQuery as F
import qualified Bootstrap.SourceInference as S
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B

sameObject a b = do
  x <- evaluate a; y <- evaluate b
  sx <- makeStableName x; sy <- makeStableName y
  pure (sx == sy)
bindingFor (Q.SourceContractEncodings entries) name = case M.lookup P.compareString name entries of
  T.Just (Q.SourceContractEncoding binding _) -> binding
  T.Nothing -> error "missing encoding"

types = [T.XBot,T.XBotKind T.Star,T.XBotKind (T.KArrow T.Star T.Star),
  T.XVar (T.XTyVar 0),T.XVar (T.XTyVar (-1)),T.XVar (T.XTyVar 9223372036854775807),
  T.XCon "Int" [],T.XCon "α😀" [T.XBot],T.XArrow T.XBot (T.XCon "Int" []),
  T.XApply (T.XCon "F" []) T.XBot,
  T.XForall (T.XTyVar 2) T.XBot (T.XVar (T.XTyVar 2)),
  T.XForall (T.XTyVar 3) T.XBot (T.XVar (T.XTyVar 3))]
names = ["value","α😀\NUL4:test","3:key"]

observe :: B.String -> IO (Either String String)
observe text = do
  value <- try (evaluate (length (B.unpack text))) :: IO (Either SomeException Int)
  pure $ case value of Left e -> Left (displayException e); Right _ -> Right (B.unpack text)

contracts entries = M.fromList P.compareString entries
contract ty classes protected = S.SourceContract ty classes protected
int = T.XCon "Int" []
bool = T.XCon "Bool" []
prepared candidates protected = S.PreparedGroup [("root",T.Nothing,T.SVar "value")]
  [("root",T.Nothing,T.SVar "value")] [("value",case candidates of { (_,_,ty):_ -> ty; [] -> int })] M.empty [("root",[],False)]
  (T.Just (S.RootAuthority "root" [] False candidates protected)) [("value",False)]

main = do
  n <- newIORef (0::Int)
  let check label ok = unless ok (fail label) >> modifyIORef' n (+1)
      roles = [T.GivenEvidence,T.SuperclassEvidence,T.InstanceEvidence]
      variants = [contract int [] False,contract bool [] False,
                  contract bool ["Eq","Show"] False,contract bool ["Show","Eq"] True]
      delta c = contracts [("value",c)]
      base = delta (head variants)
      empty = Q.prepareSourceContractEncodings M.empty
      datum = F.encodeDatatypeContext []
      key pool env group = Q.sourceQueryKeyWithContractEncodings pool "crate" "compiler" group env (Q.encodeSourceDatatypes [])
      old env group = upgradeV6 datum (F.sourceQueryKeyWithContext "crate" "compiler" group env datum)
  forM_ variants $ \v -> do
    let env=delta v
        pool=Q.extendSourceContractEncodings env (Q.prepareSourceContractEncodings base)
        ty=S.contractType v
    check "updated complete contract" (Q.cachedSourceContract pool ("value",v)==F.encodeSourceContract ("value",v))
    forM_ roles $ \role -> forM_ [[],["value"]] $ \protected -> do
      let candidate=(role,"value",ty)
          groups=[prepared [candidate] protected,prepared [candidate,candidate] protected]
      forM_ groups $ \group -> do
        check "full key bytes with role, protection and ordered repeated candidates" (key pool env group==old env group)
      check "missing entry structural candidate" (Q.cachedTypedCandidate empty protected candidate==Q.encodeTypedCandidate protected candidate)
  -- Every value here is first installed in the owning environment and cache.
  -- Name reuse without an accompanying delta is outside the driver invariant.
  forM_ names $ \name -> forM_ types $ \ty ->
    forM_ [[],["C"],["D","C"]] $ \classes -> forM_ [False,True] $ \flag -> do
      let c=contract ty classes flag
          deltaMap=contracts [(name,c)]
          cache=Q.extendSourceContractEncodings deltaMap (Q.prepareSourceContractEncodings base)
          first=Q.cachedSourceContract cache (name,c)
      check "matrix contract bytes" (first==F.encodeSourceContract (name,c))
      shared<-sameObject first (Q.cachedSourceContract cache (name,c))
      check "complete source-contract text retained" shared
      bindingShared<-sameObject (bindingFor cache name) (bindingFor cache name)
      check "candidate binding retained" bindingShared
      forM_ roles $ \role -> forM_ [[],[name],["other",name,name]] $ \protected -> do
        let candidate=(role,name,ty)
            expected=F.node "typed-definition-candidate"
              [F.encodeRole role,F.encodeBinding (name,ty),F.boolean (name `elem` protected)]
        check "matrix typed candidate exact frozen bytes" (Q.cachedTypedCandidate cache protected candidate==expected)
  let initial=Q.prepareSourceContractEncodings (contracts [("kept",contract int [] False)])
      next=Q.extendSourceContractEncodings (contracts [("new",contract bool [] True)]) initial
  kept<-sameObject (bindingFor initial "kept") (bindingFor next "kept")
  check "delta retains unrelated binding" kept
  let unusedBottom=contract (errorWithoutStackTrace "unused delta type")
        (errorWithoutStackTrace "unused delta classes") (errorWithoutStackTrace "unused delta flag")
      lazyDelta=Q.extendSourceContractEncodings (contracts [("unused",unusedBottom)]) initial
  keptDelta<-sameObject (bindingFor initial "kept") (bindingFor lazyDelta "kept")
  check "unused delta values stay lazy" keptDelta
  let v=contract int ["Eq"] True
      pool=Q.prepareSourceContractEncodings (delta v)
      cs=[(T.GivenEvidence,"value",int),(T.InstanceEvidence,"value",int),(T.SuperclassEvidence,"value",int)]
  forM_ [cs,reverse cs,cs++cs] $ \candidates ->
    check "ordered candidate sequence" (key pool (delta v) (prepared candidates ["value"])==old (delta v) (prepared candidates ["value"]))
  -- The lazy map must not force an irrelevant predecessor, including at initialization.
  let bad=errorWithoutStackTrace "unused contract forced"
      env=contracts [("unused",bad),("value",v)]
      poolUnused=Q.prepareSourceContractEncodings env
      group=prepared [(T.GivenEvidence,"value",int)] []
  check "unused bottom stays lazy" (key poolUnused env group==old env group)
  check "missing group binding cache falls back"
    (key empty env group==old env group)
  let noAuthority=S.PreparedGroup [("root",T.Nothing,T.SVar "value")]
        [("root",T.Nothing,T.SVar "value")] [("value",int)] M.empty [("root",[],False)]
        T.Nothing [("value",False)]
  check "no authority full key" (key poolUnused env noAuthority==old env noAuthority)
  -- Structural public encoders still fail in the same order as the complete frozen implementation.
  let broken=contract (errorWithoutStackTrace "type first") (errorWithoutStackTrace "classes second") False
      pairs=[(Q.encodeSourceContract ("value",broken),F.encodeSourceContract ("value",broken)),
             (Q.sourceQueryKeyWithContext (errorWithoutStackTrace "crate first") (errorWithoutStackTrace "compiler second") group env datum,
              F.sourceQueryKeyWithContext (errorWithoutStackTrace "crate first") (errorWithoutStackTrace "compiler second") group env datum)]
  forM_ pairs $ \(actual,reference) -> do
    a<-observe actual;b<-observe reference;check "public encoder first error" (a==b)
  -- Exercise a real successful finalization, then install its returned delta.
  case S.prepareSourcePlan M.empty [] [] [] (contracts [("first",IS.empty)]) [] [("first",T.Nothing,T.SIntLit 4)] of
    T.Right (T.Just plan) -> case S.prepareGroup plan M.empty ["first"] of
      T.Right first -> do
        -- A value binding is lowercase; an artifact's module identity is not.
        -- Retain the original malformed fixture as a strict rejection control.
        case I.compileLoweredGroup "first" [] [] (S.groupMembers first) of
          T.Right invalid -> case S.finishGroup first invalid of
            T.Left err -> check "invalid module identity rejected"
              (B.unpack err == "<module identity>:1:1: unexpected first; expected constructor name")
            T.Right _ -> fail "invalid module identity accepted"
          T.Left err -> fail ("compileLoweredGroup invalid identity fixture: "++B.unpack err)
        case I.compileLoweredGroup "ContractControl" [] [] (S.groupMembers first) of
          T.Right object -> case S.finishGroup first object of
            T.Right result -> do
              let final=S.finalGroupContracts result
                  cache=Q.extendSourceContractEncodings final (Q.prepareSourceContractEncodings M.empty)
              forM_ (M.toList final) $ \pair ->
                check "real finalized delta exact contract bytes" (Q.cachedSourceContract cache pair==F.encodeSourceContract pair)
              check "real finalized delta owns exactly one contract" (length (M.toList final)==1)
            T.Left err -> fail ("finishGroup finalized delta: "++B.unpack err)
          T.Left err -> fail ("compileLoweredGroup finalized delta: "++B.unpack err)
      T.Left err -> fail ("prepareGroup finalized delta: "++B.unpack err)
    _ -> fail "prepareSourcePlan finalized delta"
  -- Obtain the prepared group from the production lowering path, not a fixture constructor.
  case S.prepareSourcePlan M.empty [] [] [] (contracts [("root",IS.empty)]) [] [("root",T.Nothing,T.SVar "value")] of
    T.Right (T.Just plan) -> case S.prepareGroup plan (delta (contract int [] False)) ["root"] of
      T.Right actual -> check "actual PreparedGroup full key" (key (Q.prepareSourceContractEncodings base) base actual==old base actual)
      T.Left err -> fail ("prepareGroup provenance: "++B.unpack err)
    _ -> fail "prepareSourcePlan provenance"
  total<-readIORef n
  unless (total>2500) (fail "non-vacuous contract controls")
  putStrLn ("PASS contract encoding reuse: "++show total++" checks")
