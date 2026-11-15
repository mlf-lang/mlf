{-# LANGUAGE OverloadedStrings #-}
-- Frozen host arithmetic is compiled without rewrite rules or unfoldings.
module Main where
import Prelude
import Control.Exception
import Control.Monad
import Data.IORef
import Data.List (isInfixOf)
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as C
import qualified LegacyBase as L
import qualified Data.Bits as Bits

need label ok = unless ok (fail label)
observe x = do
 r <- try (evaluate x) :: IO (Either SomeException P.Int)
 pure (either (Left . displayException) Right r)
first :: P.Int
first = C.failure "first operand"
{-# NOINLINE first #-}
second :: P.Int
second = C.failure "second operand"
{-# NOINLINE second #-}
cases :: [(P.Int,[P.Int -> P.Int],P.Int -> P.Int)]
cases = [
 (0,[\x -> P.seq x 0, \x -> P.quotInt x 0, \x -> P.remInt x 0, \x -> P.addInt x 0, \x -> P.mulInt x 0],\x -> P.ifThenElse (P.eqInt (P.seq x 0) 0) (C.failure "later branch") 0),
 (1,[\x -> P.seq x 1, \x -> P.quotInt x 1, \x -> P.remInt x 1, \x -> P.addInt x 1, \x -> P.mulInt x 1],\x -> P.ifThenElse (P.eqInt (P.seq x 1) 1) (C.failure "later branch") 0),
 (2,[\x -> P.seq x 2, \x -> P.quotInt x 2, \x -> P.remInt x 2, \x -> P.addInt x 2, \x -> P.mulInt x 2],\x -> P.ifThenElse (P.eqInt (P.seq x 2) 2) (C.failure "later branch") 0),
 (8,[\x -> P.seq x 8, \x -> P.quotInt x 8, \x -> P.remInt x 8, \x -> P.addInt x 8, \x -> P.mulInt x 8],\x -> P.ifThenElse (P.eqInt (P.seq x 8) 8) (C.failure "later branch") 0),
 (24,[\x -> P.seq x 24, \x -> P.quotInt x 24, \x -> P.remInt x 24, \x -> P.addInt x 24, \x -> P.mulInt x 24],\x -> P.ifThenElse (P.eqInt (P.seq x 24) 24) (C.failure "later branch") 0),
 (512,[\x -> P.seq x 512, \x -> P.quotInt x 512, \x -> P.remInt x 512, \x -> P.addInt x 512, \x -> P.mulInt x 512],\x -> P.ifThenElse (P.eqInt (P.seq x 512) 512) (C.failure "later branch") 0),
 (768,[\x -> P.seq x 768, \x -> P.quotInt x 768, \x -> P.remInt x 768, \x -> P.addInt x 768, \x -> P.mulInt x 768],\x -> P.ifThenElse (P.eqInt (P.seq x 768) 768) (C.failure "later branch") 0),
 (64,[\x -> P.seq x 64, \x -> P.quotInt x 64, \x -> P.remInt x 64, \x -> P.addInt x 64, \x -> P.mulInt x 64],\x -> P.ifThenElse (P.eqInt (P.seq x 64) 64) (C.failure "later branch") 0),
 (255,[\x -> P.seq x 255, \x -> P.quotInt x 255, \x -> P.remInt x 255, \x -> P.addInt x 255, \x -> P.mulInt x 255],\x -> P.ifThenElse (P.eqInt (P.seq x 255) 255) (C.failure "later branch") 0),
 (2147483647,[\x -> P.seq x 2147483647, \x -> P.quotInt x 2147483647, \x -> P.remInt x 2147483647, \x -> P.addInt x 2147483647, \x -> P.mulInt x 2147483647],\x -> P.ifThenElse (P.eqInt (P.seq x 2147483647) 2147483647) (C.failure "later branch") 0),
 (1099511628211,[\x -> P.seq x 1099511628211, \x -> P.quotInt x 1099511628211, \x -> P.remInt x 1099511628211, \x -> P.addInt x 1099511628211, \x -> P.mulInt x 1099511628211],\x -> P.ifThenElse (P.eqInt (P.seq x 1099511628211) 1099511628211) (C.failure "later branch") 0)]
bitControls = do
 let values = [minBound,minBound+1,-65537,-1,0,1,7,255,256,65537,maxBound] :: [P.Int]
     amounts = [-1,0,1,4,7,8,16,31,32,63,64,65,maxBound] :: [P.Int]
     operations = [(P.andInt,L.v_andInt),(P.orInt,L.v_orInt),(P.xorInt,L.v_xorInt),
                   (P.shiftLInt,L.v_shiftLInt),(P.shiftRInt,L.v_shiftRInt),
                   (P.unsignedShiftRInt,L.v_unsignedShiftRInt)]
 forM_ operations $ \(actual,original) ->
  forM_ values $ \value -> forM_ (values++amounts) $ \amount -> do
   wanted <- observe (original value amount)
   got <- observe (actual value amount)
   need "bit operations preserve frozen values and errors" (wanted==got)
 forM_ values $ \value -> do
  let integer=toInteger value; unsigned=integer `mod` (2^64)
  forM_ values $ \other -> do
   need "and agrees with unbounded-integer oracle" (P.andInt value other==fromInteger (integer Bits..&. toInteger other))
   need "or agrees with unbounded-integer oracle" (P.orInt value other==fromInteger (integer Bits..|. toInteger other))
   need "xor agrees with unbounded-integer oracle" (P.xorInt value other==fromInteger (Bits.xor integer (toInteger other)))
  forM_ (filter (>=0) amounts) $ \amount -> do
   let power=2^amount
       left=if amount>=64 then 0 else fromInteger (integer*power)
       right=if amount>=64 then if value<0 then -1 else 0 else fromInteger (integer `div` power)
       logical=if amount>=64 then 0 else fromInteger (unsigned `div` power)
   need "left shift agrees with integer ring" (P.shiftLInt value amount==left)
   need "right shift agrees with integer quotient" (P.shiftRInt value amount==right)
   need "logical shift agrees with unsigned quotient" (P.unsignedShiftRInt value amount==logical)
 -- Literal call sites exercise simplification after the new INLINE boundary.
 forM_ [\x->P.shiftLInt x (-1),\x->P.shiftRInt x 0,\x->P.unsignedShiftRInt x 8,
        \x->P.shiftLInt x 64,\x->P.shiftRInt x 255] $ \actual -> do
  got <- observe (actual first)
  need "literal shifts preserve left operand priority" (case got of Left e->isInfixOf "first operand" e;_->False)
main = do
 bitControls
 forM_ cases $ \(constant,functions,branch) -> do
  let originals = [\x -> L.v_seq x constant, \x -> L.v_quotInt x constant,
        \x -> L.v_remInt x constant, \x -> L.v_addInt x constant, \x -> L.v_mulInt x constant]
  forM_ (zip functions originals) $ \(actual,original) -> do
   forM_ [minBound,minBound+1,-65537,-8,-1,0,1,7,8,65537,maxBound] $ \value -> do
    wanted <- observe (original value)
    got <- observe (actual value)
    need "exact frozen arithmetic and failures" (wanted == got)
   got <- observe (actual first)
   need "left operand precedes a total literal and zero division" (case got of Left e -> isInfixOf "first operand" e; _ -> False)
  got <- observe (branch first)
  need "literal result cannot discard condition demand" (case got of Left e -> isInfixOf "first operand" e; _ -> False)
 forM_ [P.addInt,P.subInt,P.mulInt,P.quotInt,P.remInt,P.andInt,P.orInt,P.xorInt,P.shiftLInt,P.shiftRInt,P.unsignedShiftRInt] $ \operation -> do
  got <- observe (operation first second)
  need "unknown operands retain left-before-right order" (case got of Left e -> isInfixOf "first operand" e; _ -> False)
 forM_ [P.quotInt,P.remInt] $ \operation -> do
  got <- observe (operation first 0)
  need "variable call retains zero error priority" (case got of Left e -> isInfixOf "first operand" e; _ -> False)
 ref <- newIORef False
 let action = P.ioReturn (P.seq first 1)
 action >> writeIORef ref True
 readIORef ref >>= need "unused IO result remains lazy"
 got <- try (action >>= evaluate) :: IO (Either SomeException P.Int)
 need "reused IO action still demands its result" (case got of Left e -> isInfixOf "first operand" (displayException e); _ -> False)
 putStrLn "PASS literal arithmetic, frozen errors, nested demand and lazy IO results"
