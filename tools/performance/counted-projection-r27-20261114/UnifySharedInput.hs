{-# LANGUAGE OverloadedStrings #-}
-- SOURCE DRAFT ONLY. 23 legacy cases + 16 new cases; never executed as this module.
-- Expected values are frozen authored oracles. A failed baseline is investigated,
-- never used to regenerate expected.stdout or silently adapt these assertions.
module Main where

import Prelude
import Control.Exception (evaluate, fromException, throw, throwIO)
import Control.Monad (unless)
import System.Exit (exitFailure)
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.Graph as G
import qualified MLF.Host.Base as B
import LegacyPublicApi hiding (main, cases)
import qualified LegacyPublicApi as Legacy

-- New total cases also compare public raw map constructors/counts/prefixes.
-- The old 23 cases remain byte-for-byte logical GraphView controls.
data RawTree a = NilR | TipR I a | BinR I I (RawTree a) (RawTree a)
  deriving (Eq, Show)
data RawGraph = RawGraph (RawTree NodeView) (RawTree I) I deriving (Eq, Show)
rawTree :: (a -> b) -> T.IntMapTree a -> RawTree b
rawTree view tree = case tree of
  T.IntMapNil -> NilR
  T.IntMapTip key value -> TipR key (view value)
  T.IntMapBin count prefix left right -> BinR count prefix (rawTree view left) (rawTree view right)
rawGraph :: T.Graph -> RawGraph
rawGraph (T.Graph (T.IntMap ns) (T.IntMap aliases) fresh) =
  RawGraph (rawTree nodeView ns) (rawTree id aliases) fresh
expectRightComplete :: [(I,I)] -> T.Graph -> T.Graph -> IO String
expectRightComplete equations input expected = do
  actual <- rightWhnf (G.unify equations input)
  actualText <- forced (show (graphView actual))
  expectedText <- forced (show (graphView expected))
  need (actualText == expectedText) "complete logical GraphView differs"
  need (rawGraph actual == rawGraph expected) "complete raw graph constructors/counts/prefixes differ"
  pure ("Right " ++ actualText)

expectDemand :: String -> T.Graph -> [(I,I)] -> IO String
expectDemand wanted input equations = do
  expectSentinel wanted (evaluate (G.unify equations input))
  pure ("Either-WHNF=Sentinel " ++ wanted)

expectHostFailure :: String -> T.Graph -> IO String
expectHostFailure wanted input = do
  observed <- trySync (evaluate (G.unify poisonEquations input))
  case observed of
    Left e -> case (fromException e :: Maybe B.HostError) of
      Just (B.HostError actual) -> need (actual == wanted) "wrong HostError"
      Nothing -> throwIO e
    Right _ -> throwIO (FixtureFailure "expected HostError at Either WHNF")
  pure ("Either-WHNF=HostError " ++ wanted)

rightWhnf :: T.Either B.String T.Graph -> IO T.Graph
rightWhnf value = do
  answer <- evaluate value
  case answer of
    T.Left message -> throwIO (FixtureFailure ("unexpected Left " ++ B.unpack message))
    T.Right result -> pure result

leafPayloadDemand :: Bool -> IO String
leafPayloadDemand kindCase = do
  let leaf = if kindCase
        then T.GBotK (T.KArrow T.Star (throw (Sentinel "kind-codomain")))
        else T.GSkolem (throw (Sentinel "skolem-id")) T.Star
      input = graph [(0,root 1),(1,flex 0 leaf)] [] 2
  result <- rightWhnf (G.unify [] input)
  _ <- evaluate result
  fresh <- evaluate (G.nextId result)
  need (fresh == 2) "leaf fresh counter changed"
  case G.tag (G.nodeAt result 1) of
    T.GBotK kind | kindCase -> case kind of
      T.KArrow domain codomain -> do
        _ <- evaluate domain
        need (kindView domain == StarV) "kind domain changed"
        expectSentinel "kind-codomain" (evaluate codomain)
        pure "Either=Right;Graph=WHNF;nextId=2;tag=GBotK;kind=KArrow;domain=StarV;codomain=Sentinel kind-codomain"
      _ -> throwIO (FixtureFailure "expected partial KArrow")
    T.GSkolem identity kind | not kindCase -> do
      need (kindView kind == StarV) "skolem kind changed"
      expectSentinel "skolem-id" (evaluate identity)
      pure "Either=Right;Graph=WHNF;nextId=2;tag=GSkolem;kind=StarV;identity=Sentinel skolem-id"
    _ -> throwIO (FixtureFailure "wrong leaf tag")

-- Acquire two independent public-unify Either shells, then observe results in
-- reverse order. No ST action, array handle, unsafe IO, or synthetic Graph model.
reverseResults :: ([(I,I)],T.Graph,T.Graph) -> ([(I,I)],T.Graph,T.Graph) -> IO String
reverseResults (eq1,input1,want1) (eq2,input2,want2) = do
  first <- rightWhnf (G.unify eq1 input1)
  second <- rightWhnf (G.unify eq2 input2)
  actual2 <- forced (show (graphView second))
  expected2 <- forced (show (graphView want2))
  need (actual2 == expected2) "reverse second graph differs"
  need (rawGraph second == rawGraph want2) "reverse second raw graph differs"
  actual1 <- forced (show (graphView first))
  expected1 <- forced (show (graphView want1))
  need (actual1 == expected1) "reverse first graph differs"
  need (rawGraph first == rawGraph want1) "reverse first raw graph differs"
  pure ("first-Either=Right;second-Either=Right;second=" ++ actual2 ++ ";first=" ++ actual1)

raw :: T.IntMapTree T.Node -> T.Graph
raw tree = T.Graph (T.IntMap tree) IM.empty (throw (Sentinel "unused-raw-nextId"))

newCases :: [(String, IO String)]
newCases =
  [ ("shared-dense-holes-merge", inRoute True (simple 0 4 8 9)
      (expectRightComplete [(4,8)] (simple 0 4 8 9) (merged 0 4 8 9)))
  , ("shared-multiple-repeated-merge", let
      input = graph [(0,root 1),(1,flex 0 T.GBot),(2,flex 0 T.GBot),
                     (3,flex 0 (T.GCon "Int" []))] [] 4
      expected = graph [(0,root 1),(1,flex 0 (T.GCon "Int" []))] [(2,1),(3,1)] 4
      in inRoute True input (expectRightComplete [(1,2),(1,3),(2,3)] input expected))
  , ("shared-alias-chain-merge", let
      input = graph [(0,root 10),(1,flex 0 T.GBot),(2,flex 0 (T.GCon "Int" []))]
                    [(10,11),(11,1)] 12
      expected = graph [(0,root 1),(1,flex 0 (T.GCon "Int" []))]
                       [(2,1),(10,11),(11,1)] 12
      in inRoute True input (expectRightComplete [(10,2)] input expected))
  , ("binder-payload-before-root-flag", expectDemand "binder-payload"
      (graph [(0,T.Node (T.GGen 1) T.Nothing (throw (Sentinel "later-root-flag"))),
              (1,T.Node T.GBot (T.Just (throw (Sentinel "binder-payload"))) T.Flexible)] [] 2)
      poisonEquations)
  , ("first-order-before-fresh-demand", expectLeft [(99,1)]
      (simple 0 1 2 (throw (Sentinel "unused-first-order-nextId"))) "missing graph node 99")
  , ("fresh-demand-before-permission", expectDemand "next-before-permission"
      (graph [(0,root 1),(1,T.Node T.GBot (T.Just 0) T.Rigid),
              (2,flex 0 (T.GCon "Int" []))] [] (throw (Sentinel "next-before-permission"))) [(1,2)])
  , ("binder-whnf-before-equations", expectDemand "binder-whnf"
      (graph [(0,root 1),(1,T.Node T.GBot (throw (Sentinel "binder-whnf")) T.Flexible)] [] 2)
      poisonEquations)
  , ("root-flag-before-equations", expectDemand "root-flag"
      (graph [(0,T.Node (T.GGen 1) T.Nothing (throw (Sentinel "root-flag"))),
              (1,flex 0 T.GBot)] [] 2) poisonEquations)
  , ("shared-partial-kind-prefix", leafPayloadDemand True)
  , ("shared-partial-skolem-id", leafPayloadDemand False)
  , ("forged-duplicate-root-before-equations", let
      input = raw (T.IntMapBin 3 2
                    (T.IntMapBin 2 1 (T.IntMapTip 0 (root 1)) (T.IntMapTip 0 (root 1)))
                    (T.IntMapTip 1 (flex 0 T.GBot)))
      in inRoute True input (expectLeft poisonEquations input "graph must have one binding root"))
  , ("forged-bounds-before-node-payload", let
      input = raw (T.IntMapBin 3 2
                    (T.IntMapBin 2 1 (T.IntMapTip 0 (throw (Sentinel "unused-first-node")))
                                    (T.IntMapTip 99 (throw (Sentinel "unused-outlier-node"))))
                    (T.IntMapTip 1 (throw (Sentinel "unused-last-node"))))
      in inRoute True input (expectHostFailure "array index out of bounds" input))
  , ("forged-interior-left-before-right", let
      input = raw (T.IntMapBin 4 4
                    (T.IntMapBin 2 1 (T.IntMapTip 0 (throw (Sentinel "unused-first-node")))
                                    (throw (Sentinel "left-interior")))
                    (T.IntMapBin 2 1 (throw (Sentinel "right-interior"))
                                    (T.IntMapTip 2 (throw (Sentinel "unused-last-node")))))
      in inRoute True input (expectDemand "left-interior" input poisonEquations))
  , ("sparse-disjoint-conflict-before-payload", let
      input = graph [(0,throw (Sentinel "unused-conflict-node"))] [(0,1)]
                    (throw (Sentinel "unused-conflict-nextId"))
      in inRoute False input (expectLeft poisonEquations input "missing graph node 1"))
  , ("shared-input-reverse-results", reverseResults
      ([],base,base) ([(1,2)],base,merged 0 1 2 3))
  , ("same-identities-reverse-results", let
      other = graph [(0,root 1),(1,flex 0 T.GBot),(2,flex 0 (T.GCon "Bool" []))] [] 3
      otherMerged = graph [(0,root 1),(1,flex 0 (T.GCon "Bool" []))] [(2,1)] 3
      in reverseResults ([(1,2)],base,merged 0 1 2 3) ([(1,2)],other,otherMerged))
  ]

main :: IO ()
main = do
  let allCases = Legacy.cases ++ newCases
  passed <- mapM runCase allCases
  let count = length allCases
      successes = length (filter id passed)
  putStrLn ("SUMMARY\t" ++ show count ++ "\t" ++ show successes)
  unless (successes == count) exitFailure
