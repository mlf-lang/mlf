module MLF.Syntax
  ( Flag (..), Type (..), Annotation (..), Expr (..)
  , Program (..), Pattern (..), Alternative (..), Statement (..)
  , Predicate (..), ClassDecl (..), InstanceDecl (..), EvidenceRole (..)
  ) where

import MLF.Data (DataDecl)
import MLF.Kind (Kind)
import MLF.Primitive (Primitive)

-- | Flexible instance bounds and rigid (annotation) bounds, respectively.
data Flag = Flexible | Rigid deriving (Eq, Ord, Show)

-- | Source names are resolved to graph identities before inference.
data Type
  = TVar String
  | Bottom
  | BottomKind Kind
  | Arrow Type Type
  | Con String [Type]
  | TypeApp Type Type
  | Forall Flag String Type Type
  | Qualified [Predicate] Type
  deriving (Eq, Show)

-- | Existentials are shared by the domain and codomain of a coercion (§12.3.2).
data Annotation = Annotation [String] Type deriving (Eq, Show)

data Expr
  = Var String
  | Constructor String
  | Lam String (Maybe Annotation) Expr
  | App Expr Expr
  | Let String Expr Expr
  | Ann Expr Annotation
  | IntLit Integer
  | DoubleLit Double
  | BoolLit Bool
  | StringLit String
  | Primitive Primitive
  | Case Expr [Alternative]
  | Do [Statement] Expr
  -- Surface function equations are eliminated before inference.
  | Equations [([Pattern], Expr)]
  -- Recursive groups have explicit, closed signatures.
  | LetRec [(String, Annotation, Expr)] Expr
  -- Internal forms introduced by dictionary translation.
  | Wanted String [(EvidenceRole, String)]
  | Checked Type Expr
  deriving (Eq, Show)

data Pattern
  = ConstructorPattern String [Maybe String]
  | DefaultPattern (Maybe String)
  | NestedPattern String [Pattern]
  | AnnotatedPattern String Annotation
  | IntPattern Integer
  | StringPattern String
  | BoolPattern Bool
  deriving (Eq, Show)

data Alternative = Alternative Pattern Expr deriving (Eq, Show)

data Statement
  = DoBind Pattern Expr
  | DoThen Expr
  | DoLet String (Maybe Annotation) Expr
  | DoLetRec [(String, Annotation, Expr)]
  deriving (Eq, Show)

data Predicate = Predicate String [Type] deriving (Eq, Show)

data ClassDecl = ClassDecl
  { className :: String
  , classParameters :: [(String, Kind)]
  , superclasses :: [Predicate]
  , classMethods :: [(String, Type)]
  } deriving (Eq, Show)

data InstanceDecl = InstanceDecl
  { instanceVariables :: [(String, Kind)]
  , instanceContext :: [Predicate]
  , instanceClass :: String
  , instanceHead :: [Type]
  , instanceMethods :: [(String, Expr)]
  } deriving (Eq, Show)

data EvidenceRole = GivenEvidence | SuperclassEvidence | InstanceEvidence
  deriving (Eq, Ord, Show)

data Program = Program [DataDecl] Expr
             | ClassProgram [DataDecl] [ClassDecl] [InstanceDecl] Expr
  deriving (Eq, Show)
