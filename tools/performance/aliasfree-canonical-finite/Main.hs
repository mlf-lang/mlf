{-# LANGUAGE OverloadedStrings, DeriveDataTypeable #-}
module Main where
import Prelude
import System.Environment (getArgs)
import Control.Exception (Exception, evaluate, throw, try)
import Data.Typeable (Typeable)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as G
import qualified Bootstrap.IntMap as IM
import qualified Prototype.AliasFreeCanonical as C

data Probe = Probe String deriving (Show,Typeable)
instance Exception Probe
node t b = T.Node t b T.Flexible
root n = node (T.GGen n) T.Nothing
bot b = node T.GBot (T.Just b)
{-# NOINLINE fresh #-}
fresh :: Int -> a -> a
fresh salt x = seq salt x
graph salt ns ls next =
  T.Graph (IM.fromDistinctAscList [(fresh salt n,fresh salt v) | (n,v)<-ns])
          (IM.fromDistinctAscList [(fresh salt n,fresh salt v) | (n,v)<-ls])
          (fresh salt next)
{-# NOINLINE factory #-}
factory :: Int -> Int -> T.Graph
factory which salt = seq salt (case which of
  0 -> graph salt [(0,root 1),(1,bot 0)] [] 2
  1 -> graph salt [(0,root 1),(1,node (T.GArr 2 3) (T.Just 0)),(2,bot 1),
              (3,node (T.GArr 2 2) (T.Just 0))] [] 4
  2 -> graph salt [(0,root 1),(1,node (T.GArr 2 3) (T.Just 0)),
              (2,node (T.GGen 4) (T.Just 0)),
              (3,node (T.GBotK (throw (Probe "late-kind"))) (T.Just 0)),(4,bot 2)] [] 5
  3 -> graph salt [(0,root 1),(1,node (T.GBotK (throw (Probe "unused-kind"))) (T.Just 0))] [] 2
  4 -> graph salt [(0,root 1),(1,node (T.GTyCon (throw (Probe "unused-name")) T.Star) (T.Just 0))] [] 2
  5 -> graph salt [(0,root 1),(1,bot 0)] [] (throw (Probe "unused-next"))
  6 -> graph salt [(0,root 1),(1,node (T.GArr 2 3) (T.Just 0)),
              (2,node (T.GBotK (throw (Probe "forced-kind"))) (T.Just 0)),(3,bot 0)] [] 4
  7 -> graph salt [(0,root 0),(1,root 1),(2,node T.GBot (T.Just (throw (Probe "unused-parent"))))] [] 3
  8 -> graph salt [(0,root 1),(1,node (T.GBotK (throw (Probe "masked-kind"))) (T.Just 99))] [] 2
  9 -> graph salt [(0,root 10),(1,bot 0)] [(10,1)] 11
  10 -> graph salt [(0,root 99),(1,bot 0)] [] 100
  11 -> graph salt [(0,root 1),(1,node (T.GArr 1 2) (T.Just 0)),(2,bot 0)] [] 3
  12 -> graph salt [(0,root 1),(1,node (T.GArr 2 2) (T.Just 0)),(2,bot 0),(3,bot 1)] [] 4
  13 -> graph salt [(0,root 100),(100,bot 0)] [] 101
  14 -> graph salt [(0,root 10),(1,bot 0)] [(10,11),(11,12),(12,1)] 13
  15 -> graph salt [(0,root 1),(1,node (T.GArr 10 10) (T.Just 0)),(2,bot 1)] [(10,11),(11,2)] 12
  16 -> graph salt [(0,root 1),(1,node (T.GArr 10 3) (T.Just 0)),(2,bot 1),(3,node (T.GArr 10 10) (T.Just 0))] [(10,2)] 11
  17 -> graph salt [(0,root 1),(1,bot 0)] [(10,throw (Probe "unused-link"))] 11
  18 -> graph salt [(0,root 10),(1,bot 0)] [(10,throw (Probe "forced-link"))] 11
  19 -> graph salt [(0,root 1),(1,node (T.GArr 2 10) (T.Just 0)),(2,node (T.GGen 3) (T.Just 0)),(3,bot 2)] [(10,throw (Probe "masked-link"))] 11
  20 -> graph salt [(0,root 1),(1,bot 0)] [(10,11),(11,10)] 12
  21 -> graph salt [(0,root 100),(100,bot 0)] [(200,201),(201,200)] 202
  22 -> graph salt [(0,root 10),(1,bot 0)] [(10,11),(11,10)] 12
  23 -> graph salt [(0,root 1),(1,node (T.GArr 10 11) (T.Just 0)),(2,bot 1)] [(10,2),(11,2)] 12
  24 -> graph salt [(0,root 1),(1,bot 0),(2,bot 99),(3,bot (throw (Probe "late-binder")))] [] 4
  25 -> graph salt [(0,root 1),(1,bot 0),(2,bot (throw (Probe "early-binder"))),(3,bot 99)] [] 4
  26 -> graph salt [(0,root 1),(1,node (throw (Probe "masked-tag")) (T.Just 0)),(2,bot 99)] [] 3
  27 -> graph salt [(0,root 1),(1,root 1),(2,bot 99),(3,bot (throw (Probe "masked-parent")))] [] 4
  28 -> graph salt [(0,bot 1),(1,bot 99),(2,bot (throw (Probe "masked-no-root")))] [] 3
  29 -> graph salt [(0,root 1),(1,bot 2),(3,bot 0)] [] 4
  30 -> graph salt [(0,root 1),(1,bot minBound)] [] 2
  31 -> graph salt [(0,root 1),(1,bot maxBound)] [] 2
  32 -> graph salt [(0,root 1),(1,node (T.GArr 2 3) (T.Just 0)),(2,bot 1),(3,bot 1)] [] 4
  33 -> graph salt [(0,root 1),(1,bot 2),(2,bot 1)] [] 3
  34 -> graph salt [(0,root 1),(1,T.Node T.GBot (T.Just 0) (throw (Probe "leaf-flag")))] [] 2
  35 -> graph salt [(0,root 1),(1,T.Node T.GBot (T.Just 0) (throw (Probe "leaf-flag")))] [] (throw (Probe "next-before-flag"))
  36 -> graph salt [(0,root 100),(100,T.Node T.GBot (T.Just 0) (throw (Probe "sparse-flag")))] [] 101
  37 -> graph salt [(0,root 100),(100,T.Node T.GBot (T.Just 0) (throw (Probe "sparse-flag")))] [] (throw (Probe "sparse-next"))
  38 -> graph salt [(0,root 1),(1,node (T.GCon (throw (Probe "con-name")) [2]) (T.Just 0)),(2,bot 1)] [] 3
  39 -> graph salt [(0,root 1),(1,node (T.GCon "T" [2,throw (Probe "con-child")]) (T.Just 0)),(2,bot 1)] [] (throw (Probe "con-next"))
  40 -> graph salt [(0,root 1),(1,T.Node (T.GCon (throw (Probe "con-name")) [2]) (T.Just 0) (throw (Probe "con-flag"))),(2,bot 1)] [] (throw (Probe "con-next"))
  _ -> error "unknown case")

expected :: [String]
expected =
  ["Right\n","Left ill-dominated type graph\n","Left gen nodes cannot be structural children\n",
   "Right\n","Right\n","Right\n","Probe forced-kind\n",
   "Left graph must have one binding root\n","Left missing binder\n","Right\n",
   "Left missing graph node 99\n","Left infinite type (occurs check)\n",
   "Left a type binder must structurally contain its node\n","Right\n",
   "Right\n","Right\n","Left ill-dominated type graph\n","Right\n","Probe forced-link\n",
   "Left gen nodes cannot be structural children\n","Right\n","Right\n","Right\n",
   "Left missing binder\n","Probe early-binder\n","Left missing binder\n",
   "Left graph must have one binding root\n","Left graph must have one binding root\n",
   "Left missing binder\n","Left missing binder\n","Left missing binder\n",
   "Right\n","Left cyclic binding tree\n"]
labels =
  ["valid","cached-kind-edge","gen-before-poison","unused-kind","unused-name","unused-next",
   "forced-kind","root-before-parent-poison","missing-binder-before-kind","alias-chain",
   "missing-child","occurs","containment","sparse-unobserved",
   "multi-hop","repeat-alias","cached-alias-different-parent","unused-link-poison","forced-link-poison",
   "gen-before-link-poison","unreachable-alias-cycle","sparse-unreachable-cycle","shared-canonical",
   "missing-before-late-binder","early-binder-before-missing","missing-before-tag",
   "multi-root-before-missing","no-root-before-missing","binder-hole","binder-min","binder-max",
   "sibling-order","binding-cycle"]

render (T.Left e) = "Left " ++ P.textToChars e ++ "\n"
render (T.Right ()) = "Right\n"
forceText :: String -> String
forceText s = seq (foldr (\c n -> seq c (n+1)) (0::Int) s) s
observe :: String -> IO String
observe value = do
  got <- try (evaluate (forceText value)) :: IO (Either Probe String)
  pure $ case got of { Left (Probe name) -> "Probe "++name++"\n"; Right text -> text }
runCase :: Int -> IO ()
runCase i = do
  a <- observe (render (G.validateGraph (factory i (2*i))))
  c <- observe (render (C.validateGraph (factory i (2*i+1))))
  let expectationIndex = if i >= 23 then i-1 else i
      verdict = a == expected!!expectationIndex && c == expected!!expectationIndex
      stem = labels!!expectationIndex
  writeFile (stem++".A") a
  writeFile (stem++".C") c
  writeFile (stem++".expected") (expected!!expectationIndex)
  writeFile (stem++".result") (if verdict then "PASS\n" else "FAIL\n")
  if verdict then pure () else error ("finite mismatch: "++stem)
snapshot (T.Graph ns ls next) =
  show next ++ ":" ++ concatMap entry (IM.toList ns) ++ ":" ++ show (IM.toList ls)
  where
    entry (n,T.Node t b f) = show n ++ ":" ++ P.textToChars (G.tagDescription t) ++ ":" ++ mb b ++ ":" ++ fl f ++ ";"
    mb T.Nothing = "none"
    mb (T.Just n) = show n
    fl T.Flexible = "flexible"
    fl T.Rigid = "rigid"
renderGraph full (T.Left e) = "Left " ++ P.textToChars e ++ "\n"
renderGraph full (T.Right g) = if full then "Right " ++ snapshot g ++ "\n" else "Right\n"
runUnify i mode = do
  let eqs = case mode of { 0 -> []; 1 -> [(1,1)]; 2 -> [(1,2)]; 3 -> [(99,1)] }
  -- Preserve both constructor-level demand and fully forced result payload.
  a0 <- observe (renderGraph False (G.unify eqs (factory i (1000+20*i+mode))))
  c0 <- observe (renderGraph False (C.unify eqs (factory i (2000+20*i+mode))))
  a1 <- observe (renderGraph True (G.unify eqs (factory i (3000+20*i+mode))))
  c1 <- observe (renderGraph True (C.unify eqs (factory i (4000+20*i+mode))))
  let a=a0++a1; c=c0++c1; stem="unify-"++show i++"-"++show mode
  writeFile (stem++".A") a
  writeFile (stem++".C") c
  writeFile (stem++".result") (if a==c then "PASS\n" else "FAIL\n")
  if a==c then pure () else error ("unify mismatch: "++stem++" "++a++" versus "++c)

main :: IO ()
main = do
  args <- getArgs
  case args of
    ["cycle-original"] -> putStr (render (G.validateGraph (factory 22 100)))
    ["cycle-candidate"] -> putStr (render (C.validateGraph (factory 22 101)))
    [] -> do
      mapM_ runCase ([0..21]++[23..33])
      mapM_ (\i -> mapM_ (runUnify i) [0..3]) ([0..21]++[23..40])
      putStr "PASS 33 validation and 160 unify canonicalization cases; no performance claim\n"
    _ -> error "unknown mode"

