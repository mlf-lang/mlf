{-# LANGUAGE OverloadedStrings #-}
-- R3 finite controls. The oracle is the exact f9 Solver, module rename only.
module Main where
import Prelude
import Control.Exception (SomeException, displayException, evaluate, try)
import Control.Monad (forM_, unless)
import Data.Int (Int64)
import Data.List (isInfixOf)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.IntRank as Rank
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified R3FrozenSolver as F

check label good = unless good (errorWithoutStackTrace label)
right label value = case value of T.Left e -> errorWithoutStackTrace (label ++ ": " ++ B.unpack e); T.Right x -> pure x
sameMaybe _ T.Nothing T.Nothing = True
sameMaybe eq (T.Just x) (T.Just y) = eq x y
sameMaybe _ _ _ = False
sameList eq xs ys = length xs == length ys && and (zipWith eq xs ys)
sameTree eq a b = case (a,b) of
  (T.IntMapNil,T.IntMapNil) -> True
  (T.IntMapTip k x,T.IntMapTip l y) -> k == l && eq x y
  (T.IntMapBin n p l r,T.IntMapBin m q x y) -> n == m && p == q && sameTree eq l x && sameTree eq r y
  _ -> False
sameMap eq (T.IntMap a) (T.IntMap b) = sameTree eq a b
sameSetTree a b = case (a,b) of
  (T.IntSetNil,T.IntSetNil) -> True
  (T.IntSetTip n p bits,T.IntSetTip m q other) -> n == m && p == q && bits == other
  (T.IntSetBin n p l r,T.IntSetBin m q x y) -> n == m && p == q && sameSetTree l x && sameSetTree r y
  _ -> False
sameSet (T.IntSet a) (T.IntSet b) = sameSetTree a b
sameGraph (T.Graph a b n) (T.Graph c d m) = n == m && sameMap G.equalNode a c && sameMap (==) b d
sameScopes (T.ScopeIndex a bs) (T.ScopeIndex c ds) = sameMap (==) a c && sameList (sameMap (==)) bs ds
sameSolver (T.Solver g p d s) (T.Solver h q e t) = sameGraph g h && sameMap sameSet p q && sameMap sameSet d e && sameScopes s t
sameResult eq a b = case (a,b) of
  (T.Left x,T.Left y) -> B.v_eqString x y
  (T.Right x,T.Right y) -> eq x y
  _ -> False
sameComponent (a,b) (c,d) = sameMap G.equalNode a c && sameSet b d
sameProjection (g,es,old,(Rank.MapIndex selected,scopes,stubs))
               (h,fs,new,(Rank.MapIndex selected2,scopes2,stubs2)) =
  sameGraph g h && es == fs && sameList (\(i,n) (j,m) -> i == j && G.equalNode n m) old new &&
  sameTree G.equalNode selected selected2 && sameMap (sameMaybe (==)) scopes scopes2 && sameMap (==) stubs stubs2

node tag parent = T.Node tag (T.Just parent) T.Flexible
base :: T.Graph
base = T.Graph (IM.fromList
  [(0,T.Node (T.GGen 1) T.Nothing T.Flexible), (1,node (T.GCon "Int" []) 0),
   (2,node (T.GGen 3) 0), (3,node (T.GArr 4 5) 2), (4,node (T.GArr 6 6) 3),
   (5,node T.GBot 3), (6,node T.GBot 4), (7,node (T.GGen 8) 0),
   (8,node (T.GArr 9 10) 7), (9,node T.GBot 8), (10,node T.GBot 8)]) IM.empty 11
replace i n (T.Graph ns ls next) = T.Graph (IM.insert i n ns) ls next
without ids (T.Graph ns ls next) = T.Graph (foldl (flip IM.delete) ns ids) ls next
rename f (T.Graph ns ls next) = T.Graph
  (IM.fromList [(f i,T.Node (G.mapTag f tag) (fmapMaybe f binder) flag) | (i,T.Node tag binder flag) <- IM.toList ns])
  (IM.fromList [(f a,f b) | (a,b) <- IM.toList ls]) (f next)
  where fmapMaybe _ T.Nothing = T.Nothing
        fmapMaybe g (T.Just n) = T.Just (g n)
fixtures :: [(String,T.Graph,Int64,Int64,Bool)]
fixtures =
  [("base admitted",base,2,8,True),
   ("rigid old",replace 9 (T.Node T.GBot (T.Just 8) T.Rigid) base,2,8,False),
   ("rigid target",replace 8 (T.Node (T.GArr 9 10) (T.Just 7) T.Rigid) base,2,8,False),
   ("kind mismatch",replace 8 (node (T.GTyCon "List" (T.KArrow T.Star T.Star)) 7) (without [9,10] base),2,8,False),
   ("shared old",replace 3 (node (T.GArr 4 4) 2) (replace 4 (node T.GBot 2) (without [5,6] base)),2,8,True),
   ("aliases",case base of T.Graph ns _ _ -> T.Graph ns (IM.fromList [(30,8),(31,30),(32,2)]) 33,32,31,True)]

componentControls = do
  let coordinates = [[0..95],[-65..30],[2^60..2^60+95],
        [minBound,minBound+1,-65,-64,-1,0,63,64,65,maxBound-1,maxBound]] :: [[Int64]]
  forM_ (zip [0::Int ..] coordinates) $ \(serial,ids) -> do
    let successors = tail ids ++ [head ids]
        graph = T.Graph (IM.fromList [(i,T.Node (T.GArr j j) T.Nothing T.Flexible) | (i,j) <- zip ids successors]) IM.empty maxBound
        -- A finite direct traversal fixture, deliberately cyclic; not admitted
        -- as a valid prepared graph and never passed to the full solver.
        solver = T.Solver graph IM.empty IM.empty (T.ScopeIndex IM.empty [])
    forM_ [[],[head ids],reverse ids,concatMap (replicate 3) ids] $ \pending ->
      check ("component physical ring " ++ show serial)
        (sameResult sameComponent (F.componentCanonicalNodesVisit solver IM.empty IS.empty pending)
          (S.componentCanonicalBitmapVisit solver IS.empty IM.empty IS.empty pending))
  -- These are direct helper rejection-order cases, not forged prepared proofs.
  forM_ [7..12] $ \missing -> do
    let boundary = T.Node (T.GGen 99) T.Nothing T.Flexible
        ns = IM.fromList ((0,node (T.GArr 7 8) 9):[(n,boundary) | n <- [7..11], n < missing])
        solver = T.Solver (T.Graph ns IM.empty 100)
          (IM.singleton 0 (IS.singleton 10)) (IM.singleton 0 (IS.singleton 11)) (T.ScopeIndex IM.empty [])
        expected = F.componentCanonicalNodesVisit solver IM.empty IS.empty [0,12]
        actual = S.componentCanonicalBitmapVisit solver IS.empty IM.empty IS.empty [0,12]
    check "edge order exact first missing" (sameResult sameComponent expected actual)
    case actual of
      T.Left e -> check "authored first missing bytes" (B.unpack e == "missing graph node " ++ show missing)
      _ -> errorWithoutStackTrace "missing direct node was admitted"

capture :: Int -> IO (Either String Int)
capture x = do
  result <- try (evaluate x) :: IO (Either SomeException Int)
  pure (case result of Left e -> Left (displayException e); Right n -> Right n)
outer value = case value of T.Left _ -> 0; T.Right _ -> 1
shape value = case value of
  T.Left e -> errorWithoutStackTrace (B.unpack e)
  T.Right (ns,ss) -> length (IM.keys ns) + length (IS.toList ss)
compareDemand label old new = do
  a <- capture old; b <- capture new
  check (label ++ " demand") (a == b)
  pure a

demandControls = do
  let poison = errorWithoutStackTrace "unused solver"
      badSeen = errorWithoutStackTrace "unused empty result"
  answer <- compareDemand "empty pending" (outer (F.componentCanonicalNodesVisit poison badSeen IS.empty []))
    (outer (S.componentCanonicalBitmapVisit poison (errorWithoutStackTrace "unused bitmap") badSeen IS.empty []))
  check "empty no demand" (answer == Right 1)
  let seen = IM.singleton 17 (errorWithoutStackTrace "seen payload")
  answer <- compareDemand "already seen skips graph" (shape (F.componentCanonicalNodesVisit poison seen IS.empty [17,17]))
    (shape (S.componentCanonicalBitmapVisit poison (IS.singleton 17) seen IS.empty [17,17]))
  check "seen no payload" (answer == Right 1)
  let boundary = T.Node (T.GGen (errorWithoutStackTrace "Gen root"))
                   (errorWithoutStackTrace "Gen binder") (errorWithoutStackTrace "Gen flag")
      solver = T.Solver (T.Graph (IM.singleton 5 boundary) (errorWithoutStackTrace "aliases") (errorWithoutStackTrace "counter"))
                   (errorWithoutStackTrace "parents") (errorWithoutStackTrace "descendants") (errorWithoutStackTrace "scopes")
  answer <- compareDemand "Gen stops all outgoing demands" (shape (F.componentCanonicalNodesVisit solver IM.empty IS.empty [5,5]))
    (shape (S.componentCanonicalBitmapVisit solver IS.empty IM.empty IS.empty [5,5]))
  check "Gen boundary shape" (answer == Right 2)
  let fields = T.Node (T.GCon (errorWithoutStackTrace "unused name") []) T.Nothing (errorWithoutStackTrace "unused flag")
      solver2 = T.Solver (T.Graph (IM.singleton 1 fields) IM.empty 2) IM.empty IM.empty (T.ScopeIndex IM.empty [])
  answer <- compareDemand "unused constructor name and flag" (shape (F.componentCanonicalNodesVisit solver2 IM.empty IS.empty [1]))
    (shape (S.componentCanonicalBitmapVisit solver2 IS.empty IM.empty IS.empty [1]))
  check "non-boundary unused payload" (answer == Right 1)
  let bad = T.Node (T.GArr (errorWithoutStackTrace "first-child") (errorWithoutStackTrace "second-child"))
              (errorWithoutStackTrace "later-binder") T.Flexible
      solver3 = T.Solver (T.Graph (IM.singleton 0 bad) IM.empty 1) IM.empty IM.empty (T.ScopeIndex IM.empty [])
  answer <- compareDemand "first child error remains first" (shape (F.componentCanonicalNodesVisit solver3 IM.empty IS.empty [0]))
    (shape (S.componentCanonicalBitmapVisit solver3 IS.empty IM.empty IS.empty [0]))
  check "exact authored payload error" (case answer of Left message -> "first-child" `isInfixOf` message; _ -> False)

fullControls = do
  let layouts = [("dense",id),("negative",subtract 100),("sparse",\n -> 100003*n-9001),("wide",\n -> n+2^60)]
  forM_ fixtures $ \(name,input,source,target,success) -> forM_ layouts $ \(layout,coordinate) -> do
    let label = name ++ "/" ++ layout
        graph = rename coordinate input
        a = coordinate source; b = coordinate target
    old <- right (label ++ " prepare oracle") (F.prepare graph)
    candidate <- right (label ++ " prepare candidate") (S.prepare graph)
    check (label ++ " unchanged prepare") (sameSolver old candidate)
    let expected = F.instantiateClosedPrepared a b old
        actual = S.instantiateClosedPrepared a b candidate
    check (label ++ " complete prepared physical result/error") (sameResult sameSolver expected actual)
    check (label ++ " immutable retry") (sameResult sameSolver expected (S.instantiateClosedPrepared a b candidate))
    check (label ++ " input remains unchanged") (sameSolver old candidate)
    check (label ++ " authored success category") (case expected of T.Right _ -> success; T.Left _ -> not success)
    check (label ++ " unchanged public route")
      (sameResult sameSolver (F.instantiateClosed a b old) (S.instantiateClosed a b candidate))
    (root,_,frontier,current) <- right (label ++ " expansion") (F.expandedGraphPrepared a b old)
    let first = G.nextId (F.graph old)
        fresh = F.allocatedNodes first (G.nextId current) (G.nodes current)
        equations = frontier ++ [(root,b)]
        canonical = [(G.resolve current x,G.resolve current y) | (x,y) <- equations]
        pending = filter (uncurry (/=)) canonical
    check (label ++ " exact compact projection")
      (sameResult sameProjection (F.preparedFallbackProjection old current first fresh pending)
        (S.preparedFallbackProjection candidate current first fresh pending))
    check (label ++ " full direct fallback")
      (sameResult sameSolver (F.unifyPreparedFallback equations old current first fresh)
        (S.unifyPreparedFallback equations candidate current first fresh))
    forM_ [[],[(a,a)],[(minBound,b)],[(a,minBound+1)]] $ \es ->
      check (label ++ " fallback reflexive/missing first error")
        (sameResult sameSolver (F.unifyPreparedFallback es old current first fresh)
          (S.unifyPreparedFallback es candidate current first fresh))

main = do
  check "fixed direct layouts" (length fixtures == 6)
  componentControls
  demandControls
  fullControls
  putStrLn "PASS R3 bitmap: 16 finite traversals, 6 ordered missing-node cases, 5 demand controls, 24 complete prepared/projection/fallback fixtures"
