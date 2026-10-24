-- Offline post-cutover adjustment: standard Haskell class identities.
module Hierarchy (standardHierarchy, standardInstance) where

import Control.Monad (unless)
import Data.Char (toLower)
import qualified Data.Set as S
import MLF.Host.Syntax

-- The legacy class has precisely return and bind. Keep their computations as
-- existing helper references, or lift their equations unchanged to closed,
-- signed helpers. All new methods use those computations in left-to-right
-- monadic order. No standard default is overridden in the Monad instance.
standardHierarchy :: [String] -> Module -> Either String Module
standardHierarchy names (Module n ex im ds) =
  Module n ex im . concat <$> mapM (standardInstance names) ds

standardInstance :: [String] -> Decl -> Either String [Decl]
standardInstance names original@(Instance t vs cs "Monad" [m] methods)
  | any ((== "bind") . declared) methods = do
      unless (all ((`elem` ["return", "bind"]) . declared) methods)
        (Left "legacy Monad instance has an unexpected member")
      (pureHelpers, pureExpr) <- method "return" "Pure" pureType
      (bindHelpers, bindExpr) <- method "bind" "Bind" bindType
      let freeHelpers = S.fromList [n | Var n <- [pureExpr,bindExpr]]
          choose n = head [v | v <- n:[n++show i | i <- [1::Int ..]], S.notMember v freeHelpers]
          function = choose "function"; action = choose "action"
          argument = choose "argument"; value = choose "value"
          callBind a b = apps bindExpr [a,b]
          callPure a = App pureExpr a
          result = callPure (App (Var function) (Var value))
          eq n ps b = Equation t n (map PVar ps) Nothing b
          inst cls body = Instance t vs cs cls [m] body
      pure (pureHelpers ++ bindHelpers ++
        [inst "Functor" [eq "fmap" [function,action]
            (callBind (Var action) (Lambda [PVar value] result))],
         inst "Applicative" [eq "pure" [] pureExpr,
            eq "(<*>)" [action,argument]
              (callBind (Var action) (Lambda [PVar function]
                (callBind (Var argument) (Lambda [PVar value] result))))],
         inst "Monad" [eq "(>>=)" [] bindExpr]])
  where
    a = unused "a"; b = unused "b"
    unused n = head [v | v <- n:[n++show i | i <- [1::Int ..]], v `notElem` map fst vs]
    ma ty = TyApp m (TyName ty)
    quantified ty = TyForall (vs++[(a,Nothing)]++[(b,Nothing) | usesB ty])
      (if null cs then ty else TyContext cs ty)
    usesB ty = b `S.member` typeNames ty
    pureType = quantified (TyArrow (TyName a) (ma a))
    bindType = quantified (TyArrow (ma a) (TyArrow (TyArrow (TyName a) (ma b)) (ma b)))
    base = case headType m of { c:rest -> toLower c:rest; [] -> "monad" }
    method old suffix signature = case [d | d <- methods, declared d == old] of
      [Equation _ _ [] Nothing body@(Var _)] -> pure ([],body)
      equations@(_:_) | all isEquation equations -> do
        let helper = base++suffix
        unless (helper `notElem` names) (Left ("Monad helper name collides: "++helper))
        pure (Signature t helper signature:map (rename helper) equations,Var helper)
      _ -> Left ("legacy Monad member is missing or unsupported: "++old)
    isEquation Equation{} = True
    isEquation _ = False
    rename n (Equation tok _ ps ann body) = Equation tok n ps ann body
    rename _ _ = error "non-equation member"
standardInstance _ d = Right [d]

declared (Equation _ n _ _ _) = n
declared (Signature _ n _) = n
declared _ = ""
headType (TyName n) = n
headType (TyApp a _) = headType a
headType _ = ""
typeNames ty = case ty of
  TyName n -> S.singleton n
  TyApp a b -> typeNames a `S.union` typeNames b
  TyArrow a b -> typeNames a `S.union` typeNames b
  TyForall vs b -> typeNames b S.\\ S.fromList (map fst vs)
  TyContext cs b -> S.unions (map typeNames (b:cs))
