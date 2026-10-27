-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.IntSet where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;
  wrap :: Map Int () -> IntSet;
  wrap tree = seq tree (IntSet tree);
  empty :: IntSet;
  empty = wrap M.empty;
  singleton :: Int -> IntSet;
  singleton value = wrap (M.singleton value ());
  null :: IntSet -> Bool;
  null (IntSet tree) = M.null tree;
  size :: IntSet -> Int;
  size (IntSet tree) = M.size tree;
  member :: Int -> IntSet -> Bool;
  member value (IntSet tree) = IM.memberTree value tree;
  notMember :: Int -> IntSet -> Bool;
  notMember value tree = L.not (member value tree);
  insert :: Int -> IntSet -> IntSet;
  insert value (IntSet tree) = wrap (IM.insertTree value () tree);
  delete :: Int -> IntSet -> IntSet;
  delete value (IntSet tree) = wrap (IM.deleteTree value tree);
  fromList :: [] Int -> IntSet;
  fromList values =
    wrap (L.foldlStrict (\tree value -> IM.insertTree value () tree) M.empty values);
  fromDistinctAscList :: [] Int -> IntSet;
  fromDistinctAscList values =
    wrap (M.fromDistinctAscList (L.map (\value -> (,) value ()) values));
  toList :: IntSet -> [] Int;
  toList (IntSet tree) = M.keys tree;
  toAscList :: IntSet -> [] Int;
  toAscList tree = toList tree;
  union :: IntSet -> IntSet -> IntSet;
  -- Set union is commutative. Reuse the larger tree rather than reconstructing
  -- an entire component when adding just a few enclosing scope identities.
  union (IntSet a) (IntSet b) =
    if (M.size a <= M.size b)
    then wrap (M.foldlWithKeyStrict (\tree key value -> IM.insertTree key () tree) b a)
    else wrap (M.foldlWithKeyStrict (\tree key value -> IM.insertTree key () tree) a b);
  unions :: [] IntSet -> IntSet;
  unions trees = L.foldlStrict union empty trees;
  difference :: IntSet -> IntSet -> IntSet;
  difference (IntSet a) (IntSet b) =
    wrap (M.foldlWithKeyStrict (\tree key value -> IM.deleteTree key tree) a b);
  intersection :: IntSet -> IntSet -> IntSet;
  intersection (IntSet a) (IntSet b) = wrap (M.intersection L.compareInt a b);
  isSubsetOf :: IntSet -> IntSet -> Bool;
  isSubsetOf a b = ((size a <= size b) && L.all (\value -> member value b) (toList a));
  isProperSubsetOf :: IntSet -> IntSet -> Bool;
  isProperSubsetOf a b = ((size a < size b) && isSubsetOf a b);
  disjoint :: IntSet -> IntSet -> Bool;
  disjoint a b = null (intersection a b);
  filter :: (Int -> Bool) -> IntSet -> IntSet;
  filter predicate (IntSet tree) = wrap (M.filterWithKey (\key value -> predicate key) tree);
  map :: (Int -> Int) -> IntSet -> IntSet;
  map f tree = fromList (L.map f (toList tree));
  foldr :: forall a. (Int -> a -> a) -> a -> IntSet -> a;
  foldr f z tree = L.foldr f z (toList tree);
  foldl :: forall a. (a -> Int -> a) -> a -> IntSet -> a;
  foldl f z tree = L.foldl f z (toList tree);
  lookupMin :: IntSet -> Maybe Int;
  lookupMin (IntSet tree) = L.mapOptional L.fst (M.lookupMin tree);
  lookupMax :: IntSet -> Maybe Int;
  lookupMax (IntSet tree) = L.mapOptional L.fst (M.lookupMax tree);
  findMin :: IntSet -> Int;
  findMin (IntSet tree) = L.fst (M.findMin tree);
  findMax :: IntSet -> Int;
  findMax (IntSet tree) = L.fst (M.findMax tree);
  minView :: IntSet -> Maybe ((,) Int IntSet);
  minView (IntSet tree) =
    L.mapOptional
      (\entry ->
         case entry of {
           (,) ((,) key value) rest -> (,) key (wrap rest)
         })
      (M.minViewWithKey tree);
  maxView :: IntSet -> Maybe ((,) Int IntSet);
  maxView (IntSet tree) =
    L.mapOptional
      (\entry ->
         case entry of {
           (,) ((,) key value) rest -> (,) key (wrap rest)
         })
      (M.maxViewWithKey tree);
  eqIntSet :: IntSet -> IntSet -> Bool;
  eqIntSet a b = ((size a == size b) && L.eqList eqInt (toList a) (toList b))
}
