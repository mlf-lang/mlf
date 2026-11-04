{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Monad (forM_, unless)
import Data.Bits (testBit)
import Data.List (nub, sort)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.CrateQuery as CQ
import qualified Bootstrap.Data as Data
import qualified Bootstrap.Dependency as D
import qualified Bootstrap.QueryGraph as Q
import qualified Bootstrap.IndexVec as V
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
  check "ordered index" True (order [a,b,c])
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
  let generation previous ns = do
        answer <- Q.publication "cfg" previous (table [a,b,c]) (table ns)
        pure $ case answer of
          T.Left err -> Left (H.unpack err)
          T.Right T.Nothing -> Right False
          T.Right (T.Just _) -> Right True
  check "matching admitted generation" (Right False) =<< generation sha [a,b,c]
  check "normalize unordered input on publish" (Right True) =<< generation "" [a,b,c]
  check "changed reads, same value hash" (Right True) =<< generation sha [a,node "b" [],c]
  check "reject stale reads in edited generation" (Left "query publication has stale dependency version")
    =<< generation sha [a,node "b" [("a",other)],c]
  let chain n = [node (key i) [(key (i+1),sha) | i+1 < n] | i <- [0..n-1]]
      key i = H.literal (show (10000+i :: Int))
  check "last legal query DFS depth" (Right ()) (result (Q.validateClosure (table (chain 4096))))
  check "query DFS depth limit" (Left "cyclic/deep query graph")
    (result (Q.validateClosure (table (chain 4097))))

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
      uses = Map.fromList [(H.unpack (V.at names i),map V.toInt refs) | D.Bound i _ refs <- bindings]
      target k = ids Map.! k
  check "qualified alias" [target "A.value"] (uses Map.! "Main.first")
  check "re-export keeps its defining ID" (uses Map.! "Main.first") (uses Map.! "Main.again")
  check "same spelling, different defining module" [target "B.value"] (uses Map.! "Main.second")
  check "source IDs differ" False (target "A.value" == target "B.value")
  check "local shadow has no top-level edge" [] (uses Map.! "Main.shadow")
  check "lambda shadow has no top-level edge" [] (uses Map.! "Main.lambda")
  check "nonrecursive let resolves RHS outside binder" [target "A.value"] (uses Map.! "Main.local")
  (_,entryRefs) <- right (Modules.entryUses crate (last allModules))
  check "synthetic entry refers to the resolved main" [target "Main.main"] (map V.toInt entryRefs)
  check "self-edge retains binder ID" [target "Main.self"] (uses Map.! "Main.self")
  forM_ [allBindings, Modules.boundIn crate (filter ((=="Main") . H.unpack . Modules.moduleIdentity . Modules.resolvedSource) allModules)] $
    \b@(D.BoundValues universe rows) -> do
      expected <- right (D.declarationGroups (D.boundValues b))
      -- A rebuilt graph that re-observes any source RHS fails this check.
      let sealed = D.BoundValues universe [D.Bound i (error "rescanned source declaration") r | D.Bound i _ r <- rows]
      groups <- right (D.resolvedGroups sealed [] M.empty M.empty)
      check "resolved SCC ordering" (map (map H.unpack) expected) (map (map H.unpack) (D.groupSpellings groups))
  clash <- parsed ("Local","module Local where\nimport qualified Remote as R\nf = R.x\n")
  -- An embedding may choose the same printed spelling for an external and
  -- a local. The remote occurrence must retain its own, inactive vertex.
  let remote = M.singleton "Remote" (Modules.interface [Modules.Entity "Foreign" "x" Modules.Value])
  let colliding e | H.unpack (Modules.owner e) `elem` ["Foreign","Local"] = "same"
                  | otherwise = mangle e
  collision <- right (Modules.resolveCrate T.NoImplicitPrelude remote colliding [clash])
  let matching@(D.BoundValues _ entries) = Modules.boundIn collision
        (filter ((=="Local") . H.unpack . Modules.moduleIdentity . Modules.resolvedSource) (Modules.resolvedCrateModules collision))
  case entries of
    [D.Bound owner _ [ref]] -> check "distinct entity despite equal printed name" False (V.toInt owner == V.toInt ref)
    _ -> error ("missing colliding-name fixture edge " ++ show [(V.toInt i,map V.toInt rs) | D.Bound i _ rs <- entries])
  (_,active) <- right (D.resolvedGroups matching [] M.empty M.empty)
  check "external reference cannot induce self recursion" [[False]] (map (map snd) active)
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
      terms = Modules.termIds named
      pat = T.SOverloadedStringPattern (T.ScalarString "x") "ignored" "ignored"
      expr = T.SCase (T.SIntLit 0) [T.SAlternative pat (T.SIntLit 1)]
  (_,patterns) <- right (Modules.resolveUses terms named (Modules.interface []) expr)
  patternIds <- mapM (right . Modules.termId terms) [eq,convert]
  check "implicit pattern operations retain both method IDs" (map V.toInt patternIds) (map V.toInt patterns)
  let scope = D.symbols [("Z",False),("B",False),("external",False),("method",True)]
      ix n = case M.get H.v_compareString n (D.symbolIds scope) of { [i] -> i; _ -> error "bad fixture symbol" }
      bound n ns = D.Bound (ix n) (error "late binding rescanned a source RHS") (map ix ns)
      values = D.BoundValues scope [bound "Z" ["B","method","external"],bound "B" ["B"]]
      generated = [("0selector",["Z"]),("Cdict",["B"])]
      methods = M.singleton "method" ("0selector",[] :: [H.String])
      scopes = M.singleton "B" ["Cdict"]
      oracle = reference [("Z",["B","0selector"]),("B",["B","Cdict"]),("0selector",["Z"]),("Cdict",["B"])]
  groups <- right (D.resolvedGroups values generated methods scopes)
  check "late selector and dictionary retain lexical DFS order" oracle (map (map H.unpack) (D.groupSpellings groups))

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
  resolverChecks
  putStrLn "1032 ordered SCC and reach comparisons, query DAG and package controls passed"
