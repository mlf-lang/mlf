{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
-- Supplementary controls ONLY. Production C4 and all previous oracle modules
-- remain byte-identical. Fixed matrix; no candidate-guided selection or retry.
module Main where
import Prelude
import Control.Monad (forM, forM_)
import Data.List (nub, sort)
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified FrozenGraph as FG
import qualified FrozenSolver as FS
import qualified SessionGraftFixtures as A
import qualified SessionOracle as O
import qualified C4Fixtures as F
import qualified C4TransactionControls as C

layoutNames :: [String]
layoutNames = ["reverse", "rotate-one", "odd-even", "outside-in"]
coordinates :: [(String,Integer,Integer)]
coordinates = [("dense",0,1),("sparse",-9001,100003),("huge-negative",negate (10^40),7)]

permutation :: String -> Integer -> [Integer]
permutation name n = case name of
  "reverse" -> reverse [0..n-1]
  "rotate-one" -> [1..n-1] ++ [0]
  "odd-even" -> [1,3..n-1] ++ [0,2..n-1]
  "outside-in" -> [if even i then n-1-(i `div` 2) else i `div` 2 | i <- [0..n-1]]
  _ -> errorWithoutStackTrace "unplanned permutation"

identities :: T.Graph -> Integer -> Integer -> [Integer]
identities g source target = sort (nub
  ([source,target] ++ map fst (IM.toList (FG.nodes g)) ++
   concat [[a,b] | (a,b) <- IM.toList (FG.links g)] ++
   concat [O.nodeChildren value ++ O.nodeBinder value | (_,value) <- IM.toList (FG.nodes g)]))

variant :: Int -> String -> (String,Integer,Integer) -> F.Fixture -> IO (Bool,Bool,Integer,Integer)
variant serial layout (coordinate,offset,stride) (F.Fixture label g source target admitted success _) = do
  let domain = identities g source target
      n = toInteger (length domain)
      ranks = permutation layout n
      next = offset + stride*n
      mapping = zip domain [offset + stride*r | r <- ranks]
      image old | old==FG.nextId g = next
                | otherwise = case lookup old mapping of
                    Just value -> value
                    Nothing -> errorWithoutStackTrace "incomplete independently enumerated identity domain"
      renamed = A.rename image g
      name = "heteroinput/" ++ show serial ++ "/" ++ layout ++ "/" ++ coordinate ++ "/" ++ label
  putStrLn ("CASE-BEGIN " ++ name)
  O.assert (name++" valid old domain has no allocation counter") (n>1 && FG.nextId g `notElem` domain)
  O.assert (name++" explicit total rank permutation") (sort ranks==[0..n-1])
  O.assert (name++" genuinely nonmonotone old order") (not (and (zipWith (<) ranks (drop 1 ranks))))
  O.assert (name++" all old identities below new first; positive stride")
    (stride>0 && all ((<next).snd) mapping && FG.nextId renamed==next)
  O.assert (name++" original numeric key mapping has no collisions") (length (nub (map snd mapping))==length domain)
  -- Frozen preparation/expansion before any candidate operation makes input
  -- validity and the allocation-root position independent of C4 classification.
  old <- O.right (name++" complete frozen valid prepared input") (FS.prepare renamed)
  (root,_,frontier,expanded) <- O.right (name++" complete frozen expansion")
    (FS.expanded (image source) (image target) old)
  let count=FG.nextId (FS.graph expanded)-next
      rootPosition=root-next
  O.assert (name++" copied root is in fresh allocation range") (rootPosition>=0 && rootPosition<count)
  putStrLn ("FROZEN-SPEC " ++ show (serial,label,layout,coordinate,n,next,count,rootPosition,length frontier,admitted,success))
  -- This unchanged helper compares against COMPLETE Frozen P3, including exact
  -- per-variant first errors, physical projection/Graph, aliases/scopes/counter,
  -- all reverse indexes, immutable retries and both actual prepared drivers.
  -- Authored success/admission flags are assertions, not candidate-derived data.
  C.fixture (F.Fixture name renamed (image source) (image target) admitted success Nothing)
  putStrLn ("CASE-PASS " ++ name)
  pure (admitted,success,rootPosition,count)

main :: IO ()
main = do
  let base=F.fixtures ++ F.additionalFixtures
      specs=[(layout,coordinate,f) | f<-base,layout<-layoutNames,coordinate<-coordinates]
  O.assert "fixed 18 authored fixtures" (length base==18)
  O.assert "fixed 4x3x18 matrix" (length specs==216)
  rows <- forM (zip [1::Int ..] specs) $ \(serial,(layout,coordinate,f)) -> variant serial layout coordinate f
  let count f=length(filter f rows)
      admitted=count(\(a,_,_,_)->a)
      successful=count(\(_,s,_,_)->s)
      rootFirst=count(\(_,_,p,_)->p==0)
      rootMiddle=count(\(_,_,p,n)->p>0&&p<n-1)
      rootLast=count(\(_,_,p,n)->n>1&&p==n-1)
      admittedFirst=count(\(a,_,p,_)->a&&p==0)
      admittedMiddle=count(\(a,_,p,n)->a&&p>0&&p<n-1)
      admittedLast=count(\(a,_,p,n)->a&&n>1&&p==n-1)
  O.assert "fixed 156 admitted and 60 old-route controls" (admitted==156)
  O.assert "fixed 156 success and 60 rejection controls" (successful==156)
  O.assert "nonvacuous root first/middle/last coverage" (rootFirst>0 && rootMiddle>0 && rootLast>0)
  O.assert "nonvacuous ADMITTED root first/middle/last coverage"
    (admittedFirst>0 && admittedMiddle>0 && admittedLast>0)
  putStrLn "PASS fixed 216 nonmonotone identity variants with complete Frozen P3 and unchanged transaction oracle"
  putStrLn ("{\"complete\":true,\"cases\":216,\"admitted\":"++show admitted++
    ",\"successes\":"++show successful++",\"rejections\":"++show(216-successful)++
    ",\"root_first\":"++show rootFirst++",\"root_middle\":"++show rootMiddle++
    ",\"root_last\":"++show rootLast++",\"admitted_root_first\":"++show admittedFirst++
    ",\"admitted_root_middle\":"++show admittedMiddle++",\"admitted_root_last\":"++show admittedLast++
    ",\"candidate_selected_inputs\":false,\"ordinary_timing_samples_added\":0}")
