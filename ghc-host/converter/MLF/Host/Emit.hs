module MLF.Host.Emit (emitModule, moduleValues) where

import Control.Monad.State.Strict
import Data.Char (isLower, isAlphaNum, ord)
import Data.List (intercalate, nub)
import qualified Data.Map.Strict as M
import MLF.Host.Lexer (Token, line)
import MLF.Host.Syntax

type Env = M.Map String String
type Emit = StateT Int (Either String)

-- Generated local names cannot coincide with source names (all source values
-- have the v_ prefix). Ordinary let RHSs use the previous environment.
fresh :: String -> Emit String
fresh hint = do
  i <- get
  put (i+1)
  pure ("local_"++show i++"_"++escape hint)

escape :: String -> String
escape = concatMap (\c -> if isAlphaNum c || c=='\'' then [c] else "_u"++show (ord c)++"_")

valueName :: String -> String
valueName n = case breakLastDot n of
  (prefix,base) -> prefix ++ if not (null base) && isLower (head base) then "v_"++escape base else base

breakLastDot :: String -> (String,String)
breakLastDot s = case break (=='.') (reverse s) of
  (_,[]) -> ("",s)
  (suffix,_:pre) -> (reverse pre++".",reverse suffix)

typeName :: String -> String
typeName n | not (null n) && isLower (head n) = "t_"++escape n
           | otherwise = n

emitType :: Type -> String
emitType t = case t of
  TyName n -> typeName n
  TyApp a b -> "("++emitType a++" "++emitType b++")"
  TyArrow a b -> "("++emitType a++" -> "++emitType b++")"
  TyForall vs b -> "(forall "++unwords (map emitParameter vs)++". "++emitType b++")"
  TyContext ps b -> "(("++intercalate "," (map emitType ps)++") => "++emitType b++")"
emitKind :: Kind -> String
emitKind Star = "*"
emitKind (KArrow a b) = "("++emitKind a++" -> "++emitKind b++")"
emitParameter :: (String,Maybe Kind) -> String
emitParameter (n,Nothing) = typeName n
emitParameter (n,Just k) = "("++typeName n++" :: "++emitKind k++")"

moduleValues :: [Module] -> Module -> [String]
moduleValues modules (Module _ exports imports declarations) = case exports of
  Nothing -> declared
  Just xs -> nub (concatMap exported xs)
  where declared=concatMap declValues declarations
        exported (ValueExport n) = [n]
        exported (TypeExport _ (Just members)) = filter (\n -> not (null n) && isLower (head n)) members
        exported (ModuleExport n) = imported n
        exported _ = []
        imported n = concatMap (moduleValues modules) [m | m@(Module name _ _ _) <- modules, name==n]
declValues :: Decl -> [String]
declValues (Signature _ n _) = [n]
declValues (Equation _ n _ _ _) = [n]
declValues (Class _ _ _ _ ms) = map fst ms
declValues _ = []

emitModule :: [Module] -> FilePath -> Maybe String -> Module -> Either String String
emitModule modules file override (Module name exports imports declarations) = evalStateT body 0
  where body = do
          ds <- mapM (emitDecl file M.empty) declarations
          pure $ unlines
            ["{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, ScopedTypeVariables, ViewPatterns #-}",
             "-- Generated from "++file++"; edit the .emlf source or host converter.",
             "module "++maybe name id override++maybe "" (\xs -> " ("++intercalate ", " (map emitExport xs)++")") exports++" where",
             if any (\(Import _ n _ _) -> n=="Prelude") imports then "" else "import MLF.Host.Primitives"++hidingText,
             "import qualified MLF.Host.Primitives as Host",
             unlines (map emitImport imports),unlines ds]
        shadowed=nub (concatMap declValues declarations++concatMap imported imports)
        hidingText=if null shadowed then "" else " hiding ("++intercalate "," (map valueName shadowed)++")"
        imported (Import True _ _ _) = []
        imported (Import _ "Prelude" _ _) = []
        imported (Import _ n _ selection) =
          let available=concatMap (moduleValues modules) [m | m@(Module name _ _ _) <- modules, name==n]
              selected xs=[v | ValueExport v <- xs]
          in case selection of
            Nothing -> available
            Just (False,xs) -> selected xs
            Just (True,xs) -> filter (`notElem` selected xs) available

emitExport :: Export -> String
emitExport e = case e of
  ValueExport n -> valueName n
  TypeExport n members -> n++maybe "" (\xs -> "("++intercalate "," (map valueName xs)++")") members
  ModuleExport n -> "module "++n
emitImport :: Import -> String
emitImport (Import q n alias selection) = "import "++(if q then "qualified " else "")++(if n=="Prelude" then "MLF.Host.Primitives" else n)++maybe "" (" as "++) alias++
  maybe "" (\(h,xs) -> (if h then " hiding " else " ")++"("++intercalate "," (map emitExport xs)++")") selection
location :: FilePath -> Token -> String
location file t = "{-# LINE "++show (line t)++" "++show file++" #-}\n"
emitDecl :: FilePath -> Env -> Decl -> Emit String
emitDecl file env d = case d of
  Signature t n ty -> pure (location file t++resolve env n++" :: "++emitType ty)
  Equation t n ps annotation e -> do
    (patterns,bodyEnv) <- patternsIn env ps
    body <- emitExpr bodyEnv e
    pure (location file t++maybe "" (\ty -> resolve env n++" :: "++emitType ty++"\n") annotation++resolve env n++" "++unwords patterns++" = "++body)
  Data t n vs cs -> pure (location file t++"data "++n++" "++unwords (map emitParameter vs)++" = "++intercalate " | " [c++" "++unwords (map emitType fields) | (c,fields)<-cs])
  Class t ctx n vs ms -> pure (location file t++"class "++contextText ctx++n++" "++unwords (map emitParameter vs)++" where { "++intercalate "; " [valueName m++" :: "++emitType ty | (m,ty)<-ms]++" }")
  Instance t vs ctx n ts ds -> do
    methods <- mapM (emitDeclInline env) ds
    pure (location file t++"instance "++(if null vs then "" else "forall "++unwords (map emitParameter vs)++". ")++contextText ctx++n++" "++unwords (map emitType ts)++" where { "++intercalate "; " methods++" }")
contextText :: [Type] -> String
contextText [] = ""
contextText xs = "("++intercalate "," (map emitType xs)++") => "
resolve :: Env -> String -> String
resolve env n = case n of
  "$neInt" -> "Host.neInt"
  "$leInt" -> "Host.leInt"
  "$gtInt" -> "Host.gtInt"
  "$geInt" -> "Host.geInt"
  _ -> M.findWithDefault (valueName n) n env

emitDeclInline :: Env -> Decl -> Emit String
emitDeclInline env d = case d of
  Signature _ n ty -> pure (resolve env n++" :: "++emitType ty)
  Equation _ n ps ty e -> do
    (patterns,bodyEnv) <- patternsIn env ps
    body <- emitExpr bodyEnv e
    pure (maybe "" (\a -> resolve env n++" :: "++emitType a++"; ") ty++resolve env n++" "++unwords patterns++" = "++body)
  _ -> lift (Left "local declarations must be value bindings")

patternsIn :: Env -> [Pattern] -> Emit ([String],Env)
patternsIn env ps = do
  pairs <- mapM (\n -> (,) n <$> fresh n) (concatMap patVars ps)
  let next=M.union (M.fromList pairs) env
  pure (map (emitPattern next) ps,next)

emitPattern :: Env -> Pattern -> String
emitPattern env p = case p of
  PVar n -> resolve env n
  PWild -> "_"
  PAnn n ty -> "("++resolve env n++" :: "++emitType ty++")"
  PCon c ps -> "("++valueName c++concatMap ((" "++).emitPattern env) ps++")"
  PLit (LBool b) -> show b
  PLit (LInteger n) -> "("++n++")"
  PLit (LString s) -> "(Host.matchString "++s++" -> True)"
  PLit (LDouble _) -> error "Double patterns are outside the implementation dialect"

emitLiteral :: Literal -> String
emitLiteral l = case l of
  LBool b -> show b
  LInteger n -> "("++n++" :: Int)"
  LDouble n -> "("++n++" :: Double)"
  LString s -> "(Host.literal "++s++")"

emitExpr :: Env -> Expr -> Emit String
emitExpr env expression = case expression of
  Var n -> pure (resolve env n)
  Lit l -> pure (emitLiteral l)
  App f x -> do
    a <- emitExpr env f
    b <- emitExpr env x
    pure ("("++a++" "++b++")")
  Lambda ps b -> do
    (patterns,next) <- patternsIn env ps
    body <- emitExpr next b
    pure ("(\\"++unwords patterns++" -> "++body++")")
  Case a branches -> do
    value <- emitExpr env a
    bs <- mapM (\(p,b) -> do
      (patterns,next) <- patternsIn env [p]
      body <- emitExpr next b
      pure (unwords patterns++" -> "++body)) branches
    pure ("(case "++value++" of { "++intercalate "; " bs++" })")
  If a b c -> do
    condition <- emitExpr env a
    yes <- emitExpr env b
    no <- emitExpr env c
    pure ("(if "++condition++" then "++yes++" else "++no++")")
  Let recursive ds b -> emitLet env recursive ds (\next -> emitExpr next b)
  Do ss -> emitDo env ss
  Ann e ty -> do
    value <- emitExpr env e
    pure ("("++value++" :: "++emitType ty++")")

-- Contiguous equations belong to one binding. A signature belongs to the
-- following binding and is preserved, including recursive closed signatures.
groups :: [Decl] -> Either String [[Decl]]
groups [] = Right []
groups (s@(Signature _ n _):rest) = case rest of
  Equation _ m _ _ _:more | n==m -> do
    gs <- groups rest
    case gs of
      g:others -> pure ((s:g):others)
      [] -> Left "signature without definition"
  _ -> Left ("signature without matching definition: "++n)
groups (d@(Equation _ n _ _ _):rest) = do
  let (same,after)=span (\a -> case a of { Equation _ m _ _ _ -> n==m; _ -> False }) rest
  ((d:same):) <$> groups after
groups _ = Left "invalid local declaration"
groupName :: [Decl] -> String
groupName (Signature _ n _:_) = n
groupName (Equation _ n _ _ _:_) = n
groupName _ = error "empty declaration group"

emitLet :: Env -> Bool -> [Decl] -> (Env -> Emit String) -> Emit String
emitLet env recursive ds continuation = do
  gs <- lift (groups ds)
  if recursive then do
    pairs <- mapM (\g -> (,) (groupName g) <$> fresh (groupName g)) gs
    let next=M.union (M.fromList pairs) env
    declarations <- mapM (emitDeclInline next) ds
    body <- continuation next
    pure ("(let { "++intercalate "; " declarations++" } in "++body++")")
  else sequential env gs
  where sequential current [] = continuation current
        sequential current (g:rest) = do
          let n=groupName g
          renamed <- fresh n
          -- Only the LHS changes. The RHS does not see its own binding.
          declarations <- mapM (nonrecDecl current n renamed) g
          body <- sequential (M.insert n renamed current) rest
          pure ("(let { "++intercalate "; " declarations++" } in "++body++")")
        nonrecDecl current n renamed d = case d of
          Signature _ _ ty -> pure (renamed++" :: "++emitType ty)
          Equation _ _ ps ty e -> do
            (patterns,next) <- patternsIn current ps
            rhs <- emitExpr next e
            pure (maybe "" (\a -> renamed++" :: "++emitType a++"; ") ty++renamed++" "++unwords patterns++" = "++rhs)
          _ -> lift (Left ("invalid nonrecursive declaration "++n))

emitDo :: Env -> [Statement] -> Emit String
emitDo env [Then e] = emitExpr env e
emitDo env (Then e:rest) = do
  action <- emitExpr env e
  body <- emitDo env rest
  pure ("("++resolve env "bind"++" "++action++" (\\_ -> "++body++"))")
emitDo env (Bind p e:rest) = do
  action <- emitExpr env e
  (patterns,next) <- patternsIn env [p]
  body <- emitDo next rest
  pure ("("++resolve env "bind"++" "++action++" (\\"++unwords patterns++" -> "++body++"))")
emitDo env (Local rec ds:rest) = emitLet env rec ds (\next -> emitDo next rest)
emitDo _ _ = lift (Left "do block must end in an expression")
