{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Monad (forM_, unless)
import Data.Bits (testBit)
import Data.List (nub, sort)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified Bootstrap.Dependency as D
import qualified Bootstrap.Map as M
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.Types as T
import qualified Bootstrap.Set as S
import qualified MLF.Host.Base as H
import qualified Package.Json as J
import qualified Package.Manifest as P
import qualified Package.Scheduler as Jobs

check label expected actual =
  unless (expected == actual) (error (label ++ ": expected " ++ show expected ++ ", got " ++ show actual))

-- Establish membership independently by mutual reachability. Only the DFS
-- finish order is needed to select the historical order of disjoint SCCs.
reference entries = assemble (reverse finish) Set.empty []
  where
    byName = Map.fromList entries
    roots = Map.keys byName
    row n = sort (nub [d | d <- byName Map.! n, Map.member d byName])
    walk n state@(seen, done)
      | Set.member n seen = state
      | otherwise = let (seen', done') = foldl (flip walk) (Set.insert n seen, done) (row n)
                    in (seen', done' ++ [n])
    finish = snd (foldl (flip walk) (Set.empty, []) roots)
    reaches n = fst (walk n (Set.empty, []))
    assemble [] _ groups = groups
    assemble (n:ns) seen groups
      | Set.member n seen = assemble ns seen groups
      | otherwise = let members = [d | d <- roots, Set.member d (reaches n), Set.member n (reaches d)]
                    in assemble ns (seen <> Set.fromList members) (members:groups)

testGraph entries = check "declaration groups/order" (reference entries)
  (map (map H.unpack) (D.components [(H.literal k, map H.literal deps) | (k, deps) <- entries]))

allGraphs = [[(k, [v | (j,v) <- zip [0..] names, testBit mask (i*3+j)])
             | (i,k) <- zip [0..] names] | mask <- [0..511 :: Int]]
  where names = ["z","a","id900000000000"]

package name deps mods = P.Package (H.literal ("/packages/" ++ name ++ "/mlf-package.json"))
  (J.Object [("name",J.str (H.literal name)),("version",J.str "1.0.0"),
             ("dependencies",J.Object [(H.literal n,J.empty) | n <- deps])]) mods
modl owner name deps = P.Module name owner (H.v_concatString name ".hs") deps

packageChecks = do
  let leaf = package "leaf" [] [modl "leaf" "Leaf" []]
      left = package "left" ["leaf"] [modl "left" "Left" ["Leaf","Leaf"]]
      right = package "right" ["leaf"] [modl "right" "Right" ["Leaf"]]
      root = package "root" ["right","left"]
               [modl "root" "A" ["B","Right"], modl "root" "B" ["A","Left"]]
      pkgs = [leaf,left,right,root]
      mods = concatMap P.packageModules pkgs
      graph = P.buildPackageGraph "root" pkgs mods
      names = map (H.unpack . P.packageName)
  check "namespace cycle, diamond, repeated import" ["Leaf","Left","B","Right","A"]
    (map (H.unpack . P.moduleName) (P.modules graph))
  check "transitive scheduler closure" ["leaf","left","right","root"]
    (names (Jobs.neededPackages graph ["root","left","root"]))
  check "target subset" ["right"] (names (P.targetDependencies graph root (J.Object [("dependencies",J.stringArray ["right"])])))
  let jobs = Jobs.libraryJobs graph root J.empty
  check "stable scheduler job IDs" ["library-prelude-leaf","library-prelude-left","library-prelude-right","library-prelude-root"]
    (map (H.unpack . Jobs.jobId) jobs)
  check "scheduler dependency direction/order" [[],["library-prelude-leaf"],["library-prelude-leaf"],
    ["library-prelude-left","library-prelude-right"]] (map (map H.unpack . J.getStrings "dependencies") jobs)
  let encoded = Jobs.graphJson graph
  check "worker graph roundtrip" (H.unpack (J.render encoded)) (H.unpack (J.render (Jobs.graphJson (Jobs.graphFrom encoded))))
  let user = Modules.Entity "Zed" "value" Modules.Value
      extra = Modules.Entity "Prelude" "freezeSTArray" (Modules.Primitive T.PFreezeSTArray)
      nameOf entities = case Modules.resolvedName (Modules.freshNames [] (S.fromList Modules.compareEntity entities)) user of
        T.Right name -> H.unpack name
        T.Left err -> error (H.unpack err)
  check "appended primitive preserves existing generated name" (nameOf [user]) (nameOf [extra,user])
  let direct = M.fromList H.v_compareString
                 [(H.literal k,S.fromList H.v_compareString (map H.literal ns))
                  | (k,ns) <- [("A",["B","External"]),("B",["A"]),("Alone",[])]]
  check "instance reach including external leaf"
    [("A",["A","B","External"]),("Alone",["Alone"]),("B",["A","B","External"])]
    [(H.unpack k, map H.unpack (S.toList ns)) | (k,ns) <- M.toList (Modules.moduleReach direct)]

main = do
  let chain = [("v" ++ show i,["v" ++ show (i+1)]) | i <- [0..24 :: Int]]
      wide = [("top",map fst chain)] ++ chain
      duplicate = [("z",["a"]),("a",["missing","a","a"]),("z",["other"])]
  forM_ ([]:duplicate:chain:wide:allGraphs) $ \graph -> do
    testGraph graph
    testGraph (reverse graph)
  packageChecks
  putStrLn "1032 ordered SCC comparisons and package/module graph controls passed"
