-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- Adapted from containers-0.8.1 Data.IntMap.Internal (lazy values).
-- Copyright (c) Daan Leijen 2002; Andriy Palamarchuk 2008; wren romano 2016.
-- BSD-3-Clause; see tools/release/licenses/containers-0.8.1.txt.
-- The Glasgow Haskell Compiler License
--
-- Copyright 2004, The University Court of the University of Glasgow.
-- All rights reserved.
--
-- Redistribution and use in source and binary forms, with or without
-- modification, are permitted provided that the following conditions are met:
--
-- - Redistributions of source code must retain the above copyright notice,
-- this list of conditions and the following disclaimer.
--
-- - Redistributions in binary form must reproduce the above copyright notice,
-- this list of conditions and the following disclaimer in the documentation
-- and/or other materials provided with the distribution.
--
-- - Neither name of the University nor the names of its contributors may be
-- used to endorse or promote products derived from this software without
-- specific prior written permission.
--
-- THIS SOFTWARE IS PROVIDED BY THE UNIVERSITY COURT OF THE UNIVERSITY OF
-- GLASGOW AND THE CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
-- INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
-- FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
-- UNIVERSITY COURT OF THE UNIVERSITY OF GLASGOW OR THE CONTRIBUTORS BE LIABLE
-- FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
-- DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
-- SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
-- CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
-- LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
-- OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
-- DAMAGE.
module Bootstrap.IntMap where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.IntTree as P;
  import qualified Bootstrap.IntSet as IS;
  data AscStack a = NoStack | Push Int (IntMapTree a) (AscStack a);
  data AscState a = NoState | State Int a (AscStack a);
  sizeTree :: forall a. IntMapTree a -> Int;
  sizeTree tree = case tree of {
    IntMapNil -> 0; IntMapTip key value -> 1;
    IntMapBin count prefix left right -> count
  };
  tip :: forall a. Int -> a -> IntMapTree a;
  tip key value = seq key (IntMapTip key value);
  node :: forall a. Int -> IntMapTree a -> IntMapTree a -> IntMapTree a;
  node prefix left right = let { count = sizeTree left + sizeTree right } in
    seq count (seq prefix (seq left (seq right (IntMapBin count prefix left right))));
  bin :: forall a. Int -> IntMapTree a -> IntMapTree a -> IntMapTree a;
  bin prefix left right = case left of {
    IntMapNil -> right;
    _ -> case right of { IntMapNil -> left; _ -> node prefix left right }
  };
  link :: forall a. Int -> IntMapTree a -> Int -> IntMapTree a -> IntMapTree a;
  link a left b right = let { prefix = P.mask a (P.branchMask a b) } in
    if P.left a prefix then node prefix left right else node prefix right left;
  wrap :: forall a. IntMapTree a -> IntMap a;
  wrap tree = seq tree (IntMap tree);
  empty :: forall a. IntMap a;
  empty = wrap IntMapNil;
  singleton :: forall a. Int -> a -> IntMap a;
  singleton key value = wrap (tip key value);
  null :: forall a. IntMap a -> Bool;
  null (IntMap tree) = case tree of { IntMapNil -> True; _ -> False };
  size :: forall a. IntMap a -> Int;
  size (IntMap tree) = sizeTree tree;
  lookupTree :: forall a. Int -> IntMapTree a -> Maybe a;
  lookupTree key tree = case tree of {
    IntMapNil -> Nothing;
    IntMapTip previous value -> if key == previous then Just value else Nothing;
    IntMapBin count prefix left right ->
      if P.left key prefix then lookupTree key left else lookupTree key right
  };
  memberTree :: forall a. Int -> IntMapTree a -> Bool;
  memberTree key tree = case lookupTree key tree of { Nothing -> False; Just value -> True };
  lookup :: forall a. Int -> IntMap a -> Maybe a;
  lookup key (IntMap tree) = lookupTree key tree;
  get :: forall a. Int -> IntMap a -> a;
  get key tree = case lookup key tree of { Nothing -> panic "map key not found"; Just value -> value };
  findWithDefault :: forall a. a -> Int -> IntMap a -> a;
  findWithDefault fallback key tree = L.fromMaybe fallback (lookup key tree);
  member :: forall a. Int -> IntMap a -> Bool;
  member key (IntMap tree) = memberTree key tree;
  notMember :: forall a. Int -> IntMap a -> Bool;
  notMember key tree = L.not (member key tree);
  insertTree :: forall a. Int -> a -> IntMapTree a -> IntMapTree a;
  insertTree key value tree = case tree of {
    IntMapNil -> tip key value;
    IntMapTip previous old -> if key == previous then tip key value
      else link key (tip key value) previous tree;
    IntMapBin count prefix left right ->
      if P.nomatch key prefix then link key (tip key value) prefix tree
      else if P.left key prefix then node prefix (insertTree key value left) right
      else node prefix left (insertTree key value right)
  };
  insertWithTree :: forall a. (a -> a -> a) -> Int -> a -> IntMapTree a -> IntMapTree a;
  insertWithTree combine key value tree = case tree of {
    IntMapNil -> tip key value;
    IntMapTip previous old -> if key == previous then tip key (combine value old)
      else link key (tip key value) previous tree;
    IntMapBin count prefix left right ->
      if P.nomatch key prefix then link key (tip key value) prefix tree
      else if P.left key prefix then node prefix (insertWithTree combine key value left) right
      else node prefix left (insertWithTree combine key value right)
  };
  insert :: forall a. Int -> a -> IntMap a -> IntMap a;
  insert key value (IntMap tree) = wrap (insertTree key value tree);
  insertWith :: forall a. (a -> a -> a) -> Int -> a -> IntMap a -> IntMap a;
  insertWith combine key value (IntMap tree) = wrap (insertWithTree combine key value tree);
  insertWithKey :: forall a. (Int -> a -> a -> a) -> Int -> a -> IntMap a -> IntMap a;
  insertWithKey combine key value tree = insertWith (combine key) key value tree;
  deleteTree :: forall a. Int -> IntMapTree a -> IntMapTree a;
  deleteTree key tree = case tree of {
    IntMapNil -> IntMapNil;
    IntMapTip previous value -> if key == previous then IntMapNil else tree;
    IntMapBin count prefix left right ->
      if P.nomatch key prefix then tree
      else if P.left key prefix then bin prefix (deleteTree key left) right
      else bin prefix left (deleteTree key right)
  };
  delete :: forall a. Int -> IntMap a -> IntMap a;
  delete key (IntMap tree) = wrap (deleteTree key tree);
  adjustTree :: forall a. (Int -> a -> a) -> Int -> IntMapTree a -> IntMapTree a;
  adjustTree action key tree = case tree of {
    IntMapNil -> IntMapNil;
    IntMapTip previous value -> if key == previous then tip key (action key value) else tree;
    IntMapBin count prefix left right ->
      if P.nomatch key prefix then tree
      else if P.left key prefix then node prefix (adjustTree action key left) right
      else node prefix left (adjustTree action key right)
  };
  adjustWithKey :: forall a. (Int -> a -> a) -> Int -> IntMap a -> IntMap a;
  adjustWithKey action key (IntMap tree) = wrap (adjustTree action key tree);
  adjust :: forall a. (a -> a) -> Int -> IntMap a -> IntMap a;
  adjust action key tree = adjustWithKey (\key value -> action value) key tree;
  alterMissing :: forall a. (Maybe a -> Maybe a) -> Int -> Int -> IntMapTree a -> IntMapTree a;
  alterMissing action key prefix tree = case action Nothing of {
    Nothing -> tree; Just value -> link key (tip key value) prefix tree
  };
  alterTree :: forall a. (Maybe a -> Maybe a) -> Int -> IntMapTree a -> IntMapTree a;
  alterTree action key tree = case tree of {
    IntMapNil -> case action Nothing of { Nothing -> IntMapNil; Just value -> tip key value };
    IntMapTip previous old ->
      if key == previous then case action (Just old) of {
        Nothing -> IntMapNil; Just value -> tip key value
      } else alterMissing action key previous tree;
    IntMapBin count prefix left right ->
      if P.nomatch key prefix then alterMissing action key prefix tree
      else if P.left key prefix then bin prefix (alterTree action key left) right
      else bin prefix left (alterTree action key right)
  };
  alter :: forall a. (Maybe a -> Maybe a) -> Int -> IntMap a -> IntMap a;
  alter action key (IntMap tree) = wrap (alterTree action key tree);
  update :: forall a. (a -> Maybe a) -> Int -> IntMap a -> IntMap a;
  update action key tree = alter (\old -> case old of { Nothing -> Nothing; Just value -> action value }) key tree;
  mapTree :: forall a b. (Int -> a -> b) -> IntMapTree a -> IntMapTree b;
  mapTree action tree = case tree of {
    IntMapNil -> IntMapNil;
    IntMapTip key value -> tip key (action key value);
    IntMapBin count prefix left right -> node prefix (mapTree action left) (mapTree action right)
  };
  mapWithKey :: forall a b. (Int -> a -> b) -> IntMap a -> IntMap b;
  mapWithKey action (IntMap tree) = wrap (mapTree action tree);
  map :: forall a b. (a -> b) -> IntMap a -> IntMap b;
  map action tree = mapWithKey (\key value -> action value) tree;
  mapMaybeTree :: forall a b. (Int -> a -> Maybe b) -> IntMapTree a -> IntMapTree b;
  mapMaybeTree action tree = case tree of {
    IntMapNil -> IntMapNil;
    IntMapTip key value -> case action key value of { Nothing -> IntMapNil; Just result -> tip key result };
    IntMapBin count prefix left right -> bin prefix (mapMaybeTree action left) (mapMaybeTree action right)
  };
  mapMaybeWithKey :: forall a b. (Int -> a -> Maybe b) -> IntMap a -> IntMap b;
  mapMaybeWithKey action (IntMap tree) = wrap (mapMaybeTree action tree);
  mapMaybe :: forall a b. (a -> Maybe b) -> IntMap a -> IntMap b;
  mapMaybe action tree = mapMaybeWithKey (\key value -> action value) tree;
  foldrTree :: forall a b. (Int -> a -> b -> b) -> b -> IntMapTree a -> b;
  foldrTree action result tree = case tree of {
    IntMapNil -> result;
    IntMapTip key value -> action key value result;
    IntMapBin count prefix left right ->
      if P.signBranch prefix then foldrTree action (foldrTree action result left) right
      else foldrTree action (foldrTree action result right) left
  };
  foldrWithKey :: forall a b. (Int -> a -> b -> b) -> b -> IntMap a -> b;
  foldrWithKey action result (IntMap tree) = foldrTree action result tree;
  foldr :: forall a b. (a -> b -> b) -> b -> IntMap a -> b;
  foldr action result tree = foldrWithKey (\key value rest -> action value rest) result tree;
  foldlTree :: forall a b. (b -> Int -> a -> b) -> b -> IntMapTree a -> b;
  foldlTree action result tree = case tree of {
    IntMapNil -> result;
    IntMapTip key value -> action result key value;
    IntMapBin count prefix left right ->
      if P.signBranch prefix then foldlTree action (foldlTree action result right) left
      else foldlTree action (foldlTree action result left) right
  };
  foldlWithKey :: forall a b. (b -> Int -> a -> b) -> b -> IntMap a -> b;
  foldlWithKey action result (IntMap tree) = foldlTree action result tree;
  foldl :: forall a b. (b -> a -> b) -> b -> IntMap a -> b;
  foldl action result tree = foldlWithKey (\rest key value -> action rest value) result tree;
  toList :: forall a. IntMap a -> [] ((,) Int a);
  toList tree = foldrWithKey (\key value rest -> (:) ((,) key value) rest) [] tree;
  toAscList :: forall a. IntMap a -> [] ((,) Int a);
  toAscList tree = toList tree;
  keys :: forall a. IntMap a -> [] Int;
  keys tree = foldrWithKey (\key value rest -> (:) key rest) [] tree;
  elems :: forall a. IntMap a -> [] a;
  elems tree = foldr (:) [] tree;
  keysBitmap :: forall a. IntMapTree a -> Int;
  keysBitmap tree = case tree of {
    IntMapNil -> 0; IntMapTip key value -> P.bitmapOf key;
    IntMapBin count prefix left right -> orInt (keysBitmap left) (keysBitmap right)
  };
  keysSetTree :: forall a. IntMapTree a -> IntSetTree;
  keysSetTree tree = case tree of {
    IntMapNil -> IntSetNil;
    IntMapTip key value -> IS.tip (P.prefixOf key) (P.bitmapOf key);
    IntMapBin count prefix left right ->
      if P.suffixOf prefix /= 0 then IS.tip (P.prefixOf prefix) (keysBitmap tree)
      else IS.node prefix (keysSetTree left) (keysSetTree right)
  };
  keysSet :: forall a. IntMap a -> IntSet;
  keysSet (IntMap tree) = IS.wrap (keysSetTree tree);
  fromList :: forall a. [] ((,) Int a) -> IntMap a;
  fromList entries = wrap (L.foldlStrict (\tree ((,) key value) -> insertTree key value tree) IntMapNil entries);
  fromListWith :: forall a. (a -> a -> a) -> [] ((,) Int a) -> IntMap a;
  fromListWith combine entries = wrap
    (L.foldlStrict (\tree ((,) key value) -> insertWithTree combine key value tree) IntMapNil entries);
  ascLinkTop :: forall a. AscStack a -> Int -> IntMapTree a -> Int -> AscStack a;
  ascLinkTop stack key right bit = case stack of {
    NoStack -> Push bit right stack;
    Push old left rest -> if P.unsignedLess old bit
      then ascLinkTop rest key (node (P.mask key old) left right) bit else Push bit right stack
  };
  ascInsert :: forall a. AscState a -> (,) Int a -> AscState a;
  ascInsert state ((,) key value) = case state of {
    NoState -> seq key (State key value NoStack);
    State previous old stack ->
      if key == previous then State key value stack
      else let { rest = ascLinkTop stack previous (tip previous old) (P.branchMask previous key) } in
        seq rest (State key value rest)
  };
  ascLinkStack :: forall a. AscStack a -> Int -> IntMapTree a -> IntMapTree a;
  ascLinkStack stack key right = case stack of {
    NoStack -> right;
    Push bit left rest -> let { prefix = P.mask key bit } in
      if P.signBranch prefix then node prefix right left
      else ascLinkStack rest key (node prefix left right)
  };
  fromDistinctAscList :: forall a. [] ((,) Int a) -> IntMap a;
  fromDistinctAscList entries = wrap (case L.foldlStrict ascInsert NoState entries of {
    NoState -> IntMapNil;
    State key value stack -> ascLinkStack stack key (tip key value)
  });
  unionTree :: forall a. (a -> a -> a) -> IntMapTree a -> IntMapTree a -> IntMapTree a;
  unionTree combine a b = case a of {
    IntMapNil -> b;
    IntMapTip key value -> insertWithTree combine key value b;
    IntMapBin count prefix left right -> case b of {
      IntMapNil -> a;
      IntMapTip key value -> insertWithTree (\new old -> combine old new) key value a;
      IntMapBin other second x y -> case P.relation prefix second of {
        IntTreeABL -> node prefix (unionTree combine left b) right;
        IntTreeABR -> node prefix left (unionTree combine right b);
        IntTreeBAL -> node second (unionTree combine a x) y;
        IntTreeBAR -> node second x (unionTree combine a y);
        IntTreeEQL -> node prefix (unionTree combine left x) (unionTree combine right y);
        IntTreeNOM -> link prefix a second b
      }
    }
  };
  unionWith :: forall a. (a -> a -> a) -> IntMap a -> IntMap a -> IntMap a;
  unionWith combine (IntMap a) (IntMap b) = wrap (unionTree combine a b);
  union :: forall a. IntMap a -> IntMap a -> IntMap a;
  union a b = unionWith (\left right -> left) a b;
  unions :: forall a. [] (IntMap a) -> IntMap a;
  unions trees = L.foldlStrict union empty trees;
  differenceTree :: forall a b. IntMapTree a -> IntMapTree b -> IntMapTree a;
  differenceTree a b = case a of {
    IntMapNil -> IntMapNil;
    IntMapTip key value -> if memberTree key b then IntMapNil else a;
    IntMapBin count prefix left right -> case b of {
      IntMapNil -> a;
      IntMapTip key value -> deleteTree key a;
      IntMapBin other second x y -> case P.relation prefix second of {
        IntTreeABL -> bin prefix (differenceTree left b) right;
        IntTreeABR -> bin prefix left (differenceTree right b);
        IntTreeBAL -> differenceTree a x;
        IntTreeBAR -> differenceTree a y;
        IntTreeEQL -> bin prefix (differenceTree left x) (differenceTree right y);
        IntTreeNOM -> a
      }
    }
  };
  difference :: forall a b. IntMap a -> IntMap b -> IntMap a;
  difference (IntMap a) (IntMap b) = wrap (differenceTree a b);
  intersectionTree :: forall a b c. (a -> b -> c) -> IntMapTree a -> IntMapTree b -> IntMapTree c;
  intersectionTree combine a b = case a of {
    IntMapNil -> IntMapNil;
    IntMapTip key value -> case lookupTree key b of { Nothing -> IntMapNil; Just other -> tip key (combine value other) };
    IntMapBin count prefix left right -> case b of {
      IntMapNil -> IntMapNil;
      IntMapTip key value -> case lookupTree key a of { Nothing -> IntMapNil; Just other -> tip key (combine other value) };
      IntMapBin other second x y -> case P.relation prefix second of {
        IntTreeABL -> intersectionTree combine left b;
        IntTreeABR -> intersectionTree combine right b;
        IntTreeBAL -> intersectionTree combine a x;
        IntTreeBAR -> intersectionTree combine a y;
        IntTreeEQL -> bin prefix (intersectionTree combine left x) (intersectionTree combine right y);
        IntTreeNOM -> IntMapNil
      }
    }
  };
  intersectionWith :: forall a b c. (a -> b -> c) -> IntMap a -> IntMap b -> IntMap c;
  intersectionWith combine (IntMap a) (IntMap b) = wrap (intersectionTree combine a b);
  intersection :: forall a b. IntMap a -> IntMap b -> IntMap a;
  intersection a b = intersectionWith (\left right -> left) a b;
  filterWithKey :: forall a. (Int -> a -> Bool) -> IntMap a -> IntMap a;
  filterWithKey predicate tree = mapMaybeWithKey (\key value -> if predicate key value then Just value else Nothing) tree;
  filter :: forall a. (a -> Bool) -> IntMap a -> IntMap a;
  filter predicate tree = filterWithKey (\key value -> predicate value) tree;
  lookupMinTree :: forall a. IntMapTree a -> Maybe ((,) Int a);
  lookupMinTree tree = case tree of {
    IntMapNil -> Nothing; IntMapTip key value -> Just ((,) key value);
    IntMapBin count prefix left right -> lookupMinTree (if P.signBranch prefix then right else left)
  };
  lookupMaxTree :: forall a. IntMapTree a -> Maybe ((,) Int a);
  lookupMaxTree tree = case tree of {
    IntMapNil -> Nothing; IntMapTip key value -> Just ((,) key value);
    IntMapBin count prefix left right -> lookupMaxTree (if P.signBranch prefix then left else right)
  };
  lookupMin :: forall a. IntMap a -> Maybe ((,) Int a);
  lookupMin (IntMap tree) = lookupMinTree tree;
  lookupMax :: forall a. IntMap a -> Maybe ((,) Int a);
  lookupMax (IntMap tree) = lookupMaxTree tree;
  findMin :: forall a. IntMap a -> (,) Int a;
  findMin tree = case lookupMin tree of { Nothing -> panic "findMin: empty map"; Just result -> result };
  findMax :: forall a. IntMap a -> (,) Int a;
  findMax tree = case lookupMax tree of { Nothing -> panic "findMax: empty map"; Just result -> result };
  minViewTree :: forall a. IntMapTree a -> Maybe ((,) ((,) Int a) (IntMapTree a));
  minViewTree tree = case tree of {
    IntMapNil -> Nothing; IntMapTip key value -> Just ((,) ((,) key value) IntMapNil);
    IntMapBin count prefix left right ->
      if P.signBranch prefix
      then L.mapOptional (\((,) item rest) -> (,) item (bin prefix left rest)) (minViewTree right)
      else L.mapOptional (\((,) item rest) -> (,) item (bin prefix rest right)) (minViewTree left)
  };
  minViewWithKey :: forall a. IntMap a -> Maybe ((,) ((,) Int a) (IntMap a));
  minViewWithKey (IntMap tree) = L.mapOptional (\((,) item rest) -> (,) item (wrap rest)) (minViewTree tree);
  lookupIndexTree :: forall a. Int -> Int -> IntMapTree a -> Maybe Int;
  lookupIndexTree key offset tree = case tree of {
    IntMapNil -> Nothing;
    IntMapTip previous value -> if key == previous then Just offset else Nothing;
    IntMapBin count prefix left right ->
      if P.left key prefix then lookupIndexTree key (offset + (if P.signBranch prefix then sizeTree right else 0)) left
      else lookupIndexTree key (offset + (if P.signBranch prefix then 0 else sizeTree left)) right
  };
  lookupIndex :: forall a. Int -> IntMap a -> Maybe Int;
  lookupIndex key (IntMap tree) = lookupIndexTree key 0 tree;
  elemAtTree :: forall a. Int -> IntMapTree a -> Maybe ((,) Int a);
  elemAtTree position tree =
    if position < 0 || position >= sizeTree tree then Nothing else case tree of {
      IntMapNil -> Nothing;
      IntMapTip key value -> Just ((,) key value);
      IntMapBin count prefix left right ->
        if P.signBranch prefix then
          if position < sizeTree right then elemAtTree position right else elemAtTree (position - sizeTree right) left
        else if position < sizeTree left then elemAtTree position left else elemAtTree (position - sizeTree left) right
    };
  elemAt :: forall a. Int -> IntMap a -> Maybe ((,) Int a);
  elemAt position (IntMap tree) = elemAtTree position tree;
  eqIntMap :: forall a. (a -> a -> Bool) -> IntMap a -> IntMap a -> Bool;
  eqIntMap equal a b = size a == size b && L.eqList (L.eqPair eqInt equal) (toList a) (toList b);
  -- Check one routing edge without evaluating a stored value or cached count.
  -- Recursing with this predicate proves that enumeration agrees with lookup;
  -- ascending leaves alone do not establish that for a Patricia tree.
  childRouting :: forall a. Bool -> Int -> IntMapTree a -> Bool;
  childRouting leftSide prefix child = case child of {
    IntMapNil -> False;
    IntMapTip key value -> L.not (P.nomatch key prefix) && (P.left key prefix == leftSide);
    IntMapBin count childPrefix left right ->
      case P.relation prefix childPrefix of {
        IntTreeABL -> leftSide;
        IntTreeABR -> L.not leftSide;
        _ -> False
      }
  };
  validTree :: forall a. IntMapTree a -> Bool;
  validTree tree = case tree of {
    IntMapNil -> True; IntMapTip key value -> seq key True;
    IntMapBin count prefix left right -> prefix /= 0 &&
      sizeTree left > 0 && sizeTree right > 0 && count == sizeTree left + sizeTree right &&
      foldrTree (\key value rest -> L.not (P.nomatch key prefix) && P.left key prefix && rest) True left &&
      foldrTree (\key value rest -> L.not (P.nomatch key prefix) && L.not (P.left key prefix) && rest) True right &&
      validTree left && validTree right
  };
  valid :: forall a. IntMap a -> Bool;
  valid (IntMap tree) = validTree tree
}
