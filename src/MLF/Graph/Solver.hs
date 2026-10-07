-- | Incremental, scope-preserving use of the checked graph unifier.
--
-- Type components are closed under structural edges in BOTH directions and
-- type binding edges in BOTH directions. Gen nodes stop this closure, but
-- their entire binding ancestry is retained. A Gen cannot be merged or be
-- a structural child; its binding parent must therefore also be a Gen.
-- Permissions of type nodes stop at Gens, and their inertness depends only
-- on binding descendants inside the component. Consequently the projection
-- preserves every relevant permission, structural parent and binding LCA.
-- Unrelated Gen roots are represented by private bottom leaves, then restored.
-- Neither these leaves nor compact scratch identities escape into the graph.
module MLF.Graph.Solver
  ( Solver, prepare, graph, finish, unify, instantiate, witness ) where

import Control.Monad (forM, forM_, unless, when)
import qualified Data.Array as A
import qualified Data.IntMap.Strict as IM
import qualified Data.IntSet as IS
import qualified Data.List as List
import Data.Maybe (maybeToList)
import MLF.Graph (Graph (..), Node (..), NodeId, Tag (..), children, resolve)
import qualified MLF.Graph as G
import MLF.Syntax (Flag (..))

type Index = IM.IntMap IS.IntSet

-- The constructor is private: callers cannot mutate a graph without updating
-- its reverse edges, or inject an unchecked graph into the incremental path.
data Solver = Solver
  { solverGraph :: !Graph
  , structuralParents :: !Index
  , bindingChildren :: !Index
  }

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
  pure (List.foldl' addNode (Solver g IM.empty IM.empty) (IM.toAscList (nodes g)))
  where forM_Keys ns f = mapM_ f (IM.keys ns)

-- | Independently check the complete result and the maintained reverse edges.
finish :: Solver -> Either String Graph
finish solver = do
  G.validateGraph (graph solver)
  let indexed = List.foldl' addNode (Solver (graph solver) IM.empty IM.empty)
        (IM.toAscList (nodes (graph solver)))
  unless (structuralParents solver == structuralParents indexed &&
          bindingChildren solver == bindingChildren indexed)
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
                Gen _ -> surrounding
                _ -> children (tag v) ++ surrounding ++
                  IS.toList (IM.findWithDefault IS.empty n (structuralParents solver)) ++
                  IS.toList (IM.findWithDefault IS.empty n (bindingChildren solver))
          go (IS.insert n seen) (connected ++ pending)
      where n = resolve g original

-- | Run the same checked unifier on a compact, closed component. Sorting
-- identities preserves the unifier's minimum-identity representative choice.
unify :: [(NodeId,NodeId)] -> Solver -> Either String Solver
unify [] solver = pure solver
unify equations solver = do
  selected <- component solver (concatMap (\(a,b) -> [a,b]) equations)
  let g = graph solver
      originals = [(n,nodes g IM.! n) | n <- IS.toAscList selected]
      count = length originals
      forward = IM.fromDistinctAscList (zip (map fst originals) [0..])
      backward = A.listArray (0,count-1) (map fst originals)
      compact n = forward IM.! resolve g n
      hiddenRoots = [(n,v) | (n,v) <- originals, Gen root <- [tag v], IS.notMember root selected]
      stubs = IM.fromList (zip (map fst hiddenRoots) [count..])
      localNode n v = Node
        (case IM.lookup n stubs of Just stub -> Gen stub; Nothing -> mapTag compact (tag v))
        (fmap compact (binder v)) (flag v)
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
      Just v' | binder v' == fmap compact (binder v), flag v' == flag v -> pure ()
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
    b <- traverse original (binder v)
    pure (n',Node t b (flag v))
  let patched = withAliases { nodes = IM.union (IM.fromDistinctAscList restored)
        (IM.withoutKeys (nodes g) selected) }
      removed = List.foldl' removeNode solver originals
      indexed = List.foldl' addNode removed restored
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
  when (toInteger (nextId g) + toInteger (IM.size (nodes g)) > toInteger (maxBound :: Int))
    (Left "graph identity space exhausted")
  ((root,copies,frontier),g') <- G.runBuild g (G.expand source destination)
  let (_,fresh) = IM.split (nextId g - 1) (nodes g')
      solver' = List.foldl' addNode (solver { solverGraph = g' }) (IM.toAscList fresh)
  pure (root,copies,frontier,solver')

-- | Inference solves frontier equations and the instance root together.
instantiate :: NodeId -> NodeId -> Solver -> Either String Solver
instantiate source target solver = do
  (root,_,frontier,expandedSolver) <- expanded source target solver
  unify (frontier ++ [(root,target)]) expandedSolver

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
