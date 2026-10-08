-- | Incremental, scope-preserving use of the checked graph unifier.
--
-- Type components are closed under structural edges in BOTH directions and
-- type binding edges in BOTH directions. Gen nodes stop this closure. Their
-- binding ancestry is projected with every relevant type-binding LCA intact;
-- unary empty Gen chains can be compressed and restored after unification.
-- A Gen cannot be merged or be a structural child; its binding parent must
-- therefore also be a Gen.
-- Permissions of type nodes stop at Gens, and their inertness depends only
-- on binding descendants inside the component. Consequently the projection
-- preserves every relevant permission, structural parent and binding LCA.
-- Unrelated Gen roots are represented by private bottom leaves, then restored.
-- Neither these leaves nor compact scratch identities escape into the graph.
module MLF.Graph.Solver
  ( Solver, prepare, graph, finish, unify, instantiate, instantiateClosed, witness ) where

import Control.Monad (forM, forM_, unless, when)
import Control.Monad.State.Strict (State, execState, get, put)
import qualified Data.Array as A
import qualified Data.IntMap.Strict as IM
import qualified Data.IntSet as IS
import qualified Data.List as List
import Data.List.NonEmpty (NonEmpty (..))
import qualified Data.List.NonEmpty as NE
import qualified Data.Set as Set
import Data.Maybe (maybeToList)
import MLF.Graph (Graph (..), Node (..), NodeId, Tag (..), children, resolve)
import qualified MLF.Graph as G
import MLF.Syntax (Flag (..))
import MLF.Kind (Kind (..))

type Index = IM.IntMap IS.IntSet

-- The constructor is private: callers cannot mutate a graph without updating
-- its reverse edges, or inject an unchecked graph into the incremental path.
data Solver = Solver
  { solverGraph :: !Graph
  , structuralParents :: !Index
  , bindingChildren :: !Index
  , scopeIndex :: !ScopeIndex
  }

-- Gen binding parents never change during checked component unification or
-- expansion. Number that tree once and retain binary ancestors. A component
-- can then connect its boundary scopes with their LCAs without walking every
-- empty scope between them and the root on every equation.
data ScopeIndex = ScopeIndex !(IM.IntMap (Int,Int)) !(NonEmpty (IM.IntMap NodeId)) deriving Eq

indexScopes :: Graph -> ScopeIndex
indexScopes g = ScopeIndex intervals jumps
  where
    gens = IM.filter (\v -> case tag v of Gen _ -> True; _ -> False) (nodes g)
    parents = IM.mapWithKey (\n v -> maybe n (resolve g) (binder v)) gens
    descendants = IM.fromListWith (++) [(p,[n]) | (n,p) <- IM.toList parents, n /= p]
    roots = [n | (n,p) <- IM.toList parents, n == p]
    visit :: NodeId -> State (Int,IM.IntMap (Int,Int)) ()
    visit n = do
      (start,table) <- get
      put (start+1,table)
      mapM_ visit (IM.findWithDefault [] n descendants)
      (end,table') <- get
      put (end,IM.insert n (start,end) table')
    intervals = snd (execState (mapM_ visit roots) (0,IM.empty))
    -- The highest jump reaches the root even in a maximally deep tree.
    levels = 1 + length (takeWhile (>1) (iterate (\n -> n `div` 2 + n `mod` 2) (IM.size gens)))
    double previous = IM.map (previous IM.!) previous
    jumps = parents :| take (levels-1) (iterate double (double parents))

projectScopes :: ScopeIndex -> IS.IntSet -> IM.IntMap (Maybe NodeId)
projectScopes _ seeds | IS.null seeds = IM.empty
projectScopes (ScopeIndex intervals jumps) seeds = snd (List.foldl' attach ([],IM.empty) ordered)
  where
    contains a b = let (start,end) = intervals IM.! a; (position,_) = intervals IM.! b
                   in start <= position && position < end
    lca a b | contains a b = a
            | contains b a = b
            | otherwise = NE.head jumps IM.! foldr climb a jumps
      where climb level n = let parent = level IM.! n in if contains parent b then n else parent
    sortScopes = List.sortOn (fst . (intervals IM.!)) . IS.toList
    boundary = sortScopes seeds
    closure = seeds `IS.union` IS.fromList
      ([lca a b | (a,b) <- zip boundary (drop 1 boundary)] ++
       [NE.last jumps IM.! n | n <- boundary])
    ordered = sortScopes closure
    attach (ancestors,parents) n =
      let enclosing = dropWhile (\a -> not (contains a n)) ancestors
      in (n:enclosing,IM.insert n (case enclosing of p:_ -> Just p; [] -> Nothing) parents)

-- Export a function, not the record selector: exporting the selector would
-- also permit record updates even though the constructor is private.
graph :: Solver -> Graph
graph = solverGraph

prepare :: Graph -> Either String Solver
prepare input = do
  G.validateGraph input
  unless (IM.disjoint (nodes input) (links input)) (Left "live graph identities cannot also be aliases")
  forM_Keys (nodes input) $ \n -> unless (n < nextId input) (Left "fresh identity counter overlaps graph nodes")
  forM_Keys (links input) $ \n -> unless (n < nextId input) (Left "fresh identity counter overlaps graph aliases")
  let g = input { nodes = IM.map (\v -> v { tag = mapTag (resolve input) (tag v) }) (nodes input) }
  pure (List.foldl' addNode (Solver g IM.empty IM.empty (indexScopes g)) (IM.toAscList (nodes g)))
  where forM_Keys ns f = mapM_ f (IM.keys ns)

-- | Independently check the complete result and the maintained reverse edges.
finish :: Solver -> Either String Graph
finish solver = do
  G.validateGraph (graph solver)
  let indexed = List.foldl' addNode (Solver (graph solver) IM.empty IM.empty (indexScopes (graph solver)))
        (IM.toAscList (nodes (graph solver)))
  unless (structuralParents solver == structuralParents indexed &&
          bindingChildren solver == bindingChildren indexed && scopeIndex solver == scopeIndex indexed)
    (Left "incremental graph index disagrees with the graph")
  pure (graph solver)

addNode :: Solver -> (NodeId,Node) -> Solver
addNode solver (n,v) = solver
  { structuralParents = List.foldl' (\index child -> insert child n index)
      (structuralParents solver) (children (tag v))
  , bindingChildren = List.foldl' (\index parent -> insert parent n index)
      (bindingChildren solver) (maybeToList (binder v))
  }
  where insert key value = IM.insertWith IS.union key (IS.singleton value)

removeNode :: Solver -> (NodeId,Node) -> Solver
removeNode solver (n,v) = solver
  { structuralParents = List.foldl' (\index child -> remove child n index)
      (structuralParents solver) (children (tag v))
  , bindingChildren = List.foldl' (\index parent -> remove parent n index)
      (bindingChildren solver) (maybeToList (binder v))
  }
  where
    remove key value = IM.update (\ns -> let remaining = IS.delete value ns
      in if IS.null remaining then Nothing else Just remaining) key

-- Include incoming references too: changing a shared type can affect a scope
-- or permission far from the two roots explicitly named in an equation.
component :: Solver -> [NodeId] -> Either String IS.IntSet
component solver = go IS.empty
  where
    g = graph solver
    go seen [] = pure seen
    go seen (original:pending)
      | IS.member n seen = go seen pending
      | otherwise = do
          v <- maybe (Left ("missing graph node " ++ show n)) pure (IM.lookup n (nodes g))
          let surrounding = maybeToList (binder v)
              connected = case tag v of
                Gen _ -> []
                _ -> children (tag v) ++ surrounding ++
                  IS.toList (IM.findWithDefault IS.empty n (structuralParents solver)) ++
                  IS.toList (IM.findWithDefault IS.empty n (bindingChildren solver))
          go (IS.insert n seen) (connected ++ pending)
      where n = resolve g original

-- | Run the same checked unifier on a compact, closed component. Sorting
-- identities preserves the unifier's minimum-identity representative choice.
unify :: [(NodeId,NodeId)] -> Solver -> Either String Solver
unify equations solver = do
  let g = graph solver
      canonical = [(resolve g a,resolve g b) | (a,b) <- equations]
  forM_ canonical $ \(a,b) -> forM_ [a,b] $ \n ->
    unless (IM.member n (nodes g)) (Left ("missing graph node " ++ show n))
  case filter (uncurry (/=)) canonical of
    [] -> pure solver
    pending -> unifyDistinct pending solver

unifyDistinct :: [(NodeId,NodeId)] -> Solver -> Either String Solver
unifyDistinct equations solver = do
  connected <- component solver (concatMap (\(a,b) -> [a,b]) equations)
  let g = graph solver
      boundaries = IS.filter (\n -> case tag (nodes g IM.! n) of Gen _ -> True; _ -> False) connected
      scopes = projectScopes (scopeIndex solver) boundaries
      selected = connected `IS.union` IM.keysSet scopes
      originals = [(n,nodes g IM.! n) | n <- IS.toAscList selected]
      count = length originals
      forward = IM.fromDistinctAscList (zip (map fst originals) [0..])
      backward = A.listArray (0,count-1) (map fst originals)
      compact n = forward IM.! resolve g n
      projectedBinder n v = case tag v of
        Gen _ -> fmap compact (scopes IM.! n)
        _ -> fmap compact (binder v)
      hiddenRoots = [(n,v) | (n,v) <- originals, Gen root <- [tag v], IS.notMember root selected]
      stubs = IM.fromList (zip (map fst hiddenRoots) [count..])
      localNode n v = Node
        (case IM.lookup n stubs of Just stub -> Gen stub; Nothing -> mapTag compact (tag v))
        (projectedBinder n v) (flag v)
      local = Graph (IM.fromDistinctAscList
        ([(compact n,localNode n v) | (n,v) <- originals] ++
         [(stub,Node Bot (Just (compact n)) Flexible) | ((n,_),stub) <- zip hiddenRoots [count..]]))
        IM.empty (count + length hiddenRoots)
  (_,solved) <- G.runBuild local (G.unify [(compact a,compact b) | (a,b) <- equations])
  forM_ (IM.elems stubs) $ \stub ->
    unless (IM.lookup stub (nodes solved) == IM.lookup stub (nodes local) &&
            resolve solved stub == stub)
      (Left "local unification changed a hidden scope root")
  forM_ originals $ \(n,v) -> case tag v of
    Gen _ -> case IM.lookup (compact n) (nodes solved) of
      Just v' | binder v' == projectedBinder n v, flag v' == flag v -> pure ()
      _ -> Left "local unification changed a generalization scope"
    _ -> pure ()
  let original n
        | A.inRange (A.bounds backward) n = pure (backward A.! n)
        | otherwise = Left "scope placeholder escaped local unification"
  aliases <- forM (IM.toAscList (links solved)) $ \(a,b) -> do
    a' <- original a
    b' <- original b
    pure (a',b')
  let newAliases = IM.fromList aliases
      withAliases = g { links = IM.union newAliases (links g) }
  restored <- forM [(n,v) | (n,v) <- IM.toAscList (nodes solved), n < count] $ \(n,v) -> do
    n' <- original n
    t <- case tag (nodes g IM.! n') of
      Gen root -> pure (Gen (resolve withAliases root))
      _ -> traverseTag original (tag v)
    b <- case tag (nodes g IM.! n') of
      Gen _ -> pure (binder (nodes g IM.! n'))
      _ -> traverse original (binder v)
    pure (n',Node t b (flag v))
  let restoredMap = IM.fromDistinctAscList restored
      removedNodes = [(n,v) | (n,v) <- originals, IM.lookup n restoredMap /= Just v]
      changedNodes = [(n,v) | (n,v) <- restored, IM.lookup n (nodes g) /= Just v]
      deleted = selected `IS.difference` IM.keysSet restoredMap
      patched = withAliases { nodes = List.foldl' (\ns (n,v) -> IM.insert n v ns)
        (IM.withoutKeys (nodes g) deleted) changedNodes }
      removed = List.foldl' removeNode solver removedNodes
      indexed = List.foldl' addNode removed changedNodes
  pure indexed { solverGraph = patched }

-- Expansion only allocates fresh nodes. Its entire structural copy belongs
-- to the following unification component; no unchecked expansion is exposed.
expanded :: NodeId -> NodeId -> Solver -> Either String (NodeId,IM.IntMap NodeId,[(NodeId,NodeId)],Solver)
expanded source target solver = do
  let g = graph solver
  sourceNode <- maybe (Left "missing instance source") pure (IM.lookup (resolve g source) (nodes g))
  case tag sourceNode of Gen _ -> pure (); _ -> Left "instance source must be a gen node"
  targetNode <- maybe (Left "missing instance target") pure (IM.lookup (resolve g target) (nodes g))
  destination <- maybe (Left "instance target has no binder") pure (binder targetNode)
  let ScopeIndex intervals _ = scopeIndex solver
  ((root,copies,frontier),g') <- G.runBuild g (G.expandWithScopes intervals source destination)
  let (_,fresh) = IM.split (nextId g - 1) (nodes g')
      solver' = List.foldl' addNode (solver { solverGraph = g' }) (IM.toAscList fresh)
  pure (root,copies,frontier,solver')

-- | Inference solves frontier equations and the instance root together.
instantiate :: NodeId -> NodeId -> Solver -> Either String Solver
instantiate source target solver = do
  (root,_,frontier,expandedSolver) <- expanded source target solver
  unify (frontier ++ [(root,target)]) expandedSolver

-- | Production fast path; 'instantiate' remains the exact graph operation
-- for clients requiring the fresh-copy identities and differential tests.
instantiateClosed :: NodeId -> NodeId -> Solver -> Either String Solver
instantiateClosed source target solver
  | Just grafted <- groundGraft source target solver = pure grafted
  | groundInstance (graph solver) source target = pure solver
  | otherwise = instantiate source target solver

-- Instantiating a closed monotype into a green bottom is exactly grafting.
-- Copy its entire ground structure beneath the destination, with fresh
-- identities and no shared frontier. There is no old type child to rebind,
-- and all newly introduced nodes are inert. The destination's original
-- identity/binder is retained, so every incoming reference stays valid.
groundGraft :: NodeId -> NodeId -> Solver -> Maybe Solver
groundGraft source destination solver = do
  let g = graph solver
      target = resolve g destination
  old <- IM.lookup target (nodes g)
  expectedKind <- case tag old of Bot -> Just Star; BotK k -> Just k; _ -> Nothing
  unless (green g target) Nothing
  sourceNode <- IM.lookup (resolve g source) (nodes g)
  root <- case tag sourceNode of Gen n -> Just (resolve g n); _ -> Nothing
  originals <- groundNodes g IS.empty [root]
  unless (G.kindAt g root == Right expectedKind) Nothing
  let descendants = IS.toAscList (IS.delete root originals)
      count = length descendants
  when (toInteger (nextId g) + toInteger count > toInteger (maxBound :: Int)) Nothing
  let copies = IM.insert root target (IM.fromDistinctAscList (zip descendants [nextId g..]))
      image n = copies IM.! resolve g n
      replacement = old { tag = mapTag image (tag (G.nodeAt g root)) }
      fresh = [(image n,Node (mapTag image (tag (G.nodeAt g n))) (Just target) Rigid) | n <- descendants]
      g' = g { nodes = IM.insert target replacement (IM.union (IM.fromDistinctAscList fresh) (nodes g)),
               nextId = nextId g + count }
      indexed = List.foldl' addNode (removeNode solver (target,old)) ((target,replacement):fresh)
  pure indexed { solverGraph = g' }
  where
    green g n = case G.nodeAt g n of
      Node (Gen _) _ _ -> True
      Node _ b Flexible -> maybe False (green g) b
      _ -> False
    groundNodes _ seen [] = Just seen
    groundNodes g seen (x:xs)
      | IS.member n seen = groundNodes g seen xs
      | otherwise = do
          v <- IM.lookup n (nodes g)
          case tag v of
            Bot -> Nothing; BotK _ -> Nothing; Skolem _ _ -> Nothing; Gen _ -> Nothing
            t -> groundNodes g (IS.insert n seen) (children t ++ xs)
      where n = resolve g x

-- A closed target cannot constrain any frontier variable. Match its shape
-- against the source, allowing only unconstrained flexible variables bound
-- directly by the source Gen. Repeated variables must have equal ground
-- images and kinds must agree. No external variable or bounded/rigid bottom
-- is substituted. All target nodes are inert, so retaining their distinct
-- identities changes no permission after normalization. General instances
-- continue through expansion/unification, and xMLF evidence is still checked.
groundInstance :: Graph -> NodeId -> NodeId -> Bool
groundInstance g source target = case IM.lookup (resolve g source) (nodes g) of
  Just (Node (Gen root) _ _) -> closed IS.empty [target] && go Set.empty IM.empty [(root,target)]
  _ -> False
  where
    closed _ [] = True
    closed seen (x:xs)
      | IS.member n seen = closed seen xs
      | otherwise = case IM.lookup n (nodes g) of
          Just v -> case tag v of
            Bot -> False; BotK _ -> False; Skolem _ _ -> False; Gen _ -> False
            t -> closed (IS.insert n seen) (children t ++ xs)
          Nothing -> False
      where n = resolve g x
    go _ _ [] = True
    go seen images ((x,y):rest)
      | Set.member (a,b) seen = go seen images rest
      | otherwise = case (IM.lookup a (nodes g),IM.lookup b (nodes g)) of
          (Just av,Just bv) -> case (tag av,tag bv) of
            (Bot,_) -> variable av Star
            (BotK k,_) -> variable av k
            (TyCon c k,TyCon d l) | c == d && k == l -> next []
            (Arr p q,Arr r s) -> next [(p,r),(q,s)]
            (TyApp p q,TyApp r s) -> next [(p,r),(q,s)]
            (Con c ps,Con d qs) | c == d && length ps == length qs -> next (zip ps qs)
            _ -> False
          _ -> False
      where
        a = resolve g x; b = resolve g y
        next pairs = go (Set.insert (a,b) seen) images (pairs ++ rest)
        variable v k = flag v == Flexible && binder v == Just (resolve g source) &&
          G.kindAt g b == Right k &&
          case IM.lookup a images of
            Nothing -> go (Set.insert (a,b) seen) (IM.insert a b images) rest
            Just previous -> equal Set.empty [(previous,b)] && next []
    equal _ [] = True
    equal seen ((x,y):rest)
      | a == b || Set.member (a,b) seen = equal seen rest
      | otherwise = case (tag (G.nodeAt g a),tag (G.nodeAt g b)) of
          (TyCon c k,TyCon d l) | c == d && k == l -> next []
          (Arr p q,Arr r s) -> next [(p,r),(q,s)]
          (TyApp p q,TyApp r s) -> next [(p,r),(q,s)]
          (Con c ps,Con d qs) | c == d && length ps == length qs -> next (zip ps qs)
          _ -> False
      where
        a = resolve g x; b = resolve g y
        next pairs = equal (Set.insert (a,b) seen) (pairs ++ rest)

-- | Elaboration preserves the required separate frontier-solving step and
-- returns the original-to-copy identities used to construct instance proofs.
witness :: NodeId -> NodeId -> Solver -> Either String (IM.IntMap NodeId,Solver)
witness source target solver = do
  (root,copies,frontier,expandedSolver) <- expanded source target solver
  frontierSolved <- unify frontier expandedSolver
  result <- unify [(root,target)] frontierSolved
  pure (copies,result)

mapTag :: (NodeId -> NodeId) -> Tag -> Tag
mapTag f t = case t of
  Arr a b -> Arr (f a) (f b)
  Con c ns -> Con c (map f ns)
  Gen n -> Gen (f n)
  TyApp a b -> TyApp (f a) (f b)
  _ -> t

traverseTag :: (NodeId -> Either String NodeId) -> Tag -> Either String Tag
traverseTag f t = case t of
  Arr a b -> Arr <$> f a <*> f b
  Con c ns -> Con c <$> mapM f ns
  Gen n -> Gen <$> f n
  TyApp a b -> TyApp <$> f a <*> f b
  _ -> pure t
