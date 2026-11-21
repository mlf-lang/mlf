{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Exception (ErrorCall, displayException, evaluate, try)
import Control.Monad (forM_, unless)
import Data.Bits (testBit)
import Data.List (isInfixOf, nub, sort)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified Bootstrap.ArtifactStorage as Storage
import qualified Bootstrap.ArtifactStructure as Structure
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.BuiltinPreludeLiteral as BuiltinLiteral
import qualified Bootstrap.Classes as Classes
import qualified Bootstrap.Compiler as Compiler
import qualified Bootstrap.Crate as Crate
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.CrateGraph as CrateGraph
import qualified Bootstrap.CrateQuery as CQ
import qualified Bootstrap.Data as Data
import qualified Bootstrap.Dependency as D
import qualified Bootstrap.Desugar as Desugar
import qualified Bootstrap.Fresh as Fresh
import qualified Bootstrap.IntMap as IntMap
import qualified Bootstrap.Layout as Layout
import qualified Bootstrap.Lexer as Lexer
import qualified Bootstrap.Parsec as Parsec
import qualified Bootstrap.Resolved as R
import qualified Bootstrap.SourceEquality as Equality
import qualified Bootstrap.SourceInference as Source
import qualified Bootstrap.Surface as Surface
import qualified Bootstrap.QueryGraph as Q
import qualified Bootstrap.InferenceUnit as Inference
import qualified Bootstrap.OpenFragment as Open
import qualified Bootstrap.Separate as Separate
import qualified Bootstrap.LLVM.Codegen as Codegen
import qualified Bootstrap.LLVM.Optimize as Optimize
import qualified Bootstrap.X.Check as XCheck
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Type as XT
import qualified Bootstrap.Runtime as Runtime
import qualified Tests.IndependentCheck as Independent
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.IntSet as I
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.Primitive as Primitives
import qualified Bootstrap.Map as M
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.Types as T
import qualified Bootstrap.Set as S
import qualified MLF.Host.Base as H
import qualified MLF.Primitive as Prim
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
  let frame fields = concat [show (length value) ++ ":" ++ value | value <- fields]
      branches = [Modules.Entity "M" "葉:🌿" (Modules.Constructor "T"),
                  Modules.Entity "M" "a" Modules.Value, Modules.Entity "M" "a" Modules.Value]
      fields = [frame ["M","葉:🌿","constructor","T"],frame ["M","a","value",""],frame ["M","a","value",""]]
      exportRows = [("界",branches),("A",[]),("界",[])]
      expectedExports = frame [frame ["A",""],frame ["界",frame (sort fields)],frame ["界",""]]
  check "canonical export rows preserve scalar framing, duplicate entities and same-owner order"
    expectedExports (H.unpack (Artifact.encodeExports exportRows))
  let suffixes = [(s, i) | s <- ["", "_z9", "\0a\DEL", "葉:🌿", "á"], i <- [0..length s+1]]
      scalarSuffix s i = concatMap (\c -> show (fromEnum c) ++ "_") (drop i s)
  check "legacy identifier suffixes encode Unicode scalar offsets"
    [scalarSuffix s i | (s,i) <- suffixes]
    [H.unpack (Separate.encodedFrom (H.literal s) (fromIntegral i)) | (s,i) <- suffixes]
  let builtin ident modules = Artifact.CrateInterface ident [] modules [] [] [] [] [] [] [] "" "" []
      identityCheck iface = case Artifact.validateBuiltinOwnership iface of
        T.Left message -> Left (H.unpack message)
        T.Right _ -> Right ()
  check "current IO-world builtin identity admitted" (Right ())
    (identityCheck (builtin "mlf:builtin-shared-haskell-v1:15" ["MLF.Primitive","Prelude"]))
  check "preceding builtin identity rejected" (Left "stale or forged builtin crate identity")
    (identityCheck (builtin "mlf:builtin-shared-haskell-v1:12" ["MLF.Primitive","Prelude"]))
  let bogus = builtin "wrong" ["Prelude","MLF.Primitive"]
      source = T.SourceModule "Shared.hs" (T.Just "Shared") T.Nothing [] [] [] [] [] T.Nothing T.SharedHaskellV1
      noLoad _ = error "invalid dependency reached the loader or installer"
      spec = Crate.CrateSpec "example" "" T.NoImplicitPrelude [] [] "cache" "prelude"
  existing <- Crate.withPreludeLoading noLoad noLoad spec [source] [("bogus.mlfci",bogus)]
  case (Artifact.validateInterface bogus,existing) of
    (T.Left expected,T.Left actual) -> check "caller supplied Prelude metadata receives full validation"
      (H.unpack expected) (H.unpack actual)
    _ -> fail "invalid caller supplied Prelude metadata was accepted"
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
  let origin = T.SourceSpan "pkg" "Mod" "file" 1 1 1 1
      prepared scope budget expression = case CrateGraph.packedOriginIn scope origin 0 budget expression "header" of
        T.Nothing -> Nothing
        T.Just value -> Just (H.unpack value)
      source = CrateGraph.SourceOrigin id (M.singleton "ctor" "local:0") 0 M.empty 0
      names = map H.literal (["","ctor","葉:λ","a\0"] ++ map show [1..40 :: Int])
      uses = take 150 (cycle names)
      expr = foldr (T.SApp . T.SConstructor) (T.SConstructor "end") uses
      literal name = CQ.encodeExpression (T.SConstructor name)
      field name = "x" ++ H.unpack (Separate.pack [literal name])
      charge name = H.v_stringUtf8Length (literal name)
      budget = charge "end" + sum [25 + charge name | name <- uses]
      framed name = let value = H.unpack name in show (length value) ++ ":" ++ value
      symbol seen name = case lookup name (zip seen [0..]) of
        Just slot -> ('c' : [toEnum slot],seen)
        Nothing | length seen < 32 -> ('C' : framed name,seen ++ [name])
                | otherwise -> (field name,seen)
      encode seen [] = fst (symbol seen "end")
      encode seen (name:rest) = let (encoded,next) = symbol seen name
                                in 'a' : encoded ++ encode next rest
      bytes = "P4header" ++ encode [] uses
  forM_ [CrateGraph.WrittenOrigin,source] $ \scope -> do
    check "prepared constructors retain definitions and references across pages" (Just bytes) (prepared scope budget expr)
    check "prepared constructors charge each occurrence" Nothing (prepared scope (budget-1) expr)
    check "a prepared tree without pooled constructors or literals keeps its P3 key"
      (Just "P3headerv") (fmap (take 9) (prepared scope 10000 (T.SVar "x")))
    let ctor = T.SConstructor "C"
        unary = T.SApp ctor ctor
        binary = T.SApp (T.SApp ctor unary) ctor
        cost = 3*25 + 4*charge "C"
        ref = "c" ++ [toEnum 0]
    check "unary and binary constructor fields retain preorder and dictionary slots"
      (Just ("P4header" ++ "aaC1:C" ++ "a" ++ ref ++ ref ++ ref)) (prepared scope cost binary)
    check "grouped constructor fields charge every application and every occurrence"
      Nothing (prepared scope (cost-1) binary)
    let literal n = T.SIntLit n
        packed ns = prepared scope 10000 (foldr1 T.SApp (map literal ns))
    check "prepared literals carry preorder deltas across applications"
      (Just ("P5header" ++ "a=a+a-I" ++ [toEnum 64,toEnum 1]))
      (packed [0,1,0,32])
    check "the successor of the maximum signed integer wraps to the minimum"
      (Just '+') (fmap last (packed [maxBound,minBound]))
    check "an isolated integer still charges its signed decimal payload"
      Nothing (prepared scope 31 (literal minBound))
    check "a minimum signed literal fits at its exact ordinary budget"
      True (case prepared scope 32 (literal minBound) of { Just _ -> True; Nothing -> False })
    let large = H.literal (replicate 4097 '葉')
    check "a constructor above the dictionary limit keeps its ordinary framing"
      (Just ("P3header" ++ field large)) (prepared scope (charge large) (T.SConstructor large))
  do
    let repeatedSite = T.SCallSite "s" (T.SourceSpan "pkg" "Mod" "file" 0 0 0 0) (T.SVar "s")
        appliedSites n = foldr (\_ rest -> T.SApp (T.SApp repeatedSite repeatedSite) rest) (T.SIntLit 0) [1..n]
        firstField = "d" ++ [toEnum 127] ++ "1:s" ++ "\0\0v\0"
        nextField = "d\0\0\0v\0"
    forM_ [1,3,22,43,129 :: Int] $ \n -> do
      let tree = appliedSites n
          bytes = "P5headeraa" ++ firstField ++ nextField ++
            concat (replicate (n-1) ("aa" ++ nextField ++ nextField)) ++ "="
          ordinaryCost = fromIntegral (164*n+12)
      check "cached source leaves followed by two applications keep exact preorder bytes across pages"
        (Just bytes) (prepared CrateGraph.WrittenOrigin ordinaryCost tree)
      check "the following application nodes retain their ordinary admission costs"
        Nothing (prepared CrateGraph.WrittenOrigin (ordinaryCost-1) tree)
  let spine depth = foldr (T.SApp . T.SConstructor) (T.SStringLit "尾:😀")
          (take depth (cycle ["節", "λ:𐐀"]))
      members body = [("表:λ", T.Nothing, body)]
  forM_ [63, 256, 513] $ \depth -> do
    let raw = members (T.SSourceDefinition (spine depth))
        lowered = members (spine depth)
        (a, b, retained) = CrateGraph.preparedSyntax T.Nothing raw lowered
        expected = map (H.unpack . CQ.list CQ.encodeMember) [raw, lowered]
    check "deep prepared members preserve recursive scalar framing" expected (map H.unpack [a,b])
    check "oversized prepared members stay outside the lowered cache" True
      (case retained of { T.Nothing -> True; T.Just _ -> False })
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
      let select expr schemes = names (CQ.requiredFileDataIn inventory [("value",T.Nothing,expr)] schemes)
          a = T.SAnnotation [] (T.SCon "Unused" [])
          leaf = T.SConstructor "MkA"
          alt = T.SAlternative (T.SNestedPattern "MkZ" [T.SConstructorPattern "MkB" []]) leaf
      check "file datatype roots include annotated binders and nested constructor patterns"
        ["A","B","Unused","Z"] (select (T.SLam "x" (T.Just a) (T.SCase (T.SVar "x") [alt])) [])
      check "repeated application constructors select each reachable layout once"
        ["A","B"] (select (T.SApp leaf (T.SApp (T.SConstructor "MkB") leaf)) [("p",T.XCon "External" [])])
      check "indexed wanted evidence selects its dictionary datatype"
        ["A","B","Unused"] (select (T.SWantedRefs "Unused" []) [("p",T.XCon "B" [])])
      check "ordinary term names cannot introduce file datatype roots"
        [] (select (T.SApp (T.SVar "MkZ") (T.SVar "Unused")) [])

-- Inspect the resolver's actual numeric edges before any graph is built.
-- Two aliases reach one declaration, an identically spelled import reaches
-- another, and locals do not contribute a crate edge.
resolverChecks = do
  let parsed (file,src) = right (Parser.parseModule (H.literal (file ++ ".emlf")) (H.literal src))
      right (T.Right value) = pure value
      right (T.Left msg) = error (H.unpack msg)
      mangle e = H.literal (H.unpack (Modules.owner e) ++ "." ++ H.unpack (Modules.spelling e))
  let constructor = Modules.Entity "A" "C" (Modules.Constructor "Tree")
      names = Modules.resolveNames (Modules.Names (M.singleton constructor "Tree.C"))
      env = Modules.interface [constructor]
      scopes = S.singleton "C"
      term = T.SApp (T.SConstructor "C") (T.SApp (T.SVar "C") (T.SConstructor "C"))
  resolved <- right (Modules.resolveBound names env scopes term)
  case resolved of
    R.App (R.Constructor first) (R.App (R.Local variable) (R.Constructor lastName)) ->
      check "constructor lookup preserves a same-spelled local in an application"
        ["Tree.C","C","Tree.C"] (map H.unpack [first,variable,lastName])
    _ -> error "incorrect constructor or local resolution"
  let project = Modules.resolveApplicationsWith id
        (\a b -> 10:a++b) (\f a b -> 20:f++a++b) (\_ _ b -> 30:b) T.Nothing
        (\t -> case t of T.SIntLit i -> T.Right [i]; _ -> T.Left "unknown leaf")
      wrapped = T.SCallSite "kept" (error "unused location")
  case project (T.SApp (T.SIntLit 1) (wrapped (T.SIntLit 2)))
               (T.SApp (T.SIntLit 3) (T.SIntLit 4)) of
    T.Right values -> check "application resolution honors custom unary, binary and site projections"
      [20,1,30,2,10,3,4] values
    T.Left why -> fail (H.unpack why)
  case project (T.SApp (T.SIntLit 1) (T.SVar "absent")) (error "unused right operand") of
    T.Left why -> check "binary resolution stops after its first argument fails" "unknown leaf" (H.unpack why)
    T.Right _ -> fail "unknown left argument resolved"
  let reject _ = T.Left "unresolved operand"
      seed = T.Just (M.singleton "C" (R.Global (V.fromInt 17)))
      wrap = T.SCallSite "mark" (error "undemanded call-site span")
  case Modules.resolveApplicationIn seed reject (wrap (T.SConstructor "C")) (T.SVar "missing") of
    T.Left reason -> check "application resolution preserves the first operand error" "unresolved operand" (H.unpack reason)
    _ -> error "unresolved application was accepted"
  case Modules.resolveApplicationIn seed reject (T.SVar "missing") (error "later operand was forced") of
    T.Left reason -> check "an unresolved function leaves its argument untouched" "unresolved operand" (H.unpack reason)
    _ -> error "unresolved function was accepted"
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
  headerLib <- parsed ("HeaderLib","module HeaderLib (value) where\nvalue :: Int\nvalue = 4\nprivate = 8\n")
  headerVia <- parsed ("HeaderVia","module HeaderVia (module L) where\nimport HeaderLib as L\n")
  headerMain <- parsed ("Main","module Main (main) where\nimport HeaderVia\nmain = value\n")
  let preparedInput count = H.v_concatStringList (replicate count "λ😀:0")
  forM_ [(0,4095),(250,4096),(251,16385)] $ \(names,blocks) -> do
    let ns = replicate names "λ"
        original = preparedInput blocks
        fields = W.VNode 421 [W.VText "prepared-declarations-1",Structure.toList W.VText ns,
          W.VText original,W.VText "",Structure.toList W.VText ["界"]]
    typed <- CrateGraph.hashPrepared ns original "" ["界"] >>= right
    wire <- CrateGraph.hashRebuiltValue fields >>= right
    check "large prepared text matches the admitted wire hash" (H.unpack wire) (H.unpack typed)
  let location = T.SourceSpan "pkg" "M" "file" 2 1 2 2
      site = T.SCallSite "x" location
      leaves = [T.SVar "x",T.SVar "x",T.SVar "x",T.SPrimitive T.PAddInt,T.SVar "addInt",T.SVar "x"]
      expression = foldr1 T.SApp (map site leaves)
      encodeSite budget = case CrateGraph.packedOrigin location 0 budget expression "loc" of
        T.Nothing -> Nothing
        T.Just text -> Just (H.unpack text)
      firstSite = "D" ++ [toEnum 127] ++ "1:x" ++ map toEnum [4,2,0,2]
      reuseSite = "d" ++ map toEnum [0,0,2]
      varX = "v" ++ [toEnum 0]
      fields = zipWith (++) (firstSite:repeat reuseSite)
        [varX,varX,varX,"p" ++ [toEnum 127] ++ "6:addInt","v" ++ [toEnum 1],varX]
      ordinaryCost = 5*25 + 6*(29+3+4*3) + 4*(10+3) + (11+8) + (10+8)
  check "a reused source location preserves variable and primitive wire tags"
    (Just ("P3loc" ++ concat (zipWith (++) (replicate 5 "a" ++ [""]) fields))) (encodeSite ordinaryCost)
  check "a combined source location still charges both ordinary nodes" Nothing (encodeSite (ordinaryCost-1))
  let pairs = [T.SApp (site (T.SVar "x")) (T.SIntLit n) | n <- [1..6]]
      withLiterals budget = case CrateGraph.packedOrigin location 0 budget (foldr1 T.SApp pairs) "loc" of
        T.Nothing -> Nothing
        T.Just value -> Just (H.unpack value)
      expectedPairs = zipWith (\prefix loc -> prefix ++ "a" ++ loc ++ varX ++ "+")
        (replicate 5 "a" ++ [""]) (firstSite : replicate 5 reuseSite)
      allCosts = 11*25 + 6*(29+3+4*3 + 10+3 + 12)
  check "a literal after an interned source leaf retains every preorder field"
    (Just ("P5loc" ++ concat expectedPairs)) (withLiterals allCosts)
  check "the final literal still needs its full ordinary byte charge" Nothing (withLiterals (allCosts-1))
  let capture (Crate.CompilationModules table units _) _ _ _ _ entry reach _ =
        (table,[(Crate.compilationName u,Crate.compilationExports u,Crate.compilationContents u) | u <- units],entry,reach)
      entities iface = [(H.unpack (Modules.owner e),H.unpack (Modules.spelling e),Modules.roleCode (Modules.role e)) |
                          e <- S.toList (Modules.visible iface)]
      reachable reach = [(H.unpack owner,map H.unpack (S.toList names)) | (owner,names) <- M.toList reach]
      bodyView m = [(H.unpack name,H.unpack (CQ.encodeExpression rhs)) | (name,_,rhs) <- Modules.sourceValues m]
      describe table (owner,exports,contents) = do
        iface <- right exports
        let symbols = Modules.bindingSymbols table
            binding (D.Bound slot _ rhs) = (H.unpack (D.symbolKey symbols slot),map V.toInt (R.references rhs))
        pure (H.unpack owner,entities iface,map binding (Modules.renamedBindings contents))
  forM_ [("",[primitive,dictSource]),("Main",[primitive,headerMain,headerVia,headerLib])] $ \(entry,inputs) -> do
    let spec = Crate.CrateSpec "headers" entry T.NoImplicitPrelude [] [] "" ""
    full <- right (Crate.prepareCrate spec [] inputs)
    (table,units,entryId,reach) <- right (Crate.prepareFileCrate capture spec [] inputs)
    let resolution = Crate.preparedResolution full
        modules = Modules.resolvedCrateModules resolution
        fullRows = [(Modules.moduleIdentity (Modules.resolvedSource m),Modules.resolvedExports T.NoImplicitPrelude m,
                     Modules.resolvedContents m) | m <- modules]
    want <- mapM (describe (Modules.resolvedCrateBindings resolution)) fullRows
    got <- mapM (describe table) units
    check "file compilation preserves defining exports, slots and references" want got
    let expressions tbl contents = let
          salt index = H.literal ("other slot " ++ show (V.toInt index))
          variant encode (D.Bound _ _ rhs) = H.unpack (CQ.encodeExpression (encode rhs))
          spell = D.symbolName (Modules.bindingSymbols tbl)
          in [(map (variant (R.namedExpr n)) (Modules.renamedBindings contents),
               map (variant (R.indexedExpr n)) (Modules.renamedBindings contents)) | n <- [spell, salt]]
    check "file application projections preserve declaration IDs, display policies and complete call sites"
      [expressions (Modules.resolvedCrateBindings resolution) c | (_,_,c) <- fullRows]
      [expressions table c | (_,_,c) <- units]
    let operands = [R.fileLeaf (R.Local "x"), R.fileLeaf (R.IntLit 5), R.Global (V.fromInt 8),
                    R.Lam "x" T.Nothing (R.Global (V.fromInt 13))]
        display i = H.literal ("slot " ++ show (V.toInt i))
        observe rhs = (map V.toInt (R.references rhs), H.unpack (CQ.encodeExpression (R.namedExpr display rhs)),
                       H.unpack (CQ.encodeExpression (R.indexedExpr display rhs)))
        triples apply = [observe (apply f a b) | f <- operands, a <- operands, b <- operands]
    check "saturated file applications preserve partial applications and reference order"
      (triples (\f a b -> R.fileApplication (R.fileApplication f a) b)) (triples R.fileApplicationPair)
    check "file compilation preserves entry ownership and transitive imports"
      (H.unpack (Crate.preparedEntry full),reachable (Crate.preparedReach full))
      (H.unpack (Crate.entryName entryId),reachable reach)
    forM_ inputs $ \input -> do
      let owner = Modules.moduleIdentity input
          originals = [bodyView source | m <- modules, let source = Modules.resolvedSource m,
                         Modules.moduleIdentity source == owner]
      check "each supplied module retains its original value expressions" [bodyView input] originals
    unless (H.unpack entry == "") $ do
      check "re-export retains its defining module" [("HeaderLib","value",Modules.roleCode Modules.Value)]
        (concat [es | ("HeaderVia",es,_) <- got])
      check "entry includes its transitive import" True
        ("HeaderLib" `elem` concat [ns | ("Main",ns) <- reachable reach])
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
  let display i = H.literal ("hint-" ++ show (V.toInt i))
      annotated = R.CallSite "lookup" (T.SourceSpan "pkg" "M" "source.hs" 2 3 2 9)
        (R.Equations [([R.OverloadedStringPattern (T.ScalarString "α") method external],
                       R.App (R.Global own) (R.Local "x"))])
  case R.indexedExpr display annotated of
    T.SCallSite "lookup" _ (T.SEquations [([T.SIndexedStringPattern _ (T.DeclRef eq eqName)
          (T.DeclRef str strName)],T.SApp (T.SGlobal slot slotName) (T.SVar "x"))]) -> do
      check "projected pattern and value slots preserve their identities"
        (map V.toInt [method,external,own]) (map V.toInt [eq,str,slot])
      check "projected display names come from the supplied name function"
        (map (H.unpack . display) [method,external,own]) (map H.unpack [eqName,strName,slotName])
    _ -> fail "resolved nested expression lost its source or overloaded pattern"
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
  do
    let fileRefs expression = [(case r of
          T.LexicalRef n -> (False,0,H.unpack n)
          T.DeclRef i n -> (True,V.toInt i,H.unpack n)) | r <- expression]
        lexicalGroup = T.SLet "+" (T.SVar "$MLF.Infix.+") (T.SApp (T.SVar "$MLF.Infix.+")
          (T.SDeclScope [own] (T.SLet "same" (T.SGlobal own "rhs")
            (T.SApp (T.SGlobal own "hidden") (T.SApp (T.SVar "same") (T.SGlobal foreignId "+"))))))
    forM_ [False,True] $ \inventory -> do
      check "parsed lexical observation preserves every raw slot, hint and occurrence in order"
        (fileRefs (D.valueOccurrences True inventory lexicalGroup))
        (fileRefs (D.fileValueOccurrences inventory lexicalGroup))
  let copied = T.SDeclScope [own] (T.SLet "same" (T.SGlobal own "outer") (T.SApp
        (T.SGlobal own "inner") (T.SApp (T.SVar "same") (T.SGlobal foreignId "same"))))
  check "copied helper hides its own slot only in its body" [1,0] (map V.toInt (D.expressionGlobalIds copied))
  check "scope with typed binder leaves a lexical reference free" ["same"] (map H.unpack (D.expressionNamedReads copied))
  check "prepared syntax also inventories the owned slot and enclosed occurrence"
    [1,1,1,0] [V.toInt i | T.DeclRef i _ <- D.querySyntaxRefs copied]
  do
    let a = V.fromInt 9
        b = V.fromInt 3
        candidate = D.occurrenceGlobalIds (D.fileValueOccurrences False)
        mk i n rhs = (i,(n,T.Nothing,rhs))
        body = T.SDeclScope [a] (T.SLet "same" (T.SGlobal b "same")
          (T.SApp (T.SGlobal a "hidden") (T.SWantedRefs "D"
            [(T.GivenEvidence,T.LexicalRef "same"),(T.GivenEvidence,T.DeclRef b "again")])))
        rows = [mk a "b" body,mk b "a" (T.SLet "b" (T.SConstructor "K") (T.SGlobal a "b"))]
        components result = case result of
          T.Left why -> error (H.unpack why)
          T.Right parts -> [[(V.toInt i,cyclic) | (i,cyclic) <- part] | part <- parts]
    check "file SCC occurrence projection drops lexical and bound slots and retains repeated candidates"
      [3,3] (map V.toInt (candidate body))
    check "file SCC groups use declaration identities through same-spelled lexical bindings"
      [[(3,False),(9,False)]] (components (Surface.indexedMemberComponentsWith candidate rows))
    check "independent ordered SCC reconstruction on file and ordinary inputs"
      (components (Surface.indexedMemberComponents rows)) (components (Surface.indexedMemberComponentsWith candidate rows))
  let annotation = T.SAnnotation [] (T.SQualified [T.SPredicate "C" [T.SCon "Inner" []]] (T.SCon "Body" []))
      bodyWithType = T.SChecked (T.SCon "Head" []) (T.SSignature (T.SApp (T.SGlobal own "outer") (T.SConstructor "K")) annotation)
      observed = D.observeSyntax True True bodyWithType
  check "checked and annotated terms retain references and ordered type, constructor and class fields"
    ([V.toInt own],["Head","Inner","Body"],["K"],["C"])
    ([V.toInt i | T.DeclRef i _ <- D.valueOccurrences True True bodyWithType],
     map H.unpack (D.typeNames observed),map H.unpack (D.constructorNames observed),map H.unpack (D.classNames observed))
  let brokenType = T.SAnnotation [] (T.SArrow (error "annotation domain") (error "annotation codomain"))
      incomplete = T.SApp (T.SSignature (T.SVar "x") brokenType) (error "following expression")
      firstFault refs = do
        outcome <- try (evaluate (null refs)) :: IO (Either ErrorCall Bool)
        case outcome of
          Left err -> pure (takeWhile (/= '\n') (displayException err))
          Right _ -> fail "incomplete application produced a reference list"
  expectedFault <- firstFault (D.valueRefs (D.observeSyntax False False incomplete))
  collectedFault <- firstFault (D.valueOccurrences False False incomplete)
  check "observing an incomplete application preserves the first source diagnostic"
    expectedFault collectedFault
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

signedLocalChecks = do
  let a = T.STVar "a"; b = T.STVar "b"; c = T.STVar "c"
      ar = T.SArrow; lam ns rhs = foldr (\n -> T.SLam n T.Nothing) rhs ns
      body = lam ["f","g","x"] (T.SApp (T.SVar "f") (T.SApp (T.SVar "g") (T.SVar "x")))
      arrow = ar (ar b c) (ar (ar a b) (ar a c))
      signature ns = foldr (\n -> T.SForall T.Flexible n T.SBottom) arrow ns
      members ty term = [(V.fromInt 23, ("entry", T.Just (T.SAnnotation [] ty), T.SChecked ty term))]
      checked (T.Right v) = pure v
      checked (T.Left e) = fail (H.unpack e)
      int = T.XCon "Int" []
      plus offset = let n = T.XName 200 "n" in T.XAbs n int
                      (T.XApp (T.XApp (T.XPrimitive T.PAddInt []) (T.XVarTerm n)) (T.XIntTerm offset))
  forM_ [["a","b","c"],["c","b","a"]] $ \ns -> do
    let m = members (signature ns) body
    (extern, lowered) <- checked (Inference.prepareIndexedGroup [] [] m)
    prior <- checked (Inference.finishOpenGroup extern (map snd m) lowered)
    direct <- checked (Inference.signedLocalGroup [] m lowered)
    routed <- checked (Inference.compileOpenGroupIndexed "case" [] [] m)
    check "quantified local scheme uses direct path" (H.unpack (Open.fingerprint direct)) (H.unpack (Open.fingerprint routed))
    let [(_, original)] = Open.bindings prior
    forM_ [routed,prior] $ \fragment -> case Open.body fragment of
      T.XLet name impl _ -> do
        let [(_,actual)] = Open.bindings fragment
            use = foldl (\term t -> T.XTypeApp term (X.typeApplication t)) (T.XVarTerm name) [int,int,int]
            program = T.XLet name impl (foldl T.XApp use [plus 2, plus 3, T.XIntTerm 7])
        check "quantified local scheme preserves canonical binder order" True (XT.alphaEq original actual)
        _ <- checked (Independent.checkClosed program)
        value <- checked (Runtime.integer (Runtime.evaluate (Open.dataEnvironment (Open.context fragment)) (Runtime.REnv M.empty) (X.erase program)))
        check "quantified local composition" 12 value
      _ -> fail "expected nonrecursive local function"
  let unused = members (T.SForall T.Flexible "unused" T.SBottom (signature ["a","b","c"])) body
  (ctx, lowered) <- checked (Inference.prepareIndexedGroup [] [] unused)
  case Inference.signedLocalGroup [] unused lowered of
    T.Left _ -> pure ()
    _ -> fail "unused explicit quantifier took the direct path"
  prior <- checked (Inference.finishOpenGroup ctx (map snd unused) lowered)
  current <- checked (Inference.compileOpenGroupIndexed "case" [] [] unused)
  let [(_,t)] = Open.bindings prior; [(_,u)] = Open.bindings current
  check "unused local quantifier falls back to the graph scheme" True (XT.alphaEq t u)

-- Compare the routed program with ordinary graph inference. The outer
-- argument and the selected field share a spelling, and the other field fails
-- if evaluation demands it.
signedDataChecks = do
  let a = T.STVar "a"
      pair = T.SCon "Pair" [a]
      ds = [T.DataDecl "Pair" ["a"] [T.ConstructorDecl "P" [T.Parameter "a", T.Parameter "a"]]]
      rows from to rhs =
        let sig = T.SForall T.Flexible "a" T.SBottom (T.SArrow from to)
        in [(V.fromInt 27, ("f", T.Just (T.SAnnotation [] sig), T.SChecked sig (T.SLam "x" T.Nothing rhs)))]
      make = T.SApp (T.SApp (T.SConstructor "P") (T.SVar "x")) (T.SVar "x")
      field first second = T.SCase (T.SVar "x")
        [T.SAlternative (T.SConstructorPattern "P" [T.Just first, T.Just second]) (T.SVar "x")]
      int = T.XCon "Int" []
      panicField = T.XApp (T.XPrimitive T.PPanic [int]) (T.XStringTerm "unused field")
      applied value arg = T.XApp (T.XTypeApp value (X.typeApplication int)) arg
      packed = T.XApp (T.XApp (T.XConstructor "P" [int]) panicField) (T.XIntTerm 37)
      checked (T.Right value) = pure value
      checked (T.Left message) = fail (H.unpack message)
  forM_ [(rows a pair make, False), (rows pair a (field "ignored" "x"), True)] $ \(members, projection) -> do
    (externals, lowered) <- checked (Inference.prepareIndexedGroup [] ds members)
    direct <- checked (Inference.signedDataGroup [] members lowered)
    routed <- checked (Inference.compileOpenGroupIndexed "scope" [] ds members)
    ordinary <- checked (Inference.finishOpenGroup externals (map snd members) lowered)
    check "signed data route" (H.unpack (Open.fingerprint direct)) (H.unpack (Open.fingerprint routed))
    let [(_, referenceTy)] = Open.bindings ordinary
    forM_ [routed, ordinary] $ \fragment -> do
      let [(owner, ty)] = Open.bindings fragment
          env = Open.context fragment
      check "signed data export" True (H.unpack (X.nameHint owner) == "f" && XT.alphaEq ty referenceTy)
      _ <- checked (Independent.checkClosed (Open.closedTerm fragment))
      case Open.body fragment of
        T.XLet n impl _ -> do
          let use = applied (T.XVarTerm n) (if projection then packed else panicField)
              term = T.XWithData (Open.declarations env) (T.XLet n impl use)
          _ <- checked (Independent.checkClosed term)
          result <- checked (Runtime.evaluate (Open.dataEnvironment env) (Runtime.REnv M.empty) (X.erase term))
          case (projection, result) of
            (True, Runtime.RInteger value) -> check "select the shadowing field" 37 value
            (False, Runtime.RConstructor name values) -> check "lazy signed constructor" ("P", 2) (H.unpack name, length values)
            _ -> fail "unexpected signed data result"
        _ -> fail "expected a nonrecursive signed data binding"
  -- The graph solver drops an unused quantifier, including shadowed ones.
  -- Preserve the exact exported scheme when this declaration falls back.
  let two = T.SForall T.Flexible "a" T.SBottom
            (T.SForall T.Flexible "unused" T.SBottom (T.SArrow a pair))
      unused = [(V.fromInt 28, ("f", T.Just (T.SAnnotation [] two), T.SChecked two (T.SLam "x" T.Nothing make)))]
  (scope, core) <- checked (Inference.prepareIndexedGroup [] ds unused)
  case Inference.signedDataGroup [] unused core of
    T.Left _ -> pure ()
    T.Right _ -> fail "direct route retained an unused quantifier"
  viaGraph <- checked (Inference.finishOpenGroup scope (map snd unused) core)
  viaPublic <- checked (Inference.compileOpenGroupIndexed "scope" [] ds unused)
  let [(_, expected)] = Open.bindings viaGraph
      [(_, actual)] = Open.bindings viaPublic
  check "unused signed quantifier follows source inference" True (XT.alphaEq expected actual)
  let duplicates = rows pair a (field "x" "x")
  (externals, lowered) <- checked (Inference.prepareIndexedGroup [] ds duplicates)
  case (Inference.compileOpenGroupIndexed "scope" [] ds duplicates,
        Inference.finishOpenGroup externals (map snd duplicates) lowered) of
    (T.Left actual, T.Left reference) -> check "duplicate signed field diagnostic" (H.unpack reference) (H.unpack actual)
    _ -> fail "duplicate signed fields must fail"

-- A signed first-order application may use bare constructors only when
-- the full datatype environment checks it. An omitted polymorphic argument
-- and an invalid child take the ordinary inference and diagnostic paths.
signedConstructorChecks = do
  let int = T.SCon "Int" []
      tree = T.SCon "Tree" []
      box = T.SCon "Box" [int]
      ds = [T.DataDecl "Tree" [] [T.ConstructorDecl "Tip" [T.Applied "Int" []],
                                   T.ConstructorDecl "Fork" [T.Applied "Tree" [], T.Applied "Tree" []]],
            T.DataDecl "Box" ["a"] [T.ConstructorDecl "Box" [T.Parameter "a"]]]
      construct name fields = foldl T.SApp (T.SConstructor name) fields
      tip = construct "Tip" [T.SVar "x"]
      fork = construct "Fork" [tip, tip]
      rows result rhs = let sig = T.SArrow int result
                        in [(V.fromInt 9, ("f", T.Just (T.SAnnotation [] sig), T.SChecked sig (T.SLam "x" T.Nothing rhs)))]
      checked (T.Right x) = pure x
      checked (T.Left why) = fail (H.unpack why)
      accepts result rhs = do
        let members = rows result rhs
        actual <- checked (Inference.compileOpenGroupIndexed "test" [] ds members)
        prior <- checked (Inference.compileElaboratedGroup [] ds members)
        let [(_, ty)] = Open.bindings actual
            [(_, original)] = Open.bindings prior
        check "signed constructor export" True (XT.alphaEq ty original)
        _ <- checked (Independent.checkClosed (Open.closedTerm actual))
        pure ()
  dataEnv <- checked (Data.validateDeclarations ds)
  let xt = T.XCon "Int" []
      leaf = T.XApp (T.XConstructor "Tip" []) (T.XIntTerm 4)
      branch x y = T.XApp (T.XApp (T.XConstructor "Fork" []) x) y
      resultType (T.Left e) = Left (H.unpack e)
      resultType (T.Right ty) = Right (H.unpack (Pretty.prettyType ty))
  forM_ [foldr branch leaf (replicate 129 leaf),branch leaf (T.XIntTerm 4),
         T.XConstructor "Tip" [xt],T.XConstructor "Box" [],T.XConstructor "Box" [xt],
         T.XApp (T.XConstructor "missing" []) (T.XConstructor "Box" [])] $ \expr ->
    check "constructor instantiation agrees with independent xMLF checking"
      (resultType (Independent.inferIn dataEnv XCheck.emptyEnv expr))
      (resultType (XCheck.inferIn dataEnv XCheck.emptyEnv expr))
  let [a,b,c] = map T.XTyVar [60,61,62]
      name = T.XName 8 "poly"
      ty = foldr (\v body -> T.XForall v T.XBot body)
        (T.XArrow (T.XVar a) (T.XArrow (T.XVar b) (T.XVar c))) [a,b,c]
      env = T.XEnv M.empty (M.singleton name ty)
      use p = T.XTypeApp (T.XVarTerm name) p
      apply t = T.XThen (T.XInner (T.XBottom t)) T.XElim
      args = [xt,T.XCon "Bool" [],T.XCon "Tree" [],T.XCon "Box" [],T.XCon "absent" []]
  forM_ [(x,y,z) | x<-args,y<-args,z<-args] $ \(x,y,z) ->
    forM_ [foldl1 T.XThen,foldr1 T.XThen] $ \group -> do
      let term = use (group (map apply [x,y,z]))
      check "successive type arguments retain checked types and the first diagnostic"
        (resultType (Independent.inferIn dataEnv env term)) (resultType (XCheck.inferIn dataEnv env term))
  let openConstructor = T.XCon "absent" []
  check "an unregistered nullary type constructor has kind star" True
    (case resultType (XCheck.inferIn dataEnv env (use (apply openConstructor))) of
       Right _ -> True
       Left _ -> False)
  let failedPrefix = T.XThen (apply xt) (apply (T.XCon "IO" []))
      wanted = resultType (Independent.inferIn dataEnv env (use failedPrefix))
  check "malformed prefix is rejected" True (case wanted of Left _ -> True; Right _ -> False)
  check "failed instantiation leaves its suffix undemanded" wanted
    (resultType (XCheck.inferIn dataEnv env (use (T.XThen failedPrefix (error "forced proof suffix")))))

  forM_ [(tree, fork), (T.SArrow int tree, T.SConstructor "Tip"),
         (T.SArrow tree tree, construct "Fork" [tip])] $ \(result, rhs) -> do
    direct <- checked (Inference.signedApplicationGroup [] ds (rows result rhs))
    _ <- checked (Independent.checkClosed (Open.closedTerm direct))
    accepts result rhs
  let polymorphic = construct "Box" [T.SVar "x"]
  case Inference.signedApplicationGroup [] ds (rows box polymorphic) of
    T.Left _ -> accepts box polymorphic
    _ -> fail "a polymorphic constructor needs its ordinary type argument"
  let bad = rows tree (construct "Fork" [tip, T.SBoolLit True])
  case (Inference.compileOpenGroupIndexed "test" [] ds bad, Inference.compileElaboratedGroup [] ds bad) of
    (T.Left a, T.Left b) -> check "constructor operand diagnostic" (H.unpack b) (H.unpack a)
    _ -> fail "invalid signed constructor operand admitted"

-- The checked fold uses the field order in the function's body. A field
-- absent from that body may fail if demanded, including on a nested branch.
knownConstructorFoldChecks = do
  let n i = T.XName i "same spelling"
      v i = T.XEVar (n i)
      app = T.XEApp
      prim op = foldl app (T.XEPrimitive op)
      con tag = foldl app (T.XEConstructor tag)
      poison message = prim T.PPanic [T.XEString message]
      leaf x = con "Tip" [poison "ignored", x]
      pair a b = con "Fork" [a, b]
      present = T.Just . n
      arm tag fields = T.XErasedAlternative (T.XConstructorPattern tag fields)
      base = arm "Tip" [T.Nothing, present 4] (v 4)
      step left right = arm "Fork" [present 5, present 6]
        (prim T.PSubInt [app (v 1) (v left), app (v 1) (v right)])
      rule branches = T.XEAbs (n 2) (T.XECase (v 2) branches)
      function = rule [base, step 6 5]
      use tree = T.XELetRec [(n 1, function)] (app (v 1) tree)
      int = T.Applied "Int" []
      tree = T.Applied "Tree" []
      ds = [T.DataDecl "Tree" [] [T.ConstructorDecl "Tip" [int, int], T.ConstructorDecl "Fork" [tree, tree]]]
  env <- case Data.validateDeclarations ds of
    T.Right ok -> pure ok
    T.Left why -> fail (H.unpack why)
  let run expr = case Runtime.integer (Runtime.evaluate env (Runtime.REnv M.empty) expr) of
        T.Left why -> Left (H.unpack why)
        T.Right value -> Right value
  forM_ [(pair (leaf (T.XEInt minBound)) (leaf (T.XEInt 9)), Right (9 - minBound)),
         (pair (leaf (poison "left")) (leaf (poison "right")), Left "right")] $ \(subject, expected) ->
    forM_ [use subject, Optimize.optimizeChecked (use subject)] $ \term -> check "constructor fold demand" expected (run term)
  let identity i = app (T.XEAbs (n i) (v i))
      consumer alias = identity 30 (T.XEAbs (n 2)
        (T.XELet (n alias) (identity 31 (v 2)) (T.XECase (v alias) [base, step 6 5])))
      subject = pair (leaf (v 18)) (leaf (v 19))
      bind f body = T.XELetRec [(n 1, f)] body
      normalized = Optimize.foldScopedFields M.empty
      apply = app (v 1) subject
  check "fold the checked tree before copying its declaration"
    True (X.equalErased (normalized (bind (consumer 3) apply))
      (bind (consumer 3) (prim T.PSubInt [v 19, v 18])))
  let shadowed = bind (consumer 3) (T.XEAbs (n 1) apply)
  check "early fold respects a rebound function" True (X.equalErased shadowed (normalized shadowed))
  case Optimize.constructorFold (n 1) (consumer 1) of
    T.Nothing -> pure ()
    _ -> fail "an argument alias shadowed the recursive name"
  case Optimize.constructorFold (n 1) function of
    T.Just rules -> do
      let subject = pair (leaf (v 18)) (leaf (v 19))
      case Optimize.foldKnownConstructor rules subject of
        T.Just reduced -> check "resolved fold operands" True (X.equalErased (prim T.PSubInt [v 19, v 18]) reduced)
        _ -> fail "statically known fold was missed"
      case Optimize.foldKnownConstructor rules (pair (v 8) (leaf (v 19))) of
        T.Nothing -> pure ()
        _ -> fail "unspecified subtree collapsed"
    _ -> fail "missing recursive constructor fold"
  do
    let fn i=T.XName i "operator"
        ref i=T.XEVar (fn i)
        pair h t=T.XEApp (T.XEApp (ref 22) (ref h)) t
        table=M.fromList Optimize.compareName [(fn 22,Optimize.ComposesFunctions),
          (fn 30,Optimize.TranslatesBy maxBound),(fn 31,Optimize.TranslatesBy 1)]
        chain=pair 30 (pair 31 (ref 31))
        result=T.XEApp (T.XEApp (T.XEPrimitive T.PAddInt) (ref 45)) (T.XEInt (minBound+1))
        (optimized,seed)=Optimize.runFresh (Optimize.constructorApplications table (T.XEApp chain (ref 45))) 78
    check "verified composition chain preserves its binder and wrapping offset"
      (True,78) (X.equalErased result optimized,seed)
    check "unknown callback keeps ordinary composition semantics" True
      (case Optimize.translationChain table (pair 99 (ref 31)) of T.Just T.Nothing->True;_->False)
  let select count index values = Optimize.foldKnownConstructor
        (M.singleton "Box" (count,Optimize.ReturnField index))
        (foldl T.XEApp (T.XEConstructor "Box") values)
  forM_ [0..4] $ \size -> do
    let values = take size (map T.XEInt [10..])
    forM_ [-1..size] $ \index -> case select (fromIntegral size) (fromIntegral index) values of
      T.Just (T.XEInt value) -> check "constructor field index follows source order"
        True (index >= 0 && index < size && value == fromIntegral (index+10))
      T.Nothing -> check "out-of-range constructor field" True (index < 0 || index >= size)
      _ -> fail "unexpected constructor field"
    case select (fromIntegral size+1) (error "unused index") (replicate size (error "unused field")) of
      T.Nothing -> pure ()
      _ -> fail "wrong constructor arity accepted"
  let hiddenType = error "erasure evaluated a type annotation"
      hidden value = T.XTypeApp (T.XWithData (error "erasure evaluated declarations") value) hiddenType
      ttag name = foldl (\f a -> hidden (T.XApp (hidden f) a)) (T.XConstructor name [])
      keep a = ttag "One" [error "unused constructor field",a]
      foldFields = M.fromList H.v_compareString
        [("One",(2,Optimize.ReturnField 1)),("Both",(2,Optimize.CombineFields T.PSubInt 1 0))]
      tree = ttag "Both" [keep (hidden (T.XIntTerm 17)),keep (T.XIntTerm 39)]
      typedResult = Optimize.foldTypedConstructor foldFields tree
      original = Optimize.foldKnownConstructor foldFields (X.erase tree)
  case (original,typedResult) of
    (T.Just old,T.Just new) -> check "typed constructor fold keeps selected fields and skips type evidence"
      True (X.equalErased old new && X.equalErased new (prim T.PSubInt [T.XEInt 39,T.XEInt 17]))
    _ -> fail "typed constructor field was lost"
  let literalTags = M.fromList H.v_compareString [("End",(40,0)),("Cell",(41,2)),("Row",(42,2))]
      make name fields = foldl T.XEApp (T.XEConstructor name) fields
      row i = make "Row" [T.XEInt i, T.XEInt (i*i+3)]
      cell i rest = make "Cell" [row i, rest]
  forM_ [2,127,128,129,257] $ \size -> do
    let term = foldr cell (T.XEConstructor "End") [1..size]
    case Codegen.generate literalTags term of
      T.Left err -> fail (H.unpack err)
      T.Right (_,chunks) -> do
        let bodies = lines (unlines (map H.unpack chunks))
            prefixes = filter (isInfixOf "define private ptr @mlf.constructor.prefix.") bodies
        check "closed constructor chunks are bounded and pass their tail explicitly"
          (fromIntegral size `div` 128) (length prefixes)
  let columns size = foldr cell (T.XEConstructor "End") [1..size]
      expectedWords size = concat [[2*i+1, 2*(i*i+3)+1] | i <- reverse [1..size]]
  forM_ [7,8,31] $ \size -> case Codegen.generate literalTags (columns size) of
    T.Left err -> fail (H.unpack err)
    T.Right (_,chunks) -> do
      let linesIR = lines (unlines (map H.unpack chunks))
          tables = filter (isInfixOf " = private unnamed_addr constant [") linesIR
          wordsIR = "[" ++ concat (zipWith (++) ("" : repeat ", ")
                    ["i64 " ++ show word | word <- expectedWords size]) ++ "], align 8"
      check "homogeneous rows use their exact tagged words in construction order"
        (if size < 8 then 0 else 1) (length (filter (isInfixOf wordsIR) tables))
      check "the binary row loop is emitted only when used" (size >= 8)
        (any (isInfixOf "define private ptr @mlf.construct.rows.2(") linesIR)
  let arithmetic i rest = make "Cell" [make "Row" [T.XEInt i,T.XEInt (3*i+1)],rest]
  forM_ [7,8,31,129,513] $ \size -> do
    let term = foldr arithmetic (T.XEConstructor "End") [1..size]
    case Codegen.generate literalTags term of
      T.Left err -> fail (H.unpack err)
      T.Right (_,chunks) -> do
        let ir = unlines (map H.unpack chunks)
            args = "call ptr @mlf.construct.strides.2(i64 " ++ show (2*size+1) ++
              ", i64 " ++ show (6*size+3) ++ ", i64 -2, i64 -6, i64 " ++ show size ++
              ", i64 42, i64 41, ptr "
        check "arithmetic rows retain tagged tail-to-head strides across chunks"
          (size >= 8) (args `isInfixOf` ir)
        check "an arithmetic run uses no table storage" False (" = private unnamed_addr constant [" `isInfixOf` ir)
  let hi = 4611686018427387903
      lo = -4611686018427387904
      first = Codegen.LiteralRow 42 [2*(hi-1)+1, 1]
      more = foldr (\n rest -> make "Cell" [make "Row" [T.XEInt n,T.XEInt 0],rest])
        (T.XEConstructor "End") ([hi] ++ [lo..lo+5])
  case Codegen.rowProgression literalTags "Cell" first more of
    T.Just (Codegen.RowProgression count last steps (T.XEConstructor end)) ->
      check "tagged progressions wrap between the signed compact Int boundaries"
        (8, [2*(lo+5)+1,1], [-2,0], "End") (count,last,steps,H.unpack end)
    _ -> fail "wrapping constructor progression"
  let wordView term = case Codegen.literalRow literalTags term of
        T.Just (Codegen.LiteralRow tag fields) -> Just (tag, fields)
        T.Nothing -> Nothing
  check "mixed compact tags keep their immediate pointer bits" (Just (42,[6,324]))
    (wordView (make "Row" [T.XEBool True,T.XEConstructor "End"]))
  check "signed compact boundaries encode exactly" (Just (42,[minBound+1,maxBound]))
    (wordView (make "Row" [T.XEInt (-4611686018427387904),T.XEInt 4611686018427387903]))
  let permitted = Codegen.literalConstructorField literalTags
  forM_ [(True,row 1),(True,make "Row" [T.XEConstructor "End",T.XEBool False]),
         (False,make "Row" [T.XEInt maxBound,T.XEInt 0]),(False,make "Row" [T.XEInt 1]),
         (False,make "Unknown" [T.XEInt 1,T.XEInt 2]),
         (False,make "Row" [v 17, T.XEInt 2])] $ \(expected,term) ->
    check "only closed compact constructor fields can be postponed" expected (permitted term)
  forM_ [0..4::Int] $ \arity -> do
    let example = foldl T.XEApp (T.XEConstructor "Box") (replicate arity (T.XEInt 3))
        table = M.singleton "Box" (31,fromIntegral arity)
    case Codegen.generate table example of
      T.Left message -> fail (H.unpack message)
      T.Right (_,chunks) -> do
        let ir = unlines (map H.unpack chunks)
            defined symbol = ("define private ptr @" ++ symbol ++ "(") `isInfixOf` ir
        forM_ [("mlf.allocate.constructor",arity > 0),("mlf.construct.1",arity == 1),
               ("mlf.construct.2",arity == 2),("mlf.construct.wide",arity > 2)] $ \(symbol,needed) ->
          check ("LLVM emits " ++ symbol ++ " for its constructor arity") needed (defined symbol)
  let evidence x = T.XWithData (error "unused data") (T.XTypeApp x (error "unused computation"))
      tags h args = foldl (\f a -> evidence (T.XApp f a)) (evidence h) args
      select n at term = Optimize.typedConstructorFields
        (\_ count field -> if count == n then field at else T.Nothing) term
  forM_ [0..5] $ \n -> do
    let args = [T.XIntTerm (i+10) | i <- [0..n-1]]
        term = tags (T.XConstructor "Wrapped" (error "unused type arguments")) args
    forM_ [-1..n] $ \i -> case select n i term of
      T.Just (T.XIntTerm v) -> check "typed constructor fields stay in application order"
        True (i >= 0 && i < n && v == i+10)
      T.Nothing -> check "typed constructor field bounds" True (i < 0 || i >= n)
      _ -> fail "unexpected typed field"
  let lazyPair = tags (T.XConstructor "Pair" []) [error "unused first field",T.XIntTerm 72]
  case select 2 1 lazyPair of
    T.Just (T.XIntTerm v) -> check "typed binary field leaves its neighbor lazy" 72 v
    _ -> fail "missing second typed field"
  let sumRules = M.fromList H.v_compareString
        [("Tip",(2,Optimize.ReturnField 1)),("Fork",(2,Optimize.CombineFields T.PAddInt 0 1))]
      affine coefficient amount = prim T.PAddInt [prim T.PMulInt [v 19,T.XEInt coefficient],T.XEInt amount]
      subjectAt a b = pair (leaf (affine a 13)) (pair (leaf (affine b (-7))) (leaf (v 19)))
  forM_ [(0,0),(2,-3),(maxBound,1),(minBound,-1)] $ \(a,b) -> do
    let scale = a+b+1
        scaled = if scale == 1 then v 19 else prim T.PMulInt [v 19,T.XEInt scale]
    case Optimize.foldKnownConstructor sumRules (subjectAt a b) of
      T.Just value -> check "wrapped affine constructor fold retains the input binder and exact offset"
        True (X.equalErased value (prim T.PAddInt [scaled,T.XEInt 6]))
      _ -> fail "known constructor fold was missed"
  case Optimize.constructorFold (n 1) (rule [base, step 6 6]) of
    T.Nothing -> pure ()
    _ -> fail "duplicate recursive field in constructor fold"

-- A checked open fragment with no composable proofs can retain its
-- original body up to the absolute wire depth and work limits.
openGeometryChecks = do
  let depth = W.maxDepth W.defaultLimits
      wrap count t = foldr (\_ child -> W.VNode 8 [child]) t [1..count]
      normal = W.VInt 0
      proof = W.VNode 58 [W.VNode 50 [], W.VNode 58 [W.VNode 50 [], W.VNode 50 []]]
      observe = fmapHost . Source.finalTreeGeometry depth False
      fmapHost T.Nothing = []
      fmapHost (T.Just x) = [x]
  check "deep proof-free open body" [False] (observe (wrap 1024 normal))
  check "nested proof below a deep constructor" [True] (observe (wrap 1024 proof))
  check "final geometry honors the wire depth limit" [] (observe (wrap depth normal))
  let shared glyph = wrap 300 (W.VNode 8 (replicate 40 (W.VText (H.literal (replicate 65536 glyph)))))
  check "deep open bodies charge every UTF-8 occurrence" [[False], []]
    (map (observe . shared) ['x', '😀'])
  let charge text remaining = if H.unpack text == "reject" then T.Nothing else T.Just (remaining-1)
      cursor frames n w = fmapHost (Source.finalGeometryUsing False False charge 12 frames n w False)
      frames = [(1,False,[W.VInt 7,W.VNode 4 [W.VText "ok",W.VNode 58 []],W.VInt 1]),
                (3,True,[W.VNode 58 []])]
  check "geometry resumes the remaining root and charges every sibling"
    [[],[True],[]] [cursor frames 5 10,cursor frames 6 7,cursor frames 6 6]
  check "a rejected child precedes its unevaluated sibling list" []
    (cursor [(1,False,W.VNode 4 [W.VText "reject"] : error "premature sibling demand")] 32 32)
  let proofArgument text = T.XThen (T.XInner (T.XBottom (T.XCon text []))) T.XElim
      headTerm = T.XVarTerm (T.XName (error "geometry forced a binder ID") "f")
      application proof = T.XTypeApp headTerm proof
      payment text rest = let size = Prim.stringUtf8Length text in
        if size > rest then T.Nothing else T.Just (rest - size)
      admission term depth nodes work = case Source.finalGeometryWalk True False payment depth
        (Source.GeometryTerm 1 term (Source.GeometryRoots [])) nodes work False of
          T.Nothing -> Nothing
          T.Just changed -> Just changed
      leafProof = proofArgument "λ😀"
  check "ground geometry counts its UTF-8 name and complete argument-list node"
    [Just False,Nothing,Nothing,Nothing]
    [admission (application leafProof) d n w | (d,n,w) <- [(6,12,19),(5,12,19),(6,11,19),(6,12,18)]]
  check "nested ground proof compositions preserve their original grouping flag" (Just True)
    (admission (application (T.XThen leafProof leafProof)) 7 20 33)
  let incomplete = T.XThen (T.XInner (T.XBottom (T.XCon "λ😀" (error "geometry forced type arguments"))))
        (error "geometry forced the right proof")
  check "a UTF-8 budget failure precedes both type arguments and the right proof" Nothing
    (admission (application incomplete) 6 100 14)
  let cursorHint = T.XVarTerm (T.XName (error "cursor forced binding ID") "λ😀")
      cursorPay expected _ available = if available==expected then T.Just available else T.Nothing
      cursorTerm frame budget work depth pay = case Source.finalGeometryWalk True False pay depth
          frame budget work False of { T.Just b -> Just b; T.Nothing -> Nothing }
      done = Source.GeometryRoots []
      varFrame = Source.GeometryTerm 1 cursorHint done
      guardedProof = T.XThen (T.XInner (T.XBottom (T.XCon "other" [])))
          (error "cursor forced a proof after exhausting its work")
  check "checked variable charges its name at the original remaining work"
    [Just False,Nothing,Nothing,Nothing]
    [cursorTerm varFrame 4 13 3 (cursorPay 9),
     cursorTerm varFrame 4 13 3 (cursorPay 8),
     cursorTerm varFrame 3 13 3 (cursorPay 9),
     cursorTerm varFrame 4 13 2 (cursorPay 9)]
  check "ground proof consumes its empty type-list node before the right proof" Nothing
    (cursorTerm (Source.GeometryProof 1 False guardedProof done) 20 20 5
      (\_ w -> if w==15 then T.Just 1 else error "wrong proof text charge"))

protectionChecks = do
  let runBinder hint = T.XVarTerm (T.XName (error "geometry demanded a binder ID") hint)
      runGround text = T.XThen (T.XInner (T.XBottom (T.XCon text []))) T.XElim
      runOperator proof = T.XTypeApp (runBinder "f") proof
      runHead = runOperator (runGround "I")
      runTree heads = foldr T.XApp (runBinder "z") heads
      runCost text budget = let bytes = Prim.stringUtf8Length text
        in if bytes > budget then T.Nothing else T.Just (budget-bytes)
      runAdmits term depth nodes work = case Source.finalGeometryWalkUsing True True False
          runCost depth (Source.GeometryTerm 1 term (Source.GeometryRoots [])) nodes work False of
            T.Just b -> Just b
            T.Nothing -> Nothing
      fourHeads = runTree (replicate 4 runHead)
      changedProof = runOperator (T.XThen (runGround "I") (runGround "J"))
      partialHead = T.XTypeApp (runBinder "f") (T.XThen
        (T.XInner (T.XBottom (T.XCon "longer" (error "geometry demanded the type list after exhausting UTF-8 work"))))
        (error "geometry demanded the right proof after exhausting UTF-8 work"))
  check "each repeated typed head contributes its full depth, nodes and UTF-8 work"
    [Just False,Nothing,Nothing,Nothing]
    [runAdmits fourHeads d n w | (d,n,w) <- [(10,56,65),(9,56,65),(10,55,65),(10,56,64)]]
  check "a changed proof after a repeated run still sets the composition flag" (Just True)
    (runAdmits (runTree [runHead,runHead,changedProof,runHead]) 40 500 800)
  check "a changed head exhausts its text budget before its remaining proof" Nothing
    (runAdmits (runTree [runHead,runHead,partialHead]) 40 500 46)
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
  let slot = V.fromInt
      repeated = replicate 1024 (slot 2)
      rows = [(slot 0,False,repeated),(slot 1,False,[slot 2]),(slot 0,False,repeated),
              (slot 2,True,[slot 0]),(slot 3,False,[slot 3])]
      flags = Classes.propagateProtection 4 rows
  check "retained readers across repeated rows, a cycle and an unrelated declaration"
    [True,True,True,False] (V.toList flags)
  let dormant = Classes.propagateProtection 1 [(error "unused owner",False,replicate 3 (slot 0))]
  check "an unprotected reverse edge leaves its owner lazy" [False] (V.toList dormant)
  beforeFlags <- try (evaluate (V.at (Classes.propagateProtection 1
    [(slot 0,error "early seed",[]),(slot 0,False,[error "later reference"])]) (slot 0))) :: IO (Either ErrorCall Bool)
  check "all reference bounds are demanded before any protection seed"
    (Left "later reference") (either (Left . takeWhile (/= '\n') . displayException) Right beforeFlags)

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
  let marker = "$MLF.Infix."
      suffixes = ["","x","λ","界.with.𐀀",marker,"\0name"]
      negatives = [take k marker ++ [ch] ++ drop (k+1) marker
                  | (k,actual) <- zip [0..] marker, ch <- ['a','.', '界'], ch /= actual]
  forM_ suffixes $ \suffix -> do
    check "infix lexical name projects the complete scalar suffix" suffix
      (H.unpack (D.lexicalValueName (H.literal (marker ++ suffix))))
    forM_ negatives $ \other -> check "non-matching lexical names retain their full spelling" (other ++ suffix)
      (H.unpack (D.lexicalValueName (H.literal (other ++ suffix))))
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
  let names = [replicate n 'a' ++ suffix | n <- [1,2,6,7,8,30,31,32], suffix <- ["b","B","0z","'z"]]
      distinct = ["word" ++ show n | n <- [0..300 :: Int]]
      wordsInFile = unwords (names ++ distinct ++ reverse names ++ reverse distinct)
      checked text = case Lexer.scanSourceTokens "lex" text of
        T.Left e -> T.Left e
        T.Right input@(Lexer.Scanned tokens _) -> case Lexer.validateSharedTokens "lex" tokens of
          T.Left e -> T.Left e
          T.Right () -> T.Right input
  forM_ ["A B.C", "A B .C", "A B. C", "A{- comment -}.C", "A\t.B", "A B.+",
         "A 2bad C.D", "A B . C 2bad", "A B . C {- unclosed", "Ω.A B.", "A where { B.C }"] $ \input -> do
    let sourceText = H.literal input
    check "qualified names retain source-order diagnostics and token extents after capital words"
      (scanned (checked sourceText)) (scanned (Lexer.scanValidatedSharedTokens "lex" sourceText))
  forM_ ["", " a界", " {- note -} again", " 1.bad", " {- open"] $ \suffix -> do
    let text = H.literal (wordsInFile ++ suffix)
    check "shared file scanner preserves prefix collisions, extents and first diagnostics"
      (scanned (checked text)) (scanned (Lexer.scanValidatedSharedTokens "lex" text))
  let section = Prim.stringSlice (H.literal "先😀\0終") 1 2
  let indexed = H.literal (replicate 255 'x' ++ "界😀" ++ replicate 255 'y')
      middle = H.v_stringSlice indexed 255 2
      framed = H.v_packStringFields [middle,section]
  check "hosted slices retain byte and scalar lengths across a Unicode index block"
    (2,7,[30028,128512]) (H.v_stringLength middle,H.v_stringUtf8Length middle,map (H.v_stringCodeAt middle) [0,1])
  check "framing consumes both hosted slices in order" ("2:界😀2:" ++ H.unpack section) (H.unpack framed)
  let rawImage = replicate 1023 65 ++ [0,128,255,127] ++ replicate 33 32 ++ [129]
      patches = replicate 31 'a' ++ ['\64','\65','\1','a','\3']
  raw <- Prim.newByteArray (fromIntegral (length rawImage)) 0
  forM_ (zip [0..] rawImage) $ \(i,v) -> Prim.writeByteArray raw i v
  (low,ops) <- BuiltinLiteral.compilerImageFields raw (fromIntegral (length rawImage))
  check "sparse builtin image patches across a page" patches (H.unpack ops)
  let open = BuiltinLiteral.openCompilerImage (low,ops) >>= \result -> case result of
        T.Right bytes -> pure bytes
        T.Left why -> fail (H.unpack why)
  firstImage <- open
  otherImage <- open
  Prim.writeByteArray firstImage 0 99
  imageLength <- Prim.lengthByteArray otherImage
  octets <- mapM (Prim.readByteArray otherImage) [0..imageLength-1]
  check "each installation owns all expected builtin image octets" rawImage octets
  invalid <- BuiltinLiteral.openCompilerImage ("123","a")
  case invalid of
    T.Left "invalid compiler image" -> pure ()
    _ -> fail "unfinished builtin skip"
  first <- Prim.byteArrayFromString section
  second <- Prim.byteArrayFromString section
  Prim.writeByteArray first 0 17
  check "UTF8 array snapshots preserve a slice and embedded NUL" [240,159,152,128,0]
    =<< mapM (Prim.readByteArray second) [0..4]
  check "mutating a UTF8 array preserves the input string" "😀\0" (H.unpack section)
  let replacements = M.fromList H.v_compareString [("x","inside"),("$MLF.Stack.callStack","hidden")]
      nativeStack = T.SVar "$MLF.Stack.callStack"
      application v = T.SApp (T.SApp v nativeStack) (T.SCallSite "x" span v)
        where span = T.SourceSpan "pkg" "Owner" "source.hs" 1 2 1 3
  check "repeated lexical replacements keep managed references and call sites"
    True (Equality.eqSExprBits (application (T.SVar "inside"))
      (Separate.renameParsedPlain replacements (application (T.SVar "x"))))
  let prefix = "separateLocal"
  forM_ [0,1,7,256] $ \offset ->
    forM_ ["",prefix,prefix ++ "0","separateLoca","separateLocλ","x" ++ prefix] $ \word -> do
      let text = replicate offset 'λ' ++ word ++ replicate offset 'l'
          reference = any (\i -> take (length prefix) (drop i text) == prefix) [0..length text]
      check "parsed source hygiene conservatively detects every binder prefix"
        reference (Separate.sourceHasHygienePrefix (H.literal text))
  let captureBlocks _ _ braced = T.Right (Lexer.Scanned [] (Lexer.Token (if braced then "yes" else "no") 0 0 0 0))
  forM_ ["where","let","of","do","otherwise","loop","done","Where"] $ \word ->
    forM_ [" ","\t"," {- a -} "," -- x\n "] $ \space ->
      forM_ ["","{ }","x"] $ \next -> do
        let text = H.literal ("f x " ++ word ++ space ++ next)
            expected = word `notElem` ["where","let","of","do"] || next == "{ }"
        case Lexer.scanSharedWithLayout captureBlocks "blocks" text of
          T.Right (Lexer.Scanned _ end) -> check "shared layout keyword followed by an explicit brace"
            expected (H.unpack (Lexer.tokenText end) == "yes")
          T.Left err -> fail (H.unpack err)
  forM_ [(H.literal "","e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
         (H.literal "abc","ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
         (H.literal "a\0λ😀","4fe290816c9390f64590f5c084138ccb45e844d36f955f7028682e3b18abbaad"),
         (H.v_stringSlice (H.literal "α界\0λtail") 1 3,"6c47638d59677a2695a1a624c05600dec901583df1cf5b20bcf79ef73090adda"),
         (H.literal (replicate 8193 'z'),"1740af352212ee326525f7bd044275adda2b46eb53128aca7c3e64b268121760")] $ \(text,expected) -> do
    digest <- CQ.sourceInputHash text
    check "immutable source UTF-8 SHA-256" expected (H.unpack digest)
  let mark tag code token xs = (tag,code,H.unpack (Lexer.tokenText token)):xs
      sink = Lexer.TokenOutput (mark 'w') (mark 'n') (mark 'p' 0) (mark 'f' 0)
        (\xs _ -> T.Left (H.literal (show (reverse xs))))
      source = "foo 12,9"
  case Lexer.collectTokensWith sink Lexer.scanSourceQuoted "sink" source (H.v_stringLength source)
         IntMap.empty [] (Lexer.Cursor 0 3 9) of
    T.Left marks -> check "word consumers see the leading scalar and decimal consumers see the following scalar"
      "[('w',102,\"foo\"),('n',44,\"12\"),('p',0,\",\"),('n',-1,\"9\")]" (H.unpack marks)
    T.Right _ -> fail "custom token consumer did not finish"
  let nameTree T.MapEmpty = []
      nameTree (T.MapNode n key () l r) = (n,H.unpack key) : nameTree l ++ [(-1,"")] ++ nameTree r
      namesOf (T.Set t) = nameTree t
      app = foldr1 T.SApp (map T.SVar ["a","b","b","c","a","r0","r1","λ"])
      term = T.SLet "a" app (T.SLetRec [("k",T.InferRecursive,app)] (T.SVar "k"))
      method = T.SLam "r2" T.Nothing (T.SVar "r3")
      suffix = T.SInstanceDecl [] [] "K" [] [("method",method)]
      unwrapNames (T.Left why) = fail (H.unpack why)
      unwrapNames (T.Right value) = pure value
      namesAction = do
        next <- Fresh.freshName "r"
        Fresh.Fresh (\n used -> T.Right ((H.unpack next,n,namesOf used),n,used))
  let signedTerm = T.SAnn (T.SSignature (T.SChecked (error "unused checked type") term)
                            (error "unused signature")) (error "unused annotation")
      following = ["r0","r2","尾"]
  check "name reservation traverses signed bodies in ordinary order"
    (namesOf (Fresh.reservedNames (Desugar.allNames signedTerm ++ following)))
    (namesOf (Desugar.reservedExpressionNames signedTerm following))
  expectedNames <- unwrapNames (Fresh.runFresh (Desugar.allNames term ++ Desugar.allNames method) namesAction)
  classNames <- unwrapNames (Classes.withValidatedClasses T.Nothing S.empty M.empty T.Nothing [] [] [suffix] term (\_ _ -> namesAction))
  check "class initialization preserves the reserved tree, spelling collisions and fresh count" expectedNames classNames
  let boundaries = [fromInteger (sign * (10^digits + offset)) |
        sign <- [-1,1], digits <- [0..18 :: Int], offset <- [-1..1]]
  forM_ (minBound:maxBound:boundaries) $ \value -> do
    let signedWidth = fromIntegral (length (show value))
    check "signed decimal render width matches its complete spelling" signedWidth (Storage.v2IntLength value)
    check "unsigned render width preserves the single-digit domain below ten"
      (if value < 0 then 1 else signedWidth) (Storage.v2DecimalLength value)
  let punctuation = "(),;[]{}" :: String
  forM_ punctuation $ \first -> forM_ punctuation $ \second -> do
    let source = H.literal ([first] ++ "{- {- x -} -}" ++ [second])
    case Lexer.scanSourceTokens "delimiters" source of
      T.Left err -> fail (H.unpack err)
      T.Right (Lexer.Scanned ts end) -> check "single punctuation preserves its spelling and span across a nested comment"
        ([([first],1,2),([second],15,16)],16)
        ([(H.unpack (Lexer.tokenText t),Lexer.tokenColumn t,Lexer.tokenEndColumn t) | t <- ts],
         Lexer.tokenColumn end)
  let identityBody a b c = T.XCase (T.XTypeApp (T.XIntTerm 0) (T.XHyp (T.XTyVar a)))
        (T.XForall (T.XTyVar b) T.XBot (T.XVar (T.XTyVar b)))
        [T.XAlternative (T.XConstructorPattern "K" [T.Just (T.XName c "p")]) (T.XBoolTerm True)]
  forM_ [identityBody minBound (-7) 0,identityBody 2 maxBound 91,identityBody 9 8 7,
         T.XWithData (error "unobserved datatype declarations") (T.XIntTerm 3)] $ \typed ->
    forM_ [minBound,-1,0,47,maxBound] $ \lower ->
      check "typed identity maximum includes computations, type binders and pattern binders"
        (foldr max lower (I.toList (Separate.termIdentities typed I.empty)))
        (Separate.maximumTermIdentity lower typed)
  let var ident = T.XTyVar ident
      kindInput = T.XApply (T.XVar (var 9)) (T.XArrow (T.XVar (var 2)) (T.XVar (var 5)))
      kindEnv = M.singleton (var 2) (T.XVar (var 2))
  case XT.kindOf (T.DataEnv M.empty M.empty M.empty) kindEnv kindInput of
    T.Left why -> check "kind resolution reports the first free variable in signed identity order"
      "cyclic type environment" (H.unpack why)
    _ -> fail "cyclic free-variable bound admitted"
  let variable n = T.XVar (T.XTyVar n)
      boundInventory = T.XForall (T.XTyVar 5) (variable 5)
        (T.XForall (T.XTyVar (-2)) (variable 3) (T.XArrow (variable (-2)) (variable 5)))
  check "free type variables include a quantifier's own free bound" [3,5]
    (map XT.tyVarId (S.toList (XT.freeVars boundInventory)))
  check "all type variables include negative binders" [-2,3,5]
    (map XT.tyVarId (S.toList (XT.allVars boundInventory)))
  let higherBottom = T.KArrow T.Star T.Star
      kindData = T.DataEnv M.empty M.empty (M.singleton "F" higherBottom)
      toConstructor = T.XBottom (T.XCon "F" [])
  case XCheck.checkComputationIn kindData M.empty toConstructor (T.XBotKind higherBottom) of
    T.Right (T.XCon name []) -> check "Inst-Bot preserves its higher-kinded target" "F" (H.unpack name)
    _ -> fail "higher-kinded Inst-Bot rejected"
  case XCheck.checkComputationIn kindData M.empty toConstructor (T.XBotKind T.Star) of
    T.Left message -> check "Inst-Bot reports incompatible target kinds" "Inst-Bot kind mismatch" (H.unpack message)
    _ -> fail "incompatible Inst-Bot target kind admitted"
  let ctorEnv = Classes.QualifiedEnv M.empty (const T.Nothing)
      ctor name = T.SConstructor name
      here = T.SourceSpan "P" "M" "file.hs" 1 1 1 2
      op = T.SCallSite (error "constructor function label") (error "function span") (ctor "Branch")
      called = T.SApp (T.SApp op (T.SIntLit 2)) (T.SCallSite "b" here (ctor "Leaf"))
      wanted = T.SApp (T.SApp (ctor "Branch") (T.SIntLit 2)) (ctor "Leaf")
      lowerCtor = Classes.plainLambdaApplication ctorEnv called (Fresh.freshFail "unexpected fallback")
  case Fresh.runFreshState lowerCtor 9 (Fresh.reservedNames ["old"]) of
    T.Right (Classes.PlainResult node body,next,used) -> do
      check "constructor applications preserve generated identities" (13,14) (node,next)
      check "constructor applications preserve the original reservation" ["old"] (map H.unpack (S.toList used))
      check "constructor application drops function and argument locations" True (Equality.eqSExprBits body wanted)
    _ -> fail "constructor application with source locations"
  let deferred = T.SLet "v" (error "unused binding") (error "unused body")
      primitive = T.SCallSite (error "unused function label") here (T.SPrimitive T.PAddInt)
      partial = T.SApp (T.SApp primitive deferred) (error "second operand before fallback")
  case Fresh.runFreshState (Classes.plainLambdaApplication ctorEnv partial (Fresh.freshFail "ordinary planner"))
                           9 (Fresh.reservedNames []) of
    T.Left why -> check "binary class planning observes an unsupported first operand before the second"
      "ordinary planner" (H.unpack why)
    _ -> fail "unsupported first operand bypassed the ordinary planner"
  let text = H.literal "F (A (B (C x))) y; next"
      result (Parsec.PSuccess tree (Parsec.ParseState _ rest _ _ _ _) consumed) =
        Right (H.unpack (CQ.encodeExpression tree),map (H.unpack . Lexer.tokenText) rest,consumed)
      result (Parsec.PFailure why _ consumed) = Left (H.unpack why,consumed)
  case Lexer.scanSourceTokens "group.hs" text of
    T.Left why -> fail (H.unpack why)
    T.Right (Lexer.Scanned tokens eof) -> do
      let state=Parsec.ParseState "group.hs" tokens eof T.SharedHaskellV1 "Owner" "pkg"
          parsed=result (Parsec.pRun (Parser.equationExpressionWith True) state)
      check "nested equation groups preserve the full grammar's application and source spans"
        (result (Parsec.pRun Parser.expr state)) parsed
      check "consecutive closures retain the delimiter for the enclosing declaration"
        (Right ([";","next"],True)) (fmap (\(_,tailTokens,consumed)->(tailTokens,consumed)) parsed)
  let resultType answer = case answer of
        T.Left why -> Left (H.unpack why)
        T.Right ty -> Right (H.unpack (Pretty.prettyType ty))
  forM_ (zip [0..] Primitives.allPrimitives) $ \(slot,p) -> do
    check "primitive registry order agrees with its stable code" slot (Primitives.primitiveCode p)
    case Structure.primitiveFromCode slot of
      T.Right wire -> check "wire reader identifies the indexed primitive"
        (H.unpack (Primitives.primitiveName wire)) (H.unpack (Primitives.primitiveName p))
      T.Left why -> fail (H.unpack why)
    check "indexed closed signature agrees with the independent checker"
      (resultType (Independent.inferIn Data.emptyDataEnv XCheck.emptyEnv (T.XPrimitive p [])))
      (resultType (XCheck.closedPrimitiveType p))
  check "dense primitive table covers the wire registry" True
    (case Structure.primitiveFromCode (fromIntegral (length Primitives.allPrimitives)) of
      T.Left _ -> True
      T.Right _ -> False)
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


fragmentFingerprintChecks = do
  let right (T.Right value) = pure value
      right (T.Left message) = fail (H.unpack message)
  env <- right (Open.environment [])
  let ty = T.XCon "Int" []
      arg = T.XName 0 "arg:λ"
      result = T.XName 1 "結果😀"
      add a b = T.XApp (T.XApp (T.XPrimitive T.PAddInt []) a) b
      tree 0 = T.XVarTerm arg
      tree n = add (tree (n-1)) (tree (n-1))
      parameters = Separate.pack [Separate.pack ["0", "arg:λ", "Int"]]
      exports = Separate.pack [Separate.pack ["結果😀", "Int"]]
  let decl value = T.XLet (T.XName 9 "export") value (T.XConstructor "()" [])
      occurrence i hint = T.XVarTerm (T.XName i hint)
      inputs = [(T.XName 1 "param",ty),(T.XName 2 "param",ty)]
      spelling (T.XName i hint) = (i,H.unpack hint)
  inputsUsed <- right (Open.check env inputs (decl (add (occurrence 2 "first")
    (add (occurrence 1 "second") (occurrence 2 "again")))))
  check "checked fragment uses retain first occurrence order, identities and display hints"
    [(2,"first"),(1,"second")] (map spelling (Open.usedParameters inputsUsed))
  case Open.check env (take 1 inputs) (decl (add (occurrence 1 "seen") (occurrence 3 "missing"))) of
    T.Left why -> check "a later unbound read still fails independent checking" "unbound term variable missing" (H.unpack why)
    T.Right _ -> fail "accepted an unknown parameter after the last declared input"
  forM_ [0..8 :: Int] $ \depth -> do
    let body = T.XLet result (tree depth) (T.XConstructor "()" [])
        fields = [Separate.pack [], parameters, Pretty.prettyTerm body, exports]
    fragment <- right (Open.check env [(arg,ty)] body)
    check "fragment stamp matches scalar-length-framed pretty text"
      (H.unpack (Separate.fingerprint (Separate.pack fields))) (H.unpack (Open.fingerprint fragment))

  forM_ [31,32,33,4096,4097] $ \width -> do
    let label = H.literal (take width (cycle "λx😀"))
        variable = T.XName 4 label
        leaf = T.XVarTerm variable
        sumOfArgs = foldr1 add (replicate 41 leaf)
        body = T.XLet result sumOfArgs (T.XConstructor "()" [])
        parameter = Separate.pack [Separate.pack ["4", label, "Int"]]
        fields = [Separate.pack [], parameter, Pretty.prettyTerm body, exports]
    fragment <- right (Open.check env [(variable,ty)] body)
    check "repeated Unicode names retain the scalar-framed fingerprint"
      (H.unpack (Separate.fingerprint (Separate.pack fields))) (H.unpack (Open.fingerprint fragment))
  let a = T.XTyVar 16
      b = T.XTyVar 17
      poly = T.XForall a T.XBot (T.XForall b T.XBot (T.XArrow ty ty))
      op = T.XName 19 "変換😀"
      operand = T.XVarTerm arg
      ground t = T.XThen (T.XInner (T.XBottom (T.XCon t []))) T.XElim
      f label first second = T.XTypeApp (T.XVarTerm (T.XName 19 label)) (T.XThen (ground first) (ground second))
      uses = take 131 (cycle [f "変換😀" "Int" "Bool", f "変換😀" "Int" "Bool", f "alias" "Bool" "Int"])
      body = T.XLet result (foldr T.XApp operand uses) (T.XConstructor "()" [])
      ps = Separate.pack [Separate.pack ["19","変換😀",Pretty.prettyType (Separate.normalType poly)],
                          Separate.pack ["0","arg:λ","Int"]]
      expected = Separate.fingerprint (Separate.pack [Separate.pack [], ps, Pretty.prettyTerm body, exports])
  actual <- right (Open.check env [(op,poly),(arg,ty)] body)
  check "repeated operator uses retain proof text, hint spelling and right-child parentheses"
    (H.unpack expected) (H.unpack (Open.fingerprint actual))

applicationPatternChecks = do
  let named text fields = W.VNode 82 [W.VText text,W.VNode 1 fields]
      names = [named "A" [],named "長😀" [],named "A" [],named "長😀" [W.VInt 2],named "A" []]
      encoded action = do
        value <- action
        case value of
          T.Left m -> pure (Left (H.unpack m))
          T.Right b -> do
            n <- Prim.lengthByteArray b
            Right <$> mapM (Prim.readByteArray b) [0..n-1]
  forM_ [W.defaultLimits,W.Limits 1024 8 128 256 32 64 8 19] $ \limits -> do
    expected <- encoded (W.encode limits 8 names)
    actual <- encoded (W.encodeAtoms Structure.termAtomShapes limits 8 names)
    check "named constructor atoms preserve bytes and resource diagnostics" expected actual
  let groundArg name = Structure.toXComputation (T.XThen (T.XInner (T.XBottom (T.XCon name []))) T.XElim)
      composeArgs a b = W.VNode 58 [a,b]
      smallA = groundArg "Int"
      wideB = groundArg "λ😀"
      emptyC = groundArg ""
      leftProof = composeArgs (composeArgs smallA wideB) emptyC
      rightProof = composeArgs smallA (composeArgs wideB emptyC)
      proofRoots = [leftProof,leftProof,rightProof,rightProof]
      partialProof = composeArgs (composeArgs (W.VNode (-1) (error "forced invalid child fields")) wideB)
        (error "forced a later proof")
  forM_ [127,128,130] $ \budget -> do
    expected <- encoded (W.encodeRootBounded W.defaultLimits budget 8 proofRoots)
    actual <- encoded (W.encodeRootsWithAtoms Structure.termAtomShapes W.defaultLimits budget 8 proofRoots)
    check "repeated ground compositions preserve UTF-8 costs, grouping and canonical bytes" expected actual
    check "four mixed-name proof triples cost exactly 128 work units"
      (budget >= 128) (case actual of Right _ -> True; _ -> False)
  rejectedProof <- encoded (W.encodeAtoms Structure.termAtomShapes W.defaultLimits 8 [leftProof,leftProof,partialProof])
  check "a cached composition miss preserves the first invalid tag before the right subtree"
    (Left "binary constructor tag out of range") rejectedProof
  let v n = T.XTyVar n
      ty n = T.XVar (v n)
      groundScheme vars lastBound = foldr (\(i,lower) body -> T.XForall (v i) lower body)
        (T.XArrow (ty 0) (T.XArrow (ty 1) (ty 0))) (zip vars [T.XBot,T.XBot,lastBound])
      observe ty0 = case ty0 of
        Inference.GroundVar i -> Left i
        Inference.GroundArrow _ _ -> Right (0::Int)
        Inference.GroundCon _ _ -> Right 1
        Inference.GroundApply _ _ -> Right 2
      view ground = case ground of
        T.Left why -> Left (H.unpack why)
        T.Right (body,slots,Inference.GroundState next known ranks serial) ->
          Right (observe body,[(XT.tyVarId binder,observe ty0) | (binder,ty0)<-slots],next,IntMap.keys known,IntMap.toList ranks,serial)
  forM_ [groundScheme [0,1,2] T.XBot,groundScheme [1,0,1] (T.XBotKind T.Star),
         groundScheme [0,1,2] (ty 0),T.XVar (v 841)] $ \scheme -> do
    let prepare = Inference.prepareGroundScheme scheme
    forM_ [-3,0,8,4102] $ \start -> do
      let state = Inference.GroundState start (IntMap.singleton 2 (Inference.GroundCon "Int" [])) (IntMap.singleton 2 3) 53
      check "a prepared ground scheme preserves fresh identities and its starting environment"
        (view (Inference.groundScheme M.empty [] state scheme)) (view (prepare state))
  let emptyChild = W.VNode 1 []
      unaryChild = W.VNode 11 [W.VInt 4]
      atomChild = W.VNode 82 [W.VText "A",emptyChild]
      branchChild = W.VNode 72 [atomChild,unaryChild]
      testRoots = [W.VNode 13 [branchChild,unaryChild,emptyChild,atomChild,branchChild],branchChild,emptyChild]
      expectedTables = W.Tables [W.Symbol "A" 1]
        [W.EText 0,W.ENode 1 [],W.ENode 82 [0,1],W.EInt 4,W.ENode 11 [3],
         W.ENode 72 [2,4],W.ENode 13 [5,4,1,2,5]] [6,5,1] 1 7 3 10
  expectedLayout <- case W.layout W.defaultLimits expectedTables of
    T.Left why -> fail (H.unpack why)
    T.Right layout -> pure layout
  expectedWire <- encoded (W.encodeTables 8 expectedLayout expectedTables)
  case expectedWire of
    Left why -> fail why
    Right _ -> pure ()
  forM_ [W.encode W.defaultLimits 8 testRoots,
         W.encodeRootsWithAtoms Structure.termAtomShapes W.defaultLimits 30 8 testRoots] $ \action -> do
    bytes <- encoded action
    check "binary children retain left-to-right IDs across unary, wide and repeated atom parents"
      expectedWire bytes
  tooSmall <- encoded (W.encodeRootsWithAtoms Structure.termAtomShapes W.defaultLimits 29 8 testRoots)
  check "repeated atoms and root references consume exact expanded work"
    (Left "binary expanded-work limit exceeded") tooSmall
  let underDepth = W.Limits 1024 8 32 64 12 12 1 8
      underWork = W.Limits 1024 8 32 64 12 12 8 3
      defer = error "forced a field after its limiting failure"
  forM_ [(underDepth,W.VNode 72 [defer,defer],"binary graph depth limit exceeded"),
         (underWork,W.VNode 72 [W.VNode 9 [W.VInt 1],defer],"binary expanded-work limit exceeded"),
         (W.defaultLimits,W.VNode 72 [W.VNode (-1) defer,defer],"binary constructor tag out of range")] $
    \(limits,value,why) -> do
      failed <- encoded (W.encode limits 8 [value])
      check "binary planning returns its leftmost limit before later field demand" (Left why) failed
  let wireVar i hint = W.VNode 70 [W.VNode 31 [W.VInt i,W.VText hint]]
      wireLeaf ty = W.VNode 58 [W.VNode 53 [W.VNode 51 [W.VNode 44 [W.VText ty,W.VNode 1 []]]],W.VNode 55 []]
      wireJoin x y = W.VNode 58 [x,y]
      wireHead i hint pr = W.VNode 72 [W.VNode 74 [wireVar i hint,pr],wireVar 0 "step"]
      wireProof = wireJoin (wireJoin (wireLeaf "λ") (wireLeaf "")) (wireLeaf "Int")
      wireApp h z = W.VNode 72 [h,z]
      wireChain hs = foldr wireApp (wireVar 2 "tail") hs
      wireSame = wireHead 1 "compose" wireProof
      wireOther = wireHead 3 "compose" wireProof
      wireRoots = [wireChain [wireSame,wireSame,wireSame,wireOther,wireSame],
                   wireChain [wireOther,wireOther,wireOther]]
  forM_ [300,600,2000] $ \budget -> do
    expected <- encoded (W.encodeRootBounded W.defaultLimits budget 8 wireRoots)
    actual <- encoded (W.encodeRootsWithAtoms Structure.termAtomShapes W.defaultLimits budget 8 wireRoots)
    check "admitted left subtrees preserve binder IDs, bytes and aggregate work" expected actual
  let groundBinder n = T.XTyVar n
      bottom n body = T.XForall (groundBinder n) T.XBot body
      groundInt = Inference.GroundCon "Int" []
      groundBool = Inference.GroundCon "Bool" []
      arguments = zip (map groundBinder [0,1,2]) [groundInt,groundBool,Inference.GroundArrow groundInt groundBool]
      evidenceState = Inference.GroundState 0 IntMap.empty IntMap.empty 5
      groundResult result = case result of
        T.Left msg -> pure (Left (H.unpack msg))
        T.Right proof -> encoded (W.encode W.defaultLimits 8 [Structure.toXComputation proof])
      ret = T.XArrow (T.XVar (groundBinder 0)) (T.XVar (groundBinder 2))
      sets = [arguments,take 2 arguments,arguments++[(groundBinder 1,groundInt)],
              reverse arguments,[(groundBinder 0, Inference.GroundVar 34)]]
  forM_ [bottom 0 (bottom 1 (bottom 2 ret)),
         bottom 0 (T.XForall (groundBinder 1) (T.XVar (groundBinder 0)) (bottom 2 ret)),
         bottom 0 (bottom 1 (bottom 1 ret))] $ \scheme -> do
    let Inference.GroundEvidence cached = Inference.prepareGroundEvidence scheme
    forM_ sets $ \inventory -> do
      expected <- groundResult (Inference.groundEvidence evidenceState scheme inventory)
      actual <- groundResult (cached evidenceState inventory)
      check "ground binding preserves evidence bytes, shadowing and dependent bounds" expected actual
  let applyArg label = T.XThen (T.XInner (T.XBottom (T.XCon label []))) T.XElim
      balanced [p] = p
      balanced ps = let (a,b) = splitAt (length ps `div` 2) ps in T.XThen (balanced a) (balanced b)
      canonicalBytes phi change = encoded (W.encode W.defaultLimits 8
        [Structure.toXComputation (case change of T.Nothing -> phi; T.Just p -> p)])
  forM_ [2,3,4,5,7,16,31,64] $ \n ->
    forM_ [foldl1 T.XThen,foldr1 T.XThen,balanced] $ \group -> do
      let proof = group (take n (cycle (map applyArg ["Int","型😀","Bool"])))
      case (Source.rewriteProof proof,Source.groundProofEdit proof) of
        (T.Right baseline,T.Just fast) -> do
          expected <- canonicalBytes proof baseline
          actual <- canonicalBytes proof fast
          check "ground instantiations have the graph finalizer's exact grouping and argument order" expected actual
        _ -> fail "expected a bounded sequence of complete ground arguments"
  case Source.groundProofEdit (T.XThen T.XRefl (T.XThen T.XRefl T.XRefl)) of
    T.Nothing -> pure ()
    _ -> fail "an unsupported nested proof requires ordinary graph finalization"
  let argument ty = Structure.toXComputation (T.XThen (T.XInner (T.XBottom (T.XCon ty []))) T.XElim)
      intArg = argument "Int"
      wideArg = argument "型λ😀"
      proofs = [intArg,intArg,W.VNode 58 [intArg,wideArg],wideArg,intArg]
      badProof = W.VNode 58 [W.VNode 53 [W.VNode 51 [W.VNode 44 [W.VText "Int",W.VNode 1 []]]],
                             W.VNode (-1) (error "forced children of invalid proof tag")]
      graphWork plan = case plan of
        T.Left message -> Left (H.unpack message)
        T.Right admitted -> case W.realizeGraphPlan admitted of
          T.Left message -> Left (H.unpack message)
          T.Right graph -> case W.graphExpandedWork graph of
            T.Left message -> Left (H.unpack message)
            T.Right work -> Right (W.graphRoots graph,W.graphNodeCount graph,work)
  forM_ [W.defaultLimits,W.Limits 2048 8 128 256 64 128 16 32,
         W.Limits 2048 8 128 256 64 128 4 1024] $ \limits ->
    forM_ [proofs,proofs ++ [badProof]] $ \roots -> do
      direct <- encoded (W.encode limits 8 roots)
      actual <- encoded (W.encodeAtoms Structure.termAtomShapes limits 8 roots)
      check "ground type proof preserves wire bytes and first failed limit" direct actual
      check "ground type proof preserves DAG roots, distinct nodes and expanded work"
        (graphWork (W.prepareGraphPlan limits roots))
        (graphWork (W.prepareGraphPlanWithAtoms Structure.termAtomShapes limits roots))
  let right (T.Right value) = pure value
      right (T.Left message) = fail (H.unpack message)
      rejected (T.Left _) = True
      rejected _ = False
      add a b = T.XApp (T.XApp (T.XPrimitive T.PAddInt []) a) b
      tree [x] = x
      tree xs = let (l,r) = splitAt (length xs `div` 2) xs in add (tree l) (tree r)
      arg = T.XName 0 "arg:λ"
      result = T.XName 1 "export😀"
      ty = T.XCon "Int" []
      bodies = [take 32 (iterate (+7) (maxBound-4)),replicate 32 minBound,
                take 63 (cycle [maxBound,0,7,7,-1,minBound]),
                take 64 (cycle [-10001,-1000,-101,-100,-99,-10,-9,0,9,10,99,100,101,9999,10000])]
  let var n = T.XVar (T.XTyVar n)
      xarrow = T.XArrow
      scheme = foldr (\i -> T.XForall (T.XTyVar i) T.XBot)
        (xarrow (xarrow (var 4) (var 17)) (xarrow (xarrow (var 20) (var 4)) (xarrow (var 20) (var 17)))) [4,17,20]
      headName = T.XName 55 "λ→"
      argName = T.XName 62 "変換"
      argType = Inference.GroundArrow (Inference.GroundCon "Int" []) (Inference.GroundCon "Bool" [])
      start = Inference.GroundState 19 IntMap.empty IntMap.empty 77
      order a b = if a < b then -1 else if a == b then 0 else 1
      apply bind = Inference.groundInfer
        (M.fromList order [(1,bind headName scheme),(2,Inference.GroundLocal argName argType)])
        M.empty start (T.SApp (T.SGlobal (V.fromInt 1) "ignored") (T.SGlobal (V.fromInt 2) "ignored"))
      close bind expectedSlots = case apply bind of
        T.Left message -> fail (H.unpack message)
        T.Right (term,actual,st@(Inference.GroundState next known _ serial)) -> do
          check "closed-arrow operand preserves reservations" (23,77,expectedSlots) (next,serial,IntMap.size known)
          let from = Inference.GroundCon "String" []
              to = Inference.GroundCon "Bool" []
              wanted = Inference.GroundArrow (Inference.GroundArrow from (Inference.GroundCon "Int" []))
                         (Inference.GroundArrow from to)
          solved <- right (Inference.groundUnify st actual wanted)
          sealed <- right (Inference.groundSeal solved term)
          encoded (W.encode W.defaultLimits 8 [Structure.toXTerm sealed])
  ordinaryOperand <- close Inference.prepareGroundImport 2
  forwardedOperand <- close Inference.prepareGroundApplication 1
  check "forward closed operands with the ordinary quantified proof bytes" ordinaryOperand forwardedOperand
  do
    let v n=T.XVar(T.XTyVar n)
        arrow=T.XArrow
        forallIds ids body=foldr (\n -> T.XForall (T.XTyVar n) T.XBot) body ids
        i=T.XCon "Int" []
        scheme=forallIds [19,3,8] (arrow (arrow (v 19) (v 3))
          (arrow (arrow (v 8) (v 19)) (arrow (v 8) (v 3))))
        bindings make=M.fromList H.v_compareString
          [("outer",make (T.XName 1 "outer") scheme),("offset",make (T.XName 2 "offset") (arrow i i)),
           ("zero",make (T.XName 3 "zero") (forallIds [54] (arrow (v 54) (v 54))))]
        expr n=T.SApp (foldr (\_ -> T.SApp (T.SApp (T.SVar "outer") (T.SVar "offset")))
          (T.SVar "zero") [1..n]) (T.SIntLit 8)
        infer n make=Inference.groundInfer M.empty (bindings make) (Inference.GroundState 0 IntMap.empty IntMap.empty 3) (expr n)
    forM_ [2,17::Int] $ \n -> do
      (before,_,oldState)<-right (infer n Inference.prepareGroundImport)
      (term,_,st@(Inference.GroundState next known ranks serial))<-right (infer n Inference.prepareGroundApplication)
      check "nested second-operand forwarding retains just the sentinel and the identity instance"
        (fromIntegral(5*n+2),3,1,3) (next,IntMap.size known,IntMap.size ranks,serial)
      oldTerm<-right (Inference.groundSeal oldState before)
      newTerm<-right (Inference.groundSeal st term)
      oldBytes<-encoded (W.encode W.defaultLimits 8 [Structure.toXTerm oldTerm])
      newBytes<-encoded (W.encode W.defaultLimits 8 [Structure.toXTerm newTerm])
      check "nested callback inference preserves exact ground evidence bytes" oldBytes newBytes
  env <- right (Open.environment [])
  forM_ bodies $ \xs -> do
    let source = T.XLet result (tree [add (T.XVarTerm arg) (T.XIntTerm n) | n <- xs]) (T.XConstructor "()" [])
    checked <- right (Open.check env [(arg,ty)] source)
    let frame = Separate.pack [Separate.pack [], Separate.pack [Separate.pack ["0", "arg:λ", "Int"]],
          Pretty.prettyTerm source, Separate.pack [Separate.pack ["export😀", "Int"]]]
    check "compact signed-literal fingerprint matches the complete pretty-printed frame"
      (H.unpack (Separate.fingerprint frame)) (H.unpack (Open.fingerprint checked))
    graph <- right (W.planGraph W.defaultLimits [Open.encodeRaw (W.VNode 1 []) "raw" "unit" checked])
    W.GNode 425 [_,record] <- right (W.lookupGraphNode graph (head (W.graphRoots graph)))
    W.GNode 440 [_,_,_,_,body,_,_] <- right (W.lookupGraphNode graph record)
    restored <- right (Structure.storedTerm graph body)
    unless (H.unpack (Pretty.prettyTerm restored) == H.unpack (Pretty.prettyTerm source)) (fail "stored checked application term")
    unless (rejected (Structure.fromGraphXTerm graph body)) (fail "unversioned term reader accepted application pattern")
  -- The compact coder must visit references and the raw header before it
  -- probes the literal stream. The ordinary frame fixes the error order.
  let rawRefs = W.VNode 1 []
      diskError root = do
        outcome <- try (evaluate (case W.planGraph W.defaultLimits [root] of
          T.Left message -> error (H.unpack message)
          T.Right graph -> length (W.graphRoots graph))) :: IO (Either ErrorCall Int)
        pure (either (Just . takeWhile (/= '\n') . displayException) (const Nothing) outcome)
      badValues = error "first literal" : error "later literal" : replicate 16 0
      body = T.XLet result (tree (map T.XIntTerm badValues)) (T.XConstructor "()" [])
  checked <- right (Open.check env [] body)
  forM_ [(rawRefs,"raw","unit","first literal"),(W.VText (error "references"),error "stage","unit","references"),
         (rawRefs,error "stage",error "name","stage"),(rawRefs,"raw",error "name","name")] $
    \(refs,stage,name,expected) -> do
      old <- diskError (W.VNode 425 [refs,Open.encodeBody stage name checked])
      compact <- diskError (Open.encodeRaw refs stage name checked)
      check "ordinary open-body error" (Just expected) old
      check "ordered compact-body error" old compact
  let hole = W.VNode 87 []
      join i j = W.VNode 88 [W.VInt i,W.VInt j]
      run n = W.VNode 89 [W.VInt maxBound,W.VInt 1,W.VInt n]
      pattern rows numbers root = W.VNode 86 [W.VNode 1 rows,W.VNode 1 numbers,W.VInt root]
      rows = [hole,join 0 0,join 1 1,join 2 2]
      good = pattern rows [run 8] 3
      malformed = [pattern [hole,join 1 0] [run 8] 1,pattern rows [run 7] 3,
                   pattern rows [run 9] 3,pattern (hole:[join n n | n <- [0..28]]) [run 8] 29,
                   pattern [hole,join 0 0,join 0 0,join 2 2,join 3 3] [run 8] 4]
  forM_ malformed $ \raw -> do
    graph <- right (W.planGraph W.defaultLimits [raw])
    unless (rejected (Structure.storedTerm graph (head (W.graphRoots graph)))) (fail "malformed application pattern")
  let ctor = T.XConstructor "C:λ" []
      stop = T.XConstructor "end" []
      repeatRow n = W.VNode 88 [W.VInt 2,W.VInt 3,W.VInt n]
      spine n = pattern [hole,Structure.toXTerm ctor,join 1 0,Structure.toXTerm stop,repeatRow n] [run 257] 4
      terms = take 257 (iterate (+1) maxBound)
      original = foldr (\n t -> T.XApp (T.XApp ctor (T.XIntTerm n)) t) stop terms
  graph11 <- right (W.planGraph W.defaultLimits [spine 257])
  raw11 <- right (W.planGraph W.defaultLimits [Structure.toXTerm original])
  logicalWork <- right (W.graphExpandedWork raw11)
  (spinePlans,charged) <- right (Structure.admitPatternsWith True True graph11 logicalWork)
  check "count each constructor, UTF-8 name and signed slot" logicalWork charged
  unless (rejected (Structure.admitPatternsFor True graph11 logicalWork)) (fail "older schema admitted a repeated head")
  unless (rejected (Structure.admitPatternsWith True True graph11 (logicalWork-1))) (fail "undercharged repeated head")
  [restored11] <- right (Structure.decodeStoredManyWith spinePlans graph11 (W.graphRoots graph11))
  restoredBody <- right (Structure.expectXTerm restored11)
  expectedBytes <- encoded (W.encode W.defaultLimits 8 [Structure.toXTerm original])
  restoredBytes <- encoded (W.encode W.defaultLimits 8 [Structure.toXTerm restoredBody])
  check "source order and signed wrapping in repeated application heads" expectedBytes restoredBytes
  forM_ [-1,1,256,16384,maxBound] $ \count -> do
    invalid <- right (W.planGraph W.defaultLimits [spine count])
    unless (rejected (Structure.admitPatternsWith True True invalid logicalWork)) (fail "invalid repeated application count")
  let chargeName text available = let size = H.v_stringUtf8Length text in
          if size <= available then T.Just (available-size) else T.Nothing
      compareGeometry bySpine d nodeBudget workBudget value = case
          Source.finalGeometryUsing bySpine bySpine chargeName d [(1,False,[value])] nodeBudget workBudget False of
            T.Nothing -> Nothing
            T.Just flag -> Just flag
      countNodes = 3 + 7 * 257
      chargeWork = 3 + H.v_stringUtf8Length "end" + 257 * (7 + H.v_stringUtf8Length "C:λ")
  forM_ [(260,countNodes,chargeWork),(259,countNodes,chargeWork),(260,countNodes-1,chargeWork),
         (260,countNodes,chargeWork-1)] $ \(d,n,w) ->
    check "repeated application finalization charges original depth, nodes and UTF-8 work"
      (compareGeometry False d n w (Structure.toXTerm original))
      (compareGeometry True d n w (spine 257))
  let checkedTree = T.XLet result (foldr (add . T.XIntTerm) (T.XIntTerm 0) terms) (T.XConstructor "()" [])
  checkedSpine <- right (Open.check env [] checkedTree)
  let decl = T.DataDeclK "Tree" [] [T.ConstructorDecl "End" [],
             T.ConstructorDecl "Branchλ" [T.Applied "Int" [],T.Applied "Tree" []]]
      leaf = T.XConstructor "End" []
      branch n tail = T.XApp (T.XApp (T.XConstructor "Branchλ" []) (T.XIntTerm n)) tail
      rhs = foldr branch leaf terms
      owner = T.XName 51 "rootλ"
      expression = T.XLet owner rhs (T.XConstructor "()" [])
      expected = Separate.fingerprint (Separate.pack [Separate.pack [Data.prettyDeclaration decl],
                 Separate.pack [],Pretty.prettyTerm expression,Separate.pack [Separate.pack ["rootλ","Tree"]]])
  declared <- right (Open.environment [decl])
  saved <- right (Open.check declared [] expression)
  check "repeated constructor fingerprints include every signed slot and parenthesis"
    (H.unpack expected) (H.unpack (Open.fingerprint saved))
  let wireRaw encode = encode (W.VNode 1 []) "raw" "checked" checkedSpine
  plainQuery <- right (W.planGraph W.defaultLimits [wireRaw Open.encodeRaw])
  compactQuery <- right (W.planGraph W.defaultLimits [wireRaw Open.encodeCheckedRaw])
  let payload graph = do
        W.GNode 425 [_,i] <- right (W.lookupGraphNode graph (head (W.graphRoots graph)))
        W.GNode kind [_,_,_,_,term,_,_] <- right (W.lookupGraphNode graph i)
        pure (kind,term)
  (oldTag,oldBody) <- payload plainQuery
  (newTag,newBody) <- payload compactQuery
  check "versioned private query body" (400,442) (oldTag,newTag)
  oldTerm <- right (Structure.fromGraphXTerm plainQuery oldBody)
  newTerm <- right (Structure.storedTermWith True True compactQuery newBody)
  oldBytes <- encoded (W.encode W.defaultLimits 6 [Structure.toXTerm oldTerm])
  newBytes <- encoded (W.encode W.defaultLimits 6 [Structure.toXTerm newTerm])
  check "raw query storage restores exact checked syntax" oldBytes newBytes
  unless (rejected (Structure.storedTermFor True compactQuery newBody)) (fail "old query reader admitted a spine")
  do
    let pubVar = T.XTyVar 713
        pubOp = T.XName (-18) "polymorphic"
        pubOwner = T.XName 108 "result"
        pubLeaf ty = T.XThen (T.XInner (T.XBottom ty)) T.XElim
        pubTy = T.XForall (T.XTyVar 41) T.XBot (T.XCon "Int" [])
        pubRhs ev = T.XTypeAbs pubVar T.XBot (T.XTypeApp (T.XVarTerm pubOp) ev)
        pubDecl ev = T.XLet pubOwner (pubRhs ev) (T.XConstructor "()" [])
    pubEnv <- right (Open.environment [])
    forM_ [pubLeaf (T.XCon "Int" []),pubLeaf (T.XVar pubVar)] $ \ev -> do
      before <- right (Open.check pubEnv [(pubOp,pubTy)] (pubDecl ev))
      packed <- Open.makeCheckedPackage "retained-proof" "owner" [("group",before)] >>= right
      [(_,after)] <- pure (Open.packageFragments packed)
      forM_ [0,461,maxBound-8] $ \serial -> do
        let imports = M.singleton pubOp (T.XName 328 "foreign")
            (a,ab,at) = Open.linkBody serial imports before
            (b,bb,bt) = Open.linkBody serial imports after
            asWire names body = Structure.toXTerm body :
              [W.VNode 301 [Structure.toXName n,Structure.toXType ty] | (n,ty) <- names]
        expected <- encoded (W.encode W.defaultLimits 8 (asWire ab at))
        actual <- encoded (W.encode W.defaultLimits 8 (asWire bb bt))
        check "retained ground and bound-variable proofs preserve fresh serial, export IDs and the linked term" (a,expected) (b,actual)
  -- A type argument is part of the literal template's identity. Count both
  -- UTF-8 strings and all nodes of its original, fully explicit evidence.
  let unary v t = T.XTypeApp (T.XVarTerm v) (T.XThen (T.XInner (T.XBottom t)) T.XElim)
      ground n hint tyName = W.VNode 85 [W.VInt n, W.VText hint, W.VText tyName]
      hints = [(-4,"xλ","型"),(-4,"x😀","型"),(-4,"xλ","Int"),(9,"xλ","型")]
      groundRows = [ground n h t | (n,h,t) <- hints]
      leaves = [T.XApp (unary (T.XName n h) (T.XCon t [])) (T.XIntTerm 11) | (n,h,t) <- hints]
      logical = foldr1 T.XApp leaves
      -- Keep the first-use table order explicit, including collisions in
      -- both the printed hint and the numeric variable identity.
      shared = T.XApp logical logical
      cells = [hole,groundRows!!0,join 1 0,groundRows!!1,join 3 0,groundRows!!2,join 5 0,
               groundRows!!3,join 7 0,join 6 8,join 4 9,join 2 10,join 11 11]
      raw = pattern cells [W.VNode 89 [W.VInt 11,W.VInt 0,W.VInt 8]] 12
      ordinary = Structure.toXTerm shared
      charge txt remain = let size = H.v_stringUtf8Length txt in
          if size > remain then T.Nothing else T.Just (remain - size)
      geom stored nodes work depth value = case Source.finalGeometryWith stored charge depth
          [(1,False,[value])] nodes work False of
        T.Nothing -> Nothing
        T.Just answer -> Just answer
  wire <- right (W.planGraph W.defaultLimits [raw,raw])
  original <- right (W.planGraph W.defaultLimits [ordinary,ordinary])
  expanded <- right (W.graphExpandedWork original)
  _ <- right (Structure.admitPatternsFor True wire expanded)
  unless (rejected (Structure.admitPatternsFor True wire (expanded-1))) (fail "ground occurrence UTF-8 work")
  unless (rejected (Structure.admitPatterns wire expanded)) (fail "ground rows crossed the schema-9 boundary")
  loaded <- right (Structure.storedTermFor True wire (head (W.graphRoots wire)))
  check "ground argument identity, hint, evidence and spelling" (H.unpack (Pretty.prettyTerm shared)) (H.unpack (Pretty.prettyTerm loaded))
  forM_ [1..16] $ \depth ->
    forM_ [10,98,99,104,119,120,121,128,160,240] $ \nodes ->
      forM_ [19,120,160,211,218,224,260,512] $ \work ->
        check "ground finalization geometry" (geom False nodes work depth ordinary) (geom True nodes work depth raw)
  forM_ [W.VNode 85 [],W.VNode 85 [W.VInt 9,W.VInt 0,W.VText "Int"],W.VNode 85 [W.VText "x",W.VText "x",W.VText "Int"]] $ \bad -> do
    fixture <- right (W.planGraph W.defaultLimits [pattern (hole:bad:drop 2 cells) [W.VNode 89 [W.VInt 11,W.VInt 0,W.VInt 8]] 12])
    unless (rejected (Structure.storedTermFor True fixture (head (W.graphRoots fixture)))) (fail "malformed ground atom")
  let f = T.XName 0 "fλ"; variable = T.XTyVar 42
      scheme = T.XForall variable T.XBot (T.XArrow (T.XVar variable) (T.XVar variable))
      xs = [-9..23]
      source = T.XLet result (tree [T.XApp (unary f ty) (T.XIntTerm n) | n <- xs]) (T.XConstructor "()" [])
      parameters = Separate.pack [Separate.pack ["0","fλ",Pretty.prettyType (Separate.normalType scheme)]]
      exported = Separate.pack [Separate.pack ["export😀","Int"]]
  verified <- right (Open.check env [(f,scheme)] source)
  check "checked ground fingerprint" (H.unpack (Separate.fingerprint (Separate.pack [Separate.pack [],parameters,Pretty.prettyTerm source,exported]))) (H.unpack (Open.fingerprint verified))
  persisted <- right (W.planGraph W.defaultLimits [Open.encodeRaw (W.VNode 1 []) "raw" "unit" verified])
  W.GNode 425 [_,record] <- right (W.lookupGraphNode persisted (head (W.graphRoots persisted)))
  W.GNode 441 [_,_,_,_,stored,_,_] <- right (W.lookupGraphNode persisted record)
  got <- right (Structure.storedTermFor True persisted stored)
  check "checked ground application roundtrip" (H.unpack (Pretty.prettyTerm source)) (H.unpack (Pretty.prettyTerm got))
  let unused = T.XName (-74) "unused"; local = T.XName 65 "input"
      linked serial imports fragment = let (end, bindings, term) = Open.linkBody serial imports fragment
        in (end, [(H.unpack (Pretty.name n), H.unpack (Pretty.prettyType t)) | (n,t) <- bindings],
            H.unpack (Pretty.prettyTerm term))
  forM_ [9,10] $ \version -> do
    let qualified = version == 10
        shown i = if even i then f else T.XName 0 "same identity, another hint"
        leaf i n = let ref = shown i
                       value = add (T.XVarTerm local) (T.XIntTerm n)
                   in if qualified then T.XApp (unary ref ty) value else add (T.XVarTerm ref) value
        values = take 33 (iterate (+1) (maxBound-5))
        rhs = T.XAbs local ty (tree (zipWith leaf [0 :: Int ..] values))
        body = T.XLet result rhs (T.XConstructor "()" [])
    logical <- right (Open.check env [(f,if qualified then scheme else ty),(unused,ty)] body)
    package <- Open.makePackage "link-test" "owner" [("group",logical)] >>= right
    let bytes = Open.packageBytes package
        contracts = M.fromList H.v_compareString
          [(hint,Separate.normalType t) | (T.XName _ hint,t) <- Open.parameters logical ++ Open.bindings logical]
    _ <- W.decodeGraph W.defaultLimits version bytes >>= right
    restored <- Open.readPackage bytes (Open.packageHash package) "link-test" "owner" contracts M.empty >>= right
    forM_ [package,restored] $ \actual -> do
      [("group",fragment)] <- pure (Open.packageFragments actual)
      forM_ [0,401,maxBound-8] $ \serial ->
        forM_ [M.empty,M.singleton f (T.XName 200 "imported")] $ \imports ->
          check "linked application rows retain identity allocation, hints and signed literals"
            (linked serial imports logical) (linked serial imports fragment)
  graph <- right (W.planGraph W.defaultLimits [good,good])
  unless (rejected (Structure.admitPatterns graph 45)) (fail "expanded work for repeated application roots")
  _ <- right (Structure.admitPatterns graph 46)
  pure ()

main = do
  childBytes <- Prim.newByteArray 4 0
  forM_ (zip [0..] [224,134,1,102]) $ \(i,b) -> Prim.writeByteArray childBytes i b
  let readChildren end = case W.getEntry W.defaultLimits 3 1 5 1 3 of
        W.Read action -> do
          outcome <- action (W.Cursor childBytes 5 end)
          pure $ case outcome of
            T.Right (W.ENode tag children,W.Cursor _ after _) -> Right (tag,children,after)
            T.Left msg -> Left (H.unpack msg)
            _ -> error "expected a binary node"
  check "unaligned short node retains child order and consumes each field" (Right (13,[4,1,3],32)) =<< readChildren 32
  check "child section length is checked before its fields" (Left "truncated binary child references") =<< readChildren 31
  Prim.writeByteArray childBytes 3 126
  check "short node rejects its forward second child"
    (Left "binary node has a forward, cyclic, or out-of-range reference") =<< readChildren 32
  -- Corrupt a symbol in a full frame. The integrity error takes precedence
  -- over the invalid UTF-8, including when the caller supplies a text hint.
  forM_ [24,900,1300] $ \width -> do
    let spelling = H.literal (replicate width 'q')
        requireGraph action = action >>= \value -> case value of
          T.Right graph -> pure graph
          T.Left msg -> fail (H.unpack msg)
    bytes <- W.encode W.defaultLimits 7 [W.VText spelling] >>= \encoded -> case encoded of
      T.Right value -> pure value
      T.Left msg -> fail (H.unpack msg)
    let offset = if width < 128 then 81 else 82
    graph <- requireGraph (W.decodeGraphWithText [spelling] W.defaultLimits 7 bytes)
    case W.lookupGraphNode graph (head (W.graphRoots graph)) of
      T.Right (W.GText value) -> check "decoded symbol across integrity threshold" (H.unpack spelling) (H.unpack value)
      _ -> fail "expected decoded symbol"
    Prim.writeByteArray bytes offset 255
    forM_ [[],[spelling]] $ \hints -> do
      result <- W.decodeGraphWithText hints W.defaultLimits 7 bytes
      case result of
        T.Left msg -> check "complete frame checksum precedes symbol decoding" "binary checksum mismatch" (H.unpack msg)
        T.Right _ -> fail "accepted corrupted symbol bytes"
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
  let sourceTuples = ["(" ++ replicate (arity-1) ',' ++ ")" | arity <- [2..64]]
      sourceTypes = "()" : "[]" : sourceTuples
      otherNames = ["(:)", ":", "Leaf", "Prelude.()", "MLFLegacyUnit", "List", "True",
                    "()", "[]", "(" ++ replicate 64 ',' ++ ")", "λ"]
  forM_ (sourceTypes ++ otherNames) $ \name -> do
    let s = H.literal name
    check ("wired source type " ++ name) (name `elem` sourceTypes) (Data.sourceBuiltinType s)
    check ("wired source constructor " ++ name) (name `elem` (":" : sourceTypes)) (Data.sourceBuiltinConstructor s)
  orderedSyntaxChecks
  lexicalRunChecks
  layoutTokenChecks
  loweringChecks
  resolverChecks
  protectionChecks
  projectedBindingChecks
  fragmentFingerprintChecks
  applicationPatternChecks
  importConventionChecks
  typedClassChecks
  signedDataChecks
  signedLocalChecks
  knownConstructorFoldChecks
  openGeometryChecks
  signedConstructorChecks
  putStrLn "1032 ordered SCC and reach comparisons, query DAG and package controls passed"
