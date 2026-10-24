{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import qualified Bootstrap.Types as T
import qualified Bootstrap.Module as M
import qualified Bootstrap.CrateArtifact as A
import qualified Package.Release as R
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B
expect result=case result of T.Left message->error(B.unpack message);T.Right value->pure value
check label value=if value then putStrLn("PASS "++label) else error label
main=do
 let entity=M.Entity "Main" "protected" M.Value
     plain=M.Entity "Main" "plain" M.Value
     name=A.definitionName "release-fixture" entity
     other=A.definitionName "release-fixture" plain
     iface=A.CrateInterface "release-fixture" [("dependency","/old/unit.mlfci","semantic")]
       ["Main"] [("Main",[entity,plain,M.Entity "FacadeSource" "forwarded" M.Value])]
       [("Main",["Main","FacadeSource"])] [] [] [] []
       [(name,T.XCon "Int" []),(other,T.XCon "Int" [])] "" "body-hash"
       [(name,True),(other,False)]
 _<-expect(A.validateInterface iface)
 relocated<-expect(R.relocateInterface [("dependency","/new/unit.mlfci")] iface)
 check "relocation preserves complete true/false protection" (A.crateProtection relocated==A.crateProtection iface)
 check "relocation changes only dependency path" (A.crateDependencies relocated==[("dependency","/new/unit.mlfci","semantic")])
 check "relocation leaves semantic identity unchanged" (P.eqString(A.semanticFingerprint iface)(A.semanticFingerprint relocated))
 decoded<-expect(A.decodeInterface(A.encodeInterface relocated))
 check "MLFCI5 roundtrip preserves protection" (A.crateProtection decoded==A.sortPairs (A.crateProtection iface))
 check "MLFCI5 roundtrip preserves exact bytes" (P.eqString(A.encodeInterface decoded)(A.encodeInterface relocated))
 check "missing release dependency still fails closed" (case R.relocateInterface [] iface of T.Left message->P.eqString message "release dependency is missing: dependency";_->False)
