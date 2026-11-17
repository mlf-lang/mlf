-- Test-only wrapper. No baseline Graph or Solver code is modified.
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Prototype.ClassGenTrial
  (TrialRoute(..),TrialObservation(..),trialUnify) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Graph;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.ST as ST;
  data TrialRoute = TrialAccepted | TrialCertificateRejected |
                    TrialPostRejected | TrialSparse | TrialPrecheck;
  data TrialObservation = TrialObservation TrialRoute (Maybe String) (Either String Graph);
  trialFinish :: TrialRoute -> Maybe String -> Either String Graph -> TrialObservation;
  trialFinish route diagnostic result = case result of {
    Left message -> TrialObservation route diagnostic (Left message);
    Right rebuilt -> case validateGraph rebuilt of {
      Left message -> TrialObservation route diagnostic (Left message);
      Right checked -> TrialObservation route diagnostic (Right rebuilt)
    }
  };
  trialUnify :: [] ((,) Int Int) -> Graph -> TrialObservation;
  trialUnify equations before = case validateGraph before of {
    Left message -> TrialObservation TrialPrecheck Nothing (Left message);
    Right checked -> case checkedFirstOrder equations before of {
      Left message -> TrialObservation TrialPrecheck Nothing (Left message);
      Right skeleton -> let { canonical = canonicalize skeleton } in
        case denseBounds before of {
          Nothing -> trialFinish TrialSparse Nothing (rebindSparse before canonical);
          Just ((,) low high) -> runST (trialDenseRebinding before canonical low high)
        }
    }
  };
  trialParentGen :: Graph -> Maybe Int -> Bool;
  trialParentGen old parent = case parent of {
    Nothing -> True;
    Just g -> case IM.lookup g (nodes old) of {
      Nothing -> False;
      Just node -> isGen (tag node)
    }
  };
  trialOld :: Graph -> Graph -> [] ((,) Int Node) -> Bool;
  trialOld old skeleton originals =
    IM.null (links old) && simpleKinds (nodes old) &&
    L.all (\((,) n v) ->
      equalFlag (flag v) Flexible &&
      trialParentGen old (binder v) &&
      (if isGen (tag v) then resolve skeleton n == n
       else case binder v of { Nothing -> False; Just g -> True })) originals;
  trialSameBinders :: forall s. Int -> STArray s (Maybe Int) -> Maybe Int -> [] Int -> ST s Bool;
  trialSameBinders low oldBinders expected members = case members of {
    [] -> stReturn True;
    (:) n rest -> stBind (readDense low oldBinders n)
      (\parent -> if equalMaybeInt parent expected
        then trialSameBinders low oldBinders expected rest else stReturn False)
  };
  trialClasses :: forall s. DenseRebinding s -> [] ((,) Int Node) -> ST s Bool;
  trialClasses state remaining = case remaining of {
    [] -> stReturn True;
    (:) ((,) n v) rest -> case state of {
      DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
        stBind (readDense low classes n) (\members ->
          if L.null members || L.not (equalFlag (flag v) Flexible) ||
             (isGen (tag v) && L.not (case members of { (:) one [] -> one == n; _ -> False }))
          then stReturn False
          else stBind (trialSameBinders low oldBinders (binder v) members)
            (\same -> if same then trialClasses state rest else stReturn False))
    }
  };
  trialAfterLoaded :: forall s. DenseRebinding s -> [] ((,) Int Node) -> [] ((,) Int Node) -> ST s TrialObservation;
  trialAfterLoaded state originals remaining = case state of {
    DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->
      let { baseline = \route -> \diagnostic ->
        stBind (trialOriginalTail state originals remaining)
          (\result -> stReturn (trialFinish route diagnostic result)) } in
      if L.not (trialOld old skeleton originals)
      then baseline TrialCertificateRejected Nothing
      else stBind (trialClasses state remaining) (\eligible ->
        if L.not eligible then baseline TrialCertificateRejected Nothing
        else let { candidate = mkGraph (nodesFromDistinctAscList remaining)
                      (links skeleton) (nextId skeleton) } in
          case validateGraph candidate of {
            Left message -> baseline TrialPostRejected (Just message);
            Right checked -> stReturn (TrialObservation TrialAccepted Nothing (Right candidate))
          })
  };
  trialDenseRebinding :: forall s. Graph -> Graph -> Int -> Int -> ST s TrialObservation;
  trialDenseRebinding old skeleton low high =
    let {
      count = ((high - low) + 1)
    } in
    stBind (newSTArray count Nothing)
      (\oldNodes ->
         stBind (newSTArray count Nothing)
           (\newNodes ->
              stBind (newSTArray count 0)
                (\images ->
                   stBind (newSTArray count [])
                     (\classes ->
                        stBind (newSTArray count Flexible)
                          (\flags ->
                             stBind (newSTArray count [])
                               (\parents ->
                                  stBind (newSTArray count Nothing)
                                    (\tree ->
                                       stBind (newSTArray count 0)
                                         (\depths ->
                                            stBind (newSTArray count 0)
                                              (\colours ->
                                                 stBind (newSTArray count 0)
                                                   (\grafted ->
                                                      stBind (newSTArray count Nothing)
                                                        (\oldBinders ->
                                                           stBind (newSTArray count Nothing)
                                                             (\raised ->
                                                                let {
                                                                  state =
                                                                    DenseRebinding old skeleton low
                                                                      high
                                                                      oldNodes
                                                                      newNodes
                                                                      images
                                                                      classes
                                                                      flags
                                                                      parents
                                                                      tree
                                                                      depths
                                                                      colours
                                                                      grafted
                                                                      oldBinders
                                                                      raised
                                                                } in
                                                                let {
                                                                  originals = IM.toList (nodes old)
                                                                } in
                                                                let {
                                                                  remaining =
                                                                    IM.toList (nodes skeleton)
                                                                } in
                                                                stBind
                                                                  (denseLoadOriginals state
                                                                     originals)
                                                                  (\loadedOld ->
                                                                     stBind
                                                                       (denseLoadRemainings state
                                                                          remaining)
                                                                       (\loadedNew ->
        trialAfterLoaded state originals remaining))))))))))))));
  trialOriginalTail :: forall s. DenseRebinding s -> [] ((,) Int Node) -> [] ((,) Int Node) -> ST s (Either String Graph);
  trialOriginalTail state originals remaining = case state of {
    DenseRebinding old skeleton low high oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised ->

                                                                          stBind
                                                                            (denseMarkOriginals
                                                                               state
                                                                               originals)
                                                                            (\marked ->
                                                                               ST.bindE
                                                                                 (densePlaceEntries
                                                                                    state
                                                                                    remaining)
                                                                                 (\placed ->
                                                                                    ST.bindE
                                                                                      (denseFinalNodes
                                                                                         state
                                                                                         remaining)
                                                                                      (\final ->
                                                                                         ST.bindE
                                                                                           (denseRaiseOriginals
                                                                                              state
                                                                                              originals)
                                                                                           (\up ->
                                                                                              stBind
                                                                                                (newDensePermissions
                                                                                                   low
                                                                                                   high
                                                                                                   oldNodes
                                                                                                   oldBinders
                                                                                                   originals)
                                                                                                (\oldPermissions ->
                                                                                                   stBind
                                                                                                     (raisedDensePermissions
                                                                                                        oldPermissions
                                                                                                        low
                                                                                                        high
                                                                                                        oldNodes
                                                                                                        oldBinders
                                                                                                        raised
                                                                                                        originals)
                                                                                                     (\raisedPermissions ->
                                                                                                        ST.bindE
                                                                                                          (denseCheckOriginals
                                                                                                             state
                                                                                                             oldPermissions
                                                                                                             raisedPermissions
                                                                                                             originals)
                                                                                                          (\checked ->
                                                                                                             ST.bindE
                                                                                                               (denseCheckMergeEntries
                                                                                                                  low
                                                                                                                  classes
                                                                                                                  raised
                                                                                                                  raisedPermissions
                                                                                                                  remaining)
                                                                                                               (\merged ->
                                                                                                                  ST.pureE
                                                                                                                    (mkGraph
                                                                                                                       (nodesFromDistinctAscList
                                                                                                                          final)
                                                                                                                       (links
                                                                                                                          skeleton)
                                                                                                                       (nextId
                                                                                                                          skeleton))))))))))
  };
}
