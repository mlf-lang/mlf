-- | Sharing-preserving simplification of the independently checked erasure.
-- Names are resolved identities; spelling is never used to recognize code.
module MLF.LLVM.Optimize (optimize, free, applications, lambdas) where

import Control.Monad.State.Strict
import Control.Monad (foldM)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified MLF.X.Syntax as X

type Fresh = State Int

fresh :: Fresh X.Name
fresh = do
  i <- get
  put (i + 1)
  pure (X.Name i "native")

free :: X.Erased -> Set.Set X.Name
free expression = case expression of
  X.EVar n -> Set.singleton n
  X.EAbs n b -> Set.delete n (free b)
  X.EApp f a -> free f `Set.union` free a
  X.ELet n a b -> free a `Set.union` Set.delete n (free b)
  X.ELetRec ds b -> Set.unions (free b : map (free . snd) ds) `Set.difference` Set.fromList (map fst ds)
  X.ECase s bs -> free s `Set.union` Set.unions
    [free b `Set.difference` Set.fromList (X.patternNames p) | X.ErasedAlternative p b <- bs]
  _ -> Set.empty

applications :: X.Erased -> (X.Erased,[X.Erased])
applications = go []
  where
    go args (X.EApp f a) = go (a:args) f
    go args f = (f,args)

lambdas :: X.Erased -> ([X.Name],X.Erased)
lambdas (X.EAbs n b) = let (ns,body) = lambdas b in (n:ns,body)
lambdas e = ([],e)

size :: X.Erased -> Int
size e = 1 + case e of
  X.EAbs _ b -> size b
  X.EApp f a -> size f + size a
  X.ELet _ a b -> size a + size b
  X.ELetRec ds b -> sum (map (size . snd) ds) + size b
  X.ECase s bs -> size s + sum [size b | X.ErasedAlternative _ b <- bs]
  _ -> 0

occurrences :: X.Name -> X.Erased -> Int
occurrences n e = case e of
  X.EVar v -> if n == v then 1 else 0
  X.EAbs _ b -> occurrences n b
  X.EApp f a -> occurrences n f + occurrences n a
  X.ELet _ a b -> occurrences n a + occurrences n b
  X.ELetRec ds b -> sum (map (occurrences n . snd) ds) + occurrences n b
  X.ECase s bs -> occurrences n s + sum [occurrences n b | X.ErasedAlternative _ b <- bs]
  _ -> 0

-- Capture-avoiding substitution also freshens copied binders. This keeps the
-- global identity uniqueness required by later direct-call analysis.
copy :: Map.Map X.Name X.Erased -> X.Erased -> Fresh X.Erased
copy env e = case e of
  X.EVar n -> pure (Map.findWithDefault e n env)
  X.EAbs n b -> do
    n' <- fresh
    X.EAbs n' <$> copy (Map.insert n (X.EVar n') env) b
  X.EApp f a -> X.EApp <$> copy env f <*> copy env a
  X.ELet n a b -> do
    n' <- fresh
    X.ELet n' <$> copy env a <*> copy (Map.insert n (X.EVar n') env) b
  X.ELetRec ds b -> do
    ns <- mapM (const fresh) ds
    let local = Map.union (Map.fromList (zip (map fst ds) (map X.EVar ns))) env
    ds' <- mapM (\(n,(_,a)) -> (,) n <$> copy local a) (zip ns ds)
    X.ELetRec ds' <$> copy local b
  X.ECase s bs -> X.ECase <$> copy env s <*> mapM alternative bs
    where
      alternative (X.ErasedAlternative p b) = do
        ns <- mapM (const fresh) (X.patternNames p)
        let renaming = Map.fromList (zip (X.patternNames p) ns)
            name n = Map.findWithDefault n n renaming
            p' = case p of
              X.DefaultPattern n -> X.DefaultPattern (fmap name n)
              X.ConstructorPattern c xs -> X.ConstructorPattern c (map (fmap name) xs)
        X.ErasedAlternative p' <$> copy (Map.union (Map.map X.EVar renaming) env) b
  _ -> pure e

children :: (X.Erased -> Fresh X.Erased) -> X.Erased -> Fresh X.Erased
children f e = case e of
  X.EAbs n b -> X.EAbs n <$> f b
  X.EApp a b -> X.EApp <$> f a <*> f b
  X.ELet n a b -> X.ELet n <$> f a <*> f b
  X.ELetRec ds b -> X.ELetRec <$> mapM (\(n,a) -> (,) n <$> f a) ds <*> f b
  X.ECase s bs -> X.ECase <$> f s <*> mapM (\(X.ErasedAlternative p b) -> X.ErasedAlternative p <$> f b) bs
  _ -> pure e

-- Coercions erase to identity functions. Remove them before recognizing the
-- ordinary recursive-datatype encoding of a fixed point (including renames).
identities :: X.Erased -> Fresh X.Erased
identities e = children identities e >>= \e' -> case e' of
  X.EApp (X.EAbs n (X.EVar n')) a | n == n' -> pure a
  X.ELet n (X.EVar a) b -> copy (Map.singleton n (X.EVar a)) b
  _ -> pure e'

fixedPoints :: X.Erased -> Fresh X.Erased
fixedPoints e = case e of
  X.EAbs f (X.ELet g (X.EAbs r (X.ECase (X.EVar r')
    [X.ErasedAlternative (X.ConstructorPattern c [Just next])
      (X.EApp (X.EVar f') (X.EApp (X.EVar next') (X.EVar r'')))]))
    (X.EApp (X.EVar g') (X.EApp (X.EConstructor c') (X.EVar g''))))
      | f == f' && r == r' && r == r'' && next == next' &&
        g == g' && g == g'' && c == c' -> do
          loop <- fresh
          pure (X.EAbs f (X.ELetRec [(loop,X.EApp (X.EVar f) (X.EVar loop))] (X.EVar loop)))
  _ -> children fixedPoints e

atom :: X.Erased -> Bool
atom e = case e of
  X.EVar _ -> True
  X.EPrimitive _ -> True
  X.EConstructor _ -> True
  X.EInt _ -> True
  X.EDouble _ -> True
  X.EBool _ -> True
  _ -> False

smallValue :: X.Erased -> Bool
smallValue e = atom e || case e of
  X.EAbs _ _ -> size e <= 24
  _ -> case applications e of
    (X.EConstructor _,args) -> all atom args
    _ -> False

-- A bounded bottom-up rewrite, not an evaluator. Newly created beta redexes
-- are visited on the next pass, so self application cannot loop the compiler.
pass :: X.Erased -> Fresh X.Erased
pass e = children pass e >>= \e' -> case e' of
  X.EApp (X.EAbs n b) a -> pure (X.ELet n a b)
  X.EApp (X.ELet n a f) b -> pure (X.ELet n a (X.EApp f b))
  X.EApp (X.ELetRec ds f) a -> pure (X.ELetRec ds (X.EApp f a))
  X.ELet n a b
    | not (Set.member n (free b)) -> pure b
    | smallValue a -> substitute n a b
    | X.EAbs _ _ <- a, occurrences n b == 1 -> substitute n a b
  X.ELet n (X.ELet x a b) body -> pure (X.ELet x a (X.ELet n b body))
  X.ELet n (X.ELetRec [(r,rhs)] (X.EVar r')) b | r == r' -> do
    rhs' <- copy (Map.singleton r (X.EVar n)) rhs
    pure (X.ELetRec [(n,rhs')] b)
  X.ELetRec ds b -> do
    let group = Set.fromList (map fst ds)
        expandable = [(n,a) | (n,a) <- ds, smallValue a, Set.null (free a `Set.intersection` group)]
        keep = [(n,a) | (n,a) <- ds, n `notElem` map fst expandable]
    if null expandable then pure e' else
      foldM (\body (n,a) -> substitute n a body) (if null keep then b else X.ELetRec keep b) expandable
  X.ECase s [X.ErasedAlternative (X.DefaultPattern n) b] ->
    pure (maybe b (\name -> X.ELet name s b) n)
  X.ECase s bs -> case applications s of
    (X.EConstructor c,args) -> case select c args bs of
      Just b -> pure b
      Nothing -> pure e'
    _ -> pure e'
  _ -> pure e'
  where
    -- Every occurrence gets distinct copied binders. Compound computations
    -- remain shared lets; only values are duplicated.
    substitute n a = go
      where
        go (X.EVar v) | v == n = copy Map.empty a
        go term = children go term
    select _ _ [] = Nothing
    select c args (X.ErasedAlternative p b:rest) = case p of
      X.ConstructorPattern c' ns | c == c' && length ns == length args ->
        Just (foldr (\(n,a) body -> maybe body (\v -> X.ELet v a body) n) b (zip ns args))
      X.DefaultPattern n -> Just (maybe b (\v -> X.ELet v (foldl X.EApp (X.EConstructor c) args) b) n)
      _ -> select c args rest

optimize :: X.Erased -> X.Erased
optimize expression = evalState work (1 + maximum (0 : ids expression))
  where
    work = do
      -- The checker permits identities to be reused in disjoint scopes.
      -- Make them globally unique before any substitution or let floating.
      unique <- copy Map.empty expression
      clean <- identities unique
      recursive <- fixedPoints clean
      normalized <- iterations (16 :: Int) recursive
      -- A closed erasure can be alpha-normalized from zero. Saved xMLF and
      -- source compilation then produce the same LLVM despite parser IDs.
      pure (evalState (copy Map.empty normalized) 0)
    iterations 0 e = pure e
    iterations n e = do
      next <- pass e
      if next == e then pure e else iterations (n - 1) next
    ids e = case e of
      X.EVar n -> [X.nameId n]
      X.EAbs n b -> X.nameId n : ids b
      X.EApp f a -> ids f ++ ids a
      X.ELet n a b -> X.nameId n : ids a ++ ids b
      X.ELetRec ds b -> concat [X.nameId n : ids a | (n,a) <- ds] ++ ids b
      X.ECase s bs -> ids s ++ concat [map X.nameId (X.patternNames p) ++ ids b | X.ErasedAlternative p b <- bs]
      _ -> []
