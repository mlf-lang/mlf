-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Tests.ClassDemand where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.ClassDemand as Q;

  frames :: List Q.Frame;
  frames = Cons (Q.Frame 0 Nothing 100)
    (Cons (Q.Frame 1 (Just 0) 90)
      (Cons (Q.Frame 2 (Just 1) 10)
        (Cons (Q.Frame 3 (Just 1) 20) Nil)));
  oneSeed :: List Q.Seed;
  oneSeed = Cons (Q.Seed 10 "Inspect" 2) Nil;
  assertSlots :: Q.Plan -> Int -> List Int -> Either String Unit;
  assertSlots plan node expected =
    do {
      actual <- Q.slotsAt plan node;
      ensure (IS.eqIntSet (IS.fromList actual) (IS.fromList expected))
        "unexpected demand slots"
    };
  rejects :: Either String Q.Plan -> Either String Unit;
  rejects result =
    case result of {
      Left _ -> Right Unit;
      Right _ -> Left "invalid planner input was accepted"
    };
  emptyCycle :: Either String Unit;
  emptyCycle =
    do {
      plan <- Q.solve frames Nil Nil
        (IM.fromList (Cons (Pair 0 (Q.RefNode 1)) (Cons (Pair 1 (Q.RefNode 0)) Nil)));
      assertSlots plan 0 Nil;
      ensure (Q.universeSize plan == 0 && Q.saturationUpdates plan == 0)
        "a seedless cycle invented a dictionary"
    };
  sameClassOrigins :: Either String Unit;
  sameClassOrigins =
    do {
      plan <- Q.solve frames
        (Cons (Q.Seed 10 "Inspect" 1) (Cons (Q.Seed 11 "Inspect" 1) Nil)) Nil
        (IM.fromList (Cons (Pair 0 (Q.SeedNode 10))
          (Cons (Pair 1 (Q.SeedNode 11))
            (Cons (Pair 2 (Q.UnionNodes (Cons 0 (Cons 1 Nil)))) Nil))));
      values <- Q.slotsAt plan 2;
      ensure (length values == 2 && Q.universeSize plan == 2)
        "same-class origins were merged"
    };
  nestedReentry :: Either String Unit;
  nestedReentry =
    do {
      plan <- Q.solve frames oneSeed (Cons (Q.Use 100 2 1) Nil)
        (IM.fromList (Cons (Pair 0 (Q.SeedNode 10))
          (Cons (Pair 1 (Q.UnionNodes (Cons 0 (Cons 2 Nil))))
            (Cons (Pair 2 (Q.InstantiateNode 100 1)) Nil))));
      local <- Q.seedSlot plan 10;
      promoted <- Q.instantiateSlot plan 100 local;
      inherited <- Q.instantiateSlot plan 100 promoted;
      ensure (local /= promoted && promoted == inherited)
        "nested reentry freshened an inherited origin";
      assertSlots plan 1 (Cons local (Cons promoted Nil));
      assertSlots plan 2 (Cons promoted Nil);
      -- Both h parameters must still be supplied, despite one outward demand.
      arguments <- mapM (Q.instantiateSlot plan 100) (Cons local (Cons promoted Nil));
      ensure (eqList eqInt arguments (Cons promoted (Cons promoted Nil)))
        "instantiation lost actual dictionary argument multiplicity";
      ensure (Q.universeSize plan == 2 && Q.transitionCount plan == 2)
        "nested feedback allocated an unbounded lineage"
    };
  twoNestedUses :: Either String Unit;
  twoNestedUses =
    do {
      plan <- Q.solve frames oneSeed
        (Cons (Q.Use 100 2 1) (Cons (Q.Use 101 2 1) Nil))
        (IM.fromList (Cons (Pair 0 (Q.SeedNode 10))
          (Cons (Pair 1 (Q.UnionNodes (Cons 0 (Cons 4 Nil))))
            (Cons (Pair 2 (Q.InstantiateNode 100 1))
              (Cons (Pair 3 (Q.InstantiateNode 101 1))
                (Cons (Pair 4 (Q.UnionNodes (Cons 2 (Cons 3 Nil)))) Nil))))));
      local <- Q.seedSlot plan 10;
      first <- Q.instantiateSlot plan 100 local;
      second <- Q.instantiateSlot plan 101 local;
      ensure (first /= second) "distinct nested uses shared their local dictionary";
      assertSlots plan 4 (Cons first (Cons second Nil));
      ensure (Q.universeSize plan == 3 && Q.transitionCount plan == 6)
        "nested uses manufactured extra recursive origins"
    };
  siblingLineage :: Either String Unit;
  siblingLineage =
    do {
      plan <- Q.solve frames oneSeed
        (Cons (Q.Use 100 2 3) (Cons (Q.Use 101 2 3) (Cons (Q.Use 102 3 1) Nil)))
        (IM.fromList (Cons (Pair 0 (Q.SeedNode 10))
          (Cons (Pair 1 (Q.InstantiateNode 100 0))
            (Cons (Pair 2 (Q.InstantiateNode 101 0))
              (Cons (Pair 3 (Q.UnionNodes (Cons 1 (Cons 2 Nil))))
                (Cons (Pair 4 (Q.InstantiateNode 102 3)) Nil))))));
      local <- Q.seedSlot plan 10;
      first <- Q.instantiateSlot plan 100 local;
      second <- Q.instantiateSlot plan 101 local;
      firstOuter <- Q.instantiateSlot plan 102 first;
      secondOuter <- Q.instantiateSlot plan 102 second;
      ensure (firstOuter /= secondOuter)
        "origin lineage was collapsed to seed and last use";
      assertSlots plan 4 (Cons firstOuter (Cons secondOuter Nil));
      ensure (Q.universeSize plan == 5) "completed sibling origin count changed"
    };
  capturedOrigin :: Either String Unit;
  capturedOrigin =
    do {
      plan <- Q.solve frames (Cons (Q.Seed 10 "Inspect" 1) Nil)
        (Cons (Q.Use 100 2 1) Nil)
        (IM.fromList (Cons (Pair 0 (Q.SeedNode 10))
          (Cons (Pair 1 (Q.InstantiateNode 100 0)) Nil)));
      local <- Q.seedSlot plan 10;
      inherited <- Q.instantiateSlot plan 100 local;
      ensure (inherited == local && Q.universeSize plan == 1)
        "captured outer dictionary was independently instantiated"
    };
  unreachableUses :: Either String Unit;
  unreachableUses =
    do {
      plan <- Q.solve frames
        (Cons (Q.Seed 10 "Inspect" 2) (Cons (Q.Seed 11 "Convert" 2) Nil))
        (Cons (Q.Use 100 2 1) (Cons (Q.Use 101 2 3) Nil))
        (IM.fromList (Cons (Pair 0 (Q.SeedNode 10))
          (Cons (Pair 1 (Q.SeedNode 11))
            (Cons (Pair 2 Q.Empty)
              (Cons (Pair 3 (Q.InstantiateNode 100 2))
                (Cons (Pair 4 (Q.InstantiateNode 101 2)) Nil))))));
      ensure (Q.universeSize plan == 2 && Q.transitionCount plan == 0)
        "unrelated lexical uses expanded the universe";
      selected <- Q.selectedSlotCount plan (Cons 3 (Cons 4 Nil));
      ensure (selected == 0) "empty let continuation inherited an unused RHS demand"
    };
  validation :: Either String Unit;
  validation =
    do {
      rejects (Q.solve frames oneSeed (Cons (Q.Use 100 2 2) Nil) IM.empty);
      rejects (Q.solve frames oneSeed (Cons (Q.Use 100 1 2) Nil) IM.empty);
      rejects (Q.solve
        (Cons (Q.Frame 0 Nothing 0) (Cons (Q.Frame 1 (Just 0) 1) Nil)) Nil Nil IM.empty);
      rejects (Q.solve frames (Cons (Q.Seed 10 "A" 2) (Cons (Q.Seed 10 "B" 2) Nil)) Nil IM.empty);
      rejects (Q.solve frames Nil Nil (IM.singleton 0 (Q.RefNode 1)));
      rejects (Q.solve frames Nil Nil (IM.singleton 0 (Q.InstantiateNode 99 0)));
      rejects (Q.solve frames (Cons (Q.Seed 10 "Inspect" 3) Nil)
        (Cons (Q.Use 100 2 1) Nil)
        (IM.fromList (Cons (Pair 0 (Q.SeedNode 10))
          (Cons (Pair 1 (Q.InstantiateNode 100 0)) Nil))));
      Right Unit
    };
  checks :: List (Pair String (Either String Unit));
  checks = Cons (Pair "empty recursive demand cycle" emptyCycle)
    (Cons (Pair "same-class origin distinction" sameClassOrigins)
      (Cons (Pair "nested owner reentry and actual multiplicity" nestedReentry)
        (Cons (Pair "two nested polymorphic uses" twoNestedUses)
          (Cons (Pair "completed sibling full lineage" siblingLineage)
            (Cons (Pair "captured ancestor origin" capturedOrigin)
              (Cons (Pair "no unreachable Cartesian expansion" unreachableUses)
                (Cons (Pair "invalid rank and reference rejection" validation) Nil)))))));
  checkAll :: Either String Unit;
  checkAll =
    foldM
      (\_ (Pair label result) ->
         case result of {
           Left message -> Left (label ++ (": " ++ message));
           Right Unit -> Right Unit
         }) Unit checks
}
