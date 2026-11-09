-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Async.Task.Internal (Task, Fiber, Options(..), Outcome(..), CancelReason(..), AsyncError(..), defaultOptions, taskPure, taskMap, taskBind, taskFail, capture, spawn, awaitOutcome, await, yield, sleep, withTimeout, cancel, cancelScope, all, collect, mapConcurrentlyN, runProcess, checkedProcess, withScope, run) where {
  import MLF.Primitive hiding (runProcess);
  import Async.Process (AsyncError(..));
  import Async.Task.Core (Task, Fiber, Options(..), Outcome(..), CancelReason(..), defaultOptions, taskPure, taskMap, taskBind, taskFail, capture, spawn, awaitOutcome, await, yield, sleep, withTimeout, cancel, cancelScope, all, collect, mapConcurrentlyN, runProcess, checkedProcess, withScope, run);
  -- Keep the supported internal facade opaque; tests import Core deliberately.
}
