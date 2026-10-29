{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad(unless)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as S
import qualified Bootstrap.Std as B
import qualified Bootstrap.Data as D
import qualified Bootstrap.Separate as U
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.X.Checked as C
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Type as Ty
import qualified Bootstrap.X.Pretty as Pretty
import qualified MLF.Primitive as P
right(T.Right x)=x
right(T.Left e)=error(P.textToChars e)
left(T.Left _)=True
left _=False
assert label ok=unless ok(error label)
int=T.XCon "Int" []
arrow=T.XArrow int int
unit=T.XConstructor "()" []
name n text=T.XName n text
var n text=T.XVarTerm(name n text)
app=T.XApp
prim p args=foldl app (T.XPrimitive p []) args
iface key deps binds=A.CrateInterface key deps [] [] [] [] [] [] [] binds "" "pending" [(k,False)|(k,_)<-binds]
fragment key binds term=U.UnitObject (U.UnitInterface key [] [] [] [] [] binds (U.fingerprint(Pretty.prettyTerm term))) term
object key deps binds term=A.makeObject(iface key deps binds)[fragment (P.textFromChars("Original"++P.textToChars(U.encoded key))) binds term]
empty=(A.FragmentState 0 M.empty [] [] S.empty,T.Right C.emptySpine)
by object=A.interfaceMap[A.objectInterface object]
layouts object=M.fromList P.compareString [(D.datatypeName d,A.datatypePart d)|d<-A.crateLoweredData(A.objectInterface object)]
full object=right(A.linkCrateWithSpine (by object) (layouts object) empty object)
selected object keys=right(A.linkSelectedCrateWithSpine keys (by object) (layouts object) empty object)
finish=finishWith []
finishWith declarations linked key ty=let checked=right(C.check(T.XWithData declarations(T.XAbs(name 900 key) ty (T.XLetRec [] (var 900 key)))))
                    in right(C.finishSpine(right(snd linked))[(key,key)]checked)
data Value=N P.Int|Q Bool|F T.XName T.XErased [(T.XName,Value)]|Prim T.Primitive [Value]
eval env expr=case expr of
 T.XEVar n->case [v|(k,v)<-env,X.equalName k n] of v:_->v;[]->error "free variable"
 T.XEInt n->N n
 T.XEBool b->Q b
 T.XEPrimitive p->Prim p []
 T.XEAbs n b->F n b env
 T.XEApp f x->apply(eval env f)(eval env x)
 T.XELet n rhs b->eval((n,eval env rhs):env)b
 T.XELetRec ds b->let scope=[(n,eval scope rhs)|(n,rhs)<-ds]++env in eval scope b
 _->error "unsupported oracle expression"
apply(F n b env)x=eval((n,x):env)b
apply(Prim p args)x=case (p,args++[x]) of
 (T.PEqInt,[N a,N b])->Q(a==b)
 (T.PSubInt,[N a,N b])->N(a-b)
 (T.PAddInt,[N a,N b])->N(a+b)
 (T.PIfThenElse,[Q c,a,b])->if c then a else b
 (T.PQuotInt,[N a,N b])->N(a `quot` b)
 (_,values)->Prim p values
apply _ _=error "not function"
value checked=case eval [] (X.erase(C.term checked)) of N n->n;_->error "not number"
check checked=let oracle=right(C.check(C.term checked)) in assert "independent checker" (Ty.alphaEq(C.typeOf oracle)(C.typeOf checked))
changeUnit update (U.UnitObject i t)=U.UnitObject(update i)t
changeUnit update (U.CheckedUnitObject i checked)=U.UnitObject(update i)(C.term checked)
wrongHash(U.UnitInterface a b c d e f g _)=U.UnitInterface a b c d e f g "wrong"
wrongBinding(U.UnitInterface a b c d e f g h)=U.UnitInterface a b c d e f [(k,T.XCon "Bool" [])|(k,_)<-g] h
renameUnit key(U.UnitInterface _ b c d e f g h)=U.UnitInterface key b c d e f g h
roundTrip obj=let interface=right(A.decodeInterface(A.encodeInterface(A.objectInterface obj)))
                  decoded=right(A.decodeObject interface(A.encodeObject obj))
              in if P.eqString(A.encodeObject decoded)(A.encodeObject obj) && P.eqString(A.encodeInterface interface)(A.encodeInterface(A.objectInterface obj)) then decoded else error "noncanonical crate wire roundtrip"
main=do
 let evenN=name 1 "even";oddN=name 2 "odd";param=name 3 "n"
     branch own other base=T.XAbs param int (foldl app (T.XPrimitive T.PIfThenElse [int]) [prim T.PEqInt [T.XVarTerm param,T.XIntTerm 0],T.XIntTerm base,app(T.XVarTerm other)(prim T.PSubInt[T.XVarTerm param,T.XIntTerm 1])])
     tv=T.XTyVar 100;poly=T.XForall tv T.XBot (T.XArrow(T.XVar tv)(T.XVar tv))
     identity=T.XTypeAbs tv T.XBot (T.XAbs(name 5 "x")(T.XVar tv)(var 5 "x"))
     defs=[(evenN,arrow,branch evenN oddN 1),(oddN,arrow,branch oddN evenN 0),(name 4 "answer",int,app(T.XVarTerm evenN)(T.XIntTerm 6)),(name 6 "poison",int,prim T.PQuotInt[T.XIntTerm 1,T.XIntTerm 0]),(name 7 "identity",poly,identity)]
     bindings=[(X.nameHint n,t)|(n,t,_)<-defs]
     original=roundTrip(object "test:scc" [] bindings (T.XLetRec defs unit))
     split=roundTrip(right(A.splitClosedDeclarationObject original))
     sizes=map(length.U.unitBindings.U.objectInterface)(A.objectFragments split)
 assert "nontrivial recursive SCC atomic" (2 `elem` sizes && length sizes==4)
 let states=[full original,full split,selected split ["answer"]]
 mapM_ (\state->let term=finish state "answer" int in check term>>assert "selected-full semantic parity, poison stays lazy" (value term==1)) states
 let chosen=selected split ["answer"]
 assert "closure includes mutual dependency only" (M.keys(A.fragmentBindings(fst chosen))==["answer","even","odd"])
 let polyRoot=finish(selected split ["identity"])"identity" poly
 check polyRoot
 assert "polymorphic scheme preserved" (Ty.alphaEq(C.typeOf polyRoot)poly)
 let fs=A.objectFragments split;ci=A.objectInterface split
     originalCorrupt=A.CrateObject(A.withObjectFingerprint(A.objectInterface original) "wrong")(A.objectFragments original)
     originalUnitCorrupt=A.makeObject(A.objectInterface original)(map(changeUnit wrongHash)(A.objectFragments original))
 assert "splitter rejects corrupt original object" (left(A.splitClosedDeclarationObject originalCorrupt))
 assert "splitter rejects corrupt original unit" (left(A.splitClosedDeclarationObject originalUnitCorrupt))
 assert "wrong whole hash rejected" (left(A.linkSelectedCrateWithSpine ["answer"] (by split) M.empty empty (A.CrateObject(A.withObjectFingerprint ci "wrong")fs)))
 let badUnit=A.makeObject ci [changeUnit wrongHash f|f<-fs]
 assert "wrong selected unit hash rejected" (left(A.linkSelectedCrateWithSpine ["answer"] (by badUnit) M.empty empty badUnit))
 let badType=A.makeObject ci [changeUnit wrongBinding f|f<-fs]
 assert "wrong unit binding metadata rejected" (left(A.linkSelectedCrateWithSpine ["answer"] (by badType) M.empty empty badType))
 let reversed=A.makeObject ci(reverse fs)
 assert "wrong dependency order rejected" (left(A.linkSelectedCrateWithSpine ["answer"] (by reversed) M.empty empty reversed))
 let collisionObject=object "test:collision" [] [("even",arrow)] (T.XLet(name 70 "even")(T.XAbs(name 71 "arg")int(T.XIntTerm 0))unit)
     collisionState=full collisionObject
 assert "wrong local order cannot use incoming owned-key collision" (left(A.linkSelectedCrateWithSpine ["answer"] (by reversed) M.empty collisionState reversed))
 let missing=A.makeObject ci [f|f<-fs,not("even" `elem` map fst(U.unitBindings(U.objectInterface f)))]
 assert "missing dependency rejected" (left(A.linkSelectedCrateWithSpine ["answer"] (by missing) M.empty empty missing))
 let duplicate=A.makeObject ci [changeUnit(renameUnit "same") f|f<-fs]
 assert "duplicate unselected unit names rejected" (left(A.linkSelectedCrateWithSpine [] (by duplicate) M.empty empty duplicate))
 let ext=object "test:external" [] [("external",int)](T.XLet(name 40 "external")(T.XIntTerm 9)unit)
     incoming=full ext
     dependent=object "test:consumer" [("test:external","external.mlfci",A.semanticFingerprint(A.objectInterface ext))] [("fromExternal",int)](T.XAbs(name 50 "external")int(T.XLet(name 51 "fromExternal")(var 50 "external")unit))
     interfaces=A.interfaceMap[A.objectInterface ext,A.objectInterface dependent]
     linked=right(A.linkSelectedCrateWithSpine ["fromExternal"] interfaces M.empty incoming dependent)
 check(finish linked "fromExternal" int)
 assert "incoming external state satisfies closure" (value(finish linked "fromExternal" int)==9)
 assert "missing incoming external state rejected" (left(A.linkSelectedCrateWithSpine ["fromExternal"] interfaces M.empty empty dependent))
 let badImport=object "test:consumer" [("test:external","external.mlfci",A.semanticFingerprint(A.objectInterface ext))] [("fromExternal",int)](T.XAbs(name 50 "external")(T.XCon "Bool" [])(T.XLet(name 51 "fromExternal")(T.XIntTerm 9)unit))
 assert "wrong actual import type rejected" (left(A.linkSelectedCrateWithSpine ["fromExternal"] (A.interfaceMap[A.objectInterface ext,A.objectInterface badImport]) M.empty incoming badImport))
 let unicodeObject=roundTrip(right(A.splitClosedDeclarationObject(object "test:é😀" [] [("u",int)](T.XLet(name 80 "u")(T.XIntTerm 3)unit))))
 assert "unicode crate identity encodes valid SCC module names" (value(finish(full unicodeObject) "u" int)==3)
 let builtin=roundTrip(right A.builtinPrelude)
     builtinInterface=A.objectInterface builtin
     builtinFull=full builtin
 case A.crateBindings builtinInterface of
  (key,ty):_->do
   let chosenBuiltin=selected builtin [key]
       declarations=A.crateLoweredData builtinInterface
       fullRoot=finishWith declarations builtinFull key ty
       chosenRoot=finishWith declarations chosenBuiltin key ty
   check fullRoot
   check chosenRoot
   assert "real canonical builtin wire selected/full type parity" (Ty.alphaEq(C.typeOf fullRoot)(C.typeOf chosenRoot))
  []->error "canonical builtin has no exported bindings"
 let badIdentity=A.makeObject ci [changeUnit(renameUnit "mlf:invalid") f|f<-fs]
 assert "wire module identity grammar remains strict" (left(A.decodeObject(A.objectInterface badIdentity)(A.encodeObject badIdentity)))
 putStrLn "PASS recursive SCC atomicity, polymorphic and lazy semantics, selected/full checker parity, incoming dependencies and malformed fragment rejection"
