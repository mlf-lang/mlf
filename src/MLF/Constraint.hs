module MLF.Constraint
  ( Edge (..), Typed (..), Form (..), Constraints (..)
  , generate, solve, eraseSource
  ) where

import Control.Monad (forM, forM_, unless, when)
import Control.Monad.State.Strict
import Control.Monad.Writer.Strict
import qualified Data.IntMap.Strict as IM
import qualified Data.IntSet as IS
import qualified Data.Map.Strict as Map
import qualified MLF.Syntax as S
import MLF.Graph
import qualified MLF.X.Syntax as X

data Edge = Edge { fromGen :: NodeId, toNode :: NodeId } deriving (Eq, Show)
data Typed = Typed { generalization :: NodeId, form :: Form } deriving (Eq, Show)
data Form
  = Variable X.Name (Maybe Edge)
  | Lambda X.Name NodeId Typed Edge
  | Apply Typed Typed Edge Edge
  | Binding X.Name Typed Typed Edge
  | Coercion X.Name NodeId NodeId
  | IntegerLiteral Integer
  | BooleanLiteral Bool
  deriving (Eq, Show)
data Constraints = Constraints
  { initialGraph :: Graph
  , skeleton :: Typed
  , equalities :: [(NodeId,NodeId)]
  , instances :: [Edge]
  } deriving Show

data Core
  = CVar String | CLam String Core | CApp Core Core | CLet String Core Core
  | CCoerce S.Annotation | CInt Integer | CBool Bool

desugar :: S.Expr -> Core
desugar expr = case expr of
  S.Var n -> CVar n
  S.Lam x Nothing b -> CLam x (desugar b)
  S.Lam x (Just a) b -> CLam x (CLet x (CApp (CCoerce a) (CVar x)) (desugar b))
  S.App a b -> CApp (desugar a) (desugar b)
  S.Let x a b -> CLet x (desugar a) (desugar b)
  S.Ann a t -> CApp (CCoerce t) (desugar a)
  S.IntLit n -> CInt n
  S.BoolLit b -> CBool b

data Binding = Mono X.Name NodeId | Poly X.Name NodeId
type Generate = WriterT ([(NodeId,NodeId)], [Edge]) Build

-- | Figure 9.4.1, using the scope-correct let variant of §15.2.6.
generate :: S.Expr -> Either String Constraints
generate expr = do
  ((t,(eqs,es)),g) <- runBuild emptyGraph (runWriterT (build Nothing Map.empty (desugar expr)))
  validateGraph g
  pure (Constraints g t eqs es)

build :: Maybe NodeId -> Map.Map String Binding -> Core -> Generate Typed
build parent env core = do
  gen <- lift (newNode (Gen (-1)) parent S.Flexible)
  s <- lift (newNode Bot (Just gen) S.Flexible)
  lift (setNode gen (Node (Gen s) parent S.Flexible))
  let child = build (Just gen)
      fresh = lift . freshName
      bottom = lift (newNode Bot (Just gen) S.Flexible)
      setTag t = lift (setNode s (Node t (Just gen) S.Flexible))
      edge :: NodeId -> NodeId -> Generate Edge
      edge g target = let e = Edge g target in tell ([],[e]) >> pure e
  f <- case core of
    CVar x -> case Map.lookup x env of
      Nothing -> lift (lift (Left ("unbound variable: " ++ x)))
      Just (Mono name n) -> tell ([(s,n)],[]) >> pure (Variable name Nothing)
      Just (Poly name g) -> Variable name . Just <$> edge g s
    CLam x b -> do
      name <- fresh x
      domain <- bottom
      result <- bottom
      setTag (Arr domain result)
      body <- child (Map.insert x (Mono name domain) env) b
      e <- edge (generalization body) result
      pure (Lambda name domain body e)
    CApp a b -> do
      a' <- child env a
      b' <- child env b
      domain <- bottom
      arrow <- lift (newNode (Arr domain s) (Just gen) S.Flexible)
      e1 <- edge (generalization a') arrow
      e2 <- edge (generalization b') domain
      pure (Apply a' b' e1 e2)
    CLet x a b -> do
      name <- fresh x
      a' <- child env a
      b' <- child (Map.insert x (Poly name (generalization a')) env) b
      e <- edge (generalization b') s
      pure (Binding name a' b' e)
    CCoerce (S.Annotation existentials ty) -> do
      existentialEnv <- lift $ Map.fromList <$> forM existentials (\x -> do
        n <- newNode Bot (Just gen) S.Flexible
        pure (x,n))
      domain <- lift (embed existentialEnv ty)
      result <- lift (embed existentialEnv ty)
      lift $ do
        attach s S.Rigid domain
        attach s S.Flexible result
      setTag (Arr domain result)
      name <- fresh "coerce"
      pure (Coercion name domain result)
    CInt n -> setTag (Con "Int" []) >> pure (IntegerLiteral n)
    CBool b -> setTag (Con "Bool" []) >> pure (BooleanLiteral b)
  pure (Typed gen f)

freshName :: String -> Build X.Name
freshName hint = (`X.Name` hint) <$> freshId

attach :: NodeId -> S.Flag -> NodeId -> Build ()
attach parent f n = do
  g <- get
  let v = nodeAt g n
  when (binder v == Nothing) (setNode n v { binder = Just parent, flag = f })

-- | Figure 8.2.3 with implicit rigid bounds for compound constructor arguments
-- (§8.2.2). Alias, unused, and forall-a.a bounds disappear graphically; treating
-- source alias bounds as xMLF bounds would be unsound (§15.6.2).
embed :: Map.Map String NodeId -> S.Type -> Build NodeId
embed env ty = do
  start <- gets nextId
  root <- go env ty
  g <- get
  let keep = reachable g root
  put g { nodes = IM.filterWithKey (\n _ -> n < start || IS.member n keep) (nodes g) }
  pure root
  where
    go :: Map.Map String NodeId -> S.Type -> Build NodeId
    go scope t = case t of
      S.TVar x -> maybe (lift (Left ("unbound annotation type variable: " ++ x))) pure (Map.lookup x scope)
      S.Bottom -> newNode Bot Nothing S.Flexible
      S.Arrow a b -> do
        r <- newNode Bot Nothing S.Rigid
        x <- go scope a
        y <- go scope b
        forM_ [x,y] $ \n -> unless (n `elem` Map.elems scope) (attach r S.Rigid n)
        setNode r (Node (Arr x y) Nothing S.Rigid)
        pure r
      S.Con c ts -> do
        unless (c `notElem` ["Int","Bool"] || null ts) (lift (Left ("invalid type constructor arity: " ++ c)))
        compound scope (Con c) ts
      S.Forall f x bound body -> do
        b <- go scope bound
        result <- go (Map.insert x b scope) body
        g <- get
        when (b /= result && IS.member b (reachable g result) && b `notElem` Map.elems scope) $
          setNode b (nodeAt g b) { binder = Just result, flag = f }
        pure result
    compound :: Map.Map String NodeId -> ([NodeId] -> Tag) -> [S.Type] -> Build NodeId
    compound scope constructor args = do
      r <- newNode Bot Nothing S.Rigid
      ns <- mapM (go scope) args
      forM_ ns $ \n -> unless (n `elem` Map.elems scope) (attach r S.Rigid n)
      setNode r (Node (constructor ns) Nothing S.Rigid)
      pure r

-- | §12.1.3. Generation emits instance edges after all dependencies. Lambda
-- equalities are solved first, so expansion never generalizes a lambda parameter.
solve :: Constraints -> Either String Graph
solve c = do
  (_,g) <- runBuild (initialGraph c) $ do
    unify (equalities c)
    forM_ (instances c) $ \e -> do
      before <- get
      let target = resolve before (toNode e)
      destination <- maybe (lift (Left "instance target has no binder")) pure (binder (nodeAt before target))
      (root,_,frontier) <- expand (fromGen e) destination
      unify (frontier ++ [(root,target)])
  let normalized = normalize g
  validateGraph normalized
  pure normalized

-- | The exact erasure invariant of §15.3.14, after the source annotation
-- desugaring of §12.3.2 (a coercion erases to the identity function).
eraseSource :: Typed -> X.Erased
eraseSource t = case form t of
  Variable n _ -> X.EVar n
  Lambda n _ b _ -> X.EAbs n (eraseSource b)
  Apply a b _ _ -> X.EApp (eraseSource a) (eraseSource b)
  Binding n a b _ -> X.ELet n (eraseSource a) (eraseSource b)
  Coercion n _ _ -> X.EAbs n (X.EVar n)
  IntegerLiteral n -> X.EInt n
  BooleanLiteral b -> X.EBool b
