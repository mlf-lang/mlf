-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.FunctionPolicy where {
  import MLF.Primitive;
  import qualified Bootstrap.Std as L;
  -- Each function owns its facts, including while a nested worker is emitted.
  data Facts = Facts String Int Bool Bool Bool Int;
  empty name = Facts name 0 False False False 0;
  instructionCount (Facts _ n _ _ _ _) = n;
  instruction (Facts name n loop tailCall recursive allocations) = let { next = n + 1 } in
    seq next (Facts name next loop tailCall recursive allocations);
  markLoop (Facts name n _ tailCall recursive allocations) =
    Facts name n True tailCall recursive allocations;
  markTail (Facts name n loop _ recursive allocations) =
    Facts name n loop True recursive allocations;
  pointerCall target (Facts name n loop tailCall recursive allocations) = let {
    allocates = startsWith "@mlf.allocate.thunk" target || startsWith "@mlf.construct." target ||
      eqString target "@mlf_closure" || eqString target "@mlf_env_new";
    count = if allocates then allocations + 1 else allocations;
    self = recursive || eqString name target
  } in seq count (seq self (Facts name n loop tailCall self count));
  data WorkerBodyPolicy = OptimizableWorker | LazyTailWorker | OrdinaryWorker;
  workerBodyPolicy (Facts _ _ loop tailCall recursive allocations) =
    if loop then OptimizableWorker else if tailCall && allocations >= 3 then LazyTailWorker
    else if recursive || tailCall then OptimizableWorker else OrdinaryWorker;
  attributes :: Bool -> Bool -> Bool -> String -> Facts -> String;
  attributes largeModule keepWorker collectingWorker name facts =
          if (startsWith "@mlf.numeric." name &&
              (L.not (startsWith "@mlf.numeric.entry." name) && L.not collectingWorker))
          then " alwaysinline"
          else if startsWith "@mlf.code." name || startsWith "@mlf.curry." name
               then " noinline optnone"
          else if startsWith "@mlf.worker." name then let {
            boundary = keepWorker || instructionCount facts >= 64
          } in case workerBodyPolicy facts of {
            OptimizableWorker -> if boundary then " noinline" else "";
            LazyTailWorker -> " noinline optnone";
            -- Large link units can contain thousands of ordinary boxed helpers.
            -- Keep their emitted bodies while leaving recursive bodies optimizable.
            OrdinaryWorker -> if largeModule || boundary then " noinline optnone" else ""
          } else "";
  startsWith :: String -> String -> Bool;
  startsWith prefix value =
    ((stringLength prefix <= stringLength value) &&
     eqString prefix (stringSlice value 0 (stringLength prefix)));
}
