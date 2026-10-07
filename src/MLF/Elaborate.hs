module MLF.Elaborate
  ( elaborate, elaborateResolved, resolveEvidence, typeAt, reference, schemeType, proveInstance ) where

import Control.Monad (unless)
import qualified Data.IntMap.Strict as IM
import qualified Data.Map.Strict as Map
import MLF.Graph
import qualified MLF.Graph.Solver as Solver
import MLF.Constraint
import MLF.Syntax (Flag (..))
import qualified MLF.X.Type as T
import qualified MLF.X.Syntax as X
import qualified MLF.X.Check as Check
import qualified MLF.Data as D
import MLF.Kind
import MLF.Evidence (resolveDictionary)

-- | Figure 15.3.2. Flexible nodes are named; rigid bounds are inlined.
typeAt :: Graph -> NodeId -> T.Type
typeAt g n0 = foldr (uncurry T.Forall) structure (boundsAt g n)
  where
    n = resolve g n0
    child c | flag (nodeAt g c) == Flexible = T.Var (T.TyVar (resolve g c))
            | otherwise = typeAt g c
    structure = case tag (nodeAt g n) of
      Bot -> T.Bot
      BotK k -> T.bottomKind k
      Arr a b -> T.Arrow (child a) (child b)
      Con c ns -> T.Con c (map child ns)
      TyCon c _ -> T.Con c []
      Skolem identity _ -> T.Var (T.TyVar identity)
      TyApp f a -> T.apply (child f) (child a)
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
  actual <- Check.checkComputationIn datatypes env phi source
  unless (T.alphaEq actual target) (Left "instance evidence has the wrong target")
  pure phi
  where
    datatypes = D.withKinds [(c,k) | Node (TyCon c k) _ _ <- IM.elems (nodes targetGraph)]
    go gamma s t
      | T.alphaEq s t = pure X.Refl
      | s == T.Bot = pure (X.Bottom t)
      | T.BotKind _ <- s = pure (X.Bottom t)
      | otherwise = case t of
          T.Var a -> case Map.lookup a gamma of
            Nothing -> Left ("missing target abstraction: " ++ show a)
            Just bound -> do
              p <- go gamma s bound
              pure (X.compose p (X.Hyp a))
          T.Forall a bound body -> do
            p <- go (Map.insert a bound gamma) s body
            k <- T.kindOf datatypes gamma bound
            let introduction = X.compose (if k == Star then X.Intro a else X.IntroKind a k)
                  (if bound == T.bottomKind k then X.Refl else X.Inner (X.Bottom bound))
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

-- | Reflexive edges need only Inst-Refl, whose proof uses no node image.
-- Otherwise re-expand the FINAL presolution (§15.3.10), solve the frontier
-- first (§15.2.2), and translate only the interior copy's correspondence.
edgeComputation :: Solver.Solver -> Check.TypeEnv -> Edge -> Either String X.Computation
edgeComputation solver env edge
  | T.alphaEq source targetType = proveInstance g id env source targetType
  | otherwise = do
      (copies,result) <- Solver.witness (fromGen edge) target solver
      let solved = Solver.graph result
      let image n = resolve solved (IM.findWithDefault n n copies)
      proveInstance g image env source targetType
  where
    g = Solver.graph solver
    target = resolve g (toNode edge)
    source = schemeType g (fromGen edge)
    targetType = reference g target

-- | Figure 15.3.5, including the coercion-function translation of §15.3.8.
elaborate :: Graph -> Typed -> Either String X.Term
elaborate graph typed = do
  evidence <- resolveEvidence graph typed
  elaborateResolved graph evidence typed

resolveEvidence :: Graph -> Typed -> Either String (Map.Map NodeId X.Term)
resolveEvidence graph = go Map.empty
  where
    ds = D.withKinds [(c,k) | Node (TyCon c k) _ _ <- IM.elems (nodes graph)]
    go outer typed = do
      let gen = generalization typed
          env = foldl (\e (a,b) -> Map.insert a b e) outer (boundsAt graph gen)
          child = go env
      case form typed of
        Evidence candidates -> do
          let candidate (EvidenceBinding role n t polymorphic) =
                (role,n,if polymorphic then schemeType graph t else reference graph t)
          term <- resolveDictionary ds env (map candidate candidates) (reference graph (genRoot graph gen))
          pure (Map.singleton gen term)
        Lambda _ _ b _ -> child b
        Apply a b _ _ -> Map.union <$> child a <*> child b
        Binding _ a b _ -> Map.union <$> child a <*> child b
        Match a _ bs -> Map.unions <$> mapM child (a : [b | Branch _ b _ <- bs])
        Recursive definitions b _ -> Map.unions <$> mapM child (b : [a | (_,_,a,_) <- definitions])
        Checked variables b _ -> go (foldl (\e (a,k) -> Map.insert a (T.bottomKind k) e) env variables) b
        _ -> pure Map.empty

elaborateResolved :: Graph -> Map.Map NodeId X.Term -> Typed -> Either String X.Term
elaborateResolved graph evidence typed = do
  solver <- Solver.prepare graph
  go solver Map.empty typed
  where
    go solver outer term = do
      let gen = generalization term
          bs = boundsAt graph gen
          env = foldl (\gamma (a,b) -> Map.insert a b gamma) outer bs
          inst t e = X.instantiate t <$> edgeComputation solver env e
          child = go solver env
      body <- case form term of
        Variable n Nothing -> pure (X.VarTerm n)
        Variable n (Just e) -> inst (X.VarTerm n) e
        Lambda n domain b e -> do
          b' <- child b >>= (`inst` e)
          pure (X.Abs n (reference graph domain) b')
        Apply a b ea eb -> do
          a' <- child a >>= (`inst` ea)
          b' <- child b >>= (`inst` eb)
          pure (X.App a' b')
        Binding n a b e -> do
          a' <- child a
          b' <- child b >>= (`inst` e)
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
        StringLiteral s -> pure (X.StringTerm s)
        Primitive p ns -> pure (X.Primitive p (map (reference graph) ns))
        Constructor c ns -> pure (X.Constructor c (map (reference graph) ns))
        Match a ea branches -> do
          a' <- child a >>= (`inst` ea)
          bs' <- mapM (\(Branch p b eb) -> X.Alternative p <$> (child b >>= (`inst` eb))) branches
          pure (X.Case a' (reference graph (genRoot graph gen)) bs')
        Recursive definitions b e -> do
          ds <- mapM (\(n,g,a,ea) -> do
            a' <- child a >>= (`inst` ea)
            pure (n,schemeType graph g,a')) definitions
          b' <- child b >>= (`inst` e)
          pure (X.LetRec ds b')
        Evidence _ -> maybe (Left "unresolved dictionary evidence") Right (Map.lookup gen evidence)
        Checked variables b e -> do
          let local = foldl (\gamma (a,k) -> Map.insert a (T.bottomKind k) gamma) env variables
          b' <- go solver local b
          phi <- edgeComputation solver local e
          pure (foldr (\(a,k) -> X.TypeAbs a (T.bottomKind k)) (X.instantiate b' phi) variables)
      pure (foldr (uncurry X.TypeAbs) body bs)
