-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Tests.Async.TaskProcesses where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Async.Task as T;
  import qualified Async.Process as P;
  bad message =
    do {
      putErr ("TASK PROCESS FAILURE: " ++ (message ++ "\n"));
      exitWith 1
    };
  assert condition message = if condition then ioReturn () else bad message;
  success :: forall a. T.Outcome a -> IO a;
  success outcome =
    case outcome of {
      T.Succeeded value -> ioReturn value;
      T.Failed error ->
        do {
          bad (P.errorMessage error);
          panic "unreachable"
        };
      T.Cancelled _ ->
        do {
          bad "unexpected cancellation";
          panic "unreachable"
        }
    };
  run task =
    do {
      outcome <- T.run T.defaultOptions task;
      success outcome
    };
  args2 a b = (:) a ((:) b []);
  args3 a b c = (:) a ((:) b ((:) c []));
  args4 a b c d = (:) a ((:) b ((:) c ((:) d [])));
  spec helper work name arguments =
    P.command helper arguments (work ++ ("/" ++ (name ++ ".out")))
      (work ++ ("/" ++ (name ++ ".err")));
  exited code outcome =
    case outcome of {
      P.Exited actual cleanup -> ((actual == code) && (cleanup == 0));
      _ -> False
    };
  assertFile path wanted =
    do {
      value <- readFile path;
      assert (eqString value wanted) ("artifact differs: " ++ path)
    };
  absent path =
    do {
      found <- fileExists path;
      assert (L.not found) ("unexpected execution: " ++ path)
    };
  cold helper work =
    do {
      let {
        task = T.checkedProcess (spec helper work "once" (args2 "once" (work ++ "/once.marker")))
      };
      absent (work ++ "/once.marker");
      pair <-
        run
          (T.bind (T.spawn task)
             (\fiber ->
                T.bind (T.await fiber)
                  (\first -> T.map (\second -> (,) first second) (T.await fiber))));
      case pair of {
        (,) first second ->
          assert (exited 0 first && exited 0 second) "repeated await reran cold task"
      };
      assertFile (work ++ "/once.marker") "once\n";
      let {
        unstarted =
          T.checkedProcess (spec helper work "cold" (args2 "mark" (work ++ "/cold.marker")))
      };
      ignored <- run (T.pure unstarted);
      absent (work ++ "/cold.marker");
      putStrLn "PASS cold-construction-spawn-once"
    };
  join helper work =
    do {
      value <-
        run
          (T.withScope
             (T.bind
                (T.spawn
                   (T.bind (T.sleep 1)
                      (\_ ->
                         T.checkedProcess
                           (spec helper work "joined" (args2 "mark" (work ++ "/joined.marker"))))))
                (\_ -> T.pure 9)));
      assert (value == 9) "scope result";
      assertFile (work ++ "/joined.marker") "launched\n";
      putStrLn "PASS scope-exit-joins-child"
    };
  dynamic helper work =
    do {
      pair <-
        run
          (T.bind
             (T.spawn
                (T.checkedProcess
                   (spec helper work "dynamic-c"
                      (args3 "hold" (work ++ "/c.ready") (work ++ "/c.release")))))
             (\c ->
                T.bind
                  (T.spawn
                     (T.runProcess
                        (spec helper work "dynamic-a" (args2 "after-start" (work ++ "/c.ready")))))
                  (\a ->
                     T.bind (T.await a)
                       (\aResult ->
                          case aResult of {
                            P.Exited value _ ->
                              T.bind
                                (T.checkedProcess
                                   (spec helper work "dynamic-b"
                                      (args4 "dependent" (showInt value) (work ++ "/c.ready")
                                         (work ++ "/c.release"))))
                                (\b -> T.map (\cResult -> (,) b cResult) (T.await c));
                            _ -> T.fail (P.AsyncError 990 "dynamic A did not exit")
                          }))));
      case pair of {
        (,) b c -> assert (exited 0 b && exited 0 c) "dynamic child result"
      };
      assertFile (work ++ "/dynamic-b.out") "B saw A=23 while C was waiting\n";
      putStrLn "PASS dynamic-submission-while-independent-process-runs"
    };
  cancelRunning helper work =
    do {
      outcome <-
        run
          (T.bind
             (T.spawn
                (T.runProcess
                   (spec helper work "cancel-live"
                      (args3 "hold" (work ++ "/cancel.ready") (work ++ "/cancel.never")))))
             (\fiber ->
                T.bind
                  (T.runProcess
                     (spec helper work "cancel-ready"
                        (args2 "after-start" (work ++ "/cancel.ready"))))
                  (\_ ->
                     T.bind (T.cancel fiber (T.CancelReason 44 "running"))
                       (\_ -> T.awaitOutcome fiber))));
      assert
        (case outcome of {
           T.Cancelled (T.CancelReason code _) -> (code == 44);
           _ -> False
         })
        "running cancellation outcome";
      gone <-
        run
          (T.checkedProcess
             (spec helper work "cancel-gone" (args2 "assert-gone" (work ++ "/cancel.ready"))));
      assert (exited 0 gone) "cancel returned before reaping";
      putStrLn "PASS running-process-cancellation-joins"
    };
  failFast helper work =
    do {
      outcome <-
        T.run T.defaultOptions
          (T.bind
             (T.spawn
                (T.runProcess
                   (spec helper work "failure-live"
                      (args3 "hold" (work ++ "/failure.ready") (work ++ "/failure.never")))))
             (\_ ->
                T.bind
                  (T.runProcess
                     (spec helper work "failure-ready"
                        (args2 "after-start" (work ++ "/failure.ready"))))
                  (\_ -> T.fail (P.AsyncError 991 "fail fast"))));
      assert
        (case outcome of {
           T.Failed error -> (P.errorCode error == 991);
           _ -> False
         })
        "fail-fast primary error changed";
      gone <-
        run
          (T.checkedProcess
             (spec helper work "failure-gone" (args2 "assert-gone" (work ++ "/failure.ready"))));
      assert (exited 0 gone) "failure returned before sibling reaping";
      putStrLn "PASS failure-cancels-and-joins-process-sibling"
    };
  processOutcomes helper work =
    do {
      nonzero <- run (T.runProcess (spec helper work "nonzero" (args2 "exit" "7")));
      assert (exited 7 nonzero) "nonzero process exit stopped being outcome data";
      checked <-
        run (T.capture (T.checkedProcess (spec helper work "checked-nonzero" (args2 "exit" "7"))));
      assert
        (case checked of {
           T.Failed error -> (P.errorCode error == 120);
           _ -> False
         })
        "checked nonzero exit was not failure";
      launch <- run (T.runProcess (spec (work ++ "/missing-executable") work "launch-failed" []));
      assert
        (case launch of {
           P.LaunchFailed error cleanup -> ((error /= 0) && (cleanup == 0));
           _ -> False
         })
        "launch failure was not outcome data";
      let {
        timed =
          P.ProcessSpec helper
            (args3 "hold" (work ++ "/running-timeout.ready") (work ++ "/running-timeout.never"))
            ""
            ""
            (work ++ "/running-timeout.out")
            (work ++ "/running-timeout.err")
            P.InheritEnvironment
            1
            0
      };
      timeout <- run (T.runProcess timed);
      assert
        (case timeout of {
           P.TimedOut cleanup -> (cleanup == 0);
           _ -> False
         })
        "running timeout was not outcome data";
      putStrLn "PASS process-outcomes-and-checked-failure"
    };
  yieldTwice = T.bind T.yield (\_ -> T.yield);
  oneJob = T.Options 8192 256 128 (P.ScopeOptions 1 1 64);
  queuedCancellation helper work =
    do {
      outcome <-
        T.run oneJob
          (T.bind
             (T.spawn
                (T.runProcess
                   (spec helper work "queue-held"
                      (args3 "hold" (work ++ "/queue.ready") (work ++ "/queue.never")))))
             (\held ->
                T.bind yieldTwice
                  (\_ ->
                     T.bind
                       (T.spawn
                          (T.runProcess
                             (spec helper work "queue-cancelled"
                                (args2 "mark" (work ++ "/queue.forbidden")))))
                       (\queued ->
                          T.bind yieldTwice
                            (\_ ->
                               T.bind (T.cancel queued (T.CancelReason 701 "queued process"))
                                 (\_ ->
                                    T.bind (T.cancel held (T.CancelReason 702 "release permit"))
                                      (\_ ->
                                         T.bind (T.awaitOutcome queued)
                                           (\stopped ->
                                              T.bind (T.awaitOutcome held)
                                                (\_ ->
                                                   T.map (\_ -> stopped)
                                                     (T.checkedProcess
                                                        (spec helper work "queue-next"
                                                           (args2 "mark"
                                                              (work ++ "/queue.next")))))))))))));
      stopped <- success outcome;
      assert
        (case stopped of {
           T.Cancelled (T.CancelReason code _) -> (code == 701);
           _ -> False
         })
        "queued process cancel lost";
      absent (work ++ "/queue.forbidden");
      assertFile (work ++ "/queue.next") "launched\n";
      putStrLn "PASS cancelled-pending-process-never-admitted"
    };
  ancestorCancellation helper work =
    do {
      stopped <-
        run
          (T.bind
             (T.spawn
                (T.withScope
                   (T.runProcess
                      (spec helper work "ancestor-cancelled"
                         (args2 "mark" (work ++ "/ancestor.forbidden"))))))
             (\fiber ->
                T.bind yieldTwice
                  (\_ ->
                     T.bind (T.cancel fiber (T.CancelReason 712 "nested owner"))
                       (\_ -> T.awaitOutcome fiber))));
      assert
        (case stopped of {
           T.Cancelled (T.CancelReason code _) -> (code == 712);
           _ -> False
         })
        "ancestor cancellation lost";
      absent (work ++ "/ancestor.forbidden");
      putStrLn "PASS ancestor-cancellation-before-nested-admission"
    };
  queuedDeadline helper work =
    do {
      let {
        timed =
          P.ProcessSpec helper (args2 "mark" (work ++ "/timeout.forbidden")) "" ""
            (work ++ "/timeout.out")
            (work ++ "/timeout.err")
            P.InheritEnvironment
            0
            5
      };
      outcome <-
        T.run oneJob
          (T.bind
             (T.spawn
                (T.runProcess
                   (spec helper work "timeout-held"
                      (args3 "hold" (work ++ "/timeout.ready") (work ++ "/timeout.never")))))
             (\held ->
                T.bind yieldTwice
                  (\_ ->
                     T.bind (T.withScope (T.runProcess timed))
                       (\expired ->
                          T.bind (T.cancel held (T.CancelReason 703 "done"))
                            (\_ -> T.pure expired)))));
      expired <- success outcome;
      assert
        (case expired of {
           P.TimedOut cleanup -> (cleanup == 0);
           _ -> False
         })
        "Task queue time reset process total deadline";
      absent (work ++ "/timeout.forbidden");
      putStrLn "PASS pending-process-total-deadline-includes-task-queue"
    };
  pendingBound helper work =
    do {
      outcome <-
        T.run oneJob
          (T.bind
             (T.spawn
                (T.runProcess
                   (spec helper work "bound-held"
                      (args3 "hold" (work ++ "/bound.ready") (work ++ "/bound.never")))))
             (\held ->
                T.bind yieldTwice
                  (\_ ->
                     T.bind
                       (T.spawn
                          (T.runProcess
                             (spec helper work "bound-pending"
                                (args2 "mark" (work ++ "/bound.forbidden")))))
                       (\pending ->
                          T.bind yieldTwice
                            (\_ ->
                               T.bind
                                 (T.capture
                                    (T.runProcess
                                       (spec helper work "bound-overflow"
                                          (args2 "mark" (work ++ "/bound.overflow")))))
                                 (\overflow ->
                                    T.bind (T.cancel pending (T.CancelReason 704 "pending"))
                                      (\_ ->
                                         T.bind (T.cancel held (T.CancelReason 705 "held"))
                                           (\_ -> T.pure overflow))))))));
      overflow <- success outcome;
      assert
        (case overflow of {
           T.Failed error -> (P.errorCode error == 6);
           _ -> False
         })
        "pending queue bound was bypassed";
      absent (work ++ "/bound.forbidden");
      absent (work ++ "/bound.overflow");
      putStrLn "PASS task-owned-process-pending-limit"
    };
  valueTask helper work name value =
    T.map (\_ -> value)
      (T.checkedProcess
         (spec helper work name
            (args3 "value" (showInt value) (work ++ ("/" ++ (name ++ ".artifact"))))));
  -- A synthetic dynamic build diamond: one owned prerequisite is awaited twice;
  -- B and C are discovered from its value, then D is discovered from both.
  -- Query keys, cache validity and artifact publication belong to a later engine.
  diamond helper work jobs =
    do {
      let {
        tag = ("diamond-" ++ (showInt jobs ++ "-"))
      };
      let {
        options = T.Options 8192 256 128 (P.ScopeOptions jobs 8 64)
      };
      outcome <-
        T.run options
          (T.bind (T.spawn (valueTask helper work (tag ++ "a") 41))
             (\a ->
                T.bind
                  (T.spawn
                     (T.bind (T.await a)
                        (\value -> valueTask helper work (tag ++ "b") (value + 1))))
                  (\b ->
                     T.bind
                       (T.spawn
                          (T.bind (T.await a)
                             (\value -> valueTask helper work (tag ++ "c") (value + 2))))
                       (\c ->
                          T.bind (T.await b)
                            (\bValue ->
                               T.bind (T.await c)
                                 (\cValue ->
                                    valueTask helper work (tag ++ "d") (bValue + cValue)))))));
      result <- success outcome;
      assert (result == 85) "diamond result";
      assertFile (work ++ ("/" ++ (tag ++ "a.artifact"))) "41";
      assertFile (work ++ ("/" ++ (tag ++ "b.artifact"))) "42";
      assertFile (work ++ ("/" ++ (tag ++ "c.artifact"))) "43";
      assertFile (work ++ ("/" ++ (tag ++ "d.artifact"))) "85";
      ioReturn result
    };
  main =
    do {
      helper <- getEnv "MLF_ASYNC_FIXTURE";
      work <- getEnv "MLF_ASYNC_WORK";
      assert ((stringLength helper > 0) && (stringLength work > 0)) "missing harness paths";
      cold helper work;
      join helper work;
      dynamic helper work;
      cancelRunning helper work;
      failFast helper work;
      processOutcomes helper work;
      queuedCancellation helper work;
      ancestorCancellation helper work;
      queuedDeadline helper work;
      pendingBound helper work;
      one <- diamond helper work 1;
      many <- diamond helper work 4;
      assert (one == many) "jobs changed successful artifact values";
      putStrLn "PASS synthetic-dynamic-diamond-jobs-one-and-four"
    }
}
