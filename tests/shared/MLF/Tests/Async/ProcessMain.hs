-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Tests.Async.ProcessMain where {
  import MLF.Primitive hiding (fail);
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import Async.Process;
  fail :: forall a. String -> IO a;
  fail message =
    do {
      putErr ("ASYNC TEST FAILURE: " ++ (message ++ "\n"));
      exitWith 1
    };
  assert :: Bool -> String -> IO Unit;
  assert condition message = if condition then ioReturn Unit else fail message;
  right :: forall a. Either AsyncError a -> IO a;
  right result =
    case result of {
      Right value -> ioReturn value;
      Left error -> fail (showInt (errorCode error) ++ (": " ++ errorMessage error))
    };
  errorIs :: forall a. Int -> Either AsyncError a -> Bool;
  errorIs code result =
    case result of {
      Left error -> (errorCode error == code);
      Right _ -> False
    };
  exited :: Int -> ProcessOutcome -> Bool;
  exited code outcome =
    case outcome of {
      Exited actual cleanup -> ((actual == code) && (cleanup == 0));
      _ -> False
    };
  cancelled :: Int -> ProcessOutcome -> Bool;
  cancelled reason outcome =
    case outcome of {
      Cancelled actual cleanup -> ((actual == reason) && (cleanup == 0));
      _ -> False
    };
  timedOut :: ProcessOutcome -> Bool;
  timedOut outcome =
    case outcome of {
      TimedOut cleanup -> (cleanup == 0);
      _ -> False
    };
  args2 a b = Cons a (Cons b Nil);
  args3 a b c = Cons a (Cons b (Cons c Nil));
  args4 a b c d = Cons a (Cons b (Cons c (Cons d Nil)));
  spec helper work name arguments =
    command helper arguments (work ++ ("/" ++ (name ++ ".out")))
      (work ++ ("/" ++ (name ++ ".err")));
  launch scope specification =
    do {
      result <- submit scope specification;
      right result
    };
  await scope handle =
    do {
      result <- awaitProcess scope handle;
      right result
    };
  assertFile path expected =
    do {
      actual <- readFile path;
      assert (eqString actual expected) ("wrong file: " ++ path)
    };
  absent path =
    do {
      found <- fileExists path;
      assert (L.not found) ("unexpected launch: " ++ path)
    };
  -- A bounded await services admission/timers while waiting for child readiness.
  -- The child and outer harness both have watchdogs; no timing is a pass oracle.
  ready :: ProcessScope -> ProcessHandle -> String -> IO Unit;
  ready scope handle path =
    do {
      found <- fileExists path;
      if found
      then ioReturn Unit
      else do {
             result <- awaitWithin scope handle (ForMilliseconds 10);
             assert (errorIs 10 result) "child exited before readiness";
             ready scope handle path
           }
    };
  capability =
    do {
      let {
        nul = stringFromCode 0
      };
      version <- processSupervisor ("MLF-PROCESS-1" ++ (nul ++ ("version" ++ nul)));
      assert (eqString version ("0" ++ (nul ++ ("1" ++ nul)))) "primitive capability version";
      unsupported <- processSupervisor ("MLF-PROCESS-99" ++ (nul ++ ("version" ++ nul)));
      assert (eqString (stringSlice unsupported 0 3) ("11" ++ nul))
        "unsupported transport version accepted";
      malformed <- processSupervisor "MLF-PROCESS-1";
      assert (eqString (stringSlice malformed 0 2) ("1" ++ nul)) "unterminated request accepted";
      negativeJobs <-
        processSupervisor
          ("MLF-PROCESS-1" ++
           (nul ++ ("create" ++ (nul ++ ("-1" ++ (nul ++ ("1" ++ (nul ++ ("1" ++ nul)))))))));
      assert (eqString (stringSlice negativeJobs 0 2) ("1" ++ nul))
        "negative transport option accepted";
      invalidMode <-
        processSupervisor
          ("MLF-PROCESS-1" ++ (nul ++ ("close" ++ (nul ++ ("0" ++ (nul ++ ("9" ++ nul)))))));
      assert (eqString (stringSlice invalidMode 0 2) ("1" ++ nul))
        "out-of-range close mode accepted";
      putStrLn "PASS capability-v1"
    };
  dynamic helper work =
    do {
      result <-
        withProcessScope (ScopeOptions 2 4 8)
          (\scope ->
             do {
               c <-
                 launch scope
                   (spec helper work "dynamic-c"
                      (args3 "hold" (work ++ "/c.ready") (work ++ "/c.release")));
               a <-
                 launch scope
                   (spec helper work "dynamic-a" (args2 "after-start" (work ++ "/c.ready")));
               first <- await scope a;
               assert (exited 23 first) "nonzero exit was not outcome data";
               again <- await scope a;
               assert (exited 23 again) "repeated await changed completion";
               cPending <- awaitWithin scope c (ForMilliseconds 0);
               assert (errorIs 8 cPending || errorIs 10 cPending) "unrelated C did not remain live";
               let {
                 code =
                   case exitCode first of {
                     Just value -> value;
                     Nothing -> 0
                   }
               };
               b <-
                 launch scope
                   (spec helper work "dynamic-b"
                      (args4 "dependent" (showInt code) (work ++ "/c.ready")
                         (work ++ "/c.release")));
               bResult <- await scope b;
               cResult <- await scope c;
               assert (exited 0 bResult && exited 0 cResult)
                 "dynamic dependent or concurrent child failed";
               ignored <- cancel scope a 9;
               right ignored;
               committed <- await scope a;
               assert (exited 23 committed) "late cancellation changed committed outcome";
               pending <-
                 launch scope
                   (spec helper work "request-cancel"
                      (args3 "hold" (work ++ "/request.ready") (work ++ "/request.release")));
               ready scope pending (work ++ "/request.ready");
               independent <-
                 launch scope (spec helper work "request-independent" (args2 "exit" "0"));
               requested <- requestCancel scope pending 61;
               right requested;
               progressed <- await scope independent;
               assert (exited 0 progressed) "unrelated child failed after requestCancel";
               requestedOutcome <- await scope pending;
               assert (cancelled 61 requestedOutcome) "requestCancel lost cancellation reason";
               ioReturn (Right Unit)
             });
      right result;
      assertFile (work ++ "/dynamic-b.out") "B saw A=23 while C was waiting\n";
      putStrLn "PASS dynamic-nonzero-repeat-await"
    };
  events helper work =
    do {
      result <-
        withProcessScope (ScopeOptions 1 1 2)
          (\scope ->
             do {
               empty <- poll scope;
               assert
                 (case empty of {
                    Right Nothing -> True;
                    _ -> False
                  })
                 "empty scope poll";
               handle <- launch scope (spec helper work "event" (args2 "exit" "7"));
               negativeAwait <- awaitWithin scope handle (ForMilliseconds (0 - 1));
               assert (errorIs 1 negativeAwait) "negative finite await became Forever";
               negativeWait <- waitNext scope (ForMilliseconds (0 - 1));
               assert (errorIs 1 negativeWait) "negative finite wait became Forever";
               event <- waitNext scope Forever;
               case event of {
                 Right (ProcessEvent delivered outcome) ->
                   do {
                     repeated <- await scope delivered;
                     assert (exited 7 outcome && exited 7 repeated) "wait event payload"
                   };
                 Left error -> fail (errorMessage error)
               };
               second <- poll scope;
               assert
                 (case second of {
                    Right Nothing -> True;
                    _ -> False
                  })
                 "completion delivered twice";
               repeated <- await scope handle;
               assert (exited 7 repeated) "event consumed retained outcome";
               ioReturn (Right Unit)
             });
      right result;
      putStrLn "PASS event-exactly-once"
    };
  queue helper work =
    do {
      result <-
        withProcessScope (ScopeOptions 1 1 8)
          (\scope ->
             do {
               running <-
                 launch scope
                   (spec helper work "queue-running"
                      (args3 "hold" (work ++ "/queue.ready") (work ++ "/queue.release")));
               ready scope running (work ++ "/queue.ready");
               queued <-
                 launch scope
                   (spec helper work "queue-pending" (args2 "mark" (work ++ "/queue.forbidden")));
               full <- submit scope (spec helper work "queue-overflow" (args2 "exit" "0"));
               assert (errorIs 6 full) "pending queue bound";
               cancelResult <- cancel scope queued 41;
               right cancelResult;
               outcome <- await scope queued;
               assert (cancelled 41 outcome) "queued cancellation outcome";
               writeFile (work ++ "/queue.release") "release\n";
               completed <- await scope running;
               assert (exited 0 completed) "queued cancellation affected running sibling";
               scopeChild <-
                 launch scope
                   (spec helper work "scope-running"
                      (args3 "hold" (work ++ "/scope.ready") (work ++ "/scope.release")));
               ready scope scopeChild (work ++ "/scope.ready");
               stop <- cancelScope scope 42;
               right stop;
               stopped <- await scope scopeChild;
               assert (cancelled 42 stopped) "scope cancellation reason";
               again <- cancelScope scope 43;
               right again;
               unchanged <- await scope scopeChild;
               assert (cancelled 42 unchanged) "repeated cancel changed outcome";
               refused <- submit scope (spec helper work "queue-after-stop" (args2 "exit" "0"));
               assert (errorIs 5 refused) "cancelled scope accepted submission";
               ioReturn (Right Unit)
             });
      right result;
      absent (work ++ "/queue.forbidden");
      putStrLn "PASS queued-cancel-and-bound"
    };
  retention helper work =
    do {
      result <-
        withProcessScope (ScopeOptions 1 1 1)
          (\scope ->
             do {
               handle <- launch scope (spec helper work "retained" (args2 "exit" "0"));
               outcome <- await scope handle;
               assert (exited 0 outcome) "retained original";
               full <- submit scope (spec helper work "retained-full" (args2 "exit" "0"));
               assert (errorIs 7 full) "completed retention was silently evicted";
               again <- await scope handle;
               assert (exited 0 again) "retained result disappeared";
               ioReturn (Right Unit)
             });
      right result;
      putStrLn "PASS retained-bound"
    };
  failureScope helper work =
    do {
      result <-
        withProcessScope (ScopeOptions 1 1 4)
          (\scope ->
             do {
               handle <-
                 launch scope
                   (spec helper work "failure-child"
                      (args3 "hold" (work ++ "/failure.pid") (work ++ "/failure.release")));
               ready scope handle (work ++ "/failure.pid");
               queued <-
                 launch scope
                   (spec helper work "failure-queued"
                      (args2 "mark" (work ++ "/failure.forbidden")));
               ioReturn (Left (AsyncError 99 "body failed"))
             });
      assert
        (case result of {
           Left (AsyncError code message) -> ((code == 99) && eqString message "body failed");
           _ -> False
         })
        "scope did not preserve explicit Either failure with successful cleanup";
      absent (work ++ "/failure.forbidden");
      check <-
        withProcessScope (ScopeOptions 1 1 1)
          (\scope ->
             do {
               handle <-
                 launch scope
                   (spec helper work "failure-gone" (args2 "assert-gone" (work ++ "/failure.pid")));
               outcome <- await scope handle;
               assert (exited 0 outcome) "scope returned before child was reaped";
               ioReturn (Right Unit)
             });
      right check;
      putStrLn "PASS scope-left-cancel-and-join"
    };
  closed helper work =
    do {
      escaped <-
        withProcessScope (ScopeOptions 1 1 1)
          (\scope ->
             do {
               handle <-
                 launch scope (spec helper work "joined" (args2 "mark" (work ++ "/joined.marker")));
               ioReturn (Right (Pair scope handle))
             });
      pair <- right escaped;
      assertFile (work ++ "/joined.marker") "launched\n";
      case pair of {
        Pair scope handle ->
          do {
            rejected <- awaitProcess scope handle;
            assert (errorIs 3 rejected || errorIs 5 rejected) "closed handle remained valid"
          }
      };
      putStrLn "PASS normal-scope-join-closed-handle"
    };
  crossScope helper work =
    do {
      result <-
        withProcessScope (ScopeOptions 1 1 1)
          (\outer ->
             do {
               handle <- launch outer (spec helper work "cross" (args2 "exit" "0"));
               nested <-
                 withProcessScope (ScopeOptions 1 1 1)
                   (\inner ->
                      do {
                        rejected <- awaitProcess inner handle;
                        assert (errorIs 4 rejected) "cross-scope handle accepted";
                        ioReturn (Right Unit)
                      });
               right nested;
               outcome <- await outer handle;
               assert (exited 0 outcome) "cross-scope rejection damaged owning scope";
               ioReturn (Right Unit)
             });
      right result;
      putStrLn "PASS cross-scope-handle"
    };
  timeouts helper work =
    do {
      result <-
        withProcessScope (ScopeOptions 1 1 4)
          (\scope ->
             do {
               let {
                 runningSpec =
                   ProcessSpec helper
                     (args3 "hold" (work ++ "/timeout.ready") (work ++ "/timeout.release"))
                     ""
                     ""
                     (work ++ "/timeout.out")
                     (work ++ "/timeout.err")
                     InheritEnvironment
                     40
                     0
               };
               handle <- launch scope runningSpec;
               outcome <- await scope handle;
               assert (timedOut outcome) "running timeout was not distinct";
               again <- await scope handle;
               assert (timedOut again) "timeout result changed";
               blocker <-
                 launch scope
                   (spec helper work "total-blocker"
                      (args3 "hold" (work ++ "/total.ready") (work ++ "/total.release")));
               ready scope blocker (work ++ "/total.ready");
               let {
                 queuedSpec =
                   ProcessSpec helper (args2 "mark" (work ++ "/total.forbidden")) "" ""
                     (work ++ "/total.out")
                     (work ++ "/total.err")
                     InheritEnvironment
                     0
                     30
               };
               queued <- launch scope queuedSpec;
               expired <- await scope queued;
               assert (timedOut expired) "total timeout did not include queue time";
               stopped <- cancel scope blocker 8;
               right stopped;
               ioReturn (Right Unit)
             });
      right result;
      absent (work ++ "/total.forbidden");
      putStrLn "PASS running-and-queued-timeout"
    };
  transport helper work =
    do {
      writeFile (work ++ "/cwd.marker") "cwd\n";
      writeFile (work ++ "/transport.stdin") "stdin λ\n";
      setEnv "ASYNC_PARENT_ONLY" "must not be inherited";
      result <-
        withProcessScope (ScopeOptions 1 1 2)
          (\scope ->
             do {
               let {
                 env =
                   ReplaceEnvironment (Cons "ASYNC_VALUE=line one\nλ=x" (Cons "ASYNC_EMPTY=" Nil))
               };
               let {
                 arguments = args2 "transport" "space ; $() ' \" \\ \t\nλ"
               };
               handle <-
                 launch scope
                   (ProcessSpec helper arguments work "transport.stdin" "transport.out"
                      "transport.err"
                      env
                      0
                      0);
               outcome <- await scope handle;
               assert (exited 0 outcome) "literal argv/environment/cwd/stdin transport";
               invalid <-
                 submit scope
                   (spec helper work "nul" (args2 "exit" ("0" ++ (stringFromCode 0 ++ "1"))));
               assert (errorIs 1 invalid) "embedded NUL accepted";
               missingLogs <- submit scope (command helper (args2 "exit" "0") "" "");
               assert (errorIs 1 missingLogs) "unbounded implicit capture accepted";
               ioReturn (Right Unit)
             });
      right result;
      unsetEnv "ASYNC_PARENT_ONLY";
      assertFile (work ++ "/transport.out") "argv-exact\nenv-exact\ncwd-exact\nstdin-exact\n";
      assertFile (work ++ "/transport.err") "stderr λ\n";
      putStrLn "PASS transport-argv-env-cwd-stdin"
    };
  inheritedEnvironment helper work =
    do {
      result <-
        withProcessScope (ScopeOptions 1 1 3)
          (\scope ->
             do {
               blocker <-
                 launch scope
                   (spec helper work "snapshot-blocker"
                      (args3 "hold" (work ++ "/snapshot.ready") (work ++ "/snapshot.release")));
               ready scope blocker (work ++ "/snapshot.ready");
               setEnv "ASYNC_SNAPSHOT" "submitted value";
               queued <- launch scope (spec helper work "snapshot" (Cons "environment" Nil));
               setEnv "ASYNC_SNAPSHOT" "changed after submit";
               writeFile (work ++ "/snapshot.release") "release\n";
               outcome <- await scope queued;
               assert (exited 0 outcome) "environment child failed";
               ioReturn (Right Unit)
             });
      right result;
      unsetEnv "ASYNC_SNAPSHOT";
      assertFile (work ++ "/snapshot.out") "changed after submit\n";
      putStrLn "PASS inherited-environment-at-launch"
    };
  logs helper work =
    do {
      result <-
        withProcessScope (ScopeOptions 1 1 1)
          (\scope ->
             do {
               handle <- launch scope (spec helper work "large" (Cons "large-logs" Nil));
               outcome <- await scope handle;
               assert (exited 0 outcome) "large stdout/stderr child failed or deadlocked";
               ioReturn (Right Unit)
             });
      right result;
      out <- readFile (work ++ "/large.out");
      err <- readFile (work ++ "/large.err");
      assert
        ((stringLength out == 262144) &&
         ((stringLength err == 262144) &&
          ((stringCodeAt out 262143 == 111) && (stringCodeAt err 262143 == 101))))
        "file-backed logs lost data";
      putStrLn "PASS file-backed-large-logs"
    };
  launchFailure work =
    do {
      result <-
        withProcessScope (ScopeOptions 1 1 1)
          (\scope ->
             do {
               handle <-
                 launch scope
                   (command (work ++ "/missing-executable") Nil (work ++ "/missing.out")
                      (work ++ "/missing.err"));
               outcome <- await scope handle;
               assert
                 (case outcome of {
                    LaunchFailed code cleanup -> ((code > 0) && (cleanup == 0));
                    _ -> False
                  })
                 "launch error became an exit status";
               ioReturn (Right Unit)
             });
      right result;
      putStrLn "PASS explicit-launch-failure"
    };
  main =
    do {
      helper <- getEnv "MLF_ASYNC_FIXTURE";
      work <- getEnv "MLF_ASYNC_WORK";
      assert ((stringLength helper > 0) && (stringLength work > 0)) "fixture environment missing";
      capability;
      dynamic helper work;
      events helper work;
      queue helper work;
      retention helper work;
      failureScope helper work;
      closed helper work;
      crossScope helper work;
      timeouts helper work;
      transport helper work;
      inheritedEnvironment helper work;
      logs helper work;
      launchFailure work;
      putStrLn "Async.Process: 13 interpreter/native contract cases passed"
    }
}
