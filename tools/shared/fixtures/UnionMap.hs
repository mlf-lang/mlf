-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  inputs mode count = let { asc = range 0 count } in
    if mode == 0 then (,) asc (range (count / 2) (count + count / 2))
    else if mode == 1 then (,) asc (range (count + 1) (count * 2 + 1))
    else if mode == 2 then (,) (map (\n -> n * 2) asc) (map (\n -> n * 2 + 1) asc)
    else if mode == 3 then (,) (concatMap (\k -> [k,k,k]) (reverse asc)) asc
    else if mode == 4 then (,) [0,count / 2,count + 1] asc
    else (,) asc [0,count / 2,count + 1];
  ordinary tree = if not (M.valid compareInt tree) then panic "invalid union map" else
    foldl (\acc ((,) key value) -> (acc * 131 + key) * 131 + value)
      (M.size tree) (M.toList tree);
  taggedOrder ((,) a _) ((,) b _) = compareInt a b;
  tagged tree = if not (M.valid taggedOrder tree) then panic "invalid tagged union map" else
    foldl (\acc ((,) ((,) key ordinal) value) ->
      ((acc * 131 + key) * 131 + ordinal) * 131 + value)
      (M.size tree) (M.toList tree);
  run mode count = case inputs mode count of { (,) left right -> let {
    entries offset keys = zip keys (range offset (offset + length keys - 1));
    a = entries 0 left; b = entries 10000 right;
    first = M.fromList compareInt a; second = M.fromList compareInt b;
    combine x y = x * 131 + y * 17;
    tag xs = map (\((,) key value) -> (,) ((,) key value) value) xs;
    representatives = M.unionWith taggedOrder combine
      (M.fromList taggedOrder (tag a)) (M.fromList taggedOrder (tag b))
  } in showInt (ordinary (M.union compareInt first second)) ++ "," ++
    showInt (ordinary (M.unionWith compareInt combine first second)) ++ "," ++
    showInt (tagged representatives) };
  lazy = let {
    first = M.fromList compareInt [(,) 1 17,(,) 2 (panic "unselected")];
    second = M.singleton 1 (panic "right-value");
    deferred = M.unionWith compareInt (\a b -> panic "deferred-combine") first first
  } in showInt (M.get compareInt 1 (M.union compareInt first second)) ++ "," ++
    showInt (M.get compareInt 1 (M.unionWith compareInt (\a b -> b)
      (M.singleton 1 (panic "left-value")) (M.singleton 1 23))) ++ "," ++
    showInt (M.size deferred);
  main = do {
    mode <- getArg 0;
    if eqString mode "lazy" then putStrLn lazy
    else if eqString mode "left" then seq
      (M.union compareInt (panic "left-tree") (panic "right-tree")) (putStrLn "unreachable")
    else if eqString mode "right" then seq
      (M.union compareInt M.empty (panic "right-tree")) (putStrLn "unreachable")
    else do { count <- getArg 1; putStrLn (run (readInt mode) (readInt count)) }
  }
}
