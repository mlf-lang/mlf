{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Monad (forM_, unless)
import Data.Bits (testBit)
import Data.List (nub, sort)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.Classes as Classes
import qualified Bootstrap.Compiler as Compiler
import qualified Bootstrap.Crate as Crate
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.CrateQuery as CQ
import qualified Bootstrap.Data as Data
import qualified Bootstrap.Dependency as D
import qualified Bootstrap.Desugar as Desugar
import qualified Bootstrap.Fresh as Fresh
import qualified Bootstrap.Layout as Layout
import qualified Bootstrap.Lexer as Lexer
import qualified Bootstrap.Resolved as R
import qualified Bootstrap.SourceEquality as Equality
import qualified Bootstrap.SourceInference as Source
import qualified Bootstrap.Surface as Surface
import qualified Bootstrap.QueryGraph as Q
import qualified Bootstrap.InferenceUnit as Inference
import qualified Bootstrap.OpenFragment as Open
import qualified Bootstrap.Separate as Separate
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.IntSet as I
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.Map as M
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.Types as T
import qualified Bootstrap.Set as S
import qualified MLF.Host.Base as H
import qualified Package.Json as J
import qualified Package.Manifest as P
import qualified Package.Scheduler as Jobs

check label expected actual =
  unless (expected == actual) (error (label ++ ": expected " ++ show expected ++ ", got " ++ show actual))

-- Establish membership independently by mutual reachability. Only the DFS
-- finish order is needed to select the historical order of disjoint SCCs.
reference entries = assemble (reverse finish) Set.empty []
  where
    byName = Map.fromList entries
    roots = Map.keys byName
    row n = sort (nub [d | d <- byName Map.! n, Map.member d byName])
    walk n state@(seen, done)
      | Set.member n seen = state
      | otherwise = let (seen', done') = foldl (flip walk) (Set.insert n seen, done) (row n)
                    in (seen', done' ++ [n])
    finish = snd (foldl (flip walk) (Set.empty, []) roots)
    reaches n = fst (walk n (Set.empty, []))
    assemble [] _ groups = groups
    assemble (n:ns) seen groups
      | Set.member n seen = assemble ns seen groups
      | otherwise = let members = [d | d <- roots, Set.member d (reaches n), Set.member n (reaches d)]
                    in assemble ns (seen <> Set.fromList members) (members:groups)

testGraph entries = do
  check "declaration groups/order" (reference entries)
    (map (map H.unpack) (D.components [(H.literal k, map H.literal deps) | (k, deps) <- entries]))
  let direct = Map.fromList entries
      walk seen [] = seen
      walk seen (x:xs) | Set.member x seen = walk seen xs
                       | otherwise = walk (Set.insert x seen) (Map.findWithDefault [] x direct ++ xs)
      expected = [(x, Set.toAscList (walk Set.empty [x])) | x <- Map.keys direct]
      host = M.fromList H.v_compareString [(H.literal k,S.fromList H.v_compareString (map H.literal vs))
                                          | (k,vs) <- entries]
  check "reach including external leaves" expected
    [(H.unpack k,map H.unpack (S.toList v)) | (k,v) <- M.toList (Modules.moduleReach host)]

allGraphs = [[(k, [v | (j,v) <- zip [0..] names, testBit mask (i*3+j)])
             | (i,k) <- zip [0..] names] | mask <- [0..511 :: Int]]
  where names = ["z","a","id900000000000"]

package name deps mods = P.Package (H.literal ("/packages/" ++ name ++ "/mlf-package.json"))
  (J.Object [("name",J.str (H.literal name)),("version",J.str "1.0.0"),
             ("dependencies",J.Object [(H.literal n,J.empty) | n <- deps])]) mods
modl owner name deps = P.Module name owner (H.v_concatString name ".hs") deps

packageChecks = do
  let leaf = package "leaf" [] [modl "leaf" "Leaf" []]
      left = package "left" ["leaf"] [modl "left" "Left" ["Leaf","Leaf"]]
      right = package "right" ["leaf"] [modl "right" "Right" ["Leaf"]]
      root = package "root" ["right","left"]
               [modl "root" "A" ["B","Right"], modl "root" "B" ["A","Left"]]
      pkgs = [leaf,left,right,root]
      mods = concatMap P.packageModules pkgs
      graph = P.buildPackageGraph "root" pkgs mods
      names = map (H.unpack . P.packageName)
  check "namespace cycle, diamond, repeated import" ["Leaf","Left","B","Right","A"]
    (map (H.unpack . P.moduleName) (P.modules graph))
  check "transitive scheduler closure" ["leaf","left","right","root"]
    (names (Jobs.neededPackages graph ["root","left","root"]))
  check "target subset" ["right"] (names (P.targetDependencies graph root (J.Object [("dependencies",J.stringArray ["right"])])))
  let jobs = Jobs.libraryJobs graph root J.empty
  check "stable scheduler job IDs" ["library-prelude-leaf","library-prelude-left","library-prelude-right","library-prelude-root"]
    (map (H.unpack . Jobs.jobId) jobs)
  check "scheduler dependency direction/order" [[],["library-prelude-leaf"],["library-prelude-leaf"],
    ["library-prelude-left","library-prelude-right"]] (map (map H.unpack . J.getStrings "dependencies") jobs)
  let encoded = Jobs.graphJson graph
  check "worker graph roundtrip" (H.unpack (J.render encoded)) (H.unpack (J.render (Jobs.graphJson (Jobs.graphFrom encoded))))
  let user = Modules.Entity "Zed" "value" Modules.Value
      extra = Modules.Entity "Prelude" "freezeSTArray" (Modules.Primitive T.PFreezeSTArray)
      nameOf entities = case Modules.resolvedName (Modules.freshNames [] (S.fromList Modules.compareEntity entities)) user of
        T.Right name -> H.unpack name
        T.Left err -> error (H.unpack err)
  check "appended primitive preserves existing generated name" (nameOf [user]) (nameOf [extra,user])
  let world = Modules.Entity "Prelude" "IOWorld" Modules.BuiltinType
      bridge = Modules.Entity "Prelude" "stToIO" (Modules.Primitive T.PSTToIO)
  check "IO world entities preserve existing generated name" (nameOf [user]) (nameOf [world,bridge,extra,user])
  let builtin ident modules = Artifact.CrateInterface ident [] modules [] [] [] [] [] [] [] "" "" []
      identityCheck iface = case Artifact.validateBuiltinOwnership iface of
        T.Left message -> Left (H.unpack message)
        T.Right _ -> Right ()
  check "current IO-world builtin identity admitted" (Right ())
    (identityCheck (builtin "mlf:builtin-shared-haskell-v1:15" ["MLF.Primitive","Prelude"]))
  check "preceding builtin identity rejected" (Left "stale or forged builtin crate identity")
    (identityCheck (builtin "mlf:builtin-shared-haskell-v1:12" ["MLF.Primitive","Prelude"]))
  check "incomplete current builtin rejected" (Left "builtin crate must own exactly Prelude and MLF.Primitive")
    (identityCheck (builtin "mlf:builtin-shared-haskell-v1:15" ["Prelude"]))
  let direct = M.fromList H.v_compareString
                 [(H.literal k,S.fromList H.v_compareString (map H.literal ns))
                  | (k,ns) <- [("A",["B","External"]),("B",["A"]),("Alone",[])]]
  check "instance reach including external leaf"
    [("A",["A","B","External"]),("Alone",["Alone"]),("B",["A","B","External"])]
    [(H.unpack k, map H.unpack (S.toList ns)) | (k,ns) <- M.toList (Modules.moduleReach direct)]

-- Construct the typed input independently of the writer, including the
-- noncanonical row order that an older reader accepts and must republish.
queryChecks = do
  let sha = H.literal (replicate 64 '1')
      other = H.literal (replicate 64 '2')
      node k reads = Q.QueryNode k sha reads T.Nothing
      table ns = M.fromList H.v_compareString [(Q.nodeKey n,n) | n <- ns]
      admitted ns = case W.planGraph W.defaultLimits [W.VNode 411
        [W.VText "MLF-CRATE-QUERY-GRAPH-1",W.VText "cfg",W.VNode 1 (map Q.encodeNode ns)]] of
        T.Left err -> error (H.unpack err)
        T.Right graph -> Q.admitIndex "cfg" graph
      result (T.Left err) = Left (H.unpack err)
      result (T.Right _) = Right ()
      order ns = case admitted ns of
        T.Left err -> error (H.unpack err)
        T.Right (_,canonical) -> canonical
      a = node "a" []
      shared = [("a",sha),("a",sha)]
      b = node "b" shared
      c = node "c" shared
  check "ordered v1 input needs a v2 publication" False (order [a,b,c])
  check "unordered index still admitted" False (order [c,a,b])
  check "read multiplicity" False (Q.sameNode b (node "b" [("a",sha)]))
  check "read order" False (Q.sameNode (node "c" [("a",sha),("b",sha)])
                                       (node "c" [("b",sha),("a",sha)]))
  check "payload location" False (Q.sameNode a (Q.QueryNode "a" sha [] (T.Just sha)))
  forM_ [([a,node "b" [("a",other)]], "query publication has stale dependency version"),
         ([a,node "b" [("missing",sha)]], "unpublished query dependency"),
         ([node "a" [("b",sha)],node "b" [("a",sha)]], "cyclic/deep query graph"),
         ([a,node "b" [("a","bad")]], "invalid query graph digest")] $ \(ns,err) ->
    check err (Left err) (result (admitted ns))
  let stable (Q.QueryNode k h edges location) = Q.QueryNode (Q.key "Binding" k) h
        [(Q.key "Binding" target, digest) | (target,digest) <- edges] location
      generation previous ns = do
        answer <- Q.publication "cfg" previous (table (map stable [a,b,c])) (table (map stable ns))
        pure $ case answer of
          T.Left err -> Left (H.unpack err)
          T.Right T.Nothing -> Right False
          T.Right (T.Just _) -> Right True
  check "matching admitted generation" (Right False) =<< generation sha [a,b,c]
  check "normalize unordered input on publish" (Right True) =<< generation "" [a,b,c]
  check "changed reads, same value hash" (Right True) =<< generation sha [a,node "b" [],c]
  check "reject stale reads in edited generation" (Left "query publication has stale dependency version")
    =<< generation sha [a,node "b" [("a",other)],c]
  -- Both generations describe A.f, although its declaration slot changes
  -- when A.a is added. Edges refer to the producer generation's digest.
  let l = W.VNode 1
      absent = W.VNode 4 []
      row desc h reads = W.VNode 413 [desc,W.VText h,l reads,absent]
      binding = W.VInt
      query tag i = W.VNode tag [W.VInt i]
      group = l . map binding
      snapshot names groups requests types rows = W.VNode 412
        [W.VText "MLF-CRATE-QUERY-GRAPH-2",W.VText "cfg",l (map W.VText names),l groups,
         l requests,l (map W.VText types),l rows]
      admit value = case W.planGraph W.defaultLimits [value] of
        T.Left err -> error (H.unpack err)
        T.Right graph -> Q.admitIndex "cfg" graph
      logical value k = case admit value of
        T.Right (m,_) -> case M.lookup H.v_compareString k m of
          T.Just n -> [(H.unpack target,H.unpack h) | (target,h) <- Q.nodeReads n]
          T.Nothing -> error "missing restored row"
        T.Left err -> error (H.unpack err)
      generationAt names g i h = snapshot names [group [i]] [] []
        [row (binding i) h [],row (query 419 g) sha [binding i,binding i]]
      target = Q.key "Binding" "A.f"
      groupKey = Q.key "InferScc" "3:A.f"
      reads h = replicate 2 (H.unpack target,H.unpack h)
  check "old generation resolves slot zero twice with its old version" (reads sha)
    (logical (generationAt ["A.f"] 0 0 sha) groupKey)
  check "new generation resolves slot one twice with its new version" (reads other)
    (logical (generationAt ["A.a","A.f"] 0 1 other) groupKey)
  let invalid label value = case result (admit value) of
        Left _ -> pure ()
        Right () -> error ("accepted " ++ label)
      f = row (binding 0) sha []
      fx = ["A.f","A.x"]
      two = [group [0,1]]
      e = W.VNode 414 [W.VInt 0,W.VInt 7,W.VText "Goal"]
      scoped = snapshot fx two [e] ["A.f"]
        [f,row (query 415 0) sha [],row (query 416 0) sha [],row (query 417 0) sha [],
         row (query 418 0) sha [],row (query 419 0) sha [],row (query 431 0) sha [],
         row (query 432 0) sha [binding 0,query 419 0,query 433 0],row (query 433 0) sha [],
         row (query 434 0) sha []]
      evKey = Q.key "Evidence" "10:3:A.f3:A.x1:74:Goal"
  check "typed group, binding, evidence and datatype targets preserve order"
    [(H.unpack k,H.unpack sha) | k <- [target,Q.key "InferScc" "3:A.f3:A.x",Q.key "Datatype" "A.f"]]
    (logical scoped evKey)
  mapM_ (uncurry invalid)
    [("negative declaration",snapshot fx [] [] [] [row (binding (-1)) sha []]),
     ("out of range declaration",snapshot fx [] [] [] [row (binding 2) sha []]),
     ("duplicate declaration",snapshot ["A.f","A.f"] [] [] [] [f]),
     ("duplicate group members",snapshot fx [group [1,1]] [] [] []),
     ("empty group",snapshot fx [group []] [] [] []),
     ("duplicate row",snapshot fx [] [] [] [f,f]),
     ("dangling typed read",snapshot fx two [] [] [row (binding 0) sha [query 419 0]]),
     ("cycle",snapshot fx [] [] [] [row (binding 0) sha [binding 0]]),
     ("wrong evidence group",snapshot fx [] [e] [] []),
     ("unknown edge kind",snapshot fx [] [] [] [row (query 410 0) sha []]),
     ("wrong datatype domain",snapshot fx [] [] [] [row (query 433 0) sha []])]
  check "exact logical identity budget" (Right ()) (result (Q.checkIdentityBudget 4 ["a","bcd"]))
  check "reject oversize logical identity population" (Left "query snapshot identity work limit exceeded")
    (result (Q.checkIdentityBudget 3 ["a","bcd"]))
  let chain n = [node (key i) [(key (i+1),sha) | i+1 < n] | i <- [0..n-1]]
      key i = H.literal (show (10000+i :: Int))
  check "last legal query DFS depth" (Right ()) (result (Q.validateClosure (table (chain 4096))))
  check "query DFS depth limit" (Left "cyclic/deep query graph")
    (result (Q.validateClosure (table (chain 4097))))
  let reverseChain n = [node (key i) [(key (i-1),sha) | i > 0] | i <- [0..n-1]]
  check "reaching an already-complete tail cannot hide excess depth" (Left "cyclic/deep query graph")
    (result (Q.validateClosure (table (reverseChain 4097))))

datatypeChecks = do
  let decl name constructor children = T.DataDecl name []
        [T.ConstructorDecl constructor [T.Applied child [] | child <- children]]
      ds = [decl "Z" "MkZ" ["A","B"],decl "B" "MkB" ["A"],
            decl "Unused" "MkUnused" [],decl "A" "MkA" ["B"]]
      names groups = map (H.unpack . Data.datatypeName) groups
  case CQ.prepareData ds of
    T.Left err -> error (H.unpack err)
    T.Right inventory -> do
      check "constructor selects its recursive datatype component" ["A","B"]
        (names (CQ.requiredDataIn inventory [("x",T.Nothing,T.SConstructor "MkB")] []))
      check "shared component selected once, in lexical order" ["A","B","Z"]
        (names (CQ.requiredDataIn inventory [] [("x",T.XCon "Z" []),("y",T.XCon "B" [])]))
      check "unrelated datatype roots" [] (names (CQ.requiredDataIn inventory [] [("x",T.XCon "External" [])]))

-- Inspect the resolver's actual numeric edges before any graph is built.
-- Two aliases reach one declaration, an identically spelled import reaches
-- another, and locals do not contribute a crate edge.
resolverChecks = do
  let parsed (file,src) = right (Parser.parseModule (H.literal (file ++ ".emlf")) (H.literal src))
      right (T.Right value) = pure value
      right (T.Left msg) = error (H.unpack msg)
      mangle e = H.literal (H.unpack (Modules.owner e) ++ "." ++ H.unpack (Modules.spelling e))
  mods <- mapM parsed [("A","module A where\nvalue = 1\n"),("B","module B where\nvalue = 2\n"),
    ("Via","module Via (module A) where\nimport A\n"),
    ("Main",unlines ["module Main where","import qualified A as First","import qualified B as Second",
       "import qualified Via as Again","value = 3","first = First.value","again = Again.value",
       "second = Second.value","shadow value = value","lambda = \\value -> value",
       "local = let value = First.value in value","self x = self x","left = right","right = left","main = first"])]
  crate <- right (Modules.resolveCrate T.NoImplicitPrelude M.empty mangle mods)
  let allModules = Modules.resolvedCrateModules crate
      allBindings@(D.BoundValues symbols bindings) = Modules.boundIn crate allModules
      names = D.symbolNodes symbols
      ids = Map.fromList [(H.unpack (V.at names i),V.toInt i) | D.Bound i _ _ <- bindings]
      uses = Map.fromList [(H.unpack (V.at names i),map V.toInt (R.references rhs)) | D.Bound i _ rhs <- bindings]
      target k = ids Map.! k
  check "qualified alias" [target "A.value"] (uses Map.! "Main.first")
  check "re-export keeps its defining ID" (uses Map.! "Main.first") (uses Map.! "Main.again")
  check "same spelling, different defining module" [target "B.value"] (uses Map.! "Main.second")
  check "source IDs differ" False (target "A.value" == target "B.value")
  check "local shadow has no top-level edge" [] (uses Map.! "Main.shadow")
  check "lambda shadow has no top-level edge" [] (uses Map.! "Main.lambda")
  check "nonrecursive let resolves RHS outside binder" [target "A.value"] (uses Map.! "Main.local")
  entry <- right (Modules.entryExpr crate (last allModules))
  case entry of
    R.Global i -> check "synthetic entry is a global leaf" (target "Main.main") (V.toInt i)
    _ -> error "main entry lost its declaration ID"
  check "self-edge retains binder ID" [target "Main.self"] (uses Map.! "Main.self")
  forM_ [allBindings, Modules.boundIn crate (filter ((=="Main") . H.unpack . Modules.moduleIdentity . Modules.resolvedSource) allModules)] $
    \b -> do
      expected <- right (D.declarationGroups (D.boundValues b))
      groups <- right (D.resolvedGroups b [] M.empty M.empty)
      check "resolved SCC ordering" (map (map H.unpack) expected) (map (map H.unpack) (D.groupSpellings groups))
  -- Rewrite the actual RHS. The SCC and the projected named syntax must both
  -- follow the new leaf, with no separate edge list to update.
  let same = H.literal "Main.left"
      change row@(D.Bound i a _) | V.at names i == same = D.Bound i a (R.Global i)
                                 | otherwise = row
      edited = D.BoundValues symbols (map change bindings)
  (_,editedGroups) <- right (D.resolvedGroups edited [] M.empty M.empty)
  let leftGroup = [ [(V.toInt i,rec) | (i,rec) <- g] | g <- editedGroups, any ((==target "Main.left") . V.toInt . fst) g ]
  check "replacing a global changes SCC membership and self-edge" [[(target "Main.left",True)]] leftGroup
  case [rhs | (n,_,rhs) <- D.boundValues edited, n == same] of
    [T.SVar printed] -> check "projection reads the same edited ID" "Main.left" (H.unpack printed)
    _ -> error "edited global projected as a different expression"
  clash <- parsed ("Local","module Local where\nimport qualified Remote as R\nf = R.x\n")
  -- An embedding may choose the same printed spelling for an external and
  -- a local. The remote occurrence must retain its own, inactive vertex.
  let remote = M.singleton "Remote" (Modules.interface [Modules.Entity "Foreign" "x" Modules.Value])
  let colliding e | H.unpack (Modules.owner e) `elem` ["Foreign","Local"] = "same"
                  | otherwise = mangle e
  collision <- right (Modules.resolveCrate T.NoImplicitPrelude remote colliding [clash])
  let matching@(D.BoundValues localSymbols entries) = Modules.boundIn collision
        (filter ((=="Local") . H.unpack . Modules.moduleIdentity . Modules.resolvedSource) (Modules.resolvedCrateModules collision))
  case entries of
    [D.Bound owner _ rhs] | [ref] <- R.references rhs -> do
      check "distinct entity despite equal printed name" False (V.toInt owner == V.toInt ref)
      check "printed collision preserves distinct stable identities" False (D.symbolKey localSymbols owner == D.symbolKey localSymbols ref)
      check "same-spelled local diagnostic" "Local.f" (H.unpack (D.symbolDisplay localSymbols owner))
      check "same-spelled imported diagnostic" "Foreign.x" (H.unpack (D.symbolDisplay localSymbols ref))
      check "named diagnostic chooses active definition" "Local.f"
        (H.unpack (Modules.displayNames (Modules.resolvedCrateDisplayNames collision) "same"))
    _ -> error ("missing colliding-name fixture edge " ++ show [(V.toInt i,map V.toInt (R.references rhs)) | D.Bound i _ rhs <- entries])
  (_,active) <- right (D.resolvedGroups matching [] M.empty M.empty)
  check "external reference cannot induce self recursion" [[False]] (map (map snd) active)
  -- The external reference prints as the local declaration. Its distinct
  -- slot still selects the nonrecursive unsigned source path.
  collisionPlan <- right (Source.indexedPlan matching [] M.empty M.empty)
  case collisionPlan of
    T.Just (Source.IndexedPlan table rows _ _ [[(slot,recursive)]]) -> do
      let declaration = snd (Source.namedBinding table rows slot)
      check "projected name alone would misclassify the external" False (Source.eligibleSource [declaration])
      check "resolved edge is authoritative for source eligibility" True (Source.eligibleSourceWith recursive [declaration])
    _ -> error "collision did not produce a singleton source plan"
  lib <- parsed ("ZLib","module ZLib (value) where\nvalue = 41\n")
  client <- parsed ("Client","module Client where\nimport qualified ZLib as L\nanswer = L.value\n")
  let entity = Modules.Entity "ZLib" "value" Modules.Value
      abi e = Artifact.definitionName (if Modules.owner e == "ZLib" then "lib" else "client") e
  producer <- right (Modules.resolveCrateDefinitions T.NoImplicitPrelude M.empty abi [lib])
  iface <- right (Modules.resolvedExports T.NoImplicitPrelude (last (Modules.resolvedCrateModules producer)))
  consumer <- right (Modules.resolveCrateDefinitions T.NoImplicitPrelude (M.singleton "ZLib" iface) abi [client])
  producerId <- right (Modules.termId (Modules.resolvedCrateBindings producer) entity)
  case Modules.boundIn consumer [last (Modules.resolvedCrateModules consumer)] of
    D.BoundValues slots [D.Bound _ _ body] | [importedId] <- R.references body -> do
      check "independent crates may assign different numeric slots" False (V.toInt producerId == V.toInt importedId)
      let producerSlots = Modules.bindingSymbols (Modules.resolvedCrateBindings producer)
      let oldKey = D.symbolKey producerSlots producerId
      check "stable definition remaps between two snapshots" (Just (V.toInt importedId))
        (case M.lookup H.v_compareString oldKey (D.symbolKeyIndex slots) of
          T.Just i -> Just (V.toInt i)
          T.Nothing -> Nothing)
      check "interface import preserves defining crate's ABI spelling" (H.unpack (abi entity))
        (H.unpack (D.symbolName slots importedId))
      check "two tables project the same exported identity" (H.unpack (D.symbolName producerSlots producerId))
        (H.unpack (D.symbolName slots importedId))
    _ -> error "client reference did not resolve to its own imported slot"
  both <- mapM parsed [("X","module X where\nf = 1\n"),("Y","module Y where\ng = 2\n")]
  let duplicated e | H.unpack (Modules.owner e) `elem` ["X","Y"] = "same"
                   | otherwise = mangle e
  duplicate <- right (Modules.resolveCrate T.NoImplicitPrelude M.empty duplicated both)
  case D.resolvedGroups (Modules.boundIn duplicate (Modules.resolvedCrateModules duplicate)) [] M.empty M.empty of
    T.Left reason -> check "duplicate emitted declarations" "duplicate value declaration" (H.unpack reason)
    T.Right _ -> error "two active definitions with equal spelling admitted"
  let eq = Modules.Entity "MLF.Primitive" "==" (Modules.Method "Eq")
      convert = Modules.Entity "MLF.Primitive" "fromString" (Modules.Method "IsString")
      named = Modules.Names (M.fromList Modules.compareEntity [(eq,"eq"),(convert,"convert")])
      terms = Modules.resolveNames named
      pat = T.SOverloadedStringPattern (T.ScalarString "x") "ignored" "ignored"
      expr = T.SCase (T.SIntLit 0) [T.SAlternative pat (T.SIntLit 1)]
  resolved <- right (Modules.resolveExpr terms (Modules.interface []) expr)
  patternIds <- mapM (right . Modules.termId terms) [eq,convert]
  case resolved of
    R.Case _ [(R.OverloadedStringPattern _ i j,_)] ->
      check "pattern stores both method IDs on the node" (map V.toInt patternIds) (map V.toInt [i,j])
    _ -> error "lost resolved string pattern"
  check "implicit edges come from the pattern" (map V.toInt patternIds) (map V.toInt (R.references resolved))
  let slots = D.symbols [("same",False),("same",False),("method",True)]
      [own,external,method] = V.indices (D.symbolNodes slots)
      helper = D.Bound own T.Nothing (R.IntLit 7)
      helpers = Surface.helperScope (D.BoundValues slots [helper])
      close i = right (Surface.closeResolvedInstance helpers (R.Instance [] [] "C" [] [(method,R.Global i)]))
  T.SInstanceDecl _ _ _ _ [(_,remoteBody)] <- close external
  case remoteBody of
    T.SVar n -> check "inactive import stays free in a method" "same" (H.unpack n)
    _ -> error "method captured a local helper with the import's printed name"
  T.SInstanceDecl _ _ _ _ [(_,localBody)] <- close own
  case localBody of
    T.SLet n (T.SSourceDefinition (T.SIntLit 7)) (T.SVar ref) ->
      check "local method dependency copies its source definition" ("same","same") (H.unpack n,H.unpack ref)
    _ -> error "method failed to capture its referenced helper"
  let visibility = D.indexedScopes slots [(own,"local scope"),(method,"method scope")]
      nested = D.nestedScopes visibility
  check "scope indexed by defining slot" (Just "local scope") (case D.scopeAt visibility own of
    T.Just a -> Just a; T.Nothing -> Nothing)
  check "equal spelling does not grant the external a local scope" True (case D.scopeAt visibility external of
    T.Nothing -> True; _ -> False)
  check "local shadow inherits lexical candidates" "lexical" (D.bindingScope nested "same" False "lexical")
  check "copied global helper keeps its own candidates" "local scope" (D.bindingScope nested "same" True "lexical")
  let primitive = T.SourceModule "<MLF.Primitive>" (T.Just "MLF.Primitive") T.Nothing [] [] [] [] [] T.Nothing T.LegacyEmlfV1
  let runScoped imports = do
        modules <- mapM parsed [("Inspect","module Inspect where\nclass Inspect a where { inspect : a -> Bool }\n"),
          ("Inst","module Inst () where\nimport Inspect\ninstance Inspect Int where { inspect = \\x -> true }\n"),
          ("A","module A (f) where\nimport Inspect\n" ++ imports ++ "f :: Bool\nf = inspect (1 :: Int)\n"),
          ("Main","module Main where\nimport A\nimport Inst ()\nmain = f\n")]
        pure (Compiler.compileLinked T.NoImplicitPrelude (primitive:modules))
  visible <- runScoped "import Inst ()\n"
  case visible of
    T.Right _ -> pure (); T.Left e -> error ("defining module lost its instance: " ++ H.unpack (Compiler.prettyError e))
  hidden <- runScoped ""
  case hidden of
    T.Left _ -> pure (); T.Right _ -> error "importer granted an instance to a different defining module"
  dictSource <- parsed ("DictRec",unlines ["module DictRec where",
    "class Tag a where { tag :: a -> Int }","instance Tag Int where { tag x = getName x }",
    "getName :: Int -> Int","getName x = tag x","untouched x = x"])
  dictCrate <- right (Crate.prepareCrate (Crate.CrateSpec "dict-rec" "" T.NoImplicitPrelude [] [] "" "") [] [primitive,dictSource])
  case Crate.preparedSourcePlan dictCrate of
    T.Just _ -> pure (); T.Nothing -> error "copied helper incorrectly merged a source and dictionary SCC"
  let fresh = D.symbols [("a",False),("b",False),("c",True)]
  let (appended, late) = D.appendSymbols fresh ["selector","dictionary"]
  check "generation appends slots in source order" [3,4] (map V.toInt late)
  check "appending preserves existing slot names and keys" [("a","a"),("b","b"),("c","c")]
    [(H.unpack (D.symbolName appended i),H.unpack (D.symbolKey appended i)) | i <- V.indices (D.symbolNodes fresh)]
  forM_ [-1,3] $ \number -> case D.checkedDeclId fresh number of
    T.Left why -> check "reject out-of-table slot" "declaration slot out of bounds" (H.unpack why)
    T.Right _ -> error "invalid serialized slot admitted"
  let forged = D.BoundValues fresh [D.Bound own T.Nothing (R.Global (V.fromInt 3))]
  case D.resolvedGroups forged [] M.empty M.empty of
    T.Left why -> check "reject global from another slot domain" "declaration slot out of bounds" (H.unpack why)
    T.Right _ -> error "out-of-bounds global admitted"
  case R.namedExpr (D.symbolName fresh) (R.Global external) of
    T.SVar n -> check "the same slot projects the updated spelling" "b" (H.unpack n)
    _ -> error "global projected as another kind of expression"
  let nested = R.AsPattern "x" (R.LazyPattern (R.NestedPattern "K"
                 [R.OverloadedStringPattern (T.ScalarString "p") method external]))
      exprTree = R.SharedBind nested (R.Global own)
        (R.Equations [([nested],R.LetRec [("x",T.InferRecursive,R.Global own)] (R.Local "x"))])
        (R.Global method) (R.Global external)
  check "nested, recursive and implicit edges read the actual leaves"
    (map V.toInt [method,external,own,method,external,own,method,external])
    (map V.toInt (R.references exprTree))
  let scope = D.symbols [("Z",False),("B",False),("external",False),("method",True)]
      ix n = case [i | i <- V.indices (D.symbolNodes scope), D.symbolName scope i == n] of
               [i] -> i
               _ -> error "bad fixture symbol"
      bound n ns = D.Bound (ix n) T.Nothing (foldr (R.App . R.Global . ix) (R.Constructor "()") ns)
      values = D.BoundValues scope [bound "Z" ["B","method","external"],bound "B" ["B"]]
      generated = [("0selector",["Z"]),("Cdict",["B"])]
      methods = M.singleton "method" ("0selector",[] :: [H.String])
      scopes = M.singleton "B" ["Cdict"]
      oracle = reference [("Z",["B","0selector"]),("B",["B","Cdict"]),("0selector",["Z"]),("Cdict",["B"])]
  let generatedView = D.generatedTable scope (map D.boundId [bound "Z" [],bound "B" []])
        (map fst generated) ["external","imported_dict"] methods
      slotNumber key = case D.generatedNameId generatedView key of
        T.Just i -> V.toInt i; _ -> error "missing generated table entry"
  check "selector, dictionary and imported support extend source slots" [4,5,6]
    (map slotNumber ["0selector","Cdict","imported_dict"])
  check "method redirects to the generated selector slot" (Just 4)
    (case D.selectorId generatedView (ix "method") of { T.Just i -> Just (V.toInt i); _ -> Nothing })
  check "ordinary declaration has no selector redirection" True
    (case D.selectorId generatedView (ix "Z") of { T.Nothing -> True; _ -> False })
  let abiSymbols = D.symbolsWithKeys [("same","own.key",False),("same","import.key",False)]
      [abiOwn,abiImport] = V.indices (D.symbolNodes abiSymbols)
      abiTable = D.generatedTable abiSymbols [abiOwn] [] ["import.key"] M.empty
  check "imported ABI key reuses the resolver slot despite display collision" (Just (V.toInt abiImport))
    (case D.generatedImportId abiTable "import.key" of T.Just i -> Just (V.toInt i); _ -> Nothing)
  check "no duplicate ABI declaration created" 2 (V.count (D.symbolNodes (D.generatedSymbols abiTable)))
  let splitDomain = D.symbolsWithKeys [("Z","local.Z",False),("B","B",False),("external","external",False),("method","method",True)]
      hiddenImport = D.generatedTable splitDomain [ix "Z"] [] ["Z"] M.empty
  check "local spelling and independent imported contract have separate slots" (Just 4,Just 0)
    (case D.generatedImportId hiddenImport "Z" of T.Just i -> Just (V.toInt i); _ -> Nothing,
     case D.generatedNameId hiddenImport "Z" of T.Just i -> Just (V.toInt i); _ -> Nothing)
  let ca = Modules.Entity "A" "AClass" Modules.Class
      cb = Modules.Entity "B" "BClass" Modules.Class
      ma = Modules.Entity "A" "m" (Modules.Method "AClass")
      mb = Modules.Entity "B" "m" (Modules.Method "BClass")
      resolvedMethods = Modules.resolveNames (Modules.Names (M.fromList Modules.compareEntity
          [(ca,"CA"),(cb,"CB"),(ma,"m"),(mb,"m")]))
      activeClass = D.generatedTable (Modules.bindingSymbols resolvedMethods) [] ["select_m"] []
        (M.singleton "m" ("select_m",["CA"]))
  localMethod <- right (Modules.termId resolvedMethods ma)
  inactiveMethod <- right (Modules.termId resolvedMethods mb)
  check "active class owns its selector" (Just 2) (case D.selectorId activeClass localMethod of
    T.Just i -> Just (V.toInt i); _ -> Nothing)
  check "inactive imported method cannot capture another class's same-spelled selector" True
    (case D.selectorId activeClass inactiveMethod of T.Nothing -> True; _ -> False)
  let collisions = D.symbols [("method",False),("method",True)]
      [local,importedMethod] = V.indices (D.symbolNodes collisions)
      redirects = D.generatedTable collisions [local] ["selector"] [] (M.singleton "method" ("selector",[] :: [H.String]))
  check "same-spelling local does not redirect to imported selector" True
    (case D.selectorId redirects local of { T.Nothing -> True; _ -> False })
  check "imported method retains its own selector edge" (Just 2)
    (case D.selectorId redirects importedMethod of { T.Just i -> Just (V.toInt i); _ -> Nothing })
  groups <- right (D.resolvedGroups values generated methods scopes)
  check "late selector and dictionary retain lexical DFS order" oracle (map (map H.unpack) (D.groupSpellings groups))
  let support = [("0selector",T.Nothing,T.SVar "Z"),("Cdict",T.Nothing,T.SVar "B")]
  mixed <- right (Source.indexedPlan values support methods scopes)
  case mixed of
    T.Nothing -> pure ()
    _ -> error "mixed generated/source SCC lost its whole-path fallback"
  plan <- right (Source.indexedPlan (D.BoundValues scope [bound "Z" ["B"],bound "B" ["Z"]]) [] M.empty M.empty)
  case plan of
    T.Just (Source.IndexedPlan symbols table ids [] [members]) -> do
      check "plan source order" ["Z","B"] (map (H.unpack . D.symbolName symbols) ids)
      check "plan SCC lexical order" ["B","Z"] (map (H.unpack . D.symbolName symbols . fst) members)
      let rows = map (Source.namedBinding symbols table . fst) members
      check "selected rows retain original ordinals" [(1,"B"),(0,"Z")]
        [(ordinal,H.unpack n) | (ordinal,(n,_,_)) <- rows]
    _ -> error "resolved query plan lost its indexed rows"

typedClassChecks = do
  let slots = D.symbolsWithKeys [("same","foreign.same",False),("same","own.same",False),("use","own.use",False)]
      [foreignId,own,use] = V.indices (D.symbolNodes slots)
      term = R.Lam "same" T.Nothing (R.Let "unused" (R.Global foreignId) (R.Global own))
      members = D.BoundValues slots [D.Bound own T.Nothing (R.IntLit 1),D.Bound use T.Nothing term]
      scope = D.indexedScopes slots [(own,memptyMask),(use,memptyMask)]
      memptyMask = I.empty
  body <- case Surface.bindIndexed members (T.SConstructor "()") of
    T.Left reason -> error (H.unpack reason); T.Right value -> pure value
  let rhsRefs = D.expressionGlobalIds body
  check "only the imported slot is free after the local declaration is bound" [0] (map V.toInt rhsRefs)
  result <- case Classes.lowerSeparateClassesAndSlots (M.singleton "foreign.same" (T.SCon "Int" [])) [] scope []
                 (T.SClassProgram [] [] [] body) of
    T.Left reason -> error (H.unpack reason); T.Right out -> pure out
  case result of
    ((T.SProgram [] (T.SDeclScope [parameter] (T.SLetRec [_] lowered)),_),T.Just generated) -> do
      check "external signature uses its original resolved slot" 0 (V.toInt parameter)
      check "class-free lowering keeps the imported slot despite lexical shadowing" [0] (map V.toInt (D.expressionGlobalIds lowered))
      check "external ABI admission keeps the declaration count" 3 (V.count (D.symbolNodes (D.generatedSymbols generated)))
    _ -> error "typed external wrapper disappeared"
  let methods = D.symbols [("method",True),("root",False)]
      [methodId,sourceId] = V.indices (D.symbolNodes methods)
      root = D.BoundValues methods [D.Bound sourceId T.Nothing (R.Global methodId)]
      klass = T.SClassDecl "C" [("a",T.Star)] [] [("method",T.SArrow (T.STVar "a") (T.STVar "a"))]
      instanceDecl = T.SInstanceDecl [] [] "C" [T.SCon "Int" []] [("method",T.SLam "x" T.Nothing (T.SVar "x"))]
      rootScopes = D.indexedScopes methods [(sourceId,I.singleton 0)]
  rootBody <- case Surface.bindIndexed root (T.SConstructor "()") of
    T.Left reason -> error (H.unpack reason); T.Right value -> pure value
  out <- case Classes.lowerSeparateClassesAndSlots M.empty ["dictionary"] rootScopes [I.singleton 0]
                (T.SClassProgram [] [klass] [instanceDecl] rootBody) of
    T.Left reason -> error (H.unpack reason); T.Right value -> pure value
  case out of
    ((T.SProgram _ (T.SDeclScope support (T.SLetRec _ lowered)),_),T.Just table) -> do
      check "generated selector and dictionary slots are the bound slots" [2,3] (map V.toInt support)
      let refs = D.expressionGlobalIds lowered
      check "lowered method occurrence selects its generated slot" True (2 `elem` map V.toInt refs)
      check "original method marker is not a runtime binding" False (V.toInt methodId `elem` map V.toInt refs)
      check "class candidate identity" (Just 3) (case D.generatedNameId table "dictionary" of
        T.Just i -> Just (V.toInt i); _ -> Nothing)
    _ -> error "class generation did not label support owners"
  let copied = T.SDeclScope [own] (T.SLet "same" (T.SGlobal own "outer") (T.SApp
        (T.SGlobal own "inner") (T.SApp (T.SVar "same") (T.SGlobal foreignId "same"))))
  check "copied helper hides its own slot only in its body" [1,0] (map V.toInt (D.expressionGlobalIds copied))
  check "scope with typed binder leaves a lexical reference free" ["same"] (map H.unpack (D.expressionNamedReads copied))
  check "prepared syntax also inventories the owned slot and enclosed occurrence"
    [1,1,1,0] [V.toInt i | T.DeclRef i _ <- D.querySyntaxRefs copied]
  let factsBase = D.symbolsWithKeys [("same","A.same",False),("same","B.same",False),
                                     ("method","C.method",True),("root","Root.root",False)]
      [qualified,plain,_,owner] = V.indices (D.symbolNodes factsBase)
      factsScope = D.indexedScopes factsBase [(owner,I.empty)]
      scheme h = if V.toInt h == V.toInt qualified then T.Just (["C"],True)
                 else if V.toInt h == V.toInt plain then T.Just ([],False) else T.Nothing
      rootResult used = Classes.withClassScopes M.empty [] factsScope [] (T.SClassProgram [] [klass] [] (T.SConstructor "()")) $ \inv ->
        Classes.lowerUnsignedRootAt (\_ _ _ _ -> []) (T.Just owner) (Classes.withCheckedClassContracts scheme inv)
          M.empty M.empty "root" (T.SGlobal used "same")
      rootContract used = case rootResult used of
        T.Right (Classes.SourceRootLowering body labels _ protected) -> (map (\(_,c,_) -> H.unpack c) labels,protected)
        T.Left reason -> error (H.unpack reason)
  check "qualified predecessor read by slot despite identical display" (["C"],True) (rootContract qualified)
  check "ordinary predecessor does not inherit its same-spelled peer's scheme" ([],False) (rootContract plain)
  let infer slot = Inference.compileOpenGroupIndexed "answer" [(foreignId,"external",T.XCon "Int" [])] []
        [(use,("answer",T.Nothing,T.SLet "external" (T.SBoolLit True) (T.SGlobal slot "external")))]
  case infer foreignId of
    T.Right fragment -> case Open.bindings fragment of
      [(_,T.XCon n [])] -> check "raw group global import survives local shadow" "Int" (H.unpack n)
      _ -> error "unexpected raw group export type"
    T.Left reason -> error (H.unpack reason)
  let externalType = T.XCon "Int" []
      typedUnit = Inference.compileLoweredGroupIndexed (const "") "answer" [(foreignId,"external",externalType)] []
        [(use,("answer",T.Nothing,T.SGlobal foreignId "different-display"))]
      namedUnit = Inference.compileLoweredGroupUsing (const "") "answer" [CQ.dependencyInterface [("external",externalType)]] []
        [("answer",T.Nothing,T.SVar "external")]
  case (typedUnit,namedUnit) of
    (T.Right t,T.Right n) -> check "unit and named lowering emit identical xMLF"
      (H.unpack (Pretty.prettyTerm (Separate.objectTerm n))) (H.unpack (Pretty.prettyTerm (Separate.objectTerm t)))
    (T.Left reason,_) -> error (H.unpack reason)
    (_,T.Left reason) -> error (H.unpack reason)
  case infer own of
    T.Left _ -> pure (); _ -> error "missing declaration slot was captured by a lexical name"

-- The reference propagates named flags to convergence, independently of
-- reverse edges and the candidate's work queue.
protectionChecks = do
  let chain = [(show i,[show (i+1)]) | i <- [0..126::Int]] ++ [("127",[])]
      diamond = [("join",["left","right"]),("left",["import"]),("right",["import"]),
                 ("import",[]),("cycleA",["cycleB","join"]),("cycleB",["cycleA"]),("unrelated",[])]
  forM_ [(chain,["127"]),(chain,[]),(diamond,["import"]),(diamond,[])] $ \(edges,seeds) -> do
    let keys = map fst edges
        slots = Map.fromList (zip keys (map V.fromInt [0..]))
        rows = [(slots Map.! n,n `elem` seeds,[slots Map.! ref | ref <- deps]) | (n,deps) <- edges]
        spread flags = [n | (n,deps) <- edges, n `elem` seeds || any (`elem` flags) deps]
        settle flags = let next = spread flags in if next == flags then next else settle next
        flags = Classes.propagateProtection (fromIntegral (length keys)) rows
    check "protection equals independent named fixed point" (settle []) [n | n <- keys,V.at flags (slots Map.! n)]
-- Recover the calling convention from the checked result path. Do not
-- instantiate or rewrite the type actually imported by the checker.
importConventionChecks = do
  let names = M.fromList H.v_compareString [("DA","A"),("DB","B")]
      a = T.XTyVar 7
      int = T.XCon "Int" []
      dict n = T.XCon n [int]
      prefix n = T.XArrow (dict n)
      observe = map H.unpack . Separate.importClasses names
      bounded = T.XForall a (prefix "DB" (prefix "DB" (T.XArrow int int)))
                  (prefix "DA" (T.XVar a))
      shadowed = T.XForall a (prefix "DA" int) (T.XForall a (T.XVar a) (prefix "DB" (T.XVar a)))
  check "bounded result retains all repeated evidence slots in order" ["A","B","B"] (observe bounded)
  check "shadowing forall captures the outer environment of its bound" ["B","A"] (observe shadowed)
  check "unused forall bound does not contribute evidence" [] (observe (T.XForall a bounded int))
  check "ordinary argument ends the evidence prefix" ["A"] (observe (prefix "DA" (T.XArrow int (prefix "DB" int))))
  check "constraint inside a function argument is local" [] (observe (T.XArrow (prefix "DA" int) int))
  check "a bounded ordinary input remains explicit" [] (observe (T.XForall a (dict "DA") (T.XArrow (T.XVar a) int)))
  check "unbound result variable ends the metadata view" [] (observe (T.XVar a))
  check "managed call stack can follow an ordinary hidden slot" ["B","MLFHasCallStack"]
    (observe (T.XForall a (T.XArrow (T.XCon "MLFStackEvidence" []) int) (prefix "DB" (T.XVar a))))

orderedSyntaxChecks = do
  let i = V.fromInt 4
      ref (T.LexicalRef n) = (Nothing,H.unpack n)
      ref (T.DeclRef j n) = (Just (V.toInt j),H.unpack n)
      inspect candidates inventory expr = case D.observeSyntax candidates inventory expr of
        D.Observation vs ts cs ks -> (map ref vs,map H.unpack ts,map H.unpack cs,map H.unpack ks)
      ann = T.SAnnotation [] (T.SQualified [T.SPredicate "Class" [T.SCon "Arg" []]] (T.SCon "Result" []))
      span0 = T.SourceSpan "pkg" "M" "M.hs" 1 1 1 2
      value = T.SApp (T.SVar "$MLF.Infix.+") (T.SConstructor "Box")
      scoped = T.SDeclScope [i] (T.SLam "x" (T.Just ann) (T.SGlobal i "hint"))
      wanted = T.SWantedRefs "Dict" [(T.GivenEvidence,T.LexicalRef "dict"),(T.InstanceEvidence,T.DeclRef i "impl")]
      blocks = [value,T.SCallSite "site" span0 scoped,T.SSourceDefinition wanted]
      chain = foldl1 T.SApp; pairs [x] = x
      pairs xs = pairs (combine xs) where
        combine (a:b:rs) = T.SApp a b : combine rs
        combine end = end
      count = 1024::Int
  forM_ [False,True] $ \candidates -> forM_ [False,True] $ \inventory -> do
    let vs = [(Nothing,"+")] ++ (if inventory then [(Just 4,"x"),(Just 4,"hint")] else [])
              ++ (if candidates then [(Nothing,"dict"),(Just 4,"impl")] else [])
        expected = (concat (replicate count vs),concat (replicate count ["Arg","Result","Dict"]),
                    replicate count "Box",replicate count "Class")
        trees = concat (replicate count blocks)
    check "dependency occurrence order on an application spine" expected (inspect candidates inventory (chain trees))
    check "dependency occurrence order on a balanced tree" expected (inspect candidates inventory (pairs trees))
  let vars = ["$MLF.Infix.+","Box","x","hint","Dict","dict","impl"]
  forM_ [chain,pairs] $ \build ->
    check "all names preserve binder and occurrence order" (concat (replicate count vars))
      (map H.unpack (Desugar.allNames (build (concat (replicate count blocks)))))
  let p = T.SAsPattern "outer" (T.SConstructorPattern "C" [T.Just "field",T.Nothing])
      body = T.SDo [T.SDoBind p value,T.SDoThen scoped,T.SDoLet "local" T.Nothing wanted,
               T.SDoLetRec [("rec",T.InferRecursive,T.SVar "rec")]]
             (T.SCase (T.SVar "s") [T.SAlternative p (T.SVar "z")])
  check "names in patterns, statements and recursive definitions"
    ["outer","field","$MLF.Infix.+","Box","x","hint","local","Dict","dict","impl","rec","rec","s","outer","field","z"]
    (map H.unpack (Desugar.allNames body))
  let symbols = D.symbolsWithKeys [("a","key",False),("b","key",False),("root","owner",False)]
      scope = Source.declarationScope symbols (map V.fromInt [0,1,2]) [] []
      slots = Source.GroupSlots scope [V.fromInt 2] [] []
      refs ids = chain [T.SGlobal (V.fromInt n) "label" | n <- ids]
      table ids = let member = [("root",T.Nothing,refs ids)]
                      group = Source.PreparedGroup member [] [] M.empty [] T.Nothing []
                  in case CQ.referenceTable slots group of
                       CQ.ReferenceTable _ _ ranks -> map (V.toInt . fst) (M.toList ranks)
  check "last ID wins a stable-key collision" [0,2] (table [0,1,0])
  check "reversing the last ID changes the representative" [1,2] (table [1,0,1])

layoutTokenChecks = do
  let token col text = Lexer.Token text 3 col 3 (col + H.v_stringLength text)
      view (Lexer.Token t sl sc el ec) = (H.unpack t,sl,sc,el,ec)
      end = Lexer.Token "" 5 1 5 1
      follow = [token 6 "of",token 9 "{",token 10 "y",token 11 "}",token 12 ")"]
  forM_ ["(","[","{"] $ \delimiter -> forM_ [[],[Layout.Layout Layout.LayoutBlock 3],[Layout.Marker Layout.LetMark 1]] $ \outer ->
    forM_ ([H.literal [toEnum i] | i <- [0..127]] ++ ["界","😀","then","else","do","in",":+"]) $ \text -> do
      let frames = Layout.Explicit delimiter:outer
          t = token 3 text
          previous = T.Just (Lexer.Token "first" 2 1 2 6)
      forM_ [True,False] $ \shared ->
        check "one-token layout agrees with the ordinary frame rules"
          (map view (Layout.normalLayout shared frames previous t follow end))
          (map view (Layout.normal shared frames previous t follow end))
  forM_ ([0..127] ++ [955,30028,128512]) $ \cp -> do
    let text = H.literal ['α',toEnum cp,'z']
    check "one-scalar spelling, including UTF8" (H.unpack (H.v_stringSlice text 1 1)) (H.unpack (Lexer.tokenSpelling text 1 2 (fromIntegral cp)))
  let text = H.literal "α123"
  check "multi-scalar spelling" "123" (H.unpack (Lexer.tokenSpelling text 1 4 49))

loweringChecks = do
  let x = T.SVar "x"
      def = T.SDefaultPattern T.Nothing
      bind = T.SDefaultPattern (T.Just "x")
      ann = T.SAnnotation [] (T.SCon "Int" [])
      choose arms = T.SCase x [T.SAlternative p e | (p,e) <- arms]
      simple = choose [(T.SConstructorPattern "Box" [T.Just "x"],x),(def,T.SIntLit 4)]
      statements = T.SDo [T.SDoLet "x" T.Nothing x] x
      cases = [(True, simple),(True, choose []),(True, choose [(bind,simple)]),
               (False, choose [(T.SLazyPattern bind,x)]),(False,choose [(T.SAnnotatedPattern "x" ann,x)]),
               (False, choose [(T.SNestedPattern "Box" [bind],x)]),(False,choose [(T.SBoolPattern True,x)]),
               (False,choose [(def,statements)]),(False,T.SCase statements [T.SAlternative def x]),
               (False,T.SEquations [])]
      env = Data.emptyDataEnv
      ordinary e = case Desugar.lowerSharedDo env e of
        T.Left err -> T.Left err
        T.Right shared -> Fresh.runFresh (Desugar.allNames shared) (Surface.lower env shared)
      result (T.Left err) = Left (H.unpack err)
      result (T.Right e) = Right (H.unpack (CQ.encodeExpression e))
  forM_ cases $ \(eligible,e) -> do
    check "surface-core admission" eligible (Surface.surfaceCore e)
    check "surface lowering agrees with the fresh-name traversal" (result (ordinary e))
      (result (Surface.lowerExpressionWithData env e))

lexicalRunChecks = do
  let cursor (Lexer.Cursor i l c) = (i,l,c)
      token (Lexer.Token t sl sc el ec) = (H.unpack t,sl,sc,el,ec)
      scanned result = case result of
        T.Left e -> Left (H.unpack e)
        T.Right (Lexer.Scanned ts eof) -> Right (map token (ts++[eof]))
      spellings = ["able","axon","able","a界on","able","Alpha","Amber","Alpha","name'","name2",
                   replicate 32 'a',replicate 33 'a',"\x10400","=>","++","0xA7","1.5e-2"]
      source = "start\t" ++ unwords spellings ++ "\n{- one {- two -} -}\nend"
      pos (l,c) '\n' = (l+1,1)
      pos (l,c) '\t' = (l,c+8-(c-1) `mod` 8)
      pos (l,c) _ = (l,c+1)
      range spelling start = let finish = foldl pos start spelling
                             in (spelling,fst start,snd start,fst finish,snd finish)
      wantedTokens names point = case names of
        [] -> []
        x:xs -> let item@(_,_,_,l,c) = range x point in item:wantedTokens xs (l,c+1)
      expected = [range "start" (1,1)] ++ wantedTokens spellings (1,9) ++
                 [range "end" (3,1),range "" (3,4)]
      corpus = H.literal ("0x8e☺\n \t" ++ source ++ concatMap (:[]) ['\0'..'\127'])
      size = H.v_stringLength corpus
  forM_ [Lexer.scanTokens,Lexer.scanSourceTokens] $ \scan ->
    check "cached spelling collisions preserve all token extents" (Right expected) (scanned (scan "lex" (H.literal source)))
  forM_ [Lexer.isDigit,Lexer.isHexDigit,Lexer.isIdentChar,Lexer.isOperator] $ \predicate ->
    forM_ [0..size] $ \i -> do
      let before = Lexer.Cursor i 12 19
      check "single-line runs retain the reference scanner coordinates"
        (cursor (Lexer.consumeWhile predicate corpus size before))
        (cursor (Lexer.consumeRun predicate corpus size before))
  forM_ [0,1,254,255,256,257,511,512,513] $ \n ->
    forM_ ["a","λ","a界😀"] $ \alphabet -> do
      let scalars = take n (cycle alphabet)
          t = H.literal scalars
          indices = filter (\i -> 0 <= i && i < n) [0,1,253,254,255,256,n-2,n-1]
      check "UTF8 byte length agrees with scalar widths" (fromIntegral (sum (map width scalars))) (H.v_stringUtf8Length t)
      forM_ indices $ \i -> do
        check "scalar offset in a shared or indexed block"
          (fromIntegral (fromEnum (scalars!!i))) (H.v_stringCodeAt t (fromIntegral i))
        forM_ [0,1,min 3 (n-i),n-i] $ \k ->
          check "exact slice across scalar blocks" (take k (drop i scalars))
            (H.unpack (H.v_stringSlice t (fromIntegral i) (fromIntegral k)))
  where
    width ch | fromEnum ch < 128 = 1 :: Int
             | fromEnum ch < 2048 = 2
             | fromEnum ch < 65536 = 3
             | otherwise = 4

projectedBindingChecks = do
  let base = D.symbolsWithKeys [("same","external",False),("same","local",False),("use","consumer",False),("unused","unused",False)]
      changed = D.symbols [("other",False),("local",False),("owner",False),("unused",False)]
      [external,local,owner,_] = V.indices (D.symbolNodes base)
      term = R.Lam "same" T.Nothing (R.App (R.Global external) (R.Global local))
      bound i rhs = D.Bound i T.Nothing rhs
      rows expr = [bound owner expr, bound local (R.IntLit 17)]
      scope symbols = D.indexedScopes symbols [(local,I.empty),(owner,I.empty)]
  forM_ [base,changed] $ \symbols -> do
    let bindings = D.BoundValues base (rows term)
    (plan,_) <- right (Source.prepareResolvedSourcePlan bindings M.empty [] [] [] [] (scope symbols) [])
    case plan of
      T.Just p -> case Source.planGraph p of
        Source.IndexedPlan target table ids [] _ -> do
          forM_ (zip ids (map snd3 (rows term))) $ \(i,raw) -> do
            let display = D.symbolName target
                rename _ = "different display"
                get f = let (_,(_,_,rhs)) = f table i in rhs
                shared = case V.at table i of { Source.ProjectedSource {} -> True; _ -> False }
            check "cache restricted to the original display prefix" (D.symbolName base external == display external) shared
            check "authentic indexed view" True (Equality.eqSExprBits (get (Source.planIndexedBinding target)) (R.indexedExpr display raw))
            check "arbitrary display projection" True (Equality.eqSExprBits (get (Source.indexedBindingWith rename)) (R.indexedExpr rename raw))
            check "legacy named projection" True (Equality.eqSExprBits (get (Source.projectBinding rename)) (R.namedExpr rename raw))
          check "projection source ordinal order" (map V.toInt [owner,local]) (map V.toInt ids)
          let views = [rhs | (_,_,rhs) <- Source.planSourceInputs p]
          check "source plan inputs preserve indexed globals" True (and (zipWith Equality.eqSExprBits views (map (R.indexedExpr (D.symbolName target) . snd3) (rows term))))
        _ -> fail "indexed graph expected"
      _ -> fail "source plan expected"
  where
    right (T.Right v) = pure v
    right (T.Left e) = fail (H.unpack e)
    snd3 (D.Bound _ _ rhs) = rhs


main = do
  let chain = [("v" ++ show i,["v" ++ show (i+1)]) | i <- [0..24 :: Int]]
      wide = [("top",map fst chain)] ++ chain
      duplicate = [("z",["a"]),("a",["missing","a","a"]),("z",["other"])]
  forM_ ([]:duplicate:chain:wide:allGraphs) $ \graph -> do
    testGraph graph
    testGraph (reverse graph)
  -- This path is too large for the all-pairs oracle above.
  let names = [H.literal (show (100000+i :: Int)) | i <- [0..8191]]
      line = zip names (map (:[]) (tail names) ++ [[]])
  let unpackGroups = map (map H.unpack)
  check "deep chain finish order" (unpackGroups (map (:[]) (reverse names))) (unpackGroups (D.components line))
  check "deep ring membership" [map H.unpack names]
    (unpackGroups (D.components (zip names (map (:[]) (tail names ++ [head names])))))
  packageChecks
  queryChecks
  datatypeChecks
  orderedSyntaxChecks
  lexicalRunChecks
  layoutTokenChecks
  loweringChecks
  resolverChecks
  protectionChecks
  projectedBindingChecks
  importConventionChecks
  typedClassChecks
  putStrLn "1032 ordered SCC and reach comparisons, query DAG and package controls passed"
