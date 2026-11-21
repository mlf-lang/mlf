{-# LANGUAGE ScopedTypeVariables #-}
module Main where
import Prelude
import qualified Data.Bits as Bits
import qualified Control.Exception as E
import Control.Monad (forM_, unless)
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P

need label ok = unless ok (fail label)
fails label wanted value = do
  result <- E.try (E.evaluate value)
  case result of
    Left (B.HostError message) -> need label (message == wanted)
    Right _ -> fail (label ++ ": missing exception")

-- Keep the inputs opaque until invocation. The nested operations themselves
-- are visible to the optimizer, including computations which may fail.
opaque :: a -> a
opaque x = x
{-# NOINLINE opaque #-}
bad :: String -> P.Int
bad = B.failure
{-# NOINLINE bad #-}

main = do
  let values = [minBound,minBound+1,-257,-1,0,1,7,128,255,256,maxBound-1,maxBound] :: [P.Int]
      arithmetic = [("add",P.addInt,(+)),("subtract",P.subInt,(-)),
        ("multiply",P.mulInt,(*)),("and",P.andInt,(Bits..&.)),
        ("or",P.orInt,(Bits..|.)),("xor",P.xorInt,Bits.xor)]
  forM_ arithmetic $ \(name,operation,reference) -> do
    forM_ values $ \a -> forM_ values $ \b ->
      need (name ++ " wrapping result") (operation (opaque a) (opaque b) == reference a b)
    fails (name ++ " left operand first") "left" (operation (bad "left") (bad "right"))
    fails (name ++ " right operand demanded") "right" (operation (opaque 0) (bad "right"))
  forM_ values $ \n -> do
    let x = opaque n
    need "nested machine arithmetic" (P.addInt (P.mulInt x 257) (P.subInt x 131) == x*257+x-131)
    fails "outer left precedes nested division" "left"
      (P.addInt (bad "left") (P.quotInt x (opaque 0)))
    fails "outer left precedes nested shift" "left"
      (P.xorInt (bad "left") (P.shiftLInt x (opaque (-1))))
    fails "seq precedes computed integer" "first"
      (P.seq (bad "first") (P.addInt (bad "second") x))
    fails "seq precedes partial quotient" "first"
      (P.seq (bad "first") (P.quotInt x (opaque 0)))
    fails "computed left precedes right" "left"
      (P.mulInt (P.addInt (bad "left") x) (bad "right"))
    need "unused branch remains lazy" (P.ifThenElse True x (P.quotInt x (opaque 0)) == x)
    forM_ [0,1,7,8,31,32,63,64,65] $ \amount -> do
      need "left shift boundary" (P.shiftLInt x (opaque amount) ==
        if amount >= 64 then 0 else Bits.shiftL x (fromIntegral amount))
      need "signed shift boundary" (P.shiftRInt x (opaque amount) ==
        if amount >= 64 then if x < 0 then -1 else 0 else Bits.shiftR x (fromIntegral amount))
  fails "division left before zero check" "left" (P.quotInt (bad "left") (opaque 0))
  fails "shift left before negative check" "left" (P.shiftLInt (bad "left") (opaque (-1)))
  fails "comparison left-first" "left" (P.ltInt (bad "left") (bad "right"))
  fails "reversed comparison right-first" "right" ((P.<=) (bad "left") (bad "right"))
  fails "division zero diagnostic" "integer division by zero" (P.quotInt (opaque 1) (opaque 0))
  fails "division overflow diagnostic" "integer division overflow" (P.quotInt (opaque minBound) (opaque (-1)))
  putStrLn "PASS integer results, nested demand order, shift bounds and lazy branches"
