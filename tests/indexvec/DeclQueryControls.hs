{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Monad (unless)
import System.Environment (getArgs)
import System.Directory (createDirectoryIfMissing)
import Data.String (fromString)
import qualified MLF.Host.IO as Host
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.QueryGraph as G
import qualified Bootstrap.Resolved as R
import qualified Bootstrap.OpenFragment as Open
import qualified Bootstrap.Separate as Separate
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.CrateGraph as CG
import qualified Bootstrap.Dependency as D
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.Map as M
import qualified Bootstrap.SourceInference as Source
import qualified Bootstrap.Types as T

expect (T.Right x) = pure x
expect (T.Left message) = Host.v_putErr message >> fail "unexpected declaration error"
check message result = unless result (fail message)

main = do
  let base = D.symbolsWithKeys [("inactive","I/inactive",False), ("x","Local/x",False),
                                ("y","y",False), ("x","Import/x",False)]
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
      body = T.SApp (T.SVar "Local/x") (T.SVar "external")
  (slots, prepared) <- expect (Source.slotPrepared next [y] (prepare body))
  check "name-sorted ABI order with ID-selected contracts" (map V.toInt (Source.parameterIds slots) == map V.toInt [x,ext])
  check "protection follows checked slot" (all snd (Source.groupParameterProtection prepared))
  xc <- expect (Source.checkedBinding next x)
  check "the slot retains predicate and protection" (Source.contractClasses xc == ["C"] && Source.contractProtected xc)
  let pair = Source.GroupSlots scope [x,y] [] []
      reversePair = Source.GroupSlots scope [y,x] [] []
      singleton = Source.GroupSlots scope [x] [] []
      keys = [CG.groupKey CG.PreparedQuery pair, CG.groupKey CG.ScopeInventoryQuery pair,
              CG.groupKey CG.ScopeQuery pair, CG.groupKey CG.InferQuery pair, CG.groupKey CG.FinishQuery pair,
              CG.groupKey CG.FinishQuery reversePair, CG.groupKey CG.FinishQuery singleton]
  check "distinct query kinds, membership and order" (and [k /= j | (i,k) <- zip [0..] keys, j <- drop (i+1) keys])
  let goal = T.XCon "C" [T.XCon "Int" []]
      evidence group site ty = CG.evidenceKey (CG.EvidenceQuery group site ty)
      e = evidence pair 0 goal
  check "evidence keys include kind, membership, site and normalized goal"
    (all (/= e) [CG.groupKey CG.InferQuery pair, evidence singleton 0 goal,
                 evidence pair 1 goal, evidence pair 0 (T.XCon "C" [T.XCon "Bool" []])])
  putStrLn "PASS evidence request group, site and goal identities"
  putStrLn "PASS typed SCC query kinds, ordered members and split identities"
  args <- getArgs
  case args of
    [directory] -> queryDefinitions directory
    _ -> fail "expected a fresh cache directory"
  putStrLn "PASS declaration readers, sparse publication, local shadowing, ABI order and contract fields"

-- Run a resolver-issued Global through the source query driver. The external
-- and local are deliberately given the same display spelling. Reassign both
-- slots, rename a lambda binder, then switch the Global to the local entity.
queryDefinitions directory = do
  createDirectoryIfMissing True directory
  let config = "query-declaration-fixture"
      ambient = M.fromDistinctAscList [("externalX", T.SCon "Int" [])]
      external = Separate.UnitInterface "external" [] [] [] [] [] [("externalX",T.XCon "Int" [])] "metadata"
      program offset readExternal binder = do
        let entries = (if offset then [("other","otherUnused",False)] else []) ++
                [("x","externalX",False),("x","packageX",False),("consumer","consumer",False)]
            symbols = D.symbolsWithKeys entries
            i = V.fromInt (if offset then 1 else 0)
            local = V.fromInt (V.toInt i + 1)
            owner = V.fromInt (V.toInt local + 1)
            source = D.BoundValues symbols [D.Bound local T.Nothing (R.IntLit 4),
                        D.Bound owner T.Nothing (R.Lam binder T.Nothing (R.Global (if readExternal then i else local)))]
            visibility = D.indexedScopes symbols [(local,IS.empty),(owner,IS.empty)]
        (maybePlan,_) <- expect (Source.prepareResolvedSourcePlan source ambient [] [] [] [] visibility [])
        plan <- case maybePlan of T.Just p -> pure p; _ -> fail "resolved fixture unexpectedly lowered"
        -- Protect the import exactly as a checked interface would.
        result <- CG.compile False config "fixed-config-for-slot-reassignment" (fromString directory) [external] (M.fromDistinctAscList [("externalX",False)]) plan
        state <- expect result
        let (fragments,report,_,session) = CG.result state
        _ <- G.publish session >>= expect
        let owners = [(X.nameHint n, map (X.nameHint . fst) (Open.parameters fragment)) |
                      (_,fragment) <- fragments, (n,_) <- Open.bindings fragment]
        (_,standalone,_) <- Q.compileParsedSourceGroups config (fromString (directory ++ "/parsed"))
          [external] (M.fromDistinctAscList [("externalX",False)]) plan >>= expect
        check "standalone parsed query tracks the same edited group" (Q.inferredCount standalone == Q.inferredCount report)
        pure (lookup "consumer" owners, Q.inferredCount report)
  (initial,inferred) <- program False True "u"
  check "external Global selects the external slot" (initial == Just ["externalX"] && inferred == 2)
  (shifted,misses) <- program True True "v"
  check "slot drift and local alpha edit preserve prepared inputs" (shifted == initial && misses == 0)
  (changed,dirty) <- program True False "v"
  check "rebinding the same spelling changes the selected slot" (changed == Just ["packageX"] && dirty == 1)
  putStrLn "PASS resolved Global, external/local collision, slot drift, local alpha and red/green reuse"
