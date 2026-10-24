-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Test.Assert where {
  import MLF.Primitive hiding (fail);
  import Bootstrap.Types;
  import qualified Test.Expectation as E;
  import qualified Test.Outcome as O;
  -- Ordinary assertion failures are values. IO exits, panics and crashes are not
  -- caught; callers that need that isolation must supervise a separate process.
  data Failure = Failure String (Maybe (Pair String String));
  data Test a = Test (IO (Either Failure a));
  run :: forall a. Test a -> IO (Either Failure a);
  run (Test action) = action;
  succeed :: forall a. a -> Test a;
  succeed value = Test (ioReturn (Right value));
  andThen :: forall a b. Test a -> (a -> Test b) -> Test b;
  andThen action next =
    Test
      (do {
         result <- run action;
         case result of {
           Left failure -> ioReturn (Left failure);
           Right value -> run (next value)
         }
       });
  instance Functor Test where {
    fmap function action = andThen action (\value -> succeed (function value))
  };
  instance Applicative Test where {
    pure = succeed;
    (<*>) action argument =
      andThen action (\function -> andThen argument (\value -> succeed (function value)))
  };
  instance Monad Test where {
    (>>=) = andThen
  };
  fail :: forall a. String -> Test a;
  fail message = Test (ioReturn (Left (Failure message Nothing)));
  assert :: Bool -> String -> Test Unit;
  assert condition message = if condition then succeed Unit else fail message;
  equal :: forall a. (a -> a -> Bool) -> (a -> String) -> String -> a -> a -> Test Unit;
  equal same display message expected actual =
    if same expected actual
    then succeed Unit
    else Test (ioReturn (Left (Failure message (Just (Pair (display expected) (display actual))))));
  liftIO :: forall a. IO a -> Test a;
  liftIO action =
    Test
      (do {
         value <- action;
         ioReturn (Right value)
       });
  right :: forall e a. (e -> String) -> Either e a -> Test a;
  right display value =
    case value of {
      Left error -> fail (display error);
      Right result -> succeed result
    };
  message :: Failure -> String;
  message (Failure text _) = text;
  details :: Failure -> Maybe (Pair String String);
  details (Failure _ values) = values;
  describe :: Failure -> String;
  describe (Failure text values) =
    case values of {
      Nothing -> text;
      Just (Pair expected actual) -> (text ++ ("; expected " ++ (expected ++ (", got " ++ actual))))
    };
  -- Compatibility boundary for a legacy IO suite. Keep termination outside the
  -- assertion API so the common runner can report failures and keep running.
  orExit :: forall a. Test a -> IO a;
  orExit action =
    do {
      result <- run action;
      case result of {
        Right value -> ioReturn value;
        Left failure ->
          do {
            putErr ("TEST FAILURE: " ++ (describe failure ++ "\n"));
            exitWith 1
          }
      }
    };
  -- Typed observations retain phase-specific rejection semantics. Timeouts and
  -- cancellation are failures of the outer case, never generic expected failures.
  expect :: E.Expectation -> E.Observation -> Test O.Outcome;
  expect expected observation =
    let {
      outcome = E.match expected observation
    } in
    if O.successful outcome
    then succeed outcome
    else fail (O.status outcome ++ (": " ++ O.message outcome))
}
