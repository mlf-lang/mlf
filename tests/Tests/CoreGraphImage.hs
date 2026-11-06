-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.CoreGraphImage (rawGraphImage, rawSolverImage, orderedInputImage) where {
  import MLF.Primitive;
  import Bootstrap.Types;

  -- Test comparison image, not an artifact or graph loader. Match the bytes
  -- of two independently produced boundaries; never reconstruct a worker's
  -- starting graph from this data. Every tree constructor and cached field
  -- participates, in the original left/right order (not enumeration order).
  pushInt :: Int -> ([] String) -> ([] String);
  pushInt value rest = (:) (showInt value) ((:) ";" rest);
  -- Length is interpreted in the same String domain as the payload. Text can
  -- contain the surrounding delimiters: the prefix is itself self-delimiting.
  pushText :: String -> ([] String) -> ([] String);
  pushText value rest = (:) (showInt (stringLength value)) ((:) ":" ((:) value rest));
  pushList :: forall a. (a -> ([] String) -> ([] String)) -> [] a -> ([] String) -> ([] String);
  pushList write entries rest = case entries of {
    [] -> (:) "e" rest;
    (:) value tail -> (:) "s" (write value (pushList write tail rest))
  };
  pushTree :: forall a. (a -> ([] String) -> ([] String)) -> IntMapTree a -> ([] String) -> ([] String);
  pushTree write tree rest = case tree of {
    IntMapNil -> (:) "n" rest;
    IntMapTip key value -> (:) "t" (pushInt key (write value rest));
    IntMapBin count prefix left right ->
      (:) "b" (pushInt count (pushInt prefix (pushTree write left (pushTree write right rest))))
  };
  pushMap :: forall a. (a -> ([] String) -> ([] String)) -> IntMap a -> ([] String) -> ([] String);
  pushMap write (IntMap tree) rest = pushTree write tree rest;
  pushKind :: Kind -> ([] String) -> ([] String);
  pushKind kind rest = case kind of {
    Star -> (:) "*" rest;
    KArrow domain result -> (:) ">" (pushKind domain (pushKind result rest))
  };
  pushTag :: GTag -> ([] String) -> ([] String);
  pushTag tag rest = case tag of {
    GBot -> (:) "0" rest;
    GBotK kind -> (:) "1" (pushKind kind rest);
    GArr domain result -> (:) "2" (pushInt domain (pushInt result rest));
    GCon name children -> (:) "3" (pushText name (pushList pushInt children rest));
    GTyCon name kind -> (:) "4" (pushText name (pushKind kind rest));
    GSkolem identity kind -> (:) "5" (pushInt identity (pushKind kind rest));
    GTyApp function argument -> (:) "6" (pushInt function (pushInt argument rest));
    GGen root -> (:) "7" (pushInt root rest)
  };
  pushBinder :: Maybe Int -> ([] String) -> ([] String);
  pushBinder value rest = case value of {
    Nothing -> (:) "u" rest;
    Just parent -> (:) "p" (pushInt parent rest)
  };
  pushFlag :: Flag -> ([] String) -> ([] String);
  pushFlag flag rest = case flag of {
    Flexible -> (:) "f" rest;
    Rigid -> (:) "r" rest
  };
  pushNode :: Node -> ([] String) -> ([] String);
  pushNode (Node tag binder flag) rest = pushTag tag (pushBinder binder (pushFlag flag rest));
  pushEquation :: (,) Int Int -> ([] String) -> ([] String);
  pushEquation ((,) from to) rest = pushInt from (pushInt to rest);
  pushStep :: SolveStep -> ([] String) -> ([] String);
  pushStep step rest = case step of {
    Instantiate (Edge from to) -> (:) "i" (pushInt from (pushInt to rest));
    ProjectCase fields -> (:) "j" (pushList pushEquation fields rest)
  };
  pushGraph :: Graph -> ([] String) -> ([] String);
  pushGraph (Graph nodes links next) rest = pushInt next (pushMap pushNode nodes (pushMap pushInt links rest));
  pushSetTree :: IntSetTree -> ([] String) -> ([] String);
  pushSetTree tree rest = case tree of {
    IntSetNil -> (:) "n" rest;
    IntSetTip a b c -> (:) "t" (pushInt a (pushInt b (pushInt c rest)));
    IntSetBin count prefix left right ->
      (:) "b" (pushInt count (pushInt prefix (pushSetTree left (pushSetTree right rest))))
  };
  pushSet :: IntSet -> ([] String) -> ([] String);
  pushSet (IntSet tree) rest = pushSetTree tree rest;
  rawGraphImage :: Graph -> String;
  rawGraphImage graph = concatStringList ((:) "MLF-private-raw-graph-1\n" (pushGraph graph ["\n"]));
  rawSolverImage :: Solver -> String;
  rawSolverImage (Solver graph parents children (ScopeIndex intervals jumps)) = concatStringList
    ((:) "MLF-private-raw-solver-1\n"
      (pushGraph graph (pushMap pushSet parents (pushMap pushSet children
        (pushMap pushEquation intervals (pushList (pushMap pushInt) jumps ["\n"]))))));
  orderedInputImage :: [] ((,) Int Int) -> [] SolveStep -> String;
  orderedInputImage equations steps = concatStringList
    ((:) "MLF-private-ordered-solver-input-1\n" (pushList pushEquation equations (pushList pushStep steps ["\n"])));
}
