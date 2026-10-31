-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- Adapted from containers-0.8.1 Data.IntSet.Internal.
-- Copyright (c) Daan Leijen 2002; Joachim Breitner 2011.
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
module Bootstrap.IntSet where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.IntTree as P;
  import qualified Bootstrap.IntRank as Rank;
  data AscStack = NoStack | Push Int IntSetTree AscStack;
  data AscState = NoState | State Int Int AscStack;
  sizeTree :: IntSetTree -> Int;
  sizeTree tree = case tree of {
    IntSetNil -> 0; IntSetTip count prefix bits -> count;
    IntSetBin count prefix left right -> count
  };
  tip :: Int -> Int -> IntSetTree;
  tip prefix bits = if bits == 0 then IntSetNil
    else let { count = popCountInt bits } in
      seq prefix (seq count (IntSetTip count prefix bits));
  node :: Int -> IntSetTree -> IntSetTree -> IntSetTree;
  node prefix left right = let { count = sizeTree left + sizeTree right } in
    seq count (seq prefix (seq left (seq right (IntSetBin count prefix left right))));
  bin :: Int -> IntSetTree -> IntSetTree -> IntSetTree;
  bin prefix left right = case left of {
    IntSetNil -> right;
    _ -> case right of { IntSetNil -> left; _ -> node prefix left right }
  };
  link :: Int -> IntSetTree -> Int -> IntSetTree -> IntSetTree;
  link a left b right = let { prefix = P.mask a (P.branchMask a b) } in
    if P.left a prefix then node prefix left right else node prefix right left;
  wrap :: IntSetTree -> IntSet;
  wrap tree = seq tree (IntSet tree);
  empty :: IntSet;
  empty = wrap IntSetNil;
  singleton :: Int -> IntSet;
  singleton key = wrap (tip (P.prefixOf key) (P.bitmapOf key));
  null :: IntSet -> Bool;
  null (IntSet tree) = case tree of { IntSetNil -> True; _ -> False };
  size :: IntSet -> Int;
  size (IntSet tree) = sizeTree tree;
  memberTree :: Int -> IntSetTree -> Bool;
  memberTree key tree = case tree of {
    IntSetNil -> False;
    IntSetTip count prefix bits ->
      P.prefixOf key == prefix && andInt bits (P.bitmapOf key) /= 0;
    IntSetBin count prefix left right ->
      if P.left key prefix then memberTree key left else memberTree key right
  };
  member :: Int -> IntSet -> Bool;
  member key (IntSet tree) = memberTree key tree;
  notMember :: Int -> IntSet -> Bool;
  notMember key tree = L.not (member key tree);
  insertBM :: Int -> Int -> IntSetTree -> IntSetTree;
  insertBM key bits tree = case tree of {
    IntSetNil -> tip key bits;
    IntSetTip count prefix old ->
      if key == prefix then tip key (orInt bits old)
      else link key (tip key bits) prefix tree;
    IntSetBin count prefix left right ->
      if P.nomatch key prefix then link key (tip key bits) prefix tree
      else if P.left key prefix then node prefix (insertBM key bits left) right
      else node prefix left (insertBM key bits right)
  };
  insert :: Int -> IntSet -> IntSet;
  insert key (IntSet tree) = wrap (insertBM (P.prefixOf key) (P.bitmapOf key) tree);
  deleteBM :: Int -> Int -> IntSetTree -> IntSetTree;
  deleteBM key bits tree = case tree of {
    IntSetNil -> IntSetNil;
    IntSetTip count prefix old ->
      if key == prefix then tip prefix (andInt old (P.complement bits)) else tree;
    IntSetBin count prefix left right ->
      if P.nomatch key prefix then tree
      else if P.left key prefix then bin prefix (deleteBM key bits left) right
      else bin prefix left (deleteBM key bits right)
  };
  delete :: Int -> IntSet -> IntSet;
  delete key (IntSet tree) = wrap (deleteBM (P.prefixOf key) (P.bitmapOf key) tree);
  fromList :: [] Int -> IntSet;
  fromList values = L.foldlStrict (\tree key -> insert key tree) empty values;
  ascLinkTop :: AscStack -> Int -> IntSetTree -> Int -> AscStack;
  ascLinkTop stack key right bit = case stack of {
    NoStack -> Push bit right stack;
    Push old left rest ->
      if P.unsignedLess old bit
      then ascLinkTop rest key (node (P.mask key old) left right) bit
      else Push bit right stack
  };
  ascInsert :: AscState -> Int -> AscState;
  ascInsert state key = let { prefix = P.prefixOf key; bits = P.bitmapOf key } in
    case state of {
      NoState -> seq prefix (seq bits (State prefix bits NoStack));
      State previous old stack ->
        if prefix == previous then let { combined = orInt old bits } in
          seq combined (State prefix combined stack)
        else let { rest = ascLinkTop stack previous (tip previous old) (P.branchMask previous prefix) } in
          seq bits (seq rest (State prefix bits rest))
    };
  ascLinkStack :: AscStack -> Int -> IntSetTree -> IntSetTree;
  ascLinkStack stack key right = case stack of {
    NoStack -> right;
    Push bit left rest -> let { prefix = P.mask key bit } in
      if P.signBranch prefix then node prefix right left
      else ascLinkStack rest key (node prefix left right)
  };
  fromDistinctAscList :: [] Int -> IntSet;
  fromDistinctAscList values = wrap (case L.foldlStrict ascInsert NoState values of {
    NoState -> IntSetNil;
    State key bits stack -> ascLinkStack stack key (tip key bits)
  });
  foldBitmap :: forall a. (Int -> a -> a) -> Int -> Int -> a -> a;
  foldBitmap action prefix bits result =
    if bits == 0 then result
    else action (prefix + countTrailingZerosInt bits)
      (foldBitmap action prefix (andInt bits (bits - 1)) result);
  foldTree :: forall a. (Int -> a -> a) -> a -> IntSetTree -> a;
  foldTree action result tree = case tree of {
    IntSetNil -> result;
    IntSetTip count prefix bits -> foldBitmap action prefix bits result;
    IntSetBin count prefix left right ->
      if P.signBranch prefix then foldTree action (foldTree action result left) right
      else foldTree action (foldTree action result right) left
  };
  foldr :: forall a. (Int -> a -> a) -> a -> IntSet -> a;
  foldr action result (IntSet tree) = foldTree action result tree;
  foldlBitmap :: forall a. (a -> Int -> a) -> a -> Int -> Int -> a;
  foldlBitmap action result prefix bits =
    if bits == 0 then result
    else foldlBitmap action (action result (prefix + countTrailingZerosInt bits))
      prefix (andInt bits (bits - 1));
  foldlTree :: forall a. (a -> Int -> a) -> a -> IntSetTree -> a;
  foldlTree action result tree = case tree of {
    IntSetNil -> result;
    IntSetTip count prefix bits -> foldlBitmap action result prefix bits;
    IntSetBin count prefix left right ->
      if P.signBranch prefix then foldlTree action (foldlTree action result right) left
      else foldlTree action (foldlTree action result left) right
  };
  foldl :: forall a. (a -> Int -> a) -> a -> IntSet -> a;
  foldl action result (IntSet tree) = foldlTree action result tree;
  toList :: IntSet -> [] Int;
  toList tree = foldr (:) [] tree;
  toAscList :: IntSet -> [] Int;
  toAscList tree = toList tree;
  unionTree :: IntSetTree -> IntSetTree -> IntSetTree;
  unionTree a b = case a of {
    IntSetNil -> b;
    IntSetTip count key bits -> insertBM key bits b;
    IntSetBin count prefix left right -> case b of {
      IntSetNil -> a;
      IntSetTip other key bits -> insertBM key bits a;
      IntSetBin other second x y -> case P.relation prefix second of {
        IntTreeABL -> node prefix (unionTree left b) right;
        IntTreeABR -> node prefix left (unionTree right b);
        IntTreeBAL -> node second (unionTree a x) y;
        IntTreeBAR -> node second x (unionTree a y);
        IntTreeEQL -> node prefix (unionTree left x) (unionTree right y);
        IntTreeNOM -> link prefix a second b
      }
    }
  };
  union :: IntSet -> IntSet -> IntSet;
  union (IntSet a) (IntSet b) = wrap (unionTree a b);
  unions :: [] IntSet -> IntSet;
  unions trees = L.foldlStrict union empty trees;
  bitmapAt :: Int -> IntSetTree -> Int;
  bitmapAt key tree = case tree of {
    IntSetNil -> 0;
    IntSetTip count prefix bits -> if key == prefix then bits else 0;
    IntSetBin count prefix left right ->
      if P.left key prefix then bitmapAt key left else bitmapAt key right
  };
  differenceTree :: IntSetTree -> IntSetTree -> IntSetTree;
  differenceTree a b = case a of {
    IntSetNil -> IntSetNil;
    IntSetTip count key bits -> tip key (andInt bits (P.complement (bitmapAt key b)));
    IntSetBin count prefix left right -> case b of {
      IntSetNil -> a;
      IntSetTip other key bits -> deleteBM key bits a;
      IntSetBin other second x y -> case P.relation prefix second of {
        IntTreeABL -> bin prefix (differenceTree left b) right;
        IntTreeABR -> bin prefix left (differenceTree right b);
        IntTreeBAL -> differenceTree a x;
        IntTreeBAR -> differenceTree a y;
        IntTreeEQL -> bin prefix (differenceTree left x) (differenceTree right y);
        IntTreeNOM -> a
      }
    }
  };
  difference :: IntSet -> IntSet -> IntSet;
  difference (IntSet a) (IntSet b) = wrap (differenceTree a b);
  intersectionTree :: IntSetTree -> IntSetTree -> IntSetTree;
  intersectionTree a b = case a of {
    IntSetNil -> IntSetNil;
    IntSetTip count key bits -> tip key (andInt bits (bitmapAt key b));
    IntSetBin count prefix left right -> case b of {
      IntSetNil -> IntSetNil;
      IntSetTip other key bits -> tip key (andInt bits (bitmapAt key a));
      IntSetBin other second x y -> case P.relation prefix second of {
        IntTreeABL -> intersectionTree left b;
        IntTreeABR -> intersectionTree right b;
        IntTreeBAL -> intersectionTree a x;
        IntTreeBAR -> intersectionTree a y;
        IntTreeEQL -> bin prefix (intersectionTree left x) (intersectionTree right y);
        IntTreeNOM -> IntSetNil
      }
    }
  };
  intersection :: IntSet -> IntSet -> IntSet;
  intersection (IntSet a) (IntSet b) = wrap (intersectionTree a b);
  subsetTree :: IntSetTree -> IntSetTree -> Bool;
  subsetTree a b = case a of {
    IntSetNil -> True;
    IntSetTip count key bits -> andInt bits (P.complement (bitmapAt key b)) == 0;
    IntSetBin count prefix left right -> case b of {
      IntSetBin other second x y -> case P.relation prefix second of {
        IntTreeBAL -> subsetTree a x;
        IntTreeBAR -> subsetTree a y;
        IntTreeEQL -> subsetTree left x && subsetTree right y;
        _ -> False
      };
      _ -> False
    }
  };
  isSubsetOf :: IntSet -> IntSet -> Bool;
  isSubsetOf (IntSet a) (IntSet b) = sizeTree a <= sizeTree b && subsetTree a b;
  isProperSubsetOf :: IntSet -> IntSet -> Bool;
  isProperSubsetOf a b = size a < size b && isSubsetOf a b;
  disjointTree :: IntSetTree -> IntSetTree -> Bool;
  disjointTree a b = case a of {
    IntSetNil -> True;
    IntSetTip count key bits -> andInt bits (bitmapAt key b) == 0;
    IntSetBin count prefix left right -> case b of {
      IntSetNil -> True;
      IntSetTip other key bits -> andInt bits (bitmapAt key a) == 0;
      IntSetBin other second x y -> case P.relation prefix second of {
        IntTreeABL -> disjointTree left b;
        IntTreeABR -> disjointTree right b;
        IntTreeBAL -> disjointTree a x;
        IntTreeBAR -> disjointTree a y;
        IntTreeEQL -> disjointTree left x && disjointTree right y;
        IntTreeNOM -> True
      }
    }
  };
  disjoint :: IntSet -> IntSet -> Bool;
  disjoint (IntSet a) (IntSet b) = disjointTree a b;
  filterBitmap :: (Int -> Bool) -> Int -> Int -> Int;
  filterBitmap predicate prefix bits = if bits == 0 then 0
    else let { bit = andInt bits (0 - bits); rest = andInt bits (bits - 1) } in
      if predicate (prefix + countTrailingZerosInt bits)
      then orInt bit (filterBitmap predicate prefix rest)
      else filterBitmap predicate prefix rest;
  filterTree :: (Int -> Bool) -> IntSetTree -> IntSetTree;
  filterTree predicate tree = case tree of {
    IntSetNil -> IntSetNil;
    IntSetTip count prefix bits -> tip prefix (filterBitmap predicate prefix bits);
    IntSetBin count prefix left right -> bin prefix (filterTree predicate left) (filterTree predicate right)
  };
  filter :: (Int -> Bool) -> IntSet -> IntSet;
  filter predicate (IntSet tree) = wrap (filterTree predicate tree);
  map :: (Int -> Int) -> IntSet -> IntSet;
  map action tree = fromList (L.map action (toList tree));
  lookupMinTree :: IntSetTree -> Maybe Int;
  lookupMinTree tree = case tree of {
    IntSetNil -> Nothing;
    IntSetTip count prefix bits -> Just (prefix + countTrailingZerosInt bits);
    IntSetBin count prefix left right -> lookupMinTree (if P.signBranch prefix then right else left)
  };
  lookupMaxTree :: IntSetTree -> Maybe Int;
  lookupMaxTree tree = case tree of {
    IntSetNil -> Nothing;
    IntSetTip count prefix bits -> Just (prefix + (63 - countLeadingZerosInt bits));
    IntSetBin count prefix left right -> lookupMaxTree (if P.signBranch prefix then left else right)
  };
  lookupMin :: IntSet -> Maybe Int;
  lookupMin (IntSet tree) = lookupMinTree tree;
  lookupMax :: IntSet -> Maybe Int;
  lookupMax (IntSet tree) = lookupMaxTree tree;
  findMin :: IntSet -> Int;
  findMin tree = case lookupMin tree of { Nothing -> panic "findMin: empty map"; Just value -> value };
  findMax :: IntSet -> Int;
  findMax tree = case lookupMax tree of { Nothing -> panic "findMax: empty map"; Just value -> value };
  viewTree :: Bool -> IntSetTree -> Maybe ((,) Int IntSetTree);
  viewTree highest tree = case tree of {
    IntSetNil -> Nothing;
    IntSetTip count prefix bits -> let {
      suffix = if highest then 63 - countLeadingZerosInt bits else countTrailingZerosInt bits;
      remaining = andInt bits (P.complement (shiftLInt 1 suffix))
    } in Just ((,) (prefix + suffix) (tip prefix remaining));
    IntSetBin count prefix left right ->
      if (if P.signBranch prefix then highest else L.not highest)
      then L.mapOptional (\((,) key rest) -> (,) key (bin prefix rest right)) (viewTree highest left)
      else L.mapOptional (\((,) key rest) -> (,) key (bin prefix left rest)) (viewTree highest right)
  };
  minView :: IntSet -> Maybe ((,) Int IntSet);
  minView (IntSet tree) = L.mapOptional (\((,) key rest) -> (,) key (wrap rest)) (viewTree False tree);
  maxView :: IntSet -> Maybe ((,) Int IntSet);
  maxView (IntSet tree) = L.mapOptional (\((,) key rest) -> (,) key (wrap rest)) (viewTree True tree);
  lookupIndexTree :: Int -> Int -> IntSetTree -> Maybe Int;
  lookupIndexTree = Rank.setRankTree;
  lookupIndex :: Int -> IntSet -> Maybe Int;
  lookupIndex key values = Rank.setRank key (Rank.indexSet values);
  selectBitmap :: Int -> Int -> Int -> Int -> Int;
  selectBitmap = Rank.selectBitmap;
  elemAtTree :: Int -> IntSetTree -> Maybe Int;
  elemAtTree = Rank.setSelectTree;
  elemAt :: Int -> IntSet -> Maybe Int;
  elemAt position values = Rank.setSelect position (Rank.indexSet values);
  eqIntSet :: IntSet -> IntSet -> Bool;
  eqIntSet a b = size a == size b && L.eqList eqInt (toList a) (toList b);
  validTree :: IntSetTree -> Bool;
  validTree tree = case tree of {
    IntSetNil -> True;
    IntSetTip count prefix bits ->
      bits /= 0 && P.prefixOf prefix == prefix && count == popCountInt bits;
    IntSetBin count prefix left right ->
      prefix /= 0 && P.suffixOf prefix == 0 &&
      sizeTree left > 0 && sizeTree right > 0 && count == sizeTree left + sizeTree right &&
      foldTree (\key rest -> L.not (P.nomatch key prefix) && P.left key prefix && rest) True left &&
      foldTree (\key rest -> L.not (P.nomatch key prefix) && L.not (P.left key prefix) && rest) True right &&
      validTree left && validTree right
  };
  valid :: IntSet -> Bool;
  valid (IntSet tree) = validTree tree
}
