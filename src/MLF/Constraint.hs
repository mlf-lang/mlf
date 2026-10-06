module MLF.Constraint
  ( Edge (..), Typed (..), Form (..), Branch (..), EvidenceBinding (..), Constraints (..)
  , generate, generateProgram, solve, eraseSource, eraseSourceWith
  ) where

import Control.Monad (foldM, forM, forM_, unless, when)
import Control.Monad.State.Strict
import Control.Monad.Writer.Strict
import qualified Data.IntMap.Strict as IM
import qualified Data.IntSet as IS
import qualified Data.Map.Strict as Map
import Data.List (nub)
import Data.Maybe (catMaybes)
import qualified MLF.Data as D
import MLF.Desugar (desugarDo)
import qualified MLF.Primitive as P
import qualified MLF.Syntax as S
import MLF.Kind
import qualified MLF.Kinding as K
import MLF.Graph
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

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
  | StringLiteral String
  | Primitive P.Primitive [NodeId]
  | Constructor String [NodeId]
  | Match Typed Edge [Branch]
  | Recursive [(X.Name, NodeId, Typed, Edge)] Typed Edge
  | Evidence [EvidenceBinding]
  | Checked [(T.TyVar, Kind)] Typed Edge
  deriving (Eq, Show)
data Branch = Branch X.Pattern Typed Edge deriving (Eq, Show)
data EvidenceBinding = EvidenceBinding S.EvidenceRole X.Name NodeId Bool deriving (Eq, Show)
data Constraints = Constraints
  { initialGraph :: Graph
  , skeleton :: Typed
  , equalities :: [(NodeId,NodeId)]
  , instances :: [Edge]
  } deriving Show

data Core
  = CVar String | CLam String Core | CApp Core Core | CLet String Core Core
  | CCoerce S.Annotation | CInt Integer | CBool Bool | CString String
  | CPrimitive P.Primitive
  | CConstructor String | CCase Core [(S.Pattern, Core)]
  | CRec [(String, S.Annotation, Core)] Core
  | CWanted String [(S.EvidenceRole, String)]
  | CChecked S.Type S.Expr

desugar :: S.Expr -> Core
desugar expr = case expr of
  S.Var n -> CVar n
  S.Constructor n -> CConstructor n
  S.Lam x Nothing b -> CLam x (desugar b)
  S.Lam x (Just a) b -> CLam x (CLet x (CApp (CCoerce a) (CVar x)) (desugar b))
  S.App a b -> CApp (desugar a) (desugar b)
  S.Let x a b -> CLet x (desugar a) (desugar b)
  S.Ann a t -> CApp (CCoerce t) (desugar a)
  S.IntLit n -> CInt n
  S.BoolLit b -> CBool b
  S.StringLit s -> CString s
  S.Primitive p -> CPrimitive p
  S.Case a bs -> CCase (desugar a) [(p,desugar b) | S.Alternative p b <- bs]
  S.Do _ _ -> desugar (desugarDo expr)
  S.LetRec ds b -> CRec [(n,t,desugar a) | (n,t,a) <- ds] (desugar b)
  S.Wanted c candidates -> CWanted c candidates
  S.Checked ty body -> CChecked ty body

data Binding = Mono X.Name NodeId | Poly X.Name NodeId
type Generate = WriterT ([(NodeId,NodeId)], [Edge]) Build

-- | Figure 9.4.1, using the scope-correct let variant of §15.2.6.
generate :: S.Expr -> Either String Constraints
generate = generateProgram . S.Program []

generateProgram :: S.Program -> Either String Constraints
generateProgram (S.Program declarations expr) = do
  datatypes <- D.validateDeclarations declarations
  let lowered = desugarDo expr
  validateAnnotations datatypes lowered
  ((t,(eqs,es)),g) <- runBuild emptyGraph (runWriterT (build datatypes Map.empty Nothing Map.empty (desugar lowered)))
  validateGraph g
  pure (Constraints g t eqs es)
generateProgram (S.ClassProgram _ _ _ _) = Left "class declarations must be translated before constraint generation"

build :: D.DataEnv -> Map.Map String NodeId -> Maybe NodeId -> Map.Map String Binding -> Core -> Generate Typed
build datatypes typeScope parent env core = do
  gen <- lift (newNode (Gen (-1)) parent S.Flexible)
  s <- lift (newNode Bot (Just gen) S.Flexible)
  lift (setNode gen (Node (Gen s) parent S.Flexible))
  let child = build datatypes typeScope (Just gen)
      fresh = lift . freshName
      bottom = lift (newNode Bot (Just gen) S.Flexible)
      setTag t = lift (setNode s (Node t (Just gen) S.Flexible))
      edge :: NodeId -> NodeId -> Generate Edge
      edge g target = let e = Edge g target in tell ([],[e]) >> pure e
  let resolvedCore = case core of
        CVar x | Map.notMember x env, Just p <- P.lookupPrimitive x -> CPrimitive p
        _ -> core
  f <- case resolvedCore of
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
    CRec definitions body -> do
      declarations <- forM definitions $ \(x,annotation,_) -> do
        ty <- case annotation of
          S.Annotation [] t -> pure t
          _ -> lift (lift (Left "recursive definitions require a closed signature"))
        name <- fresh x
        declarationGen <- lift (newNode (Gen (-1)) (Just gen) S.Flexible)
        root <- lift (embed datatypes Map.empty ty)
        lift (attach declarationGen S.Flexible root)
        lift (setNode declarationGen (Node (Gen root) (Just gen) S.Flexible))
        pure (x,name,declarationGen,root)
      let scope = Map.union (Map.fromList [(x,Poly n g) | (x,n,g,_) <- declarations]) env
      definitions' <- forM (zip declarations definitions) $ \((_,n,g,target),(_,_,rhs)) -> do
        rhs' <- child scope rhs
        e <- edge (generalization rhs') target
        pure (n,g,rhs',e)
      body' <- child scope body
      e <- edge (generalization body') s
      pure (Recursive definitions' body' e)
    CWanted dictionary candidates -> do
      d <- lift (lift (D.lookupDatatype datatypes dictionary))
      graph <- lift get
      let outermost n = maybe n outermost (binder (nodeAt graph n))
          scopeRoot = outermost gen
      ns <- forM (D.datatypeBinders d) $ \(_,k) ->
        lift (newNode (bottomTag k) (Just scopeRoot) S.Flexible)
      let ps = Map.fromList (zip (D.datatypeParameters d) ns)
      root <- lift (embed datatypes ps (S.Con dictionary (map S.TVar (D.datatypeParameters d))))
      lift (attach gen S.Flexible root)
      tell ([(s,root)],[])
      cs <- forM candidates $ \(role,x) -> case Map.lookup x env of
        Just (Mono n t) -> pure (EvidenceBinding role n t False)
        Just (Poly n g) -> pure (EvidenceBinding role n g True)
        Nothing -> lift (lift (Left ("dictionary candidate is out of scope: " ++ x)))
      pure (Evidence cs)
    CChecked signature expression -> do
      root <- lift (embed datatypes typeScope signature)
      lift (attach gen S.Flexible root)
      tell ([(s,root)],[])
      let leading (S.Forall S.Flexible a S.Bottom body) = let (vs,t) = leading body in ((a,Star):vs,t)
          leading (S.Forall S.Flexible a (S.BottomKind k) body) = let (vs,t) = leading body in ((a,k):vs,t)
          leading ty = ([],ty)
          (variables,expected) = leading signature
      skolems <- forM variables $ \(a,k) -> do
        n <- lift (newNode (bottomTag k) (Just gen) S.Rigid)
        lift (setNode n (Node (Skolem n k) (Just gen) S.Rigid))
        pure (a,n,k)
      let local = Map.union (Map.fromList [(a,n) | (a,n,_) <- skolems]) typeScope
          directed ty (S.Lam x annotation body) | S.Arrow domain result <- ty =
            S.Lam x (Just (maybe (S.Annotation [] domain) id annotation)) (directed result body)
          directed _ e = e
      target <- lift (embed datatypes local expected)
      lift (attach gen S.Rigid target)
      checked <- build datatypes local (Just gen) env
        (desugar (S.Ann (directed expected expression) (S.Annotation [] expected)))
      e <- edge (generalization checked) target
      pure (Checked [(T.TyVar n,k) | (_,n,k) <- skolems] checked e)
    CCoerce (S.Annotation existentials ty) -> do
      existentialEnv <- lift $ Map.fromList <$> forM existentials (\x -> do
        n <- newNode Bot (Just gen) S.Flexible
        pure (x,n))
      domain <- lift (embed datatypes (Map.union existentialEnv typeScope) ty)
      result <- lift (embed datatypes (Map.union existentialEnv typeScope) ty)
      lift $ do
        attach s S.Rigid domain
        attach s S.Flexible result
      setTag (Arr domain result)
      name <- fresh "coerce"
      pure (Coercion name domain result)
    CInt n -> setTag (Con "Int" []) >> pure (IntegerLiteral n)
    CBool b -> setTag (Con "Bool" []) >> pure (BooleanLiteral b)
    CString value -> setTag (Con "String" []) >> pure (StringLiteral value)
    CPrimitive primitive -> do
      let (parameters,signature) = P.primitiveSignature primitive
      ns <- mapM (\(_,k) -> lift (newNode (bottomTag k) (Just gen) S.Flexible)) parameters
      ty <- lift (lift (sourceField signature))
      root <- lift (embed datatypes (Map.fromList (zip (map fst parameters) ns)) ty)
      lift (attach gen S.Flexible root)
      tell ([(s,root)],[])
      pure (Primitive primitive ns)
    CConstructor c -> do
      (d,ctor) <- lift (lift (D.lookupConstructor datatypes c))
      ns <- mapM (\(_,k) -> lift (newNode (bottomTag k) (Just gen) S.Flexible)) (D.datatypeBinders d)
      let variables = Map.fromList (zip (D.datatypeParameters d) ns)
          result = S.Con (D.datatypeName d) (map S.TVar (D.datatypeParameters d))
      fields <- lift (lift (mapM sourceField (D.constructorFields ctor)))
      root <- lift (embed datatypes variables (foldr S.Arrow result fields))
      lift (attach gen S.Flexible root)
      tell ([(s,root)],[])
      pure (Constructor c ns)
    CCase scrutinee alternatives -> do
      owner <- lift (lift (D.checkAlternatives datatypes (map (patternShape . fst) alternatives)))
      domain <- bottom
      parameters <- case owner of
        Nothing -> pure Map.empty
        Just d -> do
          ns <- mapM (\(_,k) -> lift (newNode (bottomTag k) (Just gen) S.Flexible)) (D.datatypeBinders d)
          let ps = Map.fromList (zip (D.datatypeParameters d) ns)
          root <- lift (embed datatypes ps (S.Con (D.datatypeName d) (map S.TVar (D.datatypeParameters d))))
          lift (attach gen S.Flexible root)
          tell ([(domain,root)],[])
          pure ps
      a <- child env scrutinee
      ea <- edge (generalization a) domain
      bs <- forM alternatives $ \(p,b) -> do
        (pattern',bindings) <- case p of
          S.ConstructorPattern c names -> do
            (_,ctor) <- lift (lift (D.lookupConstructor datatypes c))
            fields <- forM (D.constructorFields ctor) $ \field -> do
              ty <- lift (lift (sourceField field))
              n <- lift (embed datatypes parameters ty)
              lift (attach gen S.Rigid n)
              pure n
            let used = catMaybes names
            unless (length used == length (nub used))
              (lift (lift (Left "duplicate pattern variable")))
            resolved <- mapM (traverse fresh) names
            let bindings = [(x,Mono name n) | (Just x,Just name,n) <- zip3 names resolved fields]
            pure (X.ConstructorPattern c resolved,bindings)
          S.DefaultPattern name -> do
            resolved <- traverse fresh name
            pure (X.DefaultPattern resolved,
              [(x,Mono n domain) | Just x <- [name], Just n <- [resolved]])
        b' <- child (Map.union (Map.fromList bindings) env) b
        eb <- edge (generalization b') s
        pure (Branch pattern' b' eb)
      pure (Match a ea bs)
  pure (Typed gen f)

sourceField :: D.Field -> Either String S.Type
sourceField f = case f of
  D.Parameter p -> pure (S.TVar p)
  D.Function a b -> S.Arrow <$> sourceField a <*> sourceField b
  D.Applied c ts -> S.Con c <$> mapM sourceField ts
  D.Application f' a -> S.TypeApp <$> sourceField f' <*> sourceField a
  D.Quantified a k b -> S.Forall S.Flexible a (if k == Star then S.Bottom else S.BottomKind k) <$> sourceField b

patternShape :: S.Pattern -> (Maybe String, Int)
patternShape (S.ConstructorPattern c ns) = (Just c,length ns)
patternShape (S.DefaultPattern _) = (Nothing,0)

validateAnnotations :: D.DataEnv -> S.Expr -> Either String ()
validateAnnotations ds = go Map.empty
  where
    go scope e = case e of
      S.Var _ -> pure ()
      S.Constructor _ -> pure ()
      S.Lam _ a b -> mapM_ (annotation scope) a >> go scope b
      S.App a b -> go scope a >> go scope b
      S.Let _ a b -> go scope a >> go scope b
      S.Ann a t -> go scope a >> annotation scope t
      S.IntLit _ -> pure ()
      S.BoolLit _ -> pure ()
      S.StringLit _ -> pure ()
      S.Primitive _ -> pure ()
      S.Case a bs -> go scope a >> mapM_ (\(S.Alternative _ b) -> go scope b) bs
      S.Do _ _ -> go scope (desugarDo e)
      S.LetRec bs b -> mapM_ (\(_,t,a) -> annotation scope t >> go scope a) bs >> go scope b
      S.Wanted _ _ -> pure ()
      S.Checked ty a -> do
        K.annotationType ds scope ty
        local <- binders scope ty
        go local a
    binders scope (S.Forall _ a bound body) = do
      k <- K.kindOf ds scope bound
      binders (Map.insert a k scope) body
    binders scope _ = pure scope
    annotation scope (S.Annotation xs t) = K.annotationType ds (Map.union (Map.fromList [(x,Star) | x <- xs]) scope) t

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
embed :: D.DataEnv -> Map.Map String NodeId -> S.Type -> Build NodeId
embed ds env ty = do
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
      S.BottomKind k -> newNode (bottomTag k) Nothing S.Flexible
      S.Arrow a b -> do
        r <- newNode Bot Nothing S.Rigid
        x <- go scope a
        y <- go scope b
        forM_ [x,y] $ \n -> unless (n `elem` Map.elems scope) (attach r S.Rigid n)
        setNode r (Node (Arr x y) Nothing S.Rigid)
        pure r
      S.Con c ts -> do
        let k = D.constructorKind ds c (length ts)
        h <- newNode (if k == Star then Con c [] else TyCon c k) Nothing S.Rigid
        foldM (\f a -> go scope a >>= application scope f) h ts
      S.TypeApp f a -> do
        x <- go scope f
        y <- go scope a
        application scope x y
      S.Forall f x bound body -> do
        b <- go scope bound
        result <- go (Map.insert x b scope) body
        g <- get
        when (b /= result && IS.member b (reachable g result) && b `notElem` Map.elems scope) $
          setNode b (nodeAt g b) { binder = Just result, flag = f }
        pure result
      S.Qualified _ _ -> lift (Left "untranslated class constraint")
    application scope f a = do
      r <- newNode (TyApp f a) Nothing S.Rigid
      forM_ [f,a] $ \n -> unless (n `elem` Map.elems scope) (attach r S.Rigid n)
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
eraseSource = eraseSourceWith Map.empty

eraseSourceWith :: Map.Map NodeId X.Term -> Typed -> X.Erased
eraseSourceWith evidence t = case form t of
  Variable n _ -> X.EVar n
  Lambda n _ b _ -> X.EAbs n (go b)
  Apply a b _ _ -> X.EApp (go a) (go b)
  Binding n a b _ -> X.ELet n (go a) (go b)
  Coercion n _ _ -> X.EAbs n (X.EVar n)
  IntegerLiteral n -> X.EInt n
  BooleanLiteral b -> X.EBool b
  StringLiteral s -> X.EString s
  Primitive p _ -> X.EPrimitive p
  Constructor c _ -> X.EConstructor c
  Match a _ bs -> X.ECase (go a)
    [X.ErasedAlternative p (go b) | Branch p b _ <- bs]
  Recursive ds b _ -> X.ELetRec [(n,go a) | (n,_,a,_) <- ds] (go b)
  Evidence _ -> maybe (X.EEvidenceHole (generalization t)) X.erase (Map.lookup (generalization t) evidence)
  Checked _ b _ -> go b
  where go = eraseSourceWith evidence
