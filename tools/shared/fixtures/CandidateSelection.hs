-- mlf:syntax shared-haskell-v1
-- Portable selector reference retained from 496dcae0.
-- Current Bootstrap.Classes behavior is tested by CandidateSelectionControls.hs.
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.IntSet as I;
  selectCandidates :: [] String ->
                      [] ((,) EvidenceRole String) -> IntSet -> [] ((,) EvidenceRole String);
  selectCandidates names supers indices = selectCandidateOrdinals 0 names (I.toList indices) supers;
  -- The inventory and set both use ascending ordinals. Keep repeated spellings
  -- and append the complete superclass/given tail unchanged.
  selectCandidateOrdinals ordinal names indices supers = case names of {
    [] -> supers;
    (:) _ _ -> case indices of {
      [] -> supers;
      (:) wanted more -> if wanted < ordinal then selectCandidateOrdinals ordinal names more supers
        else case dropCandidateNames (wanted - ordinal) names of {
          [] -> supers;
          (:) name rest -> (:) ((,) InstanceEvidence name)
            (selectCandidateOrdinals (wanted + 1) rest more supers)
        }
    }
  };
  -- A native O0 evaluator cannot rely on tail-call elimination. Split long
  -- gaps so skipping a sparse ordinal needs bounded local recursion plus a
  -- logarithmic call stack, without allocating a range or temporary pairs.
  dropCandidateNames count names = if count <= 256 then drop count names else
    let { half = count / 2 } in case dropCandidateNames half names of {
      [] -> [];
      rest@((:) _ _) -> dropCandidateNames (count - half) rest
    };
  -- The caller has validated the finite candidate inventory. Share a complete
  -- selection only for a bounded inventory; larger inventories retain the
  -- ordinal walk with bounded gap recursion. The subset check also admits
  -- irrelevant negative/out-of-range indices, as the original selector does.
  selectCandidateValues :: forall a. [] a -> [] a -> IntSet -> [] a;
  selectCandidateValues values tail = let {
    full = case candidateInventoryCount 256 0 values of {
      Nothing -> Nothing;
      Just count -> Just (I.fromDistinctAscList (range 0 (count - 1)))
    };
    complete = append values tail;
    selected indices = selectValueOrdinals 0 values (I.toList indices) tail
  } in \indices -> case values of {
    [] -> tail;
    (:) _ _ -> if I.null indices then tail else case full of {
      Just scope -> if I.isSubsetOf scope indices then complete else selected indices;
      Nothing -> selected indices
    }
  };
  candidateInventoryCount :: forall a. Int -> Int -> [] a -> Maybe Int;
  candidateInventoryCount remaining count values = case values of {
    [] -> Just count;
    (:) _ rest -> if remaining == 0 then Nothing
      else candidateInventoryCount (remaining - 1) (count + 1) rest
  };
  selectValueOrdinals ordinal values indices tail = case values of {
    [] -> tail;
    (:) _ _ -> case indices of {
      [] -> tail;
      (:) wanted more -> if wanted < ordinal then selectValueOrdinals ordinal values more tail
        else case dropCandidateNames (wanted - ordinal) values of {
          [] -> tail;
          (:) value rest -> (:) value (selectValueOrdinals (wanted + 1) rest more tail)
        }
    }
  };

  readIndices :: (Int -> IO String) -> Int -> Int -> IO ([] Int);
  readIndices getArg position count = if count == 0 then ioReturn [] else do {
    value <- getArg position; rest <- readIndices getArg (position + 1) (count - 1);
    ioReturn ((:) (readInt value) rest)
  };
  role value = case value of { InstanceEvidence -> "i"; SuperclassEvidence -> "s"; GivenEvidence -> "g" };
  runCase :: (Int -> IO String) -> IO ();
  runCase getArg = do {
    selector <- getArg 0;
    size <- getArg 1; modulus <- getArg 2; count <- getArg 3;
    indices <- readIndices getArg 4 (readInt count);
    let { period = readInt modulus;
      names = S.map (\i -> "n" ++ showInt (if period == 0 then i else i % period)) (S.range 0 (readInt size - 1));
      supers = [(,) SuperclassEvidence "super", (,) GivenEvidence "given", (,) InstanceEvidence "n0", (,) InstanceEvidence "n0"] };
    putStrLn (S.concatMapString (\((,) r n) -> role r ++ ":" ++ n ++ ";")
      ((if eqString selector "ids"
        then selectCandidateValues (S.map ((,) InstanceEvidence) names) supers
        else selectCandidates names supers) (I.fromList indices)))
  };
  batchArgument :: [] String -> Int -> IO String;
  batchArgument args index =
    if ltInt index 0 then panic "candidate batch getArg out of range"
    else case args of {
      [] -> panic "candidate batch getArg out of range";
      (:) value rest ->
        if eqInt index 0 then ioReturn value
        else batchArgument rest (subInt index 1)
    };
  batchLoop :: [] ((,) Int ([] String)) -> IO ();
  batchLoop entries = case entries of {
    [] -> ioReturn ();
    (:) ((,) index args) rest -> do {
      printInt 812350001; printInt index;
      runCase (batchArgument args);
      printInt 812350002;
      batchLoop rest
    }
  };
  batchCases :: [] ((,) Int ([] String));
  batchCases =
    [(,) 0 ["named", "0", "0", "0"]
    , (,) 1 ["named", "0", "0", "2", "-1", "0"]
    , (,) 2 ["named", "0", "0", "4", "0", "0", "1", "-1"]
    , (,) 3 ["named", "1", "0", "0"]
    , (,) 4 ["named", "1", "0", "2", "-1", "1"]
    , (,) 5 ["named", "1", "0", "4", "0", "0", "1", "0"]
    , (,) 6 ["named", "2", "0", "0"]
    , (,) 7 ["named", "2", "0", "2", "-1", "2"]
    , (,) 8 ["named", "2", "0", "4", "0", "0", "1", "1"]
    , (,) 9 ["named", "7", "0", "0"]
    , (,) 10 ["named", "7", "0", "2", "-1", "7"]
    , (,) 11 ["named", "7", "0", "4", "0", "0", "1", "6"]
    , (,) 12 ["ids", "0", "0", "0"]
    , (,) 13 ["ids", "0", "0", "2", "-1", "0"]
    , (,) 14 ["ids", "0", "0", "4", "0", "0", "1", "-1"]
    , (,) 15 ["ids", "1", "0", "0"]
    , (,) 16 ["ids", "1", "0", "2", "-1", "1"]
    , (,) 17 ["ids", "1", "0", "4", "0", "0", "1", "0"]
    , (,) 18 ["ids", "2", "0", "0"]
    , (,) 19 ["ids", "2", "0", "2", "-1", "2"]
    , (,) 20 ["ids", "2", "0", "4", "0", "0", "1", "1"]
    , (,) 21 ["ids", "7", "0", "0"]
    , (,) 22 ["ids", "7", "0", "2", "-1", "7"]
    , (,) 23 ["ids", "7", "0", "4", "0", "0", "1", "6"]
    ];
  main :: IO ();
  main = do {
    mode <- getArg 0;
    if eqString mode "batch-forward" then batchLoop batchCases
    else if eqString mode "batch-reverse" then batchLoop (S.reverse batchCases)
    else runCase getArg
  }
}
