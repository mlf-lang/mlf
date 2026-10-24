{-# LANGUAGE OverloadedStrings #-}
module SourceMetadataReview (runMetadataReview) where
import Prelude
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.SourceInference as SI
import qualified Bootstrap.Separate as U
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.IntSet as I
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B

m = M.fromList P.compareString
int = T.XCon "Int" []
entity = Modules.Entity "ReviewA" "f" Modules.Value
name = A.definitionName "review-a" entity
private = A.definitionName "review-a" (Modules.Entity "ReviewA" "private" Modules.Value)
iface flag privateFlag = A.CrateInterface "review-a" [] ["ReviewA"] [("ReviewA",[entity])] [("ReviewA",[])] [] [] [] [] [(name,int),(private,int)] "" "body" [(name,flag),(private,privateFlag)]
withProtection protection (A.CrateInterface a b c d e f g h i j k l _) = A.CrateInterface a b c d e f g h i j k l protection
facade dep = A.CrateInterface "review-facade" [("review-a","/tmp/review-a.mlfci",A.semanticFingerprint dep)] ["ReviewFacade"] [("ReviewFacade",[entity])] [("ReviewFacade",["ReviewA"])] [] [] [] [] [] "" "facade-body" []
check label p = if p then putStrLn ("PASS METADATA REVIEW "++label) else error label
reject label x = check label (case x of T.Left _ -> True; T.Right _ -> False)
right label x = case x of T.Left e -> error(label++": "++B.unpack e); T.Right v -> v
replaceTag tag encoded = let fields=right "metadata fields" (U.unpack encoded); prefix=tag:tail(init fields) in U.pack (prefix++[U.fingerprint(U.pack prefix)])

runMetadataReview = do
 let plain=iface False False; guarded=iface True False
 check "MLFCI5 roundtrip retains complete protection" (case A.decodeInterface(A.encodeInterface guarded) of T.Right decoded -> A.crateProtection decoded == A.crateProtection guarded; _ -> False)
 reject "missing binding protection rejects" (A.decodeInterface(A.encodeInterface(withProtection [(name,True)] guarded)))
 reject "duplicate binding protection rejects" (A.decodeInterface(A.encodeInterface(withProtection [(name,True),(private,False),(name,True)] guarded)))
 reject "foreign protection identity rejects" (A.decodeInterface(A.encodeInterface(withProtection [(name,True),("foreign",False)] guarded)))
 reject "stale MLFCI4 epoch rejects despite valid checksum" (A.decodeInterface(replaceTag "MLFCI-4" (A.encodeInterface guarded)))
 check "public plain-Int protection changes semantic ABI" (A.semanticFingerprint plain /= A.semanticFingerprint guarded)
 check "unexported protection does not pollute public ABI" (A.semanticFingerprint plain == A.semanticFingerprint(iface False True))
 let oldFacade=facade plain; newFacade=facade guarded
 check "plain-type reexport semantic tracks upstream protection" (A.semanticFingerprint oldFacade /= A.semanticFingerprint newFacade)
 reject "old facade rejects changed upstream protection" (A.validateDependencies (m[("review-a",guarded)]) oldFacade)
 let external=m[(name,T.SCon "Int" [])]
     scopes=m[("localWrapper",I.empty)]
     prepared=right "source plan" (SI.prepareSourcePlan external [] [] [] scopes [] [("localWrapper",T.Nothing,T.SVar name)])
     plan=case prepared of T.Just p -> p; _ -> error "unexpected source-plan fallback"
     -- Simulate metadata-only load through a facade: the original owner supplies
     -- the typed binding/protection; the facade supplies no implementation body.
     contracts=right "import contracts" (SI.initialContracts plan (m[(name,int)]) (m(A.crateProtection guarded)))
     group=right "prepared wrapper" (SI.prepareGroup plan contracts ["localWrapper"])
 check "plain Int imported through facade protects local wrapper" (SI.groupContracts group == [("localWrapper",[],True)])
