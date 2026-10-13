-- | Sharing-preserving simplification of the independently checked erasure.
-- Names are resolved identities; spelling is never used to recognize code.
module MLF.LLVM.Optimize (optimize, free, applications, lambdas) where

import Control.Monad.State.Strict
import Control.Monad (foldM)
import qualified Data.List as List
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

-- The inlining threshold only needs a bounded prefix of the tree. Returning
-- the remaining budget lets siblings share that bound without computing the
-- complete size of a large function that cannot be inlined.
remainingSize :: Int -> X.Erased -> Int
remainingSize budget _ | budget <= 0 = -1
remainingSize budget e = case e of
  X.EAbs _ b -> remainingSize rest b
  X.EApp f a -> remainingSize (remainingSize rest f) a
  X.ELet _ a b -> remainingSize (remainingSize rest a) b
  X.ELetRec ds b -> spend (remainingSize rest b) (map snd ds)
  X.ECase s bs -> spend (remainingSize rest s) [b | X.ErasedAlternative _ b <- bs]
  _ -> rest
  where
    rest = budget - 1
    spend n _ | n < 0 = -1
    spend n [] = n
    spend n (a:as) = spend (remainingSize n a) as

-- Dead bindings and single-use lambdas only distinguish zero, one, and
-- multiple free occurrences. Stop at the supplied limit rather than building
-- a free-variable set or counting every occurrence in the remaining program.
occurrences :: Int -> X.Name -> X.Erased -> Int
occurrences limit _ _ | limit <= 0 = 0
occurrences limit n e = case e of
  X.EVar v -> if n == v then 1 else 0
  X.EAbs v b -> if n == v then 0 else occurrences limit n b
  X.EApp f a -> count limit [f,a]
  X.ELet v a b -> count limit (a : [b | n /= v])
  X.ELetRec ds b -> if n `elem` map fst ds then 0 else count limit (b : map snd ds)
  X.ECase s bs -> count limit (s : [b | X.ErasedAlternative p b <- bs, n `notElem` X.patternNames p])
  _ -> 0
  where
    count left _ | left <= 0 = 0
    count _ [] = 0
    count left (a:as) = let used = occurrences left n a in used + count (left - used) as

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
  X.EAbs _ _ -> remainingSize 24 e >= 0
  _ -> case applications e of
    (X.EConstructor _,args) -> all atom args
    _ -> False

-- Constructor patterns have already passed the independent target checker.
-- They provide arities without assuming any constructor spelling or tag. An
-- absent or inconsistent arity disables this optimization for that name.
type Arities = Map.Map String (Maybe Int)
type ConstructorFacts = Map.Map X.Name (String,[X.Erased])

subterms :: X.Erased -> [X.Erased]
subterms e = case e of
  X.EAbs _ b -> [b]
  X.EApp f a -> [f,a]
  X.ELet _ a b -> [a,b]
  X.ELetRec ds b -> map snd ds ++ [b]
  X.ECase s bs -> s : [b | X.ErasedAlternative _ b <- bs]
  _ -> []

constructorArities :: X.Erased -> Arities
constructorArities = collect Map.empty
  where
    collect known e = List.foldl' collect (case e of
      X.ECase _ bs -> List.foldl' alternative known bs
      _ -> known) (subterms e)
    alternative known (X.ErasedAlternative p _) = case p of
      X.ConstructorPattern c ns -> Map.insertWith agree c (Just (length ns)) known
      _ -> known
    agree a b = if a == b then a else Nothing

constructorValue :: Arities -> X.Erased -> Maybe (String,[X.Erased])
constructorValue arities e = case applications e of
  (X.EConstructor c,args) | Map.lookup c arities == Just (Just (length args)) -> Just (c,args)
  _ -> Nothing

-- Extract fields once, before propagation: replacing two projections by two
-- copies of a field computation would destroy call-by-need sharing. Ordinary
-- fields stay in their lexical scope; recursive fields stay in their group,
-- including fields that refer back to the original constructor or a method.
liftConstructorFields :: Arities -> X.Erased -> Fresh X.Erased
liftConstructorFields arities e = children (liftConstructorFields arities) e >>= \e' -> case e' of
  X.ELet n rhs body -> do
    (fields,value) <- liftValue rhs
    pure (foldr (uncurry X.ELet) (X.ELet n value body) fields)
  X.ELetRec ds body -> do
    lifted <- mapM (\(n,rhs) -> do
      (fields,value) <- liftValue rhs
      pure ((n,value),fields)) ds
    pure (X.ELetRec (map fst lifted ++ concatMap snd lifted) body)
  _ -> pure e'
  where
    liftValue rhs = case constructorValue arities rhs of
      Just (c,args) -> do
        fields <- mapM liftField args
        pure (concatMap fst fields,foldl X.EApp (X.EConstructor c) (map snd fields))
      Nothing -> pure ([],rhs)
    liftField field | atom field = pure ([],field)
    liftField field = do
      n <- fresh
      pure ([(n,field)],X.EVar n)

constructorFacts :: Arities -> X.Erased -> ConstructorFacts
constructorFacts arities = collect Map.empty
  where
    collect known e = List.foldl' collect (case e of
      X.ELet n rhs _ -> binding known (n,rhs)
      X.ELetRec ds _ -> List.foldl' binding known ds
      _ -> known) (subterms e)
    binding known (n,rhs) = case constructorValue arities rhs of
      Just value@(_,fields) | all smallValue fields -> Map.insert n value known
      _ -> known

selectConstructor :: String -> [X.Erased] -> [X.ErasedAlternative] -> Maybe X.Erased
selectConstructor _ _ [] = Nothing
selectConstructor c args (X.ErasedAlternative p b:rest) = case p of
  X.ConstructorPattern c' ns | c == c' && length ns == length args ->
    Just (foldr (\(n,a) body -> maybe body (\v -> X.ELet v a body) n) b (zip ns args))
  X.DefaultPattern n -> Just (maybe b (\v -> X.ELet v (foldl X.EApp (X.EConstructor c) args) b) n)
  _ -> selectConstructor c args rest

projectConstructors :: ConstructorFacts -> X.Erased -> Fresh X.Erased
projectConstructors facts e = children (projectConstructors facts) e >>= \e' -> case e' of
  X.ECase (X.EVar n) bs | Just (c,args) <- Map.lookup n facts,
    Just selected <- selectConstructor c args bs ->
      -- Small lifted values can have been inlined back into fields. Freshen
      -- their binders when copying them into each independent projection.
      copy Map.empty selected
  _ -> pure e'

-- A bounded bottom-up rewrite, not an evaluator. Newly created beta redexes
-- are visited on the next pass, so self application cannot loop the compiler.
pass :: X.Erased -> Fresh X.Erased
pass e = children pass e >>= \e' -> case e' of
  X.EApp (X.EAbs n b) a -> pure (X.ELet n a b)
  X.EApp (X.ELet n a f) b -> pure (X.ELet n a (X.EApp f b))
  X.EApp (X.ELetRec ds f) a -> pure (X.ELetRec ds (X.EApp f a))
  X.ELet n a b ->
    let uses = occurrences 2 n b
        singleLambda = case a of X.EAbs _ _ -> uses == 1; _ -> False
    in if uses == 0 then pure b else
      if smallValue a || singleLambda then substitute n a b else case a of
        X.ELet x value body -> pure (X.ELet x value (X.ELet n body b))
        X.ELetRec [(r,rhs)] (X.EVar r') | r == r' -> do
          rhs' <- copy (Map.singleton r (X.EVar n)) rhs
          pure (X.ELetRec [(n,rhs')] b)
        _ -> pure e'
  X.ELetRec ds b -> do
    let group = Set.fromList (map fst ds)
        expandable = [(n,a) | (n,a) <- ds, smallValue a, Set.null (free a `Set.intersection` group)]
        keep = [(n,a) | (n,a) <- ds, n `notElem` map fst expandable]
    if null expandable then pure e' else
      foldM (\body (n,a) -> substitute n a body) (if null keep then b else X.ELetRec keep b) expandable
  X.ECase s [X.ErasedAlternative (X.DefaultPattern n) b] ->
    pure (maybe b (\name -> X.ELet name s b) n)
  X.ECase s bs -> case applications s of
    (X.EConstructor c,args) -> case selectConstructor c args bs of
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


-- Specialize one original call site at a time, with a bounded fresh-name
-- budget. Only syntactic function values can be duplicated; captured
-- computations remain shared variables. Clones are not revisited here.
specializeHigherOrder :: X.Erased -> Fresh X.Erased
specializeHigherOrder expression = do
  seed <- get
  visit (seed + 16384) expression
  where
    definitions = collect expression
    collect e = Map.unions (case e of
      X.ELet n a _ -> Map.singleton n a : map collect (subterms e)
      X.ELetRec ds _ -> Map.fromList ds : map collect (subterms e)
      _ -> map collect (subterms e))
    static e = case e of
      X.EAbs _ _ -> remainingSize 64 e >= 0
      _ -> case applications e of
        (X.EVar n,args) | Just rhs <- Map.lookup n definitions ->
          length args < length (fst (lambdas rhs)) && all atom args
        (X.EPrimitive _,args) -> null args
        (X.EConstructor _,args) -> all atom args
        _ -> False
    applied n e = case applications e of
      (X.EVar f,_:_) | f == n -> True
      _ -> any (applied n) (subterms e)
    visit limit e = do
      e' <- children (visit limit) e
      used <- get
      case applications e' of
        (X.EVar name,callback:args) | used < limit,
          Just rhs <- Map.lookup name definitions,
          let (params,body) = lambdas rhs,
          first:rest <- params, not (null rest),
          length args == length rest,
          remainingSize 128 rhs >= 0, static callback,
          Set.member name (free body), applied first body -> do
            specialized <- fresh
            -- Freshen the original parameter scopes before inserting the
            -- callback, whose free names belong to the caller's scope.
            copied <- copy Map.empty rhs
            case lambdas copied of
              (key:newParams,newBody) -> do
                let change term = case applications term of
                      (X.EVar self,X.EVar argument:remaining)
                        | self == name && argument == key && length remaining == length rest ->
                            foldl X.EApp (X.EVar specialized) <$> mapM change remaining
                      _ -> case term of
                        X.EVar n | n == key -> copy Map.empty callback
                        _ -> children change term
                replaced <- change newBody
                pure (X.ELetRec [(specialized,foldr X.EAbs replaced newParams)]
                  (foldl X.EApp (X.EVar specialized) args))
              _ -> pure e'
        _ -> pure e'

optimize :: X.Erased -> X.Erased
optimize expression = evalState work (1 + maximum (0 : ids expression))
  where
    work = do
      -- The checker permits identities to be reused in disjoint scopes.
      -- Make them globally unique before any substitution or let floating.
      unique <- copy Map.empty expression
      clean <- identities unique
      recursive <- fixedPoints clean
      let arities = constructorArities recursive
      lifted <- liftConstructorFields arities recursive
      simple <- iterations arities (16 :: Int) lifted
      specialized <- specializeHigherOrder simple
      normalized <- iterations arities (16 :: Int) specialized
      -- A closed erasure can be alpha-normalized from zero. Saved xMLF and
      -- source compilation then produce the same LLVM despite parser IDs.
      pure (evalState (copy Map.empty normalized) 0)
    iterations _ 0 e = pure e
    iterations arities n e = do
      let facts = constructorFacts arities e
      projected <- if Map.null facts then pure e else projectConstructors facts e
      next <- pass projected
      if next == e then pure e else iterations arities (n - 1) next
    ids e = case e of
      X.EVar n -> [X.nameId n]
      X.EAbs n b -> X.nameId n : ids b
      X.EApp f a -> ids f ++ ids a
      X.ELet n a b -> X.nameId n : ids a ++ ids b
      X.ELetRec ds b -> concat [X.nameId n : ids a | (n,a) <- ds] ++ ids b
      X.ECase s bs -> ids s ++ concat [map X.nameId (X.patternNames p) ++ ids b | X.ErasedAlternative p b <- bs]
      _ -> []
