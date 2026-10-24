-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Async.Task (Task, Fiber, Options(..), Outcome(..), CancelReason(..), AsyncError(..), defaultOptions, pure, map, bind, fail, capture, spawn, awaitOutcome, await, yield, sleep, withTimeout, cancel, cancelScope, all, collect, mapConcurrentlyN, runProcess, checkedProcess, withScope, run) where {
  import MLF.Primitive hiding (pure, bind, runProcess);
  import Async.Task.Internal (Task, Fiber, Options(..), Outcome(..), CancelReason(..), AsyncError(..), defaultOptions, capture, spawn, awaitOutcome, await, yield, sleep, withTimeout, cancel, cancelScope, all, collect, mapConcurrentlyN, runProcess, checkedProcess, withScope, run);
  import qualified Async.Task.Internal as I;
  -- Keep the scheduler's IO do-notation independent of these public names.
  -- Constructing or composing a Task is cold; run/spawn start its execution.
  pure :: forall a. a -> Task a;
  pure = I.taskPure;
  map :: forall a b. (a -> b) -> Task a -> Task b;
  map = I.taskMap;
  bind :: forall a b. Task a -> (a -> Task b) -> Task b;
  bind = I.taskBind;
  fail :: forall a. AsyncError -> Task a;
  fail = I.taskFail
}
