-- Host-only formatter regression: compare the maintained parser's source ASTs.
-- This is syntax/structure evidence, not typechecking, execution, or a native
-- bootstrap/fixed-point claim. No source rewriting or alternate parser is used.
module Main where

import Control.Exception (IOException, displayException, try)
import Control.Monad (unless)
import qualified Bootstrap.Parser as Parser
import qualified Bootstrap.SourceEquality as Equality
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as Host
import System.Environment (getArgs)
import System.Exit (die)

main :: IO ()
main = do
  args <- getArgs
  pairs <- case pairArgs args of
    Just xs | not (null xs) -> pure xs
    _ -> die "usage: FormatterCompatibility ORIGINAL FORMATTED [ORIGINAL FORMATTED ...]"
  mapM_ checkPair pairs
  putStrLn ("Formatter AST compatibility: " ++ show (length pairs) ++ " file pairs passed")

pairArgs :: [String] -> Maybe [(FilePath, FilePath)]
pairArgs [] = Just []
pairArgs (a:b:rest) = ((a,b):) <$> pairArgs rest
pairArgs _ = Nothing

checkPair :: (FilePath, FilePath) -> IO ()
checkPair (original, formatted) = do
  -- Both parses use the original logical path, including its syntax profile.
  before <- parseFile original original
  after <- parseFile original formatted
  unless (sameImports (moduleImports before) (moduleImports after)) $
    die (original ++ " -> " ++ formatted ++ ": import multiset changed")
  unless (Equality.eqSourceModule (normalizeModule before) (normalizeModule after)) $
    die (original ++ " -> " ++ formatted ++ ": source AST changed (beyond positions and import ordering)")
  putStrLn ("PASS " ++ original ++ " -> " ++ formatted)

parseFile :: FilePath -> FilePath -> IO T.SourceModule
parseFile logical physical = do
  result <- try (readFile physical >>= \s -> length s `seq` pure s) :: IO (Either IOException String)
  contents <- either (die . ((physical ++ ": read failed: ") ++) . displayException) pure result
  case Parser.parseModule (Host.literal logical) (Host.literal contents) of
    T.Left message -> die (physical ++ ": parse failed: " ++ Host.unpack message)
    T.Right parsed -> pure parsed

moduleImports :: T.SourceModule -> [T.Import]
moduleImports (T.SourceModule _ _ _ imports _ _ _ _ _ _) = imports

-- Ormolu sorts import declarations, selections and explicit member lists.
-- Match multisets at each level, preserving duplicate counts and identities.
-- Module exports and all other AST lists remain order-sensitive.
sameImports :: [T.Import] -> [T.Import] -> Bool
sameImports = sameMultiset sameImport

sameMultiset :: (a -> a -> Bool) -> [a] -> [a] -> Bool
sameMultiset _ [] ys = null ys
sameMultiset equal (x:xs) ys = case removeOne equal x ys of
  Nothing -> False
  Just rest -> sameMultiset equal xs rest

removeOne :: (a -> a -> Bool) -> a -> [a] -> Maybe [a]
removeOne _ _ [] = Nothing
removeOne equal x (y:ys)
  | equal x y = Just ys
  | otherwise = (y:) <$> removeOne equal x ys

sameImport :: T.Import -> T.Import -> Bool
sameImport (T.Import name qualified alias selection) (T.Import name2 qualified2 alias2 selection2) =
  Equality.eqImport (T.Import name qualified alias T.Everything)
    (T.Import name2 qualified2 alias2 T.Everything) && sameSelection selection selection2

sameSelection :: T.Selection -> T.Selection -> Bool
sameSelection T.Everything T.Everything = True
sameSelection (T.Only xs) (T.Only ys) = sameMultiset sameImportItem xs ys
sameSelection (T.Hiding xs) (T.Hiding ys) = sameMultiset sameImportItem xs ys
sameSelection _ _ = False

sameImportItem :: T.Export -> T.Export -> Bool
sameImportItem (T.ExportType name (T.Members xs)) (T.ExportType name2 (T.Members ys)) =
  Host.unpack name == Host.unpack name2 && sameMultiset (\x y -> Host.unpack x == Host.unpack y) xs ys
sameImportItem x y = Equality.eqExport x y

normalizeModule :: T.SourceModule -> T.SourceModule
normalizeModule (T.SourceModule _ name exports _ datatypes classes instances values body syntax) =
  T.SourceModule (Host.literal "") name exports [] datatypes classes
    (map normalizeInstance instances) (map normalizeValue values)
    (mapMaybe normalizeExpr body) syntax

normalizeInstance :: T.SInstanceDecl -> T.SInstanceDecl
normalizeInstance (T.SInstanceDecl variables context name arguments methods) =
  T.SInstanceDecl variables context name arguments
    [(method, normalizeExpr expression) | (method, expression) <- methods]

normalizeValue :: (a, b, T.SExpr) -> (a, b, T.SExpr)
normalizeValue (name, annotation, expression) = (name, annotation, normalizeExpr expression)

mapMaybe :: (a -> b) -> T.Maybe a -> T.Maybe b
mapMaybe _ T.Nothing = T.Nothing
mapMaybe f (T.Just x) = T.Just (f x)

normalizeSpan :: T.SourceSpan -> T.SourceSpan
normalizeSpan (T.SourceSpan package owner _ _ _ _ _) =
  T.SourceSpan package owner (Host.literal "") 0 0 0 0

-- Preserve call-site labels and wrappers, declaration provenance, recursive
-- groups/modes, patterns, literals, annotations and binding order verbatim.
-- An exhaustive traversal makes new expression constructors require review.
normalizeExpr :: T.SExpr -> T.SExpr
normalizeExpr expression = case expression of
  T.SGlobal slot name -> T.SGlobal slot name
  T.SDeclScope slots body -> T.SDeclScope slots (normalizeExpr body)
  T.SWantedRefs name refs -> T.SWantedRefs name refs
  T.SVar name -> T.SVar name
  T.SConstructor name -> T.SConstructor name
  T.SLam name annotation body -> T.SLam name annotation (normalizeExpr body)
  T.SApp function argument -> T.SApp (normalizeExpr function) (normalizeExpr argument)
  T.SLet name value body -> T.SLet name (normalizeExpr value) (normalizeExpr body)
  T.SAnn body annotation -> T.SAnn (normalizeExpr body) annotation
  T.SSignature body annotation -> T.SSignature (normalizeExpr body) annotation
  T.SIntLit value -> T.SIntLit value
  T.SDoubleLit value -> T.SDoubleLit value
  T.SBoolLit value -> T.SBoolLit value
  T.SStringLit value -> T.SStringLit value
  T.SPrimitive primitive -> T.SPrimitive primitive
  T.SCase scrutinee alternatives -> T.SCase (normalizeExpr scrutinee)
    [T.SAlternative pattern (normalizeExpr body) | T.SAlternative pattern body <- alternatives]
  T.SDo statements body -> T.SDo (map normalizeStatement statements) (normalizeExpr body)
  T.SEquations equations -> T.SEquations
    [(patterns, normalizeExpr body) | (patterns, body) <- equations]
  T.SLetRec bindings body -> T.SLetRec (map normalizeValue bindings) (normalizeExpr body)
  T.SWanted name evidence -> T.SWanted name evidence
  T.SChecked ty body -> T.SChecked ty (normalizeExpr body)
  T.SSourceDefinition body -> T.SSourceDefinition (normalizeExpr body)
  T.SCallSite label span body -> T.SCallSite label (normalizeSpan span) (normalizeExpr body)
  T.SSharedBind pattern action continuation method failure ->
    T.SSharedBind pattern (normalizeExpr action) (normalizeExpr continuation)
      (normalizeExpr method) (normalizeExpr failure)

normalizeStatement :: T.SStatement -> T.SStatement
normalizeStatement statement = case statement of
  T.SDoBind pattern value -> T.SDoBind pattern (normalizeExpr value)
  T.SDoThen value -> T.SDoThen (normalizeExpr value)
  T.SDoLet name annotation value -> T.SDoLet name annotation (normalizeExpr value)
  T.SDoLetRec bindings -> T.SDoLetRec (map normalizeValue bindings)
