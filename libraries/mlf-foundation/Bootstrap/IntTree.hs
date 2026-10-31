-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- Adapted from containers-0.8.1 Data.IntSet.Internal.IntTreeCommons.
-- BSD-3-Clause; see tools/release/licenses/containers-0.8.1.txt and the upstream attribution.
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
module Bootstrap.IntTree where {
  import MLF.Primitive;
  import Bootstrap.Types;
  signBit :: Int;
  signBit = (-9223372036854775807) - 1;
  unsignedLess :: Int -> Int -> Bool;
  unsignedLess a b = unsignedLtInt a b;
  unsignedLE :: Int -> Int -> Bool;
  unsignedLE a b = if unsignedLess b a then False else True;
  signBranch :: Int -> Bool;
  signBranch prefix = prefix == signBit;
  mask :: Int -> Int -> Int;
  mask key bit = orInt (andInt key (0 - bit)) bit;
  branchMask :: Int -> Int -> Int;
  -- The caller must supply distinct keys/prefixes.
  branchMask a b = unsignedShiftRInt signBit (countLeadingZerosInt (xorInt a b));
  nomatch :: Int -> Int -> Bool;
  nomatch key prefix = andInt (xorInt key prefix) (xorInt prefix (0 - prefix)) /= 0;
  left :: Int -> Int -> Bool;
  left key prefix = unsignedLess key prefix;
  greatest :: Int -> Int;
  greatest prefix = orInt prefix (prefix - 1);
  smallest :: Int -> Int;
  smallest prefix = andInt prefix (prefix - 1);
  relation :: Int -> Int -> IntTreeRelation;
  relation a b =
    if unsignedLess a b
    then if unsignedLE b (greatest a) then IntTreeABR
         else if unsignedLE (smallest b) a then IntTreeBAL else IntTreeNOM
    else if unsignedLess b a
         then if unsignedLE a (greatest b) then IntTreeBAR
              else if unsignedLE (smallest a) b then IntTreeABL else IntTreeNOM
         else IntTreeEQL;
  prefixOf :: Int -> Int;
  prefixOf key = andInt key (-64);
  suffixOf :: Int -> Int;
  suffixOf key = andInt key 63;
  bitmapOf :: Int -> Int;
  bitmapOf key = shiftLInt 1 (suffixOf key);
  complement :: Int -> Int;
  complement bits = xorInt bits (-1)
}
