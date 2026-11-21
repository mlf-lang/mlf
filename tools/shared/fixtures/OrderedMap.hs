-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  keys mode count = let { asc = range 0 count } in
    if mode == 0 then asc else if mode == 1 then reverse asc
    else if mode == 2 then concatMap (\k -> [k,k,k]) asc
    else if mode == 3 then append asc ((:) (0 - 1) asc)
    else if mode == 4 then map (\k -> (k * 79) % (count + 1)) asc
    else if mode == 5 then concatMap (\k -> [k * 4 + 3,k * 4 + 2,k * 4 + 1,k * 4]) asc
    else if mode == 6 then concatMap (\k -> [k * 4,k * 4 + 1,k * 4 + 2,k * 4 + 3]) (reverse asc)
    else concatMap (\k -> [k,0,k,1,k,2]) asc;
  summarize tree = if not (M.valid compareInt tree) then panic "invalid map" else
    foldl (\acc ((,) k v) -> (acc * 131 + k) * 131 + v) (M.size tree) (M.toList tree);
  taggedOrder a b = compareInt (fst a) (fst b);
  summarizeTagged tree = if not (M.valid taggedOrder tree) then panic "invalid tagged map" else
    foldl (\acc ((,) ((,) k ordinal) v) -> ((acc * 131 + k) * 131 + ordinal) * 131 + v)
      (M.size tree) (M.toList tree);
  run mode count = let {
    ks = keys mode count;
    entries = zip ks (range 0 (length ks - 1));
    ordinary = M.fromList compareInt entries;
    combined = M.fromListWith compareInt (\new old -> new * 131 + old) entries;
    tagged = M.fromList taggedOrder (map (\((,) key ordinal) -> (,) ((,) key ordinal) ordinal) entries)
  } in showInt (summarize ordinary) ++ "," ++ showInt (summarize combined) ++ "," ++ showInt (summarizeTagged tagged);
  lazyValues = let {
    ordinary = M.fromList compareInt [((,) (0 - 1) (panic "unselected")),((,) 1 17)];
    duplicate = M.fromListWith compareInt (\new old -> new)
      [((,) 1 (panic "replaced")),((,) 1 23)];
    deferred = M.fromListWith compareInt (\new old -> panic "deferred-combine") [((,) 1 0),((,) 1 0)]
  } in showInt (M.get compareInt 1 ordinary) ++ "," ++ showInt (M.get compareInt 1 duplicate)
    ++ "," ++ showInt (M.size deferred);
  lazyRuns = let {
    overwritten = M.fromList compareInt [(,) 0 (panic "old"),(,) 2 0,(,) 1 0,(,) 0 17];
    ignored = M.fromList compareInt [(,) 3 (panic "ignored"),(,) 2 23,(,) 1 0]
  } in showInt (M.get compareInt 0 overwritten) ++ "," ++ showInt (M.get compareInt 2 ignored);
  main = do {
    mode <- getArg 0;
    if eqString mode "lazy" then putStrLn lazyValues
    else if eqString mode "lazy-runs" then putStrLn lazyRuns
    else if eqString mode "key" then seq
      (M.fromList compareInt ((:) ((,) (panic "first-key") 0) (panic "list-tail")))
      (putStrLn "unreachable")
    else if eqString mode "compare" then seq
      (M.fromList (\a b -> panic "comparison") [((,) 0 0),((,) (panic "second-key") 0)])
      (putStrLn "unreachable")
    else do { count <- getArg 1; putStrLn (run (readInt mode) (readInt count)) }
  }
}
