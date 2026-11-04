{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Monad (unless)
import qualified Bootstrap.Dependency as D
import qualified Bootstrap.ImportParameters as Parameters
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.Map as M
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as H
import qualified MLF.Primitive as P

main :: IO ()
main = do
  -- The source and an inactive import print alike. The interface explicitly
  -- identifies slot 2. Generated support gets a new slot after all source IDs.
  let symbols = D.symbols [("a", False), ("other", False), ("a", False)]
      external = M.fromList P.compareString [("a", V.fromInt 2)]
      ty = T.XCon "Int" []
      sigs = M.fromList P.compareString [("z",ty), ("a",ty)]
      imports = Parameters.admit symbols external sigs
      parameter n = (n, T.InferRecursive, T.SIntLit 0)
      select names body = Parameters.select imports
        (T.SProgram [] (T.SLetRec (map parameter names) body), M.empty)
      slots selected = map (V.toInt . fst) (Parameters.entries selected)
      expect label ids result = case result of
        T.Left e -> error (label ++ ": " ++ H.unpack e)
        T.Right (_, selected) -> unless (slots selected == ids) (error label)
  expect "unused RHS / wanted candidate / ABI order" [2,3] $
    select ["a","z"] (T.SLet "unused" (T.SWanted "Dict" [(T.InstanceEvidence,"z")]) (T.SVar "a"))
  expect "lexically shadowed import" [] $
    select ["a","z"] (T.SLam "a" T.Nothing (T.SVar "a"))
  let zero = Parameters.namedImports M.empty
  expect "empty signature inventory" [] $
    Parameters.select zero (T.SProgram [] (T.SIntLit 0), M.empty)
  case select ["z","a"] (T.SVar "a") of
    T.Left _ -> pure ()
    _ -> error "out-of-order import inventory accepted"
  putStrLn "consumer import ID controls passed"
