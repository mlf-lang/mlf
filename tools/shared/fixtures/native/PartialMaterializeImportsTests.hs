{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad (unless)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as S
import qualified Bootstrap.Map as M
import qualified Bootstrap.ImportedRoot as I
import qualified Bootstrap.X.Checked as C
import qualified Bootstrap.X.Type as XT
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.CompilerCore as Core
import qualified MLF.Primitive as P
right (T.Right x)=x
right (T.Left e)=error(P.textToChars e)
compiled (T.Right x)=x
compiled (T.Left e)=error(P.textToChars(Core.prettyError e))
left (T.Left _)=True
left _=False
assert label ok=unless ok(error label)
int=T.XCon "Int" []
sint=T.SCon "Int" []
unit=T.XConstructor "()" []
builtin=T.XName 0 "same"
spine=[T.XLet builtin (T.XIntTerm 7) unit]
available=M.singleton "b" (builtin,int)
make names body=let sig=M.fromList P.compareString [(k,int)|k<-names]
                    defs=[(k,T.CheckRecursive(T.SAnnotation [] sint),T.SChecked sint (T.SApp(T.SPrimitive T.PPanic)(T.SStringLit "unlinked module parameter")))|k<-names]
                in (sig,compiled(I.finishCompilation sig (T.SProgram [] (T.SLetRec defs body),M.empty)))
parts (T.XWithData _ b)=b
parts b=b
stripLets (T.XLet _ _ b)=stripLets b
stripLets (T.XLetRec _ b)=stripLets b
stripLets b=b
data Value = Number P.Int | Closure T.XName T.XErased [(T.XName,Value)]
eval env term=case term of
 T.XEInt n->Number n
 T.XEVar n->case [v|(k,v)<-env,X.equalName k n] of
  v:_->v
  []->error "test evaluator found free name"
 T.XEAbs n body->Closure n body env
 T.XEApp f a->case eval env f of
  Closure n body scope->eval ((n,eval env a):scope) body
  _->error "test evaluator expected lambda"
 T.XELet n rhs body->eval ((n,eval env rhs):env) body
 T.XELetRec [] body->eval env body
 _->error "unexpected term in independent tiny evaluator"
main=do
 let linked=right(C.appendSpine C.emptySpine (right(C.check(T.XLet (T.XName 0 "b") (T.XIntTerm 7) unit))))
     materialize keys c=right(C.materializeSpine linked [(k,k)|k<-keys] (I.checkedWrapper c))
     (sig,c)=make ["b"] (T.SLam "b" (T.Just(T.SAnnotation [] sint)) (T.SVar "b"))
     (r,remaining)=materialize ["b"] c
 assert "zero native parameters" (null remaining)
 case parts(C.term r) of
  T.XLet name _ _->assert "unused library bodies still grafted" (P.textToChars(X.nameHint name)=="b")
  _->error "unused library body was erased"
 assert "returned lambda type" (XT.alphaEq(C.typeOf r)(T.XArrow int int))
 case eval [] (T.XEApp (X.erase(C.term r)) (T.XEInt 99)) of
  Number value->assert "same hint independent evaluation" (value==99)
  _->error "lambda lost"
 let (sig2,c2)=make ["b","n"] (T.SApp (T.SApp(T.SPrimitive T.PAddInt)(T.SVar "b"))(T.SVar "n"))
     (mixed,rest)=materialize ["b","n"] c2
 assert "native prefix" (rest==["n"])
 case parts(C.term mixed) of
  T.XAbs name ty _->assert "native lambda outside graft" (P.textToChars(X.nameHint name)=="n" && XT.alphaEq ty int)
  _->error "native prefix lost"
 let (_,unused)=make ["b","n"] (T.SVar "b")
     (pruned,none)=materialize ["b","n"] unused
 assert "unused native prefix pruned" (null none && XT.alphaEq(C.typeOf pruned) int)
 let (_,nested)=make ["b","n"] (T.SLet "unusedRhs" (T.SVar "n") (T.SVar "b"))
     (_,kept)=materialize ["b","n"] nested
 assert "unused local RHS still counts" (kept==["n"])
 let boolean=right(C.appendSpine C.emptySpine (right(C.check(T.XLet (T.XName 0 "b") (T.XBoolTerm True) unit))))
 assert "wrong admitted type even unused rejected" (left(C.materializeSpine boolean [("b","b")] (I.checkedWrapper c)))
 assert "wrong hint rejected" (left(C.materializeSpine linked [("b","wrong")] (I.checkedWrapper c)))
 assert "duplicate key rejected" (left(C.materializeSpine linked [("b","b"),("b","n")] (I.checkedWrapper c2)))
 assert "missing prefix rejected" (left(C.materializeSpine linked [("b","b")] (right(C.check(T.XIntTerm 3)))))
 assert "nonempty prefix missing scope group rejected" (left(C.materializeSpine linked [("b","b")] (right(C.check(T.XAbs(T.XName 9 "b") int (T.XVarTerm(T.XName 9 "b")))))))
 let unboundNative=right(C.check(T.XAbs(T.XName 1 "n") int (T.XLet(T.XName 2 "bad") (T.XVarTerm(T.XName 1 "n")) unit)))
 assert "spine cannot depend on remaining native import" (left(C.appendSpine C.emptySpine unboundNative))
 let unknown=T.XCon "New" []
     old=right(C.appendSpine C.emptySpine (right(C.check(T.XLet (T.XName 0 "f") (T.XAbs(T.XName 1 "x") unknown (T.XVarTerm(T.XName 1 "x"))) unit))))
     extension=right(C.check(T.XWithData [T.DataDecl "New" ["a"] [T.ConstructorDecl "MkNew" []]] (T.XIntTerm 1)))
 assert "unknown nominal weakening rejected" (left(C.materializeSpine old [] extension))
 let plain=right(C.check(T.XAbs(T.XName 8 "returned") int (T.XVarTerm(T.XName 8 "returned"))))
     (preserved,zero)=right(C.materializeSpine C.emptySpine [] plain)
 assert "empty requested preserves returned lambda" (null zero && XT.alphaEq(C.typeOf preserved)(C.typeOf plain))
 mapM_ (\term->let independent=right(C.check(C.term term)) in assert "independent whole checker" (XT.alphaEq(C.typeOf independent)(C.typeOf term))) [r,mixed,pruned,preserved]
 putStrLn "PASS partial checked composition, unused prefix pruning, binder identity, nominal weakening and independent checker oracle"
