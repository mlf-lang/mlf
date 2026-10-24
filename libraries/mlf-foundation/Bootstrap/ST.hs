-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.ST where {
  import MLF.Primitive;
  import Bootstrap.Types;
  -- A small, ordinary library layer over region-scoped state. Array elements
  -- remain lazy; sequencing only determines when cells are read or replaced.
  map_ :: forall s a b. (a -> ST s b) -> List a -> ST s Unit;
  map_ action values =
    case values of {
      Nil -> stReturn Unit;
      Cons value rest -> stBind (action value) (\ignored -> map_ action rest)
    };
  fold :: forall s a b. (a -> b -> ST s a) -> a -> List b -> ST s a;
  fold action initial values =
    case values of {
      Nil -> stReturn initial;
      Cons value rest -> stBind (action initial value) (\next -> fold action next rest)
    };
  pureE :: forall s a. a -> ST s (Either String a);
  pureE value = stReturn (Right value);
  failE :: forall s a. String -> ST s (Either String a);
  failE message = stReturn (Left message);
  bindE :: forall s a b. ST s (Either String a) ->
                         (a -> ST s (Either String b)) -> ST s (Either String b);
  bindE action following =
    stBind action
      (\answer ->
         case answer of {
           Left message -> stReturn (Left message);
           Right value -> following value
         });
  liftE :: forall s a. ST s a -> ST s (Either String a);
  liftE action = stBind action (\value -> pureE value);
  check :: forall s. Bool -> String -> ST s (Either String Unit);
  check condition message = if condition then pureE Unit else failE message;
  mapE :: forall s a b. (a -> ST s (Either String b)) -> List a -> ST s (Either String (List b));
  mapE action values =
    case values of {
      Nil -> pureE Nil;
      Cons value rest ->
        bindE (action value)
          (\answer -> bindE (mapE action rest) (\answers -> pureE (Cons answer answers)))
    };
  mapE_ :: forall s a b. (a -> ST s (Either String b)) -> List a -> ST s (Either String Unit);
  mapE_ action values =
    case values of {
      Nil -> pureE Unit;
      Cons value rest -> bindE (action value) (\ignored -> mapE_ action rest)
    };
  foldE :: forall s a b. (a -> b -> ST s (Either String a)) ->
                         a -> List b -> ST s (Either String a);
  foldE action initial values =
    case values of {
      Nil -> pureE initial;
      Cons value rest -> bindE (action initial value) (\next -> foldE action next rest)
    }
}
