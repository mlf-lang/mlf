{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad(foldM,unless)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as Std
import qualified Bootstrap.Classes as C
import qualified Bootstrap.Fresh as F
import qualified Bootstrap.Map as M
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Set as Set
import qualified Bootstrap.Dependency as Dependency
import qualified Bootstrap.InferenceUnit as I
import qualified Bootstrap.SourceInference as SI
import qualified Bootstrap.Separate as U
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.X.Type as XT
import qualified Bootstrap.Runtime as R
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as Prim
import System.IO
import System.Environment(getArgs)
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.SourceEquality as E
import qualified Bootstrap.Data as D
import qualified Bootstrap.X.Pretty as Pretty
import SourceMetadataReview(runMetadataReview)
import RawProtectionReview(runRawProtectionReview)
expect label x=case x of T.Left e->error(label++": "++B.unpack e);T.Right y->pure y
assert label p=unless p(error label)
pass s=putStrLn("PASS "++s)
int=T.SCon "Int" []; bool=T.SCon "Bool" []
cls=T.SClassDecl "Tag" [("a",T.Star)] [] [("tag",T.SArrow(T.STVar "a")int)]
instInt=T.SInstanceDecl [] [] "Tag" [int] [("tag",T.SLam "x" T.Nothing(T.SVar "x"))]
instBool=T.SInstanceDecl [] [] "Tag" [bool] [("tag",T.SLam "x" T.Nothing(T.SIntLit 42))]
add x y=T.SApp(T.SApp(T.SPrimitive T.PAddInt)x)y
tag=T.SApp(T.SVar "tag")
app n x=T.SApp(T.SVar n)x
-- This local type is a declaration interface: it deliberately closes one Tag Int
-- use before root compaction, retaining the same raw/final dependency context.
-- Expression SAnn remains a coercion and does not supply that declaration intent.
roots=[("sameDeps",T.SLet "known" (T.SSignature(tag(T.SIntLit 2))(T.SAnnotation [] int))(add(tag(T.SIntLit 1))(T.SVar "known")),Just 3,0),("f0",tag(T.SIntLit 21),Just 21,0),("f1",add(T.SVar "f0")(T.SVar "f0"),Just 42,0),("f2",add(T.SVar "f1")(T.SVar "f1"),Just 84,0),("mixed",add(tag(T.SIntLit 19))(tag(T.SBoolLit True)),Just 61,0),("plain",add(T.SIntLit 1)(T.SIntLit 2),Just 3,0),("nonground",T.SLam "x" T.Nothing(tag(T.SVar "x")),Nothing,1),("nongroundUse",add(app "nonground"(T.SIntLit 21))(app "nonground"(T.SBoolLit True)),Just 63,0),("mixedResidual",T.SLam "x" T.Nothing(add(tag(T.SIntLit 21))(tag(T.SVar "x"))),Nothing,2),("mixedResidualUse",app "mixedResidual"(T.SBoolLit True),Just 63,0),("partialScope",add(tag(T.SIntLit 21))(tag(T.SBoolLit True)),Nothing,2),("partialScopeUse",T.SVar "partialScope",Just 63,0),("managedRoot",T.SLet "ignoredStack" (T.SVar "$MLF.Stack.callStack") (tag(T.SIntLit 21)),Nothing,1),("managedUse",T.SVar "managedRoot",Nothing,1),("signedUse",add(T.SVar "signed")(app "recursive"(T.SIntLit 2)),Just 42,0)]
program=T.SClassProgram [] [cls] [instInt,instBool] (foldr(\(n,e,_,_)b->T.SLet n e b)(T.SConstructor "()")roots)
scopes=M.fromList Prim.compareString [(n,IS.fromList(if n=="partialScope"||n=="sameDeps" then [0] else [0,1]))|(n,_,_,_)<-roots]
data Value=Value Prim.String SI.SourceContract T.XTerm
vn(Value n _ _)=n
vc(Value _ c _)=c
vb(Value _ _ b)=b
lookupValue ns n=case filter(\v->vn v==n)ns of [v]->v;_->error("missing checked dependency "++B.unpack n)
strip(T.XWithData _ b)=strip b
strip b=b
replaceTail(T.XLet n a b)term=T.XLet n a(replaceTail b term)
replaceTail(T.XLetRec bs b)term=T.XLetRec bs(replaceTail b term)
replaceTail(T.XConstructor "()" [])term=term
replaceTail _ _=error"not fragment binding spine"
findBinding wanted(T.XLet n rhs rest)
 | X.nameHint n==wanted=(n,rhs)
 | otherwise=findBinding wanted rest
findBinding wanted(T.XLetRec bs rest)=case[(n,rhs)|(n,_,rhs)<-bs,X.nameHint n==wanted]of [v]->v;[]->findBinding wanted rest;_->error"duplicate root"
findBinding _ _=error"root absent"
evaluate term=do
 (env,_)<-expect"runtime prepare"(R.prepare False term)
 v<-expect"runtime"(R.evaluate env(R.REnv M.empty)(X.erase term))
 case v of R.RInteger n->pure n;_->error"not integer"
closed ds values parameters rhs=
 let ids=foldl(\acc(n,t)->U.typeIdentities t(Set.insert Std.compareInt(X.nameId n)acc))(U.termIdentities rhs Set.empty)parameters
     start=1+maximum(0:Set.toList ids)
     step(serial,bindings)(n,_)=let(next,term)=U.freshObject serial(strip(vb(lookupValue values(X.nameHint n))))in(next,bindings++[(n,term)])
     (_,bindings)=foldl step(start,[])parameters
 in T.XWithData ds(foldr(\(n,term)b->T.XLet n term b)rhs bindings)
main=do
 hSetBuffering stdout LineBuffering
 [cache]<-getArgs
 let members=[(n,T.Nothing,e)|(n,e,_,_)<-roots,n/= "signedUse"]
 planMaybe<-expect "source dispatcher plan" (SI.prepareSourcePlan M.empty [] [cls] [("tagInt",instInt),("tagBool",instBool)] scopes [IS.fromList[0,1],IS.fromList[0,1]] members)
 rawPlan<-case planMaybe of T.Just p->pure p;_->error "unexpected whole fallback"
 let plan=case rawPlan of SI.SourcePlan a b c d e f g _ i j -> SI.SourcePlan a b c d e f g (error "POISON old global lowering forced") i j
 (objects,cold,contracts)<-Q.compileSourceGroups "dispatch" (B.literal cache) [] M.empty plan >>= expect "cold source SCC compilation"
 assert "cold inferred all groups" (Q.inferredCount cold==fromIntegral(length(SI.planGroups plan))&&Q.reusedCount cold==0)
 values<-foldM collect [] objects
 mapM_ (\(n,_,wanted,slots)->if n=="signedUse" then pure() else do
   let v=lookupValue values n;c=case M.lookup Prim.compareString n contracts of T.Just x->x;_->error "contract absent"
   assert "source-issued residual contract"(SI.contractClasses c==replicate slots "Tag")
   case wanted of Just expected->evaluate(vb v)>>=assert ("runtime "++B.unpack n).(==expected);Nothing->pure()) roots
 (warmObjects,warm,warmContracts)<-Q.compileSourceGroups "dispatch" (B.literal cache) [] M.empty plan >>= expect "warm source SCC compilation"
 assert "warm reused every raw object"(Q.inferredCount warm==0&&Q.reusedCount warm==fromIntegral(length objects))
 assert "raw hit finalization yields exact final object bytes"(map U.encodeObject objects==map U.encodeObject warmObjects)
 assert "raw hit finalization yields exact ABI classes/protection"(map(\(n,c)->(n,Pretty.prettyType(SI.contractType c),SI.contractClasses c,SI.contractProtected c))(M.toList contracts)==map(\(n,c)->(n,Pretty.prettyType(SI.contractType c),SI.contractClasses c,SI.contractProtected c))(M.toList warmContracts))
 assert "managed direct/transitive flags persist"(all(\n->case M.lookup Prim.compareString n contracts of T.Just c->SI.contractProtected c;_->False)["managedRoot","managedUse"])
 let Q.QueryReport _ _ reports=cold
     [(groupId,digest)]=[(gid,digest)|Q.GroupResult gid names _ _ digest<-reports,names==["sameDeps"]]
     [compact]=[obj|obj<-objects,U.unitName(U.objectInterface obj)==groupId]
     cacheFile=cache++"/"++B.unpack digest++".mlfq"
 rawText<-B.literal <$> readFile cacheFile
 fields<-expect "read raw cached payload"(U.unpack rawText)
 rawIface<-expect "raw cache interface"(U.decodeInterface(fields!!2))
 rawObject<-expect "raw cache object"(U.decodeObject rawIface(fields!!3))
 let rawParameters=map(\(n,t)->(X.nameHint n,t))(fst(U.splitParameters(strip(U.objectTerm rawObject))))
 let exactKey=fields!!1
 _<-expect "counterexample generic validator accepts compact with same dependency context"(Q.decodeCached exactKey groupId rawParameters (U.unitData rawIface) ["sameDeps"] (Q.encodeCached exactKey compact))
 keyFields<-expect "source query framing"(U.unpack exactKey)
 assert "raw cache uses exact new source namespace"(head keyFields=="MLF-SOURCE-CRATE-QUERY-6")
 assert "raw provisional is not compact final object"(Q.encodeCached exactKey compact/=rawText)
 writeFile cacheFile(B.unpack(Q.encodeCached exactKey compact))
 (repairedObjects,repaired,_)<-Q.compileSourceGroups "dispatch" (B.literal cache) [] M.empty plan >>= expect "reject normalized-as-raw cache"
 assert "normalized final payload fails raw cache validation and reinfers"(Q.inferredCount repaired==1&&Q.reusedCount repaired==fromIntegral(length objects-1))
 assert "repaired cold/miss object parity"(map U.encodeObject repairedObjects==map U.encodeObject objects)
 pass "normalized payload cannot masquerade as raw cache"
 supportCycleChecks (cache++"-support-cycle")
 supportProtectionChecks (cache++"-managed-support")
 proofLayoutChecks (cache++"-proof")
 originChecks
 runMetadataReview
 runRawProtectionReview
 pass "production source dispatcher cold/warm terminal"
collect values object=do
 let (ds,term)=case U.objectTerm object of { T.XWithData ds b->(ds,b);b->([],b) }
     (parameters,core)=U.splitParameters term
 new<-mapM (\(name,ty)->do
   let(n,_)=findBinding name core;rhs=replaceTail core(T.XVarTerm n);linked=closed ds values parameters rhs
   checked<-expect "final fragment parameterized linking check"(Checked.check linked)
   pure(Value name(SI.SourceContract ty [] False)(Checked.term checked))) (U.unitBindings(U.objectInterface object))
 pure(values++new)

originChecks=do
 let signed=("signedRoot",T.Just(T.SAnnotation [] int),T.SIntLit 42)
     recursive=("recRoot",T.Just(T.SAnnotation [](T.SArrow int int)),T.SLam "x" T.Nothing(T.SApp(T.SVar "recRoot")(T.SVar "x")))
     own=[signed,recursive]
     ownScopes=M.fromList Prim.compareString[(n,IS.empty)|(n,_,_)<-own]
 pm<-expect "signed recursive plan"(SI.prepareSourcePlan M.empty [] [] [] ownScopes [] own)
 sp<-case pm of T.Just p->pure p;_->error "signed unexpected whole fallback"
 mapM_ (\names->do
   pg<-expect "original signed/recursive fallback"(SI.prepareGroup sp M.empty names)
   assert "signed or recursive cannot claim unsigned authority"(case SI.groupAuthority pg of T.Nothing->True;_->False)) (SI.planGroups sp)
 let copied=T.SCallSite "copy" (T.SourceSpan "pkg" "Mod" "file" 1 1 1 2) (T.SSourceDefinition(T.SIntLit 42))
 cp<-expect "copied source plan"(SI.prepareSourcePlan M.empty [] [] [] (M.fromList Prim.compareString[("copy",IS.empty)]) [] [("copy",T.Nothing,copied)])
 assert "copied marker under source wrapper chooses whole fallback"(case cp of T.Nothing->True;_->False)
 assert "self edge rejects unsigned optimization eligibility"(not(SI.eligibleSource[("self",T.Nothing,T.SVar "self")]))
 pass "original source ownership/signature/recursive/copied routing controls"

proofLayoutChecks cache=do
 let payload=T.DataDecl "Payload" [] [T.ConstructorDecl "Payload" []]
     box=T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a"]]
     c=T.SClassDecl "Prereq" [("a",T.Star)] [] [("payload",T.SArrow(T.STVar "a")(T.SCon "Payload" []))]
     d=T.SClassDecl "Goal" [("a",T.Star)] [] [("goal",T.SArrow(T.STVar "a")int)]
     ci=T.SInstanceDecl [] [] "Prereq" [int] [("payload",T.SLam "x" T.Nothing(T.SConstructor "Payload"))]
     di=T.SInstanceDecl [("a",T.Star)] [T.SPredicate "Prereq" [T.STVar "a"]] "Goal" [T.SCon "Box" [T.STVar "a"]] [("goal",T.SLam "x" T.Nothing(T.SIntLit 42))]
     member=("proofRoot",T.Nothing,T.SApp(T.SVar "goal")(T.SApp(T.SConstructor "Box")(T.SIntLit 1)))
     scope=M.fromList Prim.compareString[("proofRoot",IS.fromList[0,1])]
 pm<-expect "proof-only layout plan"(SI.prepareSourcePlan M.empty [payload,box] [c,d] [("prereqInt",ci),("goalAny",di)] scope [IS.fromList[0,1],IS.fromList[0,1]] [member])
 plan<-case pm of T.Just p->pure p;_->error "proof layout whole fallback"
 (objects,_,contracts)<-Q.compileSourceGroups "proof-layout" (B.literal cache) [] M.empty plan >>=expect "proof-only selected support inference"
 let [root]=[o|o<-objects,"proofRoot" `elem` map fst(U.unitBindings(U.objectInterface o))]
     layouts=map D.datatypeName(U.unitData(U.objectInterface root))
     registry=C.inventoryOrdinaryRegistry(SI.planInventory plan)
     prereqHead=case M.lookup Prim.compareString "Prereq" registry of T.Just n->n;_->error "registry"
 assert "candidate-only prerequisite dictionary layout retained"(prereqHead `elem` layouts)
 assert "transitive proof-only field layout retained"("Payload" `elem` layouts)
 let predecessors=M.filterWithKey (\name _->name/="proofRoot") contracts
 prepared<-expect "proof root prepared key"(SI.prepareGroup plan predecessors ["proofRoot"])
 needed<-expect "proof layout key context"(Q.requiredData(SI.planData plan)(SI.groupMembers prepared)(SI.groupBindings prepared++SI.groupCandidateBindings prepared))
 let mutated=[if D.datatypeName dt=="Payload" then T.DataDecl "Payload" [] [T.ConstructorDecl "Payload" [T.Applied "Int" []]] else dt|dt<-needed]
 assert "proof-only transitive field layout changes raw query key"(Q.sourceQueryKey "proof-layout" "compiler" prepared predecessors needed/=Q.sourceQueryKey "proof-layout" "compiler" prepared predecessors mutated)
 assert "ground root compacted"(case M.lookup Prim.compareString "proofRoot" contracts of T.Just co->null(SI.contractClasses co);_->False)
 values<-foldM collect [] objects
 actual<-evaluate(vb(lookupValue values "proofRoot"))
 assert "proof dependency checked and linked"(actual==42)
 pass "proof-only dependency and transitive layout closure"

supportProtectionChecks cache=do
 let managedInt=T.SInstanceDecl [] [] "Tag" [int] [("tag",T.SLam "x" T.Nothing(T.SLet "ignoredStack" (T.SVar "$MLF.Stack.callStack")(T.SVar "x")))]
     goalClass=T.SClassDecl "Goal" [("a",T.Star)] [] [("goal",T.SArrow(T.STVar "a")int)]
     goalInt=T.SInstanceDecl [] [] "Goal" [int] [("goal",T.SLam "x" T.Nothing(tag(T.SVar "x")))]
     box=T.DataDecl "ManagedBox" ["a"] [T.ConstructorDecl "ManagedBox" [T.Parameter "a"]]
     goalBox=T.SInstanceDecl [("a",T.Star)] [T.SPredicate "Tag" [T.STVar "a"]] "Goal" [T.SCon "ManagedBox" [T.STVar "a"]] [("goal",T.SLam "x" T.Nothing(T.SIntLit 21))]
     members=[("signedSafe",T.Just(T.SAnnotation [] int),tag(T.SBoolLit True)),("signedSafeUse",T.Nothing,add(T.SVar "signedSafe")(tag(T.SBoolLit True))),("nested",T.Nothing,T.SApp(T.SVar "goal")(T.SIntLit 1)),("contextual",T.Nothing,T.SApp(T.SVar "goal")(T.SApp(T.SConstructor "ManagedBox")(T.SIntLit 1))),("guarded",T.Nothing,tag(T.SIntLit 21)),("guardedUse",T.Nothing,T.SVar "guarded"),("safeBool",T.Nothing,tag(T.SBoolLit True)),("rawKnown",T.Nothing,T.SLet "known" (T.SAnn(tag(T.SIntLit 21))(T.SAnnotation [] int))(T.SVar "known")),("sink",T.Just(T.SAnnotation [] int),T.SVar "guarded")]
     scope=M.fromList Prim.compareString[(n,IS.fromList[0,1,2,3])|(n,_,_)<-members]
 pm<-expect "managed instance support plan"(SI.prepareSourcePlan M.empty [box] [cls,goalClass] [("tagInt",managedInt),("tagBool",instBool),("goalInt",goalInt),("goalBox",goalBox)] scope (replicate 4(IS.fromList[0,1,2,3])) members)
 plan<-case pm of T.Just p->pure p;_->error "managed instance fallback"
 (objects,report,contracts)<-Q.compileSourceGroups "managed-support" (B.literal cache) [] M.empty plan >>=expect "managed selected proof protection"
 let get n=case M.lookup Prim.compareString n contracts of T.Just c->c;_->error "missing managed contract"
 assert "managed instance support classified"(SI.contractProtected(get "tagInt"))
 assert "nested concrete support inherits actual lowered selected support protection"(SI.contractProtected(get "goalInt"))
 assert "signed ordinary helper ignores unused protected candidate inventory"(not(SI.contractProtected(get "signedSafe")))
 assert "signed helper successor can contract"(not(SI.contractProtected(get "signedSafeUse"))&&null(SI.contractClasses(get "signedSafeUse")))
 assert "ordinary instance support not tainted"(not(SI.contractProtected(get "tagBool")))
 mapM_ (\n->assert "selected managed proof and transitive successor protected"(SI.contractProtected(get n))) ["guarded","guardedUse","rawKnown","sink","nested","contextual"]
 let predecessors=M.filterWithKey (\name _->name/="guarded") contracts
     plainCandidate=M.insert Prim.compareString "tagInt" (SI.SourceContract(SI.contractType(get "tagInt")) [] False) predecessors
 preparedGuarded<-expect "protected candidate key preparation"(SI.prepareGroup plan predecessors ["guarded"])
 preparedPlain<-expect "plain candidate key preparation"(SI.prepareGroup plan plainCandidate ["guarded"])
 assert "candidate protection-only change invalidates source query key"(Q.sourceQueryKey "managed-support" "compiler" preparedGuarded predecessors (SI.planData plan)/=Q.sourceQueryKey "managed-support" "compiler" preparedPlain plainCandidate (SI.planData plan))
 assert "selected managed proof preserves dictionary ABI"(SI.contractClasses(get "guarded")==["Tag"])
 assert "unrelated managed candidate does not prevent safe proof contraction"(null(SI.contractClasses(get "safeBool"))&&not(SI.contractProtected(get "safeBool")))
 let Q.QueryReport _ _ rows=report
     [(gid,digest)]=[(gid,digest)|Q.GroupResult gid ns _ _ digest<-rows,ns==["guarded"]]
     [final]=[o|o<-objects,U.unitName(U.objectInterface o)==gid]
 cacheText<-B.literal <$> readFile(cache++"/"++B.unpack digest++".mlfq")
 fs<-expect "managed raw cache"(U.unpack cacheText)
 i<-expect "managed raw interface"(U.decodeInterface(fs!!2))
 raw<-expect "managed raw object"(U.decodeObject i(fs!!3))
 assert "selected managed proof veto preserves exact original object"(U.encodeObject raw==U.encodeObject final)
 values<-foldM collect [] objects
 evaluate(vb(lookupValue values "safeBool"))>>=assert "safe proof runtime".(==42)
 evaluate(vb(lookupValue values "sink"))>>=assert "managed proof baseline runtime".(==21)
 (warmObjects,warm,warmContracts)<-Q.compileSourceGroups "managed-support" (B.literal cache) [] M.empty plan >>=expect "managed protection warm cache"
 assert "protection uses checked raw dependencies identically after warm hit"(Q.inferredCount warm==0&&map U.encodeObject warmObjects==map U.encodeObject objects&&map(\(n,c)->(n,SI.contractProtected c))(M.toList warmContracts)==map(\(n,c)->(n,SI.contractProtected c))(M.toList contracts))
 pass "selected managed support protection and irrelevant signed-candidate control"

supportCycleChecks cache=do
 let ac=T.SClassDecl "A" [("a",T.Star)] [] [("a",T.SArrow(T.STVar "a")int)]
     bc=T.SClassDecl "B" [("a",T.Star)] [] [("b",T.SArrow(T.STVar "a")int)]
     ai=T.SInstanceDecl [] [] "A" [int] [("a",T.SLam "x" T.Nothing(T.SLet "ignored" (T.SVar "$MLF.Stack.callStack")(T.SApp(T.SVar "b")(T.SVar "x"))))]
     bi=T.SInstanceDecl [] [] "B" [int] [("b",T.SLam "x" T.Nothing(T.SApp(T.SVar "a")(T.SVar "x")))]
 pm<-expect "pure recursive support SCC plan"(SI.prepareSourcePlan M.empty [] [ac,bc] [("aInt",ai),("bInt",bi)] (M.fromList Prim.compareString[("plain",IS.fromList[0,1])]) [IS.fromList[0,1],IS.fromList[0,1]] [("plain",T.Nothing,T.SIntLit 42)])
 plan<-case pm of T.Just p->pure p;_->error "pure support SCC must not trigger source/support fallback"
 assert "actual generated support SCC is mutual"(any(\ns->"aInt" `elem` ns&&"bInt" `elem` ns)(SI.planGroups plan))
 (objects,_,contracts)<-Q.compileSourceGroups "support-cycle" (B.literal cache) [] M.empty plan >>=expect "support SCC checked compilation"
 assert "all support SCC peers inherit managed protection"(all(\n->case M.lookup Prim.compareString n contracts of T.Just c->SI.contractProtected c;_->False)["aInt","bInt"])
 assert "unused support SCC does not poison independent plain source"(case M.lookup Prim.compareString "plain" contracts of T.Just c->not(SI.contractProtected c);_->False)
 pass "actual recursive generated-support SCC protection closure"
