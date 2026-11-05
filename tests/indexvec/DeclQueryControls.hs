{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Monad (unless)
import System.Environment (getArgs)
import System.Directory (createDirectoryIfMissing)
import Data.String (fromString)
import qualified MLF.Host.IO as Host
import qualified Bootstrap.Crate as Crate
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.BuiltinPreludeContext as Builtin
import qualified MLF.BuiltinPreludeData as Literal
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.QueryGraph as G
import qualified Bootstrap.Resolved as R
import qualified Bootstrap.OpenFragment as Open
import qualified Bootstrap.Separate as Separate
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.CrateGraph as CG
import qualified Bootstrap.Dependency as D
import qualified Bootstrap.InferenceUnit as Inference
import qualified Bootstrap.Surface as Surface
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
    [directory] -> queryDefinitions directory >> mixedLowered (directory ++ "/mixed") >> legacyCrate (directory ++ "/crate") >> mutualOrder (directory ++ "/mutual") >> typedInputs
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
        (pooled,standalone,_) <- Q.compileParsedSourceGroups config (fromString (directory ++ "/parsed"))
          [external] (M.fromDistinctAscList [("externalX",False)]) plan >>= expect
        check "standalone parsed query tracks the same edited group" (Q.inferredCount standalone == Q.inferredCount report)
        (ordinary,nonPooled,_) <- Q.compileSourceGroups config (fromString (directory ++ "/ordinary"))
          [external] (M.fromDistinctAscList [("externalX",False)]) plan >>= expect
        check "non-pooled query retains resolved import identity and reuse"
          (Q.inferredCount nonPooled == Q.inferredCount standalone &&
           map (Pretty.prettyTerm . Separate.objectTerm) ordinary ==
           map (Pretty.prettyTerm . Separate.objectTerm) pooled)
        pure (lookup "consumer" owners, Q.inferredCount report)
  (initial,inferred) <- program False True "u"
  check "external Global selects the external slot" (initial == Just ["externalX"] && inferred == 2)
  (shifted,misses) <- program True True "v"
  check "slot drift and local alpha edit preserve prepared inputs" (shifted == initial && misses == 0)
  (changed,dirty) <- program True False "v"
  check "rebinding the same spelling changes the selected slot" (changed == Just ["packageX"] && dirty == 1)
  putStrLn "PASS resolved Global, external/local collision, slot drift, local alpha and red/green reuse"

mixedLowered directory = do
  let int = T.SCon "Int" []
      fn = T.SArrow int int
      table = D.symbols [("method",True),("f",False)]
      f = V.fromInt 1
      method = V.fromInt 0
      source = D.BoundValues table [D.Bound f (T.Just (T.SAnnotation [] fn))
                 (R.Lam "x" T.Nothing (R.App (R.Global method) (R.Local "x")))]
      layout = T.SClassDecl "C" [("a",T.Star)] [] [("method",T.SArrow (T.STVar "a") int)]
      inst = ("dictC",T.SInstanceDecl [] [] "C" [int]
               [("method",T.SLam "x" T.Nothing (T.SApp (T.SGlobal f "f") (T.SVar "x")))])
      visible = IS.fromList [0]
      scopes = D.indexedScopes table [(f,visible)]
  (route,lowered) <- expect (Source.prepareResolvedSourcePlan source M.empty [] [layout] [inst] [inst] scopes [visible])
  check "source/dictionary cycle selects lowered fallback" (case route of T.Nothing -> True; _ -> False)
  declarations <- expect lowered
  generated <- case Inference.loweredDeclarationTable declarations of
    T.Nothing -> fail "lost generating table"
    T.Just value -> pure value
  dictionary <- case D.generatedNameId generated "dictC" of
    T.Just i -> pure i
    _ -> fail "generated dictionary is absent"
  groups <- expect (Surface.indexedMemberGroups (Inference.loweredIdValues declarations))
  let isMixed group = all (\i -> V.toInt i `elem` map V.toInt group) [f,dictionary]
  check "typed SCC includes source and generated dictionary" (any isMixed groups)
  let run = CG.compileLoweredIn declarations False "mixed" "stable-mixed-config" (fromString directory) [] >>= expect
  cold <- run
  let (fragments,coldReport,_,session) = CG.checkedResult cold
  check "fragment owners retain the generating slots" (any (\(_,_,owners) -> isMixed owners) fragments)
  check "all cold groups inferred" (Q.inferredCount coldReport == fromIntegral (length groups))
  _ <- G.publish session >>= expect
  warm <- run
  let (_,warmReport,_,_) = CG.checkedResult warm
  check "mixed fallback reuses the checked group" (Q.inferredCount warmReport == 0 && Q.reusedCount warmReport == Q.inferredCount coldReport)
  let runFile = Q.compileLoweredFileGroups "mixed" (fromString (directory ++ "/file"))
                  [] declarations >>= expect
  (coldUnits,fileCold) <- runFile
  (warmUnits,fileWarm) <- runFile
  check "file-owned lowered compilation retains the mixed SCC and actual checked cache"
    (Q.inferredCount fileCold == Q.inferredCount coldReport &&
     Q.inferenceUnits fileCold == Q.inferenceUnits coldReport &&
     Q.inferredCount fileWarm == 0 && Q.reusedCount fileWarm == Q.inferredCount fileCold &&
     map Separate.encodeObject coldUnits == map Separate.encodeObject warmUnits)
  let named = Inference.LoweredDeclarations [] [("named", T.Nothing, T.SIntLit 3)] M.empty
  (namedUnits,namedCold) <- Q.compileLoweredFileGroups "named" (fromString (directory ++ "/named")) [] named >>= expect
  (namedLegacy,namedWarm) <- Q.compileGroups "named" (fromString (directory ++ "/named")) [] []
    (Inference.loweredValues named) >>= expect
  check "named adapter retains the existing cache namespace and bytes"
    (Q.inferredCount namedCold == 1 && Q.reusedCount namedWarm == 1 &&
     map Separate.encodeObject namedUnits == map Separate.encodeObject namedLegacy)
  putStrLn "PASS actual source/dictionary fallback, generation slots, lowered SCC membership and warm reuse"

-- Exercise the compatibility crate API with precisely the checked lowering
-- produced for this module. This selects its whole-lowered route explicitly.
legacyCrate directory = do
  source <- expect (Parser.parseModule "A.emlf" "module A (first, second) where\nfirst x = x\nsecond x = first x\n")
  let Builtin.RawPrelude _ _ builtin _ _ _ _ _ _ _ _ _ = Literal.builtin
      interfaces = [("builtin.mlfci", builtin)]
      spec = Crate.CrateSpec "file-api" "" T.NoImplicitPrelude [("A","A.emlf")] ["builtin.mlfci"] (fromString directory) ""
  prepared <- expect (Crate.prepareCrate spec interfaces [source])
  let lowered = case prepared of
        Crate.PreparedCrate resolution datatypes classes instances checked entry reach _ ->
          Crate.PreparedCrate resolution datatypes classes instances checked entry reach T.Nothing
      run share = Crate.compilePreparedWithEncoding share (\object _ report -> (Artifact.encodeObject object,report)) spec interfaces lowered >>= expect
  (cold,c) <- run False
  (warm,w) <- run True
  check "both public encoding modes retain checked lowered declarations"
    (cold == warm && Q.inferredCount c == 2 && Q.reusedCount w == 2)
  putStrLn "PASS public crate compatibility API, indexed lowering and named cache reuse"

typedInputs = do
  let symbols = D.symbolsWithKeys [("n","firstN",False),("n","secondN",False),("f","f",False)]
      scope = Source.declarationScope symbols [V.fromInt 2] [] []
      owner = V.fromInt 2
      a = V.fromInt 0
      b = V.fromInt 1
      ty = T.XCon "Int" []
      contract = Source.SourceContract ty [] False
      allContracts = [(a,contract),(b,contract)]
      group body = let m = [("f", T.Nothing, body)] in Source.PreparedGroup m m [] M.empty [] T.Nothing []
      input body = do
        empty <- expect (Source.installContracts scope M.empty)
        (s,g) <- expect (Source.slotPrepared (Source.publishContracts empty allContracts) [owner] (group body))
        G.hashValue (CG.preparedValue s g) >>= expect
      val ids given hint = T.SLam given T.Nothing (T.SDeclScope [owner] (T.SLet "tmp" (T.SGlobal a hint)
        (T.SWantedRefs "D" ((T.GivenEvidence,T.LexicalRef given) : [(T.InstanceEvidence,T.DeclRef i hint) | i <- ids]))))
      pat i = T.SCase (T.SStringLit "a") [T.SAlternative
        (T.SIndexedStringPattern (T.ScalarString "a") (T.DeclRef i "same") (T.DeclRef b "same")) (T.SIntLit 1)]
  original <- input (val [a,b] "x" "wrong hint")
  renamed <- input (val [a,b] "y" "different hint")
  reordered <- input (val [b,a] "x" "wrong hint")
  left <- input (pat a)
  right <- input (pat b)
  check "typed globals and lexical givens alpha-normalize; candidate order remains observable"
    (original == renamed && original /= reordered && left /= right)
  let captured i = T.SDeclScope [i] (T.SLet "copied" (T.SIntLit 2) (T.SGlobal i "copied"))
  innerA <- input (captured a)
  innerB <- input (captured b)
  check "scoped declarations remain in the Prepared table, including copied local helpers" (innerA /= innerB)
  putStrLn "PASS typed hint independence, ordered candidate roles, implicit pattern references and lexical givens"

mutualOrder directory = do
  let int = T.SCon "Int" []; bool = T.SCon "Bool" []
      z = V.fromInt 0; a = V.fromInt 1
      symbols = D.symbols [("z", False), ("a", False)]
      app2 op x y = R.App (R.App (R.Prim op) x) y
      rhsZ = R.Lam "x" T.Nothing (app2 T.PEqInt (R.App (R.Global a) (R.BoolLit False)) (R.Local "x"))
      rhsA = R.Lam "b" T.Nothing (R.App (app2 T.PIfThenElse (R.App (R.Global z) (R.IntLit 0)) (R.IntLit 1)) (R.IntLit 0))
      rows = D.BoundValues symbols [D.Bound z (T.Just (T.SAnnotation [] (T.SArrow int bool))) rhsZ,
                                    D.Bound a (T.Just (T.SAnnotation [] (T.SArrow bool int))) rhsA]
      scopes = D.indexedScopes symbols [(z, IS.empty),(a,IS.empty)]
  (maybePlan,_) <- expect (Source.prepareResolvedSourcePlan rows M.empty [] [] [] [] scopes [])
  plan <- case maybePlan of T.Just p -> pure p; _ -> fail "recursion lost source ownership"
  state <- CG.compile False "mutualOrder" "fixed" (fromString directory) [] M.empty plan >>= expect
  let (fragments,report,checked,session) = CG.checkedResult state
  _ <- G.publish session >>= expect
  check "mutual group retained" (Q.inferredCount report == 1 && length fragments == 1)
  ct <- expect (Source.checkedBinding checked a)
  cz <- expect (Source.checkedBinding checked z)
  let asArrow x y ty = case ty of T.XArrow (T.XCon n []) (T.XCon m []) -> n==x && m==y; _ -> False
  check "source-ordered z,a binders retain distinct types under lexical SCC order a,z"
    (asArrow "Bool" "Int" (Source.contractType ct) && asArrow "Int" "Bool" (Source.contractType cz))
  (_,legacy,_) <- Q.compileParsedSourceGroups "mutualOrder" (fromString (directory ++ "/parsed")) [] M.empty plan >>= expect
  check "standalone source-ordered group" (Q.inferredCount legacy == 1)
  putStrLn "PASS source-order member slots with distinct recursive calling conventions"
