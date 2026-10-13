-- Independent expected values come from the maintained Haskell seed graph.
-- To model a nonempty initial visited set, erase the children of its nodes,
-- take the seed's structural postorder, then omit those blocked nodes.
-- This avoids reproducing either MLF accumulator implementation.
module Main where
import Control.Monad (forM_, unless)
import Data.List (intercalate)
import qualified Data.IntMap.Strict as IM
import qualified Data.IntSet as IS
import qualified Data.Set as Set
import qualified MLF.Graph as G
import MLF.Kind (Kind(..))
import MLF.Syntax (Flag(..))

graphFor :: Int -> G.Graph
graphFor seed = G.Graph (IM.fromList [(n,G.Node (G.Con "T" (edges n)) Nothing Flexible) | n <- [0..6]])
  (IM.fromList (concat [[(n+100,n),(n+200,n+100)] | n <- [0..6]])) 300
  where edges n = concat [if (n*13 + m*17 + seed*(n+1)) `rem` 97 < 29
                          then [if (m+seed) `rem` 3 == 0 then m+200 else m] ++ [m | (n+m+seed) `rem` 5 == 0]
                          else [] | m <- [0..6]]

preseen :: Int -> Int -> [Int]
preseen mode root = case mode of
  0 -> []; 1 -> [root]; 2 -> [0,3,6]; 3 -> [103,999]; 4 -> [0..6]; _ -> [100..106] ++ [200..206]

showIds :: [Integer] -> String
showIds = intercalate "," . map show

checkGraph :: Int -> Int -> (Integer -> Integer) -> IO ()
checkGraph seed transform move = do
  let graph = graphFor seed
  forM_ ([0..6] ++ [100..106] ++ [200..206]) $ \root ->
    forM_ [0..5] $ \state -> forM_ [0..1] $ \prefixMode -> do
      let initial = IS.fromList (preseen state root)
          blocked = graph { G.nodes = IM.mapWithKey (\n value -> if IS.member n initial then value { G.tag = G.Bot } else value) (G.nodes graph) }
          order = filter (`IS.notMember` initial) (G.orderedBelow blocked root)
          seen = IS.union initial (IS.fromList order)
          prefix = if prefixMode == 0 then [] else [999,0,999]
          moveIds = map (move . toInteger)
          renamedSeen = Set.toAscList (Set.fromList (moveIds (IS.toList seen)))
      unless (length order == IS.size (IS.fromList order)) (fail "seed repeated a structural node")
      putStrLn (intercalate "/" (map show [seed,transform,root,state,prefixMode]) ++ "|" ++ showIds renamedSeen ++ "|" ++ showIds (moveIds (prefix ++ order)))

main :: IO ()
main = do
  -- This sentinel follows the separately executed MLF old/new demand checks;
  -- complete expected rows below are independently calculated by G.orderedBelow.
  putStrLn "ordered traversal demand: ok"
  let handGraph = G.Graph (IM.fromList
        [(0,G.Node (G.Arr 1 2) Nothing Flexible),(1,G.Node (G.TyApp 4 3) Nothing Flexible)
        ,(2,G.Node (G.Gen 4) Nothing Flexible),(3,G.Node G.Bot Nothing Flexible)
        ,(4,G.Node (G.Con "Cycle" [0,5,5]) Nothing Flexible),(5,G.Node (G.TyCon "K" Star) Nothing Flexible)]) IM.empty 6
  unless (G.orderedBelow handGraph 0 == [5,4,3,1,2,0]) (fail "seed mixed-tag order changed")
  putStrLn "mixed-tag order: 5,4,3,1,2,0"
  forM_ [0..15] $ \seed -> checkGraph seed 0 (\n -> n*11-29)
  let huge = 10^(30::Int)
  checkGraph 7 1 (huge+)
  checkGraph 12 2 (subtract huge)
  checkGraph 9 3 (huge-)
