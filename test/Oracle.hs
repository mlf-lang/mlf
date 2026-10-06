-- An independent Algorithm W oracle for the unannotated language. This module
-- imports neither the graph solver nor the xMLF type/computation definitions.
module Oracle (hmTypable, closedTerms, generatedTerms) where

import Control.Monad.State.Strict
import qualified Data.IntMap.Strict as IM
import qualified Data.IntSet as IS
import qualified Data.Map.Strict as Map
import MLF.Syntax

data Mono = Meta Int | Fun Mono Mono | IntegerType | BooleanType deriving (Eq, Show)
data Scheme = Scheme [Int] Mono
type Subst = IM.IntMap Mono
type W = StateT (Int,Subst) (Either String)

apply :: Subst -> Mono -> Mono
apply s ty = case ty of
  Meta n -> maybe ty (apply s) (IM.lookup n s)
  Fun a b -> Fun (apply s a) (apply s b)
  _ -> ty

free :: Mono -> IS.IntSet
free (Meta n) = IS.singleton n
free (Fun a b) = free a `IS.union` free b
free _ = IS.empty

fresh :: W Mono
fresh = do (n,s) <- get; put (n+1,s); pure (Meta n)

unify :: Mono -> Mono -> W ()
unify t u = do
  (_,s) <- get
  case (apply s t, apply s u) of
    (a,b) | a == b -> pure ()
    (Meta n,b) | IS.notMember n (free b) -> modify' (\(i,ss) -> (i,IM.insert n b ss))
    (a,Meta n) | IS.notMember n (free a) -> modify' (\(i,ss) -> (i,IM.insert n a ss))
    (Fun a b,Fun c d) -> unify a c >> unify b d
    _ -> lift (Left "HM mismatch")

infer :: Map.Map String Scheme -> Expr -> W Mono
infer env e = case e of
  Var x -> case Map.lookup x env of
    Nothing -> lift (Left "unbound")
    Just (Scheme ns t) -> do
      replacements <- mapM (const fresh) ns
      (_,s) <- get
      pure (apply (IM.fromList (zip ns replacements)) (apply s t))
  Lam x Nothing b -> do
    a <- fresh
    r <- infer (Map.insert x (Scheme [] a) env) b
    (_,s) <- get
    pure (Fun (apply s a) (apply s r))
  App a b -> do
    f <- infer env a
    x <- infer env b
    r <- fresh
    unify f (Fun x r)
    (_,s) <- get
    pure (apply s r)
  Let x a b -> do
    t <- infer env a
    (_,s) <- get
    let t' = apply s t
        envFree = IS.unions [free (apply s u) `IS.difference` IS.fromList ns | Scheme ns u <- Map.elems env]
        quantified = IS.toList (free t' `IS.difference` envFree)
    infer (Map.insert x (Scheme quantified t') env) b
  IntLit _ -> pure IntegerType
  BoolLit _ -> pure BooleanType
  _ -> lift (Left "oracle accepts only unannotated terms")

hmTypable :: Expr -> Bool
hmTypable e = case evalStateT (infer Map.empty e) (0,IM.empty) of Right _ -> True; Left _ -> False

-- Exhaustive, by exact AST size, with variables resolved by lexical scope.
closedTerms :: Int -> [Expr]
closedTerms limit = concat [terms n [] | n <- [1..limit]]
  where
    terms 1 env = IntLit 0 : BoolLit True : map Var env
    terms n env =
      [Lam x Nothing b | b <- terms (n-1) (x:env)] ++
      [App a b | k <- [1..n-2], a <- terms k env, b <- terms (n-1-k) env] ++
      [Let x a b | k <- [1..n-2], a <- terms k env, b <- terms (n-1-k) (x:env)]
      where x = "x" ++ show (length env)

-- Larger deterministic terms, independent of the compiler's construction.
generatedTerms :: Int -> [Expr]
generatedTerms count = [evalState (gen (7 + seed `mod` 19) []) seed | seed <- [1..count]]
  where
    pick :: Int -> State Int Int
    pick k = do
      seed <- get
      let seed' = (seed * 48271) `mod` 2147483647
      put seed'
      pure (seed' `mod` k)
    gen :: Int -> [String] -> State Int Expr
    gen n env
      | n <= 1 = do
          i <- pick (2 + length env)
          pure $ case i of
            0 -> IntLit 0
            1 -> BoolLit True
            _ -> Var (env !! (i-2))
      | otherwise = do
          shape <- if n == 2 then pure 0 else pick 3
          let x = "x" ++ show (length env)
          case shape of
            0 -> Lam x Nothing <$> gen (n-1) (x:env)
            1 -> do
              k <- (+1) <$> pick (n-2)
              App <$> gen k env <*> gen (n-1-k) env
            _ -> do
              k <- (+1) <$> pick (n-2)
              Let x <$> gen k env <*> gen (n-1-k) (x:env)
