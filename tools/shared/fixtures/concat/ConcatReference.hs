-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- Frozen balanced implementation from 2957dd08321c38dbf94a75cb275a5f48e897f58e.
-- This reference deliberately calls only the binary concatString primitive.
module ConcatReference (concatStrings) where {
  import MLF.Primitive;
  -- Join adjacent pieces in rounds. Native strings are contiguous UTF-8, so
  -- a right fold copies every suffix again; balanced joins copy O(log n) times.
  -- Force pieces in source order, retaining the old failure/strictness order.
  concatStrings :: [] String -> String;
  concatStrings xs =
    case xs of {
      [] -> "";
      (:) first rest ->
        seq first
          (case rest of {
             [] -> first;
             (:) second tail -> concatStrings (concatStringPairs xs)
           })
    };
  concatStringPairs :: [] String -> [] String;
  concatStringPairs xs =
    case xs of {
      [] -> [];
      (:) first rest ->
        seq first
          (case rest of {
             [] -> (:) first [];
             (:) second tail ->
               let {
                 joined = concatString first second
               } in
               seq joined ((:) joined (concatStringPairs tail))
           })
    };
}
