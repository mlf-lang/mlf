-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Formatter.Layout (forward, nested, shadowing, alternatives, followed,
  doLet, doExpr, nestedCase, nestedDo, parens, listCase, nearestIf) where {
  import MLF.Primitive;
  forward = let { x = y; y = 3 } in x;
  nested = let { x = let { y = 3 } in y } in x;
  shadowing = let { x = 1 } in let { x = 2; y = x } in y;
  alternatives value = case value of { True -> 1; False -> 2 };
  followed = alternatives False;
  doLet = do { let { x = y; y = 3 }; ioReturn x };
  doExpr = do {
    let { x = y; y = 3 };
    ioReturn x
  };
  nestedCase = case case True of { True -> False; False -> True } of { True -> 1; False -> 2 };
  nestedDo = case do { ioReturn 1; ioReturn 2 } of { value -> value };
  parens f = f (case True of { True -> 1; False -> 2 }) 3;
  listCase = [case True of { True -> 1; False -> 2 }, 3];
  nearestIf x y = if x then do { ioReturn 1; if y then do { ioReturn 2; ioReturn 3 } else do { ioReturn 4; ioReturn 5 } } else do { ioReturn 6; ioReturn 7 };
}
