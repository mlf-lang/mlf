{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import qualified Bootstrap.Classes as C
import qualified Bootstrap.Module as Mod
import qualified Bootstrap.Separate as Sep
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as Set
import qualified Bootstrap.Fresh as F
import qualified Bootstrap.Surface as Surface
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B
expect x=case x of T.Left e->error(B.unpack e);T.Right y->pure y
check n b=if b then putStrLn("PASS "++n) else error n
main=do
 resolution<-expect(Mod.resolveCrate T.NoImplicitPrelude M.empty Sep.stableName [Mod.preludeSource,Mod.primitiveSource])
 let modules=Mod.resolvedCrateModules resolution
     values=concatMap (Mod.renamedValues.Mod.resolvedContents) modules
     classes=concatMap (Mod.renamedClasses.Mod.resolvedContents) modules
     ds=concatMap (Mod.renamedDatatypes.Mod.resolvedContents) modules
 instances<-mapM (\(n,(_,i))->do c<-expect(Sep.closeInstance values i);pure(B.literal("instance"++show n),c)) (zip [0::Int ..] (Mod.resolvedCrateInstances resolution))
 let extra=[("direct",T.Nothing,T.SVar "$MLF.Stack.callStack"),("transitive",T.Nothing,T.SVar "direct"),("shadow",T.Nothing,T.SLam "direct" T.Nothing(T.SVar "direct")),("plain",T.Nothing,T.SIntLit 42),("id",T.Nothing,T.SLam "x" T.Nothing(T.SVar "x")),("fst",T.Nothing,T.SLam "p" T.Nothing(T.SCase(T.SVar "p")[T.SAlternative(T.SConstructorPattern "(,)" [T.Just "x",T.Just "y"])(T.SVar "x")])),("snd",T.Nothing,T.SLam "p" T.Nothing(T.SCase(T.SVar "p")[T.SAlternative(T.SConstructorPattern "(,)" [T.Just "x",T.Just "y"])(T.SVar "y")]))]
     allValues=values++extra
 body<-expect(Surface.bindValues allValues(T.SConstructor "()"))
 let config=T.Just(M.empty,map fst instances)
 flags<-expect(C.withValidatedClasses config Set.empty M.empty T.Nothing ds classes(map snd instances) body (\base decls->do
   inv<-C.prepareClassesBody config Set.empty M.empty T.Nothing ds (map snd instances) base decls
   F.freshLift(C.inventorySourceProtection inv instances allValues)))
 let flag name=case M.lookup P.compareString name flags of T.Nothing->error("missing "++B.unpack name);T.Just b->b
     name n=Sep.stableName(Mod.Entity "MLF.Primitive" n Mod.Value)
 mapM_ (\n->check(B.unpack n++" ordinary builtin") (not(flag(name n)))) ["otherwise","negate"]
 check "callStack protected" (flag "mlfCallStack")
 mapM_ (\n->check(B.unpack n++" protected") (flag n)) ["direct","transitive"]
 mapM_ (\n->check(B.unpack n++" ordinary") (not(flag n))) ["shadow","plain","id","fst","snd"]
 let method n cls=Sep.stableName(Mod.Entity "MLF.Primitive" n(Mod.Method cls))
 check "Eq selector ordinary" (not(flag(B.literal ("select_" ++ B.unpack(method "==" "Eq")))))
 check "IsString selector ordinary" (not(flag(B.literal ("select_" ++ B.unpack(method "fromString" "IsString")))))
 check "fail selector protected" (flag(B.literal ("select_" ++ B.unpack(method "fail" "MonadFail"))))
 let classId n=Sep.stableName(Mod.Entity "MLF.Primitive" n Mod.Class)
     ordinaryInstances=[n | (n,i)<-instances, any (P.eqString(C.instanceClass i).classId) ["Eq","IsString"]]
 check "ordinary Eq and IsString instances stay unprotected" (not(null ordinaryInstances) && all (not.flag) ordinaryInstances)
 check "ioError protected" (flag(name "ioError"))
 bad<-expect(C.withValidatedClasses config Set.empty M.empty T.Nothing ds classes(map snd instances) body (\base decls->do
   inv<-C.prepareClassesBody config Set.empty M.empty T.Nothing ds (map snd instances) base decls
   let externalInv=case inv of C.ClassInventory a b c d e f g h _->C.ClassInventory a b c d e f g h (M.fromList P.compareString [("foreign",T.SCon "Int" [])])
   pure(case C.inventorySourceProtection externalInv instances allValues of T.Left msg->P.eqString msg "builtin protection analysis requires a closed inventory";_->False)))
 check "external inventory rejected rather than losing protection" bad
 general<-expect(C.withValidatedClasses config Set.empty M.empty T.Nothing ds classes(map snd instances) body (\base decls->do
   inv<-C.prepareClassesBody config Set.empty M.empty T.Nothing ds (map snd instances) base decls
   let externalInv=case inv of C.ClassInventory a b c d e f g h _->C.ClassInventory a b c d e f g h (M.fromList P.compareString [("foreign",T.SCon "Int" [])])
       withUse=allValues++[("usesForeign",T.Nothing,T.SVar "foreign")]
       get ps=case C.inventoryProtection externalInv (M.fromList P.compareString ps) instances withUse of T.Left e->error(B.unpack e);T.Right flags'->case M.lookup P.compareString "usesForeign" flags' of T.Just v->v;_->error "missing usesForeign"
       missing=case C.inventoryProtection externalInv M.empty instances withUse of T.Left e->P.eqString e "imported source protection inventory is incomplete";_->False
   pure(get [("foreign",True)],get [("foreign",False)],missing)))
 check "plain-Int imported protected flag propagates" (case general of (a,_,_)->a)
 check "plain-Int ordinary import remains unprotected" (case general of (_,b,_)->not b)
 check "missing imported protection fails closed" (case general of (_,_,c)->c)
 print(length(M.toList flags))
