{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Monad (unless)
import qualified Bootstrap.Dependency as D
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.Map as M
import qualified Bootstrap.SourceInference as Source
import qualified Bootstrap.Types as T

expect (T.Right x) = pure x
expect (T.Left _) = fail "unexpected declaration error"
check message result = unless result (fail message)

main = do
  let base = D.symbols [("inactive", False), ("x", False), ("y", False), ("x", False)]
      scope = Source.declarationScope base [V.fromInt 1, V.fromInt 2] [] ["external"]
      contract = Source.SourceContract (T.XCon "Int" []) ["C"] True
      external = M.fromDistinctAscList [("external",contract)]
      members body = [("y", T.Nothing, body)]
      prepare body = Source.PreparedGroup (members body) (members body) [] M.empty [] T.Nothing []
      lookupId name = expect (Source.requireDecl scope name)
  x <- lookupId "x"
  y <- lookupId "y"
  ext <- lookupId "external"
  check "active declaration must shadow the inactive imported spelling" (V.toInt x == 1)
  checked <- expect (Source.installContracts scope external)
  case Source.slotPrepared checked [y] (prepare (T.SVar "x")) of
    T.Left _ -> pure ()
    _ -> fail "read of unfinished predecessor was admitted"
  case Source.slotPrepared checked [y] (prepare (T.SLam "x" T.Nothing (T.SVar "x"))) of
    T.Right (slots,_) -> check "local x has no predecessor" (null (Source.parameterIds slots))
    _ -> fail "local binder incorrectly read x"
  let next = Source.publishContracts checked [(x,contract)]
      body = T.SApp (T.SVar "x") (T.SVar "external")
  (slots, prepared) <- expect (Source.slotPrepared next [y] (prepare body))
  check "name-sorted ABI order with ID-selected contracts" (map V.toInt (Source.parameterIds slots) == map V.toInt [ext,x])
  check "protection follows checked slot" (all snd (Source.groupParameterProtection prepared))
  xc <- expect (Source.checkedBinding next x)
  check "the slot retains predicate and protection" (Source.contractClasses xc == ["C"] && Source.contractProtected xc)
  putStrLn "PASS declaration readers, sparse publication, local shadowing, ABI order and contract fields"
