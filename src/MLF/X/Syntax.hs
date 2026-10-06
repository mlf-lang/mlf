module MLF.X.Syntax
  ( Name (..), Computation (..), Term (..), compose, instantiate, typeApplication
  , Erased (..), erase
  ) where

import MLF.X.Type

data Name = Name { nameId :: Int, nameHint :: String } deriving (Show)
instance Eq Name where a == b = nameId a == nameId b
instance Ord Name where compare a b = compare (nameId a) (nameId b)

-- | Exactly the eight computations of Figure 14.2.5.
-- Intro and Outer carry the binder chosen by alpha conversion.
data Computation
  = Refl
  | Bottom Type
  | Hyp TyVar
  | Inner Computation
  | Outer TyVar Computation
  | Elim
  | Intro TyVar
  | Then Computation Computation
  deriving (Eq, Show)

data Term
  = VarTerm Name
  | Abs Name Type Term
  | App Term Term
  | TypeAbs TyVar Type Term
  | TypeApp Term Computation
  | Let Name Term Term
  | IntTerm Integer
  | BoolTerm Bool
  deriving (Eq, Show)

compose :: Computation -> Computation -> Computation
compose Refl b = b
compose a Refl = a
compose a b = Then a b

instantiate :: Term -> Computation -> Term
instantiate t Refl = t
instantiate (TypeApp t a) b = TypeApp t (compose a b)
instantiate t p = TypeApp t p

-- | The derived System F computation of §14.2.2.1.
typeApplication :: Type -> Computation
typeApplication t = Then (Inner (Bottom t)) Elim

data Erased
  = EVar Name | EAbs Name Erased | EApp Erased Erased
  | ELet Name Erased Erased | EInt Integer | EBool Bool
  deriving (Eq, Show)

erase :: Term -> Erased
erase t = case t of
  VarTerm n -> EVar n
  Abs n _ b -> EAbs n (erase b)
  App f a -> EApp (erase f) (erase a)
  TypeAbs _ _ b -> erase b
  TypeApp a _ -> erase a
  Let n a b -> ELet n (erase a) (erase b)
  IntTerm i -> EInt i
  BoolTerm b -> EBool b

