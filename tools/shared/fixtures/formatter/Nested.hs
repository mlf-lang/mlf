-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- Exact safe-Ormolu source/AST controls, not inference or execution evidence.
module Formatter.Nested where {
  import MLF.Primitive;
  caseIfDo c = case if c then do { ioReturn 1; ioReturn 2 } else do { ioReturn 3; ioReturn 4 } of { x -> x };
  caseLetIfDo c = case let { x = if c then do { ioReturn 1; ioReturn 2 } else do { ioReturn 3; ioReturn 4 } } in x of { y -> y };
  nestedCaseIf c = case case if c then True else False of { True -> False; False -> True } of { True -> 1; False -> 2 };
  doLetCase = do { let { x = case True of { True -> 1; False -> 2 }; y = x }; ioReturn y };
  letDo = let { x = do { ioReturn 1; ioReturn 2 }; y = x } in y;
  doCase = do { case True of { True -> ioReturn 1; False -> ioReturn 2 }; ioReturn 3 };
  letCase = let { x = case True of { True -> 1; False -> 2 }; y = 3 } in x + y;
  caseLet = case True of { True -> let { x = 1; y = 2 } in x + y; False -> 0 };
  doLets = do { let { x = 1 }; let { y = 2 }; ioReturn (x + y) };
}
