-- Independent Data.Map oracle; equivalent keys keep the complete left representative.
module Main where
import Prelude
import Control.Monad (forM_, unless, filterM)
import Control.Exception (SomeException, displayException, evaluate, try)
import Data.Int (Int64)
import qualified Data.Map.Lazy as Oracle
import qualified Bootstrap.Map as M
import qualified Bootstrap.Types as T

cmp :: Int64 -> Int64 -> Int64
cmp a b = case compare a b of LT -> -1; EQ -> 0; GT -> 1
need label ok = unless ok (fail label)
valid tree = fst (walk Nothing Nothing tree) where
 walk _ _ T.MapEmpty = (True,0 :: Int64)
 walk lo hi (T.MapNode n k _ l r) =
  let (left,ln)=walk lo (Just k) l; (right,rn)=walk (Just k) hi r
  in (left && right && n==1+ln+rn && maybe True (<k) lo && maybe True (>k) hi &&
      (ln+rn<=1 || (ln<=3*rn && rn<=3*ln)),1+ln+rn)
check a b = do
 let xs=zip a (map (:[]) [0..] :: [[Int64]]);ys=zip b (map (:[]) [10000..] :: [[Int64]])
     x=M.fromList cmp xs;y=M.fromList cmp ys;ox=Oracle.fromList xs;oy=Oracle.fromList ys
     op left right=left++[-7]++right
 forM_ [(M.union cmp x y,Oracle.union ox oy),
        (M.unionWith cmp op x y,Oracle.unionWith op ox oy)] $ \(actual,expected)->
  need ("union "++show (take 8 a,take 8 b,length a,length b))
    (valid actual && M.valid cmp actual && M.toList actual==Oracle.toList expected)
 let tag offset ks=zipWith (\k i->((k,i),[i])) ks [offset..]
     order (k,_) (l,_)=cmp k l
     l=tag 0 a;r=tag 10000 b
     actual=M.unionWith order op (M.fromList order l) (M.fromList order r)
     oracle entries=Oracle.fromList [(fst k,(k,v)) | (k,v)<-entries]
     expected=map snd (Oracle.toList (Oracle.unionWith (\(k,v) (_,w)->(k,op v w)) (oracle l) (oracle r)))
 need "left representative and combine order" (M.valid order actual && M.toList actual==expected)
expect label value = do
 result<-try (evaluate value) :: IO (Either SomeException Int64)
 need label (case result of Left e -> takeWhile (/='\n') (displayException e)==label;Right _->False)
main = do
 let small=filterM (const [False,True]) [-3..3] :: [[Int64]]
     orders ks=[ks,reverse ks,concatMap (replicate 3) ks]
     pairs=[(a,b) | a<-small,b<-small] ++
       [(a,b) | n<-[1,2,3,7,16,31,32,127,256,1024],
          a<-orders [0..n],start<-[-n,0,n `div` 2,n+1],b<-orders [start..start+n]] ++
       [([minBound,-1,0,maxBound],[minBound,1,maxBound])]
 mapM_ (uncurry check) pairs
 let tree=M.fromList cmp [(1,17::Int64),(2,error "unselected")]
 need "unselected lazy" (M.get cmp 1 (M.union cmp tree (M.singleton 3 (error "unused")))==17)
 need "left bias" (M.get cmp 1 (M.union cmp tree (M.singleton 1 (error "right")))==17)
 need "lazy combine left" (M.get cmp 1 (M.unionWith cmp (\a _->a) tree (M.singleton 1 (error "right")))==17)
 need "lazy combine right" (M.get cmp 1 (M.unionWith cmp (\_ b->b) (M.singleton 1 (error "left")) (M.singleton 1 23))==23)
 need "deferred combine" (M.size (M.unionWith cmp (\_ _->error "combine") tree tree)==2)
 need "empty comparator left" (M.size (M.union (\_ _->error "cmp") M.empty tree)==2)
 need "empty comparator right" (M.size (M.union (\_ _->error "cmp") tree M.empty)==2)
 expect "left-tree" (M.size (M.union cmp (error "left-tree") (error "right-tree")))
 expect "right-tree" (M.size (M.union cmp M.empty (error "right-tree")))
 putStrLn ("PASS union: "++show (length pairs)++" map pairs; independent content, representatives, combine order and balance; 9 demand controls")
