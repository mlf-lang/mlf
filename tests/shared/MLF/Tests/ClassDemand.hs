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

  frames :: [] Q.Frame;
  frames = (:) (Q.Frame 0 Nothing 100)
    ((:) (Q.Frame 1 (Just 0) 90)
      ((:) (Q.Frame 2 (Just 1) 10)
        ((:) (Q.Frame 3 (Just 1) 20) [])));
  oneSeed :: [] Q.Seed;
  oneSeed = (:) (Q.Seed 10 "Inspect" 2) [];
  assertSlots :: Q.Plan -> Int -> [] Int -> Either String ();
  assertSlots plan node expected =
    do {
      actual <- Q.slotsAt plan node;
      ensure (IS.eqIntSet (IS.fromList actual) (IS.fromList expected))
        "unexpected demand slots"
    };
  rejects :: Either String Q.Plan -> Either String ();
  rejects result =
    case result of {
      Left _ -> Right ();
      Right _ -> Left "invalid planner input was accepted"
    };
  emptyCycle :: Either String ();
  emptyCycle =
    do {
      plan <- Q.solve frames [] []
        (IM.fromList ((:) ((,) 0 (Q.RefNode 1)) ((:) ((,) 1 (Q.RefNode 0)) [])));
      assertSlots plan 0 [];
      ensure (Q.universeSize plan == 0 && Q.saturationUpdates plan == 0)
        "a seedless cycle invented a dictionary"
    };
  assertEmptyPlan :: IntSet -> Q.Plan -> Either String ();
  assertEmptyPlan expected (Q.Plan (Q.Universe next slots seeds transitions) values updates) =
    ensure (next == 0 && IM.null slots && IM.null seeds && IM.null transitions &&
      IS.eqIntSet expected (IM.keysSet values) &&
      IM.foldl (\empty value -> empty && IS.null value) True values && updates == 0)
      "seedless plan changed its exact universe, node sets, or update count";
  emptyDemandKinds :: Either String ();
  emptyDemandKinds = do {
    let { nodes = IM.fromList
      ((:) ((,) 0 Q.Empty)
        ((:) ((,) 1 (Q.RefNode 2))
          ((:) ((,) 2 (Q.UnionNodes ((:) 0 ((:) 1 ((:) 3 [])))))
            ((:) ((,) 3 (Q.InstantiateNode 100 2)) [])))) };
    plan <- Q.solve frames [] ((:) (Q.Use 100 2 1) []) nodes;
    assertEmptyPlan (IM.keysSet nodes) plan;
    empty <- Q.solve frames [] [] IM.empty;
    assertEmptyPlan IS.empty empty
  };
  rejectsExactly :: String -> Either String Q.Plan -> Either String ();
  rejectsExactly expected result = case result of {
    Left actual -> ensure (eqString expected actual) "planner validation diagnostic changed";
    Right _ -> Left "invalid seedless planner input was accepted"
  };
  emptyValidation :: Either String ();
  emptyValidation = do {
    rejectsExactly "class demand: unknown demand dependency 1"
      (Q.solve frames [] [] (IM.singleton 0 (Q.InstantiateNode 99 1)));
    rejectsExactly "class demand: unknown use 99"
      (Q.solve frames [] [] (IM.singleton 0 (Q.InstantiateNode 99 0)));
    rejectsExactly "class demand: unknown seed 10"
      (Q.solve frames [] [] (IM.singleton 0 (Q.SeedNode 10)));
    rejectsExactly "class demand: negative demand node identity"
      (Q.solve frames [] [] (IM.singleton (0 - 1) (Q.RefNode 99)));
    rejectsExactly "class demand: duplicate frame finish rank"
      (Q.solve ((:) (Q.Frame 0 Nothing 1)
        ((:) (Q.Frame 1 (Just 99) 1) [])) [] [] IM.empty);
    rejectsExactly "class demand: unknown parent frame 99"
      (Q.solve ((:) (Q.Frame 0 (Just 99) 1) []) [] [] IM.empty);
    rejectsExactly "class demand: instantiation receiver must finish after its binding"
      (Q.solve frames [] ((:) (Q.Use 100 1 2) []) IM.empty)
  };
  sameClassOrigins :: Either String ();
  sameClassOrigins =
    do {
      plan <- Q.solve frames
        ((:) (Q.Seed 10 "Inspect" 1) ((:) (Q.Seed 11 "Inspect" 1) [])) []
        (IM.fromList ((:) ((,) 0 (Q.SeedNode 10))
          ((:) ((,) 1 (Q.SeedNode 11))
            ((:) ((,) 2 (Q.UnionNodes ((:) 0 ((:) 1 [])))) []))));
      values <- Q.slotsAt plan 2;
      ensure (length values == 2 && Q.universeSize plan == 2)
        "same-class origins were merged"
    };
  nestedReentry :: Either String ();
  nestedReentry =
    do {
      plan <- Q.solve frames oneSeed ((:) (Q.Use 100 2 1) [])
        (IM.fromList ((:) ((,) 0 (Q.SeedNode 10))
          ((:) ((,) 1 (Q.UnionNodes ((:) 0 ((:) 2 []))))
            ((:) ((,) 2 (Q.InstantiateNode 100 1)) []))));
      local <- Q.seedSlot plan 10;
      promoted <- Q.instantiateSlot plan 100 local;
      inherited <- Q.instantiateSlot plan 100 promoted;
      ensure (local /= promoted && promoted == inherited)
        "nested reentry freshened an inherited origin";
      assertSlots plan 1 ((:) local ((:) promoted []));
      assertSlots plan 2 ((:) promoted []);
      -- Both h parameters must still be supplied, despite one outward demand.
      arguments <- mapM (Q.instantiateSlot plan 100) ((:) local ((:) promoted []));
      ensure (eqList eqInt arguments ((:) promoted ((:) promoted [])))
        "instantiation lost actual dictionary argument multiplicity";
      ensure (Q.universeSize plan == 2 && Q.transitionCount plan == 2)
        "nested feedback allocated an unbounded lineage"
    };
  twoNestedUses :: Either String ();
  twoNestedUses =
    do {
      plan <- Q.solve frames oneSeed
        ((:) (Q.Use 100 2 1) ((:) (Q.Use 101 2 1) []))
        (IM.fromList ((:) ((,) 0 (Q.SeedNode 10))
          ((:) ((,) 1 (Q.UnionNodes ((:) 0 ((:) 4 []))))
            ((:) ((,) 2 (Q.InstantiateNode 100 1))
              ((:) ((,) 3 (Q.InstantiateNode 101 1))
                ((:) ((,) 4 (Q.UnionNodes ((:) 2 ((:) 3 [])))) []))))));
      local <- Q.seedSlot plan 10;
      first <- Q.instantiateSlot plan 100 local;
      second <- Q.instantiateSlot plan 101 local;
      ensure (first /= second) "distinct nested uses shared their local dictionary";
      assertSlots plan 4 ((:) first ((:) second []));
      ensure (Q.universeSize plan == 3 && Q.transitionCount plan == 6)
        "nested uses manufactured extra recursive origins"
    };
  siblingLineage :: Either String ();
  siblingLineage =
    do {
      plan <- Q.solve frames oneSeed
        ((:) (Q.Use 100 2 3) ((:) (Q.Use 101 2 3) ((:) (Q.Use 102 3 1) [])))
        (IM.fromList ((:) ((,) 0 (Q.SeedNode 10))
          ((:) ((,) 1 (Q.InstantiateNode 100 0))
            ((:) ((,) 2 (Q.InstantiateNode 101 0))
              ((:) ((,) 3 (Q.UnionNodes ((:) 1 ((:) 2 []))))
                ((:) ((,) 4 (Q.InstantiateNode 102 3)) []))))));
      local <- Q.seedSlot plan 10;
      first <- Q.instantiateSlot plan 100 local;
      second <- Q.instantiateSlot plan 101 local;
      firstOuter <- Q.instantiateSlot plan 102 first;
      secondOuter <- Q.instantiateSlot plan 102 second;
      ensure (firstOuter /= secondOuter)
        "origin lineage was collapsed to seed and last use";
      assertSlots plan 4 ((:) firstOuter ((:) secondOuter []));
      ensure (Q.universeSize plan == 5) "completed sibling origin count changed"
    };
  capturedOrigin :: Either String ();
  capturedOrigin =
    do {
      plan <- Q.solve frames ((:) (Q.Seed 10 "Inspect" 1) [])
        ((:) (Q.Use 100 2 1) [])
        (IM.fromList ((:) ((,) 0 (Q.SeedNode 10))
          ((:) ((,) 1 (Q.InstantiateNode 100 0)) [])));
      local <- Q.seedSlot plan 10;
      inherited <- Q.instantiateSlot plan 100 local;
      ensure (inherited == local && Q.universeSize plan == 1)
        "captured outer dictionary was independently instantiated"
    };
  unreachableUses :: Either String ();
  unreachableUses =
    do {
      plan <- Q.solve frames
        ((:) (Q.Seed 10 "Inspect" 2) ((:) (Q.Seed 11 "Convert" 2) []))
        ((:) (Q.Use 100 2 1) ((:) (Q.Use 101 2 3) []))
        (IM.fromList ((:) ((,) 0 (Q.SeedNode 10))
          ((:) ((,) 1 (Q.SeedNode 11))
            ((:) ((,) 2 Q.Empty)
              ((:) ((,) 3 (Q.InstantiateNode 100 2))
                ((:) ((,) 4 (Q.InstantiateNode 101 2)) []))))));
      ensure (Q.universeSize plan == 2 && Q.transitionCount plan == 0)
        "unrelated lexical uses expanded the universe";
      selected <- Q.selectedSlotCount plan ((:) 3 ((:) 4 []));
      ensure (selected == 0) "empty let continuation inherited an unused RHS demand"
    };
  validation :: Either String ();
  validation =
    do {
      rejects (Q.solve frames oneSeed ((:) (Q.Use 100 2 2) []) IM.empty);
      rejects (Q.solve frames oneSeed ((:) (Q.Use 100 1 2) []) IM.empty);
      rejects (Q.solve
        ((:) (Q.Frame 0 Nothing 0) ((:) (Q.Frame 1 (Just 0) 1) [])) [] [] IM.empty);
      rejects (Q.solve frames ((:) (Q.Seed 10 "A" 2) ((:) (Q.Seed 10 "B" 2) [])) [] IM.empty);
      rejects (Q.solve frames [] [] (IM.singleton 0 (Q.RefNode 1)));
      rejects (Q.solve frames [] [] (IM.singleton 0 (Q.InstantiateNode 99 0)));
      rejects (Q.solve frames ((:) (Q.Seed 10 "Inspect" 3) [])
        ((:) (Q.Use 100 2 1) [])
        (IM.fromList ((:) ((,) 0 (Q.SeedNode 10))
          ((:) ((,) 1 (Q.InstantiateNode 100 0)) []))));
      Right ()
    };
  checks :: [] ((,) String (Either String ()));
  checks = append
    ((:) ((,) "slot supply independent of cardinality" independentSupply)
      ((:) ((,) "seedless exact plan across all demand forms" emptyDemandKinds)
        ((:) ((,) "seedless exact validation and error order" emptyValidation) [])))
    ((:) ((,) "empty recursive demand cycle" emptyCycle)
    ((:) ((,) "same-class origin distinction" sameClassOrigins)
      ((:) ((,) "nested owner reentry and actual multiplicity" nestedReentry)
        ((:) ((,) "two nested polymorphic uses" twoNestedUses)
          ((:) ((,) "completed sibling full lineage" siblingLineage)
            ((:) ((,) "captured ancestor origin" capturedOrigin)
              ((:) ((,) "no unreachable Cartesian expansion" unreachableUses)
                ((:) ((,) "invalid rank and reference rejection" validation) []))))))));
  independentSupply :: Either String ();
  independentSupply = do {
    let { frameMap = IM.fromList (map (\frame -> (,) (Q.frameId frame) frame) frames) };
    let { seed = Q.Slot 0 "Inspect" 2 (Q.SeedOrigin 10) };
    -- A removed/reserved range must not cause a slot identity to be reused.
    let { initial = Q.Universe 10 (IM.singleton 0 seed) (IM.singleton 10 0) IM.empty };
    allocated <- Q.allocateAt frameMap (Q.Use 100 2 1) 0 initial;
    case allocated of {
      (,) output universe -> do {
        ensure (output == 10 && Q.nextSlot universe == 11 &&
          eqList eqInt (IM.keys (Q.universeSlots universe)) ((:) 0 ((:) 10 [])))
          "slot allocation reused a removed identity";
        repeated <- Q.allocateAt frameMap (Q.Use 100 2 1) 0 universe;
        case repeated of {
          (,) again unchanged -> ensure (again == 10 && Q.nextSlot unchanged == 11)
            "cached transition consumed another slot"
        }
      }
    }
  };
  checkAll :: Either String ();
  checkAll =
    foldM
      (\_ ((,) label result) ->
         case result of {
           Left message -> Left (label ++ (": " ++ message));
           Right () -> Right ()
         }) () checks
}
