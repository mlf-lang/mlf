{-# LANGUAGE FlexibleContexts #-}
-- | Source module loading and lexical name resolution. Private declarations
-- are retained for checking, but only each module's interface enters import
-- scopes. Every user entity receives a fresh name before the core pipeline.
module MLF.Module
  ( LinkedModule (..), loadModuleMap, loadModuleFiles, linkModules, displayNames
  , Space (..), Role (..), Entity (..), Interface, Names, interface, visible
  , locals, scope, exportsFor, renameModule, primitiveEntities, primitiveScope
  , preludeSource, importsFor, label, space
  ) where

import Control.Exception (IOException, evaluate, try)
import Control.Monad (filterM, foldM, forM, forM_, unless, when)
import Control.Monad.Except
import Control.Monad.State.Strict
import Data.Char (isAlphaNum)
import Data.Bifunctor (first)
import Data.Functor.Identity (runIdentity)
import Data.List (intercalate, nub)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import System.Directory (canonicalizePath, doesFileExist)
import System.FilePath ((</>), joinPath, takeDirectory)
import qualified MLF.Data as D
import MLF.Desugar (desugarDo)
import MLF.Module.Syntax
import MLF.Parser (parseModule)
import MLF.Prelude (PreludeMode (..), monadClass, ioInstance, stInstance)
import qualified MLF.Primitive as P
import qualified MLF.Surface as Surface
import qualified MLF.Syntax as S

data LinkedModule = LinkedModule
  { linkedProgram :: S.Program
  , linkedNames :: Map.Map String String
  , linkedValueScopes :: Map.Map String (Set.Set Int)
  , linkedInstanceScopes :: [Set.Set Int]
  } deriving Show

-- Dependency order is stable, imports are loaded once, and cycles are
-- diagnosed with the complete chain rather than recursing into the loader.
loadGraph :: Monad m => (String -> m (Either String SourceModule)) -> SourceModule
          -> m (Either String [SourceModule])
loadGraph fetch root = runExceptT $ do
  (_,(_,reversed)) <- runStateT (visit [] root) (Set.empty,[])
  pure (reverse reversed)
  where
    visit trail m = do
      let name = moduleIdentity m
      when (elem name trail) (throwError ("cyclic imports: " ++ intercalate " -> " (trail ++ [name])))
      (done,_) <- get
      unless (Set.member name done) $ do
        forM_ (nub (map importedModule (sourceImports m))) $ \dependency ->
          unless (dependency == "Prelude") $ do
            when (elem dependency (trail ++ [name]))
              (throwError ("cyclic imports: " ++ intercalate " -> " (trail ++ [name,dependency])))
            (seen,_) <- get
            unless (Set.member dependency seen) $ do
              child <- lift (lift (fetch dependency)) >>= either throwError pure
              unless (sourceModuleName child == Just dependency)
                (throwError (sourcePath child ++ ": expected module " ++ dependency ++
                  ", found " ++ maybe "an unnamed script" id (sourceModuleName child)))
              when (sourceBody child /= Nothing)
                (throwError (sourcePath child ++ ": imported modules must contain declarations only"))
              visit (trail ++ [name]) child
        modify (\(done',order) -> (Set.insert name done',m:order))

loadModuleMap :: Map.Map String (FilePath,String) -> SourceModule -> Either String [SourceModule]
loadModuleMap sources root = runIdentity (loadGraph fetch root)
  where
    fetch name = pure $ case Map.lookup name sources of
      Nothing -> Left ("cannot find module " ++ name)
      Just (file,source) -> parseModule file source

loadModuleFiles :: [FilePath] -> SourceModule -> IO (Either String [SourceModule])
loadModuleFiles includes root = do
  let directory = takeDirectory (sourcePath root)
      hierarchy = iterate takeDirectory directory !! (length (components (moduleIdentity root)) - 1)
  paths <- mapM canonicalizePath (nub (directory : includes ++ [hierarchy,"."]))
  loadGraph (fetch (nub paths)) root
  where
    fetch paths name = do
      let files = [path </> joinPath (components name) ++ ".emlf" | path <- paths]
      found <- filterM doesFileExist files
      case found of
        [] -> pure (Left ("cannot find module " ++ name ++ "; searched " ++ intercalate ", " files))
        file:_ -> do
          result <- try (readFile file >>= \s -> evaluate (length s) >> pure s) :: IO (Either IOException String)
          pure (either (Left . show) (parseModule file) result)

components :: String -> [String]
components name = case break (== '.') name of
  (part,[]) -> [part]
  (part,_:rest) -> part : components rest

data Space = Terms | Types deriving (Eq, Ord, Show)
data Role = Value | Datatype | Class | Constructor String | Method String
          | BuiltinType | Primitive P.Primitive | Boolean Bool deriving (Eq, Ord, Show)
data Entity = Entity { owner :: String, spelling :: String, role :: Role } deriving (Eq, Ord, Show)
type Interface = Map.Map (Space,String) (Set.Set Entity)
type Names = Map.Map Entity String

space :: Entity -> Space
space e = case role e of Datatype -> Types; Class -> Types; BuiltinType -> Types; _ -> Terms

parent :: Entity -> Maybe (String,String)
parent e = case role e of
  Constructor t -> Just (owner e,t)
  Method c -> Just (owner e,c)
  Boolean _ -> Just ("Prelude","Bool")
  _ -> Nothing

interface :: [Entity] -> Interface
interface = Map.fromListWith Set.union . map (\e -> ((space e,spelling e),Set.singleton e))

uniqueInterface :: String -> Interface -> Either String Interface
uniqueInterface context env = do
  forM_ (Map.toList env) $ \((_,name),entities) ->
    unless (Set.size entities == 1)
      (Left (context ++ ": conflicting declarations or exports for " ++ name))
  pure env

locals :: SourceModule -> Either String Interface
locals m = do
  forM_ (sourceDatatypes m) $ \d -> do
    when (elem (D.datatypeName d) [spelling e | e <- primitiveEntities, role e == BuiltinType])
      (Left (moduleIdentity m ++ ": cannot redefine a primitive type: " ++ D.datatypeName d))
    when (elem (D.datatypeName d) ["True","False"])
      (Left (moduleIdentity m ++ ": reserved data type name"))
    forM_ (D.datatypeConstructors d) $ \c ->
      when (elem (D.constructorName c) ["True","False","Unit"])
        (Left (moduleIdentity m ++ ": cannot redefine a primitive constructor: " ++ D.constructorName c))
  let entries = [entity n Value | (n,_,_) <- sourceValues m] ++
        concat [[entity (D.datatypeName d) Datatype] ++
          [entity (D.constructorName c) (Constructor (D.datatypeName d)) | c <- D.datatypeConstructors d]
          | d <- sourceDatatypes m] ++
        concat [[entity (S.className c) Class] ++
          [entity n (Method (S.className c)) | (n,_) <- S.classMethods c] | c <- sourceClasses m]
      keys = [(space e,spelling e) | e <- entries]
  unless (length keys == length (nub keys)) (Left (moduleIdentity m ++ ": duplicate declaration"))
  uniqueInterface (moduleIdentity m) (interface entries)
  where entity n = Entity (moduleIdentity m) n

preludeSource :: SourceModule
preludeSource = SourceModule "<Prelude>" (Just "Prelude") Nothing [] [] [monadClass] [ioInstance,stInstance] [] Nothing

primitiveEntities :: [Entity]
primitiveEntities =
  [Entity "Prelude" (P.primitiveName p) (Primitive p) | p <- [minBound .. maxBound]] ++
  [Entity "Prelude" "pure" (Primitive P.IOReturn)] ++
  [Entity "Prelude" t BuiltinType |
    t <- ["Int","Double","Bool","String","Unit","IO","IntArray","DoubleArray","ByteArray","IntTable","ST","STArray"]] ++
  [Entity "Prelude" "Unit" (Constructor "Unit"), Entity "Prelude" "True" (Boolean True),
    Entity "Prelude" "False" (Boolean False)]

primitiveScope :: Interface
primitiveScope = interface (primitiveEntities ++
  [Entity "Prelude" "return" (Primitive P.IOReturn),Entity "Prelude" "bind" (Primitive P.IOBind)])

importsFor :: PreludeMode -> SourceModule -> [Import]
importsFor mode m
  | moduleIdentity m == "Prelude" = []
  | mode == ImplicitPrelude && not (any ((== "Prelude") . importedModule) imports) =
      Import "Prelude" False Nothing Everything : imports
  | otherwise = imports
  where imports = sourceImports m

-- All bindings of a name remain in the scope until use. The same original
-- entity imported along a diamond is not an ambiguity; two different ones are.
scope :: PreludeMode -> Map.Map String Interface -> SourceModule -> Interface -> Either String Interface
scope mode exports m local = do
  imported <- forM (importsFor mode m) $ \imp -> do
    available <- maybe (Left ("unknown imported module " ++ importedModule imp)) pure
      (Map.lookup (importedModule imp) exports)
    selected <- selectImport available (importSelection imp)
    let alias = maybe (importedModule imp) id (importAlias imp)
        qualifiedOnly = qualify alias selected
    pure (if importQualified imp then qualifiedOnly else union selected qualifiedOnly)
  let builtins = if mode == NoImplicitPrelude && not (any ((== "Prelude") . importedModule) (sourceImports m))
        then primitiveScope else Map.empty
      declared = foldr union (union local (qualify (moduleIdentity m) local)) imported
  pure (Map.union declared builtins)
  where
    qualify name = Map.mapKeys (\(s,n) -> (s,name ++ "." ++ n))

union :: Interface -> Interface -> Interface
union = Map.unionWith Set.union

lookupEntity :: Space -> String -> Interface -> Either String Entity
lookupEntity namespace name env = case maybe [] Set.toList (Map.lookup (namespace,name) env) of
  [] -> Left ("name is not in scope: " ++ name)
  [e] -> Right e
  es -> Left ("ambiguous name " ++ name ++ ": " ++ intercalate ", " (map label es))

label :: Entity -> String
label e = owner e ++ "." ++ spelling e

visible :: Interface -> Set.Set Entity
visible = Set.unions . Map.elems

selectItem :: Bool -> Interface -> Export -> Either String Interface
selectItem hiding env item = case item of
  ExportValue n -> interface . (:[]) <$> lookupEntity Terms n env
  ExportType n Abstract | hiding -> do
    let matches = Set.union (Map.findWithDefault Set.empty (Types,n) env)
          (Set.filter isConstructor (Map.findWithDefault Set.empty (Terms,n) env))
    when (Set.null matches) (Left ("name is not exported: " ++ n))
    pure (interface (Set.toList matches))
  ExportType n members -> do
    ty <- lookupEntity Types n env
    let children = [e | e <- Set.toList (visible env), parent e == Just (owner ty,spelling ty)]
    chosen <- case members of
      Abstract -> pure []
      AllMembers -> pure children
      Members ns -> forM ns $ \child -> case filter ((== child) . spelling) children of
        [e] -> pure e
        _ -> Left (child ++ " is not a visible member of " ++ n)
    pure (interface (ty:chosen))
  ExportModule _ -> Left "module re-exports are only allowed in export lists"
  where
    isConstructor e = case role e of Constructor _ -> True; Boolean _ -> True; _ -> False

selectImport :: Interface -> Selection -> Either String Interface
selectImport env selection = case selection of
  Everything -> pure env
  Only items -> foldM (\acc item -> union acc <$> selectItem False env item) Map.empty items
  Hiding items -> do
    hidden <- foldM (\acc item -> union acc <$> selectItem True env item) Map.empty items
    pure (Map.mapMaybe (\es -> let remaining = es Set.\\ visible hidden
                              in if Set.null remaining then Nothing else Just remaining) env)

exportsFor :: PreludeMode -> SourceModule -> Interface -> Interface -> Either String Interface
exportsFor mode m local env = case sourceExports m of
  Nothing -> pure local
  Just items -> foldM add Map.empty items >>= uniqueInterface (moduleIdentity m)
  where
    aliases = moduleIdentity m : [maybe (importedModule i) id (importAlias i) | i <- importsFor mode m]
    add acc (ExportModule name) = do
      unless (elem name aliases) (Left ("cannot re-export unimported module " ++ name))
      let entries = [e | ((s,n),es) <- Map.toList env, not (elem '.' n), e <- Set.toList es,
            Set.member e (Map.findWithDefault Set.empty (s,name ++ "." ++ n) env)]
      pure (union acc (interface entries))
    add acc item = union acc <$> selectItem False env item

freshNames :: [SourceModule] -> Set.Set Entity -> Names
freshNames modules entities = evalState (Map.fromList <$> mapM allocate (Set.toAscList entities)) (0 :: Int,used)
  where
    used = Set.fromList (words (map (\c -> if isAlphaNum c || elem c "_'" then c else ' ') (show modules)))
    allocate e | role e == BuiltinType || (owner e == "Prelude" && spelling e == "Unit") = pure (e,spelling e)
    allocate e = do
      (i,names) <- get
      let prefix = if space e == Types || isConstructor (role e) then "ModuleEntity" else "moduleEntity"
          name = prefix ++ show i
      put (i+1,Set.insert name names)
      if Set.member name names then allocate e else pure (e,name)
    isConstructor (Constructor _) = True
    isConstructor _ = False

resolvedName :: Names -> Entity -> Either String String
resolvedName names e = maybe (Left ("missing module identity: " ++ label e)) pure (Map.lookup e names)

resolveType :: Names -> Interface -> S.Type -> Either String S.Type
resolveType names env = go
  where
    go ty = case ty of
      S.Arrow a b -> S.Arrow <$> go a <*> go b
      S.Con "Unit" as -> S.Con "Unit" <$> mapM go as
      S.Con c as -> S.Con <$> typeName c <*> mapM go as
      S.TypeApp f a -> S.TypeApp <$> go f <*> go a
      S.Forall flag n bound b -> S.Forall flag n <$> go bound <*> go b
      S.Qualified ps b -> S.Qualified <$> mapM (resolvePredicate names env) ps <*> go b
      _ -> pure ty
    typeName n = lookupEntity Types n env >>= \e -> case role e of
      Class -> Left ("class used as a type constructor: " ++ n)
      _ -> resolvedName names e

resolvePredicate :: Names -> Interface -> S.Predicate -> Either String S.Predicate
resolvePredicate names env (S.Predicate n ts) = do
  e <- lookupEntity Types n env
  unless (role e == Class) (Left ("not a class: " ++ n))
  S.Predicate <$> resolvedName names e <*> mapM (resolveType names env) ts

resolveAnnotation :: Names -> Interface -> S.Annotation -> Either String S.Annotation
resolveAnnotation names env (S.Annotation ns t) = S.Annotation ns <$> resolveType names env t

resolveExpr :: Names -> Interface -> S.Expr -> Either String S.Expr
resolveExpr names env = go Set.empty . desugarDo
  where
    ann = resolveAnnotation names env
    go bound expression = case expression of
      S.Var n | Set.member n bound -> pure expression
              | otherwise -> lookupEntity Terms n env >>= variable
      S.Constructor "Unit" -> pure expression
      S.Constructor n -> lookupEntity Terms n env >>= constructor
      S.Lam n a b -> S.Lam n <$> traverse ann a <*> go (Set.insert n bound) b
      S.App a b -> S.App <$> go bound a <*> go bound b
      S.Let n a b -> S.Let n <$> go bound a <*> go (Set.insert n bound) b
      S.Ann a t -> S.Ann <$> go bound a <*> ann t
      S.LetRec ds b -> do
        let scope' = bound <> Set.fromList [n | (n,_,_) <- ds]
        S.LetRec <$> mapM (\(n,t,a) -> (,,) n <$> ann t <*> go scope' a) ds <*> go scope' b
      S.Case a bs -> S.Case <$> go bound a <*> mapM (\(S.Alternative p b) ->
        S.Alternative <$> pattern' p <*> go (bound <> Set.fromList (Surface.patternVariables p)) b) bs
      S.Equations rows -> S.Equations <$> mapM (\(ps,b) -> (,)
        <$> mapM pattern' ps <*> go (bound <> Set.fromList (concatMap Surface.patternVariables ps)) b) rows
      S.Do _ _ -> go bound (desugarDo expression)
      S.Checked _ _ -> Left "checked source forms are reserved for dictionary translation"
      S.Wanted _ _ -> Left "dictionary holes are reserved for dictionary translation"
      _ -> pure expression
    variable e = case role e of
      Primitive p -> pure (S.Primitive p)
      Value -> S.Var <$> resolvedName names e
      Method _ -> S.Var <$> resolvedName names e
      _ -> Left ("not a function or value: " ++ label e)
    constructor e = case role e of
      Constructor _ -> S.Constructor <$> resolvedName names e
      Boolean b -> pure (S.BoolLit b)
      _ -> Left ("not a data constructor: " ++ label e)
    pattern' p = case p of
      S.ConstructorPattern "Unit" [] -> pure p
      S.ConstructorPattern n fields -> do
        e <- lookupEntity Terms n env
        case role e of
          Constructor _ -> (\name -> S.ConstructorPattern name fields) <$> resolvedName names e
          Boolean b | null fields -> pure (S.BoolPattern b)
          _ -> Left ("not a constructor pattern: " ++ n)
      S.NestedPattern n ps -> do
        e <- lookupEntity Terms n env
        case role e of
          Constructor _ -> S.NestedPattern <$> resolvedName names e <*> mapM pattern' ps
          _ -> Left ("not a constructor pattern: " ++ n)
      S.AnnotatedPattern n t -> S.AnnotatedPattern n <$> ann t
      _ -> pure p

renameModule :: Names -> Interface -> Interface -> SourceModule
             -> Either String ([D.DataDecl],[S.ClassDecl],[S.InstanceDecl],[ValueDeclaration],Maybe S.Expr)
renameModule names local env m = do
  ds <- mapM datatype (sourceDatatypes m)
  cs <- mapM class' (sourceClasses m)
  is <- mapM instance' (sourceInstances m)
  vs <- mapM (\(n,t,e) -> (,,) <$> own Terms n <*> traverse annotation t <*> expression e) (sourceValues m)
  b <- traverse expression (sourceBody m)
  pure (ds,cs,is,vs,b)
  where
    own s n = lookupEntity s n local >>= resolvedName names
    annotation = resolveAnnotation names env
    typ = resolveType names env
    predicate = resolvePredicate names env
    expression = resolveExpr names env
    field f = case f of
      D.Parameter _ -> pure f
      D.Applied n fs -> do
        t <- typ (S.Con n [])
        case t of S.Con n' _ -> D.Applied n' <$> mapM field fs; _ -> Left "invalid field type"
      D.Function a b -> D.Function <$> field a <*> field b
      D.Application a b -> D.Application <$> field a <*> field b
      D.Quantified n k b -> D.Quantified n k <$> field b
    datatype d = D.DataDeclK <$> own Types (D.datatypeName d) <*> pure (D.datatypeBinders d) <*>
      mapM (\c -> D.ConstructorDecl <$> own Terms (D.constructorName c) <*> mapM field (D.constructorFields c))
        (D.datatypeConstructors d)
    class' c = S.ClassDecl <$> own Types (S.className c) <*> pure (S.classParameters c)
      <*> mapM predicate (S.superclasses c)
      <*> mapM (\(n,t) -> (,) <$> own Terms n <*> typ t) (S.classMethods c)
    instance' inst = do
      klass <- lookupEntity Types (S.instanceClass inst) env
      unless (role klass == Class) (Left ("not a class: " ++ S.instanceClass inst))
      methods <- forM (S.instanceMethods inst) $ \(n,e) -> do
        name <- resolvedName names (Entity (owner klass) n (Method (spelling klass)))
        (,) name <$> expression e
      S.InstanceDecl (S.instanceVariables inst) <$> mapM predicate (S.instanceContext inst)
        <*> resolvedName names klass <*> mapM typ (S.instanceHead inst) <*> pure methods

linkModules :: PreludeMode -> [SourceModule] -> Either String LinkedModule
linkModules _ [] = Left "no entry module"
linkModules mode supplied = do
  when (any ((== "Prelude") . moduleIdentity) supplied) (Left "Prelude is a built-in module and cannot be redefined")
  let usePrelude = any (any ((== "Prelude") . importedModule) . importsFor mode) supplied
      modules = (if usePrelude then [preludeSource] else []) ++ supplied
  localEntries <- forM modules $ \m -> do
    local <- locals m
    pure (moduleIdentity m,if moduleIdentity m == "Prelude" then union local (interface primitiveEntities) else local)
  let localMap = Map.fromList localEntries
      allEntities = Set.unions (visible primitiveScope : map (visible . snd) localEntries)
      names = freshNames modules allEntities
      publicNames = Map.fromList [(n,if owner e == "Prelude" then spelling e else label e) | (e,n) <- Map.toList names]
      bindValues values = first (displayNames publicNames) . Surface.bindValues values
  (_,resolved) <- foldM (resolveOne names localMap) (Map.empty,[]) modules
  let ds = concat [a | (_,_,(a,_,_,_,_)) <- resolved]
      cs = concat [a | (_,_,(_,a,_,_,_)) <- resolved]
      instances = [(moduleIdentity m,i) | (m,_,(_,_,is,_,_)) <- resolved, i <- is]
      values = concat [a | (_,_,(_,_,_,a,_)) <- resolved]
      reach = foldl (\acc m -> Map.insert (moduleIdentity m)
        (Set.insert (moduleIdentity m) (Set.unions
          [Map.findWithDefault Set.empty (importedModule i) acc | i <- importsFor mode m])) acc) Map.empty modules
      candidates ownerName = Set.fromList [i | (i,(o,_)) <- zip [0..] instances,
        Set.member o (Map.findWithDefault Set.empty ownerName reach)]
      scopes = Map.fromList [(n,candidates (moduleIdentity m)) | (m,_,(_,_,_,vs,_)) <- resolved, (n,_,_) <- vs]
  entry <- case last resolved of
    (m,env,(_,_,_,_,body)) -> case body of
      Just expression -> pure expression
      Nothing | any (\(n,_,_) -> n == "main") (sourceValues m) ->
        S.Var <$> resolvedName names (Entity (moduleIdentity m) "main" Value)
      Nothing -> resolveExpr names env (S.Var "main")
  body <- bindValues values entry
  -- Instance bodies can use module-level helpers. Close over only their value
  -- dependencies; class methods themselves remain dictionary references.
  let valueMap = Map.fromList [(n,(n,t,e)) | (n,t,e) <- values]
      closure seen todo = case Set.minView todo of
        Nothing -> seen
        Just (n,rest) | Set.member n seen -> closure seen rest
        Just (n,rest) -> case Map.lookup n valueMap of
          Nothing -> closure seen rest
          Just (_,_,e) -> closure (Set.insert n seen) (rest <> Surface.freeNames e)
      close e = let needed = closure Set.empty (Surface.freeNames e)
                in bindValues [v | v@(n,_,_) <- values, Set.member n needed] e
  instances' <- forM instances $ \(_,i) -> do
    methods <- mapM (\(n,e) -> (,) n <$> close e) (S.instanceMethods i)
    pure i { S.instanceMethods = methods }
  let program = if null cs && null instances' then S.Program ds body else S.ClassProgram ds cs instances' body
  pure (LinkedModule program publicNames
    scopes [candidates o | (o,_) <- instances])
  where
    resolveOne names localMap (exports,done) m = do
      local <- maybe (Left "missing module declarations") pure (Map.lookup (moduleIdentity m) localMap)
      env <- if moduleIdentity m == "Prelude" then pure local else scope mode exports m local
      exported <- exportsFor mode m local env
      renamed <- either (Left . ((sourcePath m ++ ": ") ++)) pure (renameModule names local env m)
      pure (Map.insert (moduleIdentity m) exported exports, done ++ [(m,env,renamed)])

displayNames :: Map.Map String String -> String -> String
displayNames names = go
  where
    go [] = []
    go input@(c:cs)
      | isAlphaNum c || elem c "_'" = let (word,rest) = span (\x -> isAlphaNum x || elem x "_'") input
                                    in Map.findWithDefault word word names ++ go rest
      | otherwise = c : go cs
