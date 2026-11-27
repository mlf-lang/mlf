{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Monad (forM_, unless)
import System.Environment (getArgs)
import System.Directory (createDirectoryIfMissing, makeAbsolute)
import Data.List (isInfixOf)
import Data.String (fromString)
import qualified MLF.Host.Base as HostText
import qualified MLF.Host.IO as Host
import qualified MLF.Primitive as P
import qualified Bootstrap.Crate as Crate
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.CrateSession as Session
import qualified Bootstrap.BuiltinPreludeContext as Builtin
import qualified MLF.BuiltinPreludeData as Literal
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.QueryGraph as G
import qualified Bootstrap.Resolved as R
import qualified Bootstrap.OpenFragment as Open
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.Separate as Separate
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Type as XT
import qualified Bootstrap.Runtime as Runtime
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
    [directory] -> do
      queryDefinitions directory
      mixedLowered (directory ++ "/mixed")
      legacyCrate (directory ++ "/crate")
      mutualOrder (directory ++ "/mutual")
      typedInputs
      scopeTransitions (directory ++ "/scope")
      expectedReads
      directFinishReads
      inferredDictionaryPrefix (directory ++ "/dictionary-prefix")
      groundRecursiveScope (directory ++ "/ground-scc")
      recursiveStringArms (directory ++ "/string-arms")
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

inferredDictionaryPrefix directory = do
  root <- makeAbsolute directory
  createDirectoryIfMissing True root
  let path name = root ++ "/" ++ name
      source = path "Main.hs"
      spec = fromString (path "spec")
      output = fromString (path "checked")
      metadata = fromString (path "checked.mlfci")
      identity = "inferred-dictionary-prefix"
  writeFile source (unlines
    [ "-- mlf:syntax shared-haskell-v1"
    , "{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,"
    , "             KindSignatures, FlexibleContexts, FlexibleInstances,"
    , "             MultiParamTypeClasses, OverloadedStrings #-}"
    , "module Main (main) where {"
    , "import MLF.Primitive;"
    , "data Box = Box Int;"
    , "data Other = Other Int;"
    , "class Pass a where { pass :: a -> a };"
    , "instance Pass Box where { pass (Box x) = Box (addInt x 1) };"
    , "instance Pass Other where { pass (Other x) = Other (addInt x 3) };"
    , "twice x = pass (pass x);"
    , "both x y = (twice x, twice y);"
    , "bounded f x0 = " ++ concat ["case pass (Box x" ++ show i ++ ") of { Box x" ++ show (i+1) ++ " -> " | i <- [0..7::Int]]
        ++ "f x8" ++ replicate 8 '}' ++ ";"
    , "main = case both (Box 10) (Other 10) of { (Box x, Other y) -> bounded (addInt x) y }"
    , "}"
    ])
  Host.v_writeFile spec (Separate.pack ["MLF-CRATE-1", identity, "Main", "true",
    Separate.pack [Separate.pack ["Main", fromString source]], Separate.pack [],
    fromString (path "cache"), fromString (path "builtin")])
  let verify = do
        _ <- Session.compileSpecFileWithVerification True T.Nothing spec output >>= expect
        iface <- Artifact.readInterface metadata >>= expect
        let name = Artifact.definitionName identity (Modules.Entity "Main" "twice" Modules.Value)
        case lookup name (Artifact.crateBindings iface) of
          Just (T.XForall a T.XBot (T.XArrow (T.XCon _ [T.XVar b]) (T.XArrow (T.XVar c) (T.XVar d)))) ->
            check "one dictionary for the operand type" (all (XT.equalTyVar a) [b,c,d])
          _ -> fail "twice did not export a single dictionary argument"
        let boundedName = Artifact.definitionName identity (Modules.Entity "Main" "bounded" Modules.Value)
        case lookup boundedName (Artifact.crateBindings iface) of
          Just (T.XForall a (T.XForall _ T.XBot _) (T.XArrow (T.XCon _ [_]) (T.XVar b))) ->
            check "one bounded result remains after the dictionary" (XT.equalTyVar a b)
          _ -> fail "bounded retained repeated dictionaries or lost the callback result scheme"
        term <- Artifact.linkFile metadata >>= expect
        (datatypes, _) <- expect (Runtime.prepare False term)
        value <- expect (Runtime.integer (Runtime.evaluate datatypes (Runtime.REnv M.empty) (X.erase term)))
        check "separate instantiations use their own dictionaries" (value == 36)
  verify
  verify
  putStrLn "PASS repeated inferred dictionaries, separate types and cache reuse"

groundRecursiveScope directory = do
  root <- makeAbsolute directory
  createDirectoryIfMissing True root
  let path name = root ++ "/" ++ name
      header = ["-- mlf:syntax shared-haskell-v1"
        , "{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,"
        , "             KindSignatures, FlexibleContexts, FlexibleInstances,"
        , "             MultiParamTypeClasses, OverloadedStrings #-}"
        ]
      writeModule name exports declarations = writeFile (path (name ++ ".hs")) (unlines
        (header ++ ["module " ++ name ++ " (" ++ exports ++ ") where {", "import MLF.Primitive;"]
          ++ declarations ++ ["}"]))
      writeScanner imports = writeModule "Scanner" "reader" (imports ++
        [ "import Ground;"
        , "collect n = if eqInt n 0 then shade (Mark 10) else resume (subInt n 1);"
        , "resume n = if eqInt n 0 then shade (Mark 20) else collect (subInt n 1);"
        , "reader :: Int -> Int;"
        , "reader n = collect n;"
        ])
      moduleSpec name = Separate.pack [fromString name, fromString (path (name ++ ".hs"))]
      identity = "ground-scc-fixture"
      spec = fromString (path "spec")
      output = fromString (path "checked")
      metadata = fromString (path "checked.mlfci")
      compile = Session.compileSpecFileWithVerification True T.Nothing spec output
  writeModule "Ground" "Shade(..), Mark(..)"
    ["class Shade a where { shade :: a -> Int };", "data Mark = Mark Int;"]
  writeModule "Instance" ""
    ["import Ground;", "instance Shade Mark where { shade (Mark n) = addInt n 11 };"]
  writeModule "Main" "main"
    ["import Scanner;", "import Instance ();", "main = addInt (reader 2) (reader 3);"]
  Host.v_writeFile spec (Separate.pack ["MLF-CRATE-1", identity, "Main", "true",
    Separate.pack (map moduleSpec ["Ground", "Instance", "Main", "Scanner"]), Separate.pack [],
    fromString (path "cache"), fromString (path "builtin")])
  writeScanner ["import Instance ();"]
  _ <- compile >>= expect
  iface <- Artifact.readInterface metadata >>= expect
  let int = T.XCon "Int" []
      plainFunction name = case lookup (Artifact.definitionName identity (Modules.Entity "Scanner" name Modules.Value))
          (Artifact.crateBindings iface) of
        Just ty -> XT.alphaEq ty (T.XArrow int int)
        Nothing -> False
  check "the ground dictionary prefix is removed from both recursive members"
    (all plainFunction ["collect", "resume"])
  term <- Artifact.linkFile metadata >>= expect
  (datatypes, _) <- expect (Runtime.prepare False term)
  value <- expect (Runtime.integer (Runtime.evaluate datatypes (Runtime.REnv M.empty) (X.erase term)))
  check "both recursive members use the expected ground dictionary" (value == 52)
  -- Keep the importer and the previous cache entries while removing the
  -- defining module's access to the instance.
  writeScanner []
  hidden <- compile
  case hidden of
    T.Left message -> check "the hidden instance must fail at evidence resolution"
      ("no instance or given constraint for Ground.Shade Ground.Mark" `isInfixOf` HostText.unpack message)
    T.Right _ -> fail "the importer supplied a dictionary outside the recursive group's defining scope"
  writeModule "Ground" "Shade(..), Mark(..)"
    ["class Shade a where { shade :: a -> Int };", "data Mark a = Mark a;"]
  writeModule "Instance" ""
    ["import Ground;", "instance Shade (Mark a) where { shade (Mark ignored) = 23 };"]
  writeScanner ["import Instance ();"]
  _ <- compile >>= expect
  _ <- compile >>= expect
  specialized <- Artifact.readInterface metadata >>= expect
  forM_ ["collect", "resume"] $ \name -> do
    let key = Artifact.definitionName identity (Modules.Entity "Scanner" name Modules.Value)
    check "type-instantiated ground evidence stays discharged on warm reuse"
      (maybe False (XT.alphaEq (T.XArrow int int)) (lookup key (Artifact.crateBindings specialized)))
  specializedTerm <- Artifact.linkFile metadata >>= expect
  (types, _) <- expect (Runtime.prepare False specializedTerm)
  result <- expect (Runtime.integer (Runtime.evaluate types (Runtime.REnv M.empty) (X.erase specializedTerm)))
  check "polymorphic instance selected at its definition site" (result == 46)
  writeModule "Ground" "Shade(..), Mark(..)"
    ["class Shade a where { shade :: a -> Int };", "data Mark = Mark Int;"]
  writeModule "Instance" ""
    ["import Ground;", "instance Shade Mark where { shade (Mark n) = addInt n 11 };"]
  writeModule "Scanner" "reader"
    [ "import Instance ();", "import Ground;"
    , "collect direction fuel x = if eqInt fuel 0 then shade (Mark (if direction then x else subInt 0 x)) else resume (subInt fuel 1) x;"
    , "positive = collect True;", "negative = collect False;"
    , "resume fuel x = if eqInt fuel 0 then negative 0 x else positive (subInt fuel 1) x;"
    , "reader :: Int -> Int;", "reader x = addInt (positive 0 x) (negative 0 (mulInt 2 x));"
    ]
  _ <- compile >>= expect
  _ <- compile >>= expect
  aliases <- Artifact.readInterface metadata >>= expect
  forM_ ["positive", "negative"] $ \name -> do
    let key = Artifact.definitionName identity (Modules.Entity "Scanner" name Modules.Value)
    check "a partial peer application exports only the remaining value arguments"
      (maybe False (XT.alphaEq (T.XArrow int (T.XArrow int int))) (lookup key (Artifact.crateBindings aliases)))
  aliasTerm <- Artifact.linkFile metadata >>= expect
  (aliasTypes, _) <- expect (Runtime.prepare False aliasTerm)
  aliasValue <- expect (Runtime.integer (Runtime.evaluate aliasTypes (Runtime.REnv M.empty) (X.erase aliasTerm)))
  -- reader x = (x + 11) + (11 - 2*x), main adds reader 2 and reader 3.
  check "recursive partial aliases retain distinct literal operands on warm reuse" (aliasValue == 39)
  putStrLn "PASS ground recursive dictionary prefix and definition-site scope"

recursiveStringArms directory = do
  root <- makeAbsolute directory
  createDirectoryIfMissing True root
  let path name = root ++ "/" ++ name
      source = path "Main.hs"
      spec = fromString (path "spec")
      output = fromString (path "checked")
      arms = [show key ++ " -> consume \"" ++ replicate (key + 1) 'x' ++ "\";" | key <- [0..7]]
  writeFile source (unlines
    [ "-- mlf:syntax shared-haskell-v1"
    , "{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,"
    , "             KindSignatures, FlexibleContexts, FlexibleInstances,"
    , "             MultiParamTypeClasses, OverloadedStrings #-}"
    , "module Main (main) where {"
    , "import MLF.Primitive;"
    , "data Stamp = Stamp Int;"
    , "stampLength [] = 0;"
    , "stampLength (_ : tail) = addInt 1 (stampLength tail);"
    , "instance IsString Stamp where { fromString xs = Stamp (stampLength xs) };"
    , "selectRank consume key fuel = if ltInt fuel 1 then case key of {"
    , unlines arms
    , "  _ -> (\\_ -> 99) } else selectRank consume key (subInt fuel 1);"
    , "useStamp :: Stamp -> (forall t. t -> t) -> Int;"
    , "useStamp (Stamp n) callback = if callback True then callback (addInt n 10) else 98;"
    , "main = addInt (selectRank useStamp 7 1 (\\x -> x)) (selectRank useStamp 20 1 (panic \"unused callback\"));"
    , "}"
    ])
  Host.v_writeFile spec (Separate.pack ["MLF-CRATE-1", "recursive-string-arms", "Main", "true",
    Separate.pack [Separate.pack ["Main", fromString source]], Separate.pack [],
    fromString (path "cache"), fromString (path "builtin")])
  _ <- Session.compileSpecFileWithVerification True T.Nothing spec output >>= expect
  term <- Artifact.linkFile (fromString (path "checked.mlfci")) >>= expect
  (datatypes, _) <- expect (Runtime.prepare False term)
  value <- expect (Runtime.integer (Runtime.evaluate datatypes (Runtime.REnv M.empty) (X.erase term)))
  check "string arms retain their conversion, rank-two result and lazy fallback" (value == 117)
  putStrLn "PASS recursive string arms with higher-rank result and lazy fallback"

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


-- Keep another empty group live while f acquires and loses a candidate.
-- Both transitions must recompute f; identical following runs must reuse it.
scopeTransitions directory = do
  let names = ["candidate", "stillEmpty", "f"]
      symbols = D.symbols [(n,False) | n <- names]
      available = V.fromInt 0; emptyOwner = V.fromInt 1; owner = V.fromInt 2
      scope = Source.declarationScope symbols [emptyOwner,owner] [] ["candidate"]
      int = T.XCon "Int" []; sint = T.SCon "Int" []
      contract = Source.SourceContract int [] False
      group name candidates =
        let member = (name,T.Just (T.SAnnotation [] (T.SArrow sint sint)),
                           T.SLam "x" T.Nothing (T.SVar "x"))
        in Source.PreparedGroup [member] [member] [] M.empty [(name,[],False)]
             (T.Just (Source.RootAuthority name [] False candidates [])) []
  initial <- expect (Source.installContracts scope (M.fromDistinctAscList [("candidate",contract)]))
  inventory <- expect (Q.prepareData [])
  let run present = do
        let candidates = if present then [(T.InstanceEvidence,"candidate",int)] else []
            steps = [([emptyOwner],\_ -> T.Right (group "stillEmpty" [])),
                     ([owner],\_ -> T.Right (group "f" candidates))]
        state <- CG.start True "scope-transition" "fixed" (fromString directory) "source"
                   inventory [] initial steps >>= expect
        let (_,report,_,session) = CG.result state
        _ <- G.publish session >>= expect
        let active = G.currentNodes session
        check "shared empty input and scope remain distinct authorities"
          (case (M.lookup P.compareString CG.emptyInventoryKey active,M.lookup P.compareString CG.emptyScopeKey active) of
            (T.Just _,T.Just _) -> True; _ -> False)
        check "only nonempty group owns a per-group scope"
          (case M.lookup P.compareString (CG.groupKey CG.ScopeQuery (Source.GroupSlots scope [owner] [] [])) active of T.Just _ -> present; _ -> not present)
        pure (Q.inferredCount report,Q.reusedCount report)
  results <- mapM run [False,False,True,True,False,False]
  check "candidate addition/deletion invalidation and stable warm reuse"
    (results == [(2,0),(0,2),(1,1),(0,2),(1,1),(0,2)])
  putStrLn "PASS shared empty scope, candidate addition/deletion and repeated warm reuse"

-- Old shared dependencies can remain green while the provider changes its
-- current authority or dependencies. Check exact current read order and hash.
expectedReads = do
  let h = fromString (replicate 64 'a'); h2 = fromString (replicate 64 'b')
      shared = G.QueryNode CG.emptyScopeKey h [] T.Nothing
      private = G.QueryNode (G.key "Scope" "private") h [] T.Nothing
      input = G.QueryNode (G.inputKey (G.key "Prepared" "f")) h [] T.Nothing
      wanted = G.key "InferScc" "f"
      oldReads = [G.edge input,G.edge shared]
      old = G.QueryNode wanted h oldReads (T.Just h)
      current = M.fromList P.compareString [(G.nodeKey n,n) | n <- [input,shared,private]]
      session = G.Session G.MemoryStore "cfg" "" (M.fromList P.compareString [(wanted,old)]) current M.empty
      hit result = case fst result of T.Just _ -> True; _ -> False
  check "old dependencies are green in transition counterexample" (hit (G.validate wanted session))
  check "same current dependency list reuses" (hit (G.validateExpected wanted oldReads session))
  check "route change invalidates even when old shared authority remains live"
    (not (hit (G.validateExpected wanted [G.edge input,G.edge private] session)))
  check "read reordering, repetition, omission and changed hash invalidate"
    (all (not . hit . (\reads -> G.validateExpected wanted reads session))
      [reverse oldReads,oldReads ++ [G.edge shared],[],[(G.nodeKey input,h2),G.edge shared]])
  putStrLn "PASS current authority/read-list guard independent of prepared input changes"


directFinishReads = do
  let h = fromString (replicate 64 'a'); h2 = fromString (replicate 64 'b')
      symbols = D.symbols [("f",False),("other",False)]
      owner = V.fromInt 0; other = V.fromInt 1
      scope = Source.declarationScope symbols [owner,other] [] []
      slots = Source.GroupSlots scope [owner] [] []
      key = CG.bindingKey scope owner
      fin = CG.groupKey CG.FinishQuery slots
      raw = G.QueryNode (CG.groupKey CG.InferQuery slots) h [] (T.Just h)
      source = G.QueryNode (G.inputKey (CG.groupKey CG.PreparedQuery slots)) h [] T.Nothing
      empty = G.QueryNode CG.emptyScopeKey h [] T.Nothing
      reads = [G.edge raw,G.edge source,G.edge empty]
      contract flag = Source.SourceContract (T.XArrow (T.XCon "Int" []) (T.XCon "Int" [])) [] flag
      session = G.Session G.MemoryStore "cfg" "" M.empty (M.fromList P.compareString [(G.nodeKey n,n) | n <- [raw,source,empty]]) M.empty
      run digest evidence delta = CG.recordCheckedFinish T.Nothing slots "g" digest Source.KeepRawBody raw [] [] evidence delta reads session >>= expect
      binding state = case M.lookup P.compareString key (G.currentNodes (fst state)) of
        T.Just row -> pure row; _ -> fail "missing direct Binding"
      hasFinish state = case M.lookup P.compareString fin (G.currentNodes (fst state)) of T.Just _ -> True; _ -> False
  plain <- run h [] [(owner,contract False)]
  protected <- run h [] [(owner,contract True)]
  a <- binding plain; b <- binding protected
  check "direct binding retains complete ordered finalization dependencies"
    (not (hasFinish plain) && G.nodeReads a == reads)
  check "metadata-only contract changes stay visible under the same raw hash"
    (G.nodeHash a /= G.nodeHash b && G.nodeReads b == reads)
  changedBody <- run h2 [] [(owner,contract False)]
  evidence <- run h [G.edge empty] [(owner,contract False)]
  multiple <- run h [] [(owner,contract False),(other,contract False)]
  check "different content, evidence and multi-output groups keep FinishScc"
    (all hasFinish [changedBody,evidence,multiple])
  putStrLn "PASS direct singleton finalization reads, contract metadata and fallback boundaries"
