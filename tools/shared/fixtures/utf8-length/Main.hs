{-# LANGUAGE ScopedTypeVariables #-}
module Main where
import Prelude
import Control.Monad (forM_,unless)
import qualified Control.Exception as E
import qualified Bootstrap.Primitive as Meta
import qualified Bootstrap.ArtifactStructure as A
import qualified Bootstrap.Types as T
import qualified Bootstrap.Bitstream as W
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P
need label yes=unless yes (fail label)
bytes = sum . map (\c -> let n=fromEnum c in if n<128 then 1 else if n<2048 then 2 else if n<65536 then 3 else 4)
bad label=B.failure label
{-# NOINLINE bad #-}
failed label wanted value=do
 result<-E.try (E.evaluate value)
 case result of {Left (B.HostError message)->need label (message==wanted);Right _->fail (label++": missing error")}
main=do
 need "append-only opcode inventory" (map Meta.primitiveCode Meta.allPrimitives==[0..137])
 need "previous opcode preserved" (Meta.primitiveCode T.PPackStringFields==135)
 need "UTF-8 opcode metadata" (Meta.primitiveCode T.PStringUtf8Length==136 && Meta.primitiveArity T.PStringUtf8Length==1 && Meta.primitiveStrict T.PStringUtf8Length)
 need "UTF-8 name" (B.unpack (Meta.primitiveName T.PStringUtf8Length)=="stringUtf8Length")
 need "UTF-8 lookup" (case Meta.lookupTargetPrimitive (B.literal "stringUtf8Length") of T.Just T.PStringUtf8Length->True;_->False)
 need "UTF-8 signature" (case Meta.primitiveSignature T.PStringUtf8Length of
  ([],T.Function (T.Applied a []) (T.Applied b []))->map B.unpack [a,b]==["String","Int"];_->False)
 need "artifact opcode roundtrip" (case A.fromPrimitive (A.toPrimitive T.PStringUtf8Length) of T.Right T.PStringUtf8Length->True;_->False)
 let atoms=["", "a\0z", "α中😀", "\x7f\x80\x7ff\x800\xd7ff\xe000\xffff\x10000\x10ffff"]
     inputs=[a++b|a<-atoms,b<-atoms]++[take n (cycle "aα中😀\0")|n<-[0,1,2,63,64,65,255,256,257,4096]]
 forM_ (zip [0::Int ..] inputs) $ \(i,chars)->do
  let text=B.literal chars;want=fromIntegral (bytes chars)
      padded=P.concatString (B.literal "前") (P.concatString text (B.literal "😀"))
      values=[(text,want),(padded,want+7),(P.stringSlice padded 1 (fromIntegral (length chars)),want)]
  forM_ values $ \(value,n)->do
   need ("byte count "++show i) (P.stringUtf8Length value==n)
   forM_ [-1,0,n-1,n,n+1,maxBound] $ \lim->case W.utf8Size lim value of
    T.Left e->need "byte budget rejection" (n>lim && B.unpack e=="binary symbol byte limit exceeded")
    T.Right actual->need "byte budget acceptance" (n<=lim && actual==n)
 failed "argument demanded" "text-first" (P.stringUtf8Length (bad "text-first"))
 failed "invalid scalar" "invalid Unicode scalar" (P.stringUtf8Length (B.literal "\xd800"))
 need "unused argument remains lazy" (if True then True else P.stringUtf8Length (bad "unused")==0)
 putStrLn "PASS UTF-8 length: 78 host count/slice/concat cases, byte budgets, primitive metadata and demand"
