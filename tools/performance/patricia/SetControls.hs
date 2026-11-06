{-# LANGUAGE ScopedTypeVariables #-}
module SetControls (main) where
import Prelude
import Control.Exception
import Control.Monad
import Data.Int (Int64)
import Data.Bits
import qualified Data.IntSet as O
import qualified Bootstrap.IntSet as C
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as H
import Data.List (nub,sort,elemIndex)

assertEqual :: (Eq a, Show a) => String -> a -> a -> IO ()
assertEqual label expected actual = unless (expected==actual) (error (label++": expected "++show expected++", actual "++show actual))
unwrap T.Nothing = Nothing
unwrap (T.Just a) = Just a
reference = O.fromList . map fromIntegral
keys = map fromIntegral . O.toAscList
bounds :: [Int64]
bounds = nub ([minBound,minBound+1,minBound+63,minBound+64,maxBound,maxBound-1,maxBound-63,maxBound-64]++[-130..130]++concat [[bit b-1,bit b,bit b+1,negate (bit b)] | b<-[0..62]])
randoms :: Int64 -> [Int64]
randoms seed = tail (iterate (\x -> x*6364136223846793005+1442695040888963407) seed)
shapes :: [[Int64]]
shapes = [[],bounds,reverse bounds,[-200..200],[minBound..minBound+150],[maxBound-150..maxBound],map (*64) [-80..80]]++
 [take (fromIntegral (s `mod` 129)) (randoms s)++take 5 (drop (fromIntegral s `mod` length bounds) bounds) | s<-[1..160]]
verify label expected actual = do
 assertEqual (label++" keys") (keys expected) (C.toList actual)
 assertEqual (label++" size") (fromIntegral (O.size expected)) (C.size actual)
 assertEqual (label++" null") (O.null expected) (C.null actual)
 assertEqual (label++" validity") True (C.valid actual)
 assertEqual (label++" min") (fmap fromIntegral (O.lookupMin expected)) (unwrap (C.lookupMin actual))
 assertEqual (label++" max") (fmap fromIntegral (O.lookupMax expected)) (unwrap (C.lookupMax actual))
 assertEqual (label++" foldl") (reverse (keys expected)) (C.foldl (flip (:)) [] actual)
 assertEqual (label++" foldr") (keys expected) (C.foldr (:) [] actual)
 let low = fmap (\(k,t)->(fromIntegral k,keys t)) (O.minView expected)
 let high = fmap (\(k,t)->(fromIntegral k,keys t)) (O.maxView expected)
 assertEqual (label++" minView") low (fmap (\(k,t)->(k,C.toList t)) (unwrap (C.minView actual)))
 assertEqual (label++" maxView") high (fmap (\(k,t)->(k,C.toList t)) (unwrap (C.maxView actual)))
 forM_ (zip [0..] (keys expected)) $ \(i,k)-> do
  assertEqual (label++" rank") (Just i) (unwrap (C.lookupIndex k actual))
  assertEqual (label++" select") (Just k) (unwrap (C.elemAt i actual))
 forM_ [minBound,-1,fromIntegral (O.size expected),maxBound] $ \i ->
  assertEqual (label++" outside rank") Nothing (unwrap (C.elemAt i actual))
 -- Independent prefix/cardinality audit uses base bit operations, never the
 -- candidate's prefix helpers or validation predicates.
 let audit tree = case tree of
      T.IntSetNil -> []
      T.IntSetTip n p bm ->
       let ks=[p+fromIntegral i | i<-[0..63], testBit bm i] in
       if bm/=0 && p .&. 63==0 && n==fromIntegral (length ks) then ks else error "independent tip invariant"
      T.IntSetBin n p l r ->
       let ls=audit l;rs=audit r;m=p .&. negate p
           match k=(k .&. complement (m-1)) .|. m == p
           left k=k .&. m==0
       in if p/=0 && p .&. 63==0 && not (null ls||null rs) &&
             n==fromIntegral(length ls+length rs) && all (\k->match k&&left k) ls && all (\k->match k&&not(left k)) rs
          then ls++rs else error "independent branch invariant"
 case actual of T.IntSet tree -> assertEqual (label++" independent structure") (keys expected) (sort (audit tree))
main = do
 assertEqual "reference machine word width" 64 (finiteBitSize (0::Int))
 forM_ (zip [0..] shapes) $ \(i,xs)-> do
  let expected=reference xs;actual=C.fromList xs;label="shape "++show (i::Int)
  verify label expected actual
  verify (label++" ascending") expected (C.fromDistinctAscList (keys expected))
  forM_ (take 17 (drop (i `mod` 40) bounds)++take 7 (randoms (fromIntegral i))) $ \key -> do
   assertEqual (label++" member") (O.member (fromIntegral key) expected) (C.member key actual)
   assertEqual (label++" missing rank") (fmap fromIntegral (elemIndex (fromIntegral key) (O.toAscList expected))) (unwrap (C.lookupIndex key actual))
   verify (label++" insert") (O.insert (fromIntegral key) expected) (C.insert key actual)
   verify (label++" delete") (O.delete (fromIntegral key) expected) (C.delete key actual)
  verify (label++" filter") (O.filter even expected) (C.filter even actual)
  verify (label++" map") (O.map (\k->k `quot` 64) expected) (C.map (\k->k `quot` 64) actual)
 forM_ [0..400::Int] $ \i -> do
  let xs=shapes!!(i `mod` length shapes);ys=shapes!!((i*71+3) `mod` length shapes)
      a=C.fromList xs;b=C.fromList ys;x=reference xs;y=reference ys
  verify "union" (O.union x y) (C.union a b)
  verify "intersection" (O.intersection x y) (C.intersection a b)
  verify "difference" (O.difference x y) (C.difference a b)
  assertEqual "subset" (O.isSubsetOf x y) (C.isSubsetOf a b)
  assertEqual "proper subset" (O.isProperSubsetOf x y) (C.isProperSubsetOf a b)
  assertEqual "disjoint" (O.disjoint x y) (C.disjoint a b)
  assertEqual "equality" (x==y) (C.eqIntSet a b)
 assertEqual "empty lookup key remains lazy" False (C.member (error "unused key") C.empty)
 assertEqual "empty delete key remains lazy" True (C.null (C.delete (error "unused key") C.empty))
 assertEqual "ordered fold short circuit" (-2) (C.foldr (\k _->k) (error "unused tail") (C.fromList [-2,7]))
 print ("PASS independent IntSet operations, signed ordering, bitmap boundaries, rank/select and demand",length shapes)
