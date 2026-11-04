-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import qualified Bootstrap.IndexVec as V;
  data Row = Row;
  table :: IO (V.Builder IOWorld Row Int);
  table = stToIO (V.filled 2 (panic "unused world slot"));
  manyBinds :: Int -> ST IOWorld Int;
  manyBinds n = if n == 0 then stReturn 41 else
    stBind (stReturn ()) (\_ -> manyBinds (n - 1));
  main :: IO ();
  main = do {
    mode <- getArg 0;
    cells <- table;
    let { first = V.fromInt 0; readFirst = stToIO (V.get cells first) };
    case mode of {
      "read-negative" -> stToIO (V.get cells (V.fromInt (0-1))) >>= printInt;
      "write-end" -> stToIO (V.set cells (V.fromInt 2) 1);
      "fixed-read-end" -> do { fixed <- stToIO (V.fixedFilled 1 0); stToIO (V.fixedGet fixed (V.fromInt 1)) >>= printInt };
      "fixed-write-end" -> do { fixed <- stToIO (V.fixedFilled 1 0); stToIO (V.fixedSet fixed (V.fromInt 1) 1) };
      _ -> do {
        let { unused = stToIO (panic "forced unexecuted world action") };
        seq unused (ioReturn ());
        stToIO (V.set cells first 7);
        before <- readFirst;
        snapshot <- stToIO (V.freeze cells);
        stToIO (V.set cells first 9);
        after <- readFirst;
        _ <- stToIO (stReturn (panic "ignored world result"));
        catchIOError (do {
          stToIO (V.set cells first 11);
          ioError (userError (textToChars "expected"))
        }) (\_ -> ioReturn ());
        caught <- readFirst;
        scope <- asyncScopeNew 2 2;
        _ <- asyncEnqueue scope (stToIO (V.set cells first 17));
        stepped <- asyncStep scope;
        final <- readFirst;
        asyncScopeClose scope;
        fixed <- stToIO (V.fixedFilled 1 23);
        let { fixedFirst = V.fromInt 0 };
        fixedSnapshot <- stToIO (V.fixedFreeze fixed);
        stToIO (V.fixedSet fixed fixedFirst 29);
        fixedNow <- stToIO (V.fixedGet fixed fixedFirst);
        if V.at fixedSnapshot fixedFirst == 23 && fixedNow == 29
          then ioReturn () else panic "fixed builder snapshot changed";
        let { allocate = stToIO (newSTArray 1 31) };
        firstArray <- allocate;
        secondArray <- allocate;
        stToIO (writeSTArray firstArray 0 37);
        untouched <- stToIO (readSTArray secondArray 0);
        deep <- stToIO (manyBinds 2048);
        if untouched == 31 && deep == 41
          then ioReturn () else panic "world action repetition changed";
        printInt before;
        printInt (V.at snapshot first);
        printInt after;
        printInt caught;
        printInt stepped;
        printInt final;
        printInt (V.at snapshot first)
      }
    }
  }
}
