module Main (main) where

import Control.Monad (forM_)
import qualified Data.Map.Strict as Map
import System.Environment (getArgs)
import qualified Figure12 as Figure
import qualified MLF.Compiler as Compiler

data Fixture = Fixture String [(String,(FilePath,String))] String

extra :: [Fixture]
extra =
  [ Fixture "identity" [] "\\x -> x"
  , Fixture "arithmetic" [] "main = 2 + 3 * 4"
  , Fixture "datatype" [] "data List a = Nil | Cons a (List a); main = Cons 1 Nil"
  , Fixture "nested-pattern" [] "data Maybe a = Nothing | Just a; data Box a = Box a; unbox (Box (Just x)) = x; unbox _ = 0; main = unbox (Box (Just 4))"
  , Fixture "polymorphic-recursion-signature-order" [] "data List a = Nil | Cons a (List a); foldl : forall a b. (b -> a -> b) -> b -> List a -> b; foldl f z Nil = z; foldl f z (Cons x xs) = foldl f (f z x) xs; main = foldl (\\z x -> z + x) 0 (Cons 1 Nil)"
  , Fixture "do-io" [] "main : IO Unit; main = do {putStrLn \"hello\"; return Unit}"
  , Fixture "multiparam-class" [] "class Convert a b where {convert : a -> b}; instance Convert Int String where {convert = showInt}; main = (convert 42 : String)"
  , Fixture "bad-self-application" [] "\\x -> x x"
  , Fixture "higher-kinded-field" [] "data Maybe a = Nothing | Just a; data Wrap (f : * -> *) a = Wrap (f a); case Wrap (Just 42) of { Wrap value -> value }"
  , Fixture "superclass-given" [] "class Inspect a where { inspect : a -> Bool }; class Inspect a => Test a where { test : a -> Bool }; let f : forall a. Test a => a -> Bool = \\x -> inspect x in 42"
  , Fixture "superclass-discard-parameter" [] "class Inspect a where { inspect : a -> Bool }; class Inspect b => Two a b where { two : a -> b -> Bool }; let f : forall a b. Two a b => a -> b -> Bool = \\x y -> inspect y in 42"
  , Fixture "superclass-reorder-parameters" [] "class Convert a b where { convert : a -> b }; class Convert b a => Reverse a b where { reverse : a -> b -> Bool }; let f : forall a b. Reverse a b => b -> a = \\x -> convert x in 42"
  , Fixture "missing-instance" [] "class Inspect a where { inspect : a -> Bool }; inspect 42"
  , Fixture "ambiguous-instance" [] "class Inspect a where { inspect : a -> Bool }; instance Inspect Bool where { inspect = \\x -> x }; inspect"
  , Fixture "module-qualified" [("A",("A.emlf","module A (ident) where\nident x = x"))] "module Main where\nimport qualified A as Q\nmain = Q.ident 42"
  , Fixture "module-hidden" [("A",("A.emlf","module A (public) where\npublic = 1; private = 2"))] "module Main where\nimport A\nmain = private"
  , Fixture "module-reexport" [("A",("A.emlf","module A (ident) where\nident x = x")),("B",("B.emlf","module B (module A) where\nimport A"))] "module Main where\nimport B\nmain = ident True"
  , Fixture "module-ambiguous" [("A",("A.emlf","module A where\nvalue = 1")),("B",("B.emlf","module B where\nvalue = 2"))] "module Main where\nimport A\nimport B\nmain = value"
  , Fixture "module-cycle" [("A",("A.emlf","module A where\nimport B\na = 1")),("B",("B.emlf","module B where\nimport A\nb = 2"))] "module Main where\nimport A\nmain = a"
  ]

fixtures :: Either String [Fixture]
fixtures = do
  figure <- mapM (\c -> Fixture ("Fig12-" ++ Figure.caseId c) [] <$> Figure.program c) Figure.cases
  pure (extra ++ figure)

report :: Fixture -> String
report (Fixture name modules source) = name ++ "\t" ++ case Compiler.compileModules (Map.fromList modules) (name ++ ".emlf") source of
  Left err -> "REJECT " ++ show (Compiler.phase err)
  Right result -> "ACCEPT " ++ Compiler.sourceType result

list :: (a -> String) -> [a] -> String
list f = foldr (\x xs -> "Cons (" ++ f x ++ ") (" ++ xs ++ ")") "Nil"

fixture :: Fixture -> String
fixture (Fixture name modules source) = "Triple " ++ show name ++ " (" ++ list moduleEntry modules ++ ") " ++ show source
  where moduleEntry (n,(f,s)) = "Pair " ++ show n ++ " (Pair " ++ show f ++ " " ++ show s ++ ")"

program :: [Fixture] -> String
program fs = unlines
  [ "module Main where"
  , "import Bootstrap.Types"
  , "import qualified Bootstrap.Std as L"
  , "import qualified Bootstrap.Map as M"
  , "import qualified Bootstrap.Compiler as Compiler"
  , "fixtures = " ++ list fixture fs
  , "report : Triple String (List (Pair String (Pair String String))) String -> IO Unit"
  , "report (Triple name modules source) = putStrLn (name ++ \"\\t\" ++ (case Compiler.compileModules (M.fromList compareString modules) (name ++ \".emlf\") source of"
  , "  Left err -> \"REJECT \" ++ Compiler.prettyPhase (Compiler.phase err)"
  , "  Right result -> \"ACCEPT \" ++ Compiler.sourceType result))"
  , "main = L.mapM_ report fixtures"
  ]

main :: IO ()
main = do
  args <- getArgs
  fs <- either fail pure fixtures
  case args of
    ["--generate"] -> putStr (program fs)
    [] -> forM_ fs (putStrLn . report)
    _ -> fail "usage: runghc -isrc -itest InferenceReference.hs [--generate]"
