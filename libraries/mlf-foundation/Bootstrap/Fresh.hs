-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Fresh where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Map as M;
  data Fresh a = Fresh (Int -> Set String -> Either String ((,,) a Int (Set String)));
  runFreshState :: forall a. Fresh a ->
                             Int -> Set String -> Either String ((,,) a Int (Set String));
  runFreshState (Fresh action) count used = action count used;
  freshPure :: forall a. a -> Fresh a;
  freshPure value = Fresh (\count used -> Right ((,,) value count used));
  freshBind :: forall a b. Fresh a -> (a -> Fresh b) -> Fresh b;
  freshBind action continuation =
    Fresh
      (\count used ->
         case runFreshState action count used of {
           Left error -> Left error;
           Right ((,,) value next usedNext) -> runFreshState (continuation value) next usedNext
         });
  instance Functor Fresh where {
    fmap function action = freshBind action (\value -> freshPure (function value))
  };
  instance Applicative Fresh where {
    pure = freshPure;
    (<*>) action argument =
      freshBind action (\function -> freshBind argument (\value -> freshPure (function value)))
  };
  instance Monad Fresh where {
    (>>=) = freshBind
  };
  freshFail :: forall a. String -> Fresh a;
  freshFail message = Fresh (\count used -> Left message);
  freshLift :: forall a. Either String a -> Fresh a;
  freshLift result =
    case result of {
      Left error -> freshFail error;
      Right value -> freshPure value
    };
  runFresh :: forall a. [] String -> Fresh a -> Either String a;
  runFresh used = runFreshFrom (reservedNames used);
  runFreshFrom :: forall a. Set String -> Fresh a -> Either String a;
  runFreshFrom used action =
    mapEither (\((,,) value _ _) -> value)
      (runFreshState action 0 used);
  -- Private exact String reservation: duplicates preserve the existing tree.
  -- A new key rebuilds only its insertion path. All compared names use the
  -- same exact Unicode ordering as the ordinary Set; counter rules remain.
  reserveTree :: String -> Map String () -> Maybe (Map String ());
  reserveTree name tree = case tree of {
    MapEmpty -> Just (M.singleton name ());
    MapNode _ key value left right -> let { order = compareString name key } in
      if order < 0 then case reserveTree name left of {
        Nothing -> Nothing; Just next -> Just (M.balance key value next right)
      } else if order > 0 then case reserveTree name right of {
        Nothing -> Nothing; Just next -> Just (M.balance key value left next)
      } else Nothing
  };
  -- Incremental reservation keeps the ascending prefix and the exact
  -- insertion order used by the list builder, including the first descent.
  data Reservations = NoNames | AscendingNames ([] String) String | ReservedTree (Map String ());
  reserveName state next = case state of {
    NoNames -> seq next (AscendingNames [] next);
    AscendingNames earlier last -> let { order = compareString next last } in
      if order < 0 then case S.fromDistinctAscList (reverse ((:) last earlier)) of {
        Set initial -> reserveName (ReservedTree initial) next
      } else seq next (AscendingNames (if order == 0 then earlier else (:) last earlier) next);
    ReservedTree tree -> case reserveTree next tree of {
      Nothing -> state; Just more -> seq more (ReservedTree more)
    }
  };
  finishedNames state = case state of {
    NoNames -> S.empty;
    AscendingNames earlier last -> S.fromDistinctAscList (reverse ((:) last earlier));
    ReservedTree tree -> S.wrap tree
  };
  reserveNamesFrom :: Map String () -> [] String -> Set String;
  reserveNamesFrom initial names = S.wrap (foldlStrict (\tree name -> case reserveTree name tree of {
    Nothing -> tree; Just next -> next
  }) initial names);
  reservedNames :: [] String -> Set String;
  reservedNames names = case names of {
    [] -> S.empty;
    (:) name rest -> seq name (reserveAscending [] name rest)
  };
  -- Retain the ordinary Set builder's linear ascending-prefix path.
  reserveAscending :: [] String -> String -> [] String -> Set String;
  reserveAscending reversed name names = case names of {
    [] -> S.fromDistinctAscList (reverse ((:) name reversed));
    (:) next rest -> let { order = compareString next name } in
      if order < 0 then case S.fromDistinctAscList (reverse ((:) name reversed)) of {
        Set initial -> reserveNamesFrom initial names
      } else if order == 0 then seq next (reserveAscending reversed next rest)
      else seq next (reserveAscending ((:) name reversed) next rest)
  };
  freshName :: String -> Fresh String;
  freshName prefix =
    Fresh
      (\count used ->
         let {
           name = (prefix ++ showInt count)
         } in
         if S.member compareString name used
         then runFreshState (freshName prefix) (advanceIdentity count 1) used
         else Right ((,,) name (advanceIdentity count 1) (S.insert compareString name used)));
  freshNames :: Int -> String -> Fresh ([] String);
  freshNames count prefix =
    if (count <= 0)
    then freshPure []
    else do {
           name <- freshName prefix;
           rest <- freshNames (count - 1) prefix;
           freshPure ((:) name rest)
         }
}
