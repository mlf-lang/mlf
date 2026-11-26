{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Exception (evaluate)
import Data.List (foldl')
import System.CPUTime (getCPUTime)
import System.Environment (getArgs)
import Text.Printf (printf)
import qualified Bootstrap.LLVM.Analysis as A
import qualified Bootstrap.LLVM.Optimize as O
import qualified Bootstrap.Map as M
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as H

name :: H.Int -> T.XName
name i = T.XName i "value"

var :: H.Int -> T.XErased
var = T.XEVar . name

add :: T.XErased -> T.XErased -> T.XErased
add a b = T.XEApp (T.XEApp (T.XEPrimitive T.PAddInt) a) b

balanced :: [T.XErased] -> T.XErased
balanced [] = T.XEInt 0
balanced [x] = x
balanced xs = let (left,right) = splitAt (length xs `div` 2) xs
  in add (balanced left) (balanced right)

shape :: String -> H.Int -> T.XErased
shape family size = case family of
  "demand-balanced" -> balanced (map var [1..size])
  "demand-left" -> foldl add (T.XEInt 0) (map var [1..size])
  "demand-right" -> foldr add (T.XEInt 0) (map var [1..size])
  "demand-alias" -> foldr (\i body -> T.XELet (name (1000000+i))
      (if i == 1 then add (var 1) (var 2) else add (var (999999+i)) (var (999999+i))) body)
    (var (1000000+size)) [1..size]
  "capture-chain" -> T.XELetRec
    [(name i,T.XEAbs (name (1000000+i)) (var (if i == size then -1 else i+1))) | i <- [1..size]]
    (var 1)
  "let-summary" -> foldr (\i body -> T.XELet (name i)
      (T.XEApp (T.XEApp (T.XEPrimitive T.PQuotInt) (if i == 1 then var (-1) else var (i-1))) (T.XEInt 1)) body)
    (var size) [1..size]
  _ -> error "unknown family"

-- Both length and a position-sensitive checksum are forced inside the timed
-- interval. The complete flag is checked too; a shortened prefix cannot win.
digest :: [T.XName] -> (Int, H.Int)
digest = foldl' (\(count,checksum) n -> let next = count+1
  in next `seq` let result = checksum + fromIntegral next * O.nameId n
    in result `seq` (next,result)) (0,0)

summaries :: A.LetDemands -> [T.XName]
summaries (A.LetDemands demand rest) = A.demandNames demand ++ case rest of
  T.Nothing -> []
  T.Just next -> summaries next

run :: String -> H.Int -> (Int, H.Int, Bool)
run family size = case family of
  "capture-chain" -> let entries = M.toList (A.captureFixed (A.collect term))
                         (count,checksum) = digest (concatMap (A.captures . snd) entries)
                     in (count,checksum,True)
  "let-summary" -> let (count,checksum) = digest (summaries (A.letBodyDemands M.empty term))
                   in (count,checksum,True)
  _ -> let demand = A.entryDemand M.empty M.empty term
           (count,checksum) = digest (A.demandNames demand)
       in (count,checksum,A.demandComplete demand)
  where term = shape family size

expected :: String -> H.Int -> (Int, H.Int, Bool)
expected family size = case family of
  "capture-chain" -> (fromIntegral size, fromInteger (negate (n*(n+1) `div` 2)), True)
  "let-summary" -> (fromIntegral size+1, fromInteger (n*(n+1)*(n+2) `div` 3-1), True)
  "demand-alias" -> (2,5,True)
  _ -> (fromIntegral size, fromInteger (n*(n+1)*(2*n+1) `div` 6), True)
  where n = toInteger size

main :: IO ()
main = do
  args <- getArgs
  (family,size) <- case args of
    [family,sizeText] | Just n <- readsPositive sizeText -> pure (family,n)
    _ -> fail "usage: llvm-probe FAMILY POSITIVE_SIZE"
  start <- getCPUTime
  let result@(count,checksum,complete) = run family size
  _ <- evaluate (count `seq` checksum `seq` complete `seq` result)
  end <- getCPUTime
  if result == expected family size then pure () else
    fail ("independent oracle mismatch: " ++ show result ++ ", expected " ++ show (expected family size))
  printf "{\"family\":%s,\"size\":%d,\"count\":%d,\"checksum\":%d,\"complete\":%s,\"cpu_seconds\":%.9f}\n"
    (show family) size count checksum (if complete then "true" else "false" :: String)
    (fromIntegral (end-start) / 1e12 :: Double)
  where
    readsPositive s = case reads s of
      [(n,"")] | n > 0 -> Just n
      _ -> Nothing
