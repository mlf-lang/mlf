module MLF.X.Syntax
  ( Name (..), Computation (..), Term (..), Pattern (..), Alternative (..)
  , compose, instantiate, typeApplication, patternNames
  , Erased (..), ErasedAlternative (..), erase
  ) where

import MLF.X.Type
import MLF.Data (DataDecl)
import MLF.Kind (Kind)
import qualified MLF.Primitive as P
import Data.Maybe (catMaybes, maybeToList)

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
  | IntroKind TyVar Kind
  | Then Computation Computation
  deriving (Eq, Show)

data Term
  = VarTerm Name
  | Abs Name Type Term
  | App Term Term
  | TypeAbs TyVar Type Term
  | TypeApp Term Computation
  | Let Name Term Term
  | LetRec [(Name, Type, Term)] Term
  | IntTerm Integer
  | DoubleTerm Double
  | BoolTerm Bool
  | StringTerm String
  | Primitive P.Primitive [Type]
  | Constructor String [Type]
  | Case Term Type [Alternative]
  | WithData [DataDecl] Term
  deriving (Eq, Show)

data Pattern
  = ConstructorPattern String [Maybe Name]
  | DefaultPattern (Maybe Name)
  deriving (Eq, Show)

data Alternative = Alternative Pattern Term deriving (Eq, Show)

patternNames :: Pattern -> [Name]
patternNames (ConstructorPattern _ ns) = catMaybes ns
patternNames (DefaultPattern n) = maybeToList n

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
  | ELet Name Erased Erased | EInt Integer | EDouble Double | EBool Bool
  | EString String | EPrimitive P.Primitive
  | ELetRec [(Name, Erased)] Erased
  | EEvidenceHole Int
  | EConstructor String | ECase Erased [ErasedAlternative]
  deriving (Eq, Show)

data ErasedAlternative = ErasedAlternative Pattern Erased deriving (Eq, Show)

erase :: Term -> Erased
erase t = case t of
  VarTerm n -> EVar n
  Abs n _ b -> EAbs n (erase b)
  App f a -> EApp (erase f) (erase a)
  TypeAbs _ _ b -> erase b
  TypeApp a _ -> erase a
  Let n a b -> ELet n (erase a) (erase b)
  LetRec ds b -> ELetRec [(n,erase a) | (n,_,a) <- ds] (erase b)
  IntTerm i -> EInt i
  DoubleTerm d -> EDouble d
  BoolTerm b -> EBool b
  StringTerm s -> EString s
  Primitive p _ -> EPrimitive p
  Constructor c _ -> EConstructor c
  Case a _ alternatives -> ECase (erase a)
    [ErasedAlternative p (erase b) | Alternative p b <- alternatives]
  WithData _ b -> erase b
