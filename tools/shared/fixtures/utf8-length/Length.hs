-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  emit text = do { printInt (stringUtf8Length text); printInt (stringLength text) };
  runCase :: (Int -> IO String) -> IO ();
  runCase getArg = do {
    mode <- getArg 0;
    if eqString mode "argument" then emit (panic "text-first")
    else if eqString mode "invalid" then emit (stringFromCode 55296)
    else if eqString mode "unused" then printInt (if True then 42 else stringUtf8Length (panic "unused"))
    else if eqString mode "scalar" then do { value <- getArg 1; emit (stringFromCode (readInt value)) }
    else do {
      value <- getArg 1;
      let { text = S.concatStrings (S.replicate (readInt value) ("aα中😀" ++ stringFromCode 0)) };
      if eqString mode "slice" then do {
        start <- getArg 2; count <- getArg 3;
        emit (stringSlice text (readInt start) (readInt count))
      } else emit text
    }
  };
  batchArgument :: [] String -> Int -> IO String;
  batchArgument args index =
    if ltInt index 0 then panic "UTF8 batch getArg out of range"
    else case args of {
      [] -> panic "UTF8 batch getArg out of range";
      (:) value rest ->
        if eqInt index 0 then ioReturn value
        else batchArgument rest (subInt index 1)
    };
  batchLoop :: [] ((,) Int ([] String)) -> IO ();
  batchLoop entries = case entries of {
    [] -> ioReturn ();
    (:) ((,) index args) rest -> do {
      printInt 812340001;
      printInt index;
      runCase (batchArgument args);
      printInt 812340002;
      batchLoop rest
    }
  };
  batchCases :: [] ((,) Int ([] String));
  batchCases =
    [(,) 0 ["count", "0"]
    , (,) 1 ["count", "1"]
    , (,) 2 ["count", "2"]
    , (,) 3 ["count", "63"]
    , (,) 4 ["count", "64"]
    , (,) 5 ["count", "65"]
    , (,) 10 ["scalar", "0"]
    , (,) 11 ["scalar", "1"]
    , (,) 12 ["scalar", "127"]
    , (,) 13 ["scalar", "128"]
    , (,) 14 ["scalar", "2047"]
    , (,) 15 ["scalar", "2048"]
    , (,) 16 ["scalar", "55295"]
    , (,) 17 ["scalar", "57344"]
    , (,) 18 ["scalar", "65535"]
    , (,) 19 ["scalar", "65536"]
    , (,) 20 ["scalar", "1114111"]
    , (,) 21 ["slice", "65", "0", "0"]
    , (,) 22 ["slice", "65", "0", "5"]
    , (,) 23 ["slice", "65", "1", "3"]
    , (,) 24 ["slice", "65", "3", "7"]
    , (,) 25 ["slice", "65", "255", "1"]
    , (,) 26 ["slice", "65", "256", "3"]
    , (,) 27 ["slice", "65", "324", "1"]
    , (,) 28 ["slice", "65", "325", "0"]
    ];
  main :: IO ();
  main = do {
    mode <- getArg 0;
    if eqString mode "batch-forward" then batchLoop batchCases
    else if eqString mode "batch-reverse" then batchLoop (S.reverse batchCases)
    else runCase getArg
  }
}
