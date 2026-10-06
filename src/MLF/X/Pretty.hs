module MLF.X.Pretty (prettyType, prettyTerm, prettyComputation) where

import MLF.X.Syntax
import MLF.X.Type

variable :: TyVar -> String
variable (TyVar n) | n < 0 = "z" ++ show (-n)
                   | otherwise = "a" ++ show n

name :: Name -> String
name (Name i hint) = hint ++ "_" ++ show i

parenthesize :: Bool -> String -> String
parenthesize True s = "(" ++ s ++ ")"
parenthesize False s = s

prettyType :: Type -> String
prettyType = ty (0 :: Int)
  where
    ty p t = case t of
      Var a -> variable a
      Bot -> "bot"
      Arrow a b -> parenthesize (p > 1) (ty 2 a ++ " -> " ++ ty 1 b)
      Con c [] -> c
      Con c ts -> parenthesize (p > 2) (unwords (c : map (ty 3) ts))
      Forall a Bot b -> parenthesize (p > 0) ("forall " ++ variable a ++ ". " ++ ty 0 b)
      Forall a bound b -> parenthesize (p > 0)
        ("forall (" ++ variable a ++ " >= " ++ ty 0 bound ++ "). " ++ ty 0 b)

prettyComputation :: Computation -> String
prettyComputation p = case p of
  Refl -> "id"
  Bottom t -> "bot(" ++ prettyType t ++ ")"
  Hyp a -> "hyp(" ++ variable a ++ ")"
  Inner q -> "inner(" ++ prettyComputation q ++ ")"
  Outer a q -> "outer(" ++ variable a ++ ", " ++ prettyComputation q ++ ")"
  Elim -> "elim"
  Intro a -> "intro(" ++ variable a ++ ")"
  Then a b -> prettyComputation a ++ "; " ++ prettyComputation b

prettyTerm :: Term -> String
prettyTerm = term (0 :: Int)
  where
    term p t = case t of
      VarTerm n -> name n
      Abs n ty b -> parenthesize (p > 0) ("\\(" ++ name n ++ " : " ++ prettyType ty ++ ") -> " ++ term 0 b)
      App f a -> parenthesize (p > 1) (term 1 f ++ " " ++ term 2 a)
      TypeAbs a bound b -> parenthesize (p > 0)
        ("/\\(" ++ variable a ++ " >= " ++ prettyType bound ++ ") -> " ++ term 0 b)
      TypeApp a phi -> term 2 a ++ "[" ++ prettyComputation phi ++ "]"
      Let n a b -> parenthesize (p > 0) ("let " ++ name n ++ " = " ++ term 0 a ++ " in " ++ term 0 b)
      IntTerm n -> show n
      BoolTerm b -> if b then "true" else "false"

