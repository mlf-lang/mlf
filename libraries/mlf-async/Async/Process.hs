-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Async.Process (ProcessScope, ProcessHandle, AsyncError(..), ScopeOptions(..), ProcessSpec(..), Environment(..), ProcessOutcome(..), ProcessEvent(..), Wait(..), defaultOptions, command, withProcessScope, submit, poll, waitNext, awaitProcess, awaitWithin, cancel, requestCancel, cancelScope, errorCode, errorMessage, exitCode, cleanupError) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Async.Process.Internal as I;
  -- Opaque, monomorphic identities. Scope/generation checks are native, not
  -- compile-time non-escape: a handle returned from its scope is invalid.
  data ProcessScope = ProcessScope String;
  data ProcessHandle = ProcessHandle String String String;
  data AsyncError = AsyncError Int String | CleanupFailed AsyncError AsyncError;
  data ScopeOptions = ScopeOptions Int Int Int;
  -- ReplaceEnvironment takes NAME=VALUE fields. InheritEnvironment uses
  -- the coordinator's environment at actual launch. No implicit shell parsing.
  data Environment = InheritEnvironment | ReplaceEnvironment (List String);
  -- executable, arguments (excluding argv[0]), cwd, stdin, stdout, stderr,
  -- environment, running timeout milliseconds, total timeout milliseconds.
  -- Empty cwd/stdin inherits. stdout/stderr paths are mandatory for command.
  -- Zero timeout disables it. No bounded-capture mode is exposed in v1.
  data ProcessSpec =
    ProcessSpec String (List String) String String String String Environment Int Int;
  data ProcessOutcome = Exited Int Int | LaunchFailed Int Int | Cancelled Int Int | TimedOut Int;
  data ProcessEvent = ProcessEvent ProcessHandle ProcessOutcome;
  data Wait = Forever | ForMilliseconds Int;
  defaultOptions :: ScopeOptions;
  defaultOptions = ScopeOptions 4 64 1024;
  command :: String -> List String -> String -> String -> ProcessSpec;
  command executable arguments stdoutFile stderrFile =
    ProcessSpec executable arguments "" "" stdoutFile stderrFile InheritEnvironment 0 0;
  errorCode :: AsyncError -> Int;
  errorCode error =
    case error of {
      AsyncError code _ -> code;
      CleanupFailed primary _ -> errorCode primary
    };
  errorMessage :: AsyncError -> String;
  errorMessage error =
    case error of {
      AsyncError _ message -> message;
      CleanupFailed primary cleanup ->
        (errorMessage primary ++ ("; cleanup: " ++ errorMessage cleanup))
    };
  exitCode :: ProcessOutcome -> Maybe Int;
  exitCode outcome =
    case outcome of {
      Exited code _ -> Just code;
      _ -> Nothing
    };
  cleanupError :: ProcessOutcome -> Int;
  cleanupError outcome =
    case outcome of {
      Exited _ cleanup -> cleanup;
      LaunchFailed _ cleanup -> cleanup;
      Cancelled _ cleanup -> cleanup;
      TimedOut cleanup -> cleanup
    };
  call :: List String -> IO (Either AsyncError (List String));
  call fields =
    ioBind (I.request fields)
      (\result ->
         ioReturn
           (case result of {
              Left (Pair code message) -> Left (AsyncError code message);
              Right values -> Right values
            }));
  invalid :: forall a. Either AsyncError a;
  invalid = Left (AsyncError 12 "invalid process supervisor response");
  unitResult :: Either AsyncError (List String) -> Either AsyncError Unit;
  unitResult result =
    case result of {
      Left error -> Left error;
      Right Nil -> Right Unit;
      _ -> invalid
    };
  close :: ProcessScope -> Bool -> IO (Either AsyncError Unit);
  close (ProcessScope scope) stop =
    ioBind (call (Cons "close" (Cons scope (Cons (if stop then "1" else "0") Nil))))
      (\result -> ioReturn (unitResult result));
  -- Normal return joins every child. An explicit Left cancels and joins; a
  -- native panic/exit invokes the runtime shutdown guard, and interpreter
  -- errors invoke the same guard. Forced OS termination uses native ownership.
  withProcessScope :: forall a. ScopeOptions ->
                                (ProcessScope -> IO (Either AsyncError a)) ->
                                IO (Either AsyncError a);
  withProcessScope (ScopeOptions jobs pending retained) body =
    do {
      created <-
        call
          (Cons "create"
             (Cons (showInt jobs) (Cons (showInt pending) (Cons (showInt retained) Nil))));
      case created of {
        Left error -> ioReturn (Left error);
        Right (Cons identity Nil) ->
          do {
            let {
              scope = ProcessScope identity
            };
            result <- body scope;
            cleaned <-
              close scope
                (case result of {
                   Left _ -> True;
                   Right _ -> False
                 });
            ioReturn
              (case cleaned of {
                 Right _ -> result;
                 Left cleanup ->
                   case result of {
                     Left primary -> Left (CleanupFailed primary cleanup);
                     Right _ -> Left cleanup
                   }
               })
          };
        _ -> ioReturn invalid
      }
    };
  handleFields :: ProcessHandle -> List String;
  handleFields (ProcessHandle scope generation slot) = Cons scope (Cons generation (Cons slot Nil));
  readHandle :: List String -> Either AsyncError ProcessHandle;
  readHandle fields =
    case fields of {
      Cons scope (Cons generation (Cons slot Nil)) -> Right (ProcessHandle scope generation slot);
      _ -> invalid
    };
  submit :: ProcessScope -> ProcessSpec -> IO (Either AsyncError ProcessHandle);
  submit (ProcessScope scope) (ProcessSpec executable arguments cwd input output errors environment running total) =
    if ((stringLength output == 0) || (stringLength errors == 0))
    then ioReturn (Left (AsyncError 1 "stdout and stderr log paths are required"))
    else do {
           let {
             env =
               case environment of {
                 InheritEnvironment -> Nil;
                 ReplaceEnvironment values -> values
               }
           };
           let {
             envMode =
               case environment of {
                 InheritEnvironment -> "0";
                 ReplaceEnvironment _ -> "1"
               }
           };
           let {
             argv = Cons executable arguments
           };
           let {
             fields =
               Cons "submit"
                 (Cons scope
                    (Cons executable
                       (Cons cwd
                          (Cons input
                             (Cons output
                                (Cons errors
                                   (Cons envMode
                                      (Cons (showInt running)
                                         (Cons (showInt total)
                                            (Cons (showInt (L.length argv))
                                               (L.append argv
                                                  (Cons (showInt (L.length env)) env))))))))))))
           };
           result <- call fields;
           ioReturn
             (case result of {
                Left error -> Left error;
                Right values -> readHandle values
              })
         };
  waitField :: Wait -> String;
  waitField wait =
    case wait of {
      Forever -> "-1";
      ForMilliseconds milliseconds -> if (milliseconds < 0) then "invalid" else showInt milliseconds
    };
  readOutcome :: List String -> Either AsyncError ProcessOutcome;
  readOutcome fields =
    case fields of {
      Cons kind (Cons status (Cons launch (Cons cleanup (Cons reason Nil)))) ->
        if eqString kind "0"
        then Right (Exited (readInt status) (readInt cleanup))
        else if eqString kind "1"
             then Right (LaunchFailed (readInt launch) (readInt cleanup))
             else if eqString kind "2"
                  then Right (Cancelled (readInt reason) (readInt cleanup))
                  else if eqString kind "3" then Right (TimedOut (readInt cleanup)) else invalid;
      _ -> invalid
    };
  readEvent :: List String -> Either AsyncError ProcessEvent;
  readEvent fields =
    case fields of {
      Cons scope (Cons generation (Cons slot values)) ->
        case readOutcome values of {
          Left error -> Left error;
          Right outcome -> Right (ProcessEvent (ProcessHandle scope generation slot) outcome)
        };
      _ -> invalid
    };
  poll :: ProcessScope -> IO (Either AsyncError (Maybe ProcessEvent));
  poll (ProcessScope scope) =
    do {
      result <- call (Cons "poll" (Cons scope Nil));
      ioReturn
        (case result of {
           Left (AsyncError code message) ->
             if ((code == 8) || ((code == 9) || (code == 10)))
             then Right Nothing
             else Left (AsyncError code message);
           Left error -> Left error;
           Right values ->
             case readEvent values of {
               Left error -> Left error;
               Right event -> Right (Just event)
             }
         })
    };
  waitNext :: ProcessScope -> Wait -> IO (Either AsyncError ProcessEvent);
  waitNext (ProcessScope scope) wait =
    do {
      result <- call (Cons "wait" (Cons scope (Cons (waitField wait) Nil)));
      ioReturn
        (case result of {
           Left error -> Left error;
           Right values -> readEvent values
         })
    };
  -- Supplying the scope explicitly makes accidental cross-scope use rejectable.
  -- Repeated await retains the same outcome; it never resubmits or consumes an event.
  awaitWithin :: ProcessScope -> ProcessHandle -> Wait -> IO (Either AsyncError ProcessOutcome);
  awaitWithin (ProcessScope scope) handle wait =
    do {
      result <-
        call
          (Cons "await" (Cons scope (L.append (handleFields handle) (Cons (waitField wait) Nil))));
      ioReturn
        (case result of {
           Left error -> Left error;
           Right values -> readOutcome values
         })
    };
  awaitProcess :: ProcessScope -> ProcessHandle -> IO (Either AsyncError ProcessOutcome);
  awaitProcess scope handle = awaitWithin scope handle Forever;
  -- Cancellation reason codes are caller-defined integers from 0 to 2147483647.
  cancel :: ProcessScope -> ProcessHandle -> Int -> IO (Either AsyncError Unit);
  cancel (ProcessScope scope) handle reason =
    do {
      result <-
        call
          (Cons "cancel" (Cons scope (L.append (handleFields handle) (Cons (showInt reason) Nil))));
      ioReturn (unitResult result)
    };
  -- Accept cancellation without waiting for cleanup. The queued child will never
  -- launch; a running child keeps its permit until a later supervisor call reaps
  -- it. A task coordinator must continue servicing calls until terminal outcome.
  requestCancel :: ProcessScope -> ProcessHandle -> Int -> IO (Either AsyncError Unit);
  requestCancel (ProcessScope scope) handle reason =
    do {
      result <-
        call
          (Cons "request-cancel"
             (Cons scope (L.append (handleFields handle) (Cons (showInt reason) Nil))));
      ioReturn (unitResult result)
    };
  cancelScope :: ProcessScope -> Int -> IO (Either AsyncError Unit);
  cancelScope (ProcessScope scope) reason =
    do {
      result <- call (Cons "cancelScope" (Cons scope (Cons (showInt reason) Nil)));
      ioReturn (unitResult result)
    }
}
