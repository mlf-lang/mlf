{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import System.Environment (getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.LLVM as L
import qualified MLF.Host.Base as B
ls=foldr (:) []
con s ts=T.XCon s(ls ts)
int=con "Int"[]
unit=con "()"[]
io t=con "IO"[t]
p op ts=T.XPrimitive op(ls ts)
app=foldl T.XApp
n i s=T.XName i s
v i s=T.XVarTerm(n i s)
lit=T.XIntTerm
bind i ty a b=app(p T.PIOBind[ty,unit])[a,T.XAbs(n i "bound")ty b]
check i action code=bind i unit action (T.XCase(v i "bound")(io unit)(ls[T.XAlternative(T.XConstructorPattern "()" [])(T.XApp(p T.PPrintInt[])(lit code))]))
arrayTest opNew opWrite ty initial val ident code =
 let w=ident+100; ar=ident+200; cnt=ident+300; done=ident+400
     wty=T.XArrow ty (T.XArrow int (io unit))
     recur=app(v w "writer")[v ar "array",app(p T.PSubInt[])[v cnt "count",lit 1]]
     write=app(p opWrite[])[v ar "array",lit 0,val]
     step=app(p T.PIOBind[unit,unit])[write,T.XAbs(n done "done")unit recur]
     body=T.XAbs(n ar "array")ty(T.XAbs(n cnt "count")int
       (app(p T.PIfThenElse[io unit])[app(p T.PLtInt[])[v cnt "count",lit 1],write,step]))
 in T.XLetRec(ls[(,,)(n w "writer")wty body])
     (bind ident ty (app(p opNew[])[lit 1,initial]) (check (ident+1)(app(v w "writer")[v ident "bound",lit 2])code))
sv=T.XTyVar 0
state=T.XVar sv
st t=con "ST"[state,t]
starray=con "STArray"[state,int]
stbind ident ty action body = app(p T.PSTBind[state,ty,int]) [action,T.XAbs(n ident "bound")ty body]
stcheck = T.XCase(v 41 "bound")(st int)(ls [T.XAlternative(T.XConstructorPattern "()" [])(T.XApp(p T.PSTReturn[state,int])(lit 104))])
stbody = stbind 40 starray (app(p T.PNewSTArray[state,int])[lit 1,lit 0])
   (stbind 41 unit (app(p T.PWriteSTArray[state,int])[v 40 "bound",lit 0,lit 7]) stcheck)
sttest=T.XApp(p T.PPrintInt[])(T.XApp(p T.PRunST[int])(T.XTypeAbs sv T.XBot stbody))
tupleName=B.literal ('(':replicate 63 ','++")")
tuple=app(T.XConstructor tupleName(ls(replicate 64 int)))(map lit[0..63])
tupleTest=T.XApp(p T.PPrintInt[])(T.XCase tuple int(ls[T.XAlternative(T.XConstructorPattern tupleName(ls(replicate 63 T.Nothing++[T.Just(n 70 "last")]))) (v 70 "last")]))
program=foldr (\(i,a)rest->bind i unit a rest)(T.XApp(p T.PPutStrLn[])(T.XStringTerm "DONE"))
 [(1,arrayTest T.PNewIntArray T.PWriteIntArray(con "IntArray"[])(lit 0)(lit 7)10 101),
  (2,arrayTest T.PNewDoubleArray T.PWriteDoubleArray(con "DoubleArray"[])(T.XDoubleTerm 0)(T.XDoubleTerm 7)20 102),
  (3,arrayTest T.PNewByteArray T.PWriteByteArray(con "ByteArray"[])(lit 0)(lit 7)30 103),
  (4,sttest),(5,tupleTest),
  (6,bind 50(con "IntTable"[])(p T.PNewIntTable[])(check 51(app(p T.PWriteIntTable[])[v 50 "bound",lit 3,lit 9])105))]
main = do
 args <- getArgs
 case args of
  [path] -> case L.emitLLVMIO program of
   T.Left e -> error (B.unpack e)
   T.Right llvm -> writeFile path (B.unpack llvm)
  _ -> error "expected output LLVM path"
