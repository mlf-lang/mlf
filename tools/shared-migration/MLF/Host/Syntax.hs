module MLF.Host.Syntax where

import MLF.Host.Lexer (Token)

data Module = Module String (Maybe [Export]) [Import] [Decl] deriving Show
data Export = ValueExport String | TypeExport String (Maybe [String]) | ModuleExport String deriving Show
data Import = Import Bool String (Maybe String) (Maybe (Bool,[Export])) deriving Show
data Type = TyName String | TyApp Type Type | TyArrow Type Type
          | TyForall [(String,Maybe Kind)] Type | TyContext [Type] Type deriving Show
data Kind = Star | KArrow Kind Kind deriving Show
data Pattern = PVar String | PWild | PCon String [Pattern] | PLit Literal
             | PAnn String Type deriving Show
data Literal = LInteger String | LDouble String | LString String | LBool Bool deriving (Eq, Show)
data Expr = Var String | Lit Literal | App Expr Expr | Lambda [Pattern] Expr
          | Case Expr [(Pattern,Expr)] | If Expr Expr Expr | Let Bool [Decl] Expr
          | Do [Statement] | Ann Expr Type deriving Show
data Statement = Bind Pattern Expr | Then Expr | Local Bool [Decl] deriving Show
data Decl = Signature Token String Type | Equation Token String [Pattern] (Maybe Type) Expr
          | Data Token String [(String,Maybe Kind)] [(String,[Type])]
          | Class Token [Type] String [(String,Maybe Kind)] [(String,Type)]
          | Instance Token [(String,Maybe Kind)] [Type] String [Type] [Decl] deriving Show

apps :: Expr -> [Expr] -> Expr
apps = foldl App

patVars :: Pattern -> [String]
patVars p = case p of
  PVar n -> [n]
  PAnn n _ -> [n]
  PCon _ ps -> concatMap patVars ps
  _ -> []
