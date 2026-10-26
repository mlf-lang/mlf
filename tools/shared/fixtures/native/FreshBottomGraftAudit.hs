{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Monad (forM_, unless)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified MLF.Host.Base as B

right :: String -> T.Either B.String a -> IO a
right label value = case value of
  T.Left message -> fail (label ++ ": " ++ B.unpack message)
  T.Right answer -> pure answer

sameGraph :: T.Graph -> T.Graph -> Bool
sameGraph left rightGraph =
  IM.eqIntMap G.equalNode (G.nodes left) (G.nodes rightGraph) &&
  IM.eqIntMap (==) (G.links left) (G.links rightGraph) &&
  G.nextId left == G.nextId rightGraph

firstRequired :: [a] -> a
firstRequired values = case values of
  first:_ -> first
  [] -> error "audit fixture did not construct its prescribed fresh nodes"

finish :: T.Either B.String T.Solver -> T.Either B.String T.Graph
finish value = case value of
  T.Left message -> T.Left message
  T.Right solver -> S.finish solver

sameOutcome :: String -> T.Either B.String T.Graph -> T.Either B.String T.Graph -> IO ()
sameOutcome label expected actual = case (expected, actual) of
  (T.Left first, T.Left second) ->
    unless (B.v_eqString first second) (fail (label ++ ": changed rejection: " ++ B.unpack first ++ " / " ++ B.unpack second))
  (T.Right first, T.Right second) -> do
    unless (sameGraph first second) (fail (label ++ ": changed full graph, aliases, binders, flags or fresh counter"))
    _ <- right (label ++ " validate reference") (G.validateGraph first)
    _ <- right (label ++ " validate candidate") (G.validateGraph second)
    pure ()
  (T.Left message, T.Right _) -> fail (label ++ ": accepted rejected input: " ++ B.unpack message)
  (T.Right _, T.Left message) -> fail (label ++ ": rejected accepted input: " ++ B.unpack message)

node :: T.GTag -> Integer -> T.Flag -> T.Node
node tag parent flag = T.Node tag (T.Just parent) flag

-- These hand-authored graphs do not call expansion, graft or source inference
-- to construct their expected topology. Shared variables and nested binders
-- deliberately retain different identities and permissions.
poly :: T.Graph
poly = T.Graph (IM.fromList
  [ (0, T.Node (T.GGen 1) T.Nothing T.Flexible)
  , (1, node (T.GCon "Int" []) 0 T.Rigid)
  , (2, node (T.GGen 3) 0 T.Flexible)
  , (3, node (T.GArr 4 5) 2 T.Flexible)
  , (4, node T.GBot 2 T.Flexible)
  , (5, node (T.GArr 4 6) 3 T.Rigid)
  , (6, node (T.GCon "Int" []) 5 T.Rigid)
  , (7, node (T.GGen 8) 0 T.Flexible)
  , (8, node T.GBot 7 T.Flexible)
  ]) IM.empty 9

replace :: Integer -> T.Node -> T.Graph -> T.Graph
replace identity value graph = T.Graph (IM.insert identity value (G.nodes graph))
  (G.links graph) (max (G.nextId graph) (identity + 1))

without :: [Integer] -> T.Graph -> T.Graph
without identities graph = T.Graph (foldr IM.delete (G.nodes graph) identities)
  (G.links graph) (G.nextId graph)

rename :: (Integer -> Integer) -> T.Graph -> T.Graph
rename image graph = T.Graph
  (IM.fromList [(image identity, T.Node (G.mapTag image (G.tag value))
      (G.mapMaybeInt image (G.binder value)) (G.flag value))
    | (identity, value) <- IM.toList (G.nodes graph)])
  (IM.fromList [(image identity, image target) | (identity,target) <- IM.toList (G.links graph)])
  (image (G.nextId graph))

cases :: [(String, Bool, T.Graph)]
cases =
  [ ("shared-quantifier", True, poly)
  , ("nested-flexible-quantifier", True, replace 4 (node T.GBot 3 T.Flexible) poly)
  , ("protected-nested-quantifier", True,
      replace 5 (node (T.GArr 6 6) 3 T.Rigid) (replace 6 (node T.GBot 5 T.Flexible) poly))
  , ("rigid-source-root", True, replace 3 (node (T.GArr 4 5) 2 T.Rigid) poly)
  , ("higher-kind-application", True,
      replace 3 (node (T.GTyApp 4 5) 2 T.Flexible)
      (replace 4 (node (T.GTyCon "List" (T.KArrow T.Star T.Star)) 3 T.Rigid)
      (replace 5 (node T.GBot 3 T.Flexible) (without [6] poly))))
  , ("higher-kind-bottom", True,
      replace 3 (node (T.GBotK (T.KArrow T.Star T.Star)) 2 T.Flexible)
      (replace 8 (node (T.GBotK (T.KArrow T.Star T.Star)) 7 T.Flexible) (without [4,5,6] poly)))
  , ("explicit-star-source-bottom", True, replace 3 (node (T.GBotK T.Star) 2 T.Flexible) (without [4,5,6] poly))
  , ("explicit-star-target-bottom", True,
      replace 3 (node T.GBot 2 T.Flexible) (replace 8 (node (T.GBotK T.Star) 7 T.Flexible) (without [4,5,6] poly)))
  , ("external-frontier", True, replace 4 (node T.GBot 0 T.Flexible) poly)
  , ("rigid-target", False, replace 8 (node T.GBot 7 T.Rigid) poly)
  , ("kind-mismatch", False, replace 8 (node (T.GBotK (T.KArrow T.Star T.Star)) 7 T.Flexible) poly)
  , ("incoming-target-structural-reference", True,
      replace 7 (node (T.GGen 9) 0 T.Flexible)
      (replace 9 (node (T.GArr 8 10) 7 T.Flexible)
      (replace 10 (node (T.GCon "Int" []) 9 T.Rigid) poly)))
  , ("green-target-under-type-binder", False,
      replace 7 (node (T.GGen 9) 0 T.Flexible)
      (replace 9 (node (T.GArr 8 10) 7 T.Flexible)
      (replace 8 (node T.GBot 9 T.Flexible)
      (replace 10 (node (T.GCon "Int" []) 9 T.Rigid) poly))))
  , ("rigid-target-intermediary", False,
      replace 7 (node (T.GGen 9) 0 T.Flexible)
      (replace 9 (node (T.GArr 8 10) 7 T.Rigid)
      (replace 8 (node T.GBot 9 T.Flexible)
      (replace 10 (node (T.GCon "Int" []) 9 T.Rigid) poly))))
  ]

check :: String -> Bool -> T.Graph -> Integer -> Integer -> IO ()
check label wanted original source target = do
  initial <- right (label ++ " prepare") (S.prepare original)
  (root, _, frontier, expanded) <- right (label ++ " expansion") (S.expanded source target initial)
  let admitted = S.expansionBottomGraft (G.nextId original) target root frontier expanded
  case admitted of
    T.Nothing -> unless (not wanted) (fail (label ++ ": fast path was not exercised"))
    T.Just result -> do
      unless wanted (fail (label ++ ": guard admitted an excluded graph"))
      -- Independent raw graph unification bypasses the component solver and
      -- its projection/restoration machinery entirely.
      let expected = G.unify (frontier ++ [(root,target)]) (S.graph expanded)
      sameOutcome (label ++ " raw reference") expected (S.finish result)
  sameOutcome (label ++ " component reference")
    (finish (S.instantiate source target initial))
    (finish (S.instantiateWithFreshBottom source target initial))
  putStrLn ("PASS " ++ label)

frontierControls :: IO ()
frontierControls = do
  let external = replace 4 (node T.GBot 0 T.Flexible) poly
      rooted tag flag = replace 3 (node tag 0 flag) (without [4,5,6] poly)
      rootSkolem = rooted (T.GSkolem 42 T.Star) T.Rigid
      incoming = replace 7 (node (T.GGen 9) 0 T.Flexible)
        (replace 9 (node (T.GArr 8 3) 7 T.Flexible) rootSkolem)
      twoExternal = replace 6 (node (T.GSkolem 43 T.Star) 0 T.Rigid) external
  forM_
    [ ("frontier-orange-original", True, replace 4 (node (T.GSkolem 41 T.Star) 0 T.Rigid) poly)
    , ("frontier-two-originals", True, twoExternal)
    , ("frontier-root-flexible-bottom", True, rooted T.GBot T.Flexible)
    , ("frontier-root-rigid-skolem", True, rootSkolem)
    , ("frontier-root-existing-target-parent", True, incoming)
    , ("frontier-root-explicit-star-source", False, rooted (T.GBotK T.Star) T.Flexible)
    , ("frontier-root-explicit-star-target", False,
        replace 8 (node (T.GBotK T.Star) 7 T.Flexible) (rooted T.GBot T.Flexible))
    , ("frontier-explicit-star-source", False, replace 4 (node (T.GBotK T.Star) 0 T.Flexible) poly)
    , ("frontier-root-kind-mismatch", False,
        replace 8 (node (T.GBotK (T.KArrow T.Star T.Star)) 7 T.Flexible) rootSkolem)
    , ("frontier-original-descendant-scope", False,
        replace 4 (node T.GBot 11 T.Flexible)
        (replace 2 (node (T.GGen 3) 11 T.Flexible)
        (replace 11 (node (T.GGen 4) 0 T.Flexible) poly)))
    ] $ \(label,wanted,graph) -> check label wanted graph 2 8
  let identity n = if n == 3 then 13 else if n == 9 then 14 else n
  check "frontier-root-younger-original" False (rename identity rootSkolem) 2 8
  let identityTarget tag = replace 2 (node (T.GGen 8) 0 T.Flexible)
        (replace 8 (node tag 0 T.Flexible) (without [3,4,5,6] poly))
      identitySkolem = replace 8 (node (T.GSkolem 45 T.Star) 0 T.Rigid)
        (identityTarget T.GBot)
  check "frontier-root-already-target" True (identityTarget T.GBot) 2 8
  check "frontier-identity-rigid-skolem" True identitySkolem 2 8
  check "frontier-identity-existing-children" True
    (replace 9 (node T.GBot 8 T.Flexible)
    (replace 10 (node (T.GCon "Int" []) 8 T.Rigid)
    (identityTarget (T.GArr 9 10)))) 2 8
  check "frontier-identity-explicit-star" False (identityTarget (T.GBotK T.Star)) 2 8
  check "frontier-identity-existing-aliases" True
    (T.Graph (G.nodes identitySkolem) (IM.fromList [(11,2),(12,8),(13,12)]) 14) 11 13
  let aliased = T.Graph (G.nodes rootSkolem) (IM.fromList [(11,2),(12,8),(13,12)]) 14
  check "frontier-existing-alias-chain" True aliased 11 13
  initial <- right "frontier guard prepare" (S.prepare external)
  (root, _, frontier, expanded) <- right "frontier guard expansion" (S.expanded 2 8 initial)
  let underType = S.withGraph
        (replace 4 (node T.GBot 1 T.Flexible) (S.graph expanded)) expanded
  case S.frontierBottomGraft (G.nextId external) 8 root frontier underType of
    T.Nothing -> putStrLn "PASS frontier-original-under-rigid-type"
    T.Just _ -> fail "frontier-original-under-rigid-type: malformed source bypassed guard"

congruenceControls :: IO ()
congruenceControls = do
  let shaped = replace 8 (node (T.GArr 9 10) 7 T.Flexible)
        (replace 9 (node T.GBot 8 T.Flexible)
        (replace 10 (node (T.GArr 9 11) 8 T.Rigid)
        (replace 11 (node (T.GCon "Int" []) 10 T.Rigid) poly)))
      sharedFresh flag = let tag = if G.equalFlag flag T.Rigid then T.GCon "Int" [] else T.GBot
        in replace 5 (node (T.GArr 6 6) 3 T.Flexible)
        (replace 6 (node tag 3 flag)
        (replace 4 (node tag 2 flag)
        (replace 9 (node tag 8 flag)
        (replace 10 (node (T.GArr 9 9) 8 T.Flexible) (without [11] shaped)))))
      frontier = replace 4 (node T.GBot 0 T.Flexible)
        (replace 8 (node (T.GArr 4 10) 7 T.Flexible)
        (replace 10 (node (T.GArr 4 11) 8 T.Rigid) (without [9] shaped)))
      protected = replace 5 (node (T.GArr 6 6) 3 T.Rigid)
        (replace 6 (node T.GBot 5 T.Flexible)
        (replace 10 (node (T.GArr 11 11) 8 T.Rigid)
        (replace 11 (node T.GBot 10 T.Flexible) shaped)))
      cyclic = replace 3 (node (T.GArr 4 4) 2 T.Flexible) (without [5,6] shaped)
      rigidInstantiation = replace 4 (node T.GBot 2 T.Rigid)
        (replace 9 (node (T.GCon "Int" []) 8 T.Rigid) shaped)
  forM_
    [ ("congruence-shared-local", True, shaped)
    , ("congruence-flexible-variable-instance", True,
        replace 9 (node (T.GCon "Int" []) 8 T.Rigid) shaped)
    , ("congruence-many-fresh-one-flexible-original", True, sharedFresh T.Flexible)
    , ("congruence-many-fresh-one-orange-original", True, sharedFresh T.Rigid)
    , ("congruence-frontier-descendant", True, frontier)
    , ("congruence-sharing-conflict", False,
        replace 10 (node (T.GArr 12 11) 8 T.Rigid)
        (replace 12 (node T.GBot 8 T.Flexible) shaped))
    , ("congruence-binder-capture", False, replace 9 (node T.GBot 7 T.Flexible) shaped)
    , ("congruence-flag-change", False, replace 10 (node (T.GArr 9 11) 8 T.Flexible) shaped)
    , ("congruence-protected-flexible", False, protected)
    , ("congruence-rigid-variable-instantiation", False, rigidInstantiation)
    , ("congruence-old-cycle-equations", False, cyclic)
    , ("congruence-frontier-capture", False, replace 4 (node T.GBot 0 T.Flexible) shaped)
    ] $ \(label,wanted,graph) -> check label wanted graph 2 8
  check "congruence-target-alias-chain" True
    (T.Graph (G.nodes shaped) (IM.fromList [(30,2),(31,8),(32,31)]) 33) 30 32
  initial <- right "rigid rejection prepare" (S.prepare rigidInstantiation)
  case S.instantiateWithFreshBottom 2 8 initial of
    T.Left message -> unless (B.v_eqString message "cannot instantiate a rigid or protected type variable")
      (fail ("rigid rejection changed diagnostic: " ++ B.unpack message))
    T.Right _ -> fail "rigid variable was instantiated despite matching structure"
  putStrLn "PASS congruence-rigid-variable-rejection-diagnostic"


-- A long type spine with one argument variable shared by every arrow checks
-- reuse of overlapping subgraphs, rather than only small tree-shaped types.
congruenceKindControls :: IO ()
congruenceKindControls = do
  let depth = 64
      chain first parent childParent =
        [ (first + offset, node (T.GArr (first + depth)
            (if offset + 1 == depth then first + depth else first + offset + 1))
            (if offset == 0 then parent else childParent) T.Flexible)
        | offset <- [0 .. depth - 1]] ++
        [(first + depth, node T.GBot childParent T.Flexible)]
      long = T.Graph (IM.fromList
        ([(0, T.Node (T.GGen 1) T.Nothing T.Flexible),
          (1, node (T.GCon "Int" []) 0 T.Rigid),
          (2, node (T.GGen 10) 0 T.Flexible),
          (3, node (T.GGen 1000) 0 T.Flexible)] ++
         chain 10 2 2 ++ chain 1000 3 1000)) IM.empty 1065
      higher = replace 3 (node (T.GBotK (T.KArrow T.Star T.Star)) 2 T.Flexible)
        (replace 8 (node (T.GTyCon "List" (T.KArrow T.Star T.Star)) 7 T.Rigid)
        (without [4,5,6] poly))
  check "congruence-long-shared-arrow-spine" True long 2 1000
  check "congruence-long-spine-aliases" True
    (T.Graph (G.nodes long) (IM.fromList [(2000,2),(2001,1000),(2002,2001)]) 2003) 2000 2002
  check "congruence-higher-kind-instance" True higher 2 8
  check "congruence-higher-kind-instance-mismatch" False
    (replace 8 (node (T.GTyCon "Int" T.Star) 7 T.Rigid) higher) 2 8
  initial <- right "kind cycle prepare" (S.prepare
    (replace 3 (node T.GBot 2 T.Flexible)
    (replace 8 (node (T.GCon "Int" []) 7 T.Flexible) (without [4,5,6] poly))))
  (root, _, frontier, expanded) <- right "kind cycle expansion" (S.expanded 2 8 initial)
  let cyclic = replace 8 (node (T.GArr 8 8) 7 T.Flexible) (S.graph expanded)
  case G.unify (frontier ++ [(root,8)]) cyclic of
    T.Right _ -> fail "malformed old kind cycle was unexpectedly accepted by the reference"
    T.Left _ -> pure ()
  case S.congruentExpansionGraft (G.nextId (S.graph initial)) 8 root frontier
         (S.withGraph cyclic expanded) of
    T.Just _ -> fail "malformed old kind cycle was admitted by congruent reuse"
    T.Nothing -> putStrLn "PASS congruence-malformed-old-kind-cycle"

-- The validation oracle retains the original identities and delegates directly
-- to the public graph validator. Only duplicate IDs and anchor collisions are
-- separately rejected as malformed fragment inputs outside the prepared domain.
fragmentNodes :: [(Integer, T.Node)]
fragmentNodes = [(10,node (T.GArr 11 12) 0 T.Flexible), (11,node T.GBot 10 T.Flexible), (12,node (T.GCon "Int" []) 10 T.Rigid)]
replaceFragment :: Integer -> T.Node -> [(Integer, T.Node)] -> [(Integer, T.Node)]
replaceFragment i n = map (\(j,v) -> if i == j then (j,n) else (j,v))
fragmentReference :: Integer -> T.Maybe Integer -> [(Integer, T.Node)] -> Integer -> Bool
fragmentReference root parent fresh next = case parent of
  T.Nothing -> False
  T.Just scope -> case G.validateGraph (T.Graph
      (IM.insert scope (T.Node (T.GGen root) T.Nothing T.Flexible) (IM.fromList fresh)) IM.empty next) of
    T.Left _ -> False
    T.Right _ -> True
fragmentValidationControls :: IO ()
fragmentValidationControls = do
  let cases =
        [("valid",True,10,T.Just 0,fragmentNodes),
         ("missing-root",False,99,T.Just 0,fragmentNodes),
         ("missing-scope",False,10,T.Nothing,fragmentNodes),
         ("missing-structural-node",False,10,T.Just 0,replaceFragment 10 (node (T.GArr 11 99) 0 T.Flexible) fragmentNodes),
         ("missing-binder",False,10,T.Just 0,replaceFragment 11 (node T.GBot 99 T.Flexible) fragmentNodes),
         ("structural-cycle",False,10,T.Just 0,replaceFragment 10 (node (T.GArr 10 12) 0 T.Flexible) fragmentNodes),
         ("binding-cycle",False,10,T.Just 0,replaceFragment 10 (node (T.GArr 11 12) 11 T.Flexible) fragmentNodes),
         ("invalid-type-binder",False,10,T.Just 0,replaceFragment 11 (node T.GBot 12 T.Flexible) fragmentNodes),
         ("extra-binding-root",False,10,T.Just 0,replaceFragment 11 (T.Node T.GBot T.Nothing T.Flexible) fragmentNodes),
         ("generalization-child",False,10,T.Just 0,replaceFragment 11 (node (T.GGen 12) 10 T.Flexible) fragmentNodes),
         ("invalid-arrow-kind",False,10,T.Just 0,replaceFragment 11 (node (T.GBotK (T.KArrow T.Star T.Star)) 10 T.Flexible) fragmentNodes),
         ("rigid-root",True,10,T.Just 0,replaceFragment 10 (node (T.GArr 11 12) 0 T.Rigid)
          (replaceFragment 11 (node T.GBot 10 T.Rigid) fragmentNodes)),
         ("protected-variable",True,10,T.Just 0,replaceFragment 10 (node (T.GArr 11 12) 0 T.Rigid) fragmentNodes),
         ("higher-kind-application",True,10,T.Just 0,
          replaceFragment 10 (node (T.GTyApp 11 12) 0 T.Flexible)
          (replaceFragment 11 (node (T.GTyCon "List" (T.KArrow T.Star T.Star)) 10 T.Rigid) fragmentNodes)),
         ("unused-direct-gen-node",True,10,T.Just 0,fragmentNodes++[(13,node T.GBot 0 T.Flexible)])]
  forM_ [("ordinary",1,0),("sparse",100003,-9001),("huge",1,10^40),("negative",1,negate (10^40))] $ \(prefix,scale,offset) ->
    forM_ cases $ \(label,wanted,root,parent,fresh) -> do
      let image n = n*scale+offset
          nodes = [(image n,T.Node (G.mapTag image (G.tag v)) (G.mapMaybeInt image (G.binder v)) (G.flag v)) | (n,v)<-fresh]
          r=image root; b=G.mapMaybeInt image parent; next=image 100
          old=fragmentReference r b nodes next; new=S.validFreshFragment r b nodes next
      unless (old==wanted && new==wanted) (fail (prefix++"/"++label++": validity changed"))
      putStrLn ("PASS fragment-"++prefix++"/"++label)
  forM_ [("duplicate-node",10,T.Just 0,fragmentNodes++[(11,node T.GBot 10 T.Flexible)]),
         ("anchor-collision",10,T.Just 10,fragmentNodes)] $ \(label,root,parent,fresh) -> do
    unless (not (S.validFreshFragment root parent fresh 100)) (fail (label++": malformed input admitted"))
    putStrLn ("PASS fragment-"++label)

guardControls :: IO ()
guardControls = do
  initial <- right "guard prepare" (S.prepare poly)
  (root, _, frontier, expanded) <- right "guard expansion" (S.expanded 2 8 initial)
  let graph = S.graph expanded
      first = G.nextId poly
      fresh = S.allocatedNodes first (G.nextId graph) (G.nodes graph)
      other = firstRequired [identity | (identity,_) <- fresh, identity /= root]
      later = firstRequired [identity | (identity,_) <- fresh, identity /= root, identity /= other]
      unchanged old = S.withGraph old expanded
      mutations =
        [ ("fresh-root-binder-mismatch", replace root (node (G.tag (G.nodeAt graph root)) 0 T.Flexible) graph)
        , ("fresh-generalization-node", replace other (node (T.GGen other) root T.Flexible) graph)
        , ("fresh-external-binder", replace other (node (G.tag (G.nodeAt graph other)) 0 T.Flexible) graph)
        , ("fresh-external-edge", replace root (node (T.GArr other 1) 7 T.Flexible) graph)
        , ("fresh-missing-edge", replace root (node (T.GArr other 999999) 7 T.Flexible) graph)
        , ("fresh-invalid-internal-binder", replace later (node (G.tag (G.nodeAt graph later)) other T.Flexible) graph)
        ]
  forM_ mutations $ \(label, changed) -> case S.freshBottomGraft first 8 root frontier (unchanged changed) of
    T.Nothing -> putStrLn ("PASS " ++ label)
    T.Just _ -> fail (label ++ ": malformed expansion was admitted")
  let T.Solver expandedGraph expandedParents expandedChildren expandedScopes = expanded
      boundTarget = T.Solver expandedGraph expandedParents
        (IM.insert 8 (IS.singleton 123456) expandedChildren) expandedScopes
  case S.freshBottomGraft first 8 root frontier boundTarget of
    T.Nothing -> putStrLn "PASS existing-target-binding-child"
    T.Just _ -> fail "existing-target-binding-child: guard was bypassed"
  -- The final solver check remains mandatory and independently audits every
  -- index, including untouched/disconnected entries. The shortcut never
  -- repairs a stale original structural-parent entry into successful evidence.
  let T.Solver old parents children scopes = initial
      stale = T.Solver old (IM.insert 123456 (IS.singleton 654321) parents) children scopes
  sameOutcome "malformed-disconnected-index"
    (finish (S.instantiate 2 8 stale))
    (finish (S.instantiateWithFreshBottom 2 8 stale))
  putStrLn "PASS malformed-disconnected-index"

main :: IO ()
main = do
  forM_ cases $ \(label,wanted,graph) -> check label wanted graph 2 8
  forM_ [("sparse",100003,-9001), ("huge",1,10^40), ("negative",1,-10^40)] $ \(name,scale,offset) ->
    forM_ (take 8 cases) $ \(label,wanted,graph) -> do
      let image n = scale*n+offset
      check (name ++ "-" ++ label) wanted (rename image graph) (image 2) (image 8)
  let aliased = T.Graph (G.nodes poly) (IM.fromList [(11,2),(12,8)]) 13
  check "source-and-target-aliases" True aliased 11 12
  guardControls
  frontierControls
  congruenceControls
  congruenceKindControls
  fragmentValidationControls
  putStrLn "Fresh bottom graft audit: 146 checks passed"
