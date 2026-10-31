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
module Bootstrap.IntRank where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.IntTree as P;
  -- Immutable rank/select views. Construction shares the existing Patricia
  -- tree, does not enumerate keys, and never forces map payloads. Keeping this
  -- boundary separate lets the solver avoid depending on collection layout.
  -- Cached counts are also required by the public O(1) size contract; removing
  -- them is a separate representation/performance decision, not an API cleanup.
  data MapIndex a = MapIndex (IntMapTree a);
  data SetIndex = SetIndex IntSetTree;
  indexMap :: forall a. IntMap a -> MapIndex a;
  indexMap (IntMap tree) = MapIndex tree;
  indexSet :: IntSet -> SetIndex;
  indexSet (IntSet tree) = SetIndex tree;
  mapTreeSize :: forall a. IntMapTree a -> Int;
  mapTreeSize tree = case tree of {
    IntMapNil -> 0; IntMapTip key value -> 1;
    IntMapBin count prefix left right -> count
  };
  setTreeSize :: IntSetTree -> Int;
  setTreeSize tree = case tree of {
    IntSetNil -> 0; IntSetTip count prefix bits -> count;
    IntSetBin count prefix left right -> count
  };
  mapSize :: forall a. MapIndex a -> Int;
  mapSize (MapIndex tree) = mapTreeSize tree;
  mapRank :: forall a. Int -> Int -> MapIndex a -> Maybe Int;
  mapRank key offset (MapIndex tree) = mapRankTree key offset tree;
  mapSelect :: forall a. Int -> MapIndex a -> Maybe Int;
  mapSelect position (MapIndex tree) = case mapEntryTree position tree of {
    Nothing -> Nothing; Just ((,) key value) -> Just key
  };
  setRank :: Int -> SetIndex -> Maybe Int;
  setRank key (SetIndex tree) = setRankTree key 0 tree;
  setSelect :: Int -> SetIndex -> Maybe Int;
  setSelect position (SetIndex tree) = setSelectTree position tree;
  mapRankTree :: forall a. Int -> Int -> IntMapTree a -> Maybe Int;
  mapRankTree key offset tree = case tree of {
    IntMapNil -> Nothing;
    IntMapTip previous value -> if key == previous then Just offset else Nothing;
    IntMapBin count prefix left right ->
      if P.left key prefix then mapRankTree key (offset + (if P.signBranch prefix then mapTreeSize right else 0)) left
      else mapRankTree key (offset + (if P.signBranch prefix then 0 else mapTreeSize left)) right
  };
  mapEntryTree :: forall a. Int -> IntMapTree a -> Maybe ((,) Int a);
  mapEntryTree position tree =
    if position < 0 || position >= mapTreeSize tree then Nothing else case tree of {
      IntMapNil -> Nothing;
      IntMapTip key value -> Just ((,) key value);
      IntMapBin count prefix left right ->
        if P.signBranch prefix then
          if position < mapTreeSize right then mapEntryTree position right else mapEntryTree (position - mapTreeSize right) left
        else if position < mapTreeSize left then mapEntryTree position left else mapEntryTree (position - mapTreeSize left) right
    };
  setRankTree :: Int -> Int -> IntSetTree -> Maybe Int;
  setRankTree key offset tree = case tree of {
    IntSetNil -> Nothing;
    IntSetTip count prefix bits ->
      if P.prefixOf key == prefix && andInt bits (P.bitmapOf key) /= 0
      then Just (offset + popCountInt (andInt bits (P.bitmapOf key - 1))) else Nothing;
    IntSetBin count prefix left right ->
      if P.left key prefix
      then setRankTree key (offset + (if P.signBranch prefix then setTreeSize right else 0)) left
      else setRankTree key (offset + (if P.signBranch prefix then 0 else setTreeSize left)) right
  };
  selectBitmap :: Int -> Int -> Int -> Int -> Int;
  selectBitmap position bits width offset =
    if position == 0 then offset + countTrailingZerosInt bits
    else let { lower = andInt bits (shiftLInt 1 width - 1); count = popCountInt lower } in
      if position < count then selectBitmap position lower (quotInt width 2) offset
      else selectBitmap (position - count) (unsignedShiftRInt bits width) (quotInt width 2) (offset + width);
  setSelectTree :: Int -> IntSetTree -> Maybe Int;
  setSelectTree position tree =
    if position < 0 || position >= setTreeSize tree then Nothing
    else case tree of {
      IntSetNil -> Nothing;
      IntSetTip count prefix bits -> Just (prefix + selectBitmap position bits 32 0);
      IntSetBin count prefix left right ->
        if P.signBranch prefix
        then if position < setTreeSize right then setSelectTree position right
             else setSelectTree (position - setTreeSize right) left
        else if position < setTreeSize left then setSelectTree position left
             else setSelectTree (position - setTreeSize left) right
    };
}
