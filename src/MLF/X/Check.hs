module MLF.X.Check
  ( TypeEnv, Env (..), emptyEnv, wellFormed, checkComputation, infer, checkClosed ) where

import Control.Monad (unless, when)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import MLF.X.Syntax
import MLF.X.Type

type TypeEnv = Map.Map TyVar Type
data Env = Env { typeEnv :: TypeEnv, termEnv :: Map.Map Name Type } deriving Show

emptyEnv :: Env
emptyEnv = Env Map.empty Map.empty

wellFormed :: TypeEnv -> Type -> Either String ()
wellFormed env ty = case ty of
  Var a -> unless (Map.member a env) (Left ("unbound type variable " ++ show a))
  Bot -> pure ()
  Arrow a b -> wellFormed env a >> wellFormed env b
  Con c args -> do
    when (c `elem` ["Int", "Bool"] && not (null args)) (Left ("invalid arity for " ++ c))
    mapM_ (wellFormed env) args
  Forall a bound body -> do
    -- Quantifiers inside a TYPE are lexical: a shared graph type can be
    -- inlined in multiple scopes, including one with the same display ID.
    -- Only its free variables matter (Figure 14.2.4). This does not relax the
    -- freshness checks on term abstractions or computation binders.
    wellFormed env bound
    wellFormed (Map.insert a bound env) body

fresh :: TypeEnv -> TyVar -> Either String ()
fresh env a = when (Map.member a env) (Left ("type binder already in scope: " ++ show a))

-- | Figure 14.2.6, including the Inst-Hyp premise deliberately omitted by
-- the thesis's unchecked type-computation function (Figure 14.2.7).
checkComputation :: TypeEnv -> Computation -> Type -> Either String Type
checkComputation env computation source = do
  validateTypeEnv env
  wellFormed env source
  result <- go computation source
  wellFormed env result
  pure result
  where
    go p s = case (p,s) of
      (Refl, _) -> pure s
      (Bottom t, Bot) -> wellFormed env t >> pure t
      (Hyp a, _) -> case Map.lookup a env of
        Just bound | alphaEq bound s -> pure (Var a)
        Just _ -> Left ("Inst-Hyp bound mismatch for " ++ show a)
        Nothing -> Left ("Inst-Hyp unbound variable " ++ show a)
      (Then p1 p2, _) -> checkComputation env p1 s >>= checkComputation env p2
      (Inner q, Forall a bound body) -> do
        bound' <- checkComputation env q bound
        pure (Forall a bound' body)
      (Outer a q, Forall b bound body) -> do
        fresh env a
        when (a /= b && a `Set.member` freeVars body) (Left "Inst-Outer would capture a variable")
        let body' = substitute b (Var a) body
        result <- checkComputation (Map.insert a bound env) q body'
        pure (Forall a bound result)
      (Elim, Forall a bound body) -> pure (substitute a bound body)
      (Intro a, _) -> do
        fresh env a
        when (a `Set.member` freeVars s) (Left "Inst-Quant-Intro would capture a variable")
        pure (Forall a Bot s)
      _ -> Left ("computation " ++ show p ++ " does not apply to " ++ show s)

-- | This checker neither imports nor calls the inference graph or solver.
infer :: Env -> Term -> Either String Type
infer env term = do
  validateTypeEnv (typeEnv env)
  mapM_ (wellFormed (typeEnv env)) (Map.elems (termEnv env))
  inferIn env term

inferIn :: Env -> Term -> Either String Type
inferIn env term = case term of
  VarTerm x -> maybe (Left ("unbound term variable " ++ nameHint x)) pure (Map.lookup x (termEnv env))
  Abs x t body -> do
    wellFormed (typeEnv env) t
    when (Map.member x (termEnv env)) (Left "term binder already in scope")
    Arrow t <$> inferIn env { termEnv = Map.insert x t (termEnv env) } body
  App f a -> do
    ft <- inferIn env f
    at <- inferIn env a
    case ft of
      Arrow domain result | alphaEq domain at -> pure result
                          | otherwise -> Left ("application type mismatch: expected " ++ show domain ++ ", got " ++ show at)
      _ -> Left ("application of a non-function: " ++ show ft)
  TypeAbs a bound body -> do
    fresh (typeEnv env) a
    wellFormed (typeEnv env) bound
    Forall a bound <$> inferIn env { typeEnv = Map.insert a bound (typeEnv env) } body
  TypeApp t p -> inferIn env t >>= checkComputation (typeEnv env) p
  Let x a b -> do
    when (Map.member x (termEnv env)) (Left "term binder already in scope")
    t <- inferIn env a
    inferIn env { termEnv = Map.insert x t (termEnv env) } b
  IntTerm _ -> pure (Con "Int" [])
  BoolTerm _ -> pure (Con "Bool" [])

checkClosed :: Term -> Either String Type
checkClosed = infer emptyEnv

validateTypeEnv :: TypeEnv -> Either String ()
validateTypeEnv env = mapM_ (visit Set.empty) (Map.keys env)
  where
    visit path a
      | a `Set.member` path = Left "cyclic type environment"
      | otherwise = case Map.lookup a env of
          Nothing -> Left ("unbound variable in type environment: " ++ show a)
          Just bound -> do
            wellFormed (Map.delete a env) bound
            mapM_ (visit (Set.insert a path)) (Set.toList (freeVars bound))
