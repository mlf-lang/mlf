-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.CorePartitions where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Package.OS as O;
  -- Physical compilation targets do not change the logical core execution unit.
  -- Keep this data-only: a campaign or shard must not import another shard's actions.
  familyNames :: [] String;
  familyNames =
    O.words
      "core/substring-adapter core/optimizer-uses core/crate-codegen core/declaration-queries core/incremental-crate-cache core/component-projection core/int-set-unions core/index-edges core/projection-ranks core/projection-changes core/strict-wrappers core/solver-index-audit core/dense-normalization core/checked-emission core/solver-allocation core/inference-and-annotations core/type-computations core/binding-hygiene core/graph-expansion core/graph-validation core/graph-unification core/graph-solver core/embedding-pruning core/datatypes core/typeclasses core/do-notation core/surface-syntax core/readability core/modules core/separate-compilation core/state-types core/hm-oracle core/annotation-corpus core/example-files core/guards";
  partitions :: [] ((,) String ([] String));
  partitions =
    (:)
      ((,) "core-crates"
         (O.words
            "core/optimizer-uses core/crate-codegen core/declaration-queries core/incremental-crate-cache core/strict-wrappers core/checked-emission"))
      ((:)
         ((,) "core-solver"
            (O.words
               "core/component-projection core/int-set-unions core/index-edges core/projection-ranks core/projection-changes core/solver-index-audit core/dense-normalization core/solver-allocation core/graph-expansion core/graph-validation core/graph-unification core/graph-solver core/embedding-pruning"))
         ((:)
            ((,) "core-language"
               (O.words
                  "core/substring-adapter core/inference-and-annotations core/type-computations core/binding-hygiene core/datatypes core/typeclasses core/do-notation core/surface-syntax core/guards"))
            ((:)
               ((,) "core-modules"
                  (O.words
                     "core/readability core/modules core/separate-compilation core/state-types core/hm-oracle core/annotation-corpus core/example-files"))
               [])));
  targets :: [] String;
  targets = S.map S.fst partitions;
  forTarget :: String -> [] String;
  forTarget target = S.fromMaybe [] (S.lookup eqString target partitions);
  selectedTargets :: [] String -> [] String;
  selectedTargets selected =
    S.map S.fst
      (S.filter (\entry -> S.any (\name -> S.elem eqString name selected) (S.snd entry))
         partitions);
  validate :: [] String -> Either String ();
  validate reviewed =
    let {
      flat = S.concatMap S.snd partitions
    } in
    if ((S.length flat == S.length (S.nubBy eqString flat)) &&
        (S.eqList eqString (S.sortBy compareString flat) (S.sortBy compareString familyNames) &&
         (S.eqList eqString familyNames reviewed &&
          ((S.length targets == S.length (S.nubBy eqString targets)) &&
           S.all
             (\entry ->
                (S.not (S.null (S.snd entry)) &&
                 S.eqList eqString (S.snd entry)
                   (S.filter (\name -> S.elem eqString name (S.snd entry)) familyNames)))
             partitions))))
    then Right ()
    else Left "core compilation partition changed the reviewed family inventory";
  validateCompleted :: [] String -> [] String -> Either String ();
  validateCompleted expected completed =
    if (S.not (S.null expected) &&
        ((S.length expected == S.length (S.nubBy eqString expected)) &&
         (S.all (\name -> S.elem eqString name familyNames) expected &&
          ((S.length completed == S.length (S.nubBy eqString completed)) &&
           S.eqList eqString (S.sortBy compareString completed)
             (S.sortBy compareString expected)))))
    then Right ()
    else Left "core partial reports do not cover the exact selected family union"
}
