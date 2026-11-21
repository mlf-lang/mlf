{-# LANGUAGE OverloadedStrings #-}
module Main where

import Prelude
import Control.Monad (forM_, unless)
import Data.Int (Int64)
import Data.List (subsequences)
import qualified Data.Set as Set
import qualified Data.Map.Lazy as Map
import qualified Bootstrap.Map as M
import qualified Bootstrap.Classes as C
import qualified Bootstrap.IntSet as I
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as B

render (role, name) = (case role of
  T.InstanceEvidence -> "instance"
  T.SuperclassEvidence -> "superclass"
  T.GivenEvidence -> "given", B.unpack name)

check names indices supers = do
  let wanted = Set.fromList indices
      expected = [("instance", n) | (i, n) <- zip [0 :: Int64 ..] names, Set.member i wanted]
        ++ map render supers
      actual = map render (C.selectCandidates (map B.literal names) supers (I.fromList indices))
  unless (actual == expected) (fail "candidate ordinal/order/multiplicity mismatch")

namedMain = do
  let supers = [(T.SuperclassEvidence, "super"), (T.GivenEvidence, "given"),
                (T.InstanceEvidence, "n0"), (T.InstanceEvidence, "n0")]
      cases = [(n, indices) | n <- [0..8], indices <- subsequences [-1..fromIntegral n]]
  forM_ cases $ \(n, indices) ->
    forM_ [map (\i -> "n" ++ show i) [0..n-1], replicate n "repeat"] $ \names ->
      forM_ [[], supers] $ \tail -> check names indices tail
  forM_ [1,63,64,65,127,128,255,256,257,1024,4096,65536,131072] $ \n ->
    forM_ [[], [minBound, -1, maxBound], [0, fromIntegral n - 1],
            [fromIntegral n, fromIntegral n + 1], [0,0,1,1,63,64,65],
            [0,7..fromIntegral n-1]] $ \indices ->
      check (map (\i -> "n" ++ show (i `mod` 7)) [0..n-1]) indices supers
  unless (map render (C.selectCandidates [error "unselected", "selected"] [] (I.singleton 1))
    == [("instance", "selected")]) (fail "unselected name forced")
  unless (map render (C.selectCandidates [] supers (error "unused indices")) == map render supers)
    (fail "empty inventory forced indices")
  putStrLn ("PASS candidate selection: " ++ show (length cases * 4 + 78) ++ " cases and 2 demand checks")

role T.InstanceEvidence = "instance"
role T.SuperclassEvidence = "superclass"
role T.GivenEvidence = "given"

checkIds names supers indices = do
  let global = [(T.InstanceEvidence, name) | name <- names] ++ supers
      entries = [(name, (r, i)) | ((r, name), i) <- zip global [100 :: Int64 ..]]
      expectedByName = Map.fromList [(name, (role r, i)) | (name, (r, i)) <- entries]
      actualByName = M.fromList B.v_compareString
        [(B.literal name, (r, i)) | (name, (r, i)) <- entries]
      resolve name = M.get B.v_compareString (B.literal name) actualByName
      chosen = Set.fromList indices
      wantedNames = [name | (i, name) <- zip [0 :: Int64 ..] names, Set.member i chosen]
        ++ map snd supers
      expected = map (expectedByName Map.!) wantedNames
      select = C.selectCandidateValues (map resolve names) (map (resolve . snd) supers)
      actual = [(role r, i) | (r, i) <- select (I.fromList indices)]
  unless (actual == expected) (fail "candidate ID order, multiplicity or last-role mapping differs")

idMain = do
  let tails = [[], [(T.SuperclassEvidence, "super"), (T.GivenEvidence, "given")],
               [(T.SuperclassEvidence, "n0"), (T.GivenEvidence, "n0"),
                (T.InstanceEvidence, "n1"), (T.GivenEvidence, "n0")]]
      cases = [(n, indices) | n <- [0..8], indices <- subsequences [-1..fromIntegral n]]
  forM_ cases $ \(n, indices) ->
    forM_ [map (\i -> "n" ++ show i) [0..n-1],
           map (\i -> "n" ++ show (i `mod` 3)) [0..n-1]] $ \names ->
      forM_ tails $ \tail -> checkIds names tail indices
  let sizes = [1,63,64,65,127,128,255,256,257,1024,4096,65536,131072]
  forM_ sizes $ \n ->
    forM_ [[], [minBound, -1, maxBound], [0, fromIntegral n-1],
           [fromIntegral n, fromIntegral n+1], [0,0,1,1,63,64,65],
           [0,7..fromIntegral n-1], [0..fromIntegral n-1],
           minBound : ([0..fromIntegral n-1] ++ [maxBound])] $ \indices ->
      checkIds (map (\i -> "n" ++ show (i `mod` 7)) [0..n-1]) (last tails) indices
  checkIds ["", "λ", "a\0b", "λ", "n0"] [(T.GivenEvidence, "λ")] [-1..6]
  unless (C.selectCandidateValues ([] :: [Int]) [7] (error "unused indices") == [7])
    (fail "empty inventory forces indices")
  unless (C.selectCandidateValues [error "unselected", 3 :: Int] [7] (I.singleton 1) == [3,7])
    (fail "unselected candidate is forced")
  unless (take 1 (C.selectCandidateValues [3 :: Int] (error "unused tail") (I.singleton 0)) == [3])
    (fail "selected prefix forces superclass tail")
  unless (C.selectCandidateValues [error "first", error "second" :: Int] [7] I.empty == [7])
    (fail "empty selection forces candidate values")
  unless (C.selectCandidateValues [error "first", error "second" :: Int] [7]
          (I.fromList [-1,2,maxBound]) == [7])
    (fail "out-of-range ordinals force candidate values")
  putStrLn ("PASS candidate IDs: " ++ show (length cases * 6 + length sizes * 8 + 1)
            ++ " cases and 5 demand checks")

main :: IO ()
main = namedMain >> idMain
