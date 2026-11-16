{-# LANGUAGE OverloadedStrings, DeriveDataTypeable #-}
module Main where
import Prelude
import Control.Exception (Exception, evaluate, throw, try)
import Data.Typeable (Typeable)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as G
import qualified Bootstrap.IntMap as IM
import qualified Prototype.OwnedDenseValidation as C

data Probe = Probe String deriving (Eq,Show,Typeable)
instance Exception Probe
-- Raw lazy records intentionally avoid mkNode/mkGraph's additional constructor
-- strictness, so the validator, not the fixture builder, determines demand.
node :: T.GTag -> T.Maybe P.Int -> T.Node
node t b = T.Node t b T.Flexible
root child = node (T.GGen child) T.Nothing
bot parent = node T.GBot (T.Just parent)
arr a b parent = node (T.GArr a b) (T.Just parent)
graph :: [(P.Int,T.Node)] -> [(P.Int,P.Int)] -> P.Int -> T.Graph
graph ps ls fresh = T.Graph (IM.fromDistinctAscList ps) (IM.fromDistinctAscList ls) fresh
unit result = case result of
  T.Left e -> "Left "++show (P.textToChars e)
  T.Right () -> "Right ()"
forceString :: String -> ()
forceString []=()
forceString (c:cs)=c `seq` forceString cs
observe :: T.Either P.String () -> IO String
observe answer = do
  let text=unit answer
  result <- try (evaluate (forceString text)) :: IO (Either Probe ())
  pure (case result of Left (Probe label)->"Probe "++label; Right ()->text)
check :: String -> String -> T.Graph -> IO ()
check label expected input = do
  a <- observe (G.validateGraph input)
  c <- observe (C.validateGraphOwned input)
  checkText label expected a c
checkText label expected a c = do
  writeFile (label++".A") (a++"\n")
  writeFile (label++".C") (c++"\n")
  writeFile (label++".expected") (expected++"\n")
  let ok=a==expected && c==expected
  writeFile (label++".result") (if ok then "PASS\n" else "FAIL\n")
  if ok then pure () else error (label++": finite validation contract mismatch")

-- Boundary control of ORIGINAL public APIs, not candidate helper exposure.
-- The arbitrary boxed initializer stays lazy. The original strict integer
-- wrapper forces value at action construction even before array/index poison.
publicBoundary :: IO String
publicBoundary = do
  let lazyValue = P.runST $ do
        a <- P.newSTArray 1 (throw (Probe "unused-lazy-initial") :: P.Int)
        P.writeSTArray a 0 7
        P.readSTArray a 0
      action = G.writeDenseInt 0 (throw (Probe "array"))
        (throw (Probe "index")) (throw (Probe "value")) :: P.ST () ()
  observed <- try (evaluate action >> pure ()) :: IO (Either Probe ())
  pure ("lazy="++show lazyValue++"|writeDemand="++case observed of
    Left (Probe label)->"Probe "++label; Right ()->"RETURNED")

main :: IO ()
main = do
  check "valid-minimal" "Right ()" (graph [(0,root 1),(1,bot 0)] [] 2)
  check "valid-negative-dense" "Right ()" (graph [(-2,root (-1)),(-1,bot (-2))] [] 0)
  check "valid-max-dense" "Right ()" (graph [(9223372036854775806,root 9223372036854775807),(9223372036854775807,bot 9223372036854775806)] [] 0)
  check "valid-min-dense" "Right ()" (graph [(-9223372036854775808,root (-9223372036854775807)),(-9223372036854775807,bot (-9223372036854775808))] [] 0)
  check "valid-sparse-span" "Right ()" (graph [(0,root 9223372036854775807),(9223372036854775807,bot 0)] [] 0)
  check "valid-sparse-wrapped-span" "Right ()" (graph [(-9223372036854775808,root 9223372036854775807),(9223372036854775807,bot (-9223372036854775808))] [] 0)
  check "valid-alias-chain" "Right ()" (graph [(0,root 8),(1,bot 0)] [(8,9),(9,1)] 10)
  check "valid-overlap-sparse" "Right ()" (graph [(0,root 1),(1,bot 0),(2,bot 0)] [(1,2)] 3)
  check "valid-holes-cached-child" "Right ()" (graph [(0,root 2),(2,arr 4 4 0),(4,bot 2)] [] 5)
  check "valid-transitive-type-binder" "Right ()" (graph [(0,root 1),(1,arr 2 3 0),(2,arr 4 4 1),(3,bot 0),(4,bot 1)] [] 5)
  check "valid-kind-application" "Right ()" (graph [(0,root 1),(1,node (T.GTyApp 2 3) (T.Just 0)),(2,node (T.GTyCon "F" (T.KArrow T.Star T.Star)) (T.Just 1)),(3,bot 1)] [] 4)
  check "empty" "Left \"graph must have one binding root\"" (graph [] [] 0)
  check "two-roots" "Left \"graph must have one binding root\"" (graph [(0,root 1),(1,node T.GBot T.Nothing)] [] 2)
  check "non-gen-root" "Left \"binding root must be a gen node\"" (graph [(0,node T.GBot T.Nothing)] [] 1)
  check "missing-binder" "Left \"missing binder\"" (graph [(0,root 1),(1,bot 99)] [] 2)
  check "binding-cycle" "Left \"cyclic binding tree\"" (graph [(0,root 1),(1,bot 2),(2,bot 1)] [] 3)
  check "structural-cycle" "Left \"infinite type (occurs check)\"" (graph [(0,root 1),(1,arr 1 1 0)] [] 2)
  check "gen-structural-child" "Left \"gen nodes cannot be structural children\"" (graph [(0,root 1),(1,node (T.GGen 2) (T.Just 0)),(2,bot 1)] [] 3)
  check "rigid-gen" "Left \"gen nodes must be flexible\"" (graph [(0,T.Node (T.GGen 1) T.Nothing T.Rigid),(1,bot 0)] [] 2)
  check "missing-structural-child" "Left \"missing graph node 99\"" (graph [(0,root 99),(1,bot 0)] [] 2)
  check "missing-alias-terminal" "Left \"missing graph node 9\"" (graph [(0,root 8),(1,bot 0)] [(8,9)] 10)
  check "ill-dominated" "Left \"ill-dominated type graph\"" (graph [(0,root 1),(1,arr 2 2 0),(2,bot 3),(3,node (T.GGen 4) (T.Just 0)),(4,bot 3)] [] 5)
  check "type-binder-not-containing" "Left \"a type binder must structurally contain its node\"" (graph [(0,root 1),(1,bot 0),(2,bot 1)] [] 3)
  check "kind-application-arity" "Left \"invalid type constructor arity: a type of kind * cannot be applied\"" (graph [(0,root 1),(1,node (T.GTyApp 2 3) (T.Just 0)),(2,bot 1),(3,bot 1)] [] 4)
  check "function-kind" "Left \"function types require kind * arguments\"" (graph [(0,root 1),(1,arr 2 3 0),(2,node (T.GBotK (T.KArrow T.Star T.Star)) (T.Just 1)),(3,bot 1)] [] 4)
  check "legacy-kind" "Left \"legacy type constructor has a non-* argument\"" (graph [(0,root 1),(1,node (T.GCon "C" [2]) (T.Just 0)),(2,node (T.GBotK (T.KArrow T.Star T.Star)) (T.Just 1))] [] 3)
  check "root-count-before-tag" "Left \"graph must have one binding root\"" (graph [(0,node (throw (Probe "tag0")) T.Nothing),(1,node (throw (Probe "tag1")) T.Nothing)] [] 2)
  check "missing-binder-before-tag" "Left \"missing binder\"" (graph [(0,node (throw (Probe "tag0")) T.Nothing),(1,node (throw (Probe "tag1")) (T.Just 99))] [] 2)
  check "binding-cycle-before-rigid" "Left \"cyclic binding tree\"" (graph [(0,T.Node (T.GGen 1) T.Nothing T.Rigid),(1,bot 2),(2,bot 1)] [] 3)
  check "poison-graph" "Probe graph" (throw (Probe "graph"))
  check "poison-nodes-before-links" "Probe nodes" (T.Graph (throw (Probe "nodes")) (throw (Probe "links")) 0)
  check "poison-links-before-node" "Probe links" (T.Graph (IM.singleton 0 (throw (Probe "node"))) (throw (Probe "links")) 1)
  check "poison-node" "Probe node" (graph [(0,throw (Probe "node"))] [] 1)
  check "poison-binder-before-tag" "Probe binder" (graph [(0,node (throw (Probe "tag")) (throw (Probe "binder")))] [] 1)
  check "poison-root-flag" "Probe flag" (graph [(0,T.Node (T.GGen 1) T.Nothing (throw (Probe "flag"))),(1,bot 0)] [] 2)
  check "lazy-next-id" "Right ()" (graph [(0,root 1),(1,bot 0)] [] (throw (Probe "fresh")))
  check "lazy-boxed-kind" "Right ()" (graph [(0,root 1),(1,node (T.GBotK (throw (Probe "kind"))) (T.Just 0))] [] 2)
  boundary <- publicBoundary
  checkText "original-public-boundary" "lazy=7|writeDemand=Probe value" boundary boundary
  putStrLn "PASS finite owned dense scalar validation differential"
