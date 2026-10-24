-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Tests.CallStackProgram where {
  import MLF.Primitive;
  data Probe a = Pure a | Failed CallStack;
  data Optional a = Missing | Present a;
  instance Functor Probe where {
    fmap f (Pure x) = Pure (f x);
    fmap f (Failed s) = Failed s
  };
  instance Applicative Probe where {
    pure = Pure;
    (<*>) (Pure f) (Pure x) = Pure (f x);
    (<*>) (Failed s) x = Failed s;
    (<*>) x (Failed s) = Failed s
  };
  instance Monad Probe where {
    (>>=) (Pure x) f = f x;
    (>>=) (Failed s) f = Failed s
  };
  instance MonadFail Probe where {
    fail message = Failed callStack
  };
  leaf :: HasCallStack => Int -> CallStack;
  leaf x = callStack;
  unsigned x = leaf x;
  signed :: Int -> CallStack;
  signed x = leaf x;
  forward :: HasCallStack => Int -> CallStack;
  forward x = leaf x;
  custom :: HasCallStack => Probe Int;
  custom = fail "custom failure";
  patterned :: HasCallStack => Probe Int;
  patterned = do { Present x <- pure Missing; pure x };
  displayProbe :: Probe Int -> IO Unit;
  displayProbe (Pure x) = printInt x;
  displayProbe (Failed s) = putStrLn (textFromChars (prettyCallStack s));
  main :: IO Unit;
  main = do {
    putStrLn "UNSIGNED";
    putStrLn (textFromChars (prettyCallStack (unsigned 0)));
    putStrLn "SIGNED";
    putStrLn (textFromChars (prettyCallStack (signed 0)));
    putStrLn "FORWARD";
    putStrLn (textFromChars (prettyCallStack (forward 0)));
    putStrLn "CUSTOM";
    displayProbe custom;
    putStrLn "PATTERNED";
    displayProbe patterned;
    putStrLn "ANNOTATED";
    displayProbe ((fail :: HasCallStack => [Char] -> Probe Int) "annotated failure");
    putStrLn "ANNOTATED_UNSIGNED";
    displayProbe (let { unsignedFail = (fail :: HasCallStack => [Char] -> Probe Int) }
                 in unsignedFail "annotated unsigned failure");
    putStrLn "SHADOW";
    printInt (let { mlfCallStack = 42 } in mlfCallStack);
    putStrLn "DONE"
  }
}
