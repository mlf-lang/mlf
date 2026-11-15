{-# LANGUAGE ScopedTypeVariables #-}
-- Proposal-only semantic probe. No timing loop and no benchmark claims.
-- The rankControls key/shapes pattern is adapted from the repository's
-- tools/performance/patricia/design-controls/Main.hs at the pinned commit.
-- IntRankCandidate retains the complete original source licence header.
module Main(main) where

import Prelude
import Control.Exception (catch, evaluate, throw)
import Control.Monad (forM_, unless)
import Data.Int (Int64)
import Data.IORef (IORef, newIORef, modifyIORef', readIORef)
import qualified Data.List as List
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntRank as Old
import qualified IntRankCandidate as New
import qualified MLF.Host.Base as B

data Depth = ConstructorOnly | ResultPayload deriving Show
data Observation = Absent | Present | Value Int64 | Raised String
  deriving (Eq, Show)
type RankFn = Int64 -> Int64 -> T.IntMapTree Int64 -> T.Maybe Int64
type Checks = IORef Int

poison :: String -> a
poison label = throw (B.HostError label)
{-# NOINLINE poison #-}

-- Catch only the explicit synchronous HostError poison family. Asynchronous
-- exceptions, timeouts, IO failures and programming errors are NOT results.
observe :: Depth -> T.Maybe Int64 -> IO Observation
observe depth thunk = action `catch` \(B.HostError label) -> pure (Raised label)
  where
    action = do
      value <- evaluate thunk
      case value of
        T.Nothing -> pure Absent
        T.Just n -> case depth of
          ConstructorOnly -> pure Present
          ResultPayload -> evaluate n >>= pure . Value

observeHost :: a -> IO (Either String a)
observeHost value = (Right <$> evaluate value)
  `catch` \(B.HostError label) -> pure (Left label)

check :: Checks -> String -> Bool -> IO ()
check counter label good = do
  unless good (ioError (userError ("FAIL: " ++ label)))
  modifyIORef' counter (+1)

expect :: Checks -> String -> Observation -> Observation
       -> Int64 -> Int64 -> T.IntMapTree Int64 -> IO ()
expect counter label whnf payload key offset tree =
  forM_ [("old", Old.mapRankTree), ("new", New.mapRankTree)] $ \(side, rank) ->
    forM_ [(ConstructorOnly, whnf), (ResultPayload, payload)] $ \(depth, expected) -> do
      actual <- observe depth (rank key offset tree)
      check counter (label ++ "/" ++ side ++ "/" ++ show depth ++
        " expected=" ++ show expected ++ " actual=" ++ show actual) (actual == expected)

differential :: Checks -> String -> Int64 -> Int64 -> T.IntMapTree Int64 -> IO ()
differential counter label key offset tree =
  forM_ [ConstructorOnly, ResultPayload] $ \depth -> do
    old <- observe depth (Old.mapRankTree key offset tree)
    new <- observe depth (New.mapRankTree key offset tree)
    check counter (label ++ "/" ++ show depth ++ " old=" ++ show old ++ " new=" ++ show new)
      (old == new)

-- Use arbitrary-precision arithmetic for the mathematical expected value,
-- followed by the explicit signed Int64 wrapping conversion.
wrapAdd :: Int64 -> Int64 -> Int64
wrapAdd a b = fromInteger (toInteger a + toInteger b)

keys :: [Int64]
keys = [minBound, minBound+1, -(2^62), -(2^32), -65,-64,-1,0,
        1,63,64,65,2^32,2^62,maxBound-1,maxBound]

validControls :: Checks -> IO ()
validControls counter = do
  let shapes = [[],keys,reverse keys,keys++keys] ++ map (flip take keys) [1..length keys]
      offsets = [minBound,minBound+1,-17,-1,0,17,maxBound-1,maxBound] :: [Int64]
  check counter "exactly twenty valid insertion shapes" (length shapes == 20)
  forM_ (zip [0 :: Int ..] shapes) $ \(shapeId,xs) -> do
    let ordered = List.nub (List.sort xs)
        values = IM.fromList [(k,poison "map-payload") | k <- xs]
        T.IntMap tree = values
        oldIndex = Old.indexMap values
        newIndex = New.indexMap values
        label = "valid-shape-" ++ show shapeId
    check counter (label ++ "/old-size") (Old.mapSize oldIndex == fromIntegral (length ordered))
    check counter (label ++ "/new-size") (New.mapSize newIndex == fromIntegral (length ordered))
    forM_ (keys ++ [-100,100]) $ \key -> forM_ offsets $ \offset -> do
      let position = fromIntegral <$> List.elemIndex key ordered
          expected = maybe Absent (Value . wrapAdd offset) position
          whnf = maybe Absent (const Present) position
      expect counter (label ++ "/key=" ++ show key ++ "/offset=" ++ show offset)
        whnf expected key offset tree
      oldPublic <- observe ResultPayload (Old.mapRank key offset oldIndex)
      newPublic <- observe ResultPayload (New.mapRank key offset newIndex)
      check counter (label ++ "/public-mapRank-old") (oldPublic == expected)
      check counter (label ++ "/public-mapRank-new") (newPublic == expected)
    forM_ [-1..fromIntegral (length ordered)] $ \position -> do
      let expected = if position < 0 || position >= fromIntegral (length ordered)
            then Absent else Value (ordered !! fromIntegral position)
      old <- observe ResultPayload (Old.mapSelect position oldIndex)
      new <- observe ResultPayload (New.mapSelect position newIndex)
      check counter (label ++ "/select-old") (old == expected)
      check counter (label ++ "/select-new") (new == expected)
      -- Check the inverse on present positions, not just independent answers.
      case expected of
        Value key -> do
          a <- observe ResultPayload (Old.mapRank key 0 oldIndex)
          b <- observe ResultPayload (New.mapRank key 0 newIndex)
          check counter (label ++ "/inverse-old") (a == Value position)
          check counter (label ++ "/inverse-new") (b == Value position)
        _ -> pure ()

tip :: Int64 -> T.IntMapTree Int64
tip key = T.IntMapTip key (poison "selected-map-payload")
bin :: Int64 -> T.IntMapTree Int64 -> T.IntMapTree Int64 -> T.IntMapTree Int64
bin prefix left right = T.IntMapBin (poison "unused-root-count") prefix left right
sizeNode :: Int64 -> T.IntMapTree Int64
sizeNode count = T.IntMapBin count (poison "unused-sibling-prefix")
  (poison "unused-sibling-left") (poison "unused-sibling-right")

rawControls :: Checks -> IO ()
rawControls c = do
  let p = Present; v = Value; e = Raised; off = poison "offset"
      leftZero = bin 1 (tip 0) (poison "unselected-right")
      rightZero = bin minBound (poison "unselected-left") (tip (-1))
      rightPlus count = bin 1 (sizeNode count) (tip 1)
      leftPlus count = bin minBound (tip 0) (sizeNode count)
  expect c "Nil-does-not-demand-key-or-offset" Absent Absent (poison "key") off T.IntMapNil
  expect c "tip-payload-lazy-offset-lazy-at-Just" p (e "offset") 0 off (tip 0)
  expect c "missing-tip-keeps-offset-lazy" Absent Absent 1 off (tip 0)
  expect c "non-sign-left-zero-unselected-poison" p (v 17) 0 17 leftZero
  expect c "sign-right-zero-unselected-poison" p (v 17) (-1) 17 rightZero
  expect c "non-sign-left-zero-offset-poison" p (e "offset") 0 off leftZero
  expect c "sign-right-zero-offset-poison" p (e "offset") (-1) off rightZero
  expect c "non-sign-right-count-is-not-forced-at-Just" p (e "sibling-count")
    1 17 (rightPlus (poison "sibling-count"))
  expect c "sign-left-count-is-not-forced-at-Just" p (e "sibling-count")
    0 17 (leftPlus (poison "sibling-count"))
  expect c "non-sign-right-offset-before-count" p (e "offset")
    1 off (rightPlus (poison "sibling-count"))
  expect c "sign-left-offset-before-count" p (e "offset")
    0 off (leftPlus (poison "sibling-count"))
  expect c "right-sibling-root-demand-only-on-payload" p (e "sibling-tree")
    1 17 (bin 1 (poison "sibling-tree") (tip 1))
  expect c "left-sibling-root-demand-only-on-payload" p (e "sibling-tree")
    0 17 (bin minBound (tip 0) (poison "sibling-tree"))
  expect c "sibling-tip-neither-key-nor-payload-demanded-for-size" p (v 18)
    1 17 (bin 1 (T.IntMapTip (poison "sibling-key") (poison "sibling-value")) (tip 1))
  expect c "missing-Nil-sibling-size-offset-all-lazy" Absent Absent
    1 off (bin 1 (sizeNode (poison "sibling-count")) T.IntMapNil)
  expect c "missing-tip-sibling-size-offset-all-lazy" Absent Absent
    1 off (bin 1 (sizeNode (poison "sibling-count")) (tip 2))
  expect c "selected-tree-before-offset-or-sibling-count" (e "selected-tree") (e "selected-tree")
    1 off (bin 1 (sizeNode (poison "sibling-count")) (poison "selected-tree"))
  expect c "root-tree-before-query" (e "root-tree") (e "root-tree")
    (poison "query") off (poison "root-tree")
  expect c "routing-query-before-prefix" (e "query") (e "query")
    (poison "query") off (bin (poison "prefix") (poison "left") (poison "right"))
  expect c "routing-prefix-before-selected-child-or-offset" (e "prefix") (e "prefix")
    0 off (bin (poison "prefix") (poison "left") (poison "right"))
  expect c "forged-root-count-is-not-recomputed-or-demanded" p (v 5)
    0 5 (T.IntMapBin (-999) 1 (tip 0) (poison "right"))
  expect c "raw-duplicate-leaves-no-normalization" p (v 5)
    0 5 (T.IntMapBin 999 1 (tip 0) (tip 0))
  expect c "raw-prefix-zero-is-not-validated" p (v 8)
    0 5 (bin 0 (sizeNode 3) (tip 0))
  let nested = bin 4 (sizeNode (poison "earlier-count"))
        (bin 6 (sizeNode (poison "later-count")) (tip 7))
  expect c "nested-prior-offset-chain-before-later-count" p (e "earlier-count") 7 0 nested
  expect c "nested-initial-offset-before-both-counts" p (e "offset") 7 off nested
  expect c "nested-zero-chain-does-not-demand-siblings" p (v (-17)) 0 (-17)
    (bin 4 leftZero (poison "outer-right"))
  -- Raw constructors deliberately bypass IntMap.node/fromList validation.
  forM_ [minBound,-7,-1,0,1,17,maxBound] $ \count ->
    forM_ [minBound,-17,0,17,maxBound] $ \offset -> do
      expect c ("forged-right-count=" ++ show count ++ "/offset=" ++ show offset)
        p (v (wrapAdd offset count)) 1 offset (rightPlus count)
      expect c ("forged-sign-left-count=" ++ show count ++ "/offset=" ++ show offset)
        p (v (wrapAdd offset count)) 0 offset (leftPlus count)
  -- Tip (==) is Prelude Eq Int64, not Base.orderedStrict. Do not invent an
  -- operand-order guarantee; require unchanged observed first-error behavior.
  differential c "tip-query-versus-stored-key-first-error"
    (poison "query") off (T.IntMapTip (poison "stored-key") (poison "payload"))

primitiveControls :: Checks -> IO ()
primitiveControls c = do
  a <- observeHost (B.v_addInt (poison "left") (poison "right"))
  b <- observeHost (B.v_unsignedLtInt (poison "key") (poison "prefix"))
  check c "host-addition-ordered-demand" (a == Left "left")
  check c "host-routing-ordered-demand" (b == Left "key")

main :: IO ()
main = do
  counter <- newIORef 0
  primitiveControls counter
  validControls counter
  rawControls counter
  n <- readIORef counter
  putStrLn ("PASS narrow IntRank semantic probe: " ++ show n ++
    " checks; constructor/payload, valid/raw trees, demand and first-error only; no performance claim")
