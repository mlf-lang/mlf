-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Async.Task.Core where {
  import MLF.Primitive hiding (runProcess);
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import Async.Process (AsyncError(..));
  import qualified Async.Process as P;
  import qualified Async.Process.Internal as PI;
  -- Internal scheduler implementation and explicit white-box test interface.
  -- Public Task and Internal facades keep constructors private.
  -- Only uniform IO Unit resumptions enter the runtime queue. Generic outcomes
  -- never pass through an IntTable or an ID-to-value lookup. Constructors stay
  -- private, including the resolver endpoint inside Fiber.
  data Task a = Task (Context -> (Outcome a -> IO Unit) -> IO Unit);
  data Fiber a = Fiber Scope Int (Completion (Outcome a)) (Completion CancelReason);
  data Outcome a = Succeeded a | Failed AsyncError | Cancelled CancelReason;
  data CancelReason = CancelReason Int String;
  -- Retained cells, callback reservations, maximum live fibers, process options.
  -- A waiting fiber consumes retained memory, but no process/runnable permit.
  data Options = Options Int Int Int P.ScopeOptions;
  data Scope =
    Scope AsyncScope IntArray IntTable (Completion AsyncError) (Completion CancelReason) (Completion
                                                                                          Unit) P.ProcessScope Limits;
  -- Shared counters: 0 live fibers, 1 admitted processes, 2 pending processes.
  -- The cleanup cell is group-local and retains the first cleanup diagnostic.
  data Limits = Limits Int Int Int IntArray (Completion AsyncError) (Maybe Context);
  data Context = Context Scope Int (Completion CancelReason);
  defaultOptions :: Options;
  defaultOptions = Options 65536 8192 4096 P.defaultOptions;
  unit :: IO Unit;
  unit = ioReturn Unit;
  runtimeError :: Int -> String -> AsyncError;
  runtimeError code operation =
    AsyncError (100 + code) (operation ++ (" (async status " ++ (showInt code ++ ")")));
  limitError :: AsyncError;
  limitError = runtimeError 4 "retained completion or live fiber limit reached";
  -- Metadata: 0 next fiber ID, 1 live fibers, 2 closed, 3 identity probe.
  -- Identity is tested through a private mutable bit, without requiring pointer
  -- equality or manufacturing any typed handle. No callback runs between writes.
  sameScope :: Scope -> Scope -> IO Bool;
  sameScope (Scope _ first _ _ _ _ _ _) (Scope _ second _ _ _ _ _ _) =
    do {
      writeIntArray first 3 0;
      writeIntArray second 3 1;
      value <- readIntArray first 3;
      ioReturn (value == 1)
    };
  stopped :: Context -> IO (Maybe (Outcome Unit));
  stopped (Context (Scope _ metadata _ failure stoppedScope _ _ (Limits _ _ _ _ _ parent)) _ stoppedFiber) =
    do {
      closed <- readIntArray metadata 2;
      if (closed == 1)
      then ioReturn (Just (Failed (runtimeError 3 "scope is closed")))
      else do {
             inherited <-
               case parent of {
                 Nothing -> ioReturn Nothing;
                 Just context -> stopped context
               };
             case inherited of {
               Just outcome -> ioReturn (Just outcome);
               Nothing ->
                 asyncReadCompletion failure (\error -> ioReturn (Just (Failed error)))
                   (asyncReadCompletion stoppedScope (\reason -> ioReturn (Just (Cancelled reason)))
                      (asyncReadCompletion stoppedFiber
                         (\reason -> ioReturn (Just (Cancelled reason)))
                         (ioReturn Nothing)))
             }
           }
    };
  stopAs :: forall a. Outcome Unit -> Outcome a;
  stopAs outcome =
    case outcome of {
      Failed error -> Failed error;
      Cancelled reason -> Cancelled reason;
      Succeeded _ -> Failed (runtimeError 12 "invalid stop outcome")
    };
  start :: forall a. Task a -> Context -> (Outcome a -> IO Unit) -> IO Unit;
  start (Task action) context complete =
    do {
      stop <- stopped context;
      case stop of {
        Just outcome -> complete (stopAs outcome);
        Nothing -> action context complete
      }
    };
  taskPure :: forall a. a -> Task a;
  taskPure value = Task (\_ complete -> complete (Succeeded value));
  taskMap :: forall a b. (a -> b) -> Task a -> Task b;
  taskMap function task = taskBind task (\value -> taskPure (function value));
  taskBind :: forall a b. Task a -> (a -> Task b) -> Task b;
  taskBind task next =
    Task
      (\context complete ->
         start task context
           (\outcome ->
              case outcome of {
                Succeeded value -> start (next value) context complete;
                Failed error -> complete (Failed error);
                Cancelled reason -> complete (Cancelled reason)
              }));
  taskFail :: forall a. AsyncError -> Task a;
  taskFail error = Task (\_ complete -> complete (Failed error));
  -- Recovery happens inside the child's task before its fiber reports failure.
  -- External cancellation remains cancellation and is never converted to success.
  capture :: forall a. Task a -> Task (Outcome a);
  capture task =
    Task
      (\context complete ->
         start task context
           (\outcome ->
              case outcome of {
                Succeeded value -> complete (Succeeded (Succeeded value));
                Failed error ->
                  do {
                    stop <- stopped context;
                    case stop of {
                      Nothing -> complete (Succeeded (Failed error));
                      Just external -> complete (preserveCleanup external error)
                    }
                  };
                Cancelled reason -> complete (Cancelled reason)
              }));
  -- Cancellation still propagates through capture, but cleanup failure is never
  -- turned back into an ordinary cancellation or overwritten primary failure.
  preserveCleanup :: forall a. Outcome Unit -> AsyncError -> Outcome a;
  preserveCleanup external original =
    case original of {
      CleanupFailed _ cleanup ->
        Failed
          (CleanupFailed
             (case external of {
                Failed primary -> primary;
                Cancelled (CancelReason code message) ->
                  AsyncError 122 ("task cancelled (" ++ (showInt code ++ ("): " ++ message)));
                Succeeded _ -> runtimeError 12 "invalid external stop"
              })
             cleanup);
      _ -> stopAs external
    };
  finish :: forall a. Context -> Completion (Outcome a) -> Outcome a -> IO Unit;
  finish (Context (Scope _ metadata edges failure scopeStop drained _ (Limits _ _ _ shared cleanup _)) identity _) cell outcome =
    do {
      accepted <- asyncResolveCompletion cell outcome;
      if (accepted == 0)
      then do {
             writeIntTable edges identity 0;
             total <- readIntArray shared 0;
             writeIntArray shared 0 (total - 1);
             case outcome of {
               Failed (CleanupFailed _ error) ->
                 ioBind (asyncResolveCompletion cleanup error) (\_ -> unit);
               _ -> unit
             };
             active <- readIntArray metadata 1;
             writeIntArray metadata 1 (active - 1);
             if (active == 1)
             then ioBind (asyncResolveCompletion drained Unit) (\_ -> unit)
             else unit;
             case outcome of {
               Failed error -> ioBind (asyncResolveCompletion failure error) (\_ -> unit);
               Cancelled reason ->
                 if (identity == 0)
                 then ioBind (asyncResolveCompletion scopeStop reason) (\_ -> unit)
                 else unit;
               _ -> unit
             }
           }
      else unit
    };
  launch :: forall a. Scope -> Task a -> (Either AsyncError (Fiber a) -> IO Unit) -> IO Unit;
  launch scope task complete =
    case scope of {
      Scope queue metadata _ _ _ _ _ (Limits maximum _ _ shared _ _) ->
        do {
          closed <- readIntArray metadata 2;
          active <- readIntArray metadata 1;
          total <- readIntArray shared 0;
          if (closed == 1)
          then complete (Left (runtimeError 3 "scope is closed"))
          else if (total >= maximum)
               then complete (Left limitError)
               else asyncNewCompletion queue
                      (\cell ->
                         asyncNewCompletion queue
                           (\stop ->
                              do {
                                identity <- readIntArray metadata 0;
                                writeIntArray metadata 0 (identity + 1);
                                writeIntArray metadata 1 (active + 1);
                                writeIntArray shared 0 (total + 1);
                                let {
                                  context = Context scope identity stop
                                };
                                queued <-
                                  asyncEnqueue queue (start task context (finish context cell));
                                status <- asyncSubscriptionStatus queued;
                                if (status == 0)
                                then complete (Right (Fiber scope identity cell stop))
                                else do {
                                       finish context cell
                                         (Failed (runtimeError status "cannot enqueue fiber"));
                                       complete (Left (runtimeError status "cannot enqueue fiber"))
                                     }
                              })
                           (complete (Left limitError)))
                      (complete (Left limitError))
        }
    };
  spawn :: forall a. Task a -> Task (Fiber a);
  spawn task =
    Task
      (\context complete ->
         case context of {
           Context scope _ _ ->
             launch scope task
               (\result ->
                  case result of {
                    Left error -> complete (Failed error);
                    Right fiber -> complete (Succeeded fiber)
                  })
         });
  dropSubscriptions :: List AsyncSubscription -> IO Unit;
  dropSubscriptions subscriptions =
    case subscriptions of {
      Nil -> unit;
      Cons subscription rest ->
        do {
          asyncCancelSubscription subscription;
          dropSubscriptions rest
        }
    };
  subscriptionsOK :: List AsyncSubscription -> IO Int;
  subscriptionsOK subscriptions =
    case subscriptions of {
      Nil -> ioReturn 0;
      Cons subscription rest ->
        do {
          status <- asyncSubscriptionStatus subscription;
          if (status == 0) then subscriptionsOK rest else ioReturn status
        }
    };
  -- Each fiber has at most one dynamic wait edge. IDs identify graph metadata
  -- only; the typed cell always arrives directly through the opaque Fiber.
  reaches :: IntTable -> Int -> Int -> IO Bool;
  reaches edges current wanted =
    if (current == wanted)
    then ioReturn True
    else do {
           target <- readIntTable edges current;
           if (target == 0) then ioReturn False else reaches edges (target - 1) wanted
         };
  resumeWait :: forall a. Context ->
                          IntArray ->
                          Completion (List AsyncSubscription) ->
                          (Outcome a -> IO Unit) -> Outcome a -> IO Unit;
  resumeWait context won subscriptions complete outcome =
    do {
      already <- readIntArray won 0;
      if (already == 1)
      then unit
      else do {
             writeIntArray won 0 1;
             asyncReadCompletion subscriptions dropSubscriptions unit;
             case context of {
               Context (Scope _ _ edges _ _ _ _ _) identity _ -> writeIntTable edges identity 0
             };
             stop <- stopped context;
             case stop of {
               Just external -> complete (stopAs external);
               Nothing -> complete outcome
             }
           }
    };
  waitPending :: forall a. Context ->
                           Int -> Completion (Outcome a) -> (Outcome a -> IO Unit) -> IO Unit;
  waitPending context target cell complete =
    case context of {
      Context (Scope queue _ edges failure scopeStop _ _ _) identity fiberStop ->
        do {
          cyclic <- reaches edges target identity;
          if cyclic
          then complete (Failed (runtimeError 9 "self-await or dynamic wait cycle"))
          else asyncNewCompletion queue
                 (\subscriptions ->
                    do {
                      won <- newIntArray 1 0;
                      let {
                        resume = resumeWait context won subscriptions complete
                      };
                      valueSubscription <- asyncSubscribeCompletion cell resume;
                      failureSubscription <-
                        asyncSubscribeCompletion failure (\error -> resume (Failed error));
                      scopeSubscription <-
                        asyncSubscribeCompletion scopeStop (\reason -> resume (Cancelled reason));
                      fiberSubscription <-
                        asyncSubscribeCompletion fiberStop (\reason -> resume (Cancelled reason));
                      let {
                        registered =
                          Cons valueSubscription
                            (Cons failureSubscription
                               (Cons scopeSubscription (Cons fiberSubscription Nil)))
                      };
                      asyncResolveCompletion subscriptions registered;
                      status <- subscriptionsOK registered;
                      if (status == 0)
                      then writeIntTable edges identity (target + 1)
                      else do {
                             writeIntArray won 0 1;
                             dropSubscriptions registered;
                             complete
                               (Failed (runtimeError status "cannot reserve await callbacks"))
                           }
                    })
                 (complete (Failed limitError))
        }
    };
  awaitOutcome :: forall a. Fiber a -> Task (Outcome a);
  awaitOutcome (Fiber owner target cell _) =
    Task
      (\context complete ->
         case context of {
           Context scope _ _ ->
             do {
               same <- sameScope scope owner;
               if L.not same
               then complete (Failed (runtimeError 5 "fiber belongs to another scope"))
               else do {
                      let {
                        observe =
                          \outcome ->
                            do {
                              stop <- stopped context;
                              case stop of {
                                Nothing -> complete (Succeeded outcome);
                                Just external -> complete (stopAs external)
                              }
                            }
                      };
                      asyncReadCompletion cell observe (waitPending context target cell observe)
                    }
             }
         });
  await :: forall a. Fiber a -> Task a;
  await fiber =
    taskBind (awaitOutcome fiber)
      (\outcome ->
         case outcome of {
           Succeeded value -> taskPure value;
           Failed error -> taskFail error;
           Cancelled reason -> Task (\_ complete -> complete (Cancelled reason))
         });
  yield :: Task Unit;
  yield =
    Task
      (\context complete ->
         case context of {
           Context (Scope queue _ _ _ _ _ _ _) _ _ ->
             do {
               queued <- asyncEnqueue queue (start (taskPure Unit) context complete);
               status <- asyncSubscriptionStatus queued;
               if (status == 0)
               then unit
               else complete (Failed (runtimeError status "cannot enqueue yield"))
             }
         });
  -- Timers are monotonic native reservations. Cancellation/failure removes the
  -- sleeping timer immediately; it never waits for the original duration.
  sleep :: Int -> Task Unit;
  sleep milliseconds =
    if ((milliseconds < 0) || (milliseconds > 4294967295))
    then taskFail (runtimeError 1 "invalid sleep duration")
    else Task
           (\context complete ->
              case context of {
                Context (Scope queue _ _ failure scopeStop _ _ _) _ fiberStop ->
                  asyncNewCompletion queue
                    (\subscriptions ->
                       do {
                         won <- newIntArray 1 0;
                         let {
                           resume = resumeWait context won subscriptions complete
                         };
                         timer <- asyncDelay queue milliseconds (resume (Succeeded Unit));
                         failed <-
                           asyncSubscribeCompletion failure (\error -> resume (Failed error));
                         scopeCancelled <-
                           asyncSubscribeCompletion scopeStop
                             (\reason -> resume (Cancelled reason));
                         fiberCancelled <-
                           asyncSubscribeCompletion fiberStop
                             (\reason -> resume (Cancelled reason));
                         let {
                           registered =
                             Cons timer
                               (Cons failed (Cons scopeCancelled (Cons fiberCancelled Nil)))
                         };
                         asyncResolveCompletion subscriptions registered;
                         status <- subscriptionsOK registered;
                         if (status == 0)
                         then unit
                         else do {
                                writeIntArray won 0 1;
                                dropSubscriptions registered;
                                complete
                                  (Failed (runtimeError status "cannot reserve sleep callbacks"))
                              }
                       })
                    (complete (Failed limitError))
              });
  cancel :: forall a. Fiber a -> CancelReason -> Task Unit;
  cancel (Fiber owner _ result stoppedFiber) reason =
    Task
      (\context complete ->
         case context of {
           Context scope _ _ ->
             do {
               same <- sameScope scope owner;
               if L.not same
               then complete (Failed (runtimeError 5 "fiber belongs to another scope"))
               else asyncReadCompletion result (\_ -> complete (Succeeded Unit))
                      (do {
                         asyncResolveCompletion stoppedFiber reason;
                         complete (Succeeded Unit)
                       })
             }
         });
  cancelScope :: CancelReason -> Task Unit;
  cancelScope reason =
    Task
      (\context complete ->
         case context of {
           Context (Scope _ _ _ _ stoppedScope _ _ _) _ _ ->
             do {
               asyncResolveCompletion stoppedScope reason;
               complete (Cancelled reason)
             }
         });
  spawnWindow :: forall a. Int -> List (Task a) -> Task (Pair (List (Fiber a)) (List (Task a)));
  spawnWindow count tasks =
    if (count <= 0)
    then taskPure (Pair Nil tasks)
    else case tasks of {
           Nil -> taskPure (Pair Nil Nil);
           Cons task rest ->
             taskBind (spawn task)
               (\fiber ->
                  taskBind (spawnWindow (count - 1) rest)
                    (\remaining ->
                       case remaining of {
                         Pair fibers pending -> taskPure (Pair (Cons fiber fibers) pending)
                       }))
         };
  awaitWindow :: forall a. List (Fiber a) -> Task (List a);
  awaitWindow fibers =
    case fibers of {
      Nil -> taskPure Nil;
      Cons fiber rest ->
        taskBind (await fiber) (\value -> taskMap (\values -> Cons value values) (awaitWindow rest))
    };
  -- Bounded, input-ordered windows deliberately avoid allocating an unbounded
  -- list of fibers or callbacks. A slow first window can leave unused capacity.
  all :: forall a. Int -> List (Task a) -> Task (List a);
  all width tasks =
    if (width <= 0)
    then taskFail (runtimeError 1 "concurrency width must be positive")
    else case tasks of {
           Nil -> taskPure Nil;
           _ ->
             taskBind (spawnWindow width tasks)
               (\window ->
                  case window of {
                    Pair fibers pending ->
                      taskBind (awaitWindow fibers)
                        (\values -> taskMap (L.append values) (all width pending))
                  })
         };
  collect :: forall a. Int -> List (Task a) -> Task (List (Outcome a));
  collect width tasks = all width (L.map capture tasks);
  mapConcurrentlyN :: forall a b. Int -> (a -> Task b) -> List a -> Task (List b);
  mapConcurrentlyN width function values = all width (L.map function values);
  -- On a scheduler/protocol failure there may be no callback slot left. The
  -- error path joins this specific process synchronously before releasing its
  -- fiber; a nested scope cannot report completion with an abandoned child.
  failProcess :: P.ProcessScope ->
                 P.ProcessHandle -> AsyncError -> (Outcome P.ProcessOutcome -> IO Unit) -> IO Unit;
  failProcess processes handle primary complete =
    do {
      cleanup <- P.cancel processes handle 0;
      complete
        (Failed
           (case cleanup of {
              Right _ -> primary;
              Left error -> P.CleanupFailed primary error
            }))
    };
  -- A stopped task still owns cleanup diagnostics. Nested task scopes share
  -- their process supervisor, so do not postpone these errors to outer teardown.
  processStopped :: Outcome Unit -> P.ProcessOutcome -> Outcome P.ProcessOutcome;
  processStopped stoppedOutcome processOutcome =
    if (P.cleanupError processOutcome == 0)
    then stopAs stoppedOutcome
    else let {
           primary =
             case stoppedOutcome of {
               Failed error -> error;
               Cancelled (CancelReason code message) ->
                 AsyncError 122 ("task cancelled (" ++ (showInt code ++ ("): " ++ message)));
               Succeeded _ -> runtimeError 12 "invalid process stop outcome"
             }
         } in
         Failed
           (P.CleanupFailed primary
              (AsyncError (P.cleanupError processOutcome) "process cleanup failed"));
  pollProcess :: Context -> P.ProcessHandle -> (Outcome P.ProcessOutcome -> IO Unit) -> IO Unit;
  pollProcess context handle complete =
    case context of {
      Context (Scope queue _ _ _ _ _ processes _) _ _ ->
        do {
          stop <- stopped context;
          requested <-
            case stop of {
              Nothing -> ioReturn (Right Unit);
              Just _ -> P.requestCancel processes handle 0
            };
          case requested of {
            Left error -> failProcess processes handle error complete;
            Right _ ->
              do {
                result <- P.awaitWithin processes handle (P.ForMilliseconds 0);
                case result of {
                  Right outcome ->
                    case stop of {
                      Nothing -> complete (Succeeded outcome);
                      Just external -> complete (processStopped external outcome)
                    };
                  Left error ->
                    if ((P.errorCode error == 8) || (P.errorCode error == 10))
                    then do {
                           queued <- asyncDelay queue 2 (pollProcess context handle complete);
                           status <- asyncSubscriptionStatus queued;
                           if (status == 0)
                           then unit
                           else failProcess processes handle
                                  (runtimeError status "cannot enqueue process poll")
                                  complete
                         }
                    else failProcess processes handle error complete
                }
              }
          }
        }
    };
  clockMilliseconds :: IO (Either AsyncError Int);
  clockMilliseconds =
    do {
      result <- PI.request (Cons "clock" Nil);
      ioReturn
        (case result of {
           Right (Cons value Nil) -> Right (readInt value);
           Left (Pair code message) -> Left (AsyncError code message);
           _ -> Left (runtimeError 12 "invalid monotonic clock response")
         })
    };
  releasePending :: IntArray -> Bool -> IO Unit;
  releasePending shared waiting =
    if L.not waiting
    then unit
    else do {
           pending <- readIntArray shared 2;
           writeIntArray shared 2 (pending - 1)
         };
  finishProcess :: IntArray ->
                   (Outcome P.ProcessOutcome -> IO Unit) -> Outcome P.ProcessOutcome -> IO Unit;
  finishProcess shared complete outcome =
    do {
      active <- readIntArray shared 1;
      writeIntArray shared 1 (active - 1);
      complete outcome
    };
  remainingSpec :: P.ProcessSpec -> Maybe Int -> Int -> P.ProcessSpec;
  remainingSpec specification deadline now =
    case specification of {
      P.ProcessSpec executable arguments cwd input output errors environment running total ->
        P.ProcessSpec executable arguments cwd input output errors environment running
          (case deadline of {
             Nothing -> total;
             Just at -> (at - now)
           })
    };
  queueProcess :: Context ->
                  P.ProcessSpec -> Maybe Int -> (Outcome P.ProcessOutcome -> IO Unit) -> IO Unit;
  queueProcess context specification deadline complete =
    case context of {
      Context (Scope queue _ _ _ _ _ _ (Limits _ _ _ shared _ _)) _ _ ->
        do {
          reserved <-
            asyncDelay queue 2 (admitProcess context specification deadline True complete);
          status <- asyncSubscriptionStatus reserved;
          if (status == 0)
          then unit
          else do {
                 releasePending shared True;
                 complete (Failed (runtimeError status "cannot reserve process admission"))
               }
        }
    };
  -- Keep waiting work in the Task coordinator, never in the native launch queue.
  -- A stopped waiter therefore cannot be launched by another fiber's native pump.
  -- Shared active/pending counters also apply to every nested task group.
  admitProcess :: Context ->
                  P.ProcessSpec ->
                  Maybe Int -> Bool -> (Outcome P.ProcessOutcome -> IO Unit) -> IO Unit;
  admitProcess context specification deadline waiting complete =
    case context of {
      Context (Scope _ _ _ _ _ _ processes (Limits _ jobs pendingLimit shared _ _)) _ _ ->
        do {
          stop <- stopped context;
          case stop of {
            Just external ->
              do {
                releasePending shared waiting;
                complete (stopAs external)
              };
            Nothing ->
              do {
                clock <-
                  case deadline of {
                    Nothing -> ioReturn (Right 0);
                    Just _ -> clockMilliseconds
                  };
                case clock of {
                  Left error ->
                    do {
                      releasePending shared waiting;
                      complete (Failed error)
                    };
                  Right now ->
                    if case deadline of {
                         Nothing -> False;
                         Just at -> (now >= at)
                       }
                    then do {
                           releasePending shared waiting;
                           complete (Succeeded (P.TimedOut 0))
                         }
                    else do {
                           active <- readIntArray shared 1;
                           if (active < jobs)
                           then do {
                                  releasePending shared waiting;
                                  writeIntArray shared 1 (active + 1);
                                  submitted <-
                                    P.submit processes (remainingSpec specification deadline now);
                                  case submitted of {
                                    Left error -> finishProcess shared complete (Failed error);
                                    Right handle ->
                                      pollProcess context handle (finishProcess shared complete)
                                  }
                                }
                           else if waiting
                                then queueProcess context specification deadline complete
                                else do {
                                       pending <- readIntArray shared 2;
                                       if (pending >= pendingLimit)
                                       then complete
                                              (Failed
                                                 (AsyncError 6 "pending process queue is full"))
                                       else do {
                                              writeIntArray shared 2 (pending + 1);
                                              queueProcess context specification deadline complete
                                            }
                                     }
                         }
                }
              }
          }
        }
    };
  runProcess :: P.ProcessSpec -> Task P.ProcessOutcome;
  -- Reserve before admission, and account ready-queue time in total.
  runProcess specification =
    Task
      (\context complete ->
         case context of {
           Context (Scope queue _ _ _ _ _ _ _) _ _ ->
             case specification of {
               P.ProcessSpec _ _ _ _ _ _ _ running total ->
                 if ((running < 0) ||
                     ((running > 4294967295) || ((total < 0) || (total > 4294967295))))
                 then complete (Failed (AsyncError 1 "invalid process timeout"))
                 else do {
                        clock <- if (total == 0) then ioReturn (Right 0) else clockMilliseconds;
                        case clock of {
                          Left error -> complete (Failed error);
                          Right now ->
                            do {
                              let {
                                deadline = if (total == 0) then Nothing else Just (now + total)
                              };
                              reserved <-
                                asyncEnqueue queue
                                  (admitProcess context specification deadline False complete);
                              status <- asyncSubscriptionStatus reserved;
                              if (status == 0)
                              then unit
                              else complete
                                     (Failed
                                        (runtimeError status "cannot reserve process continuation"))
                            }
                        }
                      }
             }
         });
  checkedProcess :: P.ProcessSpec -> Task P.ProcessOutcome;
  checkedProcess specification =
    taskBind (runProcess specification)
      (\outcome ->
         case outcome of {
           P.Exited code cleanup ->
             if ((code == 0) && (cleanup == 0))
             then taskPure outcome
             else taskFail
                    (AsyncError 120
                       ("process failed: exit " ++
                        (showInt code ++ (", cleanup " ++ showInt cleanup))));
           P.LaunchFailed code cleanup ->
             taskFail
               (AsyncError 121
                  ("process launch failed: " ++
                   (showInt code ++ (", cleanup " ++ showInt cleanup))));
           P.Cancelled reason cleanup ->
             taskFail
               (AsyncError 122
                  ("process cancelled: " ++ (showInt reason ++ (", cleanup " ++ showInt cleanup))));
           P.TimedOut cleanup ->
             taskFail (AsyncError 123 ("process timed out; cleanup " ++ showInt cleanup))
         });
  -- Run drains every started fiber, even after the root returns. Failure and
  -- cancellation wake suspended waits through reserved callbacks. The process
  -- scope then joins or cancels-and-joins before the result leaves this function.
  drain :: Scope -> IO Unit;
  drain scope =
    case scope of {
      Scope queue metadata _ failure _ _ _ _ ->
        do {
          active <- readIntArray metadata 1;
          if (active == 0)
          then unit
          else do {
                 status <- asyncStep queue;
                 if (status == 0)
                 then drain scope
                 else if (status == 1)
                      then do {
                             waited <- asyncWait queue (0 - 1);
                             if (waited == 0)
                             then drain scope
                             else do {
                                    asyncResolveCompletion failure
                                      (runtimeError 9
                                         "scope has unfinished fibers but no runnable work");
                                    afterFailure <- asyncStep queue;
                                    if (afterFailure == 0) then drain scope else unit
                                  }
                           }
                      else do {
                             asyncResolveCompletion failure
                               (runtimeError status "scheduler step failed");
                             unit
                           }
               }
        }
    };
  hasCleanup :: AsyncError -> AsyncError -> Bool;
  hasCleanup error wanted =
    case error of {
      CleanupFailed primary cleanup ->
        (((P.errorCode cleanup == P.errorCode wanted) &&
          eqString (P.errorMessage cleanup) (P.errorMessage wanted)) ||
         hasCleanup primary wanted);
      _ -> False
    };
  withCleanup :: forall a b. Completion AsyncError -> Outcome a -> (Outcome a -> IO b) -> IO b;
  withCleanup cleanup outcome complete =
    asyncReadCompletion cleanup
      (\error ->
         complete
           (Failed
              (case outcome of {
                 Failed primary ->
                   if hasCleanup primary error then primary else CleanupFailed primary error;
                 Cancelled (CancelReason code message) ->
                   CleanupFailed
                     (AsyncError 122 ("task cancelled (" ++ (showInt code ++ ("): " ++ message))))
                     error;
                 Succeeded _ -> error
               })))
      (complete outcome);
  closeNested :: forall a. Context ->
                           Scope ->
                           Completion (Fiber a) ->
                           Completion (List AsyncSubscription) -> (Outcome a -> IO Unit) -> IO Unit;
  closeNested parent scope rootFiber subscriptions callback =
    case scope of {
      Scope _ metadata _ failure scopeStop _ _ (Limits _ _ _ _ cleanup _) ->
        do {
          let {
            complete = \outcome -> withCleanup cleanup outcome callback
          };
          asyncReadCompletion subscriptions dropSubscriptions unit;
          writeIntArray metadata 2 1;
          external <- stopped parent;
          case external of {
            Just outcome -> complete (stopAs outcome);
            Nothing ->
              asyncReadCompletion failure (\error -> complete (Failed error))
                (asyncReadCompletion scopeStop (\reason -> complete (Cancelled reason))
                   (asyncReadCompletion rootFiber
                      (\fiber ->
                         case fiber of {
                           Fiber _ _ result _ ->
                             asyncReadCompletion result complete
                               (complete (Failed (runtimeError 9 "nested root never completed")))
                         })
                      (complete (Failed (runtimeError 9 "nested root was not started")))))
          }
        }
    };
  -- A nested group has its own failure, cancellation, live count and wait graph.
  -- It shares the coordinator queue, retained-cell budget and process budget.
  -- Its caller stays suspended until all group fibers have finished. A failure
  -- can therefore be captured around withScope before escaping to the parent.
  withScope :: forall a. Task a -> Task a;
  withScope task = scoped Nothing task;
  -- A total monotonic deadline covers the body and all its child joins. Expiry
  -- fails the group and waits for cancellation/cleanup before returning.
  withTimeout :: forall a. Int -> Task a -> Task a;
  withTimeout milliseconds task =
    if ((milliseconds < 0) || (milliseconds > 4294967295))
    then taskFail (runtimeError 1 "invalid task deadline")
    else scoped (Just milliseconds) task;
  scoped :: forall a. Maybe Int -> Task a -> Task a;
  scoped timeout task =
    Task
      (\parent complete ->
         case parent of {
           Context (Scope queue _ _ outerFailure outerStop _ processes (Limits maximum jobs pending shared _ _)) _ parentStop ->
             asyncNewCompletion queue
               (\cleanup ->
                  asyncNewCompletion queue
                    (\failure ->
                       asyncNewCompletion queue
                         (\scopeStop ->
                            asyncNewCompletion queue
                              (\drained ->
                                 asyncNewCompletion queue
                                   (\rootFiber ->
                                      asyncNewCompletion queue
                                        (\subscriptions ->
                                           do {
                                             metadata <- newIntArray 4 0;
                                             edges <- newIntTable;
                                             let {
                                               scope =
                                                 Scope queue metadata edges failure scopeStop
                                                   drained
                                                   processes
                                                   (Limits maximum jobs pending shared cleanup
                                                      (Just parent))
                                             };
                                             failed <-
                                               asyncSubscribeCompletion outerFailure
                                                 (\error ->
                                                    ioBind (asyncResolveCompletion failure error)
                                                      (\_ -> unit));
                                             stoppedScope <-
                                               asyncSubscribeCompletion outerStop
                                                 (\reason ->
                                                    ioBind (asyncResolveCompletion scopeStop reason)
                                                      (\_ -> unit));
                                             stoppedParent <-
                                               asyncSubscribeCompletion parentStop
                                                 (\reason ->
                                                    ioBind (asyncResolveCompletion scopeStop reason)
                                                      (\_ -> unit));
                                             finished <-
                                               asyncSubscribeCompletion drained
                                                 (\_ ->
                                                    closeNested parent scope rootFiber subscriptions
                                                      complete);
                                             timers <-
                                               case timeout of {
                                                 Nothing -> ioReturn Nil;
                                                 Just milliseconds ->
                                                   do {
                                                     timer <-
                                                       asyncDelay queue milliseconds
                                                         (ioBind
                                                            (asyncResolveCompletion failure
                                                               (AsyncError 124
                                                                  "task deadline expired"))
                                                            (\_ -> unit));
                                                     ioReturn (Cons timer Nil)
                                                   }
                                               };
                                             let {
                                               registered =
                                                 Cons failed
                                                   (Cons stoppedScope
                                                      (Cons stoppedParent (Cons finished timers)))
                                             };
                                             asyncResolveCompletion subscriptions registered;
                                             status <- subscriptionsOK registered;
                                             if (status == 0)
                                             then launch scope task
                                                    (\launched ->
                                                       case launched of {
                                                         Right fiber ->
                                                           ioBind
                                                             (asyncResolveCompletion rootFiber
                                                                fiber)
                                                             (\_ -> unit);
                                                         Left error ->
                                                           do {
                                                             dropSubscriptions registered;
                                                             writeIntArray metadata 2 1;
                                                             complete (Failed error)
                                                           }
                                                       })
                                             else do {
                                                    dropSubscriptions registered;
                                                    writeIntArray metadata 2 1;
                                                    complete
                                                      (Failed
                                                         (runtimeError status
                                                            "cannot reserve nested scope callbacks"))
                                                  }
                                           })
                                        (complete (Failed limitError)))
                                   (complete (Failed limitError)))
                              (complete (Failed limitError)))
                         (complete (Failed limitError)))
                    (complete (Failed limitError)))
               (complete (Failed limitError))
         });
  runScope :: forall a. Options -> P.ProcessScope -> Task a -> IO (Outcome a);
  runScope (Options cells callbacks maximum (P.ScopeOptions jobs pending _)) processes task =
    do {
      queue <- asyncScopeNew cells callbacks;
      shared <- newIntArray 3 0;
      result <-
        asyncNewCompletion queue
          (\cleanup ->
             asyncNewCompletion queue
               (\failure ->
                  asyncNewCompletion queue
                    (\scopeStop ->
                       asyncNewCompletion queue
                         (\drained ->
                            do {
                              metadata <- newIntArray 4 0;
                              edges <- newIntTable;
                              let {
                                scope =
                                  Scope queue metadata edges failure scopeStop drained processes
                                    (Limits maximum jobs pending shared cleanup Nothing)
                              };
                              asyncNewCompletion queue
                                (\rootResult ->
                                   do {
                                     launch scope task
                                       (\launched ->
                                          case launched of {
                                            Left error ->
                                              ioBind
                                                (asyncResolveCompletion rootResult (Failed error))
                                                (\_ -> unit);
                                            Right (Fiber _ _ root _) ->
                                              do {
                                                drain scope;
                                                asyncReadCompletion failure
                                                  (\error ->
                                                     ioBind
                                                       (asyncResolveCompletion rootResult
                                                          (Failed error))
                                                       (\_ -> unit))
                                                  (asyncReadCompletion scopeStop
                                                     (\reason ->
                                                        ioBind
                                                          (asyncResolveCompletion rootResult
                                                             (Cancelled reason))
                                                          (\_ -> unit))
                                                     (asyncReadCompletion root
                                                        (\outcome ->
                                                           ioBind
                                                             (asyncResolveCompletion rootResult
                                                                outcome)
                                                             (\_ -> unit))
                                                        (ioBind
                                                           (asyncResolveCompletion rootResult
                                                              (Failed
                                                                 (runtimeError 9
                                                                    "root never completed")))
                                                           (\_ -> unit))))
                                              }
                                          });
                                     writeIntArray metadata 2 1;
                                     asyncReadCompletion rootResult
                                       (\outcome -> withCleanup cleanup outcome ioReturn)
                                       (ioReturn (Failed (runtimeError 9 "root result missing")))
                                   })
                                (ioReturn (Failed limitError))
                            })
                         (ioReturn (Failed limitError)))
                    (ioReturn (Failed limitError)))
               (ioReturn (Failed limitError)))
          (ioReturn (Failed limitError));
      asyncScopeClose queue;
      ioReturn result
    };
  run :: forall a. Options -> Task a -> IO (Outcome a);
  run options task =
    case options of {
      Options cells callbacks maximum processOptions ->
        if ((cells < 7) || ((callbacks < 4) || (maximum < 1)))
        then ioReturn (Failed (runtimeError 1 "invalid task scope limits"))
        else do {
               scoped <-
                 P.withProcessScope processOptions
                   (\processes ->
                      do {
                        outcome <- runScope options processes task;
                        case outcome of {
                          Succeeded value -> ioReturn (Right (Succeeded value));
                          Failed error -> ioReturn (Left error);
                          Cancelled reason ->
                            do {
                              cleanup <- P.cancelScope processes 0;
                              ioReturn
                                (case cleanup of {
                                   Left error -> Left error;
                                   Right _ -> Right (Cancelled reason)
                                 })
                            }
                        }
                      });
               ioReturn
                 (case scoped of {
                    Left error -> Failed error;
                    Right outcome -> outcome
                  })
             }
    }
}
