{-# LANGUAGE PatternSynonyms, ViewPatterns #-}
-- Test-only representation bridge. No candidate container helper is imported.
-- Frozen BST algorithms keep their bodies; only their Types import is redirected.
-- Views inspect keys and shape, never map payloads. Partial/corrupt container
-- spines are outside this bridge; direct demand/corruption controls cover them.
module OracleTypes
  (module T,IntMap,IntSet,pattern IntMap,pattern IntSet,
   wrapMap,unwrapMap,wrapSet,unwrapSet,validMap,validSet,
   mapEntries,setEntries,sameMap,sameSet) where
import Bootstrap.Types as T hiding (IntMap(..),IntSet(..))
import qualified Bootstrap.Types as R
import qualified MLF.Host.Base as B
import Prelude hiding (Maybe(..),Either(..))
import qualified Prelude
import Data.Bits
import Data.Word(Word64)
import Data.List(sortOn)

type IntMap=R.IntMap
type IntSet=R.IntSet
pattern IntMap :: Map B.Int a -> R.IntMap a
pattern IntMap tree <- (unwrapMap -> tree) where IntMap tree=wrapMap tree
pattern IntSet :: Map B.Int () -> R.IntSet
pattern IntSet tree <- (unwrapSet -> tree) where IntSet tree=wrapSet tree
{-# COMPLETE IntMap #-}
{-# COMPLETE IntSet #-}

oldEntries :: Map B.Int a -> [(B.Int,a)]
oldEntries MapEmpty=[]
oldEntries(MapNode _ k v l r)=oldEntries l++[(k,v)]++oldEntries r
oldProof :: Map B.Int a -> Prelude.Maybe(B.Int,[B.Int])
oldProof MapEmpty=Prelude.Just(0,[])
oldProof(MapNode n k _ l r)=do
 (lc,ls)<-oldProof l;(rc,rs)<-oldProof r
 if n==1+lc+rc && all(<k)ls && all(>k)rs
 then Prelude.Just(n,ls++[k]++rs) else Prelude.Nothing
balanced :: [(B.Int,a)] -> Map B.Int a
balanced []=MapEmpty
balanced xs=case splitAt(length xs `div` 2)xs of
 (ls,(k,v):rs)->MapNode(fromIntegral(length xs))k v(balanced ls)(balanced rs)
 _->error "oracle balanced builder: impossible split"

unsigned :: B.Int -> Word64
unsigned=fromIntegral
prefixFor :: [B.Int] -> Prelude.Maybe(B.Int,Word64)
prefixFor []=Prelude.Nothing
prefixFor ks=let ws=map unsigned ks;difference=minimum ws `xor` maximum ws
             in if difference==0 then Prelude.Nothing else
                let mask=bit(63-countLeadingZeros difference)::Word64
                    prefix=(head ws .&. complement(mask-1)) .|. mask
                in Prelude.Just(fromIntegral prefix,mask)
validBranch :: B.Int -> [B.Int] -> [B.Int] -> Bool
validBranch p ls rs=not(null ls || null rs) && case prefixFor(ls++rs)of
 Prelude.Nothing->False
 Prelude.Just(expected,mask)->p==expected && all(\k->unsigned k .&. mask==0)ls && all(\k->unsigned k .&. mask/=0)rs
mapProof :: R.IntMapTree a -> Prelude.Maybe(B.Int,[B.Int])
mapProof R.IntMapNil=Prelude.Just(0,[])
mapProof(R.IntMapTip k _)=k `seq` Prelude.Just(1,[k])
mapProof(R.IntMapBin n p l r)=do
 (lc,ls)<-mapProof l;(rc,rs)<-mapProof r
 if n==lc+rc && validBranch p ls rs then Prelude.Just(n,ls++rs) else Prelude.Nothing
setProof :: R.IntSetTree -> Prelude.Maybe(B.Int,[B.Int])
setProof R.IntSetNil=Prelude.Just(0,[])
setProof(R.IntSetTip n p bits)=
 if p .&. 63==0 && bits/=0 && n==fromIntegral(popCount(unsigned bits))
 then Prelude.Just(n,[p .|. fromIntegral i|i<-[0..63],testBit bits i]) else Prelude.Nothing
setProof(R.IntSetBin n p l r)=do
 (lc,ls)<-setProof l;(rc,rs)<-setProof r
 if n==lc+rc && validBranch p ls rs then Prelude.Just(n,ls++rs) else Prelude.Nothing
validMap :: R.IntMap a -> Bool
validMap(R.IntMap t)=case mapProof t of Prelude.Just _->True;_->False
validSet :: R.IntSet -> Bool
validSet(R.IntSet t)=case setProof t of Prelude.Just _->True;_->False
mapEntries :: R.IntMap a -> [(B.Int,a)]
mapEntries(R.IntMap t)=sortOn fst(go t) where
 go R.IntMapNil=[]
 go(R.IntMapTip k v)=[(k,v)]
 go(R.IntMapBin _ _ l r)=go l++go r
setEntries :: R.IntSet -> [B.Int]
setEntries(R.IntSet t)=sortOn id(go t) where
 go R.IntSetNil=[]
 go(R.IntSetTip _ p bits)=[p .|. fromIntegral i|i<-[0..63],testBit bits i]
 go(R.IntSetBin _ _ l r)=go l++go r
unwrapMap :: R.IntMap a -> Map B.Int a
unwrapMap m=if validMap m then balanced(mapEntries m) else error "oracle bridge: invalid Patricia map"
unwrapSet :: R.IntSet -> Map B.Int ()
unwrapSet s=if validSet s then balanced[(k,())|k<-setEntries s] else error "oracle bridge: invalid Patricia set"
wrapMap :: Map B.Int a -> R.IntMap a
wrapMap t=case oldProof t of
 Prelude.Nothing->error "oracle bridge: invalid BST map"
 Prelude.Just _->let tree=build(sortOn(unsigned.fst)(oldEntries t)) in tree `seq` R.IntMap tree
 where
 build []=R.IntMapNil
 build [(k,v)]=k `seq` R.IntMapTip k v
 build xs=case prefixFor(map fst xs)of
  Prelude.Nothing->error "oracle bridge: duplicate map key"
  Prelude.Just(p,mask)->let { (ls,rs)=span(\(k,_)->unsigned k .&. mask==0)xs;
                            l=build ls;r=build rs;n=fromIntegral(length xs) }
                       in n `seq` p `seq` l `seq` r `seq` R.IntMapBin n p l r
wrapSet :: Map B.Int () -> R.IntSet
wrapSet t=case oldProof t of
 Prelude.Nothing->error "oracle bridge: invalid BST set"
 Prelude.Just _->let tree=build(sortOn unsigned(map fst(oldEntries t))) in tree `seq` R.IntSet tree
 where
 build []=R.IntSetNil
 build ks=let p=head ks .&. complement 63;n=fromIntegral(length ks) in
  if all(\k->k .&. complement 63==p)ks
  then let bitmap=foldl(\b k->setBit b(fromIntegral(k .&. 63)))0 ks
       in n `seq` p `seq` bitmap `seq` R.IntSetTip n p bitmap
  else case prefixFor ks of
   Prelude.Nothing->error "oracle bridge: duplicate set key"
   Prelude.Just(q,mask)->let (ls,rs)=span(\k->unsigned k .&. mask==0)ks;l=build ls;r=build rs
                        in n `seq` q `seq` l `seq` r `seq` R.IntSetBin n q l r
sameMap :: (a->b->Bool) -> R.IntMap a -> R.IntMap b -> Bool
sameMap eq (R.IntMap a)(R.IntMap b)=go a b where
 go R.IntMapNil R.IntMapNil=True
 go(R.IntMapTip k v)(R.IntMapTip j w)=k==j && eq v w
 go(R.IntMapBin n p l r)(R.IntMapBin m q s t)=n==m && p==q && go l s && go r t
 go _ _=False
sameSet :: R.IntSet -> R.IntSet -> Bool
sameSet(R.IntSet a)(R.IntSet b)=go a b where
 go R.IntSetNil R.IntSetNil=True
 go(R.IntSetTip n p x)(R.IntSetTip m q y)=n==m && p==q && x==y
 go(R.IntSetBin n p l r)(R.IntSetBin m q s t)=n==m && p==q && go l s && go r t
 go _ _=False
