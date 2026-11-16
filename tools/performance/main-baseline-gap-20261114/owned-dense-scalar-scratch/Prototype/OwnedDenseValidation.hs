-- GHC-only isolated compiler experiment; original public Graph remains unchanged.
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Prototype.OwnedDenseValidation (validateGraphOwned, unifyOwned) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.ST as ST;
  import Bootstrap.Graph (denseBounds, validateSparse, nodes, resolve, binder,
    isGen, tag, flag, equalFlag, children, equalKind, applyKind, readDense, writeDense);
  import qualified Bootstrap.Graph as G;
  import qualified Prelude as P;
  import qualified Data.Int as Fixed;
  import qualified Data.Array.ST as A;
  import qualified Data.Array.Base as AB;
  import qualified MLF.Host.Base as H;
  import GHC.Conc (pseq);

  -- No constructor/helper is exported. Every scratch is independently allocated
  -- by ownedDenseValidation. Node, Kind, descendants remain lazy boxed arrays.
  data OwnedIntScratch s = OwnedIntScratch !Int !(A.STUArray s P.Int Fixed.Int64);
  ownedNewIntScratch :: forall s. Int -> Int -> ST s (OwnedIntScratch s);
  ownedNewIntScratch n initial =
    P.pure n P.>>= (\operand ->
      let { size = H.bounded "invalid array length" (9223372036854775807 `P.quot` 8) operand } in
      (size `pseq` A.newArray (0, size P.- 1) initial) P.>>=
        (\cells -> P.pure (OwnedIntScratch (P.fromIntegral size) cells)));
  -- Array, then index checks occur in the action, as in Host.Base. The private
  -- initialization values are exactly 0/-1; no public lazy initializer contract.
  ownedReadInt :: forall s. Int -> OwnedIntScratch s -> Int -> ST s Int;
  ownedReadInt low array identity =
    P.pure array P.>>= (\(OwnedIntScratch size cells) ->
      AB.unsafeRead cells (H.stIndex size (array `pseq` (identity - low))));
  ownedWriteIntAction :: forall s. Int -> OwnedIntScratch s -> Int -> Int -> ST s ();
  ownedWriteIntAction low array identity value =
    P.pure array P.>>= (\(OwnedIntScratch size cells) ->
      AB.unsafeWrite cells (H.stIndex size (array `pseq` (identity - low))) value);
  -- IMPORTANT: force value while constructing the action, not only executing it.
  -- This is the exact writeDenseInt demand barrier, with only its private store changed.
  ownedWriteInt :: forall s. Int -> OwnedIntScratch s -> Int -> Int -> ST s ();
  ownedWriteInt low array identity value = seq value (ownedWriteIntAction low array identity value);
  validateGraphOwned :: Graph -> Either String ();
  validateGraphOwned graph =
    case denseBounds graph of {
      Nothing -> validateSparse graph;
      Just ((,) low high) -> ownedValidateDense graph low high
    };
  data OwnedDenseValidation s =
    OwnedDenseValidation Graph Int Int (STArray s (Maybe Node)) (STArray s ([] Int))
      (OwnedIntScratch s) (STArray s Kind) (OwnedIntScratch s)
      (OwnedIntScratch s) (OwnedIntScratch s);
  ownedValidateDense :: Graph -> Int -> Int -> Either String ();
  ownedValidateDense graph low high = runST (ownedDenseValidation graph low high);
  ownedDenseValidation :: forall s. Graph -> Int -> Int -> ST s (Either String ());
  ownedDenseValidation graph low high =
    let {
      count = ((high - low) + 1)
    } in
    stBind (newSTArray count Nothing)
      (\table ->
         stBind (newSTArray count [])
           (\descendants ->
              stBind (ownedNewIntScratch count 0)
                (\colours ->
                   stBind (newSTArray count Star)
                     (\kinds ->
                        stBind (ownedNewIntScratch count (0 - 1))
                          (\starts ->
                             stBind (ownedNewIntScratch count (0 - 1))
                               (\ends ->
                                  stBind (ownedNewIntScratch count (0 - 1))
                                    (\visited ->
                                       let {
                                         state =
                                           OwnedDenseValidation graph low high table descendants colours
                                             kinds
                                             starts
                                             ends
                                             visited
                                       } in
                                       let {
                                         entries = IM.toList (nodes graph)
                                       } in
                                       stBind (ownedDenseLoadValidation low table entries)
                                         (\loaded -> ownedDenseValidateEntries state entries))))))));
  ownedDenseGetNode :: forall s. OwnedDenseValidation s -> Int -> ST s (Maybe Node);
  ownedDenseGetNode (OwnedDenseValidation graph low high table descendants colours kinds starts ends visited) n =
    if ((n < low) || (high < n)) then stReturn Nothing else readDense low table n;
  ownedDenseRequire :: forall s. OwnedDenseValidation s -> Int -> ST s (Either String Node);
  ownedDenseRequire state n =
    stBind (ownedDenseGetNode state n)
      (\answer ->
         case answer of {
           Nothing -> ST.failE ("missing graph node " ++ showInt n);
           Just value -> ST.pureE value
         });
  ownedDenseCheckBinder :: forall s. OwnedDenseValidation s -> (,) Int Node -> ST s (Either String ());
  ownedDenseCheckBinder state ((,) n v) =
    case binder v of {
      Nothing -> ST.pureE ();
      Just b ->
        stBind (ownedDenseGetNode state b)
          (\answer ->
             case answer of {
               Nothing -> ST.failE "missing binder";
               Just ignored -> ST.pureE ()
             })
    };
  ownedDenseAddDescendant :: forall s. OwnedDenseValidation s -> (,) Int Node -> ST s ();
  ownedDenseAddDescendant (OwnedDenseValidation graph low high table descendants colours kinds starts ends visited) ((,) n v) =
    case binder v of {
      Nothing -> stReturn ();
      Just b ->
        stBind (readDense low descendants b)
          (\previous -> writeDense low descendants b ((:) n previous))
    };
  ownedDenseBindingVisit :: forall s. OwnedDenseValidation s -> Int -> Int -> ST s Int;
  ownedDenseBindingVisit state n position =
    case state of {
      OwnedDenseValidation graph low high table descendants colours kinds starts ends visited ->
        stBind (ownedWriteInt low starts n position)
          (\ignored ->
             stBind (readDense low descendants n)
               (\children ->
                  stBind (ownedDenseBindingChildren state (position + 1) children)
                    (\end -> stBind (ownedWriteInt low ends n end) (\written -> stReturn end))))
    };
  ownedDenseContains :: forall s. OwnedDenseValidation s -> Int -> Int -> ST s Bool;
  ownedDenseContains (OwnedDenseValidation graph low high table descendants colours kinds starts ends visited) ancestor n =
    stBind (ownedReadInt low starts ancestor)
      (\a ->
         stBind (ownedReadInt low ends ancestor)
           (\b -> stBind (ownedReadInt low starts n) (\p -> stReturn ((a <= p) && (p < b)))));
  ownedDenseStructurally :: forall s. OwnedDenseValidation s ->
                                 Int -> Int -> [] Int -> ST s (Either String Bool);
  ownedDenseStructurally state wanted stamp pending =
    case pending of {
      [] -> ST.pureE False;
      (:) original rest ->
        case state of {
          OwnedDenseValidation graph low high table descendants colours kinds starts ends visited ->
            let {
              n = resolve graph original
            } in
            if (n == wanted)
            then ST.pureE True
            else ST.bindE (ownedDenseRequire state n)
                   (\v ->
                      stBind (ownedReadInt low visited n)
                        (\mark ->
                           if (mark == stamp)
                           then ownedDenseStructurally state wanted stamp rest
                           else stBind (ownedWriteInt low visited n stamp)
                                  (\written ->
                                     ownedDenseStructurally state wanted stamp
                                       (L.append (children (tag v)) rest))))
        }
    };
  ownedDenseValidateEntries :: forall s. OwnedDenseValidation s ->
                                    [] ((,) Int Node) -> ST s (Either String ());
  ownedDenseValidateEntries state entries =
    case L.filter
           (\entry ->
              case entry of {
                (,) n v ->
                  case binder v of {
                    Nothing -> True;
                    Just ignored -> False
                  }
              })
           entries of {
      (:) ((,) root value) [] ->
        ST.bindE (ownedDenseCheckBinders state entries)
          (\binders ->
             stBind (ownedDenseAddDescendants state entries)
               (\loaded ->
                  stBind (ownedDenseBindingVisit state root 0)
                    (\count ->
                       if (count == L.length entries)
                       then ownedDenseKindEntries state entries
                       else ST.failE "cyclic binding tree")));
      _ -> ST.failE "graph must have one binding root"
    };
  -- Each structural edge is checked even if the child's kind is already cached.
  ownedDenseChild :: forall s. OwnedDenseValidation s -> Int -> Int -> ST s (Either String Kind);
  ownedDenseChild state parent original =
    case state of {
      OwnedDenseValidation graph low high table descendants colours kinds starts ends visited ->
        let {
          n = resolve graph original
        } in
        ST.bindE (ownedDenseRequire state n)
          (\v ->
             if isGen (tag v)
             then ST.failE "gen nodes cannot be structural children"
             else case binder v of {
                    Nothing -> ST.failE "structural child has no binder";
                    Just b ->
                      stBind (ownedDenseContains state b parent)
                        (\dominated ->
                           if dominated
                           then ownedDenseKind state n v
                           else ST.failE "ill-dominated type graph")
                  })
    };
  ownedDenseKindBinder :: forall s. OwnedDenseValidation s -> Int -> Node -> ST s (Either String ());
  ownedDenseKindBinder state n v =
    case binder v of {
      Nothing -> ST.check (isGen (tag v)) "binding root must be a gen node";
      Just b ->
        ST.bindE (ownedDenseRequire state b)
          (\parent ->
             if isGen (tag parent)
             then ST.pureE ()
             else case state of {
                    OwnedDenseValidation graph low high table descendants colours kinds starts ends visited ->
                      if L.any (\child -> (resolve graph child == n)) (children (tag parent))
                      then ST.pureE ()
                      else stBind (ownedReadInt low starts n)
                             (\stamp ->
                                ST.bindE (ownedDenseStructurally state n stamp ((:) b []))
                                  (\found ->
                                     ST.check found
                                       "a type binder must structurally contain its node"))
                  })
    };
  ownedDenseKind :: forall s. OwnedDenseValidation s -> Int -> Node -> ST s (Either String Kind);
  ownedDenseKind state n v =
    case state of {
      OwnedDenseValidation graph low high table descendants colours kinds starts ends visited ->
        stBind (ownedReadInt low colours n)
          (\colour ->
             if (colour == 1)
             then ST.failE "infinite type (occurs check)"
             else if (colour == 2)
                  then ST.liftE (readDense low kinds n)
                  else stBind (ownedWriteInt low colours n 1)
                         (\active ->
                            ST.bindE (ownedDenseKindBinder state n v)
                              (\bound ->
                                 ST.bindE (ownedDenseTagKind state n v)
                                   (\kind ->
                                      stBind (writeDense low kinds n kind)
                                        (\stored ->
                                           stBind (ownedWriteInt low colours n 2)
                                             (\complete -> ST.pureE kind))))))
    };
  ownedDenseTagKind :: forall s. OwnedDenseValidation s -> Int -> Node -> ST s (Either String Kind);
  ownedDenseTagKind state n v =
    case tag v of {
      GBot -> ST.pureE Star;
      GBotK kind -> ST.pureE kind;
      GTyCon name kind -> ST.pureE kind;
      GSkolem identity kind -> ST.pureE kind;
      GGen child ->
        if equalFlag (flag v) Flexible
        then ownedDenseChild state n child
        else ST.failE "gen nodes must be flexible";
      GArr a b ->
        ST.bindE (ownedDenseChild state n a)
          (\ka ->
             ST.bindE (ownedDenseChild state n b)
               (\kb ->
                  if (equalKind ka Star && equalKind kb Star)
                  then ST.pureE Star
                  else ST.failE "function types require kind * arguments"));
      GCon name children ->
        ST.bindE (ownedDenseChildKinds state n children)
          (\kinds ->
             if L.all (\kind -> equalKind kind Star) kinds
             then ST.pureE Star
             else ST.failE "legacy type constructor has a non-* argument");
      GTyApp function argument ->
        ST.bindE (ownedDenseChild state n function)
          (\kf -> ST.bindE (ownedDenseChild state n argument) (\ka -> stReturn (applyKind kf ka)))
    };
  ownedDenseLoadValidation :: forall s. Int ->
                                   STArray s (Maybe Node) -> [] ((,) Int Node) -> ST s ();
  ownedDenseLoadValidation low table values =
    case values of {
      [] -> stReturn ();
      (:) entry rest ->
        stBind
          (case entry of {
             (,) n v -> writeDense low table n (Just v)
           })
          (\ignored -> ownedDenseLoadValidation low table rest)
    };
  ownedDenseCheckBinders :: forall s. OwnedDenseValidation s ->
                                 [] ((,) Int Node) -> ST s (Either String ());
  ownedDenseCheckBinders state values =
    case values of {
      [] -> ST.pureE ();
      (:) entry rest ->
        ST.bindE (ownedDenseCheckBinder state entry) (\ignored -> ownedDenseCheckBinders state rest)
    };
  ownedDenseAddDescendants :: forall s. OwnedDenseValidation s -> [] ((,) Int Node) -> ST s ();
  ownedDenseAddDescendants state values =
    case values of {
      [] -> stReturn ();
      (:) entry rest ->
        stBind (ownedDenseAddDescendant state entry) (\ignored -> ownedDenseAddDescendants state rest)
    };
  ownedDenseKindEntries :: forall s. OwnedDenseValidation s ->
                                [] ((,) Int Node) -> ST s (Either String ());
  ownedDenseKindEntries state values =
    case values of {
      [] -> ST.pureE ();
      (:) entry rest ->
        ST.bindE
          (case entry of {
             (,) n v -> ownedDenseKind state n v
           })
          (\ignored -> ownedDenseKindEntries state rest)
    };
  ownedDenseBindingChildren :: forall s. OwnedDenseValidation s -> Int -> [] Int -> ST s Int;
  ownedDenseBindingChildren state position children =
    case children of {
      [] -> stReturn position;
      (:) child rest ->
        stBind (ownedDenseBindingVisit state child position)
          (\next -> ownedDenseBindingChildren state next rest)
    };
  ownedDenseChildKinds :: forall s. OwnedDenseValidation s ->
                               Int -> [] Int -> ST s (Either String ([] Kind));
  ownedDenseChildKinds state n values =
    case values of {
      [] -> ST.pureE [];
      (:) entry rest ->
        ST.bindE (ownedDenseChild state n entry)
          (\answer ->
             ST.bindE (ownedDenseChildKinds state n rest) (\answers -> ST.pureE ((:) answer answers)))
    };
  unifyOwned :: [] ((,) Int Int) -> Graph -> Either String Graph;
  unifyOwned equations before =
    G.bindE (validateGraphOwned before)
      (\ignored ->
         G.bindE (G.checkedFirstOrder equations before)
           (\skeleton ->
              G.bindE (G.rebind before (G.canonicalize skeleton))
                (\rebuilt -> G.bindE (validateGraphOwned rebuilt) (\verified -> Right rebuilt))));
}
