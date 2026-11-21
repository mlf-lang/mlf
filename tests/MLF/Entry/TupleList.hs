-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Entry.TupleList where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Test.Runner as Runner;
  import qualified Tests.TupleList as TupleList;

  main :: IO ();
  main = do {
    count <- getArgCount;
    args <- Runner.arguments 0 count;
    selected <- case args of {
      [] -> do {
        path <- getEnv "MLF_TUPLE_LIST_REPORT";
        ioReturn (if eqString path "" then [] else (:) "--report" ((:) path []))
      };
      _ -> ioReturn (frameworkArgs args)
    };
    code <- Runner.run selected TupleList.cases;
    if code == 0 then
      case args of {
        [] -> putStrLn "Tuple/list focused checks passed.";
        _ -> ioReturn ()
      }
    else exitWith code
  };

  frameworkArgs :: [] String -> [] String;
  frameworkArgs args =
    case args of {
      (:) flag rest ->
        if eqString flag "--framework" then rest
        else if eqString flag "--framework-list" then (:) "--list" rest
        else args;
      [] -> []
    }
}
