-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- Standalone, unregistered study kernel. This is not a public Solver route.
module Bootstrap.Graph.IndexStore
  ( Index(..), Edit(..), Store, importIndices, readBucket, commitEdits,
    freezeIndices ) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;

  data Index = Structural | Binding;
  -- The two integer arguments are outer target, then member/source.
  data Edit = InsertMember Index Int Int | RemoveMember Index Int Int;
  -- Both directory cells and every leaf belong to the same private region.
  -- A copied directory would still alias its pages; it is never a snapshot.
  data Store s = Store
    (STArray s (IntMap (STArray s IntSet)))
    (STArray s (IntMap (STArray s IntSet)));

  directoryFor :: forall s. Index -> Store s -> STArray s (IntMap (STArray s IntSet));
  directoryFor index (Store structural binding) =
    case index of {
      Structural -> structural;
      Binding -> binding
    };

  coordinates :: Int -> (,) Int Int;
  coordinates key =
    let {
      quotient = quotInt key 64;
      remainder = key - (64 * quotient)
    } in
    if (remainder < 0)
    then (,) (quotient - 1) (remainder + 64)
    else (,) quotient remainder;

  forceBucket :: IntSet -> ();
  forceBucket (IntSet tree) = seq tree ();

  forceDirectory :: forall a. IntMap a -> ();
  forceDirectory (IntMap tree) = seq tree ();

  -- Admission contract: both maps are canonical valid finite reverse indices,
  -- with valid NONEMPTY immutable buckets and already prepared root demand.
  -- This internal function is not a validator or a raw/forged-state adapter.
  -- Imported bucket roots are shared, never enumerated or reinserted.
  importIndices :: forall s. IntMap IntSet -> IntMap IntSet -> ST s (Store s);
  importIndices structural binding =
    stBind (newSTArray 1 IM.empty)
      (\structuralDirectory ->
         stBind (newSTArray 1 IM.empty)
           (\bindingDirectory ->
              stBind (importEntries (IM.toAscList structural) structuralDirectory)
                (\ignoredStructural ->
                   stBind (importEntries (IM.toAscList binding) bindingDirectory)
                     (\ignoredBinding ->
                        stReturn (Store structuralDirectory bindingDirectory)))));

  importEntries :: forall s. [] ((,) Int IntSet) ->
                   STArray s (IntMap (STArray s IntSet)) -> ST s ();
  importEntries entries directory =
    case entries of {
      [] -> stReturn ();
      (:) ((,) key bucket) rest ->
        stBind (importBucket key bucket directory)
          (\ignored -> importEntries rest directory)
    };

  importBucket :: forall s. Int -> IntSet ->
                  STArray s (IntMap (STArray s IntSet)) -> ST s ();
  importBucket key bucket directory =
    stBind (readSTArray directory 0)
      (\pages ->
         case coordinates key of {
           (,) pageId offset ->
             case IM.lookup pageId pages of {
               Nothing -> admitPage pageId offset bucket pages directory;
               Just page -> seq (forceBucket bucket) (writeSTArray page offset bucket)
             }
         });

  -- Only first admission changes a directory. Every leaf always has 64 slots;
  -- no operation resizes/copies a leaf or narrows an outer key/page identity.
  admitPage :: forall s. Int -> Int -> IntSet -> IntMap (STArray s IntSet) ->
               STArray s (IntMap (STArray s IntSet)) -> ST s ();
  admitPage pageId offset bucket pages directory =
    seq (forceBucket bucket)
      (stBind (newSTArray 64 IS.empty)
         (\page ->
            stBind (writeSTArray page offset bucket)
              (\ignored ->
                 let {
                   updated = IM.insert pageId page pages
                 } in
                 seq (forceDirectory updated) (writeSTArray directory 0 updated))));

  readBucket :: forall s. Index -> Int -> Store s -> ST s IntSet;
  readBucket index key store =
    stBind (readSTArray (directoryFor index store) 0)
      (\pages ->
         case coordinates key of {
           (,) pageId offset ->
             case IM.lookup pageId pages of {
               Nothing -> stReturn IS.empty;
               Just page -> readSTArray page offset
             }
         });

  -- Ordered committed edits, not a rollback transaction. A caller stages
  -- speculative edits without running this action and commits only on success.
  commitEdits :: forall s. [] Edit -> Store s -> ST s ();
  commitEdits edits store =
    case edits of {
      [] -> stReturn ();
      (:) edit rest ->
        stBind (commitEdit edit store) (\ignored -> commitEdits rest store)
    };

  commitEdit :: forall s. Edit -> Store s -> ST s ();
  commitEdit edit store =
    case edit of {
      InsertMember index key member -> insertMember key member (directoryFor index store);
      RemoveMember index key member -> removeMember key member (directoryFor index store)
    };

  insertMember :: forall s. Int -> Int ->
                  STArray s (IntMap (STArray s IntSet)) -> ST s ();
  insertMember key member directory =
    stBind (readSTArray directory 0)
      (\pages ->
         case coordinates key of {
           (,) pageId offset ->
             case IM.lookup pageId pages of {
               Nothing -> admitPage pageId offset (IS.singleton member) pages directory;
               Just page ->
                 stBind (readSTArray page offset)
                   (\bucket ->
                      let {
                        updated = IS.insert member bucket
                      } in
                      seq (forceBucket updated) (writeSTArray page offset updated))
             }
         });

  removeMember :: forall s. Int -> Int ->
                  STArray s (IntMap (STArray s IntSet)) -> ST s ();
  removeMember key member directory =
    stBind (readSTArray directory 0)
      (\pages ->
         case coordinates key of {
           (,) pageId offset ->
             case IM.lookup pageId pages of {
               Nothing -> stReturn ();
               Just page ->
                 stBind (readSTArray page offset)
                   (\bucket ->
                      let {
                        remaining = IS.delete member bucket
                      } in
                      if (IS.size remaining == 0)
                      then writeSTArray page offset IS.empty
                      else writeSTArray page offset remaining)
             }
         });

  -- Every read runs before returning either immutable map. Pure assembly only
  -- sees captured immutable bucket roots, never a delayed mutable read action.
  freezeIndices :: forall s. Store s -> ST s ((,) (IntMap IntSet) (IntMap IntSet));
  freezeIndices (Store structural binding) =
    stBind (freezeDirectory structural)
      (\structuralIndex ->
         stBind (freezeDirectory binding)
           (\bindingIndex -> stReturn ((,) structuralIndex bindingIndex)));

  freezeDirectory :: forall s. STArray s (IntMap (STArray s IntSet)) ->
                     ST s (IntMap IntSet);
  freezeDirectory directory =
    stBind (readSTArray directory 0)
      (\pages ->
         stBind (freezePages (IM.toAscList pages) [])
           (\reversedEntries ->
              let {
                frozen = IM.fromDistinctAscList (L.reverse reversedEntries)
              } in
              seq (forceDirectory frozen) (stReturn frozen)));

  freezePages :: forall s. [] ((,) Int (STArray s IntSet)) ->
                 [] ((,) Int IntSet) -> ST s ([] ((,) Int IntSet));
  freezePages pages reversedEntries =
    case pages of {
      [] -> stReturn reversedEntries;
      (:) ((,) pageId page) rest ->
        stBind (freezeSlots pageId page 0 reversedEntries)
          (\nextEntries -> freezePages rest nextEntries)
    };

  freezeSlots :: forall s. Int -> STArray s IntSet -> Int ->
                 [] ((,) Int IntSet) -> ST s ([] ((,) Int IntSet));
  freezeSlots pageId page offset reversedEntries =
    if (offset >= 64)
    then stReturn reversedEntries
    else stBind (readSTArray page offset)
           (\bucket ->
              if IS.null bucket
              then freezeSlots pageId page (offset + 1) reversedEntries
              else let {
                     key = (64 * pageId) + offset
                   } in
                   seq key
                     (freezeSlots pageId page (offset + 1)
                        ((:) ((,) key bucket) reversedEntries)))
}
