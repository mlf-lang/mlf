module MLF.X.Type
  ( TyVar (..), Type (..), freeVars, allVars, substitute, alphaEq
  , apply, bottomKind, kindOf, instantiateField, applicationView ) where

import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified MLF.Data as D
import MLF.Kind
import Control.Monad (foldM, unless)

-- | Identities, not display names. Inference uses nonnegative graph node IDs.
newtype TyVar = TyVar { tyVarId :: Int } deriving (Eq, Ord, Show)

-- | Figure 14.2.1. Rigid bounds have already been inlined.
data Type
  = Var TyVar
  | Bot
  | BotKind Kind
  | Arrow Type Type
  | Con String [Type]
  | Apply Type Type
  | Forall TyVar Type Type
  deriving (Eq, Show)

freeVars :: Type -> Set.Set TyVar
freeVars ty = case ty of
  Var a -> Set.singleton a
  Bot -> Set.empty
  BotKind _ -> Set.empty
  Arrow a b -> freeVars a `Set.union` freeVars b
  Con _ ts -> Set.unions (map freeVars ts)
  Apply f a -> freeVars f `Set.union` freeVars a
  Forall a bound body -> freeVars bound `Set.union` Set.delete a (freeVars body)

allVars :: Type -> Set.Set TyVar
allVars ty = case ty of
  Var a -> Set.singleton a
  Bot -> Set.empty
  BotKind _ -> Set.empty
  Arrow a b -> allVars a `Set.union` allVars b
  Con _ ts -> Set.unions (map allVars ts)
  Apply f a -> allVars f `Set.union` allVars a
  Forall a bound body -> Set.insert a (allVars bound `Set.union` allVars body)

-- | Capture-avoiding substitution, including the bound of a quantification.
-- A quantified variable is not in scope in its own bound.
substitute :: TyVar -> Type -> Type -> Type
substitute a replacement = go
  where
    go ty = case ty of
      Var b | a == b -> replacement
            | otherwise -> ty
      Bot -> Bot
      BotKind k -> BotKind k
      Arrow x y -> Arrow (go x) (go y)
      Con c ts -> Con c (map go ts)
      Apply f x -> apply (go f) (go x)
      Forall b bound body
        | a == b -> Forall b (go bound) body
        | a `Set.notMember` freeVars body -> Forall b (go bound) body
        | b `Set.member` freeVars replacement ->
            let used = Set.insert a (allVars body `Set.union` allVars replacement)
                choose i | TyVar i `Set.member` used = choose (i-1)
                         | otherwise = TyVar i
                fresh = choose (-1)
            in Forall fresh (go bound) (go (substitute b (Var fresh) body))
        | otherwise -> Forall b (go bound) (go body)

-- | xMLF equality is ONLY alpha equivalence (§15.6), not MLF equivalence.
alphaEq :: Type -> Type -> Bool
alphaEq = go Map.empty Map.empty (0 :: Int)
  where
    go l r depth a b = case (a,b) of
      (Var x, Var y) -> case (Map.lookup x l, Map.lookup y r) of
        (Just i, Just j) -> i == j
        (Nothing, Nothing) -> x == y
        _ -> False
      (Bot, Bot) -> True
      (Bot, BotKind Star) -> True
      (BotKind Star, Bot) -> True
      (BotKind k, BotKind k') -> k == k'
      (Arrow x y, Arrow z w) -> go l r depth x z && go l r depth y w
      (Con c xs, Con d ys) -> c == d && length xs == length ys && and (zipWith (go l r depth) xs ys)
      (Apply f x, Apply g y) -> go l r depth f g && go l r depth x y
      (Forall x xb xt, Forall y yb yt) ->
        go l r depth xb yb && go (Map.insert x depth l) (Map.insert y depth r) (depth+1) xt yt
      -- Con stores a compact application spine; Apply is the general form.
      _ | Just (f,x) <- applicationView a, Just (g,y) <- applicationView b ->
            go l r depth f g && go l r depth x y
      _ -> False

apply :: Type -> Type -> Type
apply (Con c xs) x = Con c (xs ++ [x])
apply f x = Apply f x

applicationView :: Type -> Maybe (Type, Type)
applicationView (Apply f x) = Just (f,x)
applicationView (Con c xs) = case reverse xs of
  x:rest -> Just (Con c (reverse rest),x)
  [] -> Nothing
applicationView _ = Nothing

bottomKind :: Kind -> Type
bottomKind Star = Bot
bottomKind k = BotKind k

kindOf :: D.DataEnv -> Map.Map TyVar Type -> Type -> Either String Kind
kindOf ds bounds ty = do
  kinds <- Map.fromList <$> mapM (\a -> (,) a <$> visit Set.empty a) (Set.toList (freeVars ty))
  go kinds ty
  where
    visit seen a
      | a `Set.member` seen = Left "cyclic type environment"
      | otherwise = case Map.lookup a bounds of
          Nothing -> Left ("unbound type variable " ++ show a)
          Just b -> do
            ks <- Map.fromList <$> mapM (\v -> (,) v <$> visit (Set.insert a seen) v) (Set.toList (freeVars b))
            go ks b
    go env t = case t of
      Var a -> maybe (Left ("unbound type variable " ++ show a)) Right (Map.lookup a env)
      Bot -> pure Star
      BotKind k -> pure k
      Arrow a b -> do
        ka <- go env a
        kb <- go env b
        unless (ka == Star && kb == Star) (Left "function types require kind * arguments")
        pure Star
      Con c args -> mapM (go env) args >>= foldM applyKind (D.constructorKind ds c (length args))
      Apply f a -> do
        kf <- go env f
        ka <- go env a
        applyKind kf ka
      Forall a bound body -> do
        k <- go env bound
        go (Map.insert a k env) body

instantiateField :: Map.Map String Type -> D.Field -> Either String Type
instantiateField env field = case field of
  D.Parameter a -> maybe (Left ("unbound data type parameter: " ++ a)) Right (Map.lookup a env)
  D.Function a b -> Arrow <$> go a <*> go b
  D.Applied c args -> Con c <$> mapM go args
  D.Application f a -> apply <$> go f <*> go a
  D.Quantified n k b -> do
    let used = Set.unions (map allVars (Map.elems env))
        fresh i | TyVar i `Set.member` used = fresh (i-1)
                | otherwise = TyVar i
        a = fresh (-1)
    Forall a (bottomKind k) <$> instantiateField (Map.insert n (Var a) env) b
  where go = instantiateField env
