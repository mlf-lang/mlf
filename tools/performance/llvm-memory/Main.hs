module Main where
import Prelude
import qualified CandidateBase as C
import qualified LegacyBase as F
import Control.Exception(SomeException,try,evaluate,displayException)
import Control.Monad(forM_,unless)
import Data.Char(ord)

assert label value=unless value(errorWithoutStackTrace label)
texts=[replicate n 'a'++mark++replicate (1025-n) 'z'|n<-[0,1,254,255,256,257,510,511,512,513,767,768,1023,1024,1025],mark<-["é","λ","中","😀","e\x0301","é中😀"]]++["","ascii","é中😀",concat(replicate 300 "aé中😀")]
capture x=do
 result<-try(evaluate x)::IO(Either SomeException Integer)
 pure(case result of Left e->Left(displayException e);Right value->Right value)
main=do
 assert "94 independent Unicode fixtures"(length texts==94)
 forM_ texts $ \text->do
  let current=C.literal text;old=F.literal text;size=length text
  assert "scalar lengths"(C.v_stringLength current==fromIntegral size&&F.v_stringLength old==fromIntegral size)
  forM_ (zip[0..]text) $ \(i,c)->do
   assert "candidate scalar against independent list"(C.v_stringCodeAt current i==fromIntegral(ord c))
   assert "frozen scalar against independent list"(F.v_stringCodeAt old i==fromIntegral(ord c))
  forM_ (filter(<=size)[0,1,254,255,256,257,511,512,513,size]) $ \start->
   forM_ (filter(<=size-start)[0,1,2,255,256,size-start]) $ \count->do
    let wanted=take count(drop start text)
    assert "candidate Unicode slice"(C.unpack(C.v_stringSlice current(fromIntegral start)(fromIntegral count))==wanted)
    assert "frozen Unicode slice"(F.unpack(F.v_stringSlice old(fromIntegral start)(fromIntegral count))==wanted)
  forM_ [-1,fromIntegral size] $ \i->do
   a<-capture(toInteger(F.v_stringCodeAt old i));b<-capture(toInteger(C.v_stringCodeAt current i))
   assert "exact out-of-range error"(a==b&&case a of Left _->True;_->False)
  forM_ [(-1,0),(0,-1),(size,1),(size+1,0)] $ \(i,n)->do
   a<-capture(toInteger(F.v_stringLength(F.v_stringSlice old(fromIntegral i)(fromIntegral n))))
   b<-capture(toInteger(C.v_stringLength(C.v_stringSlice current(fromIntegral i)(fromIntegral n))))
   assert "exact slice bounds error"(a==b&&case a of Left _->True;_->False)
 putStrLn "PASS 94 Unicode fixtures: every scalar, block-boundary slices, exact bounds errors"
