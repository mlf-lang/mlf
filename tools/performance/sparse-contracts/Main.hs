{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Exception (SomeException, evaluate, try, displayException)
import Control.Monad (forM_, unless, foldM)
import Data.IORef
import qualified Bootstrap.CrateQuery as Q
import qualified FrozenCrateQuery as FQ
import qualified Bootstrap.SourceInference as S
import qualified FrozenSourceInference as FS
import qualified Bootstrap.InferenceUnit as I
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Set as Set
import qualified Bootstrap.Fresh as Fresh
import qualified Bootstrap.Classes as C
import qualified FrozenClasses as FC
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B

mapOf = M.fromList P.compareString
contract ty classes flag = S.SourceContract ty classes flag
frozen (S.SourceContract ty classes flag) = FS.SourceContract ty classes flag
oldContracts env = M.map frozen env
oldPrepared (FS.PreparedGroup original members bindings registry specs authority flags) =
  S.PreparedGroup original members bindings registry specs (case authority of
    T.Nothing -> T.Nothing
    T.Just (FS.RootAuthority name labels flag candidates protected) ->
      T.Just (S.RootAuthority name labels flag candidates protected)) flags
observe text = do
  value <- try (evaluate (length (B.unpack text))) :: IO (Either SomeException Int)
  pure $ case value of Left e -> Left (displayException e); Right _ -> Right (B.unpack text)
expect label result = case result of
  T.Left err -> fail (label++": "++B.unpack err)
  T.Right x -> pure x
plan result = do
  result' <- expect "source plan" result
  case result' of T.Nothing -> fail "source plan unsupported"; T.Just x -> pure x
members body = [("root",T.Nothing,body)]
int = T.XCon "Int" []
boolean = T.XCon "Bool" []

main = do
  n<-newIORef (0::Int)
  let check label ok = unless ok (fail label) >> modifyIORef' n (+1)
      env=mapOf [("z",contract int ["Eq"] False),("a",contract boolean ["Show","Eq"] True),
                 ("α😀\NULx",contract int [] False),("unused",contract int [] True)]
      envOld=oldContracts env
      bodies=[T.SIntLit 4,T.SVar "missing",T.SVar "z",T.SApp (T.SVar "z") (T.SVar "a"),
              T.SApp (T.SVar "a") (T.SVar "a"),T.SVar "α😀\NULx",
              T.SLam "a" T.Nothing (T.SVar "a")]
      enc=Q.list Q.encodeBinding
  forM_ [0,1,8,32,128] $ \size -> do
    let extra=mapOf [(B.literal ("key"++show k),contract int [] False) | k<-[1..size]]
        varied=M.union P.compareString env extra
        variedOld=oldContracts varied
    forM_ bodies $ \body -> do
      let actual=S.selectedContractBindings (members body) varied
          expected=FS.selectedBindings (members body) (FS.contractTypes variedOld)
      check "selected bindings sorted, duplicate, missing and bound names" (enc actual==enc expected)
  let ordered=S.selectedContractBindings (members (T.SApp (T.SVar "z") (T.SVar "a"))) env
  check "selected bindings exact ordinal order" (enc ordered==enc [("a",boolean),("z",int)])
  check "empty selected list" (null (S.selectedContractBindings (members (T.SVar "missing")) env))
  -- Unused values remain unforced in direct selection and complete owned keys.
  let bad=errorWithoutStackTrace "unused bottom"
      lazyEnv=mapOf [("a",contract boolean [] False),("unused",bad)]
      direct=S.selectedContractBindings (members (T.SVar "a")) lazyEnv
      synthetic=S.PreparedGroup (members (T.SVar "a")) (members (T.SVar "a")) [("a",boolean)]
        M.empty [("root",[],False)] T.Nothing [("a",False)]
      context=FQ.encodeDatatypeContext []
      fullPool=Q.prepareSourceContractEncodings lazyEnv
      missingPool=Q.prepareSourceContractEncodings M.empty
      expectedKey=FQ.sourceQueryKeyWithContext "crate" "compiler" synthetic lazyEnv context
  check "unused bottom direct selection" (enc direct==enc [("a",boolean)])
  check "unused bottom owned full key" (Q.sourceQueryKeyWithContractEncodings fullPool "crate" "compiler" synthetic lazyEnv context==expectedKey)
  check "missing cache falls back for full key" (Q.sourceQueryKeyWithContractEncodings missingPool "crate" "compiler" synthetic lazyEnv context==expectedKey)
  -- Compare both successful preparations and legitimate failures against the complete old source.
  successes<-newIORef (0::Int)
  forM_ [env,mapOf [("z",contract int [] False),("a",contract boolean [] True),
                   ("α😀\NULx",contract int [] False)]] $ \current -> do
    forM_ bodies $ \body -> do
      let scopes=mapOf [("root",IS.empty)]
      newPlan<-plan (S.prepareSourcePlan M.empty [] [] [] scopes [] (members body))
      oldPlan<-plan (FS.prepareSourcePlan M.empty [] [] [] scopes [] (members body))
      case (S.prepareGroupSparse newPlan current ["root"], FS.prepareGroup oldPlan (oldContracts current) ["root"]) of
        (T.Left a,T.Left b) -> check "matching prepareGroup failure" (a==b)
        (T.Right new,T.Right old) -> do
          modifyIORef' successes (+1)
          let previous=oldPrepared old
              pool=Q.prepareSourceContractEncodings current
              a=Q.sourceQueryKeyWithContractEncodings pool "crate" "compiler" new current context
              b=FQ.sourceQueryKeyWithContext "crate" "compiler" previous current context
          check "actual prepared group full exact key" (a==b)
          check "actual prepared group exact selected bindings" (enc (S.groupBindings new)==enc (FS.groupBindings old))
        _ -> fail "new and frozen prepareGroup disagree on success"
  successful<-readIORef successes
  check "several real prepared successes" (successful>=3)
  -- Model the driver's successful-finalization updates: both maps receive the
  -- same left-biased delta, including replacement under an existing name.
  let trace=[mapOf [("a",contract int [] False)],
             mapOf [("b",contract boolean ["Eq"] True)],
             mapOf [("a",contract boolean ["Show","Eq"] True)],
             mapOf [("a",contract int [] False),("b",contract int [] False)]]
      traceMembers=members (T.SApp (T.SVar "b") (T.SVar "a"))
  _<-foldM (\(current,cache) delta -> do
    let next=M.union P.compareString delta current
        nextCache=Q.extendSourceContractEncodings delta cache
        selected=S.selectedContractBindings traceMembers next
        oldSelected=FS.selectedBindings traceMembers (FS.contractTypes (oldContracts next))
        group=S.PreparedGroup traceMembers traceMembers selected M.empty [("root",[],False)]
          T.Nothing (S.parameterProtection next selected)
        actual=Q.sourceQueryKeyWithContractEncodings nextCache "crate" "compiler" group next context
        reference=FQ.sourceQueryKeyWithContext "crate" "compiler" group next context
    check "synchronized contract delta exact key" (actual==reference)
    check "synchronized contract delta selected bindings" (enc selected==enc oldSelected)
    pure (next,nextCache)) (M.empty,Q.prepareSourceContractEncodings M.empty) trace
  -- Real successful compiler/finalizer result agrees with the frozen source owner.
  let scope=mapOf [("root",IS.empty)]; literal=members (T.SIntLit 4)
  np<-plan (S.prepareSourcePlan M.empty [] [] [] scope [] literal)
  op<-plan (FS.prepareSourcePlan M.empty [] [] [] scope [] literal)
  ng<-expect "new finalized group" (S.prepareGroupSparse np M.empty ["root"])
  og<-expect "old finalized group" (FS.prepareGroup op M.empty ["root"])
  -- Preserve the malformed module fixture as a rejection, not a success oracle.
  invalid<-expect "compile invalid identity fixture" (I.compileLoweredGroup "root" [] [] (S.groupMembers ng))
  case S.finishGroup ng invalid of
    T.Left err -> check "invalid module identity rejected"
      (B.unpack err == "<module identity>:1:1: unexpected root; expected constructor name")
    T.Right _ -> fail "invalid module identity accepted"
  obj<-expect "compile group" (I.compileLoweredGroup "SparseContractControl" [] [] (S.groupMembers ng))
  nf<-expect "new finish" (S.finishGroup ng obj)
  ofn<-expect "frozen finish" (FS.finishGroup og obj)
  let oldFinal=M.map (\(FS.SourceContract ty cs p)->S.SourceContract ty cs p) (FS.finalGroupContracts ofn)
  check "finalized exact contract bytes" (Q.list Q.encodeSourceContract (M.toList (S.finalGroupContracts nf))==
    FQ.list FQ.encodeSourceContract (M.toList oldFinal))
  check "one successful finalized contract" (length (M.toList oldFinal)==1)
  -- Public interfaces keep structural partial-value order.
  let bad1=errorWithoutStackTrace "crate first"; bad2=errorWithoutStackTrace "compiler second"
      group=S.PreparedGroup literal literal [] M.empty [("root",[],False)] T.Nothing []
  a<-observe (Q.sourceQueryKeyWithContext bad1 bad2 group M.empty "context")
  b<-observe (FQ.sourceQueryKeyWithContext bad1 bad2 group M.empty "context")
  check "public first error unchanged" (a==b)
  let partial=mapOf [("a",contract (errorWithoutStackTrace "type first") [] False),
                     ("z",errorWithoutStackTrace "other contract")]
      publicGroup=S.PreparedGroup (members (T.SVar "a")) (members (T.SVar "a"))
        [("a",errorWithoutStackTrace "binding first")] M.empty [] T.Nothing []
  pa<-observe (Q.sourceQueryKeyWithContext "crate" "compiler" publicGroup partial "context")
  pb<-observe (FQ.sourceQueryKeyWithContext "crate" "compiler" publicGroup partial "context")
  check "public partial map demand unchanged" (pa==pb)
  -- Retained public makePrepared observes partial input in the old order.
  let partialEnv=mapOf [("a",contract (errorWithoutStackTrace "selected type first") [] False),
                        ("unused",errorWithoutStackTrace "unused contract later")]
      oldPartial=oldContracts partialEnv
      makeNew=S.makePrepared (members (T.SVar "a")) (members (T.SVar "a")) M.empty [] T.Nothing partialEnv
      makeOld=FS.makePrepared (members (T.SVar "a")) (members (T.SVar "a")) M.empty [] T.Nothing oldPartial
  ma<-observe (Q.list Q.encodeBinding (S.groupBindings makeNew))
  mb<-observe (FQ.list FQ.encodeBinding (FS.groupBindings makeOld))
  check "public makePrepared partial value demand unchanged" (ma==mb)
  -- Independent complete baseline versus the file-owned view/index path.
  -- The inputs deliberately have source order different from lexical and SCC
  -- request order. Every expected-success case is required to succeed.
  let orderedSources=[("zeta",T.Just (T.SAnnotation [] (T.SCon "Int" [])),T.SIntLit 1),
                      ("alpha",T.Just (T.SAnnotation [] (T.SCon "Int" [])),T.SIntLit 2),
                      ("plain",T.Nothing,T.SVar "value"),
                      ("recZ",T.Nothing,T.SVar "recA"),
                      ("recA",T.Nothing,T.SVar "recZ")]
      orderedScopes=mapOf [(name,IS.empty) | (name,_,_)<-orderedSources]
      classDecls=[T.SClassDecl "C" [("a",T.Star)] [] [("method",T.STVar "a")]]
      comparePrepared label current new old = do
        let previous=oldPrepared old
            textMembers=Q.list Q.encodeMember
        check (label++" original exact order")
          (textMembers (S.groupOriginal new)==textMembers (S.groupOriginal previous))
        check (label++" lowered members exact order")
          (textMembers (S.groupMembers new)==textMembers (S.groupMembers previous))
        check (label++" complete prepared key")
          (Q.sourceQueryKeyWithContext "crate" "compiler" new current context==
           FQ.sourceQueryKeyWithContext "crate" "compiler" previous current context)
      compareOwned label expectSuccess owned newPlan oldPlan current names =
        case (S.prepareGroupOwned owned newPlan current names,
              FS.prepareGroup oldPlan (oldContracts current) names) of
          (T.Right new,T.Right old) -> do
            unless expectSuccess (fail (label++": unexpectedly succeeded"))
            comparePrepared label current new old
          (T.Left a,T.Left b) -> do
            whenExpected expectSuccess label
            check (label++" exact error") (a==b)
          _ -> fail (label++": owned and frozen results disagree")
      whenExpected wanted label = if wanted then fail (label++": expected success") else pure ()
      compareViews label current (S.OwnedSourceContext _ _ overloads protection _) = do
        let reference=oldContracts current
        check (label++" complete overload view")
          (M.toList overloads==M.toList (FS.contractOverloads reference))
        check (label++" complete protection view")
          (M.toList protection==M.toList (M.map FS.contractProtected reference))
      mkNew sources scopes classes = do
        p<-plan (S.prepareSourcePlan M.empty [] classes [] scopes [] sources)
        expect "new protection" (S.initializeProtection p M.empty)
      mkOld sources scopes classes = do
        p<-plan (FS.prepareSourcePlan M.empty [] classes [] scopes [] sources)
        expect "frozen protection" (FS.initializeProtection p M.empty)
  indexedPlan<-mkNew orderedSources orderedScopes []
  indexedOld<-mkOld orderedSources orderedScopes []
  let initial=mapOf [("value",contract int [] False)]
      indexedOwned=S.prepareOwnedSourceContext indexedPlan initial
  compareViews "initial" initial indexedOwned
  compareOwned "annotated source order" True indexedOwned indexedPlan indexedOld initial ["alpha","zeta"]
  case S.prepareGroupOwned indexedOwned indexedPlan initial ["alpha","zeta"] of
    T.Right g -> check "source order is declaration order, not request or key order"
      (map (\(name,_,_)->name) (S.groupOriginal g)==["zeta","alpha"])
    T.Left _ -> fail "ordered source group"
  compareOwned "unsigned source" True indexedOwned indexedPlan indexedOld initial ["plain"]
  compareOwned "recursive source" True indexedOwned indexedPlan indexedOld initial ["recA","recZ"]
  compareOwned "missing name" False indexedOwned indexedPlan indexedOld initial ["missing"]
  compareOwned "duplicate name" False indexedOwned indexedPlan indexedOld initial ["zeta","zeta"]
  compareOwned "self predecessor" False indexedOwned indexedPlan indexedOld
    (M.union P.compareString (mapOf [("zeta",contract int [] False)]) initial) ["zeta"]
  -- Real class-generated support plus a source group, with initialized
  -- protection, tests both the indexed support path and mixed-group rejection.
  let supportSource=members (T.SIntLit 4); supportScopes=mapOf [("root",IS.empty)]
  supportPlan<-mkNew supportSource supportScopes classDecls
  supportOld<-mkOld supportSource supportScopes classDecls
  let supportNames=map (\(name,_,_)->name) (S.planSupports supportPlan)
      supportOwned=S.prepareOwnedSourceContext supportPlan M.empty
  check "class generates support declarations" (not (null supportNames))
  forM_ supportNames $ \name ->
    compareOwned "generated support" True supportOwned supportPlan supportOld M.empty [name]
  compareOwned "mixed support/source" False supportOwned supportPlan supportOld M.empty [head supportNames,"root"]
  -- Views follow the exact left-biased contract delta, including replacement.
  -- The unsigned preparation actually references the changed contract.
  let changes=[mapOf [("value",contract boolean [] True)],
               mapOf [("other",contract int ["C"] True)],
               mapOf [("value",contract int [] False),("other",contract boolean [] False)],
               M.empty]
  _<-foldM (\(current,owned) delta -> do
    let next=M.union P.compareString delta current
        nextOwned=S.extendOwnedSourceContext delta owned
    compareViews "delta" next nextOwned
    compareOwned "owned delta unsigned" True nextOwned indexedPlan indexedOld next ["plain"]
    compareOwned "owned delta annotated" True nextOwned indexedPlan indexedOld next ["alpha","zeta"]
    pure (next,nextOwned)) (initial,indexedOwned) changes
  -- Unused bottom must stay unused by an owned preparation just as it does in
  -- the frozen traversal. Compare forced serialized group/key outcomes.
  let bottomEnv=mapOf [("value",contract int [] False),("unused",errorWithoutStackTrace "owned unused bottom")]
      bottomOwned=S.prepareOwnedSourceContext indexedPlan bottomEnv
  compareOwned "owned unused bottom" True bottomOwned indexedPlan indexedOld bottomEnv ["plain"]
  -- Exercise the reservation optimization against the complete independently
  -- frozen Classes implementation, including the final Fresh counter and set.
  let setOf = Set.fromList P.compareString
      setList = Set.toList
      methodEnv=mapOf [("shadow",("oldTarget",[])),("left",("sharedTarget",[])),
                       ("right",("sharedTarget",[]))]
      overloadEnv=mapOf [("shadow",("shadow",[])),("wantedDictionary0",("wantedDictionary0",[]))]
      environment=M.union P.compareString overloadEnv methodEnv
      reservedKeys=setOf (M.keys overloadEnv)
      suffix=["candidateCollision","wantedDictionary1"]
      originalNames=M.keys environment ++ map fst (M.elems environment) ++ suffix
      ownedNames=C.sourceOwnedEnvironmentNames overloadEnv methodEnv environment suffix
      oldSet=setOf originalNames
      ownedSet=foldr (Set.insert P.compareString) reservedKeys ownedNames
  check "reservation set equals full environment, targets and candidates" (setList oldSet==setList ownedSet)
  check "shadowed method target excluded" (not (Set.member P.compareString "oldTarget" ownedSet))
  check "shared target retained after another target shadowed" (Set.member P.compareString "sharedTarget" ownedSet)
  check "unused imported collision reserved" (Set.member P.compareString "wantedDictionary0" ownedSet)
  check "candidate collision reserved" (Set.member P.compareString "candidateCollision" ownedSet)
  let shadowBottom=mapOf [("shadow",(errorWithoutStackTrace "shadowed target",[]))]
      shadowEnvironment=M.union P.compareString overloadEnv shadowBottom
      oldShadowSet=setOf (M.keys shadowEnvironment ++ map fst (M.elems shadowEnvironment))
      newShadowSet=foldr (Set.insert P.compareString) reservedKeys
        (C.sourceOwnedEnvironmentNames overloadEnv shadowBottom shadowEnvironment [])
  check "shadowed unused bottom remains unforced" (setList oldShadowSet==setList newShadowSet)
  let encodeRoot (C.SourceRootLowering body labels candidates protected) =
        (Q.encodeExpression body,labels,Q.list Q.encodeCandidate candidates,protected)
      encodeOldRoot (FC.SourceRootLowering body labels candidates protected) =
        (Q.encodeExpression body,labels,Q.list Q.encodeCandidate candidates,protected)
      compareRootFresh label newInventory oldInventory overloads protection body initialCount initialUsed = do
        let ownedUsed=foldr (Set.insert P.compareString) initialUsed (M.keys overloads)
            actual=Fresh.runFreshState
              (C.lowerUnsignedSourceRootProtectedOwned newInventory overloads protection "root" body)
              initialCount ownedUsed
            expected=Fresh.runFreshState
              (FC.lowerUnsignedSourceRootProtected oldInventory overloads protection "root" body)
              initialCount initialUsed
        case (actual,expected) of
          (T.Right (a,ac,au),T.Right (b,bc,bu)) -> do
            check (label++" full root result") (encodeRoot a==encodeOldRoot b)
            check (label++" next fresh counter") (ac==bc)
            check (label++" complete used set") (setList au==setList bu)
            pure ac
          (T.Left a,T.Left b) -> fail (label++": expected success, both failed: "++B.unpack a++" / "++B.unpack b)
          _ -> fail (label++": fresh root disagrees")
      compareGroupFresh label newInventory oldInventory overloads protection group initialCount initialUsed = do
        let ownedUsed=foldr (Set.insert P.compareString) initialUsed (M.keys overloads)
            actual=Fresh.runFreshState
              (C.lowerSourceGroupUnchangedOwned newInventory overloads protection group) initialCount ownedUsed
            expected=Fresh.runFreshState
              (FC.lowerSourceGroupUnchanged oldInventory overloads protection group) initialCount initialUsed
        case (actual,expected) of
          (T.Right ((a,as),ac,au),T.Right ((b,bs),bc,bu)) -> do
            check (label++" group body and contracts") (Q.encodeExpression a==Q.encodeExpression b && as==bs)
            check (label++" next fresh counter") (ac==bc)
            check (label++" complete used set") (setList au==setList bu)
          (T.Left a,T.Left b) -> fail (label++": expected success, both failed: "++B.unpack a++" / "++B.unpack b)
          _ -> fail (label++": fresh group disagrees")
      collisions=setOf ["wantedDictionary1","candidateCollision"]
      protection=mapOf [("wantedDictionary0",True)]
  generatedCount<-compareRootFresh "fresh unsigned collision" (S.planInventory supportPlan) (FS.planInventory supportOld)
       overloadEnv protection (T.SVar "method") 0 collisions
  check "collision fixture allocates fresh names" (generatedCount>0)
  let candidateScopes=mapOf [("root",[(T.InstanceEvidence,"candidateCollision")])]
      newCandidateInventory=case S.planInventory supportPlan of
        C.ClassInventory ds denv infos _ candidates methods supports names externals ->
          C.ClassInventory ds denv infos candidateScopes candidates methods supports names externals
      oldCandidateInventory=case FS.planInventory supportOld of
        FC.ClassInventory ds denv infos _ candidates methods supports names externals ->
          FC.ClassInventory ds denv infos candidateScopes candidates methods supports names externals
  _<-compareRootFresh "fresh body and candidate collision" newCandidateInventory oldCandidateInventory
       overloadEnv protection (T.SLam "candidateCollision" T.Nothing (T.SVar "candidateCollision")) 0 collisions
  -- Every group starts at the original count and used set, even when another
  -- group previously allocated names. Compare repeated results independently.
  let missingNew=Fresh.runFreshState
        (C.lowerUnsignedSourceRootProtected (S.planInventory supportPlan) overloadEnv protection
          "missingScope" (T.SIntLit 4)) 0 collisions
      missingOld=Fresh.runFreshState
        (FC.lowerUnsignedSourceRootProtected (FS.planInventory supportOld) overloadEnv protection
          "missingScope" (T.SIntLit 4)) 0 collisions
  case (missingNew,missingOld) of
    (T.Left a,T.Left b) -> check "public missing scope first error unchanged" (a==b)
    _ -> fail "public missing scope should fail in both implementations"
  _<-compareRootFresh "fresh unsigned reset" (S.planInventory supportPlan) (FS.planInventory supportOld)
       overloadEnv protection (T.SVar "method") 0 collisions
  compareGroupFresh "fresh annotated" (S.planInventory indexedPlan) (FS.planInventory indexedOld)
       overloadEnv protection (take 2 orderedSources) 7 collisions
  compareGroupFresh "fresh recursive" (S.planInventory indexedPlan) (FS.planInventory indexedOld)
       overloadEnv protection (drop 3 orderedSources) 7 collisions
  -- Cached used is independently reconstructed from the original plan used
  -- and the current contract keys. Replacement and empty deltas add no names.
  let S.SourcePlan _ _ _ _ _ baseUsed _ _ _ _ = indexedPlan
      expectedUsed current=foldr (Set.insert P.compareString) baseUsed (M.keys current)
      checkUsed current owned=check "cached reservation exact current domain"
        (setList (S.ownedSourceUsed owned)==setList (expectedUsed current))
  checkUsed initial indexedOwned
  _<-foldM (\(current,owned) delta -> do
    let next=M.union P.compareString delta current
        nextOwned=S.extendOwnedSourceContext delta owned
    checkUsed next nextOwned
    pure (next,nextOwned)) (initial,indexedOwned) changes
  count<-readIORef n
  unless (count>=50) (fail "complete sparse control matrix")
  putStrLn ("PASS sparse contract selection: "++show count++" checks")
  putStrLn ("owned successes: annotated=5 unsigned=6 recursive=1 support="++show (length supportNames)++"; expected errors=4")
