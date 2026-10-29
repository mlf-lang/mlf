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
 let (sig,c)=make ["b"] (T.SLam "b" (T.Just(T.SAnnotation [] sint)) (T.SVar "b"))
     (r,remaining)=right(I.materializeImports sig c 1 available spine)
 assert "zero native parameters" (M.null remaining)
 assert "returned lambda type" (XT.alphaEq(C.typeOf r)(T.XArrow int int))
 case stripLets(parts(C.term r)) of
  T.XAbs _ _ _->pure ()
  _->error "returned user lambda removed"
 case eval [] (T.XEApp (X.erase(C.term r)) (T.XEInt 99)) of
  Number value->assert "same-hint distinct identity preserved" (value==99)
  _->error "returned lambda failed to return its argument"
 let (sig2,c2)=make ["b","n"] (T.SApp (T.SApp(T.SPrimitive T.PAddInt)(T.SVar "b"))(T.SVar "n"))
     (mixed,rest)=right(I.materializeImports sig2 c2 1 available spine)
 assert "mixed only native remains" (M.keys rest==["n"])
 case parts(C.term mixed) of
  T.XAbs name ty _->assert "native prefix remains outside graft" (P.textToChars(X.nameHint name)=="n" && XT.alphaEq ty int)
  _->error "native prefix lost"
 let again=right(C.check(C.term mixed))
 assert "independent type" (XT.alphaEq(C.typeOf again)(C.typeOf mixed))
 assert "wrong map type rejected" (left(I.materializeImports sig c 1 (M.singleton "b" (builtin,T.XCon "Bool" [])) spine))
 assert "unbound map identity rejected" (left(I.materializeImports sig2 c2 1 (M.singleton "b" (T.XName 999 "same",int)) spine))
 let (unchanged,retained)=right(I.materializeImports sig2 c2 1 M.empty [])
 assert "no overlap retains native inventory" (M.size retained==2 && XT.alphaEq(C.typeOf unchanged)(C.typeOf(I.checkedWrapper c2)))
 putStrLn "PASS zero-native returned lambda, mixed imports, same-hint distinct identity, wrong mapping rejection, independent check"
