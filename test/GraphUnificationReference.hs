-- Frozen map-based unification from before the indexed graph optimization.
-- The production path uses mutable arrays and DFS/depth LCA; this reference
-- deliberately retains Kahn traversal, path LCA, and persistent maps.
module GraphUnificationReference (referenceUnify) where

import Control.Monad (foldM, forM_, unless, when)
import Control.Monad.State.Strict
import Data.List (find)
import qualified Data.List as List
import Data.Maybe (mapMaybe)
import qualified Data.IntMap.Strict as IM
import qualified Data.IntMap.Lazy as Lazy
import qualified Data.IntSet as IS
import MLF.Syntax (Flag (..))
import MLF.Graph (NodeId, Tag (..), Node (..), Graph (..), Build,
  nodeAt, resolve, children, kindAt, reachable, validateGraph)

mapTag :: (NodeId -> NodeId) -> Tag -> Tag
mapTag _ Bot = Bot
mapTag _ (BotK k) = BotK k
mapTag f (Arr a b) = Arr (f a) (f b)
mapTag f (Con c ns) = Con c (map f ns)
mapTag f (Gen n) = Gen (f n)
mapTag _ (TyCon c k) = TyCon c k
mapTag _ (Skolem n k) = Skolem n k
mapTag f (TyApp a b) = TyApp (f a) (f b)

isBottom :: Tag -> Bool
isBottom Bot = True
isBottom (BotK _) = True
isBottom _ = False

inertNodes :: Graph -> IM.IntMap Bool
inertNodes g = table
  where
    flexChildren = IM.fromListWith (++)
      [(b,[n]) | (n,v) <- IM.toList (nodes g), Just b <- [binder v], flag v == Flexible]
    table = Lazy.mapWithKey (\n v -> not (isBottom (tag v)) &&
      all (table IM.!) (IM.findWithDefault [] n flexChildren)) (nodes g)

data Permission = Green | Orange | Red | Inert deriving (Eq, Show)

permissions :: Graph -> IM.IntMap Permission
permissions g = IM.mapWithKey classify (nodes g)
  where
    inertness = inertNodes g
    flexiblePaths = Lazy.map (\v -> case tag v of
      Gen _ -> True
      _ | flag v == Rigid -> False
        | otherwise -> maybe True (flexiblePaths IM.!) (binder v)) (nodes g)
    classify n v
      | inertness IM.! n = Inert
      | flag v == Rigid = Orange
      | flexiblePaths IM.! n = Green
      | otherwise = Red

topological :: Graph -> Either String [NodeId]
topological g = fmap reverse (snd <$> foldM visit (IS.empty,[]) (IM.keys (nodes g)))
  where
    visit (done,order) n | IS.member n done = pure (done,order)
    visit acc n = dfs IS.empty acc n
    dfs stack (done,order) n
      | IS.member n done = pure (done,order)
      | IS.member n stack = Left "infinite type (occurs check)"
      | otherwise = do
          unless (IM.member n (nodes g)) (Left ("missing graph node " ++ show n))
          (done',order') <- foldM (dfs (IS.insert n stack)) (done,order)
            (map (resolve g) (children (tag (nodeAt g n))))
          pure (IS.insert n done', n:order')

referenceUnify :: [(NodeId,NodeId)] -> Build ()
referenceUnify equations = do
  before <- get
  lift (validateGraph before)
  mapM_ firstOrder equations
  skeleton <- get
  let canon = resolve skeleton
      ns = IM.map (\v -> v { tag = mapTag canon (tag v) }) (nodes skeleton)
      sk = skeleton { nodes = ns }
  _ <- lift (topological sk)
  rebuilt <- lift (rebind before sk)
  put rebuilt
  lift (validateGraph rebuilt)
  where
    firstOrder :: (NodeId,NodeId) -> Build ()
    firstOrder (a0,b0) = do
      g <- get
      let a = resolve g a0; b = resolve g b0
      when (a /= b) $ do
        ka <- lift (kindAt g a)
        kb <- lift (kindAt g b)
        unless (ka == kb) (lift (Left ("kind mismatch during unification: " ++ show ka ++ " versus " ++ show kb)))
        let av = nodeAt g a; bv = nodeAt g b
            ta = tag av; tb = tag bv
        (t, pairs) <- lift $ case (ta,tb) of
          (Gen _,_) -> Left "cannot unify generalization nodes"
          (_,Gen _) -> Left "cannot unify generalization nodes"
          _ | isBottom ta -> pure (tb,[])
          _ | isBottom tb -> pure (ta,[])
          (Arr x y, Arr z w) -> pure (ta,[(x,z),(y,w)])
          (Con c xs, Con d ys) | c == d && length xs == length ys -> pure (ta,zip xs ys)
          (TyCon c k, TyCon d l) | c == d && k == l -> pure (ta,[])
          (Skolem c k, Skolem d l) | c == d && k == l -> pure (ta,[])
          (TyApp f x, TyApp h y) -> pure (ta,[(f,h),(x,y)])
          _ -> Left ("type constructor mismatch: " ++ show ta ++ " versus " ++ show tb)
        let winner = min a b; loser = max a b
        put g { nodes = IM.insert winner (av { tag = t }) (IM.delete loser (nodes g))
              , links = IM.insert loser winner (links g) }
        mapM_ firstOrder pairs

-- | Figure 7.3.2. LCA uses a simple persistent tree, rather than the linear-time
-- data structure discussed in §7.5. This favors auditability over asymptotics.
rebind :: Graph -> Graph -> Either String Graph
rebind old sk = do
  tree <- buildTree IM.empty dependencyCounts initiallyReady
  let finalNodes = IM.mapWithKey (\n v -> v { binder = tree IM.! n, flag = newFlag n }) (nodes sk)
      result = sk { nodes = finalNodes }
  up <- traverseWithKeyEither (raisedBinder tree) (nodes old)
  let raised = old { nodes = IM.mapWithKey (\m v -> v { binder = up IM.! m }) (nodes old) }
      oldPermissions = permissions old
      raisedPermissions = permissions raised
  forM_ (IM.toList (nodes old)) $ \(m,v) -> do
    when (isBottom (tag v) && not (isBottom (tag (nodeAt sk m))) && oldPermissions IM.! m /= Green)
      (Left "cannot instantiate a rigid or protected type variable")
    when (oldPermissions IM.! m == Red && binder v /= (up IM.! m))
      (Left "cannot raise a protected type variable")
    when (raisedPermissions IM.! m == Red && flag v /= newFlag (image m))
      (Left "cannot weaken a protected type variable")
  forM_ (IM.elems classes) $ \ms ->
    forM_ [(a,b) | a <- ms, b <- ms, a < b] $ \(a,b) ->
      when ((raisedPermissions IM.! a == Red || raisedPermissions IM.! b == Red) && up IM.! a == up IM.! b)
        (Left "cannot merge distinct protected type variables")
  pure result
  where
    image = resolve sk
    classes = IM.fromListWith (++) [(image m,[m]) | m <- IM.keys (nodes old)]
    members n = IM.findWithDefault [] n classes
    newFlag n = maximum (Flexible : [flag (nodeAt old m) | m <- members n])
    parents = IM.fromListWith IS.union
      [(image c, IS.singleton p) | (p,v) <- IM.toList (nodes sk), c <- children (tag v)]
    grafted = IS.unions
      [IS.delete (image m) (reachable sk (image m)) | (m,v) <- IM.toList (nodes old), isBottom (tag v)]
    candidates n = IS.toList $ IS.fromList (map image (mapMaybe (binder . nodeAt old) (members n)))
      `IS.union` (if IS.member n grafted then IM.findWithDefault IS.empty n parents else IS.empty)
    candidateMap = IM.mapWithKey (\n _ -> candidates n) (nodes sk)
    dependencyMap = IM.mapWithKey (\n cs -> IS.fromList cs `IS.union` IM.findWithDefault IS.empty n parents) candidateMap
    dependencyCounts = IM.map IS.size dependencyMap
    initiallyReady = IM.keysSet (IM.filter (== 0) dependencyCounts)
    dependents = IM.fromListWith (++)
      [(dependency,[n]) | (n,ds) <- IM.toList dependencyMap, dependency <- IS.toList ds]
    -- Kahn's traversal chooses the smallest ready identity, exactly as the
    -- previous scan of the ascending pending list did, without rescanning it.
    buildTree tree counts ready = case IS.minView ready of
      Nothing | IM.size tree == IM.size (nodes sk) -> pure tree
              | otherwise -> Left "cyclic structure/binding dependencies"
      Just (n,rest) -> do
        b <- lca tree (candidateMap IM.! n)
        let release (pending,available) child =
              let count = pending IM.! child - 1
              in (IM.insert child count pending, if count == 0 then IS.insert child available else available)
            (counts',ready') = List.foldl' release (counts,rest) (IM.findWithDefault [] n dependents)
        buildTree (IM.insert n b tree) counts' ready'
    lca _ [] = pure Nothing
    lca tree (b:bs) =
      let path n = n : maybe [] path (tree IM.! n)
      in maybe (Left "binders have no common ancestor") (pure . Just)
           (find (\n -> all (elem n . path) bs) (path b))
    raisedBinder tree m v = case tree IM.! image m of
      Nothing -> pure Nothing
      Just wanted -> climb wanted (binder v)
      where
        climb _ Nothing = Left "a node's binder cannot be lowered"
        climb wanted (Just p)
          | image p == wanted = pure (Just p)
          | otherwise = climb wanted (binder (nodeAt old p))

traverseWithKeyEither :: (Int -> a -> Either String b) -> IM.IntMap a -> Either String (IM.IntMap b)
traverseWithKeyEither = IM.traverseWithKey
