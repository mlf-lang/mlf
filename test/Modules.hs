module Modules
  ( moduleTests, modulePrograms, moduleRejections, ModuleRejection (..)
  , checkModule, withScratch, ModuleProgram
  ) where

import Control.Exception (bracket)
import Control.Monad (forM_, unless)
import Data.List (isInfixOf)
import qualified Data.Map.Strict as Map
import System.Directory
import System.FilePath ((</>), takeDirectory)
import System.IO (hClose, openTempFile)
import MLF.Compiler
import MLF.Module.Syntax
import MLF.Parser (parseModule)
import qualified MLF.X.Check as C
import qualified MLF.X.Parser as XP
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T
import MLF.X.Pretty (prettyTerm)

type Test = (String,IO ())
type Libraries = [(String,String)]
type ModuleProgram = (String,PreludeMode,Libraries,String,String)

require :: Bool -> String -> IO ()
require ok message = unless ok (fail message)

right :: Show e => Either e a -> IO a
right = either (fail . show) pure

sources :: Libraries -> Map.Map String (FilePath,String)
sources = Map.fromList . map (\(n,s) -> (n,(n ++ ".emlf",s)))

build :: PreludeMode -> Libraries -> String -> Either CompileError Compilation
build mode libraries = compileModulesWithPrelude mode (sources libraries) "Main.emlf"

checkModule :: PreludeMode -> Libraries -> String -> IO Compilation
checkModule mode libraries input = do
  result <- right (build mode libraries input)
  parsed <- right (XP.parseTerm "<module xMLF>" (prettyTerm (compiledTerm result)))
  ty <- right (C.checkClosed parsed)
  require (T.alphaEq ty (inferredType result)) "module target round trip changed type"
  require (X.erase parsed == X.erase (compiledTerm result)) "module target round trip changed erasure"
  pure result

numbers, box, rendering :: Libraries
numbers = [("Math.Numbers",unlines
  ["module Math.Numbers (inc, twice, factorial) where",
   "inc x = x + 1", "twice f x = f (f x)",
   "factorial : Int -> Int", "factorial 0 = 1", "factorial n = n * factorial (n-1)",
   "private = 99"])]
box = [("Data.Box",unlines
  ["module Data.Box (Box(..), unwrap) where", "data Box a = Box a",
   "unwrap (Box x) = x"])]
rendering =
  [("Render",unlines ["module Render (Render(..)) where", "class Render a where", "  render : a -> String"])
  ,("Instances",unlines ["module Instances () where", "import Render (Render)",
     "import Prefix (prefix)", "instance Render Int where", "  render n = prefix ++ showInt (adjust n)",
     "adjust n = n + 1"])
  ,("Prefix","module Prefix (prefix) where\nprefix = \"number: \"\n")
  ,("Facade","module Facade (module R) where\nimport Render as R\nimport Instances ()\n")]

modulePrograms :: [ModuleProgram]
modulePrograms =
  [ ("selective and qualified imports",ImplicitPrelude,numbers,
      unlines ["module Main (main) where", "import Math.Numbers (inc)",
       "import qualified Math.Numbers as N (twice, factorial)",
       "main = do", "  printInt (N.twice inc 40)", "  printInt (N.factorial 6)"], "42\n720\n")
  , ("unnamed entry expression imports",ImplicitPrelude,numbers,
      "import Math.Numbers hiding (twice, factorial)\nprintInt (Math.Numbers.inc 41)\n", "42\n")
  , ("qualified types, fields and nested patterns",ImplicitPrelude,box,
      unlines ["module Main where", "import qualified Data.Box as B",
       "data Wrapped = Wrapped (B.Box Int)",
       "read : Wrapped -> Int", "read (Wrapped (B.Box x)) = x",
       "main = printInt (read (Wrapped (B.Box 42)))"], "42\n")
  , ("private names and constructor identities",ImplicitPrelude,
      [("A","module A (Box(..), get) where\ndata Box = Box Int\nhelper x = x + 1\nget (Box x) = helper x\n"),
       ("B","module B (Box(..), get) where\ndata Box = Box Int\nhelper x = x * 2\nget (Box x) = helper x\n")],
      "module Main where\nimport qualified A\nimport qualified B\nmain = printInt (A.get (A.Box 20) + B.get (B.Box 10))\n",
      "41\n")
  , ("diamond reexports preserve identity",ImplicitPrelude,
      numbers ++ [("Left","module Left (module N) where\nimport Math.Numbers as N\n"),
       ("Right","module Right (inc) where\nimport Math.Numbers (inc)\n")],
      "module Main where\nimport Left\nimport Right\nmain = printInt (inc 41)\n", "42\n")
  , ("transitive empty imports carry instances and private helpers",ImplicitPrelude,rendering,
      "module Main where\nimport Facade\nmain = putStrLn (render 41)\n", "number: 42\n")
  , ("qualified class, hidden methods in instance declaration",ImplicitPrelude,
      [("Convert","module Convert (Convert(convert)) where\nclass Convert a b where\n  convert : a -> b\n"),
       ("Conversions",unlines ["module Conversions () where", "import qualified Convert as C (Convert)",
        "instance C.Convert Int String where", "  convert = showInt"])],
      "module Main where\nimport qualified Convert as C\nimport Conversions ()\nmain = putStrLn (C.convert 42)\n", "42\n")
  , ("abstract datatype used by exported functions",ImplicitPrelude,
      [("Secret","module Secret (Secret, make, reveal) where\ndata Secret = Secret Int\nmake = Secret\nreveal (Secret x) = x\n")],
      "module Main where\nimport Secret\nanswer : Secret\nanswer = make 42\nmain = printInt (reveal answer)\n", "42\n")
  , ("local shadowing and self qualification",ImplicitPrelude,numbers,
      unlines ["module Main where", "import Math.Numbers (inc)",
       "answer = 42", "f inc = inc Main.answer",
       "main = printInt (let answer = 0 in f (\\x -> x))"], "42\n")
  , ("explicit qualified Prelude",ImplicitPrelude,[],
      unlines ["module Main where", "import qualified Prelude as P",
       "main : P.IO P.Unit", "main = P.bind (P.return 42) P.printInt"], "42\n")
  , ("explicit Prelude with implicit import disabled",NoImplicitPrelude,[],
      "module Main where\nimport Prelude (Monad(..), printInt)\nmain = do\n  x <- return 42\n  printInt x\n", "42\n")
  , ("hiding Prelude method for local definition",ImplicitPrelude,[],
      "module Main where\nimport Prelude hiding (return)\nreturn x = x\nmain = do\n  printInt (return 42)\n  putStrLn \"done\"\n",
      "42\ndone\n")
  , ("module lexical scope protects imported do",ImplicitPrelude,
      [("Actions","module Actions (action) where\naction = do\n  x <- return 42\n  printInt x\n")],
      "module Main where\nimport Actions\nimport Prelude hiding (bind, return)\nbind x = x\nreturn x = 0\nmain = action\n",
      "42\n")
  , ("polymorphic Monad function across modules",ImplicitPrelude,
      [("Repeat",unlines ["module Repeat (twice) where",
        "twice : forall (m : * -> *) a. Monad m => m a -> m a",
        "twice action = do", "  action", "  action"])],
      "module Main where\nimport Repeat\nmain = twice (putStrLn \"again\")\n", "again\nagain\n")
  , ("qualified Boolean constructor patterns",ImplicitPrelude,[],
      "module Main where\nimport qualified Prelude as P\nmain = P.printInt (case P.True of\n  P.True -> 42\n  P.False -> 0)\n",
      "42\n")
  , ("internal name hygiene",ImplicitPrelude,
      [("A","module A (moduleEntity0) where\nmoduleEntity0 moduleEntity1 = moduleEntity1 + 1\n")],
      "module Main where\nimport A\nmoduleEntity2 = 41\nmain = printInt (moduleEntity0 moduleEntity2)\n", "42\n")
  , ("same method name from distinct classes",ImplicitPrelude,
      [("A","module A where\nclass Show a where\n  show : a -> String\ninstance Show Int where\n  show = showInt\n"),
       ("B","module B where\nclass Show a where\n  show : a -> String\ninstance Show Bool where\n  show b = if b then \"yes\" else \"no\"\n")],
      "module Main where\nimport qualified A\nimport qualified B\nmain = do\n  putStrLn (A.show 42)\n  putStrLn (B.show true)\n",
      "42\nyes\n")
  , ("instance may recursively use an exported helper",ImplicitPrelude,
      [("Count",unlines ["module Count (Count(..)) where", "class Count a where", "  count : a -> Int",
       "instance Count Int where", "  count = sumDown", "sumDown : Int -> Int",
       "sumDown 0 = 0", "sumDown n = n + sumDown (n-1)"])],
      "module Main where\nimport Count\nmain = printInt (count 8)\n", "36\n")
  , ("bare primitive fallback without implicit Prelude",NoImplicitPrelude,[],
      "module Main where\nmain = do\n  x <- return 42\n  printInt x\n", "42\n")
  , ("entry selects its own main",ImplicitPrelude,
      [("A","module A where\nmain = printInt 0\nanswer = 42\n")],
      "module Main where\nimport A\nmain = printInt answer\n", "42\n")
  , ("primitive fallback permits local definitions",NoImplicitPrelude,[],
      "module Main where\naddInt x y = x - y\nmain = printInt (addInt 43 1)\n", "42\n")
  ]

data ModuleRejection = ModuleRejection String Libraries String Phase String

rejects :: ModuleRejection -> Test
rejects (ModuleRejection label libraries input expected reason) = ("modules rejection: " ++ label,
  case build ImplicitPrelude libraries input of
    Left err -> require (phase err == expected && reason `isInfixOf` diagnostic err) (show err)
    Right result -> fail ("unexpected acceptance: " ++ sourceType result))

moduleRejections :: [ModuleRejection]
moduleRejections =
  [ ModuleRejection "private function" numbers
      "module Main where\nimport Math.Numbers\nmain = private\n" ModuleResolution "not in scope: private"
  , ModuleRejection "qualified private function" numbers
      "module Main where\nimport qualified Math.Numbers as N\nmain = N.private\n" ModuleResolution "not in scope: N.private"
  , ModuleRejection "selected imports exclude others" numbers
      "import Math.Numbers (inc)\nfactorial 6" ModuleResolution "not in scope: factorial"
  , ModuleRejection "qualified-only is not unqualified" numbers
      "import qualified Math.Numbers\ninc 1" ModuleResolution "not in scope: inc"
  , ModuleRejection "alias replaces qualified module name" numbers
      "import Math.Numbers as N\nMath.Numbers.inc 1" ModuleResolution "not in scope: Math.Numbers.inc"
  , ModuleRejection "hiding also affects qualification" numbers
      "import Math.Numbers hiding (inc)\nMath.Numbers.inc 1" ModuleResolution "not in scope: Math.Numbers.inc"
  , ModuleRejection "unknown import selection" numbers
      "import Math.Numbers (missing)\n42" ModuleResolution "not in scope: missing"
  , ModuleRejection "unknown hidden name" numbers
      "import Math.Numbers hiding (missing)\n42" ModuleResolution "not in scope: missing"
  , ModuleRejection "private constructor" [("A","module A (Box, make) where\ndata Box = Box Int\nmake = Box\n")]
      "import A\nBox 42" ModuleResolution "not in scope: Box"
  , ModuleRejection "type-only selective import" box
      "import Data.Box (Box)\nBox 42" ModuleResolution "not in scope: Box"
  , ModuleRejection "member belongs to selected type" box
      "import Data.Box (Box(Other))\n42" ModuleResolution "not a visible member"
  , ModuleRejection "private type annotation" [("A","module A (make) where\ndata Box = Box Int\nmake = Box\n")]
      "import A\n(make 42 : Box)" ModuleResolution "not in scope: Box"
  , ModuleRejection "hidden members cannot be reexported"
      [("A","module A (Box) where\ndata Box = Box Int\n"),
       ("B","module B (Box(..)) where\nimport A\n")]
      "import B\nBox 42" ModuleResolution "not in scope: Box"
  , ModuleRejection "default exports exclude imports"
      [("A","module A where\nx = 1\n"),("B","module B where\nimport A\ny = x\n")]
      "import B\nx" ModuleResolution "not in scope: x"
  , ModuleRejection "transitive names are not imported" rendering
      "import Facade\nprefix" ModuleResolution "not in scope: prefix"
  , ModuleRejection "distinct imports are ambiguous"
      [("A","module A where\nx = 1\n"),("B","module B where\nx = 2\n")]
      "import A\nimport B\nx" ModuleResolution "ambiguous name x"
  , ModuleRejection "top-level import collision requires hiding"
      [("A","module A where\nx = 1\n")]
      "module Main where\nimport A\nx = 2\nmain = x\n" ModuleResolution "ambiguous name x"
  , ModuleRejection "explicit reexport conflict"
      [("A","module A where\nx = 1\n"),("B","module B where\nx = 2\n"),
       ("Both","module Both (A.x, B.x) where\nimport qualified A\nimport qualified B\n")]
      "import Both\n42" ModuleResolution "conflicting declarations or exports"
  , ModuleRejection "unknown module reexport" []
      "module Main (module Missing) where\nmain = 42\n" ModuleResolution "unimported module"
  , ModuleRejection "qualified-only module reexport has no unqualified names"
      [("A","module A where\nx = 1\n"),("B","module B (module A) where\nimport qualified A\n")]
      "import B\nx" ModuleResolution "not in scope: x"
  , ModuleRejection "empty exports"
      [("A","module A () where\nx = 1\n")] "import A\nx" ModuleResolution "not in scope: x"
  , ModuleRejection "missing module" [] "import Missing\n42" ModuleResolution "cannot find module Missing"
  , ModuleRejection "mismatched module header" [("A","module B where\nx = 1\n")]
      "import A\n42" ModuleResolution "expected module A, found B"
  , ModuleRejection "unnamed library" [("A","x = 1\nmain = x\n")]
      "import A\n42" ModuleResolution "expected module A, found an unnamed script"
  , ModuleRejection "cycle includes chain"
      [("A","module A where\nimport B\nx = 1\n"),("B","module B where\nimport A\ny = 2\n")]
      "import A\n42" ModuleResolution "Main -> A -> B -> A"
  , ModuleRejection "self import" [] "module Main where\nimport Main\nmain = 42\n"
      ModuleResolution "Main -> Main"
  , ModuleRejection "module header followed by bare expression" [] "module Main where\n42\n" Parsing "declarations only"
  , ModuleRejection "imports must precede definitions" [] "module Main where\nmain = 42\nimport Prelude\n" Parsing "import"
  , ModuleRejection "definitions cannot be qualified" [] "module Main where\nA.f = 42\n" Parsing "named modules contain declarations only"
  , ModuleRejection "explicit empty Prelude removes value names" []
      "module Main where\nimport Prelude ()\nmain = printInt 42\n" ModuleResolution "not in scope: printInt"
  , ModuleRejection "qualified Prelude suppresses implicit Prelude" []
      "module Main where\nimport qualified Prelude as P\nmain = return 42\n" ModuleResolution "not in scope: return"
  , ModuleRejection "Prelude cannot be redefined" [] "module Prelude where\nmain = 42\n"
      ModuleResolution "built-in module"
  , ModuleRejection "primitive constructor cannot be redefined" []
      "module Main where\ndata Foo = Unit\nmain = Unit\n" ModuleResolution "primitive constructor"
  , ModuleRejection "primitive type cannot be redefined" []
      "module Main where\ndata Int = Number\nmain = Number\n" ModuleResolution "primitive type"
  , ModuleRejection "unused private definitions still checked"
      [("A","module A (x) where\nx = 42\nbad = missing\n")]
      "import A\nx" ModuleResolution "not in scope: missing"
  , ModuleRejection "export list cannot name missing value" []
      "module Main (missing) where\nmain = 42\n" ModuleResolution "not in scope: missing"
  , ModuleRejection "recursive signature error names the source function" []
      "module Main where\nloop x = loop x\nmain = loop 0\n" ModuleResolution "Main.loop requires an explicit closed signature"
  , ModuleRejection "instance not visible in imported signed definition"
      [("Render","module Render where\nclass Render a where\n  render : a -> String\n"),
       ("Bad","module Bad (text) where\nimport Render\ntext : String\ntext = render 42\n"),
       ("Orphan","module Orphan () where\nimport Render\ninstance Render Int where\n  render = showInt\n")]
      "module Main where\nimport Bad\nimport Orphan ()\nmain = putStrLn text\n" Resolution "no instance or given constraint for Render.Render Int"
  , ModuleRejection "instance not visible in another instance"
      [("A","module A where\nclass First a where\n  first : a -> String\nclass Second a where\n  second : a -> String\n"),
       ("Bad","module Bad () where\nimport A\ninstance First Int where\n  first n = second n\n"),
       ("Orphan","module Orphan () where\nimport A\ninstance Second Int where\n  second = showInt\n")]
      "module Main where\nimport A\nimport Bad ()\nimport Orphan ()\nmain = putStrLn (first 42)\n" Resolution "no instance or given constraint for A.Second Int"
  ]

moduleTests :: [Test]
moduleTests =
  [ ("modules checking: " ++ label, do
      result <- checkModule mode libraries input
      require (T.alphaEq (inferredType result) (T.Con "IO" [T.Con "Unit" []])) (sourceType result))
    | (label,mode,libraries,input,_) <- modulePrograms ] ++
  map rejects moduleRejections ++
  [ ("modules: original source type names", do
      result <- checkModule ImplicitPrelude box "import Data.Box\nBox 42"
      require ("Data.Box.Box" `isInfixOf` sourceType result) (sourceType result))
  , ("modules: unit syntax is intrinsic", do
      result <- checkModule ImplicitPrelude [] "module Main where\nimport Prelude ()\nmain : ()\nmain = ()\n"
      require (sourceType result == "Unit") (sourceType result))
  , ("modules: empty libraries and multiline headers", do
      result <- checkModule ImplicitPrelude [("Empty","module Empty () where\n")]
        "module Main\n  (main)\n  where\n    import Empty ()\n    main = 42\n"
      require (sourceType result == "Int") (sourceType result))
  , ("modules: explicit braces and layout parse identically", do
      a <- right (parseModule "Main.emlf" "module Main (main) where\nimport qualified Prelude as P\nmain = P.printInt 42\n")
      b <- right (parseModule "Main.emlf" "module Main (main) where { import qualified Prelude as P; main = P.printInt 42; }")
      require (a == b) (show (a,b)))
  , ("modules: libraries can be parsed without main", do
      m <- right (parseModule "A.emlf" "module A where\nx = 42\n")
      require (sourceModuleName m == Just "A" && sourceBody m == Nothing) (show m))
  , ("modules: unused imports do not cause value ambiguity", do
      result <- checkModule ImplicitPrelude [("A","module A where\nx = 1\n"),("B","module B where\nx = 2\n")]
        "import A\nimport B\n42"
      require (sourceType result == "Int") (sourceType result))
  , ("modules: legacy compile path preserves checked output", do
      a <- right (compile "script.emlf" "main = do { printInt 42; return Unit };")
      b <- right (build ImplicitPrelude numbers "main = do { printInt 42; return Unit };")
      require (compiledTerm a == compiledTerm b && inferredType a == inferredType b) "unused source map changed compilation")
  , ("modules: file loader, includes, hierarchy and errors", fileTests)
  ]

withScratch :: (FilePath -> IO a) -> IO a
withScratch = bracket create removeDirectoryRecursive
  where
    create = do
      temporary <- getTemporaryDirectory
      (path,handle) <- openTempFile temporary "mlf-modules"
      hClose handle
      removeFile path
      createDirectory path
      pure path

fileTests :: IO ()
fileTests = withScratch $ \directory -> do
  let put path input = do
        createDirectoryIfMissing True (takeDirectory path)
        writeFile path input
      includes = directory </> "libraries"
      entry = directory </> "app" </> "Main.emlf"
  numberSource <- maybe (fail "missing Numbers test source") pure (lookup "Math.Numbers" numbers)
  put (includes </> "Math" </> "Numbers.emlf") numberSource
  put entry "module Main where\nimport Math.Numbers (inc)\nmain = inc 41\n"
  good <- compileFile [includes] entry >>= right
  require (sourceType good == "Int") (sourceType good)
  unusedMissing <- compileFile [directory </> "absent search root",includes] entry >>= right
  require (sourceType unusedMissing == "Int") "unused missing search root changed compilation"
  missing <- compileFile [] entry
  case missing of
    Left err -> require ("cannot find module Math.Numbers; searched" `isInfixOf` diagnostic err) (show err)
    Right _ -> fail "module loaded outside search roots"
  -- A hierarchical entry can locate siblings from its own inferred source root.
  put (includes </> "Math" </> "Main.emlf")
    "module Math.Main where\nimport Math.Numbers\nmain = inc 41\n"
  _ <- compileFile [] (includes </> "Math" </> "Main.emlf") >>= right
  forM_ [entry, includes </> "Math" </> "Numbers.emlf"] $ \file -> do
    put file "module Wrong where\nmain = 42\n"
  -- The entry module may have any name; an imported module must match its path.
  put entry "module Main where\nimport Math.Numbers\nmain = 42\n"
  wrong <- compileFile [includes] entry
  case wrong of
    Left err -> require ("expected module Math.Numbers, found Wrong" `isInfixOf` diagnostic err) (show err)
    Right _ -> fail "wrong file header accepted"
  absent <- compileFile [] (directory </> "Missing.emlf")
  case absent of
    Left err -> require (phase err == ModuleResolution) (show err)
    Right _ -> fail "missing entry accepted"
