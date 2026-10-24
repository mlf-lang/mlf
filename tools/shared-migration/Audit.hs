module Main where
import MLF.Host.Parser
import MLF.Host.Syntax
import MLF.Host.Lexer (Token, line)
import System.Environment
import Control.Monad
import Data.List (intercalate, nub, (\\))
import qualified Data.Set as Set

type Ctx = (String,String)
row (modu,loc) kind fields = putStrLn (intercalate "\t" ([modu,kind,loc] ++ fields))
at (m,loc) t n = (m,loc ++ "/" ++ n ++ ":" ++ show (line t))
child (m,loc) s = (m,loc++s)
reserved = words "type newtype default deriving foreign infix infixl infixr forall family role pattern static mdo proc stock anyclass via safe unsafe interruptible qualified as hiding fromInteger fromRational fromString negate ifThenElse otherwise"
hooks = words "fromInteger fromRational fromString negate ifThenElse otherwise"
bind c n = when (n `elem` reserved) (row c (if n `elem` hooks then "HOOK_BINDER" else "KEYWORD_BINDER") [n])
pt c p = case p of
 PVar n -> bind c n
 PAnn n t -> bind c n >> ty c t
 PCon _ ps -> zipWithM_ (\i -> pt (child c ("/field"++show i))) [0::Int ..] ps
 PLit (LString s) -> row c "STRING_PATTERN" [show s]
 PLit (LDouble s) -> row c "DOUBLE_PATTERN" [s]
 _ -> pure ()
ty c t = case t of
 TyApp a b -> ty c a >> ty c b
 TyArrow a b -> ty c a >> ty c b
 TyForall ns a -> mapM_ (bind c . fst) ns >> ty c a
 TyContext ts a -> mapM_ (ty c) ts >> ty c a
 _ -> pure ()
tfv t = case t of
 TyName n -> if not (null n) && head n `elem` ['a'..'z'] then [n] else []
 TyApp a b -> nub (tfv a++tfv b)
 TyArrow a b -> nub (tfv a++tfv b)
 TyForall ns a -> tfv a \\ map fst ns
 TyContext ts a -> nub (concatMap tfv ts++tfv a)
name (Signature _ n _) = [n]
name (Equation _ n _ _ _) = [n]
name _ = []
freeDecl (Equation _ _ ps _ b) = fv b \\ concatMap patVars ps
freeDecl _ = []
-- Nonrecursive declaration groups have sequential scope; each contiguous equation group is one binding.
groups [] = []
groups (d@(Signature _ _ _):ds) = groups ds
groups (d@(Equation _ n _ _ _):ds) = let (same,rest)=span (\x -> name x==[n]) ds in (n,d:same):groups rest
groups (_:ds)=groups ds
fvDecls True ds b = nub (concatMap freeDecl ds ++ b) \\ concatMap name ds
fvDecls False ds b = go (groups ds) where
 go []=b
 go ((n,g):rest)=nub (concatMap freeDecl g ++ (go rest \\ [n]))
fv e = case e of
 Var n -> [n]
 Lit _ -> []
 App a b -> nub (fv a++fv b)
 Lambda ps b -> fv b \\ concatMap patVars ps
 Case a bs -> nub (fv a++concatMap (\(p,b) -> fv b \\ patVars p) bs)
 If a b c -> nub (fv a++fv b++fv c)
 Let rec ds b -> fvDecls rec ds (fv b)
 Do ss -> fs ss
 Ann a _ -> fv a
fs []=[]
fs (Then a:ss)=nub (fv a++fs ss)
fs (Bind p a:ss)=nub (fv a++(fs ss \\ patVars p))
fs (Local rec ds:ss)=fvDecls rec ds (fs ss)
ex c e = case e of
 Var n | n == "negate" || reverse (take 7 (reverse n)) == ".negate" -> row c "NEGATE_USE" [n]
 Lit (LDouble ('-':s)) -> row c "NEGATIVE_DOUBLE" ['-':s]
 App a b -> ex (child c "/function") a >> ex (child c "/argument") b
 Lambda ps b -> zipWithM_ (\i -> pt (child c ("/lambda"++show i))) [0::Int ..] ps >> ex (child c "/lambda-body") b
 Case a bs -> ex (child c "/scrutinee") a >> zipWithM_ (\i (p,b) -> pt (child c ("/case"++show i)) p >> ex (child c ("/case"++show i++"-body")) b) [0::Int ..] bs
 If a b d -> ex c a >> ex c b >> ex c d
 Let rec ds b -> do
  row c "LET_GROUP" [show rec,show (map fst (groups ds))]
  when rec (row c "RECURSIVE_LET" [show ds])
  auditGroup c (if rec then "recursive-let" else "sequential-let") ds
  ex (child c "/let-body") b
 Do ss -> zipWithM_ (st . child c . ("/do"++) . show) [0::Int ..] ss
 Ann a t -> ex c a >> ty c t
 _ -> pure ()
st c s = case s of
 Bind p a -> pt c p >> ex c a
 Then a -> ex c a
 Local rec ds -> do
  row c "DO_LET_GROUP" [show rec,show (map fst (groups ds))]
  when rec (row c "RECURSIVE_DO_LET" [show ds])
  auditGroup c (if rec then "recursive-do-let" else "sequential-do-let") ds

auditGroup c kind ds = do
 let sigs=[(n,t) | Signature _ n t <- ds] ++ [(n,t) | Equation _ n _ (Just t) _ <- ds]
 let names=nub (concatMap name ds)
 forM_ (groups ds) $ \(n,g) -> do
  let deps=filter (`elem` names) (nub (concatMap freeDecl g))
  row c "GROUP_BINDING" [kind,n,intercalate "," deps,maybe "NONE" (show . tfv) (lookup n sigs),maybe "NONE" show (lookup n sigs)]
 mapM_ (decl c) ds

decl c d = case d of
 Signature t n a -> bind (at c t n) n >> ty (at c t n) a
 Equation t n ps a b -> do
  let z=at c t n
  bind z n
  zipWithM_ (\i -> pt (child z ("/param"++show i))) [0::Int ..] ps
  maybe (pure ()) (ty z) a
  ex z b
 Data t n ps cs -> do
  mapM_ (bind (at c t n) . fst) ps
  mapM_ (mapM_ (ty (at c t n)) . snd) cs
 Class t supers n ps methods -> do
  mapM_ (ty (at c t n)) supers
  mapM_ (bind (at c t n) . fst) ps
  mapM_ (\(s,a) -> bind (at c t n) s >> ty (at c t n) a) methods
 Instance t ps supers n args methods -> do
  mapM_ (bind (at c t n) . fst) ps
  mapM_ (ty (at c t n)) (supers++args)
  auditGroup (at c t n) "instance" methods
main = do
 [manifest] <- getArgs
 files <- lines <$> readFile manifest
 forM_ files $ \entry -> do
  let (n,'\t':path)=break (=='\t') entry
  source <- readFile path
  case parseModule path source of
   Left err -> error err
   Right (Module actual _ _ ds) -> row (n,actual) "MODULE" [path] >> auditGroup (n,actual) "top" ds
