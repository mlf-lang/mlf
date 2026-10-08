-- | Surface patterns and declaration groups lower to the existing small core.
-- Matching is ordered, left-to-right, and leaves wildcard fields lazy.
module MLF.Surface
  ( lowerSurface, lowerExpression, bindValues, recursiveValues
  , patternVariables, freeNames, function
  ) where

import Control.Monad (foldM, forM, forM_, replicateM, unless)
import Control.Monad.State.Strict
import Data.Char (isAlphaNum)
import Data.Graph (SCC (..), stronglyConnComp)
import Data.List (nub, sortOn)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import MLF.Desugar (desugarDo)
import qualified MLF.Primitive as P
import MLF.Syntax

type Value = (String, Maybe Annotation, Expr)

patternVariables :: Pattern -> [String]
patternVariables p = case p of
  DefaultPattern n -> maybe [] (:[]) n
  ConstructorPattern _ ns -> [n | Just n <- ns]
  NestedPattern _ ps -> concatMap patternVariables ps
  AnnotatedPattern n _ -> [n]
  _ -> []

freeNames :: Expr -> Set.Set String
freeNames e = case e of
  Var n -> Set.singleton n
  Lam n _ b -> Set.delete n (freeNames b)
  App a b -> freeNames a <> freeNames b
  Let n a b -> freeNames a <> Set.delete n (freeNames b)
  Ann a _ -> freeNames a
  Case a bs -> freeNames a <> Set.unions
    [freeNames b Set.\\ Set.fromList (patternVariables p) | Alternative p b <- bs]
  Equations rows -> Set.unions
    [freeNames b Set.\\ Set.fromList (concatMap patternVariables ps) | (ps,b) <- rows]
  LetRec ds b -> Set.unions (freeNames b : [freeNames a | (_,_,a) <- ds])
    Set.\\ Set.fromList [n | (n,_,_) <- ds]
  Do _ _ -> freeNames (desugarDo e)
  Checked _ a -> freeNames a
  _ -> Set.empty

function :: [([Pattern],Expr)] -> Expr
function [(ps,b)] | all variable ps = foldr parameter b ps
  where
    variable (DefaultPattern (Just _)) = True
    variable (AnnotatedPattern _ _) = True
    variable _ = False
    parameter (DefaultPattern (Just n)) = Lam n Nothing
    parameter (AnnotatedPattern n a) = Lam n (Just a)
    parameter _ = id
function rows = Equations rows

-- Top-level values use stable dependency order. Acyclic definitions still
-- generalize exactly like let; only cyclic SCCs require signatures.
bindValues :: [Value] -> Expr -> Either String Expr
bindValues values body = do
  let names = [n | (n,_,_) <- values]
  unless (length names == length (nub names)) (Left "duplicate value declaration")
  let index = Map.fromList (zip names [0 :: Int ..])
      dependencies e = [i | n <- Set.toList (freeNames e), Just i <- [Map.lookup n index]]
      nodes = [(i,i,dependencies e) | (i,(_,_,e)) <- zip [0..] values]
      members (AcyclicSCC i) = [i]
      members (CyclicSCC is) = sortOn id is
      components = stronglyConnComp nodes
      groups = sortOn (minimum . members) components
      order done pending = case pending of
        [] -> Right []
        _ -> case [g | g <- pending, all (ready done (members g))
                      [d | i <- members g, d <- dependencies (third (values !! i))]] of
          g:_ -> (g :) <$> order (done <> Set.fromList (members g)) (filter ((/= members g) . members) pending)
          [] -> Left "invalid declaration dependencies"
      ready done local i = Set.member i done || elem i local
      third (_,_,e) = e
      wrap (AcyclicSCC i) rest =
        let (n,a,e) = values !! i in pure (Let n (maybe e (Ann e) a) rest)
      wrap g@(CyclicSCC _) rest = LetRec <$> recursiveValues [values !! i | i <- members g] <*> pure rest
  sorted <- order Set.empty groups
  foldM (flip wrap) body (reverse sorted)

recursiveValues :: [Value] -> Either String [(String,Annotation,Expr)]
recursiveValues values = forM values $ \(n,a,e) -> case a of
  Just annotation@(Annotation [] _) -> pure (n,annotation,e)
  _ -> Left ("recursive definition " ++ n ++ " requires an explicit closed signature")

lowerSurface :: Program -> Either String Program
lowerSurface p = case p of
  Program ds e -> Program ds <$> lowerExpression e
  ClassProgram ds cs is e -> ClassProgram ds cs
    <$> mapM (\i -> do
      ms <- mapM (\(n,a) -> (,) n <$> lowerExpression a) (instanceMethods i)
      pure i { instanceMethods = ms }) is
    <*> lowerExpression e

type Lower = StateT (Int,Set.Set String) (Either String)
type Row = ([Pattern],Expr,Int)

lowerExpression :: Expr -> Either String Expr
lowerExpression original | not (needsLowering original) = Right original
lowerExpression original = evalStateT (go (desugarDo original)) (0,used)
  where
    used = Set.fromList (words (map (\c -> if isAlphaNum c || elem c "_'" then c else ' ') (show original)))

needsLowering :: Expr -> Bool
needsLowering e = case e of
  Equations _ -> True
  Do _ _ -> True
  Lam _ _ b -> needsLowering b
  App a b -> needsLowering a || needsLowering b
  Let _ a b -> needsLowering a || needsLowering b
  Ann a _ -> needsLowering a
  Checked _ a -> needsLowering a
  LetRec ds b -> any (\(_,_,a) -> needsLowering a) ds || needsLowering b
  Case a bs -> needsLowering a || any branch bs
  _ -> False
  where
    branch (Alternative p b) = not (flat p) || needsLowering b
    flat (ConstructorPattern _ _) = True
    flat (DefaultPattern _) = True
    flat _ = False

fresh :: Lower String
fresh = do
  (i,used) <- get
  let n = "matchValue" ++ show i
  put (i+1,Set.insert n used)
  if Set.member n used then fresh else pure n

go :: Expr -> Lower Expr
go e = case e of
  Lam n a b -> Lam n a <$> go b
  App a b -> App <$> go a <*> go b
  Let n a b -> Let n <$> go a <*> go b
  Ann a t -> (\a' -> Ann a' t) <$> go a
  LetRec ds b -> LetRec <$> mapM (\(n,t,a) -> (,,) n t <$> go a) ds <*> go b
  Checked t a -> Checked t <$> go a
  Equations [] -> lift (Left "function has no equations")
  Equations equations@((firstPatterns,_):_) -> do
    let arity = length firstPatterns
    unless (all ((== arity) . length . fst) equations) (lift (Left "function equations have different arities"))
    ns <- replicateM arity fresh
    body <- matching (map Var ns) equations
    pure (foldr (\n b -> Lam n Nothing b) body ns)
  Case a bs -> do
    a' <- go a
    if all (\(Alternative p _) -> flat p) bs
      then Case a' <$> mapM (\(Alternative p b) -> Alternative p <$> go b) bs
      else do
        n <- fresh
        body <- matching [Var n] [([p],b) | Alternative p b <- bs]
        pure (Let n a' body)
  Do _ _ -> go (desugarDo e)
  _ -> pure e
  where
    flat (ConstructorPattern _ _) = True
    flat (DefaultPattern _) = True
    flat _ = False

matching :: [Expr] -> [([Pattern],Expr)] -> Lower Expr
matching values equations = do
  forM_ equations $ \(ps,_) -> do
    let names = concatMap patternVariables ps
    unless (length names == length (nub names)) (lift (Left "duplicate pattern variable"))
  rows <- forM (zip [0..] equations) $ \(i,(ps,b)) -> (,,) ps <$> go b <*> pure i
  (body,used) <- matrix values rows
  unless (Set.size used == length rows) (lift (Left "unreachable pattern or function equation"))
  pure body

wild :: Pattern
wild = DefaultPattern Nothing

isVariable :: Pattern -> Bool
isVariable (DefaultPattern _) = True
isVariable (AnnotatedPattern _ _) = True
isVariable _ = False

bindPattern :: Expr -> Pattern -> Expr -> Expr
bindPattern value (DefaultPattern (Just n)) = Let n value
bindPattern value (AnnotatedPattern n a) = Let n (Ann value a)
bindPattern _ _ = id

constructor :: Pattern -> Maybe (String,[Pattern])
constructor (ConstructorPattern c ns) = Just (c,map DefaultPattern ns)
constructor (NestedPattern c ps) = Just (c,ps)
constructor _ = Nothing

matrix :: [Expr] -> [Row] -> Lower (Expr,Set.Set Int)
matrix _ [] = lift (Left "non-exhaustive patterns")
matrix values rows@((firstPatterns,firstBody,firstIndex):_)
  | any (\(ps,_,_) -> length ps /= length values) rows =
      lift (Left "function equations have different arities")
  | all isVariable firstPatterns =
      pure (foldr (\(value,p) b -> bindPattern value p b) firstBody (zip values firstPatterns),Set.singleton firstIndex)
  | otherwise = do
      let patterns = [selected ps | (ps,_,_) <- rows, not (isVariable (selected ps))]
          defaults = [(remaining ps,bindPattern v (selected ps) b,i) | (ps,b,i) <- rows, isVariable (selected ps)]
      case patterns of
        p:_ | Just _ <- constructor p -> do
          unless (all (maybe False (const True) . constructor) patterns)
            (lift (Left "mixed constructor and literal patterns"))
          let cs = nub [c | p' <- patterns, Just (c,_) <- [constructor p']]
          branches <- forM cs $ \c -> do
            let arities = [length ps | p' <- patterns, Just (c',ps) <- [constructor p'], c == c']
            arity <- case arities of
              a:_ -> pure a
              [] -> lift (Left "invalid constructor specialization")
            unless (all (== arity) arities) (lift (Left ("constructor pattern arity mismatch: " ++ c)))
            ns <- replicateM arity fresh
            let specialize (ps,b,i) = case constructor (selected ps) of
                  Just (c',fields) | c == c' -> [(replace fields ps,b,i)]
                  _ | isVariable (selected ps) -> [(replace (replicate arity wild) ps,bindPattern v (selected ps) b,i)]
                  _ -> []
            (b,used) <- matrix (replace (map Var ns) values) (concatMap specialize rows)
            pure (Alternative (ConstructorPattern c (map Just ns)) b,used)
          fallback <- if null defaults then pure [] else do
            (b,used) <- matrix vs defaults
            pure [(Alternative (DefaultPattern Nothing) b,used)]
          pure (Case v (map fst (branches ++ fallback)),Set.unions (map snd (branches ++ fallback)))
        BoolPattern _:_ -> do
          unless (all isBool patterns) (lift (Left "mixed literal pattern types"))
          yes <- literalBranch (BoolPattern True)
          no <- literalBranch (BoolPattern False)
          pure (choose v (fst yes) (fst no),snd yes <> snd no)
        IntPattern _:_ -> literals isInt P.EqInt (\p -> case p of IntPattern n -> IntLit n; _ -> v) defaults patterns
        StringPattern _:_ -> literals isString P.EqString (\p -> case p of StringPattern s -> StringLit s; _ -> v) defaults patterns
        _ -> lift (Left "invalid pattern matrix")
  where
    -- Select the first refutable position of the first equation, preserving
    -- source order after specialization. Testing an arbitrary column would
    -- force a wildcard argument that an earlier equation never demanded.
    column = length (takeWhile isVariable firstPatterns)
    selected xs = xs !! column
    replace fields xs = take column xs ++ fields ++ drop (column + 1) xs
    remaining = replace []
    v = selected values
    vs = remaining values
    isBool (BoolPattern _) = True
    isBool _ = False
    isInt (IntPattern _) = True
    isInt _ = False
    isString (StringPattern _) = True
    isString _ = False
    literalBranch literal = matrix vs
      [(remaining ps,bindPattern v p b,i) | (ps,b,i) <- rows, let p = selected ps, p == literal || isVariable p]
    literals predicate primitive value defaults patterns = do
      unless (all predicate patterns) (lift (Left "mixed literal pattern types"))
      fallback <- matrix vs defaults
      foldM (\(rest,used) p -> do
        (b,used') <- literalBranch p
        pure (choose (App (App (Primitive primitive) v) (value p)) b rest,used <> used'))
        fallback (reverse (nub patterns))

choose :: Expr -> Expr -> Expr -> Expr
choose a b c = App (App (App (Primitive P.IfThenElse) a) b) c
