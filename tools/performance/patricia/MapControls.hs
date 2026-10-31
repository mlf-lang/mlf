{-# LANGUAGE ScopedTypeVariables #-}
module MapControls (main) where
import Prelude hiding (lookup)
import Control.Exception
import Control.Monad
import Data.Int (Int64)
import Data.Bits
import qualified Data.IntMap.Lazy as O
import qualified Bootstrap.IntMap as C
import qualified Bootstrap.IntSet as S
import qualified Bootstrap.Types as T
import Data.List (nub,sort,elemIndex)

assertEqual :: (Eq a,Show a)=>String->a->a->IO ()
assertEqual label expected actual = unless (expected==actual) (error (label++": expected "++show expected++", actual "++show actual))
unwrap T.Nothing = Nothing
unwrap (T.Just a) = Just a
rewrap Nothing = T.Nothing
rewrap (Just a) = T.Just a
bounds :: [Int64]
bounds = nub ([minBound,minBound+1,minBound+63,minBound+64,maxBound,maxBound-1,maxBound-63,maxBound-64]++[-130..130]++concat [[bit b-1,bit b,bit b+1,negate (bit b)] | b<-[0..62]])
randoms :: Int64->[Int64]
randoms seed = tail(iterate (\x->x*6364136223846793005+1442695040888963407) seed)
shapes :: [[Int64]]
shapes = [[],bounds,reverse bounds,[-200..200],[minBound..minBound+150],[maxBound-150..maxBound],map (*64) [-80..80]]++
 [take (fromIntegral (s `mod` 129)) (randoms s)++take 5 (drop (fromIntegral s `mod` length bounds) bounds) | s<-[1..160]]
entries xs = zip xs (map show [0::Int ..])
reference xs = O.fromList [(fromIntegral k,v)|(k,v)<-xs]
list = map (\(k,v)->(fromIntegral k,v)) . O.toAscList
verify label expected actual = do
 let expectedList=list expected
 assertEqual (label++" list") expectedList (C.toList actual)
 assertEqual (label++" size") (fromIntegral (O.size expected)) (C.size actual)
 assertEqual (label++" null") (O.null expected) (C.null actual)
 assertEqual (label++" valid") True (C.valid actual)
 assertEqual (label++" keys") (map fst expectedList) (C.keys actual)
 assertEqual (label++" elems") (map snd expectedList) (C.elems actual)
 assertEqual (label++" keysSet") (map fst expectedList) (S.toList (C.keysSet actual))
 assertEqual (label++" keysSet valid") True (S.valid (C.keysSet actual))
 assertEqual (label++" foldl") (reverse expectedList) (C.foldlWithKey (\rest k v->(k,v):rest) [] actual)
 assertEqual (label++" foldr") expectedList (C.foldrWithKey (\k v rest->(k,v):rest) [] actual)
 assertEqual (label++" min") (fmap (\(k,v)->(fromIntegral k,v)) (O.lookupMin expected)) (unwrap (C.lookupMin actual))
 assertEqual (label++" max") (fmap (\(k,v)->(fromIntegral k,v)) (O.lookupMax expected)) (unwrap (C.lookupMax actual))
 assertEqual (label++" minView") (fmap (\((k,v),t)->((fromIntegral k,v),list t)) (O.minViewWithKey expected))
   (fmap (\(item,t)->(item,C.toList t)) (unwrap (C.minViewWithKey actual)))
 forM_ (zip [0..] expectedList) $ \(i,(k,v))-> do
  assertEqual (label++" rank") (Just i) (unwrap (C.lookupIndex k actual))
  assertEqual (label++" select") (Just (k,v)) (unwrap (C.elemAt i actual))
 forM_ [minBound,-1,fromIntegral (O.size expected),maxBound] $ \i->
  assertEqual (label++" outside rank") Nothing (unwrap (C.elemAt i actual))
 let audit tree = case tree of
      T.IntMapNil -> []
      T.IntMapTip k _ -> [k]
      T.IntMapBin n p l r ->
       let ls=audit l;rs=audit r;m=p .&. negate p
           match k=(k .&. complement (m-1)) .|. m == p
           left k=k .&. m==0
       in if p/=0 && not(null ls||null rs) && n==fromIntegral(length ls+length rs) &&
             all (\k->match k&&left k) ls && all (\k->match k&&not(left k)) rs
          then ls++rs else error "independent branch invariant"
 case actual of T.IntMap tree -> assertEqual (label++" independent structure") (map fst expectedList) (sort(audit tree))
routingControls tree = do
 let keys t=case t of
      T.IntMapNil->[]
      T.IntMapTip k _->[k]
      T.IntMapBin _ _ l r->keys l++keys r
     prefixes=[minBound,maxBound,-1,1,2,4,8,16,64,128,256]::[Int64]
 forM_ prefixes $ \p->forM_ [False,True] $ \side->do
  let m=p .&. negate p
      expected=not(null(keys tree)) && all(\k->((k .&. complement(m-1)) .|. m)==p && ((k .&. m==0)==side))(keys tree)
  assertEqual "independent child routing bounds" expected (C.childRouting side p tree)
 case tree of
  T.IntMapBin _ _ l r->routingControls l>>routingControls r
  _->pure ()
main = do
 assertEqual "reference machine word width" 64 (finiteBitSize (0::Int))
 forM_ (zip [0..] shapes) $ \(i,ks)-> do
  let xs=entries ks;expected=reference xs;actual=C.fromList xs;label="shape "++show(i::Int)
  case actual of T.IntMap tree->routingControls tree
  verify label expected actual
  verify (label++" ascending") expected (C.fromDistinctAscList (list expected))
  verify (label++" fromListWith") (O.fromListWith (++) [(fromIntegral k,v)|(k,v)<-xs++xs]) (C.fromListWith (++) (xs++xs))
  forM_ (take 13 (drop (i `mod` 40) bounds)++take 5 (randoms(fromIntegral i))) $ \key-> do
   let k=fromIntegral key
   assertEqual "lookup" (O.lookup k expected) (unwrap(C.lookup key actual))
   assertEqual "member" (O.member k expected) (C.member key actual)
   assertEqual "rank" (fmap fromIntegral (elemIndex k (O.keys expected))) (unwrap(C.lookupIndex key actual))
   verify "insert" (O.insert k "new" expected) (C.insert key "new" actual)
   verify "insertWith" (O.insertWith (++) k "new" expected) (C.insertWith (++) key "new" actual)
   verify "insertWithKey" (O.insertWithKey (\n a b->show n++a++b) k "new" expected) (C.insertWithKey (\n a b->show n++a++b) key "new" actual)
   verify "delete" (O.delete k expected) (C.delete key actual)
   verify "adjust" (O.adjust ("prefix"++) k expected) (C.adjust ("prefix"++) key actual)
   verify "adjustWithKey" (O.adjustWithKey (\n v->show n++v) k expected) (C.adjustWithKey (\n v->show n++v) key actual)
   let change x = if even key then Nothing else Just (maybe "new" ("old"++) x)
   verify "alter" (O.alter change k expected) (C.alter (rewrap . change . unwrap) key actual)
   verify "update" (O.update (change . Just) k expected) (C.update (rewrap . change . Just) key actual)
  verify "map" (O.map ("p"++) expected) (C.map ("p"++) actual)
  verify "mapWithKey" (O.mapWithKey (\k v->show k++v) expected) (C.mapWithKey (\k v->show k++v) actual)
  verify "mapMaybe" (O.mapMaybe (\v->if even(length v) then Just(v++"p") else Nothing) expected)
   (C.mapMaybe (\v->rewrap(if even(length v) then Just(v++"p") else Nothing)) actual)
  verify "filterWithKey" (O.filterWithKey (\k v->even k||length v==1) expected) (C.filterWithKey (\k v->even k||length v==1) actual)
 forM_ [0..300::Int] $ \i-> do
  let xs=entries(shapes!!(i `mod` length shapes));ys=entries(shapes!!((i*71+3) `mod` length shapes))
      a=C.fromList xs;b=C.fromList ys;x=reference xs;y=reference ys
  verify "union" (O.union x y) (C.union a b)
  verify "unionWith" (O.unionWith (++) x y) (C.unionWith (++) a b)
  verify "intersection" (O.intersection x y) (C.intersection a b)
  verify "intersectionWith" (O.intersectionWith (++) x y) (C.intersectionWith (++) a b)
  verify "difference" (O.difference x y) (C.difference a b)
  assertEqual "equality" (x==y) (C.eqIntMap (==) a b)
 let lazyMap=C.fromList [(minBound,error "left payload"),(0,error "middle payload"),(maxBound,error "right payload")] :: T.IntMap String
 assertEqual "stored values lazy" 3 (C.size lazyMap)
 assertEqual "keysSet ignores values" [minBound,0,maxBound] (S.toList(C.keysSet lazyMap))
 assertEqual "lazy map results" 3 (C.size(C.map (error "unused map action") lazyMap))
 assertEqual "lazy adjustment" 3 (C.size(C.adjust (error "unused adjustment") 0 lazyMap))
 assertEqual "left-biased union lazy" "left" (C.get 0 (C.union (C.singleton 0 "left") lazyMap))
 assertEqual "left-biased intersection lazy" "left" (C.get 0 (C.intersection (C.singleton 0 "left") lazyMap))
 assertEqual "difference ignores values" [] (C.toList(C.difference lazyMap lazyMap))
 assertEqual "empty lookup key lazy" False (C.member (error "unused key") (C.empty::T.IntMap String))
 assertEqual "empty delete key lazy" True (C.null(C.delete (error "unused key") (C.empty::T.IntMap String)))
 assertEqual "empty missing adjust lazy" True (C.null(C.adjust (error "unused action") (error "unused key") (C.empty::T.IntMap String)))
 assertEqual "empty missing alter key lazy" True (C.null(C.alter (\_->T.Nothing) (error "unused key") (C.empty::T.IntMap String)))
 assertEqual "ascending fold short circuit" minBound (C.foldrWithKey (\k _ _->k) (error "unused tail") lazyMap)
 print ("PASS independent IntMap operations, lazy values, signed ordering, cached counts and rank/select",length shapes)
