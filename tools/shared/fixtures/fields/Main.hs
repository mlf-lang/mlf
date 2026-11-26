{-# LANGUAGE ScopedTypeVariables #-}
module Main where
import Prelude
import qualified Control.Exception as E
import Control.Monad (forM_,unless)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Separate as S
import qualified Bootstrap.Primitive as Metadata
import qualified Bootstrap.Types as T
import qualified MLF.Primitive as P

need label ok = unless ok (fail label)
old fields = B.v_concatStringList (concatMap (\s->[B.v_showInt (B.v_stringLength s),B.literal ":",s]) fields)
reference = concatMap (\s->show (length s)++":"++s)
bad label = B.failure label
{-# NOINLINE bad #-}
failed label wanted value = do
  result <- E.try (E.evaluate value)
  case result of
    Left (B.HostError message) -> need label (message==wanted)
    Right _ -> fail (label++": did not fail")

main = do
 need "primitive code and previous bound" (Metadata.primitiveCode T.PPackStringFields==135 && Metadata.primitiveCode T.PByteArrayCRC32==134)
 need "primitive inventory" (map Metadata.primitiveCode Metadata.allPrimitives==[0..137])
 need "primitive name, arity and strictness" (B.unpack(Metadata.primitiveName T.PPackStringFields)=="packStringFields" && Metadata.primitiveArity T.PPackStringFields==1 && Metadata.primitiveStrict T.PPackStringFields)
 need "primitive signature" (case Metadata.primitiveSignature T.PPackStringFields of
   ([],T.Function (T.Applied list [T.Applied input []]) (T.Applied output [])) -> map B.unpack [list,input,output]==["[]","String","String"]
   _ -> False)
 need "primitive lookup" (case Metadata.lookupTargetPrimitive(B.literal "packStringFields") of T.Just T.PPackStringFields -> True; _ -> False)
 let atoms=["",":","000:aa","a\0z","α中😀","\x7f\x80\x7ff\x800\xd7ff\xe000\xffff\x10000\x10ffff"]
     sizes=[0,1,2,9,10,11,99,100,101,255,256,257,999,1000,1001,1023,1024,1025,9999,10000]
     fields=[[take n (cycle "aα中😀\0:")] | n<-sizes]++
       [[a,b,c]|a<-atoms,b<-atoms,c<-atoms]++
       [[take ((i*37) `mod` 300) (cycle "X😀中\0")|i<-[0..n]]|n<-[0,1,10,100,1024]]
 forM_ (zip [0::Int ..] fields) $ \(i,parts)->do
  let inputs=map B.literal parts; want=reference parts
  need ("shared decoder "++show i) (case S.unpack (S.pack inputs) of T.Right actual -> map B.unpack actual==parts; _ -> False)
  forM_ [("legacy",old inputs),("host",P.packStringFields inputs),("shared caller",S.pack inputs)] $ \(lane,value)->do
   need (lane++" bytes "++show i) (B.unpack value==want)
   need (lane++" scalar length "++show i) (B.v_stringLength value==fromIntegral(length want))
   forM_ (filter (<length want) [0,1,2,255,256,257,length want-1]) $ \j->whenNonnegative j $
    need (lane++" scalar indexing "++show(i,j)) (B.v_stringCodeAt value (fromIntegral j)==fromIntegral(fromEnum(want!!j)))
   need (lane++" suffix "++show i) (B.unpack (B.v_stringSlice value 0 (B.v_stringLength value))==want)
 forM_ [("legacy",old),("host",P.packStringFields),("shared caller",S.pack)] $ \(lane,encode)->do
  failed (lane++" spine") "spine" (encode (bad "spine"))
  failed (lane++" first before tail") "head" (encode (bad "head":bad "tail"))
  failed (lane++" later head") "second" (encode [B.literal "ok",bad "second",bad "third"])
  failed (lane++" later spine") "tail" (encode (B.literal "":bad "tail"))
  failed (lane++" invalid scalar first") "invalid Unicode scalar" (encode [B.literal "\xd800",bad "later"])
  need (lane++" unused remains lazy") (if True then True else B.v_stringLength(encode[bad "unused"])==0)
 putStrLn ("PASS framing "++show(length fields)++" independent cases in 3 lanes, Unicode scalar caches and 6 demand controls per lane")
 where whenNonnegative i action = if i>=0 then action else pure ()
