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
        (T.SProgram [] (T.SDeclScope [V.fromInt 2,V.fromInt 3] (T.SLetRec (map parameter names) body)), M.empty)
      slots selected = map (V.toInt . fst) (Parameters.entries selected)
      expect label ids result = case result of
        T.Left e -> error (label ++ ": " ++ H.unpack e)
        T.Right (_, selected) -> unless (slots selected == ids) (error label)
  expect "unused RHS / wanted candidate / ABI order" [2,3] $
    select ["a","z"] (T.SLet "unused" (T.SWantedRefs "Dict" [(T.InstanceEvidence,T.DeclRef (V.fromInt 3) "a")]) (T.SGlobal (V.fromInt 2) "a"))
  expect "lexically shadowed import" [] $
    select ["a","z"] (T.SLam "a" T.Nothing (T.SVar "a"))
  expect "same spelling, local declaration and lexical binder" [2] $
    select ["a","z"] (T.SLam "a" T.Nothing
      (T.SApp (T.SGlobal (V.fromInt 0) "a") (T.SGlobal (V.fromInt 2) "a")))
  expect "implicit overloaded pattern operations" [2,3] $
    select ["a","z"] (T.SCase (T.SStringLit "") [T.SAlternative
      (T.SIndexedStringPattern (T.ScalarString "") (T.DeclRef (V.fromInt 2) "a") (T.DeclRef (V.fromInt 3) "a"))
      (T.SIntLit 0)])
  let mixed = T.SLam "a" T.Nothing (T.SWantedRefs "Dict" [(T.GivenEvidence,T.LexicalRef "a"),
        (T.SuperclassEvidence,T.LexicalRef "b"), (T.InstanceEvidence,T.DeclRef (V.fromInt 2) "a")])
  unless (map H.unpack (D.expressionNamedReads mixed) == ["b"] &&
          map V.toInt (D.expressionGlobalIds mixed) == [2]) (error "mixed reference domains")
  let zero = Parameters.namedImports M.empty
  expect "empty signature inventory" [] $
    Parameters.select zero (T.SProgram [] (T.SIntLit 0), M.empty)
  case select ["z","a"] (T.SVar "a") of
    T.Left _ -> pure ()
    _ -> error "out-of-order import inventory accepted"
  putStrLn "consumer import ID controls passed"
