-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Entry.TupleList where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Test.Runner as Runner;
  import qualified Tests.TupleList as TupleList;
  import qualified Tests.TupleListLegacy as Legacy;
  -- Preserve the frozen default until executed equivalence is established.
  -- Opt-in routes share the new leaf registry, never run both implementations.
  main :: IO Unit;
  main =
    do {
      count <- getArgCount;
      args <- Runner.arguments 0 count;
      let {
        matchValueShared1 = args
      } in
      case matchValueShared1 of {
        Cons matchValueShared2 matchValueShared3 ->
          if MLF.Primitive.eqString matchValueShared2 "--framework"
          then let {
                 rest = matchValueShared3
               } in
               finish rest
          else if MLF.Primitive.eqString matchValueShared2 "--framework-list"
               then let {
                      rest = matchValueShared3
                    } in
                    finish (Cons "--list" rest)
               else Legacy.main;
        _ -> Legacy.main
      }
    };
  finish :: List String -> IO Unit;
  finish args =
    do {
      code <- Runner.run args TupleList.cases;
      if (code == 0) then ioReturn Unit else exitWith code
    }
}
