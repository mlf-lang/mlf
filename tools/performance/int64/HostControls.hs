{-# OPTIONS_GHC -Wno-overflowed-literals #-}
module Main (main) where
import Prelude
import qualified Data.Int as I
import qualified Data.Word as W
import qualified Data.Bits as Bits
import GHC.Float(castDoubleToWord64)
import Control.Exception(try,evaluate,SomeException,throw)
import Control.Monad(forM_,unless)
import qualified MLF.Host.Base as B

check label good = unless good (errorWithoutStackTrace ("FAIL "++label))
values :: [I.Int64]
values = [-64..64] ++ [minBound,minBound+1,minBound+2,maxBound-2,maxBound-1,maxBound,2^62,-(2^62),2^32,-(2^32)]
observe :: I.Int64 -> IO (Either SomeException I.Int64)
observe = try . evaluate
arithmetic = [("add",B.v_addInt,(+)),("sub",B.v_subInt,(-)),("mul",B.v_mulInt,(*)),
              ("and",B.v_andInt,(Bits..&.)),("or",B.v_orInt,(Bits..|.)),("xor",B.v_xorInt,Bits.xor)]
shifts = [("shiftL",B.v_shiftLInt,\x n->Bits.shiftL x (fromIntegral n)),
          ("shiftR",B.v_shiftRInt,\x n->Bits.shiftR x (fromIntegral n)),
          ("unsignedShiftR",B.v_unsignedShiftRInt,\x n->fromIntegral (Bits.shiftR (fromIntegral x::W.Word64) (fromIntegral n)))]
main :: IO ()
main = do
  forM_ values $ \x -> do
    forM_ values $ \y -> do
      forM_ arithmetic $ \(name,f,ref) -> check name (f x y==ref x y)
      check "unsigned comparison" (B.v_unsignedLtInt x y==((fromIntegral x::W.Word64)<fromIntegral y))
      check "signed comparison" (B.v_ltInt x y==(x<y) && B.v_eqInt x y==(x==y))
      forM_ [("quot",B.v_quotInt,quot),("rem",B.v_remInt,rem)] $ \(name,f,ref) -> do
        actual<-observe(f x y);expected<-observe(ref x y)
        case (actual,expected) of
          (Right a,Right e)->check name (a==e)
          (Left _,Left _)->pure ()
          _->check (name++" outcome") False
    forM_ [-1,0,1,31,32,62,63,64,65,127,maxBound] $ \n ->
      forM_ shifts $ \(name,f,ref) -> do
        actual<-observe(f x n);expected<-observe(ref x n)
        case (actual,expected) of
          (Right a,Right e)->check name (a==e)
          (Left _,Left _)->pure ()
          _->check (name++" outcome") False
    check "leading zero count" (B.v_countLeadingZerosInt x==fromIntegral(Bits.countLeadingZeros x))
    check "trailing zero count" (B.v_countTrailingZerosInt x==fromIntegral(Bits.countTrailingZeros x))
    check "population count" (B.v_popCountInt x==fromIntegral(Bits.popCount x))
    check "Int to Integer is sign preserving" (B.v_intToInteger x==toInteger x)
    check "all Double bits" (castDoubleToWord64(B.v_doubleFromBits x)==fromIntegral x)
    check "signed Double bits" (B.v_doubleToBits(B.v_doubleFromBits x)==x)
  forM_ [-(2^1024),-(2^64)-1,-(2^63)-1,-(2^63),-1,0,2^63-1,2^63,2^64-1,2^64,2^1024] $ \n -> do
    check "Integer to Int wraps" (B.v_integerToInt n==(fromInteger n::I.Int64))
    check "decimal read wraps" (B.v_readInt(B.literal(show n))==(read(show n)::I.Int64))
    check "explicit Integer read" (B.v_readInteger(B.literal(show n))==n)
    check "explicit Integer show" (B.unpack(B.v_showInteger n)==show n)
  check "literal wraps" ((9223372036854775808::B.Int)==minBound && (18446744073709551616::B.Int)==0)
  forM_ ["","+","-"," 1","1 ","0x10","1.0","1x"] $ \s -> do
    r<-observe(B.v_readInt(B.literal s));case r of Left _->pure ();_->check "MLF decimal grammar" False
  let left=throw(B.HostError "left");right=throw(B.HostError "right")
  forM_ [("signed",B.v_ltInt),("unsigned",B.v_unsignedLtInt)] $ \(name,f) -> do
    result<-try(evaluate(f left right))::IO(Either B.HostError Bool)
    case result of Left(B.HostError message)->check (name++" comparison demand") (message=="left");_->check name False
  forM_ [(n,f)| (n,f,_)<-arithmetic++shifts] $ \(name,f) -> do
    r<-try(evaluate(f left right))::IO(Either B.HostError I.Int64)
    case r of Left(B.HostError s)->check (name++" demand") (s=="left");_->check name False
  forM_ [("division overflow",B.v_quotInt minBound (-1),"integer division overflow"),
         ("quotient zero",B.v_quotInt 1 0,"integer division by zero"),
         ("remainder zero",B.v_remInt 1 0,"integer division by zero"),
         ("negative shift",B.v_shiftLInt 1 (-1),"integer shift overflow"),
         ("invalid decimal",B.v_readInt(B.literal "1x"),"invalid integer input")] $ \(name,value,message) -> do
    actual<-try(evaluate value)::IO(Either B.HostError I.Int64)
    case actual of Left(B.HostError found)->check name (found==message);_->check name False
  let bigs=[-(2^1024),-(2^63),-1,0,1,2^63,2^1024]::[Integer]
  forM_ bigs $ \x -> forM_ bigs $ \y -> do
    check "Integer addition" (B.v_addInteger x y==x+y)
    check "Integer subtraction" (B.v_subInteger x y==x-y)
    check "Integer multiplication" (B.v_mulInteger x y==x*y)
    check "Integer comparison" (B.v_eqInteger x y==(x==y) && B.v_ltInteger x y==(x<y))
    unless (y==0) $ check "Integer division" (B.v_quotInteger x y==quot x y && B.v_remInteger x y==rem x y)
  putStrLn "PASS Int64 host: 139 values; arithmetic, division, bit operations, shifts, decimal/literal overflow, explicit Integer, Double bits, ordered demand"
