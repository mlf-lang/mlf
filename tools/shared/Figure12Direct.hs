-- Test-only direct host entry. Never translates implementation or guest source.
-- Fixture data comes from the fail-closed decoder of the maintained legacy suite.
module Main where
import qualified Prelude as P
import Prelude
import qualified Data.List as L
import qualified Data.Set as Set
import qualified System.Environment as Env
import qualified MLF.Host.Base as H
import qualified Bootstrap.Types as T
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.Desugar as Desugar
import qualified Bootstrap.Compiler as C
import qualified Bootstrap.X.Parser as XP
import qualified Bootstrap.X.Check as XC
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.X.Type as XT
import qualified Bootstrap.X.Syntax as XS
import qualified Package.Json as J

list :: T.List a -> [a]
list T.Nil = []
list (T.Cons x xs) = x:list xs
mlist :: [a] -> T.List a
mlist = foldr T.Cons T.Nil
text = H.unpack . J.text
field key = J.get (H.literal key)
items key = list . J.values . field key
str key = text . field key
boolean key = J.bool . field key
right :: T.Either H.String a -> IO a
right (T.Left e) = fail (H.unpack e)
right (T.Right x) = return x
ensure True _ = return ()
ensure False s = fail s
pairs = map pair . list . J.values where
  pair x = case list (J.values x) of
    [a,b] -> (text a,text b)
    _ -> error "fixture pair arity"

-- Same structural free-name contract as Tests.Figure12.freeNames, including
-- sorted set order, constructors excluded and right-biased signature bindings.
freeNames :: T.SExpr -> Set.Set String
freeNames expression = case expression of
  T.SVar x -> Set.singleton (H.unpack x)
  T.SConstructor _ -> Set.empty
  T.SLam x _ b -> Set.delete (H.unpack x) (freeNames b)
  T.SApp a b -> Set.union (freeNames a) (freeNames b)
  T.SLet x a b -> Set.union (freeNames a) (Set.delete (H.unpack x) (freeNames b))
  T.SAnn a _ -> freeNames a
  T.SSignature a _ -> freeNames a
  T.SIntLit _ -> Set.empty
  T.SDoubleLit _ -> Set.empty
  T.SBoolLit _ -> Set.empty
  T.SStringLit _ -> Set.empty
  T.SPrimitive _ -> Set.empty
  T.SWanted _ candidates -> Set.fromList [H.unpack n | T.Pair _ n <- list candidates]
  T.SChecked _ a -> freeNames a
  T.SEquations equations -> Set.unions
    [freeNames body Set.\\ Set.unions (map bound (list ps)) | T.Pair ps body <- list equations]
  T.SDo _ _ -> freeNames (Desugar.desugarDo expression)
  T.SLetRec ds b -> Set.unions (freeNames b:[freeNames a | T.Triple _ _ a <- list ds])
    Set.\\ Set.fromList [H.unpack n | T.Triple n _ _ <- list ds]
  T.SCase a bs -> Set.union (freeNames a) (Set.unions
    [freeNames b Set.\\ bound p | T.SAlternative p b <- list bs])
  where
    bound (T.SConstructorPattern _ ns) = Set.fromList [H.unpack n | T.Just n <- list ns]
    bound (T.SDefaultPattern n) = case n of T.Just x -> Set.singleton (H.unpack x); T.Nothing -> Set.empty
    bound (T.SNestedPattern _ ps) = Set.unions (map bound (list ps))
    bound (T.SAnnotatedPattern n _) = Set.singleton (H.unpack n)
    bound (T.SIntPattern _) = Set.empty
    bound (T.SStringPattern _) = Set.empty
    bound (T.SBoolPattern _) = Set.empty

assumptions fixture c = do
  e <- right (Parser.parseExpr (H.literal (str "id" c)) (H.literal (str "expression" c)))
  let env = reverse (pairs (field "signatures" fixture) ++ pairs (field "local_signatures" c))
  mapM (\n -> maybe (fail ("fixture has no signature for " ++ n)) (\s -> return (n,s)) (lookup n env))
    (Set.toAscList (freeNames e))
program fixture c = do
  ss <- assumptions fixture c
  return (foldr (\(n,s) b -> "\\(" ++ n ++ " : " ++ s ++ ") ->\n" ++ b) (str "expression" c) ss)
checkOutput result = do
  parsed <- right (XP.parseTerm (H.literal "<Figure12 xMLF>") (Pretty.prettyTerm (C.compiledTerm result)))
  ty <- right (XC.checkClosed parsed)
  ensure (XT.alphaEq ty (C.inferredType result)) "Figure12 target roundtrip changed type"
  ensure (XS.equalErased (XS.erase parsed) (XS.erase (C.compiledTerm result))) "Figure12 target roundtrip changed erasure"
compileSource source = case C.compile (H.literal "<Figure12 direct host>") (H.literal source) of
  T.Left e -> fail (H.unpack (C.prettyError e))
  T.Right result -> checkOutput result >> return result
checkCase fixture c = do
  source <- program fixture c
  case C.compile (H.literal ("<Figure12 " ++ str "id" c ++ ">")) (H.literal source) of
    T.Left e -> do
      ensure (not (boolean "expected_acceptance" c)) (H.unpack (C.prettyError e))
      ensure (case C.phase e of T.Inference -> True; _ -> False) "wrong rejection phase"
      let protected = str "id" c `elem` ["A8","E1a"]
          reason = if protected then "cannot raise a protected type variable" else "type constructor mismatch:"
          diagnostic = H.unpack (C.diagnostic e)
      ensure (reason `L.isInfixOf` diagnostic) ("wrong rejection reason: " ++ diagnostic)
      ensure (protected || ("Con \"Bool\" []" `L.isInfixOf` diagnostic && "Con \"Int\" []" `L.isInfixOf` diagnostic)) "expected Int/Bool conflict"
    T.Right result -> ensure (boolean "expected_acceptance" c) "expected rejection" >> checkOutput result
xtype j = case list (J.values j) of
  [tag] | text tag == "XBot" -> T.XBot
  [tag,v] | text tag == "XVar" -> T.XVar (variable v)
  [tag,a,b] | text tag == "XArrow" -> T.XArrow (xtype a) (xtype b)
  [tag,v,a,b] | text tag == "XForall" -> T.XForall (variable v) (xtype a) (xtype b)
  _ -> error "unsupported fixture XType data"
  where variable v = case list (J.values v) of
          [tag,J.Number n] | text tag == "XTyVar" -> T.XTyVar (read (H.unpack n))
          _ -> error "unsupported fixture XTyVar data"
jsonString = J.String . H.literal
jsonArray = J.Array . mlist
jsonPair (a,b) = jsonArray [jsonString a,jsonString b]
object xs = J.Object (mlist [T.Pair (H.literal k) v | (k,v) <- xs])
main = do
  args <- Env.getArgs
  case args of
    [path,mode,index] -> do
      raw <- readFile path
      fixture <- right (J.parse (H.literal raw))
      let cases = items "cases" fixture
      ss <- fmap (L.nub . concat) (mapM (assumptions fixture) cases)
      programs <- mapM (program fixture) cases
      let keys = zipWith (\c p -> (boolean "expected_acceptance" c,p)) cases programs
          aliases = [(str "id" c,str "id" (cases !! first)) | (n,(c,k)) <- zip [0..] (zip cases keys), let Just first = L.elemIndex k keys, first < n]
      ensure (length cases == 43 && length (L.nub keys) == 41 && length ss == 29) "Figure12 inventory changed"
      ensure (aliases == [("A12.1","A10.1"),("E3a","A12.2")]) "Figure12 execution sharing changed"
      let ix = read index :: Int
      case mode of
        "inventory" -> putStrLn (H.unpack (J.render (object
          [("assumptions",jsonArray (map jsonPair ss)),("programs",jsonArray (map jsonString programs)),("aliases",jsonArray (map jsonPair aliases))])))
        "case" -> checkCase fixture (cases !! ix) >> putStrLn "PASS case"
        "assumption" -> do
          let (n,s) = ss !! ix
          _ <- compileSource ("\\(" ++ n ++ " : " ++ s ++ ") -> " ++ n)
          putStrLn "PASS assumption"
        "type" -> do
          let c = items "type_checks" fixture !! ix
          result <- compileSource (str "source" c)
          ensure (XT.alphaEq (C.inferredType result) (xtype (field "expected" c))) "principal type differs"
          putStrLn "PASS type"
        "repair" -> checkCase fixture (items "repairs" fixture !! ix) >> putStrLn "PASS repair"
        _ -> fail "unknown mode"
    _ -> fail "usage: figure12-direct FIXTURE.json MODE INDEX"
