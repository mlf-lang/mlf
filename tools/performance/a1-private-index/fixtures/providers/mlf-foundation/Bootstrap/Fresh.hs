-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Fresh where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Set as S;
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
  runFresh used action =
    mapEither (\((,,) value _ _) -> value)
      (runFreshState action 0 (S.fromList compareString used));
  freshName :: String -> Fresh String;
  freshName prefix =
    Fresh
      (\count used ->
         let {
           name = (prefix ++ showInt count)
         } in
         if S.member compareString name used
         then runFreshState (freshName prefix) (count + 1) used
         else Right ((,,) name (count + 1) (S.insert compareString name used)));
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
