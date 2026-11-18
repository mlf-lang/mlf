{-# LANGUAGE NoImplicitPrelude, RankNTypes, OverloadedStrings #-}
module Prototype.ValidationReadObserverMutant
  (Event(..), Report(..), observeGraph) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Graph hiding (denseValidation, denseGetNode, denseRequire, denseCheckBinder, denseAddDescendant, denseBindingVisit, denseContains, denseStructurally, denseValidateEntries, denseChild, denseKindBinder, denseKind, denseTagKind, denseLoadValidation, denseCheckBinders, denseAddDescendants, denseKindEntries, denseBindingChildren, denseChildKinds, DenseValidation(..));
  import qualified Bootstrap.Graph as G;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.ST as ST;
  data Event = Event String (Maybe Int);
  data Report = Report (Either String ()) ([] Event);
  data DenseValidation s = DenseValidation Graph Int Int
    (STArray s (Maybe Node)) (STArray s ([] Int)) (STArray s Int)
    (STArray s Kind) (STArray s Int) (STArray s Int) (STArray s Int)
    (STArray s Int) (STArray s ([] Event));
  emit :: forall s. DenseValidation s -> String -> Maybe Int -> ST s ();
  emit (DenseValidation g lo hi tab ds cs ks ss es vs count events) label identity =
    stBind (readSTArray count 0) (\n ->
      if n >= 8192 then panic "observer event cap"
      else seq (n + 1)
        (stBind (writeSTArray count 0 (n + 1)) (\written ->
          stBind (readSTArray events 0) (\previous ->
            writeSTArray events 0 ((:) (Event label identity) previous)))));
  traceE :: forall s a. DenseValidation s -> String -> Maybe Int ->
    ST s (Either String a) -> ST s (Either String a);
  traceE state label identity action =
    stBind (emit state ("entry:" ++ label) identity) (\entered ->
      stBind action (\answer -> case answer of {
        Left message -> stBind (emit state ("failure:" ++ label) identity)
          (\failed -> stReturn answer);
        Right value -> stBind (emit state ("success:" ++ label) identity)
          (\completed -> stReturn answer)
      }));
  resolveObserved :: forall s. DenseValidation s -> Int -> ST s Int;
  resolveObserved state@(DenseValidation graph lo hi tab ds cs ks ss es vs count events) original =
    case IM.lookup original (links graph) of {
      Nothing -> stBind (emit state "alias:absent" (Just original))
        (\logged -> stReturn original);
      Just next -> stBind (emit state "alias:present" (Just original))
        (\logged -> resolveObserved state next)
    };
  directChildObserved :: forall s. DenseValidation s -> Int -> [] Int -> ST s Bool;
  directChildObserved state wanted pending = case pending of {
    [] -> stReturn False;
    (:) child rest -> stBind (resolveObserved state child) (\n ->
      if n == wanted then stReturn True else directChildObserved state wanted rest)
  };
  observeGraph :: Graph -> Report;
  observeGraph graph = case G.denseBounds graph of {
    Nothing -> Report (G.validateSparse graph) ((:) (Event "sparse:unobserved" Nothing) []);
    Just ((,) low high) -> runST
      (stBind (newSTArray 1 0) (\count ->
        stBind (newSTArray 1 []) (\events ->
          stBind (denseValidation count events graph low high) (\answer ->
            stBind (readSTArray events 0) (\backwards ->
              stReturn (Report answer (L.reverse backwards)))))))
  };
  denseValidation :: forall s. STArray s Int -> STArray s ([] Event) -> Graph -> Int -> Int -> ST s (Either String ());
  denseValidation logCount logEvents graph low high =
    let {
      count = ((high - low) + 1)
    } in
    stBind (newSTArray count Nothing)
      (\table ->
         stBind (newSTArray count [])
           (\descendants ->
              stBind (newSTArray count 0)
                (\colours ->
                   stBind (newSTArray count Star)
                     (\kinds ->
                        stBind (newSTArray count (0 - 1))
                          (\starts ->
                             stBind (newSTArray count (0 - 1))
                               (\ends ->
                                  stBind (newSTArray count (0 - 1))
                                    (\visited ->
                                       let {
                                         state =
                                           DenseValidation graph low high table descendants colours
                                             kinds
                                             starts
                                             ends
                                             visited logCount logEvents
                                       } in
                                       let {
                                         entries = IM.toList (nodes graph)
                                       } in
                                       stBind (denseLoadValidation low table entries)
                                         (\loaded -> denseValidateEntries state entries))))))));


  denseGetNode :: forall s. DenseValidation s -> Int -> ST s (Maybe Node);
  denseGetNode state@(DenseValidation graph low high table descendants colours kinds starts ends visited logCount logEvents) n =
    stBind (if ((n < low) || (high < n)) then stReturn Nothing else readDense low table n)
      (\answer -> case answer of {
        Nothing -> stBind (emit state "node:absent" (Just n)) (\logged -> stReturn answer);
        Just value -> stBind (emit state "node:present" (Just n)) (\logged -> stReturn answer)
      });


  denseRequire :: forall s. DenseValidation s -> Int -> ST s (Either String Node);
  denseRequire state n =
    traceE state "require" (Just n)
      (stBind (denseGetNode state n)
      (\answer ->
         case answer of {
           Nothing -> ST.failE ("missing graph node " ++ showInt n);
           Just value -> ST.pureE value
         }));

  denseCheckBinder :: forall s. DenseValidation s -> (,) Int Node -> ST s (Either String ());
  denseCheckBinder state ((,) n v) =
    traceE state "binder-exists" (Just n)
      (case binder v of {
      Nothing -> ST.pureE ();
      Just b ->
        stBind (denseGetNode state b)
          (\answer ->
             case answer of {
               Nothing -> ST.failE "missing binder";
               Just ignored -> ST.pureE ()
             })
    });

  denseAddDescendant :: forall s. DenseValidation s -> (,) Int Node -> ST s ();
  denseAddDescendant (DenseValidation graph low high table descendants colours kinds starts ends visited logCount logEvents) ((,) n v) =
    case binder v of {
      Nothing -> stReturn ();
      Just b ->
        stBind (readDense low descendants b)
          (\previous -> writeDense low descendants b ((:) n previous))
    };


  denseBindingVisit :: forall s. DenseValidation s -> Int -> Int -> ST s Int;
  denseBindingVisit state n position =
    case state of {
      DenseValidation graph low high table descendants colours kinds starts ends visited logCount logEvents ->
        stBind (writeDenseInt low starts n position)
          (\ignored ->
             stBind (readDense low descendants n)
               (\children ->
                  stBind (denseBindingChildren state (position + 1) children)
                    (\end -> stBind (writeDenseInt low ends n end) (\written -> stReturn end))))
    };


  denseContains :: forall s. DenseValidation s -> Int -> Int -> ST s Bool;
  denseContains state@(DenseValidation graph low high table descendants colours kinds starts ends visited logCount logEvents) ancestor n =
    stBind (emit state "dependency:global-euler" Nothing) (\logged ->
    stBind (readDense low starts ancestor)
      (\a ->
         stBind (readDense low ends ancestor)
           (\b -> stBind (readDense low starts n) (\p -> stReturn ((a <= p) && (p < b))))));


  denseStructurally :: forall s. DenseValidation s ->
                                 Int -> Int -> [] Int -> ST s (Either String Bool);
  denseStructurally state wanted stamp pending =
    case pending of {
      [] -> ST.pureE False;
      (:) original rest ->
        case state of {
          DenseValidation graph low high table descendants colours kinds starts ends visited logCount logEvents ->
            stBind (resolveObserved state original) (\n ->
            if (n == wanted)
            then ST.pureE True
            else ST.bindE (denseRequire state n)
                   (\v ->
                      stBind (readDense low visited n)
                        (\mark ->
                           if (mark == stamp)
                           then denseStructurally state wanted stamp rest
                           else stBind (writeDenseInt low visited n stamp)
                                  (\written ->
                                     stBind (emit state "selector:structural-tag-children" (Just n)) (\logged ->
                                     denseStructurally state wanted stamp
                                       (L.append (children (tag v)) rest)))))
        )}
    };


  denseValidateEntries :: forall s. DenseValidation s ->
                                    [] ((,) Int Node) -> ST s (Either String ());
  denseValidateEntries state entries =
    traceE state "global-root-binding-euler" (Nothing)
      (case L.filter
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
        ST.bindE (denseCheckBinders state entries)
          (\binders ->
             stBind (denseAddDescendants state entries)
               (\loaded ->
                  stBind (denseBindingVisit state root 0)
                    (\count ->
                       if (count == L.length entries)
                       then stBind (emit state "success:global-euler" Nothing) (\logged -> denseKindEntries state entries)
                       else ST.failE "cyclic binding tree")));
      _ -> ST.failE "graph must have one binding root"
    });

  denseChild :: forall s. DenseValidation s -> Int -> Int -> ST s (Either String Kind);
  denseChild state parent original =
    traceE state "edge-gates" (Nothing)
      (case state of {
      DenseValidation graph low high table descendants colours kinds starts ends visited logCount logEvents ->
        stBind (resolveObserved state original) (\n ->
        ST.bindE (denseRequire state n)
          (\v ->
             stBind (readDense low colours n) (\cached ->
               if cached == 2 then ST.liftE (readDense low kinds n)
               else stBind (emit state "selector:child-tag" (Just n)) (\logged ->
             if isGen (tag v)
             then ST.failE "gen nodes cannot be structural children"
             else stBind (emit state "selector:child-binder" (Just n)) (\binderRead -> case binder v of {
                    Nothing -> ST.failE "structural child has no binder";
                    Just b ->
                      stBind (denseContains state b parent)
                        (\dominated ->
                           if dominated
                           then denseKind state n v
                           else ST.failE "ill-dominated type graph")
                  }))))
    )});

  denseKindBinder :: forall s. DenseValidation s -> Int -> Node -> ST s (Either String ());
  denseKindBinder state n v =
    traceE state "node-binder" (Just n)
      (case binder v of {
      Nothing -> stBind (emit state "selector:root-tag" (Just n)) (\logged -> ST.check (isGen (tag v)) "binding root must be a gen node");
      Just b ->
        ST.bindE (denseRequire state b)
          (\parent ->
             stBind (emit state "selector:parent-tag" (Just b)) (\logged ->
             if isGen (tag parent)
             then ST.pureE ()
             else case state of {
                    DenseValidation graph low high table descendants colours kinds starts ends visited logCount logEvents ->
                      stBind (directChildObserved state n (children (tag parent)))
                      (\direct -> if direct
                      then ST.pureE ()
                      else stBind (readDense low starts n)
                             (\stamp ->
                                ST.bindE (denseStructurally state n stamp ((:) b []))
                                  (\found ->
                                     ST.check found
                                       "a type binder must structurally contain its node")))
                  }))
    });

  denseKind :: forall s. DenseValidation s -> Int -> Node -> ST s (Either String Kind);
  denseKind state n v =
    traceE state "kind-fact" (Just n)
      (case state of {
      DenseValidation graph low high table descendants colours kinds starts ends visited logCount logEvents ->
        stBind (readDense low colours n)
          (\colour ->
             if (colour == 1)
             then ST.failE "infinite type (occurs check)"
             else if (colour == 2)
                  then stBind (emit state "cache:kind-hit" (Just n)) (\logged -> ST.liftE (readDense low kinds n))
                  else stBind (writeDenseInt low colours n 1)
                         (\active ->
                            ST.bindE (denseKindBinder state n v)
                              (\bound ->
                                 ST.bindE (denseTagKind state n v)
                                   (\kind ->
                                      stBind (writeDense low kinds n kind)
                                        (\stored ->
                                           stBind (writeDenseInt low colours n 2)
                                             (\complete -> ST.pureE kind))))))
    });

  denseTagKind :: forall s. DenseValidation s -> Int -> Node -> ST s (Either String Kind);
  denseTagKind state n v =
    traceE state "tag-kind" (Just n)
      (case tag v of {
      GBot -> ST.pureE Star;
      GBotK kind -> stBind (emit state "selector:kind-payload-not-forced" (Just n)) (\logged -> ST.pureE kind);
      GTyCon name kind -> stBind (emit state "selector:kind-payload-not-forced" (Just n)) (\logged -> ST.pureE kind);
      GSkolem identity kind -> stBind (emit state "selector:kind-payload-not-forced" (Just n)) (\logged -> ST.pureE kind);
      GGen child ->
        stBind (emit state "selector:gen-flag" (Just n)) (\logged -> if equalFlag (flag v) Flexible
        then denseChild state n child
        else ST.failE "gen nodes must be flexible");
      GArr a b ->
        ST.bindE (denseChild state n a)
          (\ka ->
             ST.bindE (denseChild state n b)
               (\kb ->
                  if (equalKind ka Star && equalKind kb Star)
                  then ST.pureE Star
                  else ST.failE "function types require kind * arguments"));
      GCon name children ->
        ST.bindE (denseChildKinds state n children)
          (\kinds ->
             if L.all (\kind -> equalKind kind Star) kinds
             then ST.pureE Star
             else ST.failE "legacy type constructor has a non-* argument");
      GTyApp function argument ->
        ST.bindE (denseChild state n function)
          (\kf -> ST.bindE (denseChild state n argument) (\ka -> stReturn (applyKind kf ka)))
    });

  denseLoadValidation :: forall s. Int ->
                                   STArray s (Maybe Node) -> [] ((,) Int Node) -> ST s ();
  denseLoadValidation low table values =
    case values of {
      [] -> stReturn ();
      (:) entry rest ->
        stBind
          (case entry of {
             (,) n v -> writeDense low table n (Just v)
           })
          (\ignored -> denseLoadValidation low table rest)
    };


  denseCheckBinders :: forall s. DenseValidation s ->
                                 [] ((,) Int Node) -> ST s (Either String ());
  denseCheckBinders state values =
    case values of {
      [] -> ST.pureE ();
      (:) entry rest ->
        ST.bindE (denseCheckBinder state entry) (\ignored -> denseCheckBinders state rest)
    };


  denseAddDescendants :: forall s. DenseValidation s -> [] ((,) Int Node) -> ST s ();
  denseAddDescendants state values =
    case values of {
      [] -> stReturn ();
      (:) entry rest ->
        stBind (denseAddDescendant state entry) (\ignored -> denseAddDescendants state rest)
    };


  denseKindEntries :: forall s. DenseValidation s ->
                                [] ((,) Int Node) -> ST s (Either String ());
  denseKindEntries state values =
    case values of {
      [] -> ST.pureE ();
      (:) entry rest ->
        ST.bindE
          (case entry of {
             (,) n v -> denseKind state n v
           })
          (\ignored -> denseKindEntries state rest)
    };


  denseBindingChildren :: forall s. DenseValidation s -> Int -> [] Int -> ST s Int;
  denseBindingChildren state position children =
    case children of {
      [] -> stReturn position;
      (:) child rest ->
        stBind (denseBindingVisit state child position)
          (\next -> denseBindingChildren state next rest)
    };


  denseChildKinds :: forall s. DenseValidation s ->
                               Int -> [] Int -> ST s (Either String ([] Kind));
  denseChildKinds state n values =
    case values of {
      [] -> ST.pureE [];
      (:) entry rest ->
        ST.bindE (denseChild state n entry)
          (\answer ->
             ST.bindE (denseChildKinds state n rest) (\answers -> ST.pureE ((:) answer answers)))
    };

}

