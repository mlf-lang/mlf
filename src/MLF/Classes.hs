-- | Classes elaborate to ordinary, explicitly typed dictionary data. Local
-- overloaded lets abstract their wanted dictionaries; uses request fresh
-- evidence, so the graph solver still controls type generalization.
module MLF.Classes (lowerClasses, lowerClassesWithImports, prettyQualified) where

import Control.Monad (foldM, forM, forM_, unless, when)
import Control.Monad.State.Strict
import Data.Char (isAlphaNum)
import Data.List (intercalate, nub)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified MLF.Data as D
import MLF.Desugar (desugarDo)
import MLF.Kind
import qualified MLF.Kinding as K
import qualified MLF.Syntax as S
import qualified MLF.X.Type as T
import MLF.X.Pretty (prettyType)

data Info = Info S.ClassDecl String String [(String,String)] [String]
type Infos = Map.Map String Info
type Front = StateT (Int,Set.Set String) (Either String)
type Overloads = Map.Map String (String,[String])
type Wants = [(String,String)]

fresh :: String -> Front String
fresh prefix = do
  (i,used) <- get
  let name = prefix ++ show i
  put (i+1,Set.insert name used)
  if name `Set.member` used then fresh prefix else pure name

lookupInfo :: Infos -> String -> Either String Info
lookupInfo infos name = maybe (Left ("unknown class: " ++ name)) Right (Map.lookup name infos)

dictionary :: Infos -> S.Predicate -> Either String S.Type
dictionary infos (S.Predicate c ts) = do
  Info _ name _ _ _ <- lookupInfo infos c
  pure (S.Con name ts)

bottom :: Kind -> S.Type
bottom Star = S.Bottom
bottom k = S.BottomKind k

quantify :: [(String,Kind)] -> S.Type -> S.Type
quantify vars ty = foldr (\(a,k) -> S.Forall S.Flexible a (bottom k)) ty vars

freeType :: S.Type -> Set.Set String
freeType ty = case ty of
  S.TVar a -> Set.singleton a
  S.Arrow a b -> freeType a `Set.union` freeType b
  S.TypeApp a b -> freeType a `Set.union` freeType b
  S.Con _ ts -> Set.unions (map freeType ts)
  S.Forall _ a bound body -> freeType bound `Set.union` Set.delete a (freeType body)
  S.Qualified ps t -> freeType t `Set.union` Set.unions [freeType a | S.Predicate _ as <- ps, a <- as]
  _ -> Set.empty

unique :: String -> [String] -> Either String ()
unique label xs = unless (length xs == length (nub xs)) (Left ("duplicate " ++ label))

-- Only predicates at the outside of a scheme introduce implicit arguments.
scheme :: S.Type -> ([(S.Flag,String,S.Type)], [S.Predicate], S.Type)
scheme (S.Forall f a b t) = let (vs,ps,body) = scheme t in ((f,a,b):vs,ps,body)
scheme (S.Qualified ps t) = ([],ps,t)
scheme t = ([],[],t)

qualified :: S.Type -> Bool
qualified ty = case ty of
  S.Qualified _ _ -> True
  S.Forall _ _ a b -> qualified a || qualified b
  S.Arrow a b -> qualified a || qualified b
  S.TypeApp a b -> qualified a || qualified b
  S.Con _ ts -> any qualified ts
  _ -> False

translateScheme :: D.DataEnv -> Infos -> S.Type -> Either String S.Type
translateScheme ds infos ty = do
  let (vs,ps,body) = scheme ty
  when (qualified body || any (qualified . third) vs) (Left "class constraints must occur at the outside of a type scheme")
  scope <- foldM (\env (_,a,b) -> do k <- K.kindOf ds env b; pure (Map.insert a k env)) Map.empty vs
  mapM_ (checkPredicate ds infos scope) ps
  args <- mapM (dictionary infos) ps
  let result = foldr (\(f,a,b) -> S.Forall f a b) (foldr S.Arrow body args) vs
  K.annotationType ds Map.empty result
  pure result
  where third (_,_,x) = x

checkPredicate :: D.DataEnv -> Infos -> Map.Map String Kind -> S.Predicate -> Either String ()
checkPredicate ds infos scope (S.Predicate c arguments) = do
  Info declaration _ _ _ _ <- lookupInfo infos c
  let parameters = S.classParameters declaration
  unless (length arguments == length parameters)
    (Left ("class argument arity mismatch: " ++ c ++ " expects " ++ show (length parameters) ++
      ", got " ++ show (length arguments)))
  actual <- mapM (K.kindOf ds scope) arguments
  unless (actual == map snd parameters) (Left ("class parameter kind mismatch: " ++ c))

field :: S.Type -> Either String D.Field
field ty = case ty of
  S.TVar a -> pure (D.Parameter a)
  S.Arrow a b -> D.Function <$> field a <*> field b
  S.TypeApp f a -> D.Application <$> field f <*> field a
  S.Con c args -> D.Applied c <$> mapM field args
  S.Forall S.Flexible a S.Bottom b -> D.Quantified a Star <$> field b
  S.Forall S.Flexible a (S.BottomKind k) b -> D.Quantified a k <$> field b
  _ -> Left "class methods require ordinary forall signatures without bounded or nested class constraints"

lowerClasses :: S.Program -> Either String (S.Program, Map.Map String String)
lowerClasses = lowerClassesWithImports Set.empty

-- Imported classes retain their full dictionaries and instance interfaces.
-- Only unqualified method lookup gives local declarations precedence.
lowerClassesWithImports :: Set.Set String -> S.Program -> Either String (S.Program, Map.Map String String)
lowerClassesWithImports _ p@(S.Program _ _) = pure (p,Map.empty)
lowerClassesWithImports imported program@(S.ClassProgram datatypes declarations instances body) = do
  base <- D.validateDeclarations datatypes
  unique "class" (map S.className declarations)
  forM_ [False,True] $ \isImported ->
    unique "class method" [n | d <- declarations, Set.member (S.className d) imported == isImported,
      (n,_) <- S.classMethods d]
  forM_ declarations $ \d -> do
    unique "class method" (map fst (S.classMethods d))
    unique "class parameter" (map fst (S.classParameters d))
    when (null (S.classParameters d)) (Left "class must have at least one parameter")
  let implicit d = d { S.classMethods =
        [(n,quantify [(a,Star) | a <- Set.toAscList (freeType t Set.\\ Set.fromList (map fst (S.classParameters d)))] t)
        | (n,t) <- S.classMethods d] }
      classes = map implicit declarations
      tokens = words (map (\c -> if isAlphaNum c || c `elem` "_'" then c else ' ') (show program))
  evalStateT (lower base classes) (0,Set.fromList tokens)
  where
    lower base classes = do
      entries <- forM classes $ \d -> do
        dict <- fresh ("Dict" ++ S.className d)
        ctor <- fresh ("Make" ++ S.className d)
        methods <- forM (S.classMethods d) $ \(n,_) -> (,) n <$> fresh ("select" ++ S.className d)
        supers <- mapM (const (fresh "superclass")) (S.superclasses d)
        pure (S.className d,Info d dict ctor methods supers)
      let infos = Map.fromList entries
      lift (validateClasses base infos)
      dictionaries <- lift (mapM (dictionaryDecl infos . snd) entries)
      ds <- lift (D.validateDeclarations (datatypes ++ dictionaries))
      checkedInstances <- lift (mapM (validateInstance ds infos) instances)
      lift (checkOverlap checkedInstances)
      names <- mapM (const (fresh "instanceDictionary")) checkedInstances
      let globalCandidates = [(S.InstanceEvidence,n) | n <- names] ++
            [(S.SuperclassEvidence,n) | (_,Info _ _ _ _ ns) <- entries, n <- ns]
          methodBindings isImported = Map.fromList [(name,(selector,[className])) |
            (className,Info _ _ _ methods _) <- entries,
            Set.member className imported == isImported, (name,selector) <- methods]
          methodEnv = Map.union (methodBindings False) (methodBindings True)
      selectors <- concat <$> mapM (selectorDefinitions infos . snd) entries
      definitions <- forM (zip names checkedInstances) $ \(name,inst) -> do
        Info decl _ ctor _ _ <- lift (lookupInfo infos (S.instanceClass inst))
        givenNames <- mapM (const (fresh "givenDictionary")) (S.instanceContext inst)
        let givens = [(S.GivenEvidence,n) | n <- givenNames]
            candidates = givens ++ globalCandidates
        methodBodies <- forM (S.classMethods decl) $ \(method,methodType) -> do
          original <- maybe (lift (Left ("missing instance method: " ++ method))) pure (lookup method (S.instanceMethods inst))
          (translated,wants) <- lowerExpr ds infos methodEnv candidates original
          expected <- instantiateMethod (Map.fromList (zip (map fst (S.classParameters decl)) (S.instanceHead inst))) methodType
          pure (S.Checked expected (closeWants infos candidates wants translated))
        superBodies <- forM (S.superclasses decl) $ \(S.Predicate c _) -> do
          Info _ dict _ _ _ <- lift (lookupInfo infos c)
          pure (S.Wanted dict candidates)
        contextTypes <- lift (mapM (dictionary infos) (S.instanceContext inst))
        resultType <- lift (dictionary infos (S.Predicate (S.instanceClass inst) (S.instanceHead inst)))
        let ty = quantify (S.instanceVariables inst) (foldr S.Arrow resultType contextTypes)
            rhs = foldr (\n b -> S.Lam n Nothing b)
              (foldl S.App (S.Constructor ctor) (superBodies ++ methodBodies)) givenNames
        pure (name,S.Annotation [] ty,rhs)
      (expression,wants) <- lowerExpr ds infos methodEnv globalCandidates body
      let result = closeWants infos globalCandidates wants expression
          bindings = [(n,annotation,S.Checked ty rhs) | (n,annotation@(S.Annotation [] ty),rhs) <- selectors ++ definitions]
          expr = if null bindings then result else S.LetRec bindings result
      pure (S.Program (datatypes ++ dictionaries) expr,
        Map.fromList [(dict,c) | (c,Info _ dict _ _ _) <- entries])

validateClasses :: D.DataEnv -> Infos -> Either String ()
validateClasses ds infos = do
  forM_ (Map.elems infos) $ \(Info d _ _ _ _) -> do
    let scope = Map.fromList (S.classParameters d)
    mapM_ (checkPredicate ds infos scope) (S.superclasses d)
    forM_ (S.classMethods d) $ \(n,t) -> do
      let missing = Map.keysSet scope Set.\\ freeType t
      unless (Set.null missing)
        (Left ("ambiguous class method: " ++ n ++ " does not mention class parameters " ++ show (Set.toList missing)))
      K.annotationType ds scope t
      _ <- field t
      pure ()
  mapM_ (visit Set.empty) (Map.keys infos)
  where
    visit seen name
      | name `Set.member` seen = Left ("cyclic superclass hierarchy: " ++ name)
      | otherwise = do
          Info d _ _ _ _ <- lookupInfo infos name
          mapM_ (\(S.Predicate c _) -> visit (Set.insert name seen) c) (S.superclasses d)

dictionaryDecl :: Infos -> Info -> Either String D.DataDecl
dictionaryDecl infos (Info decl name ctor _ _) = do
  supers <- mapM (dictionary infos) (S.superclasses decl)
  fields <- mapM field (supers ++ map snd (S.classMethods decl))
  pure (D.DataDeclK name (S.classParameters decl) [D.ConstructorDecl ctor fields])

selectorDefinitions :: Infos -> Info -> Front [(String,S.Annotation,S.Expr)]
selectorDefinitions infos (Info decl dict ctor methods supers) = do
  superTypes <- lift (mapM (dictionary infos) (S.superclasses decl))
  let signatures = zip supers superTypes ++ zip (map snd methods) (map snd (S.classMethods decl))
      parameters = S.classParameters decl
  forM (zip [0 :: Int ..] signatures) $ \(index,(name,ty)) -> do
    d <- fresh "dictionary"
    value <- fresh "methodValue"
    let fields = [if i == index then Just value else Nothing | i <- [0 .. length signatures - 1]]
        rhs = S.Lam d Nothing (S.Case (S.Var d) [S.Alternative (S.ConstructorPattern ctor fields) (S.Var value)])
        signature = quantify parameters (S.Arrow (S.Con dict (map (S.TVar . fst) parameters)) ty)
    pure (name,S.Annotation [] signature,rhs)

validateInstance :: D.DataEnv -> Infos -> S.InstanceDecl -> Either String S.InstanceDecl
validateInstance ds infos inst = do
  Info decl _ _ _ _ <- lookupInfo infos (S.instanceClass inst)
  unique "instance method" (map fst (S.instanceMethods inst))
  let required = Set.fromList (map fst (S.classMethods decl))
      supplied = Set.fromList (map fst (S.instanceMethods inst))
  unless (required == supplied) (Left ("instance methods do not match class " ++ S.instanceClass inst ++
    "; missing " ++ show (Set.toList (required Set.\\ supplied)) ++ "; unexpected " ++ show (Set.toList (supplied Set.\\ required))))
  unique "instance type variable" (map fst (S.instanceVariables inst))
  let headArguments = S.instanceHead inst
      free = Set.unions (map freeType headArguments)
      explicit = S.instanceVariables inst
      vars = explicit ++ [(a,Star) | a <- Set.toAscList (free Set.\\ Set.fromList (map fst explicit))]
      scope = Map.fromList vars
  unless (Set.fromList (map fst vars) == free) (Left "instance variables must occur in the instance head")
  checkPredicate ds infos scope (S.Predicate (S.instanceClass inst) headArguments)
  -- Retain the original single-parameter instance restriction. In a relation
  -- with several parameters, variables (including repeated ones) are useful
  -- heads in their own right; all arguments are checked jointly for overlap.
  case headArguments of
    [S.Con _ _] -> pure ()
    [_] -> Left "instance head must start with a named type constructor"
    _ -> pure ()
  mapM_ (headType "") headArguments
  forM_ (S.instanceContext inst) $ \p@(S.Predicate _ args) -> do
    unless (Set.unions (map freeType args) `Set.isSubsetOf` free) (Left "instance context has a variable absent from the head")
    checkPredicate ds infos scope p
    unless (sum (map typeSize args) < sum (map typeSize headArguments) &&
      all (\a -> sum (map (occurrences a) args) <= sum (map (occurrences a) headArguments)) (Set.toList free))
      (Left "instance context must be structurally smaller than its head")
  pure inst { S.instanceVariables = vars }

-- Structural overlap, independent of instance order. Higher-kinded head
-- applications use the same first-order application spine as inference.
data Head = HVar String | HCon String [Head] deriving (Eq, Show)

headType :: String -> S.Type -> Either String Head
headType prefix ty = case ty of
  S.TVar a -> pure (HVar (prefix ++ a))
  S.Con c ts -> foldM (\f a -> HCon "@" . (f:) . (:[]) <$> headType prefix a) (HCon c []) ts
  S.TypeApp f a -> HCon "@" <$> mapM (headType prefix) [f,a]
  S.Arrow a b -> HCon "->" <$> mapM (headType prefix) [a,b]
  _ -> Left "instance heads must be monotypes"

checkOverlap :: [S.InstanceDecl] -> Either String ()
checkOverlap instances = forM_ [(a,b) | (i,a) <- zip [0 :: Int ..] instances, b <- drop (i+1) instances,
    S.instanceClass a == S.instanceClass b] $ \(a,b) -> do
  xs <- mapM (headType "left:") (S.instanceHead a)
  ys <- mapM (headType "right:") (S.instanceHead b)
  when (overlap Map.empty (zip xs ys)) (Left ("overlapping instances for " ++ S.instanceClass a))
  where
    overlap _ [] = True
    overlap subst ((x,y):rest) = case (walk subst x,walk subst y) of
      (a,b) | a == b -> overlap subst rest
      (HVar a,b) | not (occurs a b) -> overlap (Map.insert a b subst) rest
      (a,HVar b) | not (occurs b a) -> overlap (Map.insert b a subst) rest
      (HCon a xs,HCon b ys) | a == b && length xs == length ys -> overlap subst (zip xs ys ++ rest)
      _ -> False
    walk s t@(HVar a) = maybe t (walk s) (Map.lookup a s)
    walk s (HCon c ts) = HCon c (map (walk s) ts)
    occurs a (HVar b) = a == b
    occurs a (HCon _ ts) = any (occurs a) ts

typeSize :: S.Type -> Int
typeSize (S.TVar _) = 1
typeSize (S.Con _ xs) = 1 + sum (map typeSize xs)
typeSize (S.TypeApp f a) = typeSize f + typeSize a
typeSize (S.Arrow a b) = 1 + typeSize a + typeSize b
typeSize _ = 1

occurrences :: String -> S.Type -> Int
occurrences a (S.TVar b) = if a == b then 1 else 0
occurrences a (S.Con _ xs) = sum (map (occurrences a) xs)
occurrences a (S.TypeApp f x) = occurrences a f + occurrences a x
occurrences a (S.Arrow x y) = occurrences a x + occurrences a y
occurrences _ _ = 0

lowerExpr :: D.DataEnv -> Infos -> Overloads -> [(S.EvidenceRole,String)] -> S.Expr -> Front (S.Expr,Wants)
lowerExpr ds infos env candidates expression = case expression of
  S.Var x -> case Map.lookup x env of
    Nothing -> pure (expression,[])
    Just (name,classes) -> do
      wants <- forM classes $ \c -> do n <- fresh "wantedDictionary"; pure (n,c)
      pure (foldl S.App (S.Var name) [S.Var n | (n,_) <- wants],wants)
  S.Constructor _ -> pure (expression,[])
  S.IntLit _ -> pure (expression,[])
  S.DoubleLit _ -> pure (expression,[])
  S.BoolLit _ -> pure (expression,[])
  S.StringLit _ -> pure (expression,[])
  S.Primitive _ -> pure (expression,[])
  S.App a b -> do
    (a',as) <- case a of
      S.Ann rhs (S.Annotation [] ty) | (_,ps,_) <- scheme ty, not (null ps) -> do
        function <- signed rhs ty
        wants <- forM ps $ \(S.Predicate c _) -> do n <- fresh "wantedDictionary"; pure (n,c)
        pure (foldl S.App function [S.Var n | (n,_) <- wants],wants)
      _ -> recurse a
    (b',bs) <- recurse b
    pure (S.App a' b',as ++ bs)
  S.Lam x annotation body -> do
    (annotation',classes) <- case annotation of
      Nothing -> pure (Nothing,[])
      Just (S.Annotation existential ty) -> do
        translated <- if null existential then lift (translateScheme ds infos ty) else pure ty
        let (_,ps,_) = scheme ty
        pure (Just (S.Annotation existential translated),[c | S.Predicate c _ <- ps])
    (body',wants) <- lowerExpr ds infos (Map.insert x (x,classes) env) candidates body
    pure (S.Lam x annotation' body',wants)
  S.Let x (S.Ann rhs (S.Annotation [] ty)) body -> do
    rhs' <- signed rhs ty
    let (_,ps,_) = scheme ty
    (body',wants) <- lowerExpr ds infos (Map.insert x (x,[c | S.Predicate c _ <- ps]) env) candidates body
    pure (S.Let x rhs' body',wants)
  S.Let x rhs body -> do
    (rhs',wanted) <- recurse rhs
    (body',wants) <- lowerExpr ds infos (Map.insert x (x,map snd wanted) env) candidates body
    pure (S.Let x (foldr (\(n,_) -> S.Lam n Nothing) rhs' wanted) body',wants)
  S.Ann a (S.Annotation existential ty) -> do
    let (_,ps,_) = scheme ty
    if not (null ps) then do
      unless (null existential) (lift (Left "qualified annotations cannot bind existentials"))
      result <- signed a ty
      pure (result,[])
    else do
      (a',wants) <- recurse a
      translated <- if null existential then lift (translateScheme ds infos ty) else pure ty
      pure (S.Ann a' (S.Annotation existential translated),wants)
  S.Case a branches -> do
    (a',as) <- recurse a
    bs <- forM branches $ \(S.Alternative p b) -> do
      let names = case p of S.ConstructorPattern _ ns -> [n | Just n <- ns]; S.DefaultPattern n -> [x | Just x <- [n]]
          scope = foldr (\n -> Map.insert n (n,[])) env names
      (b',wants) <- lowerExpr ds infos scope candidates b
      pure (S.Alternative p b',wants)
    pure (S.Case a' (map fst bs),as ++ concatMap snd bs)
  S.Do _ _ -> recurse (desugarDo expression)
  S.LetRec _ _ -> lift (Left "recursive source forms are reserved for dictionary translation")
  S.Wanted _ _ -> lift (Left "dictionary holes are reserved for dictionary translation")
  S.Checked _ _ -> lift (Left "checked source forms are reserved for dictionary translation")
  where
    recurse = lowerExpr ds infos env candidates
    signed a ty = do
      translated <- lift (translateScheme ds infos ty)
      let (_,ps,_) = scheme ty
      names <- mapM (const (fresh "givenDictionary")) ps
      let local = [(S.GivenEvidence,n) | n <- names] ++ candidates
      (body,wants) <- lowerExpr ds infos env local a
      let closed = closeWants infos local wants body
      pure (S.Checked translated (foldr (\n -> S.Lam n Nothing) closed names))

closeWants :: Infos -> [(S.EvidenceRole,String)] -> Wants -> S.Expr -> S.Expr
closeWants infos candidates wants = go
  where
    replacements = Map.fromList [(n,dict) | (n,c) <- wants, Just (Info _ dict _ _ _) <- [Map.lookup c infos]]
    go expr = case expr of
      S.Var n -> maybe expr (\d -> S.Wanted d candidates) (Map.lookup n replacements)
      S.Lam n a b -> S.Lam n a (go b)
      S.App a b -> S.App (go a) (go b)
      S.Let n a b -> S.Let n (go a) (go b)
      S.Ann a t -> S.Ann (go a) t
      S.Case a bs -> S.Case (go a) [S.Alternative p (go b) | S.Alternative p b <- bs]
      S.Checked ty a -> S.Checked ty (go a)
      _ -> expr

-- Substitute all class parameters simultaneously. Instance variables may
-- reuse a class parameter's spelling, so sequential substitution is wrong.
instantiateMethod :: Map.Map String S.Type -> S.Type -> Front S.Type
instantiateMethod arguments = go
  where
    go ty = case ty of
      S.TVar n -> pure (Map.findWithDefault ty n arguments)
      S.Forall f n bound body -> do
        freshName <- fresh "methodType"
        bound' <- go bound
        body' <- go (substitute n (S.TVar freshName) body)
        pure (S.Forall f freshName bound' body')
      S.Arrow a b -> S.Arrow <$> go a <*> go b
      S.TypeApp f a -> S.TypeApp <$> go f <*> go a
      S.Con c xs -> S.Con c <$> mapM go xs
      _ -> pure ty
    substitute n replacement ty = case ty of
      S.TVar a | n == a -> replacement
      S.Forall f a bound body -> S.Forall f a (substitute n replacement bound)
        (if a == n then body else substitute n replacement body)
      S.Arrow a b -> S.Arrow (substitute n replacement a) (substitute n replacement b)
      S.TypeApp f a -> S.TypeApp (substitute n replacement f) (substitute n replacement a)
      S.Con c xs -> S.Con c (map (substitute n replacement) xs)
      _ -> ty

prettyQualified :: Map.Map String String -> T.Type -> String
prettyQualified names = go
  where
    go (T.Forall a bound body) = "forall " ++ binder a bound ++ ". " ++ go body
    go ty = case constraints ty of
      ([],_) -> prettyType ty
      (ps,body) -> (if length ps == 1 then headPredicate ps else "(" ++ intercalate ", " ps ++ ")") ++ " => " ++ go body
    headPredicate [p] = p
    headPredicate ps = intercalate ", " ps
    binder a T.Bot = prettyType (T.Var a)
    binder a (T.BotKind k) = "(" ++ prettyType (T.Var a) ++ " : " ++ prettyKind k ++ ")"
    binder a b = "(" ++ prettyType (T.Var a) ++ " >= " ++ prettyType b ++ ")"
    constraints (T.Arrow (T.Con d args) body)
      | Just cls <- Map.lookup d names = let (ps,result) = constraints body in (unwords (cls : map argument args):ps,result)
    constraints t = ([],t)
    argument t = case t of
      T.Var _ -> prettyType t
      T.Con _ [] -> prettyType t
      _ -> "(" ++ prettyType t ++ ")"
