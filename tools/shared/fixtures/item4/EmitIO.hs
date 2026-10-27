{-# LANGUAGE OverloadedStrings #-}
module Main where
-- Focused checked-xMLF-to-native boundary probe, not a shared syntax fixture.
import Prelude
import System.Environment (getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.LLVM as L
import qualified MLF.Host.Base as B

ls = foldr (:) []
con s ts = T.XCon s (ls ts)
int = con "Int" []
unit = con "()" []
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
  [T.XAlternative (T.XConstructorPattern "[]" []) (T.XIntTerm 0),
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
main = do
  args <- getArgs
  case args of
    [destination] -> case L.emitLLVMIO program of
      T.Left e -> error (B.unpack e)
      T.Right llvm -> writeFile destination (B.unpack llvm)
    _ -> error "usage: emit-item4-io OUTPUT.ll"
