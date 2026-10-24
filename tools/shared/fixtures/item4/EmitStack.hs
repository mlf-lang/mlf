{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import System.Environment (getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.LLVM as L
import qualified MLF.Host.Base as B

ls = foldr T.Cons T.Nil
con s ts = T.XCon s (ls ts)
int = con "Int" []
unit = con "Unit" []
char = con "Char" []
chars = con "[]" [char]
ioerr = con "IOError" []
io t = con "IO" [t]
p op ts = T.XPrimitive op (ls ts)
a = T.XApp
app f xs = foldl a f xs
name n h = T.XName n h
text s = T.XStringTerm s
charsOf s = a (p T.PTextToChars []) (text s)
fromChars x = a (p T.PTextFromChars []) x
puts x = a (p T.PPutStrLn []) x
printInt x = a (p T.PPrintInt []) x
seqIO n first second = app (p T.PIOBind [unit,unit]) [first, T.XAbs (name n "ignored") unit second]
listCode s = T.XCase (charsOf s) int (ls
  [T.XAlternative (T.XConstructorPattern "[]" T.Nil) (T.XIntTerm 0),
   T.XAlternative (T.XConstructorPattern ":" (ls [T.Just (name 11 "head"),T.Nothing]))
     (a (p T.PCharCode []) (T.XVarTerm (name 11 "head")))])
errValue = a (p T.PUserError []) (charsOf "caught λ😀")
raise = a (p T.PIOError [unit]) errValue
short = seqIO 21 raise (puts (text "BAD continuation"))
handler = T.XAbs (name 22 "error") ioerr
  (puts (fromChars (a (p T.PIOErrorString []) (T.XVarTerm (name 22 "error")))))
recover = app (p T.PCatchIOError [unit]) [short,handler]
program = foldr (uncurry seqIO) (puts (text "DONE"))
  [(1,puts (fromChars (charsOf "roundtrip λ😀"))),
   (2,printInt (listCode "A")),(3,printInt (listCode "")),(4,recover)]
stackTy = con "MLFCallStack" []
emptyStack = p T.PEmptyCallStack []
frame f = app (T.XConstructor "MLFStackFrame" T.Nil)
  [text f,text "pkg",text "Mod",text "file.hs",T.XIntTerm 10,T.XIntTerm 2,T.XIntTerm 12,T.XIntTerm 9]
pushFrame f stk = app (p T.PPushCallStack []) [frame f,stk]
sourceStack = pushFrame "inner" (pushFrame "outer" emptyStack)
prettyStack stk = fromChars (a (p T.PPrettyCallStack []) stk)
raiseStack s stk = app (p T.PIOErrorWithStack [unit]) [a (p T.PUserError []) (charsOf s),stk]
caught action h = app (p T.PCatchIOError [unit]) [action,h]
constant n body = T.XAbs (name n "exception") ioerr body
raiseNamed s = raiseStack s emptyStack
nested = caught (caught (raiseNamed "a") (constant 40 (raiseNamed "b"))) (constant 41 (raiseNamed "c"))
active = caught (raiseNamed "a") (constant 42 (caught (raiseNamed "b") (constant 43 (raiseNamed "c"))))
stackProgram = foldr (uncurry seqIO) (puts (text "STACK DONE"))
  [(51,puts (prettyStack sourceStack)),
   (52,puts (prettyStack emptyStack)),
   (53,caught (raiseStack "caught stack" sourceStack) handler),
   (54,caught (raiseStack "ignored stack" (a (p T.PPanic [stackTy]) (text "BAD stack"))) (constant 44 (puts (text "bottom stack ignored")))),
   (55,caught (app (p T.PIOErrorWithStack [unit])
     [a (p T.PUserError []) (a (p T.PPanic [chars]) (text "BAD message")),sourceStack])
     (constant 45 (puts (text "bottom message ignored"))))]
main = do
  [directory] <- getArgs
  mapM_ (emit directory) [("success",stackProgram),("uncaught",raiseStack "message" sourceStack),("nested",nested),("active",active)]
  where emit directory (mode,term) = case L.emitLLVMIO term of
          T.Left e -> error (mode++": "++B.unpack e)
          T.Right llvm -> writeFile (directory++"/"++mode++".ll") (B.unpack llvm)
