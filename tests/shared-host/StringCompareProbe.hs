{-# LANGUAGE OverloadedStrings #-}
module Main where

import Prelude
import Control.Exception (evaluate, try)
import Control.Monad (forM_, unless)
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P

need label actual wanted =
  unless (actual == wanted) (fail (label ++ ": " ++ show actual ++ " /= " ++ show wanted))

opaque :: a -> a
opaque value = value
{-# NOINLINE opaque #-}

bad :: String -> B.String
bad = B.failure
{-# NOINLINE bad #-}

fails label message value = do
  result <- try (evaluate value)
  case result of
    Left (B.HostError actual) -> need label actual message
    Right _ -> fail (label ++ ": missing exception")

sign :: Ordering -> P.Int
sign LT = -1
sign EQ = 0
sign GT = 1

main = do
  let suffixes = ["", "a", "b", "ab", "abc", "\0", "a\0b", "é", "α", "中", "😀", "\x10ffff"]
      strings = suffixes ++
        [replicate n 'x' ++ suffix | n <- [1, 2, 7, 63, 255, 256, 257, 1024], suffix <- suffixes]
      pairs = [(a,b) | a <- strings, b <- strings]
      engines = [("host", B.v_compareString), ("primitive", P.compareString)]
  forM_ engines $ \(engine, operation) -> do
    forM_ (zip [0 :: Int ..] pairs) $ \(i,(a,b)) ->
      need (engine ++ " codepoint order " ++ show i)
        (operation (opaque (B.literal a)) (opaque (B.literal b))) (sign (compare a b))
    fails (engine ++ " left before right") "left"
      (operation (bad "left") (bad "right"))
    fails (engine ++ " right demanded") "right"
      (operation (opaque "") (bad "right"))
    fails (engine ++ " left validation before right") "invalid Unicode scalar"
      (operation (B.literal (opaque ['\xd800'])) (bad "right"))
    fails (engine ++ " right validation") "invalid Unicode scalar"
      (operation (opaque "") (B.literal (opaque ['\xdfff'])))
    fails (engine ++ " left constructor before right") "left-tail"
      (operation (B.literal ('a':B.failure "left-tail")) (bad "right"))
    fails (engine ++ " outer demand before comparison") "outer"
      (P.seq (bad "outer") (operation (bad "left") (bad "right")))
    need (engine ++ " partial application stays lazy")
      (P.seq (operation (bad "left")) (7 :: P.Int)) 7
    need (engine ++ " unused branch stays lazy")
      (P.ifThenElse True (7 :: P.Int) (operation (bad "left") (bad "right"))) 7
  putStrLn ("PASS string comparison: " ++ show (length pairs) ++
    " codepoint pairs and 8 demand/error controls per host/primitive lane")
