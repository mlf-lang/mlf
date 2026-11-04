-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Main where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.ST as ST;
  data Row = Row;
  example :: forall s. ST s ([] Int);
  example = stBind V.new (\table ->
    stBind (V.push table (panic "forced unused cell")) (\first ->
    stBind (V.push table 7) (\second ->
    stBind (V.freeze table) (\old ->
    stBind (V.get table second) (\before ->
    stBind (V.set table second 9) (\_ ->
    stBind (ST.map_ (\i -> V.push table i) (S.range 2 65)) (\_ ->
    stBind (V.set table first 3) (\_ ->
    stBind (V.freeze table) (\now ->
    stBind (V.size table) (\n ->
      stReturn [V.count old, V.at old second, before, n, V.toInt first, V.toInt second,
                V.at now first, V.at now second, V.at now (V.fromInt 64),
                S.foldlStrict addInt 0 (V.toList now)]))))))))));
  frozen :: V.IndexVec Row Int;
  frozen = V.fromList [2, 3];
  main :: IO ();
  main = do {
    mode <- getArg 0;
    case mode of {
      "read-negative" -> printInt (V.at frozen (V.fromInt (0-1)));
      "read-end" -> printInt (V.at frozen (V.fromInt 2));
      "huge" -> printInt (V.at frozen (V.fromInt 9223372036854775807));
      "get-end" -> printInt (runST (stBind V.new (\table -> V.get table (V.fromInt 0))));
      "set-end" -> printInt (runST (stBind V.new (\table ->
        stBind (V.set table (V.fromInt 0) 1) (\_ -> stReturn 0))));
      "snapshot-empty" -> printInt (runST (stBind (newSTArray 0 17) freezeSTArray) 0);
      "snapshot-negative" -> printInt (runST (stBind (newSTArray 1 17) freezeSTArray) (0-1));
      "capacity" -> printInt (runST (stBind (V.filled 1152921504606846976 0) V.size));
      _ -> do {
        let { empty = V.fromList [] };
        printInt (V.count empty);
        S.mapM_ printInt (runST example)
      }
    }
  }
}
