{-# LANGUAGE OverloadedStrings #-}
module Main where
-- Fresh nominal types may close their constructor-site census. This fixture
-- combines a strict saturated site with a bare constructor passed to opaque
-- installed polymorphic code, which creates a lazy poison field. Escaping must
-- invalidate the earlier strict-field observation, including after optimization.
import Prelude
import Control.Monad (forM_)
import System.Environment (getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.X.Checked as C
import qualified Bootstrap.LLVM.Library as N
import qualified MLF.Primitive as P
right (T.Right x)=x
right (T.Left x)=error(P.textToChars x)
identity=P.textFromChars(replicate 64 'a')
unit=T.XConstructor "()" []
main=do
 [directory]<-getArgs
 let a=T.XTyVar 0; at=T.XVar a; double=T.XCon "Double" []
     idTy=T.XForall a T.XBot (T.XArrow at at)
     makeTy=T.XForall a T.XBot (T.XArrow (T.XArrow double at) at)
     arg=T.XName 10 "argument"
     poison=T.XApp (T.XPrimitive T.PPanic [double]) (T.XStringTerm "private-poison")
     ident=T.XTypeAbs a T.XBot (T.XAbs arg at (T.XVarTerm arg))
     maker=T.XTypeAbs a T.XBot (T.XAbs arg (T.XArrow double at) (T.XApp (T.XVarTerm arg) poison))
     entries=[("ident","ident",idTy),("maker","maker",makeTy)]
     values=[("ident",ident),("maker",maker)]
     linked=foldl (\spine (i,(key,value))->right(C.appendSpine spine(right(C.check(T.XLet(T.XName i key)value unit))))) C.emptySpine(zip[0..]values)
     base=right(N.prepareLayout identity entries [])
     layout=right(N.prepareLayoutWithTypeNames identity entries [] (right(N.libraryTypeNames base linked)))
     private=T.DataDecl "PrivateBox" [] [T.ConstructorDecl "PrivateBoxValue" [T.Applied "Double" []]]
     privateTy=T.XCon "PrivateBox" []
     parameter=T.XName 20 "parameter";field=T.XName 21 "field"
     ioUnit=T.XCon "IO" [T.XCon "()" []]
     output n=T.XApp(T.XPrimitive T.PPrintInt[])(T.XIntTerm n)
     observed=T.XApp(T.XApp(T.XPrimitive T.PEqDouble[])(T.XVarTerm field))(T.XDoubleTerm 4)
     demanded=T.XApp(T.XApp(T.XApp(T.XPrimitive T.PIfThenElse[ioUnit])observed)(output 1))(output 0)
 writeFile(directory++"/private-library.ll")(concatMap P.textToChars(right(N.emitLibrary layout linked)))
 forM_[("private-identity","ident",idTy,False),("private-escape-ignore","maker",makeTy,True),("private-escape-demand","maker",makeTy,False)] $ \(label,key,ty,ignored)->do
  let selected=T.XName 20 key
      instantiate=T.XTypeApp(T.XVarTerm selected)(T.XThen (T.XInner (T.XBottom privateTy)) T.XElim)
      value=if key=="ident" then T.XApp instantiate(T.XApp(T.XConstructor "PrivateBoxValue"[])(T.XDoubleTerm 4)) else T.XApp instantiate(T.XConstructor "PrivateBoxValue"[])
      answer=T.XCase value ioUnit[T.XAlternative(T.XConstructorPattern "PrivateBoxValue"[if ignored then T.Nothing else T.Just field])(if ignored then output 1 else demanded)]
      identityName=T.XName 22 "ident"
      seed=T.XApp(T.XTypeApp(T.XVarTerm identityName)(T.XThen(T.XInner(T.XBottom privateTy))T.XElim))(T.XApp(T.XConstructor "PrivateBoxValue"[])(T.XDoubleTerm 4))
      body=if key=="ident" then T.XAbs selected ty answer else
        T.XAbs selected ty(T.XAbs identityName idTy(T.XCase seed ioUnit[T.XAlternative(T.XConstructorPattern "PrivateBoxValue"[T.Nothing])answer]))
      selectedKeys=if key=="ident" then [key] else [key,"ident"]
  writeFile(directory++"/"++label++".ll")(concatMap P.textToChars(right(N.emitRoot layout selectedKeys(right(C.check(T.XWithData[private]body))))))
 putStrLn "PASS private constructor boundary emission"
