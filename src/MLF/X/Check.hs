module MLF.X.Check
  ( TypeEnv, Env (..), emptyEnv, wellFormed, checkComputation, checkComputationIn, infer, inferWithData, checkClosed ) where

import Control.Monad (forM_, unless, when)
import Data.Char (ord)
import Data.List (nub)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified MLF.Data as D
import MLF.Kind
import qualified MLF.Primitive as P
import MLF.X.Syntax
import MLF.X.Type

type TypeEnv = Map.Map TyVar Type
data Env = Env { typeEnv :: TypeEnv, termEnv :: Map.Map Name Type } deriving Show

emptyEnv :: Env
emptyEnv = Env Map.empty Map.empty

wellFormed :: TypeEnv -> Type -> Either String ()
wellFormed = wellFormedIn D.emptyDataEnv

wellFormedIn :: D.DataEnv -> TypeEnv -> Type -> Either String ()
wellFormedIn ds env ty = kindOf ds env ty >> pure ()

termType :: D.DataEnv -> TypeEnv -> Type -> Either String ()
termType ds env ty = do
  k <- kindOf ds env ty
  unless (k == Star) $ case ty of
    Con c args -> D.checkArity ds c (length args) >> Left "term type must have kind *"
    _ -> Left "term type must have kind *"

fresh :: TypeEnv -> TyVar -> Either String ()
fresh env a = when (Map.member a env) (Left ("type binder already in scope: " ++ show a))

-- | Figure 14.2.6, including the Inst-Hyp premise deliberately omitted by
-- the thesis's unchecked type-computation function (Figure 14.2.7).
checkComputation :: TypeEnv -> Computation -> Type -> Either String Type
checkComputation = checkComputationIn D.emptyDataEnv

checkComputationIn :: D.DataEnv -> TypeEnv -> Computation -> Type -> Either String Type
checkComputationIn ds env computation source = do
  validateTypeEnv ds env
  checkComputationScoped ds env computation source

-- The public boundary validates arbitrary caller-supplied environments.
-- Recursive computations and inferIn extend a validated environment only
-- with fresh, well-formed bounds, so rewalking its dependency graph at every
-- evidence node is redundant. Source/result kind checks remain in place.
checkComputationScoped :: D.DataEnv -> TypeEnv -> Computation -> Type -> Either String Type
checkComputationScoped ds env computation source = do
  wellFormedIn ds env source
  result <- go computation source
  wellFormedIn ds env result
  pure result
  where
    go p s = case (p,s) of
      (Refl, _) -> pure s
      (Bottom t, Bot) -> termType ds env t >> pure t
      (Bottom t, BotKind k) -> do
        actual <- kindOf ds env t
        unless (actual == k) (Left "Inst-Bot kind mismatch")
        pure t
      (Hyp a, _) -> case Map.lookup a env of
        Just bound | alphaEq bound s -> pure (Var a)
        Just _ -> Left ("Inst-Hyp bound mismatch for " ++ show a)
        Nothing -> Left ("Inst-Hyp unbound variable " ++ show a)
      (Then p1 p2, _) -> checkComputationScoped ds env p1 s >>= checkComputationScoped ds env p2
      (Inner q, Forall a bound body) -> do
        bound' <- checkComputationScoped ds env q bound
        pure (Forall a bound' body)
      (Outer a q, Forall b bound body) -> do
        fresh env a
        when (a /= b && a `Set.member` freeVars body) (Left "Inst-Outer would capture a variable")
        let body' = substitute b (Var a) body
        result <- checkComputationScoped ds (Map.insert a bound env) q body'
        pure (Forall a bound result)
      (Elim, Forall a bound body) -> pure (substitute a bound body)
      (Intro a, _) -> do
        fresh env a
        when (a `Set.member` freeVars s) (Left "Inst-Quant-Intro would capture a variable")
        pure (Forall a Bot s)
      (IntroKind a k, _) -> do
        fresh env a
        when (a `Set.member` freeVars s) (Left "Inst-Quant-Intro would capture a variable")
        pure (Forall a (bottomKind k) s)
      _ -> Left ("computation " ++ show p ++ " does not apply to " ++ show s)

-- | This checker neither imports nor calls the inference graph or solver.
infer :: Env -> Term -> Either String Type
infer env term = case term of
  WithData declarations body -> do
    ds <- D.validateDeclarations declarations
    inferWithData ds env body
  _ -> inferWithData D.emptyDataEnv env term

inferWithData :: D.DataEnv -> Env -> Term -> Either String Type
inferWithData ds env body = do
  validateTypeEnv ds (typeEnv env)
  mapM_ (termType ds (typeEnv env)) (Map.elems (termEnv env))
  inferIn ds env body

inferIn :: D.DataEnv -> Env -> Term -> Either String Type
inferIn ds env term = case term of
  VarTerm x -> maybe (Left ("unbound term variable " ++ nameHint x)) pure (Map.lookup x (termEnv env))
  Abs x t body -> do
    termType ds (typeEnv env) t
    when (Map.member x (termEnv env)) (Left "term binder already in scope")
    Arrow t <$> inferIn ds env { termEnv = Map.insert x t (termEnv env) } body
  App f a -> do
    ft <- inferIn ds env f
    at <- inferIn ds env a
    case ft of
      Arrow domain result | alphaEq domain at -> pure result
                          | otherwise -> Left ("application type mismatch: expected " ++ show domain ++ ", got " ++ show at)
      _ -> Left ("application of a non-function: " ++ show ft)
  TypeAbs a bound body -> do
    fresh (typeEnv env) a
    wellFormedIn ds (typeEnv env) bound
    Forall a bound <$> inferIn ds env { typeEnv = Map.insert a bound (typeEnv env) } body
  TypeApp t p -> inferIn ds env t >>= checkComputationScoped ds (typeEnv env) p
  Let x a b -> do
    when (Map.member x (termEnv env)) (Left "term binder already in scope")
    t <- inferIn ds env a
    inferIn ds env { termEnv = Map.insert x t (termEnv env) } b
  LetRec bindings body -> do
    let names = [n | (n,_,_) <- bindings]
    unless (length names == length (nub names)) (Left "duplicate recursive binder")
    when (any (`Map.member` termEnv env) names) (Left "recursive binder already in scope")
    mapM_ (termType ds (typeEnv env)) [t | (_,t,_) <- bindings]
    let scope = env { termEnv = Map.union (Map.fromList [(n,t) | (n,t,_) <- bindings]) (termEnv env) }
    forM_ bindings $ \(_,expected,rhs) -> do
      actual <- inferIn ds scope rhs
      unless (alphaEq expected actual) (Left "recursive definition does not have its declared type")
    inferIn ds scope body
  IntTerm _ -> pure (Con "Int" [])
  DoubleTerm n -> do
    unless (not (isNaN n || isInfinite n)) (Left "non-finite Double literal")
    pure (Con "Double" [])
  BoolTerm _ -> pure (Con "Bool" [])
  StringTerm text -> do
    unless (all (\c -> ord c < 0xd800 || ord c > 0xdfff) text)
      (Left "invalid Unicode scalar in string literal")
    pure (Con "String" [])
  Primitive p arguments -> do
    let (parameters,signature) = P.primitiveSignature p
    unless (length arguments == length parameters) (Left "primitive type argument arity mismatch")
    actualKinds <- mapM (kindOf ds (typeEnv env)) arguments
    unless (actualKinds == map snd parameters) (Left "primitive type argument kind mismatch")
    instantiateField (Map.fromList (zip (map fst parameters) arguments)) signature
  Constructor c arguments -> do
    (d,ctor) <- D.lookupConstructor ds c
    unless (length arguments == length (D.datatypeParameters d))
      (Left ("constructor type argument arity mismatch: " ++ c))
    actualKinds <- mapM (kindOf ds (typeEnv env)) arguments
    unless (actualKinds == map snd (D.datatypeBinders d)) (Left "constructor type argument kind mismatch")
    let parameters = Map.fromList (zip (D.datatypeParameters d) arguments)
    fields <- mapM (instantiateField parameters) (D.constructorFields ctor)
    pure (foldr Arrow (Con (D.datatypeName d) arguments) fields)
  Case scrutinee result alternatives -> do
    st <- inferIn ds env scrutinee
    termType ds (typeEnv env) result
    owner <- D.checkAlternatives ds (map shape alternatives)
    parameters <- case owner of
      Nothing -> pure Map.empty
      Just d -> case st of
        Con c args | c == D.datatypeName d -> do
          D.checkArity ds c (length args)
          pure (Map.fromList (zip (D.datatypeParameters d) args))
        _ -> Left "case scrutinee has the wrong data type"
    forM_ alternatives $ \(Alternative p body) -> do
      let names = patternNames p
      unless (length names == length (nub names)) (Left "duplicate pattern variable")
      when (any (`Map.member` termEnv env) names) (Left "pattern binder already in scope")
      bindings <- case p of
        DefaultPattern n -> pure [(x,st) | Just x <- [n]]
        ConstructorPattern c ns -> do
          (_,ctor) <- D.lookupConstructor ds c
          fields <- mapM (instantiateField parameters) (D.constructorFields ctor)
          pure [(n,t) | (Just n,t) <- zip ns fields]
      bt <- inferIn ds env { termEnv = Map.union (Map.fromList bindings) (termEnv env) } body
      unless (alphaEq bt result) (Left "case alternative result type mismatch")
    pure result
  WithData _ _ -> Left "data declarations must be at the outermost level"
  where
    shape (Alternative (ConstructorPattern c ns) _) = (Just c,length ns)
    shape (Alternative (DefaultPattern _) _) = (Nothing,0)

checkClosed :: Term -> Either String Type
checkClosed = infer emptyEnv

validateTypeEnv :: D.DataEnv -> TypeEnv -> Either String ()
validateTypeEnv ds env = mapM_ (visit Set.empty) (Map.keys env)
  where
    visit path a
      | a `Set.member` path = Left "cyclic type environment"
      | otherwise = case Map.lookup a env of
          Nothing -> Left ("unbound variable in type environment: " ++ show a)
          Just bound -> do
            wellFormedIn ds (Map.delete a env) bound
            mapM_ (visit (Set.insert a path)) (Set.toList (freeVars bound))
