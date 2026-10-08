{-# LANGUAGE MonoLocalBinds #-}
module MLF.Graph
  ( NodeId, Tag (..), Node (..), Graph (..), Build, emptyGraph
  , freshId, newNode, setNode, nodeAt, resolve, children, runBuild
  , reachable, underBinder, inert, Permission (..), permission
  , unify, expand, expandWithScopes, normalize, validateGraph, orderedBelow, genRoot, kindAt, bottomTag
  ) where

import Control.Monad (foldM, forM, forM_, unless, when)
import Control.Monad.State.Strict
import Control.Monad.Except (runExceptT, throwError)
import Control.Monad.ST (ST, runST)
import qualified Data.Array as A
import Data.Array.ST (STArray, STUArray, newArray, readArray, writeArray)
import Data.List (find)
import qualified Data.List as List
import Data.Maybe (mapMaybe)
import qualified Data.IntMap.Strict as IM
import qualified Data.IntMap.Lazy as Lazy
import qualified Data.IntSet as IS
import MLF.Syntax (Flag (..))
import MLF.Kind

type NodeId = Int

data Tag = Bot | BotK Kind | Arr !NodeId !NodeId | Con String [NodeId]
         | TyCon String Kind | Skolem Int Kind | TyApp !NodeId !NodeId | Gen !NodeId
  deriving (Eq, Show)
data Node = Node { tag :: !Tag, binder :: !(Maybe NodeId), flag :: !Flag }
  deriving (Eq, Show)
data Graph = Graph
  { nodes :: !(IM.IntMap Node)
  , links :: !(IM.IntMap NodeId)
  , nextId :: !Int
  } deriving (Eq, Show)

type Build = StateT Graph (Either String)

emptyGraph :: Graph
emptyGraph = Graph IM.empty IM.empty 0

runBuild :: Graph -> Build a -> Either String (a, Graph)
runBuild = flip runStateT

freshId :: Build NodeId
freshId = do
  g <- get
  put g { nextId = nextId g + 1 }
  pure (nextId g)

newNode :: Tag -> Maybe NodeId -> Flag -> Build NodeId
newNode t b f = do
  n <- freshId
  setNode n (Node t b f)
  pure n

setNode :: NodeId -> Node -> Build ()
setNode n v = modify' (\g -> g { nodes = IM.insert (resolve g n) v (nodes g) })

resolve :: Graph -> NodeId -> NodeId
resolve g n = maybe n (resolve g) (IM.lookup n (links g))

-- Internal access, on graphs validated at the public inference boundaries.
nodeAt :: Graph -> NodeId -> Node
nodeAt g n = nodes g IM.! resolve g n

children :: Tag -> [NodeId]
children Bot = []
children (BotK _) = []
children (Arr a b) = [a,b]
children (Con _ ns) = ns
children (Gen n) = [n]
children (TyCon _ _) = []
children (Skolem _ _) = []
children (TyApp f a) = [f,a]

mapTag :: (NodeId -> NodeId) -> Tag -> Tag
mapTag _ Bot = Bot
mapTag _ (BotK k) = BotK k
mapTag f (Arr a b) = Arr (f a) (f b)
mapTag f (Con c ns) = Con c (map f ns)
mapTag f (Gen n) = Gen (f n)
mapTag _ (TyCon c k) = TyCon c k
mapTag _ (Skolem n k) = Skolem n k
mapTag f (TyApp a b) = TyApp (f a) (f b)

bottomTag :: Kind -> Tag
bottomTag Star = Bot
bottomTag k = BotK k

isBottom :: Tag -> Bool
isBottom Bot = True
isBottom (BotK _) = True
isBottom _ = False

kindAt :: Graph -> NodeId -> Either String Kind
kindAt g start = (IM.! resolve g start) <$> kindsAt g [start]

-- Share results across all requested roots of one immutable structural DAG.
-- The active path still detects cycles; only completed nodes enter the cache.
kindsAt :: Graph -> [NodeId] -> Either String (IM.IntMap Kind)
kindsAt g starts = execStateT (mapM_ (go IS.empty) starts) IM.empty
  where
    go :: IS.IntSet -> NodeId -> StateT (IM.IntMap Kind) (Either String) Kind
    go path original = do
      let n = resolve g original
      cached <- gets (IM.lookup n)
      case cached of
        Just k -> pure k
        Nothing -> do
          when (IS.member n path) (lift (Left "infinite type (occurs check)"))
          v <- maybe (lift (Left ("missing graph node " ++ show n))) pure (IM.lookup n (nodes g))
          let child = go (IS.insert n path)
          k <- case tag v of
            Bot -> pure Star
            BotK kind -> pure kind
            TyCon _ kind -> pure kind
            Skolem _ kind -> pure kind
            Gen s -> child s
            Arr a b -> do
              ka <- child a
              kb <- child b
              unless (ka == Star && kb == Star) (lift (Left "function types require kind * arguments"))
              pure Star
            Con _ ns -> do
              ks <- mapM child ns
              unless (all (== Star) ks) (lift (Left "legacy type constructor has a non-* argument"))
              pure Star
            TyApp f a -> do
              kf <- child f
              ka <- child a
              lift (applyKind kf ka)
          modify' (IM.insert n k)
          pure k

genRoot :: Graph -> NodeId -> NodeId
genRoot g n = case tag (nodeAt g n) of
  Gen s -> resolve g s
  _ -> error "internal invariant: expected a generalization node"

reachable :: Graph -> NodeId -> IS.IntSet
reachable g start = go IS.empty [resolve g start]
  where
    go seen [] = seen
    go seen (n:ns)
      | IS.member n seen = go seen ns
      | otherwise = go (IS.insert n seen) (map (resolve g) (children (tag (nodeAt g n))) ++ ns)

-- Validation asks about one node, so do not materialize every descendant of
-- its binder. In particular, a direct child of a deep type is found at once.
structurallyContains :: Graph -> NodeId -> NodeId -> Bool
structurallyContains g parent wanted = go IS.empty [resolve g parent]
  where
    target = resolve g wanted
    go _ [] = False
    go seen (n:ns)
      | n == target = True
      | IS.member n seen = go seen ns
      | otherwise = go (IS.insert n seen)
          (map (resolve g) (children (tag (nodeAt g n))) ++ ns)

-- | Strict membership in a binding-tree interior.
underBinder :: Graph -> NodeId -> NodeId -> Bool
underBinder g n ancestor = go (binder (nodeAt g n))
  where
    wanted = resolve g ancestor
    go Nothing = False
    go (Just b) | resolve g b == wanted = True
                | otherwise = go (binder (nodeAt g b))

inert :: Graph -> NodeId -> Bool
inert g n = inertNodes g IM.! resolve g n

-- These analyses are shared only within one immutable graph. Binding edges
-- form a tree after validation, so the lazy tables are well founded.
inertNodes :: Graph -> IM.IntMap Bool
inertNodes g = table
  where
    flexChildren = IM.fromListWith (++)
      [(b,[n]) | (n,v) <- IM.toList (nodes g), Just b <- [binder v], flag v == Flexible]
    table = Lazy.mapWithKey (\n v -> not (isBottom (tag v)) &&
      all (table IM.!) (IM.findWithDefault [] n flexChildren)) (nodes g)

data Permission = Green | Orange | Red | Inert deriving (Eq, Show)

permission :: Graph -> NodeId -> Permission
permission g n = permissions g IM.! resolve g n

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

validateGraph :: Graph -> Either String ()
validateGraph g = case denseBounds g of
  Just bounds -> validateDense g bounds
  Nothing -> validateSparse g

-- Source-generated identities are dense, but Graph is also a public API.
-- Keep storage proportional to the input even for arbitrary sparse IDs.
denseBounds :: Graph -> Maybe (NodeId,NodeId)
denseBounds g = do
  (lo,_) <- IM.lookupMin (nodes g)
  (hi,_) <- IM.lookupMax (nodes g)
  if toInteger hi - toInteger lo <= 8 * toInteger (IM.size (nodes g))
      && IM.disjoint (nodes g) (links g)
    then Just (lo,hi) else Nothing

newInts :: (Int,Int) -> Int -> ST s (STUArray s Int Int)
newInts = newArray

newKinds :: (Int,Int) -> ST s (STArray s Int Kind)
newKinds bounds = newArray bounds Star

newBinders :: (Int,Int) -> ST s (STArray s Int (Maybe NodeId))
newBinders bounds = newArray bounds Nothing

-- All scratch storage is confined to this validation. Three-colour DFS
-- checks kinds, scope and structural cycles after numbering the binding tree.
-- No persistent map is rebuilt for every node visited.
validateDense :: Graph -> (Int,Int) -> Either String ()
validateDense g bounds = runST $ runExceptT $ do
  colours <- lift (newInts bounds 0)
  kinds <- lift (newKinds bounds)
  starts <- lift (newInts bounds (-1))
  ends <- lift (newInts bounds (-1))
  visited <- lift (newInts bounds (-1))
  let entries = IM.toAscList (nodes g)
      table = A.accumArray (\_ v -> Just v) Nothing bounds entries
      getNode n = if A.inRange bounds n then table A.! n else Nothing
      require n = maybe (throwError ("missing graph node " ++ show n)) pure (getNode n)
  root <- case [n | (n,v) <- entries, binder v == Nothing] of
    [n] -> pure n
    _ -> throwError "graph must have one binding root"
  forM_ entries $ \(_,v) -> forM_ (binder v) $ \b ->
    unless (maybe False (const True) (getNode b)) (throwError "missing binder")
  let descendants = A.accumArray (flip (:)) [] bounds
        [(b,n) | (n,v) <- entries, Just b <- [binder v]]
      visit n position = do
        lift (writeArray starts n position)
        end <- foldM (flip visit) (position + 1) (descendants A.! n)
        lift (writeArray ends n end)
        pure end
      contains ancestor n = do
        a <- lift (readArray starts ancestor)
        b <- lift (readArray ends ancestor)
        p <- lift (readArray starts n)
        pure (a <= p && p < b)
      structurally _ _ [] = pure False
      structurally wanted stamp (original:rest) = do
        let n = resolve g original
        if n == wanted then pure True else do
          v <- require n
          mark <- lift (readArray visited n)
          if mark == stamp then structurally wanted stamp rest else do
            lift (writeArray visited n stamp)
            structurally wanted stamp (children (tag v) ++ rest)
  count <- visit root 0
  unless (count == length entries) (throwError "cyclic binding tree")
  let -- Check domination on every edge, even when its child's kind is cached.
      -- Passing the already looked-up child to kind avoids a second lookup.
      child parent original = do
        let n = resolve g original
        v <- require n
        case tag v of
          Gen _ -> throwError "gen nodes cannot be structural children"
          _ -> pure ()
        case binder v of
          Nothing -> throwError "structural child has no binder"
          Just b -> do
            dominated <- contains b parent
            unless dominated (throwError "ill-dominated type graph")
        kind n v
      kind n v = do
        colour <- lift (readArray colours n)
        case colour of
          1 -> throwError "infinite type (occurs check)"
          2 -> lift (readArray kinds n)
          _ -> do
            lift (writeArray colours n 1)
            case binder v of
              Nothing -> case tag v of
                Gen _ -> pure ()
                _ -> throwError "binding root must be a gen node"
              Just b -> do
                parent <- require b
                case tag parent of
                  Gen _ -> pure ()
                  _ -> unless (any ((== n) . resolve g) (children (tag parent))) $ do
                    stamp <- lift (readArray starts n)
                    found <- structurally n stamp [b]
                    unless found (throwError "a type binder must structurally contain its node")
            k <- case tag v of
              Bot -> pure Star
              BotK t -> pure t
              TyCon _ t -> pure t
              Skolem _ t -> pure t
              Gen s -> do
                unless (flag v == Flexible) (throwError "gen nodes must be flexible")
                child n s
              Arr a b -> do
                ka <- child n a
                kb <- child n b
                unless (ka == Star && kb == Star) (throwError "function types require kind * arguments")
                pure Star
              Con _ ns -> do
                ks <- mapM (child n) ns
                unless (all (== Star) ks) (throwError "legacy type constructor has a non-* argument")
                pure Star
              TyApp f a -> do
                kf <- child n f
                ka <- child n a
                either throwError pure (applyKind kf ka)
            lift (writeArray kinds n k >> writeArray colours n 2)
            pure k
  mapM_ (uncurry kind) entries

validateSparse :: Graph -> Either String ()
validateSparse g = do
  _ <- kindsAt g (IM.keys (nodes g))
  intervals <- bindingIntervals g
  let contains ancestor n =
        let (start,end) = intervals IM.! ancestor
            (position,_) = intervals IM.! n
        in start <= position && position < end
  forM_ (IM.toList (nodes g)) $ \(n,v) -> do
    case binder v of
      Nothing -> case tag v of
        Gen _ -> pure ()
        _ -> Left "binding root must be a gen node"
      Just b -> do
        case tag (nodeAt g b) of
          Gen _ -> pure ()
          _ -> unless (structurallyContains g b n) (Left "a type binder must structurally contain its node")
  -- Every structural edge must respect lexical scope. Together with the
  -- binding tree this is exactly domination for mixed paths (§4.3.3, §9.2.1).
  forM_ (IM.toList (nodes g)) $ \(p,v) -> do
    case tag v of
      Gen _ -> unless (flag v == Flexible) (Left "gen nodes must be flexible")
      _ -> pure ()
    forM_ (children (tag v)) $ \c -> do
      case tag (nodeAt g c) of
        Gen _ -> Left "gen nodes cannot be structural children"
        _ -> pure ()
      case binder (nodeAt g c) of
        Just b -> unless (contains b p) (Left "ill-dominated type graph")
        Nothing -> Left "structural child has no binder"

-- A DFS interval answers binding ancestry without walking to the root for
-- every structural edge. With one root, one parent per other node, and no
-- missing parents, every node outside the root's tree belongs to a component
-- containing a cycle. Such a component cannot be reached by this traversal.
bindingIntervals :: Graph -> Either String (IM.IntMap (Int,Int))
bindingIntervals g = do
  root <- case [n | (n,v) <- IM.toList (nodes g), binder v == Nothing] of
    [n] -> pure n
    _ -> Left "graph must have one binding root"
  forM_ (IM.elems (nodes g)) $ \v -> forM_ (binder v) $ \b ->
    unless (IM.member b (nodes g)) (Left "missing binder")
  let descendants = IM.fromListWith (++)
        [(b,[n]) | (n,v) <- IM.toList (nodes g), Just b <- [binder v]]
      visit n (position,known) =
        let (end,known') = List.foldl' (flip visit) (position + 1,known)
              (IM.findWithDefault [] n descendants)
        in (end,IM.insert n (position,end) known')
      (_,intervals) = visit root (0,IM.empty)
  unless (IM.size intervals == IM.size (nodes g)) (Left "cyclic binding tree")
  pure intervals

-- | Figure 7.3.1: first-order unification followed by Rebind. All permission
-- checks use the immutable input graph, never union-find representatives alone.
unify :: [(NodeId,NodeId)] -> Build ()
unify equations = do
  before <- get
  lift (validateGraph before)
  -- Every successful merge preserves kind. All following equations refer to
  -- descendants of these roots, and representatives retain an original
  -- identity, so one immutable kind table suffices for the whole operation.
  kinds <- lift (kindsAt before (concatMap (\(a,b) -> [a,b]) equations))
  mapM_ (firstOrder kinds) equations
  skeleton <- get
  let canon = resolve skeleton
      canonical v = case tag v of
        Arr a b -> pair Arr a b
        TyApp a b -> pair TyApp a b
        Gen n -> let n' = canon n in if n == n' then v else v { tag = Gen n' }
        Con c ns' -> let cs = map canon ns' in if cs == ns' then v else v { tag = Con c cs }
        _ -> v
        where
          pair constructor a b = let a' = canon a; b' = canon b
            in if a == a' && b == b' then v else v { tag = constructor a' b' }
      ns = IM.map canonical (nodes skeleton)
      sk = skeleton { nodes = ns }
  -- Rebind's dependency traversal includes every reverse structural edge,
  -- so it also performs the occurs check on the unified skeleton. A separate
  -- structural topological sort would visit the same DAG once more.
  rebuilt <- lift (rebind before sk)
  put rebuilt
  lift (validateGraph rebuilt)
  where
    firstOrder :: IM.IntMap Kind -> (NodeId,NodeId) -> Build ()
    firstOrder kinds (a0,b0) = do
      g <- get
      let a = resolve g a0; b = resolve g b0
      when (a /= b) $ do
        let ka = kinds IM.! a; kb = kinds IM.! b
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
        mapM_ (firstOrder kinds) pairs

-- | Figure 7.3.2. Both implementations check the complete dependency DAG and
-- the permissions of original identities, then return the same binding LCAs.
rebind :: Graph -> Graph -> Either String Graph
rebind old sk = case denseBounds old of
  Just bounds -> rebindDense old sk bounds
  Nothing -> rebindSparse old sk

-- The dependency graph determines a unique binding tree. A memoized DFS
-- computes parents before children directly, instead of constructing and
-- updating persistent maps for a Kahn queue. LCA walks by cached depth.
rebindDense :: Graph -> Graph -> (Int,Int) -> Either String Graph
rebindDense old sk bounds = runST $ runExceptT $ do
  tree <- lift (newBinders bounds)
  depths <- lift (newInts bounds 0)
  colours <- lift (newInts bounds 0)
  grafted <- lift (newInts bounds 0)
  let originals = IM.toAscList (nodes old)
      remaining = IM.toAscList (nodes sk)
      oldNodes = A.array bounds originals
      newNodes = A.array bounds remaining
      images = A.array bounds [(m,resolve sk m) | (m,_) <- originals]
      image n = images A.! n
      classes = A.accumArray (flip (:)) [] bounds [(image m,m) | (m,_) <- originals]
      flags = A.accumArray max Flexible bounds [(image m,flag v) | (m,v) <- originals]
      parents = A.accumArray (flip (:)) [] bounds
        [(c,p) | (p,v) <- remaining, c <- children (tag v)]
      mark n = do
        seen <- lift (readArray grafted n)
        when (seen == 0) $ do
          lift (writeArray grafted n 1)
          mapM_ mark (children (tag (newNodes A.! n)))
      common a b | a == b = pure a
      common a b = do
        da <- lift (readArray depths a)
        db <- lift (readArray depths b)
        let parent n = lift (readArray tree n) >>=
              maybe (throwError "binders have no common ancestor") pure
        case compare da db of
          GT -> parent a >>= \p -> common p b
          LT -> parent b >>= common a
          EQ -> do
            p <- parent a
            q <- parent b
            common p q
      place n = do
        colour <- lift (readArray colours n)
        case colour of
          1 -> throwError "cyclic structure/binding dependencies"
          2 -> pure ()
          _ -> do
            lift (writeArray colours n 1)
            graft <- lift (readArray grafted n)
            let ps = parents A.! n
                cs = [image b | m <- classes A.! n, Just b <- [binder (oldNodes A.! m)]]
                  ++ if graft == 0 then [] else ps
            mapM_ place cs
            mapM_ place ps
            b <- case cs of
              [] -> pure Nothing
              p:rest -> Just <$> foldM common p rest
            depth <- maybe (pure 0) (\p -> (+1) <$> lift (readArray depths p)) b
            lift (writeArray tree n b >> writeArray depths n depth >> writeArray colours n 2)
  -- Mark the union once, even when many old bottom nodes have the same
  -- representative or their instantiated structures share descendants.
  forM_ originals $ \(m,v) -> when (isBottom (tag v)) $
    mapM_ mark (children (tag (newNodes A.! image m)))
  mapM_ (place . fst) remaining
  final <- forM remaining $ \(n,v) -> do
    b <- lift (readArray tree n)
    let f = flags A.! n
    pure (n,if b == binder v && f == flag v then v else v { binder = b, flag = f })
  raised <- forM originals $ \(m,v) -> do
    wanted <- lift (readArray tree (image m))
    let climb _ Nothing = throwError "a node's binder cannot be lowered"
        climb p (Just b)
          | image b == p = pure (Just b)
          | otherwise = climb p (binder (oldNodes A.! b))
    b <- maybe (pure Nothing) (\p -> climb p (binder v)) wanted
    pure (m,b)
  let up = A.array bounds raised
      oldPermissions = permissionTable bounds originals (binder . (oldNodes A.!))
      raisedPermissions = permissionTable bounds originals (up A.!)
  forM_ originals $ \(m,v) -> do
    when (isBottom (tag v) && not (isBottom (tag (newNodes A.! image m))) && oldPermissions A.! m /= Green)
      (throwError "cannot instantiate a rigid or protected type variable")
    when (binder v /= up A.! m && oldPermissions A.! m == Red)
      (throwError "cannot raise a protected type variable")
    when (flag v /= flags A.! image m && raisedPermissions A.! m == Red)
      (throwError "cannot weaken a protected type variable")
  forM_ remaining $ \(n,_) -> do
    let ms = classes A.! n
    forM_ [(a,b) | a <- ms, b <- ms, a < b] $ \(a,b) ->
      when (up A.! a == up A.! b && (raisedPermissions A.! a == Red || raisedPermissions A.! b == Red))
        (throwError "cannot merge distinct protected type variables")
  pure sk { nodes = IM.fromDistinctAscList final }

permissionTable :: (Int,Int) -> [(NodeId,Node)] -> (NodeId -> Maybe NodeId) -> A.Array Int Permission
permissionTable bounds entries binding = table
  where
    flexChildren = A.accumArray (flip (:)) [] bounds
      [(b,n) | (n,v) <- entries, Just b <- [binding n], flag v == Flexible]
    inertness = A.array bounds
      [(n,not (isBottom (tag v)) && all (inertness A.!) (flexChildren A.! n)) | (n,v) <- entries]
    paths = A.array bounds [(n,case tag v of
      Gen _ -> True
      _ | flag v == Rigid -> False
        | otherwise -> maybe True (paths A.!) (binding n)) | (n,v) <- entries]
    table = A.array bounds [(n,if inertness A.! n then Inert
      else if flag v == Rigid then Orange else if paths A.! n then Green else Red) | (n,v) <- entries]

rebindSparse :: Graph -> Graph -> Either String Graph
rebindSparse old sk = do
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

-- | §10.1 expansion. The map records original-to-copy identity, including
-- frontier proxies. Frontier equations must be solved before elaboration.
expand :: NodeId -> NodeId -> Build (NodeId, IM.IntMap NodeId, [(NodeId,NodeId)])
expand = expandWithScopes IM.empty

-- A validated solver may supply DFS intervals for the immutable Gen binding
-- tree. Type binding edges can change, so only Gen-to-Gen ancestry is cached
-- across equations. An empty index retains the standalone expansion path.
expandWithScopes :: IM.IntMap (Int,Int) -> NodeId -> NodeId -> Build (NodeId, IM.IntMap NodeId, [(NodeId,NodeId)])
expandWithScopes intervals gen destination = do
  g <- get
  let source = genRoot g gen
      -- Scope and kind queries share one immutable input graph. Cache the
      -- binding ancestry reached by this expansion, rather than repeatedly
      -- climbing the same deep external scope for each frontier node.
      inside :: NodeId -> State (IM.IntMap Bool) Bool
      inside n = do
        cached <- gets (IM.lookup n)
        case cached of
          Just answer -> pure answer
          Nothing -> do
            answer <- case binder (nodeAt g n) of
              Nothing -> pure False
              Just b | resolve g b == resolve g gen -> pure True
                     | Just (start,end) <- IM.lookup (resolve g gen) intervals
                     , Just (position,_) <- IM.lookup (resolve g b) intervals ->
                         pure (start <= position && position < end)
                     | otherwise -> inside (resolve g b)
            modify' (IM.insert n answer)
            pure answer
      visit seen [] = pure seen
      visit seen (x:xs)
        | IS.member n seen = visit seen xs
        | otherwise = do
            local <- inside n
            visit (IS.insert n seen) ((if local then children (tag (nodeAt g n)) else []) ++ xs)
        where n = resolve g x
      (visited,scopes) = runState (visit IS.empty [source]) IM.empty
      originals = IS.toList visited
  -- IntMap.size walks the complete map. Check the actual expansion size,
  -- avoiding a whole-program scan for each small instance while retaining
  -- the overflow check before any fresh identity is allocated.
  when (toInteger (nextId g) + toInteger (length originals) > toInteger (maxBound :: Int))
    (lift (Left "graph identity space exhausted"))
  copies <- IM.fromList <$> mapM (\n -> do c <- freshId; pure (n,c)) originals
  kinds <- lift (kindsAt g originals)
  let copy n = IM.findWithDefault (resolve g n) (resolve g n) copies
      root = copy source
      frontier = [n | n <- originals, not (scopes IM.! n)]
      frontierSet = IS.fromDistinctAscList frontier
  forM_ originals $ \n -> do
    let k = kinds IM.! n
        v = nodeAt g n
        new | IS.member n frontierSet = Node (bottomTag k) (Just destination) Flexible
            | n == source = Node (mapTag copy (tag v)) (Just destination) Flexible
            | otherwise = Node (mapTag copy (tag v))
                (fmap (\b -> if resolve g b == resolve g gen then root else copy b) (binder v)) (flag v)
    setNode (copy n) new
  pure (root,copies,[(n,copy n) | n <- frontier])

-- | §15.2.8: weaken ALL inert nodes for a modular internal language, then
-- scheme roots and existential nodes (§15.2.10). No inferred bound is erased.
normalize :: Graph -> Graph
normalize g = g { nodes = IM.mapWithKey norm (nodes g) }
  where
    inertness = inertNodes g
    norm n v = case tag v of
      Gen _ -> v
      _ | inertness IM.! n || schemeOrExistential n v -> v { flag = Rigid }
        | otherwise -> v
    schemeOrExistential n v = case binder v of
      Just b -> case tag (nodeAt g b) of
        Gen s -> n == resolve g s || IS.notMember n (reachable g s)
        _ -> False
      Nothing -> False

-- | §15.2.7 leftmost-lowermost order: structural postorder, skipping a shared
-- node after its first occurrence. Used for both type and term quantifiers.
orderedBelow :: Graph -> NodeId -> [NodeId]
orderedBelow g root = snd (go IS.empty (resolve g root))
  where
    go seen n
      | IS.member n seen = (seen,[])
      | otherwise =
          let step (visited,acc) c = let (visited',childOrder) = go visited (resolve g c)
                                    in (visited',acc ++ childOrder)
              (seen',xs) = foldl step (IS.insert n seen,[]) (children (tag (nodeAt g n)))
          in (seen', xs ++ [n])
