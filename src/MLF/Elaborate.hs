module MLF.Elaborate
  ( elaborate, typeAt, reference, schemeType, proveInstance ) where

import Control.Monad (unless)
import qualified Data.IntMap.Strict as IM
import qualified Data.Map.Strict as Map
import MLF.Graph
import MLF.Constraint
import MLF.Syntax (Flag (..))
import qualified MLF.X.Type as T
import qualified MLF.X.Syntax as X
import qualified MLF.X.Check as Check

-- | Figure 15.3.2. Flexible nodes are named; rigid bounds are inlined.
typeAt :: Graph -> NodeId -> T.Type
typeAt g n0 = foldr (uncurry T.Forall) structure (boundsAt g n)
  where
    n = resolve g n0
    child c | flag (nodeAt g c) == Flexible = T.Var (T.TyVar (resolve g c))
            | otherwise = typeAt g c
    structure = case tag (nodeAt g n) of
      Bot -> T.Bot
      Arr a b -> T.Arrow (child a) (child b)
      Con c ns -> T.Con c (map child ns)
      Gen _ -> error "typeAt: a gen node is not a type"

reference :: Graph -> NodeId -> T.Type
reference g n
  | named = T.Var (T.TyVar (resolve g n))
  | otherwise = typeAt g n
  where
    v = nodeAt g n
    named = flag v == Flexible && case binder v of
      Just b -> case tag (nodeAt g b) of Gen _ -> True; _ -> False
      Nothing -> False

boundsAt :: Graph -> NodeId -> [(T.TyVar,T.Type)]
boundsAt g parent =
  [ (T.TyVar n, typeAt g n)
  | n <- orderedBelow g root
  , binder (nodeAt g n) == Just (resolve g parent)
  , flag (nodeAt g n) == Flexible
  ]
  where root = case tag (nodeAt g parent) of Gen s -> s; _ -> parent

schemeType :: Graph -> NodeId -> T.Type
schemeType g gen = foldr (uncurry T.Forall) (reference g (genRoot g gen)) (boundsAt g gen)

-- | Construct a computation from a graph instance's identity map. Quantifiers
-- of the target are introduced in dependency order, then source bounds are
-- instantiated at their mapped nodes and eliminated. This groups the atomic
-- graft/raise/merge/weakening steps of Figure 15.3.4 as suggested in §15.4.1.
-- It also implements the reordering of §15.3.2, without equating reordered types.
-- There is deliberately no congruence rule under arrows or type constructors.
proveInstance :: Graph -> (NodeId -> NodeId) -> Check.TypeEnv -> T.Type -> T.Type -> Either String X.Computation
proveInstance targetGraph image env source target = do
  phi <- go env source target
  actual <- Check.checkComputation env phi source
  unless (T.alphaEq actual target) (Left "instance evidence has the wrong target")
  pure phi
  where
    go gamma s t
      | T.alphaEq s t = pure X.Refl
      | s == T.Bot = pure (X.Bottom t)
      | otherwise = case t of
          T.Var a -> case Map.lookup a gamma of
            Nothing -> Left ("missing target abstraction: " ++ show a)
            Just bound -> do
              p <- go gamma s bound
              pure (X.compose p (X.Hyp a))
          T.Forall a bound body -> do
            p <- go (Map.insert a bound gamma) s body
            let introduction = X.compose (X.Intro a)
                  (if bound == T.Bot then X.Refl else X.Inner (X.Bottom bound))
            pure (X.compose introduction (X.Outer a p))
          _ -> eliminate gamma s t
    eliminate gamma s t = case s of
      T.Forall a bound body -> do
        let n = image (T.tyVarId a)
        unless (IM.member n (nodes targetGraph)) (Left ("instance lost node provenance: " ++ show a))
        let replacement = if Map.member (T.TyVar n) gamma
              then T.Var (T.TyVar n) else typeAt targetGraph n
        p <- go gamma bound replacement
        q <- go gamma (T.substitute a replacement body) t
        pure (X.compose (X.compose (if p == X.Refl then X.Refl else X.Inner p) X.Elim) q)
      _ -> Left ("no permitted instance from " ++ show s ++ " to " ++ show t)

-- | Re-expand each edge of the FINAL presolution (§15.3.10). The frontier is
-- solved first (§15.2.2); only the interior copy's correspondence is translated.
edgeComputation :: Graph -> Check.TypeEnv -> Edge -> Either String X.Computation
edgeComputation g env edge = do
  let target = resolve g (toNode edge)
  destination <- maybe (Left "edge target has no binder") pure (binder (nodeAt g target))
  ((root,copies,frontier),expanded) <- runBuild g (expand (fromGen edge) destination)
  (_,withFrontier) <- runBuild expanded (unify frontier)
  (_,solved) <- runBuild withFrontier (unify [(root,target)])
  let image n = resolve solved (IM.findWithDefault n n copies)
  proveInstance g image env (schemeType g (fromGen edge)) (reference g target)

-- | Figure 15.3.5, including the coercion-function translation of §15.3.8.
elaborate :: Graph -> Typed -> Either String X.Term
elaborate graph = go Map.empty
  where
    go outer typed = do
      let gen = generalization typed
          bs = boundsAt graph gen
          env = foldl (\gamma (a,b) -> Map.insert a b gamma) outer bs
          inst t e = X.instantiate t <$> edgeComputation graph env e
      body <- case form typed of
        Variable n Nothing -> pure (X.VarTerm n)
        Variable n (Just e) -> inst (X.VarTerm n) e
        Lambda n domain b e -> do
          b' <- go env b >>= (`inst` e)
          pure (X.Abs n (reference graph domain) b')
        Apply a b ea eb -> do
          a' <- go env a >>= (`inst` ea)
          b' <- go env b >>= (`inst` eb)
          pure (X.App a' b')
        Binding n a b e -> do
          a' <- go env a
          b' <- go env b >>= (`inst` e)
          pure (X.Let n a' b')
        Coercion n domain codomain -> do
          let local = boundsAt graph (genRoot graph gen)
              gamma = foldl (\acc (a,b) -> Map.insert a b acc) env local
              dom = reference graph domain
              cod = if Map.member (T.TyVar (resolve graph codomain)) gamma
                      then T.Var (T.TyVar (resolve graph codomain)) else typeAt graph codomain
          phi <- proveInstance graph id gamma dom cod
          pure (foldr (uncurry X.TypeAbs) (X.Abs n dom (X.instantiate (X.VarTerm n) phi)) local)
        IntegerLiteral n -> pure (X.IntTerm n)
        BooleanLiteral b -> pure (X.BoolTerm b)
      pure (foldr (uncurry X.TypeAbs) body bs)
