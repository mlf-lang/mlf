-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.IndexVec
  (Index, fromInt, toInt, IndexVec, count, at, indices, toList, fromList,
   Builder, new, filled, size, get, set, push, freeze,
   FixedBuilder, fixedFilled, fixedGet, fixedSet, fixedFreeze) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;

  data Index domain = Index Int;
  fromInt :: forall d. Int -> Index d;
  fromInt n = Index n;
  toInt :: forall d. Index d -> Int;
  toInt (Index n) = n;

  data IndexVec domain a = Vector Int (Int -> a);
  count :: forall d a. IndexVec d a -> Int;
  count (Vector n _) = n;
  checked :: forall a. Int -> Int -> a -> a;
  checked n i result =
    if i >= 0 && i < n then result else panic "IndexVec index out of bounds";
  at :: forall d a. IndexVec d a -> Index d -> a;
  at (Vector n lookup) (Index i) = checked n i (lookup i);
  indices :: forall d a. IndexVec d a -> [] (Index d);
  indices vec = S.map Index (S.range 0 (count vec - 1));
  toList :: forall d a. IndexVec d a -> [] a;
  toList vec = S.map (at vec) (indices vec);

  -- Aliases share this header even when growth replaces the backing array.
  data FixedBuilder s domain a = FixedBuilder Int (STArray s a);
  fixedFilled :: forall s d a. Int -> a -> ST s (FixedBuilder s d a);
  fixedFilled n value = if n < 0 || n > maxCells then panic "invalid IndexVec length"
    else stBind (newSTArray n value) (\cells -> stReturn (FixedBuilder n cells));
  fixedGet :: forall s d a. FixedBuilder s d a -> Index d -> ST s a;
  fixedGet (FixedBuilder n cells) (Index i) = checked n i (readSTArray cells i);
  fixedSet :: forall s d a. FixedBuilder s d a -> Index d -> a -> ST s ();
  fixedSet (FixedBuilder n cells) (Index i) value = checked n i (writeSTArray cells i value);
  fixedFreeze :: forall s d a. FixedBuilder s d a -> ST s (IndexVec d a);
  fixedFreeze (FixedBuilder n cells) = stBind (freezeSTArray cells) (\lookup -> stReturn (Vector n lookup));
  data Buffer s a = Buffer Int Int (STArray s a);
  data Builder s domain a = Builder (STArray s (Buffer s a));
  maxCells :: Int;
  maxCells = 1152921504606846975;
  filled :: forall s d a. Int -> a -> ST s (Builder s d a);
  filled n value =
    if n < 0 || n > maxCells then panic "invalid IndexVec length"
    else stBind (newSTArray n value) (\cells ->
         stBind (newSTArray 1 (Buffer n n cells)) (\header -> stReturn (Builder header)));
  new :: forall s d a. ST s (Builder s d a);
  new = filled 0 (panic "unused IndexVec capacity");
  size :: forall s d a. Builder s d a -> ST s Int;
  size (Builder header) = stBind (readSTArray header 0) (\(Buffer n _ _) -> stReturn n);
  get :: forall s d a. Builder s d a -> Index d -> ST s a;
  get (Builder header) (Index i) =
    stBind (readSTArray header 0) (\(Buffer n _ cells) -> checked n i (readSTArray cells i));
  set :: forall s d a. Builder s d a -> Index d -> a -> ST s ();
  set (Builder header) (Index i) value =
    stBind (readSTArray header 0) (\(Buffer n _ cells) -> checked n i (writeSTArray cells i value));

  copy :: forall s a. STArray s a -> STArray s a -> Int -> Int -> ST s ();
  copy src dst i n =
    if i == n then stReturn ()
    else stBind (readSTArray src i) (\value ->
         stBind (writeSTArray dst i value) (\_ -> copy src dst (i + 1) n));
  push :: forall s d a. Builder s d a -> a -> ST s (Index d);
  push (Builder header) value = stBind (readSTArray header 0) (\(Buffer n capacity cells) ->
    let {
      publish nextCapacity dst = stBind (writeSTArray dst n value) (\_ ->
        let { next = n + 1 } in seq next (stBind (writeSTArray header 0 (Buffer next nextCapacity dst))
          (\_ -> stReturn (Index n))))
    } in
    if n < capacity then publish capacity cells
    else if n == maxCells then panic "IndexVec capacity overflow"
    else let { nextCapacity = if capacity == 0 then 1
               else if capacity > quotInt maxCells 2 then maxCells else capacity * 2 } in
         stBind (newSTArray nextCapacity (panic "unused IndexVec capacity")) (\dst ->
           stBind (copy cells dst 0 n) (\_ -> publish nextCapacity dst)));
  freeze :: forall s d a. Builder s d a -> ST s (IndexVec d a);
  freeze (Builder header) = stBind (readSTArray header 0) (\(Buffer n _ cells) ->
    stBind (freezeSTArray cells) (\lookup -> stReturn (Vector n lookup)));

  fillList :: forall s a. STArray s a -> Int -> [] a -> ST s ();
  fillList cells i values = case values of {
    [] -> stReturn ();
    (:) x rest -> stBind (writeSTArray cells i x) (\_ -> fillList cells (i + 1) rest)
  };
  fromList :: forall d a. [] a -> IndexVec d a;
  fromList values = case values of {
    [] -> Vector 0 (\_ -> panic "IndexVec index out of bounds");
    (:) _ _ -> let { n = S.length values } in runST
      (stBind (newSTArray n (panic "uninitialized IndexVec slot")) (\cells ->
        stBind (fillList cells 0 values) (\_ ->
        stBind (freezeSTArray cells) (\lookup -> stReturn (Vector n lookup)))))
  }
}
