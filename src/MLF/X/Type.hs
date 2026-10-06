module MLF.X.Type
  ( TyVar (..), Type (..), freeVars, allVars, substitute, alphaEq ) where

import qualified Data.Map.Strict as Map
import qualified Data.Set as Set

-- | Identities, not display names. Inference uses nonnegative graph node IDs.
newtype TyVar = TyVar { tyVarId :: Int } deriving (Eq, Ord, Show)

-- | Figure 14.2.1. Rigid bounds have already been inlined.
data Type
  = Var TyVar
  | Bot
  | Arrow Type Type
  | Con String [Type]
  | Forall TyVar Type Type
  deriving (Eq, Show)

freeVars :: Type -> Set.Set TyVar
freeVars ty = case ty of
  Var a -> Set.singleton a
  Bot -> Set.empty
  Arrow a b -> freeVars a `Set.union` freeVars b
  Con _ ts -> Set.unions (map freeVars ts)
  Forall a bound body -> freeVars bound `Set.union` Set.delete a (freeVars body)

allVars :: Type -> Set.Set TyVar
allVars ty = case ty of
  Var a -> Set.singleton a
  Bot -> Set.empty
  Arrow a b -> allVars a `Set.union` allVars b
  Con _ ts -> Set.unions (map allVars ts)
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
      Arrow x y -> Arrow (go x) (go y)
      Con c ts -> Con c (map go ts)
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
      (Arrow x y, Arrow z w) -> go l r depth x z && go l r depth y w
      (Con c xs, Con d ys) -> c == d && length xs == length ys && and (zipWith (go l r depth) xs ys)
      (Forall x xb xt, Forall y yb yt) ->
        go l r depth xb yb && go (Map.insert x depth l) (Map.insert y depth r) (depth+1) xt yt
      _ -> False
