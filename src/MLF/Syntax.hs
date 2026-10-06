module MLF.Syntax
  ( Flag (..), Type (..), Annotation (..), Expr (..)
  ) where

-- | Flexible instance bounds and rigid (annotation) bounds, respectively.
data Flag = Flexible | Rigid deriving (Eq, Ord, Show)

-- | Source names are resolved to graph identities before inference.
data Type
  = TVar String
  | Bottom
  | Arrow Type Type
  | Con String [Type]
  | Forall Flag String Type Type
  deriving (Eq, Show)

-- | Existentials are shared by the domain and codomain of a coercion (§12.3.2).
data Annotation = Annotation [String] Type deriving (Eq, Show)

data Expr
  = Var String
  | Lam String (Maybe Annotation) Expr
  | App Expr Expr
  | Let String Expr Expr
  | Ann Expr Annotation
  | IntLit Integer
  | BoolLit Bool
  deriving (Eq, Show)

