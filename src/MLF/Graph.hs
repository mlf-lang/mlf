module MLF.Graph
  ( NodeId, Tag (..), Node (..), Graph (..), Build, emptyGraph
  , freshId, newNode, setNode, nodeAt, resolve, children, runBuild
  , reachable, underBinder, inert, Permission (..), permission
  , unify, expand, normalize, validateGraph, orderedBelow, genRoot
  ) where

import Control.Monad (foldM, forM_, unless, when)
import Control.Monad.State.Strict
import Data.List (find)
import Data.Maybe (mapMaybe)
import qualified Data.IntMap.Strict as IM
import qualified Data.IntSet as IS
import MLF.Syntax (Flag (..))

type NodeId = Int

data Tag = Bot | Arr NodeId NodeId | Con String [NodeId] | Gen NodeId
  deriving (Eq, Show)
data Node = Node { tag :: Tag, binder :: Maybe NodeId, flag :: Flag }
  deriving (Eq, Show)
data Graph = Graph
  { nodes :: IM.IntMap Node
  , links :: IM.IntMap NodeId
  , nextId :: Int
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
children (Arr a b) = [a,b]
children (Con _ ns) = ns
children (Gen n) = [n]

mapTag :: (NodeId -> NodeId) -> Tag -> Tag
mapTag _ Bot = Bot
mapTag f (Arr a b) = Arr (f a) (f b)
mapTag f (Con c ns) = Con c (map f ns)
mapTag f (Gen n) = Gen (f n)

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

-- | Strict membership in a binding-tree interior.
underBinder :: Graph -> NodeId -> NodeId -> Bool
underBinder g n ancestor = go (binder (nodeAt g n))
  where
    wanted = resolve g ancestor
    go Nothing = False
    go (Just b) | resolve g b == wanted = True
                | otherwise = go (binder (nodeAt g b))

inert :: Graph -> NodeId -> Bool
inert g n = tag (nodeAt g n) /= Bot && all (inert g) flexChildren
  where
    flexChildren = [m | (m,v) <- IM.toList (nodes g), binder v == Just (resolve g n), flag v == Flexible]

data Permission = Green | Orange | Red | Inert deriving (Eq, Show)

permission :: Graph -> NodeId -> Permission
permission g n
  | inert g n = Inert
  | flag (nodeAt g n) == Rigid = Orange
  | flexibleToGen n = Green
  | otherwise = Red
  where
    flexibleToGen m = case tag (nodeAt g m) of
      Gen _ -> True
      _ | flag (nodeAt g m) == Rigid -> False
        | otherwise -> maybe True flexibleToGen (binder (nodeAt g m))

-- | A topological order of the structural DAG. Gen nodes also own existential
-- nodes through the binding tree; these are checked separately below.
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

validateGraph :: Graph -> Either String ()
validateGraph g = do
  _ <- topological g
  let roots = [n | (n,v) <- IM.toList (nodes g), binder v == Nothing]
  unless (length roots == 1) (Left "graph must have one binding root")
  forM_ (IM.toList (nodes g)) $ \(n,v) -> do
    checkPath IS.empty n
    case binder v of
      Nothing -> case tag v of
        Gen _ -> pure ()
        _ -> Left "binding root must be a gen node"
      Just b -> do
        unless (IM.member b (nodes g)) (Left "missing binder")
        case tag (nodeAt g b) of
          Gen _ -> pure ()
          _ -> unless (IS.member n (reachable g b)) (Left "a type binder must structurally contain its node")
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
        Just b -> unless (b == p || underBinder g p b) (Left "ill-dominated type graph")
        Nothing -> Left "structural child has no binder"
  where
    checkPath seen n
      | IS.member n seen = Left "cyclic binding tree"
      | otherwise = case IM.lookup n (nodes g) of
          Nothing -> Left "missing binder"
          Just v -> maybe (pure ()) (checkPath (IS.insert n seen)) (binder v)

-- | Figure 7.3.1: first-order unification followed by Rebind. All permission
-- checks use the immutable input graph, never union-find representatives alone.
unify :: [(NodeId,NodeId)] -> Build ()
unify equations = do
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
        let av = nodeAt g a; bv = nodeAt g b
            ta = tag av; tb = tag bv
        (t, pairs) <- lift $ case (ta,tb) of
          (Gen _,_) -> Left "cannot unify generalization nodes"
          (_,Gen _) -> Left "cannot unify generalization nodes"
          (Bot,_) -> pure (tb,[])
          (_,Bot) -> pure (ta,[])
          (Arr x y, Arr z w) -> pure (ta,[(x,z),(y,w)])
          (Con c xs, Con d ys) | c == d && length xs == length ys -> pure (ta,zip xs ys)
          _ -> Left ("type constructor mismatch: " ++ show ta ++ " versus " ++ show tb)
        let winner = min a b; loser = max a b
        put g { nodes = IM.insert winner (av { tag = t }) (IM.delete loser (nodes g))
              , links = IM.insert loser winner (links g) }
        mapM_ firstOrder pairs

-- | Figure 7.3.2. LCA uses a simple persistent tree, rather than the linear-time
-- data structure discussed in §7.5. This favors auditability over asymptotics.
rebind :: Graph -> Graph -> Either String Graph
rebind old sk = do
  tree <- buildTree IM.empty (IM.keys (nodes sk))
  let finalNodes = IM.mapWithKey (\n v -> v { binder = tree IM.! n, flag = newFlag n }) (nodes sk)
      result = sk { nodes = finalNodes }
  up <- traverseWithKeyEither (raisedBinder tree) (nodes old)
  let raised = old { nodes = IM.mapWithKey (\m v -> v { binder = up IM.! m }) (nodes old) }
  forM_ (IM.toList (nodes old)) $ \(m,v) -> do
    when (tag v == Bot && tag (nodeAt sk m) /= Bot && permission old m /= Green)
      (Left "cannot instantiate a rigid or protected type variable")
    when (permission old m == Red && binder v /= (up IM.! m))
      (Left "cannot raise a protected type variable")
    when (permission raised m == Red && flag v /= newFlag (image m))
      (Left "cannot weaken a protected type variable")
  forM_ (IM.elems classes) $ \ms ->
    forM_ [(a,b) | a <- ms, b <- ms, a < b] $ \(a,b) ->
      when ((permission raised a == Red || permission raised b == Red) && up IM.! a == up IM.! b)
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
      [IS.delete (image m) (reachable sk (image m)) | (m,v) <- IM.toList (nodes old), tag v == Bot]
    candidates n = IS.toList $ IS.fromList (map image (mapMaybe (binder . nodeAt old) (members n)))
      `IS.union` (if IS.member n grafted then IM.findWithDefault IS.empty n parents else IS.empty)
    dependencies n = IS.fromList (candidates n) `IS.union` IM.findWithDefault IS.empty n parents
    buildTree tree [] = pure tree
    buildTree tree todo = case find (\n -> all (`IM.member` tree) (IS.toList (dependencies n))) todo of
      Nothing -> Left "cyclic structure/binding dependencies"
      Just n -> do
        b <- lca tree (candidates n)
        buildTree (IM.insert n b tree) (filter (/=n) todo)
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
expand gen destination = do
  g <- get
  let source = genRoot g gen
      visit seen n0
        | IS.member n seen = seen
        | not (underBinder g n gen) = IS.insert n seen
        | otherwise = foldl visit (IS.insert n seen) (children (tag (nodeAt g n)))
        where n = resolve g n0
      originals = IS.toList (visit IS.empty source)
  copies <- IM.fromList <$> mapM (\n -> do c <- freshId; pure (n,c)) originals
  let copy n = IM.findWithDefault (resolve g n) (resolve g n) copies
      root = copy source
      frontier = [n | n <- originals, not (underBinder g n gen)]
  forM_ originals $ \n -> do
    let v = nodeAt g n
        new | n `elem` frontier = Node Bot (Just destination) Flexible
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
    norm n v = case tag v of
      Gen _ -> v
      _ | inert g n || schemeOrExistential n v -> v { flag = Rigid }
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
