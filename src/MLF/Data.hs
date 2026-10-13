-- | Closed, nominal algebraic declarations shared by the source and target.
-- Fields may quantify variables, including higher-kinded variables. Data
-- parameters may also be instantiated with polymorphic types by MLF.
module MLF.Data
  ( Field (..), ConstructorDecl (..), DataDecl (..), DataEnv
  , emptyDataEnv, validateDeclarations, lookupConstructor, lookupDatatype
  , datatypeName, datatypeParameters, datatypeBinders, datatypeConstructors
  , constructorKind, withKinds, checkArity, checkAlternatives, prettyDeclaration
  ) where

import Control.Monad (foldM, forM_, unless, when)
import Data.Char (isAlphaNum, isLower, isUpper)
import Data.List (intercalate, nub)
import qualified Data.Map.Strict as Map
import MLF.Kind

data Field
  = Parameter String
  | Function Field Field
  | Applied String [Field]
  | Application Field Field
  | Quantified String Kind Field
  deriving (Eq, Show)

data ConstructorDecl = ConstructorDecl
  { constructorName :: String
  , constructorFields :: [Field]
  } deriving (Eq, Show)

data DataDecl = DataDecl String [String] [ConstructorDecl]
              | DataDeclK String [(String, Kind)] [ConstructorDecl]
  deriving (Eq, Show)

datatypeName :: DataDecl -> String
datatypeName (DataDecl n _ _) = n
datatypeName (DataDeclK n _ _) = n
datatypeParameters :: DataDecl -> [String]
datatypeParameters = map fst . datatypeBinders
datatypeBinders :: DataDecl -> [(String, Kind)]
datatypeBinders (DataDecl _ ps _) = [(p,Star) | p <- ps]
datatypeBinders (DataDeclK _ ps _) = ps
datatypeConstructors :: DataDecl -> [ConstructorDecl]
datatypeConstructors (DataDecl _ _ cs) = cs
datatypeConstructors (DataDeclK _ _ cs) = cs

data DataEnv = DataEnv (Map.Map String DataDecl)
                      (Map.Map String (DataDecl, ConstructorDecl))
                      (Map.Map String Kind) deriving Show

emptyDataEnv :: DataEnv
emptyDataEnv = withKinds []

primitiveKinds :: Map.Map String Kind
primitiveKinds = Map.fromList
  [("Int",Star),("Double",Star),("Bool",Star),("String",Star),("Unit",Star),
   ("IntArray",Star),("DoubleArray",Star),("ByteArray",Star),("IntTable",Star),("IO",KArrow Star Star),
   ("ST",KArrow Star (KArrow Star Star)),("STArray",KArrow Star (KArrow Star Star))]

unitDeclaration :: DataDecl
unitDeclaration = DataDecl "Unit" [] [ConstructorDecl "Unit" []]

withKinds :: [(String,Kind)] -> DataEnv
withKinds ks = DataEnv (Map.singleton "Unit" unitDeclaration)
  (Map.singleton "Unit" (unitDeclaration,ConstructorDecl "Unit" []))
  (Map.union primitiveKinds (Map.fromList ks))

lookupDatatype :: DataEnv -> String -> Either String DataDecl
lookupDatatype (DataEnv ds _ _) n = maybe (Left ("unknown data type: " ++ n)) Right (Map.lookup n ds)

lookupConstructor :: DataEnv -> String -> Either String (DataDecl, ConstructorDecl)
lookupConstructor (DataEnv _ cs _) n = maybe (Left ("unknown data constructor: " ++ n)) Right (Map.lookup n cs)

constructorKind :: DataEnv -> String -> Int -> Kind
constructorKind (DataEnv _ _ ks) n fallback
  | Just k <- Map.lookup n primitiveKinds = k
  | otherwise = Map.findWithDefault (foldr KArrow Star (replicate fallback Star)) n ks

-- Abstract constructor types remain available in annotations, as in the core
-- language. Declared data types and the primitive types have fixed arities.
checkArity :: DataEnv -> String -> Int -> Either String ()
checkArity (DataEnv ds _ _) n actual = case arity of
  Just expected -> unless (actual == expected)
    (Left ("invalid type constructor arity: " ++ n ++ " expects " ++ show expected ++ ", got " ++ show actual))
  Nothing -> pure ()
  where
    arity | Just k <- Map.lookup n primitiveKinds = Just (kindArity k)
          | otherwise = length . datatypeParameters <$> Map.lookup n ds
    kindArity Star = 0
    kindArity (KArrow _ k) = 1 + kindArity k

validateDeclarations :: [DataDecl] -> Either String DataEnv
validateDeclarations ds = do
  distinct "data type" (map datatypeName ds)
  distinct "data constructor" [constructorName c | d <- ds, c <- datatypeConstructors d]
  let declarations = unitDeclaration : ds
      env = DataEnv (Map.fromList [(datatypeName d,d) | d <- declarations])
            (Map.fromList [(constructorName c,(d,c)) | d <- declarations, c <- datatypeConstructors d])
            (Map.union primitiveKinds (Map.fromList [(datatypeName d,foldr (KArrow . snd) Star (datatypeBinders d)) | d <- ds]))
  forM_ ds $ \d -> do
    upper "data type" (datatypeName d)
    when (Map.member (datatypeName d) primitiveKinds) (Left "cannot redefine a primitive type")
    when (datatypeName d `elem` ["True", "False"]) (Left "reserved data type name")
    distinct "type parameter" (datatypeParameters d)
    forM_ (datatypeParameters d) $ \p ->
      unless (identifier isLower p && p `notElem` keywords) (Left ("invalid type parameter: " ++ p))
    when (null (datatypeConstructors d)) (Left ("data type has no constructors: " ++ datatypeName d))
    forM_ (datatypeConstructors d) $ \c -> do
      upper "data constructor" (constructorName c)
      when (constructorName c `elem` ["True", "False", "Unit"]) (Left "cannot redefine a primitive constructor")
      forM_ (constructorFields c) $ \t -> do
        k <- field env (Map.fromList (datatypeBinders d)) t
        unless (k == Star) (Left "constructor field must have kind *")
  pure env
  where
    field env ps t = case t of
      Parameter p -> maybe (Left ("unbound data type parameter: " ++ p)) Right (Map.lookup p ps)
      Function a b -> do
        a' <- field env ps a
        b' <- field env ps b
        unless (a' == Star && b' == Star) (Left "function fields require kind * arguments")
        pure Star
      Applied c args -> do
        unless (Map.member c primitiveKinds || c `elem` map datatypeName ds)
          (Left ("unknown field type: " ++ c))
        let arity Star = 0
            arity (KArrow _ k) = 1 + arity k
        when (length args > arity (constructorKind env c 0)) (checkArity env c (length args))
        ks <- mapM (field env ps) args
        foldM applyKind (constructorKind env c (length args)) ks
      Application a b -> do
        ka <- field env ps a
        kb <- field env ps b
        applyKind ka kb
      Quantified a k body -> field env (Map.insert a k ps) body
    upper what n = unless (identifier isUpper n) (Left ("invalid " ++ what ++ " name: " ++ n))
    identifier first (c:cs) = first c && all (\x -> isAlphaNum x || x `elem` "_'") cs
    identifier _ [] = False
    keywords = ["data", "class", "instance", "where", "case", "of", "do", "let", "in", "forall", "exists", "true", "false", "bot"]

distinct :: String -> [String] -> Either String ()
distinct what xs = unless (length xs == length (nub xs)) (Left ("duplicate " ++ what))

-- Nothing denotes a wildcard or variable alternative. Return the datatype
-- determined by constructor patterns, if any. Used independently at both
-- typing boundaries; body and binder typing are checked by their own systems.
checkAlternatives :: DataEnv -> [(Maybe String, Int)] -> Either String (Maybe DataDecl)
checkAlternatives env alternatives = do
  when (null alternatives) (Left "case has no alternatives")
  let names = [c | (Just c,_) <- alternatives]
      defaults = [i | (i,(Nothing,_)) <- zip [0 :: Int ..] alternatives]
  distinct "constructor alternative" names
  unless (null defaults || defaults == [length alternatives - 1])
    (Left "a default alternative must be last and unique")
  owners <- mapM owner [(c,n) | (Just c,n) <- alternatives]
  case owners of
    [] -> pure Nothing
    d:rest -> do
      unless (all ((== datatypeName d) . datatypeName) rest)
        (Left "case patterns belong to different data types")
      let missing = filter (`notElem` names) (map constructorName (datatypeConstructors d))
      when (null defaults && not (null missing))
        (Left ("non-exhaustive case; missing: " ++ intercalate ", " missing))
      pure (Just d)
  where
    owner (c,n) = do
      (d,ctor) <- lookupConstructor env c
      unless (n == length (constructorFields ctor))
        (Left ("constructor pattern arity mismatch: " ++ c))
      pure d

prettyDeclaration :: DataDecl -> String
prettyDeclaration d = "data " ++ unwords (datatypeName d : map parameter (datatypeBinders d)) ++
  " = " ++ intercalate " | " (map constructor (datatypeConstructors d)) ++ ";"
  where
    constructor c = unwords (constructorName c : map (field 2) (constructorFields c))
    parameter (n,Star) = n
    parameter (n,k) = "(" ++ n ++ " : " ++ prettyKind k ++ ")"
    field :: Int -> Field -> String
    field p f = case f of
      Parameter a -> a
      Applied c [] -> c
      Applied c args -> par (p > 1) (unwords (c : map (field 2) args))
      Function a b -> par (p > 0) (field 1 a ++ " -> " ++ field 0 b)
      Application a b -> par (p > 1) (field 1 a ++ " " ++ field 2 b)
      Quantified n k b -> par (p > 0) ("forall " ++ parameter (n,k) ++ ". " ++ field 0 b)
    par True s = "(" ++ s ++ ")"
    par False s = s
