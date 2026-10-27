module Migrate (migrateModule, reportTSV, report, Stats(..), moduleValues, stringsIn, stringPatterns, sameAST, astShape, renderDeclaration) where

import Prelude hiding ((<>))
import Control.Monad (when, unless, forM, forM_, replicateM, foldM)
import Control.Monad.State.Strict
import Data.Char (isLower, isSpace)
import Data.List (nub, intercalate, isPrefixOf)
import qualified Data.Map.Strict as M
import qualified Data.Set as S
import Text.PrettyPrint
import MLF.Host.Lexer (Token(..))
import MLF.Host.Syntax
import Hierarchy (standardHierarchy)
import LiteralSignatures (literalSignatures)
import MLF.Host.Parser (parseModule)

-- This is an offline, one-time migration. The output is authoritative source;
-- no compiler, package build, or test runner depends on this module.
data Stats = Stats { nextName :: Int, usedNames :: S.Set String,
  counters :: M.Map String Int, events :: [String] } deriving Show
type Transform = StateT Stats (Either String)
type Env = M.Map String String

tick n = modify (\s -> s { counters = M.insertWith (+) n 1 (counters s) })
record s = modify (\st -> st { events = s : events st })
failT = lift . Left
fresh hint = do
  s <- get
  let candidates = [hint++"Shared"++show i | i <- [nextName s..]]
      n = head (filter (`S.notMember` usedNames s) candidates)
  put s { nextName = nextName s+1, usedNames = S.insert n (usedNames s) }
  tick "fresh_names"
  pure n
report s = intercalate "\n" (reverse (events s))
reportTSV s = intercalate "\t" [k++"="++show n | (k,n) <- M.toAscList (counters s)]
resolve env n = M.findWithDefault n n env

hooks = words "fromInteger fromRational fromString negate ifThenElse otherwise"
keywords = words "case class data default deriving do else foreign if import in infix infixl infixr instance let module newtype of then type where forall exists rec"
-- Contextual Haskell keywords are conservatively renamed when bound.
unsafeName n = n `elem` hooks || n `elem` keywords

-- Lexical free names use the original sequential/nonrecursive MLF scope.
free e = case e of
  Var n -> S.singleton n
  Lit _ -> S.empty
  App a b -> free a `S.union` free b
  Lambda ps b -> free b S.\\ S.fromList (concatMap patVars ps)
  Case a bs -> free a `S.union` S.unions [free b S.\\ S.fromList (patVars p) | (p,b) <- bs]
  If a b c -> S.unions (map free [a,b,c])
  Let rec ds b -> freeDecls rec ds (free b)
  Do ss -> freeDo ss
  Ann a _ -> free a
freeDecl d = case d of
  Equation _ _ ps _ b -> free b S.\\ S.fromList (concatMap patVars ps)
  _ -> S.empty
freeDecls rec ds continuation
  | rec = (S.unions (map freeDecl ds) `S.union` continuation) S.\\ S.fromList (map declName ds)
  | otherwise = foldr (\g rest -> S.unions (map freeDecl g) `S.union` S.delete (groupName g) rest) continuation (either error id (groups ds))
freeDo [] = S.empty
freeDo (Then e:ss) = free e `S.union` freeDo ss
freeDo (Bind p e:ss) = free e `S.union` (freeDo ss S.\\ S.fromList (patVars p))
freeDo (Local rec ds:ss) = freeDecls rec ds (freeDo ss)

declName d = case d of
  Signature _ n _ -> n
  Equation _ n _ _ _ -> n
  Data _ n _ _ -> n
  Class _ _ n _ _ -> n
  Instance {} -> ""
groupName = declName . head

groups [] = Right []
groups (s@(Signature _ n _):rest) = case rest of
  Equation _ m _ _ _:_ | n==m -> do
    gs <- groups rest
    case gs of { g:more -> pure ((s:g):more); _ -> Left "signature without equation" }
  _ -> Left ("signature without matching definition: "++n)
groups (d@(Equation _ n _ _ _):rest) = do
  let (same,after) = span (\x -> case x of { Equation _ m _ _ _ -> n==m; _ -> False }) rest
  ((d:same):) <$> groups after
groups _ = Left "invalid local declaration"

-- Module exports are resolved through the finite acyclic closed inventory.
moduleValues modules (Module _ ex im ds) = case ex of
  Nothing -> nub (concatMap declared ds)
  Just xs -> nub (concatMap exported xs)
  where
    declared d = case d of
      Signature _ n _ -> [n]
      Equation _ n _ _ _ -> [n]
      Class _ _ _ _ ms -> map fst ms
      _ -> []
    exported e = case e of
      ValueExport n -> [n]
      TypeExport _ (Just ns) -> filter (\n -> not (null n) && isLower (head n)) ns
      ModuleExport n -> concatMap (moduleValues modules) [m | m@(Module name _ _ _) <- modules, name==n]
      _ -> []
importedValues modules (Import q n _ selection)
  | q = []
  | otherwise = case selection of
      Nothing -> available
      Just (False,xs) -> filter (`elem` selected xs) available
      Just (True,xs) -> filter (`notElem` selected xs) available
  where available = concatMap (moduleValues modules) [m | m@(Module name _ _ _) <- modules,name==n]
        selected xs = [v | ValueExport v <- xs] ++ concat [vs | TypeExport _ (Just vs) <- xs]

-- Existing syntax hooks are never renamed by text substitution. Only a
-- resolved reference to Bootstrap.Std.negate changes to negateInt.
initialEnv modules (Module name _ imports ds) = M.fromList (global++imported++qualified++[("$negateDouble",if name=="Bootstrap.Std" then "negateDouble" else "SharedSyntax.negateDouble")])
  where global = [(n,if name=="Bootstrap.Std" && n=="negate" then "negateInt" else n) | n <- map declName ds]
        imported = [("negate","negateInt") | name/="Bootstrap.Std", any (elem "negate" . importedValues modules) imports, "negate" `notElem` map declName ds]
        qualified = [(prefix++".negate",prefix++".negateInt") | Import _ "Bootstrap.Std" alias _ <- imports, prefix <- [maybe "Bootstrap.Std" id alias]]

migrateModule modules primitives originalTokens sourceText file newName original@(Module oldName exports imports ds) = do
  let initial=Stats 1 (S.fromList (map spelling originalTokens)) M.empty []
      env=initialEnv modules original
  (newDs,st) <- runStateT (mapTop env ds >>= addDoubleHelper oldName) initial
  let hasNegative = M.findWithDefault 0 "negative_double_literals" (counters st)>0
      doubleAlias = "SharedSyntax"
      newImports = [renameImport i | i@(Import _ n _ _) <- imports, n/="Prelude", n/="MLF.Primitive"] ++
        [Import True "Bootstrap.Std" (Just doubleAlias) Nothing | hasNegative && oldName/="Bootstrap.Std"]
      shadows = nub (concatMap declValues ds ++ concatMap (importedValues modules) imports)
      hidden = filter (\n -> n `elem` primitives && n `notElem` hooks) shadows
      facade = Import False "MLF.Primitive" Nothing (if null hidden then Nothing else Just (True,map ValueExport hidden))
      newExports = fmap (map (renameExport (oldName=="Bootstrap.Std"))) exports
      output = Module newName newExports (facade:newImports) newDs
  when (M.findWithDefault 0 "string_pattern_matrices" (counters st)>0 && any (`elem` hidden) ["eqString","eqInt"]) (Left ("literal matrix requires unhidden fixed primitive equality: "++file))
  when (hasNegative && "SharedSyntax" `S.member` usedNames initial) (Left ("reserved migration helper alias already used: "++file))
  standard <- standardHierarchy (map spelling originalTokens) output
  annotated <- addLiteralSignatures standard
  let count=length [() | Instance _ _ _ "Monad" _ ms <- ds, Equation _ "bind" _ _ _ <- ms]
      latest=st { counters=M.insert "standard_monad_instances" count (counters st) }
  pure (renderModule sourceText annotated,latest,annotated)
  where
    declValues d = case d of { Signature _ n _ -> [n]; Equation _ n _ _ _ -> [n]; Class _ _ _ _ ms -> map fst ms; _ -> [] }
    renameImport (Import q n a xs) = Import q n a (fmap (\(h,es) -> (h,map (renameExport (n=="Bootstrap.Std")) es)) xs)
    renameExport ren e = case e of { ValueExport "negate" | ren -> ValueExport "negateInt"; _ -> e }

-- These signatures were selected from the actual whole-corpus GHC type dump,
-- not guessed or applied as a blanket defaulting rule. New frontend helpers not
-- present in an older frozen preimage are naturally absent from that proposal.
addLiteralSignatures (Module name exports imports ds) = do
  let present=[n | Signature _ n _ <- ds]
      wanted=[(n,ty) | (owner,n,ty) <- literalSignatures, owner==name, n `notElem` present]
  types <- forM wanted $ \(n,sourceType) -> do
    parsed <- parseModule "literal-signature" ("module Annotation where { "++n++" :: "++sourceType++"; "++n++" = "++n++" }")
    case parsed of
      Module _ _ _ (Signature _ _ ty:_) -> pure (n,ty)
      _ -> Left ("invalid reviewed literal signature: "++n)
  let add d@(Equation tok n _ _ _) = case lookup n types of
        Just ty -> [Signature tok n ty,d]
        Nothing -> [d]
      add d = [d]
      go []=[]
      go (d@Equation{}:rest) =
        let (same,after)=span (\x -> case x of {Equation{} -> declName x==declName d; _ -> False}) rest
        in add d++same++go after
      go (d:rest)=d:go rest
  pure (Module name exports imports (go ds))

addDoubleHelper name ds
  | name/="Bootstrap.Std" = pure ds
  | otherwise = do
      tick "negate_double_helper"
      let t=Token "negateDouble" 0 0 0 0
          bits=Var "bits"
          mask=Lit (LInteger "9223372036854775808")
          op n a b=apps (Var ("$infix:"++n)) [a,b]
          rhs=Let True [Equation t "bits" [] Nothing (App (Var "doubleToBits") (Var "value"))]
                (App (Var "doubleFromBits") (If (op "<" bits mask) (op "+" bits mask) (op "-" bits mask)))
      pure (ds++[Signature t "negateDouble" (TyArrow (TyName "Double") (TyName "Double")),Equation t "negateDouble" [PVar "value"] Nothing rhs])

mapTop env [] = pure []
mapTop env (d@Equation{}:ds) = do
  let n=declName d; (same,rest)=span (\x -> case x of { Equation{} -> declName x==n; _ -> False }) ds
  out <- transformGroup env (resolve env n) (d:same)
  (out++) <$> mapTop env rest
mapTop env (d:ds) = do
  d' <- case d of
    Signature t n ty -> tick "signatures" >> pure (Signature t (resolve env n) ty)
    Data{} -> pure d
    Class t cs n vs ms -> pure (Class t cs n vs ms)
    Instance t vs cs n ts methods -> do
      ms <- mapTop env methods
      pure (Instance t vs cs n ts ms)
  (d':) <$> mapTop env ds

patternsIn env ps = do
  let names=concatMap patVars ps
  when (length (nub names)/=length names) (failT "duplicate pattern binder")
  pairs <- forM names $ \n -> do
    output <- if unsafeName n then fresh (n++"Value") else pure n
    when (output/=n) (record ("reserved-binder\t"++n++"\t"++output))
    tick "pattern_binders"
    pure (n,output)
  let next=M.union (M.fromList pairs) env
  pure (map (renamePattern next) ps,next)
renamePattern env p = case p of
  PVar n -> PVar (resolve env n)
  PAnn{} -> error "typed variable patterns are outside shared-v1"
  PCon c ps -> PCon c (map (renamePattern env) ps)
  _ -> p

transformGroup env output ds = do
  converted <- forM ds $ \d -> case d of
    Signature t _ ty -> tick "signatures" >> pure (Signature t output ty)
    Equation t _ ps annotation b -> do
      (ps',next) <- patternsIn env ps
      b' <- transform next b
      pure (Equation t output ps' annotation b')
    _ -> failT "invalid value group"
  let rows=[(ps,b) | Equation _ _ ps _ b <- converted]
      affected=any (any hasString . fst) rows
  if not affected then pure (concatMap separateAnnotation converted) else do
    tick "string_pattern_matrices"
    let first= head [t | Equation t _ _ _ _ <- converted]
        arity=length (fst (head rows))
    names <- replicateM arity (fresh "matchValue")
    (body,used) <- matrix (map Var names) (zipWith (\i (ps,b) -> (ps,b,i)) [0..] rows)
    when (S.size used/=length rows) (failT "unreachable row in migrated literal equation matrix")
    pure ([s | s@Signature{} <- converted] ++ [Signature first output ty | Equation _ _ _ (Just ty) _ <- converted] ++ [Equation first output (map PVar names) Nothing body])
separateAnnotation d = case d of
  Equation t n ps (Just ty) b -> [Signature t n ty,Equation t n ps Nothing b]
  _ -> [d]

transform env e = case e of
  Var n -> do
    tick "resolved_value_references"
    let out=resolve env n
    when (out/=n) (tick "renamed_value_references")
    pure (Var out)
  Lit (LDouble ('-':n)) -> tick "negative_double_literals" >> pure (App (Var (resolve env "$negateDouble")) (Lit (LDouble n)))
  Lit l -> pure (Lit l)
  App a b -> App <$> transform env a <*> transform env b
  Lambda ps b -> do
    (ps',next) <- patternsIn env ps
    b' <- transform next b
    if any hasString ps' then do
      tick "string_pattern_matrices"
      names <- replicateM (length ps') (fresh "matchValue")
      (body,_) <- matrix (map Var names) [(ps',b',0)]
      pure (Lambda (map PVar names) body)
    else pure (Lambda ps' b')
  Case a bs -> do
    a' <- transform env a
    bs' <- forM bs $ \(p,b) -> do
      (patterns,next) <- patternsIn env [p]
      let p'=head patterns
      b' <- transform next b
      pure (p',b')
    if any (hasString.fst) bs' then do
      tick "string_pattern_matrices"
      n <- fresh "matchValue"
      (body,used) <- matrix [Var n] (zipWith (\i (p,b) -> ([p],b,i)) [0..] bs')
      when (S.size used/=length bs') (failT "unreachable row in migrated literal case matrix")
      pure (Let True [Equation dummy n [] Nothing a'] body)
    else pure (Case a' bs')
  If a b c -> If <$> transform env a <*> transform env b <*> transform env c
  Let rec ds b -> localBindings env rec ds (\next -> transform next b)
  Do ss -> Do <$> statements env ss
  Ann a ty -> Ann <$> transform env a <*> pure ty

dummy=Token "" 0 0 0 0
localBindings env recursive ds continuation = do
  gs <- lift (groups ds)
  if recursive then do
    tick "recursive_groups"
    forM_ gs $ \g -> do
      let annotations=[ty | Signature _ _ ty <- g]++[ty | Equation _ _ _ (Just ty) _ <- g]
      unless (length annotations==1 && S.null (freeType (head annotations))) (failT ("recursive binding lacks exactly one closed signature: "++groupName g))
      record ("recursive-closed\t"++groupName g++"\t"++show (head annotations))
    pairs <- forM gs $ \g -> do
      let n=groupName g
      out <- if unsafeName n then fresh (n++"Value") else pure n
      pure (n,out)
    let next=M.union (M.fromList pairs) env
    ds' <- concat <$> mapM (\g -> transformGroup next (resolve next (groupName g)) g) gs
    b' <- continuation next
    pure (Let True ds' b')
  else sequential env gs
  where
    sequential current []=continuation current
    sequential current (g:rest)=do
      tick "sequential_bindings"
      let n=groupName g
          refs=S.map (resolve current) (S.unions (map freeDecl g))
          captures=n `S.member` refs
      out <- if captures || unsafeName n then fresh n else pure n
      when captures $ do
        tick "capture_hazards"
        record ("nonrecursive-capture\t"++n++"\t"++out++"\t"++show (S.toList refs))
      ds' <- transformGroup current out g
      b' <- sequential (M.insert n out current) rest
      pure (Let True ds' b')

-- Preserve real do syntax. Refutable binds use a variable bind and a case
-- containing the remainder, so mismatch and field demand follow native MLF.
statements env ss = case ss of
  [] -> failT "empty do block"
  [Then e] -> (:[]) . Then <$> transform env e
  Then e:rest -> (:) <$> (Then <$> transform env e) <*> statements env rest
  Bind p e:rest -> do
    e' <- transform env e
    (patterns,next) <- patternsIn env [p]
    let p'=head patterns
    remaining <- statements next rest
    if simple p' then pure (Bind p' e':remaining) else do
      tick "refutable_do_binds"
      n <- fresh "boundValue"
      if hasString p' then do
        (body,_) <- matrix [Var n] [([p'],Do remaining,0)]
        pure [Bind (PVar n) e',Then body]
      else pure [Bind (PVar n) e',Then (Case (Var n) [(p',Do remaining)])]
  Local rec ds:rest -> do
    lowered <- localBindings env rec ds (\next -> Do <$> statements next rest)
    pure (flattenLocal lowered)
    where flattenLocal (Let True ds b)=Local True ds:flattenLocal b
          flattenLocal (Do rest)=rest
          flattenLocal e=[Then e]
  _ -> failT "do must finish in expression"
simple p=case p of { PVar{} -> True; PWild -> True; _ -> False }
hasString p=case p of { PLit (LString _) -> True; PCon _ ps -> any hasString ps; _ -> False }
freeType ty=case ty of
  TyName n -> if not (null n) && isLower (head n) then S.singleton n else S.empty
  TyApp a b -> freeType a `S.union` freeType b
  TyArrow a b -> freeType a `S.union` freeType b
  TyForall vs b -> freeType b S.\\ S.fromList (map fst vs)
  TyContext ps b -> S.unions (map freeType (b:ps))

-- Direct transcription of Bootstrap.Surface.matrix, constructorsMatrix,
-- specializeRow, literalBranch and literalMatrix. The first non-variable
-- column in the first row determines the next demand, never an entire spine.
replace i fields xs = take i xs++fields++drop (i+1) xs
bindPattern v p b=case p of { PVar n -> Let True [Equation dummy n [] Nothing v] b; PWild -> b; _ -> b }
matrix values [] = failT "non-exhaustive migrated literal pattern matrix"
matrix values rows@((first,body,index):_)
  | any (\(ps,_,_) -> length ps/=length values) rows = failT "matrix arity mismatch"
  | all simple first = pure (foldr (\(v,p) b -> bindPattern v p b) body (zip values first),S.singleton index)
  | otherwise = do
      let column=length (takeWhile simple first)
          value=values!!column
          patterns=[ps!!column | (ps,_,_) <- rows, not (simple (ps!!column))]
          defaults=[(replace column [] ps,bindPattern value (ps!!column) b,i) | (ps,b,i) <- rows,simple (ps!!column)]
      case head patterns of
        PCon{} -> do
          unless (all isCon patterns) (failT "mixed constructor/literal matrix")
          let names=nub [c | PCon c _ <- patterns]
          branches <- forM names $ \name -> do
            let arities=[length fields | PCon c fields <- patterns,c==name]
                arity=head arities
            unless (all (==arity) arities) (failT "constructor arity mismatch")
            names' <- replicateM arity (fresh "matchValue")
            let specialize (ps,b,i)=case ps!!column of
                  PCon c fields | c==name -> [(replace column fields ps,b,i)]
                  p | simple p -> [(replace column (replicate arity PWild) ps,bindPattern value p b,i)]
                  _ -> []
            (next,used) <- matrix (replace column (map Var names') values) (concatMap specialize rows)
            pure ((PCon name (map PVar names'),next),used)
          fallback <- if null defaults then pure [] else do
            (next,used) <- matrix (replace column [] values) defaults
            pure [((PWild,next),used)]
          pure (Case value (map fst (branches++fallback)),S.unions (map snd (branches++fallback)))
        PLit (LBool _) -> do
          unless (all isBool patterns) (failT "mixed bool matrix")
          (yes,uy) <- literalBranch column values rows (LBool True)
          (no,un) <- literalBranch column values rows (LBool False)
          pure (If value yes no,uy `S.union` un)
        PLit literal -> do
          unless (all (sameKind literal) patterns) (failT "mixed literal matrix")
          (fallback,used) <- matrix (replace column [] values) defaults
          let literals=nubLiteral [l | PLit l <- patterns]
          foldM (\(rest,used') l -> do
            (next,u) <- literalBranch column values rows l
            let eq=case l of { LString _ -> "MLF.Primitive.eqString"; LInteger _ -> "MLF.Primitive.eqInt"; _ -> error "unsupported literal" }
            pure (If (apps (Var eq) [value,Lit l]) next rest,used' `S.union` u)) (fallback,used) (reverse literals)
        _ -> failT "invalid matrix pattern"
  where isCon PCon{}=True; isCon _=False
        isBool (PLit (LBool _))=True; isBool _=False
        sameKind (LString _) (PLit (LString _))=True
        sameKind (LInteger _) (PLit (LInteger _))=True
        sameKind _ _=False
literalBranch column values rows literal = matrix (replace column [] values)
  [(replace column [] ps,bindPattern (values!!column) p b,i) | (ps,b,i) <- rows,let p=ps!!column,simple p || equalPattern p literal]
equalPattern (PLit l) r=equalLiteral l r
equalPattern _ _=False
equalLiteral (LString a) (LString b)=(read a::String)==read b
equalLiteral (LInteger a) (LInteger b)=(read a::Integer)==read b
equalLiteral a b=a==b
nubLiteral []=[]
nubLiteral (x:xs)=x:nubLiteral (filter (not.equalLiteral x) xs)

-- The printer is intentionally conventional source, not a generated v_/t_
-- namespace. Explicit braces remove layout ambiguity from all block forms.
renderModule sourceText (Module name exports imports ds) = unlines
  ["-- mlf:syntax shared-haskell-v1",
   "{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,",
   "             KindSignatures, FlexibleContexts, FlexibleInstances,",
   "             MultiParamTypeClasses, OverloadedStrings #-}",
   renderStyle (Style PageMode 100 1.0) $ openBlock (text ("module "++name) <+> maybe empty (parens.hsep.punctuate comma.map exportDoc) exports <+> text "where")
      (map importDoc imports++annotatedDecls sourceText ds)]
renderDeclaration = renderStyle (Style PageMode 100 1.0) . declDoc
exportDoc e=case e of
  ValueExport n -> text n
  TypeExport n Nothing -> text n
  TypeExport n (Just ns) -> text n <> parens (hcat (punctuate comma (map text ns)))
  ModuleExport n -> text "module" <+> text n
importDoc (Import q n alias selection)=text "import" <+> (if q then text "qualified" else empty) <+> text n <+> maybe empty (\a -> text "as" <+> text a) alias <+> maybe empty (\(h,xs) -> (if h then text "hiding" else empty) <+> parens (hsep (punctuate comma (map exportDoc xs)))) selection
block ds = openBlock empty ds
openBlock header ds = (header <+> lbrace) $$ nest 2 (vcat (punctuate semi ds)) $$ rbrace
smallBlock ds = braces (hsep (punctuate semi ds))
kindDoc k=case k of { Star -> char '*'; KArrow a b -> parens (kindDoc a <+> text "->" <+> kindDoc b) }
parameterDoc (n,Nothing)=text n
parameterDoc (n,Just k)=parens (text n <+> text "::" <+> kindDoc k)
typeDoc p ty=case ty of
  TyName n -> text n
  TyApp a b -> wrap (p>9) (sep [typeDoc 9 a,typeDoc 10 b])
  TyArrow a b -> wrap (p>0) (sep [typeDoc 1 a <+> text "->",typeDoc 0 b])
  TyForall vs b -> wrap (p>0) (text "forall" <+> hsep (map parameterDoc vs) <> char '.' <+> typeDoc 0 b)
  TyContext cs b -> wrap (p>0) (contextDoc cs <+> typeDoc 0 b)
contextDoc []=empty
contextDoc cs=parens (hsep (punctuate comma (map (typeDoc 0) cs))) <+> text "=>"
wrap True=parens
wrap False=id
declDoc d=case d of
  Signature _ n ty -> text n <+> text "::" <+> typeDoc 0 ty
  Equation _ n ps _ b -> hang (text n <+> hsep (map (patternDoc 10) ps) <+> equals) 2 (exprDoc 0 b)
  Data _ n vs cs -> hang (text "data" <+> text n <+> hsep (map parameterDoc vs) <+> equals) 2 (sep (punctuate (text " |") [text c <+> hsep (map (typeDoc 10) fields) | (c,fields)<-cs]))
  Class _ cs n vs methods -> openBlock (text "class" <+> contextDoc cs <+> text n <+> hsep (map parameterDoc vs) <+> text "where") [text m <+> text "::" <+> typeDoc 0 ty | (m,ty)<-methods]
  Instance _ vs cs n ts ds -> openBlock (text "instance" <+> (if null vs then empty else text "forall" <+> hsep (map parameterDoc vs) <> char '.') <+> contextDoc cs <+> text n <+> hsep (map (typeDoc 10) ts) <+> text "where") (map declDoc ds)
patternDoc p pat=case pat of
  PVar n -> text n
  PWild -> char '_'
  PCon n ps -> wrap (p>9 && not (null ps)) (text n <+> hsep (map (patternDoc 10) ps))
  PLit l -> literalDoc l
  PAnn{} -> error "typed variable pattern in shared output"
literalDoc l=case l of
  LString s -> text s
  LInteger ('-':n) -> parens (text ('-':n))
  LInteger n -> text n
  LDouble n -> text n
  LBool b -> text (show b)
exprDoc p e=case e of
  Var n -> text n
  Lit l -> literalDoc l
  App (App (Var n) a) b | "$infix:" `isPrefixOf` n -> parens (sep [exprDoc 1 a <+> text (drop 7 n),exprDoc 1 b])
  App a b -> wrap (p>9) (hang (exprDoc 9 a) 2 (exprDoc 10 b))
  Lambda ps b -> wrap (p>0) (hang (char '\\' <> hsep (map (patternDoc 10) ps) <+> text "->") 2 (exprDoc 0 b))
  Case a bs -> wrap (p>0) (openBlock (text "case" <+> exprDoc 0 a <+> text "of") [hang (patternDoc 0 pat <+> text "->") 2 (exprDoc 0 b) | (pat,b)<-bs])
  If a b c -> wrap (p>0) (sep [text "if" <+> exprDoc 0 a,text "then" <+> exprDoc 0 b,text "else" <+> exprDoc 0 c])
  Let _ ds b -> wrap (p>0) (openBlock (text "let") (map declDoc ds) <+> text "in" $$ exprDoc 0 b)
  Do ss -> wrap (p>0) (openBlock (text "do") (map statementDoc ss))
  Ann a ty -> parens (exprDoc 0 a <+> text "::" <+> typeDoc 0 ty)
statementDoc st=case st of
  Then e -> exprDoc 0 e
  Bind p e -> hang (patternDoc 0 p <+> text "<-") 2 (exprDoc 0 e)
  Local _ ds -> openBlock (text "let") (map declDoc ds)

stringsIn (Module _ _ _ ds)=concatMap declStrings ds
  where
    declStrings d=case d of { Equation _ _ _ _ b -> exprStrings b; Instance _ _ _ _ _ xs -> concatMap declStrings xs; _ -> [] }
    exprStrings e=case e of
      Lit (LString s) -> [s]
      App a b -> exprStrings a++exprStrings b
      Lambda _ b -> exprStrings b
      Case a bs -> exprStrings a++concatMap (exprStrings.snd) bs
      If a b c -> concatMap exprStrings [a,b,c]
      Let _ ds b -> concatMap declStrings ds++exprStrings b
      Do ss -> concatMap statementStrings ss
      Ann a _ -> exprStrings a
      _ -> []
    statementStrings s=case s of { Bind _ e -> exprStrings e; Then e -> exprStrings e; Local _ ds -> concatMap declStrings ds }
stringPatterns (Module _ _ _ ds)=concatMap declPatterns ds
  where
    ps p=case p of { PLit (LString s) -> [s]; PCon _ xs -> concatMap ps xs; _ -> [] }
    declPatterns d=case d of { Equation _ _ patterns _ b -> concatMap ps patterns++ex b; Instance _ _ _ _ _ xs -> concatMap declPatterns xs; _ -> [] }
    ex e=case e of
      App a b -> ex a++ex b
      Lambda patterns b -> concatMap ps patterns++ex b
      Case a bs -> ex a++concat [ps p++ex b | (p,b)<-bs]
      If a b c -> concatMap ex [a,b,c]
      Let _ ds b -> concatMap declPatterns ds++ex b
      Do ss -> concatMap st ss
      Ann a _ -> ex a
      _ -> []
    st s=case s of { Bind p e -> ps p++ex e; Then e -> ex e; Local _ ds -> concatMap declPatterns ds }


-- Keep the human explanation from the legacy sources. Standalone comments
-- remain before the following declaration; inline comments are associated
-- with their containing declaration. Literal bytes are never scanned as code.
annotatedDecls sourceText ds =
  [vcat [commentDoc raw | (slot,raw)<-assigned,slot==i] $$ declDoc d | (i,d)<-zip [0..] ds] ++
  [vcat [commentDoc raw | (slot,raw)<-assigned,slot==length ds] | any ((==length ds).fst) assigned]
  where
    starts=[(i,declLine d) | (i,d)<-zip [0..] ds,declLine d>0]
    assigned=[(choose l c,raw) | (l,c,raw)<-sourceComments sourceText]
    choose l c
      | c<=1 = case [i | (i,start)<-starts,start>=l] of { i:_ -> i; [] -> length ds }
      | otherwise = case [i | (i,start)<-starts,start<=l] of { [] -> 0; xs -> last xs }
    declLine d=case d of
      Signature t _ _ -> line t
      Equation t _ _ _ _ -> line t
      Data t _ _ _ -> line t
      Class t _ _ _ _ -> line t
      Instance t _ _ _ _ _ -> line t
    commentDoc raw = vcat (map text (lines (if take 2 raw=="--" && take 1 (drop 2 raw)/=" " then "-- "++drop 2 raw else raw)))
sourceComments = go 1 1
  where
    go _ _ []=[]
    go l c ('"':xs)=let (raw,rest)=quoted ['"'] xs; (l',c')=advance l c raw in go l' c' rest
    go l c ('-':'-':xs)=let (body,rest)=break (=='\n') xs; raw="--"++body; (l',c')=advance l c raw in (l,c,raw):go l' c' rest
    go l c ('{':'-':xs)=let (raw,rest)=comment 1 "{-" xs; (l',c')=advance l c raw in (l,c,raw):go l' c' rest
    go l _ ('\n':xs)=go (l+1) 1 xs
    go l c (_:xs)=go l (c+1) xs
    advance l c raw=foldl (\(a,b) x -> if x=='\n' then (a+1,1) else (a,b+1)) (l,c) raw
    quoted acc []=(reverse acc,[])
    quoted acc ('\\':rest) = case span isSpace rest of
      (gap,'\\':xs) | not (null gap) -> quoted (reverse ('\\':gap++"\\")++acc) xs
      (_,x:xs) -> quoted (x:'\\':acc) xs
      _ -> (reverse ('\\':acc),[])
    quoted acc ('"':xs)=(reverse ('"':acc),xs)
    quoted acc (x:xs)=quoted (x:acc) xs
    comment _ acc []=(acc,[])
    comment depth acc ('{':'-':xs)=comment (depth+1) (acc++"{-") xs
    comment depth acc ('-':'}':xs)
      | depth==1=(acc++"-}",xs)
      | otherwise=comment (depth-1) (acc++"-}") xs
    comment depth acc (x:xs)=comment depth (acc++[x]) xs


-- Pretty-printing must not accidentally change precedence, grouping, patterns
-- or literal spellings. Ignore positions, and normalize the one deliberate
-- syntax change: output local groups are simultaneous recursive Haskell lets.
sameAST a b = astShape a==astShape b
astShape = show . normalModule
normalModule (Module n ex im ds)=Module n ex im (map normalDecl ds)
normalDecl d=case d of
  Signature _ n ty -> Signature dummy n ty
  Equation _ n ps ty b -> Equation dummy n (map normalPattern ps) ty (normalExpr b)
  Data _ n vs cs -> Data dummy n vs cs
  Class _ cs n vs ms -> Class dummy cs n vs ms
  Instance _ vs cs n ts ds -> Instance dummy vs cs n ts (map normalDecl ds)
normalPattern p=case p of
  PCon "True" [] -> PLit (LBool True)
  PCon "False" [] -> PLit (LBool False)
  PCon n ps -> PCon n (map normalPattern ps)
  _ -> p
normalExpr e=case e of
  App a b -> App (normalExpr a) (normalExpr b)
  Lambda ps b -> Lambda (map normalPattern ps) (normalExpr b)
  Case a bs -> Case (normalExpr a) [(normalPattern p,normalExpr b) | (p,b)<-bs]
  If a b c -> If (normalExpr a) (normalExpr b) (normalExpr c)
  Let _ ds b -> Let True (map normalDecl ds) (normalExpr b)
  Do ss -> Do (map normalStatement ss)
  Ann a ty -> Ann (normalExpr a) ty
  _ -> e
normalStatement s=case s of
  Bind p e -> Bind (normalPattern p) (normalExpr e)
  Then e -> Then (normalExpr e)
  Local _ ds -> Local True (map normalDecl ds)
