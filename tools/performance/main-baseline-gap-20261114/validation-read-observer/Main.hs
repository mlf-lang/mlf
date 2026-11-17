{-# LANGUAGE OverloadedStrings, DeriveDataTypeable #-}
module Main where
import Prelude
import Control.Exception (Exception, evaluate, throw, try)
import Data.Typeable (Typeable)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as G
import qualified Bootstrap.IntMap as IM
import qualified Prototype.ValidationReadObserver as O
import qualified Prototype.ValidationReadObserverMutant as M

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
  _ -> error "unknown case")

expected :: [String]
expected =
  ["Right\n","Left ill-dominated type graph\n","Left gen nodes cannot be structural children\n",
   "Right\n","Right\n","Right\n","Probe forced-kind\n",
   "Left graph must have one binding root\n","Left missing binder\n","Right\n",
   "Left missing graph node 99\n","Left infinite type (occurs check)\n",
   "Left a type binder must structurally contain its node\n","Right\n"]
labels =
  ["valid","cached-kind-edge","gen-before-poison","unused-kind","unused-name","unused-next",
   "forced-kind","root-before-parent-poison","missing-binder-before-kind","alias-chain",
   "missing-child","occurs","containment","sparse-unobserved"]

render (T.Left e) = "Left " ++ P.textToChars e ++ "\n"
render (T.Right ()) = "Right\n"
forceText :: String -> String
forceText s = seq (foldr (\c n -> seq c (n+1)) (0::Int) s) s
observe :: String -> IO String
observe value = do
  got <- try (evaluate (forceText value)) :: IO (Either Probe String)
  pure $ case got of { Left (Probe name) -> "Probe "++name++"\n"; Right text -> text }
key T.Nothing = "-"
key (T.Just n) = show n
event (O.Event label identity) = P.textToChars label ++ "\t" ++ key identity ++ "\n"
eventLabel (O.Event label _) = P.textToChars label
isKind2Success (O.Event label identity) =
  P.textToChars label == "success:kind-fact" &&
    case identity of { T.Just n -> n == 2; T.Nothing -> False }

runCase :: Int -> IO ()
runCase i = do
  -- Separate NOINLINE factory calls with distinct demanded salts; no shared Graph binding.
  a <- observe (render (G.validateGraph (factory i (2*i))))
  let report = O.observeGraph (factory i (2*i+1))
  c <- observe (case report of { O.Report result _ -> render result })
  trace <- if take 6 c == "Probe " then pure "<unavailable-on-Probe>\n"
           else observe (case report of { O.Report _ es -> concatMap event es })
  let traceOK = case i of
        1 -> case report of
          O.Report _ es ->
            let after = dropWhile (not . isKind2Success) es
            in not (null after) && any ((=="failure:edge-gates") . eventLabel) after
        9 -> elem "alias:present\t10\n" (linesWithNewline trace) &&
             elem "alias:absent\t1\n" (linesWithNewline trace)
        13 -> trace == "sparse:unobserved\t-\n"
        _ -> if take 6 c == "Probe " then trace == "<unavailable-on-Probe>\n"
             else not (null trace) && take 6 trace /= "Probe "
      verdict = a == expected!!i && c == expected!!i && traceOK
      stem = labels!!i
  writeFile (stem++".A") a
  writeFile (stem++".C") c
  writeFile (stem++".events") trace
  writeFile (stem++".expected") (expected!!i)
  writeFile (stem++".result") (if verdict then "PASS\n" else "FAIL\n")
  if verdict then pure () else error ("finite mismatch: "++stem)

linesWithNewline = map (++"\n") . lines
main :: IO ()
main = do
  mapM_ runCase [0..13]
  -- Deliberately wrong edge cache shortcut must be detected on the real full-graph witness.
  wrong <- observe (case M.observeGraph (factory 1 1001) of { M.Report result _ -> render result })
  writeFile "cached-kind-edge.mutant" wrong
  if wrong == "Right\n" then pure () else error "mutant witness did not distinguish"
  putStr "PASS 14 finite validator read-observer cases; no certificate reuse\n"
