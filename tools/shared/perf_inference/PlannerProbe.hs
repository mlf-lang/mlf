{-# LANGUAGE OverloadedStrings #-}
module Main where
import qualified MLF.Host.Base as B
import MLF.Host.IO (runEntry)
import qualified Bootstrap.Types as T
import qualified Bootstrap.ClassDemand as Q
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import GHC.Clock (getMonotonicTimeNSec)
import System.CPUTime (getCPUTime)
import System.Environment (getArgs)
import qualified Control.Exception as E
import Data.List (foldl')
import Data.Char (ord)
frame i p f = Q.Frame i p f
origin (Q.SeedOrigin n) = "S" ++ show n
origin (Q.InstantiatedOrigin u n) = "I" ++ show (u,n)
slot (Q.Slot n c o r) = show (n,B.unpack c,o,origin r)
serialize (T.Left e) = "ERROR " ++ B.unpack e
serialize (T.Right (Q.Plan (Q.Universe slots seeds transitions) values updates)) =
  show (map (\(k,s)->(k,slot s)) (IM.toAscList slots), IM.toAscList seeds,
        map (\(k,m)->(k,IM.toAscList m)) (IM.toAscList transitions),
        map (\(k,s)->(k,IS.toAscList s)) (IM.toAscList values),updates)
inputs kind n =
 let frames = [frame 0 T.Nothing 2,frame 1 (T.Just 0) 1]
     uses = [Q.Use 0 1 0]
     demand i = case i `mod` 4 of
       0 -> Q.Empty
       1 -> Q.RefNode ((i+1) `mod` n)
       2 -> Q.UnionNodes [((i+1) `mod` n),((i+2) `mod` n)]
       _ -> Q.InstantiateNode 0 ((i+1) `mod` n)
     nodes = IM.fromList [(i,demand i) | i <- [0..n-1]]
 in case kind of
  "empty" -> (frames,[],uses,nodes)
  "seed" -> (frames,[Q.Seed 0 "Inspect" 1],uses,IM.fromList [(0,Q.SeedNode 0),(1,Q.InstantiateNode 0 0),(2,Q.UnionNodes [0,1]),(3,Q.RefNode 2)])
  "dup-frame" -> (frames ++ [frame 0 T.Nothing 2],[],uses,nodes)
  "dup-seed" -> (frames,[Q.Seed 0 "C" 0,Q.Seed 0 "C" 0],uses,nodes)
  "dup-use" -> (frames,[],uses++uses,nodes)
  "dup-rank" -> ([frame 0 T.Nothing 2,frame 1 (T.Just 0) 2],[],uses,nodes)
  "bad-frame" -> ([frame 0 (T.Just 8) 2],[],[],nodes)
  "bad-seed-owner" -> (frames,[Q.Seed 0 "C" 9],uses,nodes)
  "bad-use" -> (frames,[],[Q.Use 0 0 1],nodes)
  "bad-dependency" -> (frames,[],uses,IM.singleton 0 (Q.RefNode 999999))
  "bad-seed" -> (frames,[],uses,IM.singleton 0 (Q.SeedNode 0))
  "bad-node-use" -> (frames,[],[],IM.singleton 0 (Q.InstantiateNode 0 0))
  "negative-node" -> (frames,[],uses,IM.singleton (-1) Q.Empty)
  _ -> error "unknown case"
main = runEntry $ do
 args <- getArgs
 case args of
  [kind,size,mode] -> do
   let (frames,seeds,uses,nodes) = inputs kind (read size)
   startWall <- getMonotonicTimeNSec
   startCPU <- getCPUTime
   let output = serialize (Q.solve frames seeds uses nodes)
   checksum <- E.evaluate (foldl' (\acc c -> acc + ord c) (0 :: Int) output)
   size <- E.evaluate (length output)
   -- Strict checksum forces every character of the exact Plan serialization.
   -- This bundle includes lazy fixture construction, solve, and serialization.
   endCPU <- getCPUTime
   endWall <- getMonotonicTimeNSec
   if mode == "dump" then putStrLn output else putStrLn ("serialized_chars=" ++ show size ++ " checksum=" ++ show checksum)
   putStrLn ("wall_ns=" ++ show (endWall-startWall) ++ " cpu_ps=" ++ show (endCPU-startCPU))
  _ -> error "usage: planner CASE SIZE dump|time"
