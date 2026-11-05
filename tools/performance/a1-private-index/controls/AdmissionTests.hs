{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
-- Independent finite admission controls. This is test code, never production.
module AdmissionTests where

import Prelude
import Control.Exception (SomeException, displayException, evaluate, try)
import Control.Monad (forM_)
import Data.List (sortOn)
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph.Solver as S
import qualified FrozenSolver as FS
import qualified SessionUnderTest as N
import qualified SessionOracle as O

-- Hand fixtures use a host-authored balanced constructor, not candidate map,
-- graph, solver, canonicalization, index or admission builders.
mapOf :: [(Integer,a)] -> T.IntMap a
mapOf entries = T.IntMap (tree (sortOn fst entries))
  where
    tree [] = T.MapEmpty
    tree xs = case splitAt (length xs `div` 2) xs of
      (left,(key,value):right) ->
        T.MapNode (fromIntegral (length xs)) key value (tree left) (tree right)
      _ -> errorWithoutStackTrace "fixture builder impossible split"

graphOf :: [(Integer,T.Node)] -> [(Integer,Integer)] -> Integer -> T.Graph
graphOf ns aliases fresh = T.Graph (mapOf ns) (mapOf aliases) fresh

root :: Integer -> T.Node
root child = T.Node (T.GGen child) T.Nothing T.Flexible

bound :: T.GTag -> Integer -> T.Node
bound tag parent = T.Node tag (T.Just parent) T.Flexible

minimal :: T.Graph
minimal = graphOf [(0,root 1),(1,bound T.GBot 0)] [] 2

duplicates :: T.Graph
duplicates = graphOf
  [(0,root 1),(1,bound (T.GArr 2 2) 0),(2,bound T.GBot 1)] [] 3

nested :: T.Graph
nested = graphOf
  [(0,root 1),(1,T.Node (T.GCon "Unit" []) (T.Just 0) T.Rigid),
   (2,bound (T.GGen 3) 0),(3,bound (T.GArr 4 4) 2),(4,bound T.GBot 3)] [] 5

aliased :: T.Graph
aliased = graphOf [(0,root 10),(1,bound T.GBot 0)] [(10,11),(11,1)] 12

aliasedCanonical :: T.Graph
aliasedCanonical = graphOf [(0,root 1),(1,bound T.GBot 0)] [(10,11),(11,1)] 12

wide :: T.Graph
wide = graphOf
  ([(0,root 1),(1,bound (T.GCon "Pack" [2..130]) 0)] ++
   [(n,bound T.GBot 1) | n <- [2..130]]) [] 131

-- Pure syntax renaming for our hand-authored finite tags, not Graph.mapTag.
rename :: (Integer -> Integer) -> T.Graph -> T.Graph
rename f (T.Graph ns aliases fresh) = graphOf
  [(f n,renameNode v) | (n,v) <- O.mapEntries ns]
  [(f n,f target) | (n,target) <- O.mapEntries aliases] (f fresh)
  where
    renameNode (T.Node tag binder flag) = T.Node (renameTag tag) (renameBinder binder) flag
    renameBinder T.Nothing = T.Nothing
    renameBinder (T.Just n) = T.Just (f n)
    renameTag T.GBot = T.GBot
    renameTag (T.GGen n) = T.GGen (f n)
    renameTag (T.GArr a b) = T.GArr (f a) (f b)
    renameTag (T.GCon name ns) = T.GCon name (map f ns)
    renameTag _ = errorWithoutStackTrace "fixture renamer received unlisted tag"

-- This adapter follows the NEW production admission route, then observes one
-- detached snapshot. It does not call candidate openSession on an old Solver.
admit :: T.Graph -> T.Either B.String T.Solver
admit input = case N.prepareGraph input of
  T.Left message -> T.Left message
  T.Right canonical -> P.runST $ do
    initial <- N.openPreparedSession canonical
    snapshot <- N.freezeSession initial
    pure (T.Right snapshot)

type Edges = [(Integer,[Integer])]
type Intervals = [(Integer,(Integer,Integer))]
type Jumps = [[(Integer,Integer)]]
type Positive = (String,T.Graph,T.Graph,Edges,Edges,Intervals,Jumps)

oneScope :: Intervals
oneScope = [(0,(0,1))]

oneJump :: Jumps
oneJump = [[(0,0)]]

renameCase :: String -> (Integer -> Integer) -> Positive -> Positive
renameCase label f (_,input,canonical,parents,binders,intervals,jumps) =
  (label,rename f input,rename f canonical,
   [(f key,map f members) | (key,members) <- parents],
   [(f key,map f members) | (key,members) <- binders],
   [(f key,span) | (key,span) <- intervals],
   [[(f key,f parent) | (key,parent) <- level] | level <- jumps])

duplicateCase :: Positive
duplicateCase = ("duplicate child and separate binder index",duplicates,duplicates,
  [(1,[0]),(2,[1])],[(0,[1]),(1,[2])],oneScope,oneJump)

positives :: [Positive]
positives =
  [("minimal",minimal,minimal,[(1,[0])],[(0,[1])],oneScope,oneJump),
   duplicateCase,
   ("nested scope intervals and jumps",nested,nested,
    [(1,[0]),(3,[2]),(4,[3])],[(0,[1,2]),(2,[3]),(3,[4])],
    [(0,(0,2)),(2,(1,2))],[[(0,0),(2,0)],[(0,0),(2,0)]]),
   ("alias chain canonicalizes children but retains links",aliased,aliasedCanonical,
    [(1,[0])],[(0,[1])],oneScope,oneJump),
   ("three pages and ascending immutable bucket",wide,wide,
    [(1,[0])] ++ [(n,[1]) | n <- [2..130]],
    [(0,[1]),(1,[2..130])],oneScope,oneJump),
   renameCase "sparse identities" (\n -> 17 + 4096*n) duplicateCase,
   renameCase "arbitrary precision identities" (\n -> 10^(40::Integer) + 4096*n) duplicateCase,
   renameCase "negative page boundary robustness" (\n -> n-65) duplicateCase]

positiveControls :: IO ()
positiveControls = do
  forM_ positives $ \(label,input,canonical,parents,binders,intervals,jumps) -> do
    old <- O.right (label ++ "/literal prepare") (FS.prepare input)
    public <- O.right (label ++ "/unchanged public prepare") (S.prepare input)
    current <- O.right (label ++ "/new private admission") (admit input)
    O.checkSolver (label ++ "/public remains literal") True old public
    O.checkSolver (label ++ "/complete detached private state") False old current
    let T.Solver actualGraph actualParents actualBinders actualScopes = current
        T.ScopeIndex actualIntervals actualJumps = actualScopes
    O.assert (label ++ "/hand canonical graph, aliases and counter")
      (O.sameGraphLogical canonical actualGraph)
    O.assert (label ++ "/hand structural parents") (O.indexEntries actualParents == parents)
    O.assert (label ++ "/hand binding children") (O.indexEntries actualBinders == binders)
    O.assert (label ++ "/hand scope intervals") (O.mapEntries actualIntervals == intervals)
    O.assert (label ++ "/hand scope jumps") (map O.mapEntries actualJumps == jumps)
  putStrLn "PASS admission handwritten topology aliases scopes paging and identities"

withFresh :: Integer -> T.Graph -> T.Graph
withFresh next (T.Graph ns aliases _) = T.Graph ns aliases next

overlap :: T.Graph
overlap = graphOf [(0,root 1),(1,bound T.GBot 0),(2,bound T.GBot 0)] [(1,2)] 3

withAlias :: Integer -> T.Graph -> T.Graph
withAlias next (T.Graph ns _ _) = T.Graph ns (mapOf [(10,1)]) next

rigidRoot :: T.Graph
rigidRoot = graphOf
  [(0,T.Node (T.GGen 1) T.Nothing T.Rigid),(1,bound T.GBot 0)] [] 2

validationAndOverlap :: T.Graph
validationAndOverlap = graphOf
  [(0,T.Node (T.GGen 1) T.Nothing T.Rigid),(1,bound T.GBot 0),(2,bound T.GBot 0)]
  [(1,2)] 0

negatives :: [(String,String,T.Graph)]
negatives =
  [("empty is rejected", "graph must have one binding root", graphOf [] [] 0),
   ("non-gen root", "binding root must be a gen node",
    graphOf [(0,T.Node T.GBot T.Nothing T.Flexible)] [] 1),
   ("two roots", "graph must have one binding root",
    graphOf [(0,root 1),(1,bound T.GBot 0),(2,root 3),(3,bound T.GBot 2)] [] 4),
   ("rigid gen", "gen nodes must be flexible",rigidRoot),
   ("overlap before both counters", "live graph identities cannot also be aliases",withFresh 0 overlap),
   ("node counter before alias counter", "fresh identity counter overlaps graph nodes",withAlias 1 minimal),
   ("alias counter", "fresh identity counter overlaps graph aliases",withAlias 2 minimal),
   ("validation before overlap and counters", "gen nodes must be flexible",validationAndOverlap)]

expectLeft :: String -> String -> T.Either B.String a -> IO ()
expectLeft label wanted answer = case answer of
  T.Left message -> O.assert (label ++ "/literal expected diagnostic") (B.unpack message == wanted)
  T.Right _ -> errorWithoutStackTrace (label ++ "/unexpected success")

negativeControls :: IO ()
negativeControls = do
  forM_ negatives $ \(label,wanted,input) -> do
    expectLeft (label ++ "/frozen") wanted (FS.prepare input)
    expectLeft (label ++ "/public") wanted (S.prepare input)
    expectLeft (label ++ "/private actual admission") wanted (admit input)
  putStrLn "PASS admission literal rejection and first-error ordering"

-- These are selected exception-marker observations, not arbitrary-bottom
-- equivalence. In particular we never compare a lazy Right constructor alone
-- with an eagerly executed private region: a successful Solver is demanded.
observeValue :: a -> IO String
observeValue value = do
  result <- try (evaluate value >> pure ()) :: IO (Either SomeException ())
  pure $ case result of
    Left exception -> "Exception:" ++ displayException exception
    Right () -> "Value"

observeOutcome :: T.Either B.String T.Solver -> IO String
observeOutcome answer = do
  let force = case answer of
        T.Left message -> length (B.unpack message) `seq` ()
        T.Right solver -> solver `seq` ()
  result <- observeValue force
  pure $ if result /= "Value" then result else case answer of
    T.Left message -> "Left:" ++ B.unpack message
    T.Right _ -> "Right"

freshDemandControls :: IO ()
freshDemandControls = do
  let marker = errorWithoutStackTrace "admission/fresh-counter"
      cases =
        [("invalid ignores counter",graphOf [] [] marker,"Left:graph must have one binding root"),
         ("overlap ignores counter",withFresh marker overlap,"Left:live graph identities cannot also be aliases"),
         ("valid graph demands counter",withFresh marker minimal,"Exception:admission/fresh-counter")]
  forM_ cases $ \(label,input,wanted) -> do
    old <- observeOutcome (FS.prepare input)
    public <- observeOutcome (S.prepare input)
    current <- observeOutcome (admit input)
    O.assert (label ++ "/frozen prescribed observation") (old == wanted)
    O.assert (label ++ "/public prescribed observation") (public == wanted)
    O.assert (label ++ "/private prescribed observation") (current == wanted)
  putStrLn "PASS admission finite fresh-counter demand probes"

localOrderingControls :: IO ()
localOrderingControls = do
  initial <- O.right "local ordering finite initial state" (FS.prepare minimal)
  let childTail = errorWithoutStackTrace "admission/child-tail"
      binder = errorWithoutStackTrace "admission/binder"
      pending = T.Node (T.GCon "Pack" (1:childTail)) binder T.Flexible
      complete = T.Node (T.GCon "Pack" [1]) binder T.Flexible
      private entry = P.runST $ do
        state <- N.openSession initial
        next <- N.addInitialNode state entry
        N.freezeSession next
      cases = [("child tail before binder",pending,"Exception:admission/child-tail"),
               ("binder after finite children",complete,"Exception:admission/binder")]
  forM_ cases $ \(label,node,wanted) -> do
    old <- observeValue (FS.addNode initial (100,node))
    current <- observeValue (private (100,node))
    O.assert (label ++ "/frozen prescribed local demand") (old == wanted)
    O.assert (label ++ "/private prescribed local demand") (current == wanted)
  oldState <- observeValue (FS.addNode (errorWithoutStackTrace "admission/state")
    (errorWithoutStackTrace "admission/entry"))
  privateState <- observeValue (P.runST $ do
    next <- N.addInitialNode (errorWithoutStackTrace "admission/state")
      (errorWithoutStackTrace "admission/entry")
    N.freezeSession next)
  O.assert "state before entry/frozen" (oldState == "Exception:admission/state")
  O.assert "state before entry/private" (privateState == "Exception:admission/state")
  putStrLn "PASS admission test-only children-before-binder demand"

main :: IO ()
main = positiveControls >> negativeControls >> freshDemandControls >> localOrderingControls
