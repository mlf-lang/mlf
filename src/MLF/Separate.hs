{-# LANGUAGE FlexibleContexts #-}
-- | Separate compilation at the checked xMLF boundary. Interfaces contain
-- declarations and schemes, never source implementations. Objects are closed
-- xMLF functions over their imports, verified again when they are linked.
module MLF.Separate
  ( UnitInterface(..), UnitObject(..), compileUnit, builtinPrelude
  , encodeInterface, decodeInterface, encodeObject, decodeObject, interfaceFingerprint
  , compileModuleFile, linkModuleFile, showInterfaceFile
  , linkObjects, objectTerm, stableName
  ) where

import Control.Exception (IOException, evaluate, try)
import Control.Monad (foldM, forM, forM_, unless)
import Control.Monad.State.Strict
import Data.Bifunctor (first)
import Data.Char (ord, isDigit)
import Data.List (intercalate, nub, sortOn)
import qualified Data.List as List
import qualified Data.Map.Strict as M
import qualified Data.Set as Set
import System.Directory (doesFileExist, createDirectoryIfMissing, renameFile)
import System.FilePath ((</>), takeDirectory, dropExtension)
import qualified MLF.Classes as Classes
import MLF.Compiler (finishCompilation, compiledTerm)
import qualified MLF.Data as D
import MLF.Desugar (desugarDo)
import MLF.Kind
import MLF.Module
import MLF.Module.Syntax
import qualified MLF.Parser as Parser
import MLF.Prelude (PreludeMode(..))
import qualified MLF.Primitive as P
import qualified MLF.Surface as Surface
import qualified MLF.Syntax as S
import qualified MLF.X.Check as Check
import qualified MLF.X.Parser as XP
import qualified MLF.X.Pretty as Pretty
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

data UnitInterface = UnitInterface
  { unitName :: String
  , unitDependencies :: [(String,String)]
  , unitExports :: [Entity]
  , unitData :: [D.DataDecl]
  , unitClasses :: [S.ClassDecl]
  , unitInstances :: [(String,S.InstanceDecl)]
  , unitBindings :: [(String,T.Type)]
  , unitObjectFingerprint :: String
  } deriving Show
data UnitObject = UnitObject UnitInterface X.Term deriving Show
objectTerm :: UnitObject -> X.Term
objectTerm (UnitObject _ term) = term

ensure :: Bool -> String -> Either String ()
ensure p e = unless p (Left e)

-- Injective nominal identities. All source-local binders are alpha-renamed
-- before resolution, so even deliberately similar user spellings cannot
-- capture a global. These identities do not depend on import traversal order.
encoded :: String -> String
encoded = concatMap (\c -> show (ord c) ++ "_")
stableName :: Entity -> String
stableName e
  | role e == BuiltinType || (owner e == "Prelude" && spelling e == "Unit") = spelling e
  | otherwise = (if space e == Types || constructor (role e) then "Module_" else "module_")
      ++ encoded (owner e) ++ "z_" ++ encoded (spelling e)
  where constructor (Constructor _) = True; constructor _ = False

hygiene :: S.Expr -> S.Expr
hygiene e = evalState (go M.empty e) (0 :: Int)
  where
    fresh n = do i <- get; put (i+1); pure (n,"separateLocal" ++ show i)
    bind env ns = do pairs <- mapM fresh ns; pure (M.union (M.fromList pairs) env)
    name env n = M.findWithDefault n n env
    annotation = id
    pat env p = case p of
      S.DefaultPattern n -> S.DefaultPattern (name env <$> n)
      S.ConstructorPattern c ns -> S.ConstructorPattern c (map (fmap (name env)) ns)
      S.NestedPattern c ps -> S.NestedPattern c (map (pat env) ps)
      S.AnnotatedPattern n a -> S.AnnotatedPattern (name env n) a
      _ -> p
    go env a = case a of
      S.Var n -> pure (S.Var (name env n))
      S.Lam n t b -> do scope' <- bind env [n]; S.Lam (name scope' n) (annotation t) <$> go scope' b
      S.App f x -> S.App <$> go env f <*> go env x
      S.Let n x b -> do scope' <- bind env [n]; S.Let (name scope' n) <$> go env x <*> go scope' b
      S.Ann x t -> (`S.Ann` t) <$> go env x
      S.LetRec ds b -> do
        scope' <- bind env [n | (n,_,_) <- ds]
        S.LetRec <$> mapM (\(n,t,x) -> (,,) (name scope' n) t <$> go scope' x) ds <*> go scope' b
      S.Case x bs -> S.Case <$> go env x <*> mapM (\(S.Alternative p b) -> do
        scope' <- bind env (Surface.patternVariables p)
        S.Alternative (pat scope' p) <$> go scope' b) bs
      S.Equations rows -> S.Equations <$> mapM (\(ps,b) -> do
        scope' <- bind env (concatMap Surface.patternVariables ps)
        (,) (map (pat scope') ps) <$> go scope' b) rows
      S.Do _ _ -> go env (desugarDo a)
      _ -> pure a

-- A canonical source type for a target scheme. Leading dictionary arguments
-- become class predicates so imported overloaded functions remain overloaded.
sourceScheme :: M.Map String String -> T.Type -> S.Type
sourceScheme dictionaries = go True
  where
    variable (T.TyVar i) = "a" ++ show (if i < 0 then 2*(-i)+1 else 2*i)
    go qualified t = case t of
      T.Var a -> S.TVar (variable a)
      T.Bot -> S.Bottom
      T.BotKind k -> S.BottomKind k
      T.Arrow (T.Con d ts) b | qualified, Just c <- M.lookup d dictionaries ->
        case go True b of
          S.Qualified ps body -> S.Qualified (S.Predicate c (map (go False) ts):ps) body
          body -> S.Qualified [S.Predicate c (map (go False) ts)] body
      T.Arrow a b -> S.Arrow (go False a) (go False b)
      T.Con c ts -> S.Con c (map (go False) ts)
      T.Apply a b -> S.TypeApp (go False a) (go False b)
      T.Forall a bound b -> S.Forall S.Flexible (variable a) (go False bound) (go qualified b)

-- Deterministic alpha-normal forms make ABI fingerprints independent of graph
-- allocation IDs, implementation edits, and seed/self-hosted elaborator IDs.
normalType :: T.Type -> T.Type
normalType t = evalState (go M.empty t) (0 :: Int)
  where
    go env ty = case ty of
      T.Var n -> maybe (pure ty) (pure . T.Var) (M.lookup n env)
      T.Arrow a b -> T.Arrow <$> go env a <*> go env b
      T.Con c ts -> T.Con c <$> mapM (go env) ts
      T.Apply a b -> T.Apply <$> go env a <*> go env b
      T.Forall n a b -> do
        a' <- go env a
        i <- get; put (i+1)
        T.Forall (T.TyVar i) a' <$> go (M.insert n (T.TyVar i) env) b
      _ -> pure ty

compileUnit :: PreludeMode -> [UnitInterface] -> SourceModule -> Either String UnitObject
compileUnit mode dependencies original = do
  let name = moduleIdentity original
      imported = nub [importedModule i | i <- importsFor mode original]
      dependencyMap = M.fromList [(unitName i,i) | i <- dependencies]
  ensure (name /= "Prelude" || sourcePath original == "<Prelude>") "Prelude is a built-in module and cannot be redefined"
  ensure (M.notMember name dependencyMap) ("cyclic imports: " ++ name)
  mapM_ (\n -> ensure (M.member n dependencyMap) ("missing compiled interface for " ++ n)) imported
  let clean = original { sourceValues = [(n,t,hygiene e) | (n,t,e) <- sourceValues original]
        , sourceInstances = [i { S.instanceMethods = [(n,hygiene e) | (n,e) <- S.instanceMethods i] } | i <- sourceInstances original]
        , sourceBody = hygiene <$> sourceBody original }
  declared <- locals clean
  let local = if name == "Prelude" then M.unionWith Set.union declared (interface primitiveEntities) else declared
      public = M.fromList [(unitName i,interface (unitExports i)) | i <- dependencies]
  env <- if name == "Prelude" then pure local else scope mode public clean local
  exported <- exportsFor mode clean local env
  let entities = Set.unions [visible env,visible local,visible primitiveScope]
      methodEntities = [Entity (owner e) n (Method (spelling e)) | e <- Set.toList entities, role e == Class,
        inst <- sourceInstances original, (n,_) <- S.instanceMethods inst]
      names = M.fromList [(e,stableName e) | e <- Set.toList entities ++ methodEntities]
  (ds,cs,is,vs,expression) <- renameModule names local env clean
  let mainName = stableName (Entity name "main" Value)
      inheritedMain = case Set.toList (M.findWithDefault Set.empty (Terms,"main") env) of
        [e] | not (any (\(n,_,_) -> n == mainName) vs), role e == Value -> [(mainName,Nothing,S.Var (stableName e))]
        _ -> []
      values = case expression of Nothing -> vs ++ inheritedMain; Just e -> vs ++ [(mainName,Nothing,e)]
      valueMap = M.fromList [(n,v) | v@(n,_,_) <- values]
      closure seen todo = case Set.minView todo of
        Nothing -> seen
        Just (n,rest) | Set.member n seen -> closure seen rest
        Just (n,rest) -> case M.lookup n valueMap of
          Nothing -> closure seen rest
          Just (_,_,e) -> closure (Set.insert n seen) (rest <> Surface.freeNames e)
      close e = Surface.bindValues [v | v@(n,_,_) <- values, Set.member n (closure Set.empty (Surface.freeNames e))] e
  instances <- forM is $ \i -> do
    methods <- mapM (\(n,e) -> (,) n <$> close e) (S.instanceMethods i)
    pure i { S.instanceMethods = methods }
  body <- Surface.bindValues values (S.Constructor "Unit")
  let allClasses = concatMap unitClasses dependencies ++ cs
      dictionaries = M.fromList [("Dict_" ++ S.className c,S.className c) | c <- allClasses]
      externalTypes = M.fromList (concatMap unitBindings dependencies)
      externals = M.mapWithKey (\n ty -> sourceScheme
        (if take 7 n == "module_" then dictionaries else M.empty) ty) externalTypes
      ownInstances = [("instance_" ++ encoded name ++ "z_" ++ show i,inst) | (i,inst) <- zip [0 :: Int ..] instances]
      allInstances = concatMap unitInstances dependencies ++ ownInstances
      program = S.ClassProgram (concatMap unitData dependencies ++ ds) allClasses (map snd allInstances) body
  lowered <- Classes.lowerSeparateClasses externals (map fst allInstances) program
  compiled <- first show (finishCompilation lowered)
  let full = compiledTerm compiled
      (declarations,core) = case full of X.WithData declarations' core' -> (declarations',core'); _ -> ([],full)
  (parameters,implementation) <- if M.null externalTypes then pure ([],core) else case core of
    X.LetRec bs rest -> do
      ensure (map (X.nameHint . first3) bs == M.keys externalTypes) "module import parameter order mismatch"
      forM_ bs $ \(n,t,_) -> ensure (maybe False (T.alphaEq t) (M.lookup (X.nameHint n) externalTypes))
        ("imported scheme changed during elaboration: " ++ X.nameHint n)
      pure ([(n,t) | (n,t,_) <- bs],rest)
    _ -> Left "module elaboration did not retain its import parameters"
  dataEnv <- D.validateDeclarations declarations
  bindings <- collectBindings dataEnv (Check.Env M.empty (M.fromList parameters)) implementation
  let payload = X.WithData declarations (foldr (uncurry X.Abs) implementation parameters)
      iface = UnitInterface name [(n,interfaceFingerprint (dependencyMap M.! n)) | n <- imported]
        (sortOn entityEncoding (Set.toList (visible exported))) ds cs
        [(n,stripInstance i) | (n,i) <- ownInstances]
        (sortOn fst [(X.nameHint n,normalType t) | (n,t) <- bindings]) (fingerprint (Pretty.prettyTerm payload))
  _ <- Check.checkClosed payload
  pure (UnitObject iface payload)
  where first3 (a,_,_) = a

stripInstance :: S.InstanceDecl -> S.InstanceDecl
stripInstance i = i { S.instanceMethods = [(n,S.App (S.Primitive P.Panic) (S.StringLit "interface method")) | (n,_) <- S.instanceMethods i] }

builtinPrelude :: Either String UnitObject
builtinPrelude = compileUnit NoImplicitPrelude [] preludeSource

collectBindings :: D.DataEnv -> Check.Env -> X.Term -> Either String [(X.Name,T.Type)]
collectBindings ds env term = case term of
  X.Let n rhs rest -> do
    ty <- Check.inferWithData ds env rhs
    ensure (Set.null (T.freeVars ty)) "module binding has an open type"
    ((n,ty):) <$> collectBindings ds env { Check.termEnv = M.insert n ty (Check.termEnv env) } rest
  X.LetRec bs rest -> do
    let entries = [(n,t) | (n,t,_) <- bs]
    ensure (all (Set.null . T.freeVars . snd) entries) "module binding has an open type"
    (entries ++) <$> collectBindings ds env { Check.termEnv = M.union (M.fromList entries) (Check.termEnv env) } rest
  X.Constructor "Unit" [] -> pure []
  _ -> Left "invalid module object: expected declarations ending in Unit"

-- Length-prefixed UTF-8-decoded strings: bounded, unambiguous, and shared with
-- the self-hosted compiler. No executable source bodies occur in interfaces.
pack :: [String] -> String
pack = concatMap (\s -> show (length s) ++ ":" ++ s)
unpack :: String -> Either String [String]
unpack "" = Right []
unpack input = case span isDigit input of
  (digits,':':rest) | not (null digits), length digits <= 9 -> do
    let n = read digits :: Int
    ensure (n <= length rest) "truncated module artifact"
    (take n rest :) <$> unpack (drop n rest)
  _ -> Left "malformed module artifact framing"

-- Change detection, not a signature or a security boundary. Objects and all
-- their schemes are independently checked even when this checksum matches.
fingerprint :: String -> String
fingerprint text = show (List.foldl' step (0 :: Integer) text) ++ "-" ++ show (List.foldl' step2 (1 :: Integer) text)
  where step h c = (h * 65599 + toInteger (ord c)) `mod` 2147483647
        step2 h c = (h * 131 + toInteger (ord c)) `mod` 2147483629

entityEncoding :: Entity -> String
entityEncoding (Entity owner' name role') = pack [owner',name,tag,argument]
  where (tag,argument) = case role' of
          Value -> ("value",""); Datatype -> ("data",""); Class -> ("class","")
          Constructor p -> ("constructor",p); Method p -> ("method",p)
          BuiltinType -> ("builtin",""); Primitive p -> ("primitive",P.primitiveName p)
          Boolean b -> ("bool",if b then "true" else "false")
decodeEntity :: String -> Either String Entity
decodeEntity text = unpack text >>= \fields -> case fields of
  [owner',name,tag,arg] -> Entity owner' name <$> case tag of
    "value" -> noArg Value arg; "data" -> noArg Datatype arg; "class" -> noArg Class arg
    "constructor" -> Right (Constructor arg); "method" -> Right (Method arg)
    "builtin" -> noArg BuiltinType arg
    "primitive" -> maybe (Left "unknown interface primitive") (Right . Primitive) (P.lookupPrimitive arg)
    "bool" | arg == "true" -> Right (Boolean True)
           | arg == "false" -> Right (Boolean False)
    _ -> Left "unknown interface entity role"
  _ -> Left "malformed interface entity"
  where noArg role' "" = Right role'; noArg _ _ = Left "unexpected entity argument"

prettySourceType :: S.Type -> String
prettySourceType ty = case ty of
  S.TVar n -> n
  S.Bottom -> "bot"
  S.BottomKind k -> "bot[" ++ prettyKind k ++ "]"
  S.Arrow a b -> "(" ++ prettySourceType a ++ " -> " ++ prettySourceType b ++ ")"
  S.TypeApp a b -> "(" ++ prettySourceType a ++ " " ++ prettySourceType b ++ ")"
  S.Con c ts -> "(" ++ unwords (c : map prettySourceType ts) ++ ")"
  S.Forall flag n bound body -> "(forall (" ++ n ++ (if flag == S.Flexible then " >= " else " > ") ++ prettySourceType bound ++ "). " ++ prettySourceType body ++ ")"
  S.Qualified ps b -> "(" ++ prettyContext ps ++ prettySourceType b ++ ")"
prettyPredicate :: S.Predicate -> String
prettyPredicate (S.Predicate c ts) = unwords (c:map prettySourceType ts)
prettyContext :: [S.Predicate] -> String
prettyContext [] = ""
prettyContext ps = "(" ++ intercalate ", " (map prettyPredicate ps) ++ ") => "
prettyParameter :: (String,Kind) -> String
prettyParameter (n,k) = "(" ++ n ++ " : " ++ prettyKind k ++ ")"
prettyClass :: S.ClassDecl -> String
prettyClass c = "class " ++ prettyContext (S.superclasses c) ++ S.className c ++ " " ++
  unwords (map prettyParameter (S.classParameters c)) ++ " where { " ++
  intercalate "; " [n ++ " : " ++ prettySourceType ty | (n,ty) <- S.classMethods c] ++ " };"
prettyInstance :: S.InstanceDecl -> String
prettyInstance i = "instance " ++ (if null (S.instanceVariables i) then "" else "forall " ++ unwords (map prettyParameter (S.instanceVariables i)) ++ ". ") ++
  prettyContext (S.instanceContext i) ++ S.instanceClass i ++ " " ++ unwords (map prettySourceType (S.instanceHead i)) ++
  " where { " ++ intercalate "; " [n ++ " = panic \"interface method\"" | (n,_) <- S.instanceMethods i] ++ " };"

interfaceFields :: UnitInterface -> [String]
interfaceFields i = ["MLFI-1",unitName i,pack [pack [n,h] | (n,h) <- unitDependencies i],
  pack (map entityEncoding (unitExports i)),
  unlines (map D.prettyDeclaration (unitData i) ++ map prettyClass (unitClasses i) ++ map (prettyInstance . snd) (unitInstances i)),
  pack (map fst (unitInstances i)),pack [pack [n,Pretty.prettyType (normalType t)] | (n,t) <- unitBindings i]]
interfaceFingerprint :: UnitInterface -> String
interfaceFingerprint = fingerprint . pack . interfaceFields
encodeInterface :: UnitInterface -> String
encodeInterface i = pack (interfaceFields i ++ [unitObjectFingerprint i])
decodeInterface :: String -> Either String UnitInterface
decodeInterface input = unpack input >>= \fields -> case fields of
  ["MLFI-1",name,deps,exports,metadata,instanceNames,bindings,objectHash] -> do
    ds <- unpack deps >>= mapM pair
    es <- unpack exports >>= mapM decodeEntity
    source <- Parser.parseModule "<module interface>" ("module InterfaceMetadata where {\n" ++ metadata ++ "\n}")
    ns <- unpack instanceNames
    bs <- unpack bindings >>= mapM (\field -> do (n,ty) <- pair field; (,) n <$> XP.parseType ty)
    ensure (length ns == length (sourceInstances source)) "interface instance count mismatch"
    ensure (null (sourceValues source) && null (sourceImports source)) "interface contains executable declarations"
    ensure (length ds == length (nub (map fst ds)) && length ns == length (nub ns) && length bs == length (nub (map fst bs))) "duplicate interface entry"
    ensure (all (Set.null . T.freeVars . snd) bs) "interface has open types"
    ensure (not (null name) && not (null objectHash)) "incomplete module interface"
    mapM_ validModuleName (name : map fst ds ++ map owner es)
    let i = UnitInterface name ds es (sourceDatatypes source) (sourceClasses source) (zip ns (map stripInstance (sourceInstances source))) bs objectHash
    ensure (encodeInterface i == input) "noncanonical module interface"
    pure i
  _ -> Left "unsupported or malformed module interface (expected MLFI-1)"
  where pair field = unpack field >>= \xs -> case xs of [a,b] -> Right (a,b); _ -> Left "malformed interface pair"

validModuleName :: String -> Either String ()
validModuleName name = do
  parsed <- Parser.parseModule "<module identity>" ("module " ++ name ++ " where {}")
  ensure (sourceModuleName parsed == Just name) "invalid compiled module identity"

encodeObject :: UnitObject -> String
encodeObject (UnitObject i term) = pack ["MLFO-1",unitName i,interfaceFingerprint i,Pretty.prettyTerm term]
decodeObject :: UnitInterface -> String -> Either String UnitObject
decodeObject i input = unpack input >>= \fields -> case fields of
  ["MLFO-1",name,abi,body] -> do
    ensure (name == unitName i) "module object name mismatch"
    ensure (abi == interfaceFingerprint i) "module object interface mismatch"
    ensure (fingerprint body == unitObjectFingerprint i) "module object checksum mismatch"
    term <- XP.parseTerm "<module object>" body
    _ <- Check.checkClosed term
    pure (UnitObject i term)
  _ -> Left "unsupported or malformed module object (expected MLFO-1)"

-- Remap every identity, including computations, before joining lexical scopes.
mapTerm :: (X.Name -> X.Name) -> (T.TyVar -> T.TyVar) -> X.Term -> X.Term
mapTerm name variable = term
  where
    ty t = case t of
      T.Var a -> T.Var (variable a); T.Arrow a b -> T.Arrow (ty a) (ty b)
      T.Con c ts -> T.Con c (map ty ts); T.Apply a b -> T.Apply (ty a) (ty b)
      T.Forall a bound b -> T.Forall (variable a) (ty bound) (ty b); _ -> t
    computation c = case c of
      X.Bottom t -> X.Bottom (ty t); X.Hyp a -> X.Hyp (variable a)
      X.Inner a -> X.Inner (computation a); X.Outer a b -> X.Outer (variable a) (computation b)
      X.Intro a -> X.Intro (variable a); X.IntroKind a k -> X.IntroKind (variable a) k
      X.Then a b -> X.Then (computation a) (computation b); _ -> c
    pattern' p = case p of
      X.ConstructorPattern c ns -> X.ConstructorPattern c (map (fmap name) ns)
      X.DefaultPattern n -> X.DefaultPattern (name <$> n)
    term t = case t of
      X.VarTerm n -> X.VarTerm (name n); X.Abs n a b -> X.Abs (name n) (ty a) (term b)
      X.App a b -> X.App (term a) (term b); X.TypeAbs a bound b -> X.TypeAbs (variable a) (ty bound) (term b)
      X.TypeApp a c -> X.TypeApp (term a) (computation c)
      X.Let n a b -> X.Let (name n) (term a) (term b)
      X.LetRec bs b -> X.LetRec [(name n,ty a,term rhs) | (n,a,rhs) <- bs] (term b)
      X.Primitive p ts -> X.Primitive p (map ty ts); X.Constructor c ts -> X.Constructor c (map ty ts)
      X.Case a t' bs -> X.Case (term a) (ty t') [X.Alternative (pattern' p) (term b) | X.Alternative p b <- bs]
      X.WithData ds b -> X.WithData ds (term b); _ -> t

freshObject :: Int -> X.Term -> (Int,X.Term)
freshObject start term = (next,mapTerm (\n -> X.Name (names M.! X.nameId n) (X.nameHint n)) (\a -> T.TyVar (types M.! T.tyVarId a)) term)
  where
    -- Traversal records identities without interpreting names or pretty text.
    (names,types,next) = execState (walk term) (M.empty,M.empty,start)
    addName n = modify (\(ns,ts,i) -> if M.member (X.nameId n) ns then (ns,ts,i) else (M.insert (X.nameId n) i ns,ts,i+1))
    addType a = modify (\(ns,ts,i) -> if M.member (T.tyVarId a) ts then (ns,ts,i) else (ns,M.insert (T.tyVarId a) i ts,i+1))
    walkType t = case t of
      T.Var a -> addType a; T.Arrow a b -> walkType a >> walkType b
      T.Con _ ts -> mapM_ walkType ts; T.Apply a b -> walkType a >> walkType b
      T.Forall a b c -> addType a >> walkType b >> walkType c; _ -> pure ()
    walkComp c = case c of
      X.Bottom t -> walkType t; X.Hyp a -> addType a; X.Inner p -> walkComp p
      X.Outer a p -> addType a >> walkComp p; X.Intro a -> addType a
      X.IntroKind a _ -> addType a; X.Then a b -> walkComp a >> walkComp b; _ -> pure ()
    walk t = case t of
      X.VarTerm n -> addName n; X.Abs n a b -> addName n >> walkType a >> walk b
      X.App a b -> walk a >> walk b; X.TypeAbs a bound b -> addType a >> walkType bound >> walk b
      X.TypeApp a c -> walk a >> walkComp c; X.Let n a b -> addName n >> walk a >> walk b
      X.LetRec bs b -> mapM_ (\(n,a,rhs) -> addName n >> walkType a >> walk rhs) bs >> walk b
      X.Primitive _ ts -> mapM_ walkType ts; X.Constructor _ ts -> mapM_ walkType ts
      X.Case a ty bs -> walk a >> walkType ty >> mapM_ (\(X.Alternative p b) -> mapM_ addName (X.patternNames p) >> walk b) bs
      X.WithData _ b -> walk b; _ -> pure ()

validateObjectBoundary :: [UnitInterface] -> UnitObject -> Either String ()
validateObjectBoundary interfaces (UnitObject iface term) = do
  deps <- closure [unitName iface] [] (map fst (unitDependencies iface))
  let allInterfaces = deps ++ [iface]
      classes = concatMap unitClasses allInterfaces
      instances = concatMap unitInstances allInterfaces
      declared = concatMap unitData allInterfaces
      (ds,inner) = case term of X.WithData ds' b -> (ds',b); _ -> ([],term)
      parameters (X.Abs n t b) = (X.nameHint n,normalType t):parameters b
      parameters _ = []
      expected = sortOn fst (concatMap unitBindings deps)
  ensure (parameters inner == expected) "module object dependency parameter mismatch"
  (program,_) <- Classes.lowerSeparateClasses M.empty (map fst instances)
    (S.ClassProgram declared classes (map snd instances) (S.Constructor "Unit"))
  expectedData <- case program of S.Program xs _ -> pure xs; _ -> Left "invalid module metadata"
  ensure (sortOn id (map D.prettyDeclaration ds) == sortOn id (map D.prettyDeclaration expectedData))
    "module object datatype interface mismatch"
  where
    byName = M.fromList [(unitName i,i) | i <- interfaces]
    closure _ done [] = Right done
    closure trail done (n:ns)
      | n `elem` trail = Left ("cyclic compiled imports: " ++ intercalate " -> " (trail ++ [n]))
      | any ((== n) . unitName) done = closure trail done ns
      | otherwise = do
          child <- maybe (Left ("missing interface: " ++ n)) pure (M.lookup n byName)
          earlier <- closure (trail ++ [n]) done (map fst (unitDependencies child))
          closure trail (earlier ++ [child]) ns

linkObjects :: [UnitObject] -> String -> Either String X.Term
linkObjects objects root = do
  ensure (not (null objects)) "no compiled modules to link"
  forM_ objects (validateObjectBoundary [i | UnitObject i _ <- objects])
  (serial,_,bindings,bodies,declarations) <- foldM add (0,M.empty,M.empty,[],[]) objects
  entry <- linkEntry serial [i | UnitObject i _ <- objects] bindings root
  body <- foldM (flip graft) entry (reverse bodies)
  let term = X.WithData declarations body
  _ <- Check.checkClosed term
  pure term
  where
    add (serial,done,available,bodies,allData) (UnitObject iface original) = do
      ensure (M.notMember (unitName iface) done) ("duplicate module object: " ++ unitName iface)
      forM_ (unitDependencies iface) $ \(n,h) -> ensure (M.lookup n done == Just h) ("stale or missing dependency interface: " ++ n)
      let (next,term) = freshObject serial original
          (ds,inner) = case term of X.WithData ds' inner' -> (ds',inner'); _ -> ([],term)
          split (X.Abs n ty rest) = let (ps,b) = split rest in ((n,ty):ps,b)
          split b = ([],b)
          (parameters,implementation) = split inner
      replacements <- forM parameters $ \(n,ty) -> do
        (actual,expected) <- maybe (Left ("unresolved module symbol: " ++ X.nameHint n)) pure (M.lookup (X.nameHint n) available)
        ensure (T.alphaEq ty expected) ("module import type mismatch: " ++ X.nameHint n)
        pure (n,actual)
      let substitution = M.fromList replacements
          linked = mapTerm (\n -> M.findWithDefault n n substitution) id implementation
      dataEnv <- D.validateDeclarations ds
      own <- collectBindings dataEnv (Check.Env M.empty (M.fromList [(n,ty) | (n,ty) <- parameters])) implementation
      let expected = M.fromList (unitBindings iface)
      ensure (sortOn fst [(X.nameHint n,normalType t) | (n,t) <- own] == M.toAscList expected) "module object export type mismatch"
      let bindings = M.fromList [(X.nameHint n,(n,t)) | (n,t) <- own]
      ensure (M.null (M.intersection available bindings)) "duplicate module symbol"
      -- Duplicate nominal declarations must be structurally identical.
      combined <- foldM (\acc d -> case filter ((== D.datatypeName d) . D.datatypeName) acc of
        [] -> pure (acc ++ [d]); [other] | D.prettyDeclaration other == D.prettyDeclaration d -> pure acc
        _ -> Left ("conflicting module datatype: " ++ D.datatypeName d)) allData ds
      _ <- Check.checkClosed original
      pure (next,M.insert (unitName iface) (interfaceFingerprint iface) done,M.union bindings available,bodies ++ [linked],combined)
    graft declarations body = case declarations of
      X.Let n a b -> X.Let n a <$> graft b body
      X.LetRec ds b -> X.LetRec ds <$> graft b body
      X.Constructor "Unit" [] -> pure body
      _ -> Left "invalid module object declaration spine"

-- Selecting main is an ordinary use of an imported scheme, including implicit
-- dictionary arguments. Elaborate only that use against interfaces; no module
-- implementation participates in this small final inference problem.
linkEntry :: Int -> [UnitInterface] -> M.Map String (X.Name,T.Type) -> String -> Either String X.Term
linkEntry serial interfaces available root = do
  ensure (M.member entryName available) ("entry module has no main binding: " ++ root)
  reachable <- closure [] [] [root]
  let classes = concatMap unitClasses reachable
      instances = concatMap unitInstances reachable
      dictionaries = M.fromList [("Dict_" ++ S.className c,S.className c) | c <- classes]
      signatures = M.fromList (concatMap unitBindings reachable)
      externals = M.mapWithKey (\n ty -> sourceScheme
        (if take 7 n == "module_" then dictionaries else M.empty) ty) signatures
      program = S.ClassProgram (concatMap unitData reachable) classes (map snd instances) (S.Var entryName)
  lowered <- Classes.lowerSeparateClasses externals (map fst instances) program
  compiled <- first show (finishCompilation lowered)
  removeParameters signatures (snd (freshObject serial (compiledTerm compiled)))
  where
    entryName = stableName (Entity root "main" Value)
    byName = M.fromList [(unitName i,i) | i <- interfaces]
    closure _ done [] = Right done
    closure trail done (n:ns)
      | n `elem` trail = Left "cyclic entry dependencies"
      | any ((== n) . unitName) done = closure trail done ns
      | otherwise = do
          child <- maybe (Left ("missing entry interface: " ++ n)) pure (M.lookup n byName)
          earlier <- closure (trail ++ [n]) done (map fst (unitDependencies child))
          closure trail (earlier ++ [child]) ns
    removeParameters signatures t = case t of
      X.WithData _ b -> removeParameters signatures b
      X.TypeAbs a bound b -> X.TypeAbs a bound <$> removeParameters signatures b
      X.TypeApp b p -> (`X.TypeApp` p) <$> removeParameters signatures b
      X.LetRec bs b -> do
        ensure (map (\(n,_,_) -> X.nameHint n) bs == M.keys signatures) "entry parameter mismatch"
        replacements <- forM bs $ \(n,ty,_) -> do
          (actual,expected) <- maybe (Left ("missing entry symbol: " ++ X.nameHint n)) pure (M.lookup (X.nameHint n) available)
          ensure (T.alphaEq ty expected) ("entry parameter type mismatch: " ++ X.nameHint n)
          pure (n,actual)
        let substitution = M.fromList replacements
        pure (mapTerm (\n -> M.findWithDefault n n substitution) id b)
      _ -> Left "entry elaboration did not retain its import parameters"

readStrict :: FilePath -> IO (Either String String)
readStrict path = do
  r <- try (readFile path >>= \s -> evaluate (length s) >> pure s) :: IO (Either IOException String)
  pure (first show r)

-- Graph loading reads only .mlfi files. Objects are opened exclusively by the
-- linker; -c therefore works even when dependency source and objects are absent.
loadInterfaces :: [FilePath] -> [String] -> IO (Either String [(FilePath,UnitInterface)])
loadInterfaces paths roots = visitMany [] [] roots
  where
    visitMany _ done [] = pure (Right done)
    visitMany trail done (n:ns)
      | elem n trail = pure (Left ("cyclic compiled imports: " ++ intercalate " -> " (trail ++ [n])))
      | any ((== n) . unitName . snd) done = visitMany trail done ns
      | n == "Prelude" = case builtinPrelude of
          Left e -> pure (Left e)
          Right (UnitObject i _) -> visitMany trail (done ++ [("<Prelude>",i)]) ns
      | otherwise = do
          found <- findInterface [p </> map (\c -> if c == '.' then '/' else c) n ++ ".mlfi" | p <- paths]
          case found of
            Left e -> pure (Left e)
            Right path -> do
              input <- readStrict path
              case input >>= decodeInterface of
                Left e -> pure (Left (path ++ ": " ++ e))
                Right i | unitName i /= n -> pure (Left (path ++ ": expected interface for " ++ n))
                Right i -> do
                  children <- visitMany (trail ++ [n]) done (map fst (unitDependencies i))
                  case children >>= \xs -> validateDependencies xs i >> pure xs of
                    Left e -> pure (Left e)
                    Right xs -> visitMany trail (xs ++ [(path,i)]) ns
    findInterface [] = pure (Left "cannot find compiled module interface; compile dependencies first or add -i DIR")
    findInterface (p:ps) = doesFileExist p >>= \present -> if present then pure (Right p) else findInterface ps

validateDependencies :: [(FilePath,UnitInterface)] -> UnitInterface -> Either String ()
validateDependencies dependencies iface = forM_ (unitDependencies iface) $ \(n,h) ->
  ensure (lookup n [(unitName i,interfaceFingerprint i) | (_,i) <- dependencies] == Just h)
    ("stale dependency interface: " ++ unitName iface ++ " requires a different " ++ n ++ "; recompile " ++ unitName iface)

searchRoots :: [FilePath] -> FilePath -> String -> [FilePath]
searchRoots includes file name = nub (directory:includes ++ [hierarchy,"."])
  where directory = takeDirectory file
        hierarchy = iterate takeDirectory directory !! length (filter (== '.') name)

compileModuleFile :: PreludeMode -> [FilePath] -> FilePath -> FilePath -> IO (Either String ())
compileModuleFile mode includes source prefix = do
  input <- readStrict source
  case input >>= Parser.parseModule source of
    Left e -> pure (Left e)
    Right root -> do
      loaded <- loadInterfaces (searchRoots includes source (moduleIdentity root)) (nub (map importedModule (importsFor mode root)))
      case loaded >>= \deps -> compileUnit mode (map snd deps) root of
        Left e -> pure (Left e)
        Right object@(UnitObject iface _) -> do
          -- Publishing the interface last makes interrupted or mismatched pairs
          -- fail checksum validation rather than silently link stale code.
          result <- try $ do
            createDirectoryIfMissing True (takeDirectory prefix)
            writeFile (prefix ++ ".mlfo.tmp") (encodeObject object)
            renameFile (prefix ++ ".mlfo.tmp") (prefix ++ ".mlfo")
            writeFile (prefix ++ ".mlfi.tmp") (encodeInterface iface)
            renameFile (prefix ++ ".mlfi.tmp") (prefix ++ ".mlfi")
          pure (first (show :: IOException -> String) result)

linkModuleFile :: [FilePath] -> FilePath -> IO (Either String X.Term)
linkModuleFile includes path = do
  input <- readStrict path
  case input >>= decodeInterface of
    Left e -> pure (Left e)
    Right root -> do
      loaded <- loadInterfaces (searchRoots includes path (unitName root)) (map fst (unitDependencies root))
      case loaded >>= \deps -> validateDependencies deps root >> pure (deps ++ [(path,root)]) of
        Left e -> pure (Left e)
        Right interfaces -> do
          objects <- forM interfaces $ \(file,i) -> if file == "<Prelude>" then pure builtinPrelude else do
            object <- readStrict (dropExtension file ++ ".mlfo")
            pure (object >>= decodeObject i)
          pure (sequence objects >>= \os -> linkObjects os (unitName root))

showInterfaceFile :: FilePath -> IO (Either String String)
showInterfaceFile path = do
  input <- readStrict path
  pure $ do
    i <- input >>= decodeInterface
    let names = M.fromList [(stableName e,label e) | e <- unitExports i]
    pure (unlines (["module " ++ unitName i,"interface " ++ interfaceFingerprint i] ++
      ["import " ++ n ++ " " ++ h | (n,h) <- unitDependencies i] ++
      [label e ++ " : " ++ displayNames names (Pretty.prettyType ty) |
        e <- unitExports i, role e == Value, Just ty <- [lookup (stableName e) (unitBindings i)]]))
