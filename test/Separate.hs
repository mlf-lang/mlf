module Separate (separateTests, separatePrograms, compileSeparateProgram) where

import Control.Monad (foldM, unless)
import Data.List (isInfixOf)
import qualified Data.Map.Strict as M
import MLF.Compiler (PreludeMode(..))
import MLF.Module
import MLF.Module.Syntax
import MLF.Parser (parseModule)
import MLF.Separate
import qualified MLF.X.Check as Check
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T
import Modules (ModuleProgram, modulePrograms, moduleRejections, ModuleRejection(..))

separatePrograms :: [ModuleProgram]
separatePrograms = modulePrograms ++
  [("inferred overloaded export",ImplicitPrelude,
    [("Render",unlines ["module Render (Render(..), renderTwice) where", "class Render a where", "  render : a -> String", "instance Render Int where", "  render = showInt", "renderTwice x = render x ++ render x"])],
    "module Main where\nimport Render\nmain = putStrLn (renderTwice 4)\n", "44\n")
  ,("rank-n constructor field",ImplicitPrelude,
    [("Poly","module Poly where\ndata Poly = Poly (forall a. a -> a)\npoly = Poly (\\x -> x)\n")],
    "module Main where\nimport Poly\nmain = case poly of\n  Poly f -> do\n    let id = (\\x -> x) (f : forall a. a -> a)\n    printInt (id 42)\n    putStrLn (id \"polymorphic\")\n", "42\npolymorphic\n")
  ,("class-free bounded annotation rules",NoImplicitPrelude,
    [("Poly","module Poly where\ndata Poly = Poly (forall a. a -> a)\npoly = Poly (\\x -> x)\n")],
    "module Main where\nimport Poly\nmain = case poly of\n  Poly f -> let id = f : forall a. a -> a in ioBind (printInt (id 42)) (\\ignored -> putStrLn (id \"polymorphic\"))\n", "42\npolymorphic\n")
  ,("unexported nominal type in inferred signature",ImplicitPrelude,
    [("Secret","module Secret (make, reveal) where\ndata Hidden = Hidden Int\nmake = Hidden\nreveal (Hidden x) = x\n")],
    "module Main where\nimport Secret\nmain = printInt (reveal (make 42))\n", "42\n")
  ,("mutually recursive module values",ImplicitPrelude,
    [("Parity",unlines ["module Parity (even) where", "even : Int -> Bool", "even n = if n == 0 then true else odd (n-1)", "odd : Int -> Bool", "odd n = if n == 0 then false else even (n-1)"])],
    "module Main where\nimport Parity\nmain = printInt (if even 42 then 42 else 0)\n", "42\n")
  ,("Unicode interface identity",ImplicitPrelude,
    [("Unicode","module Unicode (λ) where\nλ = 42\n")],
    "module Main where\nimport Unicode\nmain = printInt λ\n", "42\n")
  ,("nominal global cannot capture local binder",ImplicitPrelude,
    [("A","module A where\nx = 41\n")],
    "module Main where\nimport A\nf module_65_z_120_ = x + module_65_z_120_\nmain = printInt (f 1)\n", "42\n")]
  ++ [("imported entry binding",ImplicitPrelude,
    [("Entry","module Entry (main) where\nmain = printInt 42\n")],
    "module Main where\nimport Entry\n", "42\n")]

right :: Either String a -> IO a
right = either fail pure
assert :: Bool -> String -> IO ()
assert p s = unless p (fail s)

compileSeparateProgram :: PreludeMode -> [(String,String)] -> String -> Either String [UnitObject]
compileSeparateProgram mode libraries source = do
  root <- parseModule "Main.emlf" source
  modules <- loadModuleMap (M.fromList [(n,(n ++ ".emlf",s)) | (n,s) <- libraries]) root
  prelude <- builtinPrelude
  let initial = M.singleton "Prelude" prelude
      iface (UnitObject i _) = i
      dependencies known m = closure [] (map importedModule (importsFor mode m))
        where
          closure done [] = Right done
          closure done (n:ns) | any ((== n) . unitName . iface) done = closure done ns
          closure done (n:ns) = do
            o <- maybe (Left ("missing dependency " ++ n)) Right (M.lookup n known)
            earlier <- closure done (map fst (unitDependencies (iface o)))
            closure (earlier ++ [o]) ns
      compileOne (known,objects) m = do
        deps <- dependencies known m
        object@(UnitObject i _) <- compileUnit mode (map iface deps) m
        -- Exercise both on-disk formats even in the pure graph tests.
        i' <- decodeInterface (encodeInterface i)
        checked <- decodeObject i' (encodeObject object)
        pure (M.insert (unitName i) checked known,objects ++ [checked])
  (known,_) <- foldM compileOne (initial,[]) modules
  deps <- dependencies known root
  object <- maybe (Left "missing entry") Right (M.lookup (moduleIdentity root) known)
  pure (deps ++ [object])

separateTests :: [(String,IO ())]
separateTests =
  [("separate modules: " ++ name, do
      objects <- right (compileSeparateProgram mode libraries source)
      term <- right (linkObjects objects "Main")
      ty <- right (Check.checkClosed term)
      assert (T.alphaEq ty (T.Con "IO" [T.Con "Unit" []]))
        ("module entry retained unresolved arguments: " ++ show ty))
    | (name,mode,libraries,source,_) <- separatePrograms] ++
  [("separate rejects: " ++ name, case compileSeparateProgram mode libraries source of
      Left _ -> pure ()
      Right _ -> fail ("accepted invalid modules: " ++ name))
    | ModuleRejection name libraries source _ _ <- moduleRejections
    , let mode = ImplicitPrelude] ++
  [("separate interface version rejection", do
      assert (either (const True) (const False) (decodeInterface "6:MLFI-9")) "accepted unknown format")
  ,("separate object export scheme is independently checked", do
      source <- right (parseModule "Main.emlf" "module Main where\nmain = printInt 42\n")
      UnitObject iface term <- right (compileUnit NoImplicitPrelude [] source)
      let forged = UnitObject iface { unitBindings = [(n,T.Con "Bool" []) | (n,_) <- unitBindings iface] } term
      expect "export type mismatch" (linkObjects [forged] "Main"))
  ,("separate object datatype layout is independently checked", do
      source <- right (parseModule "Main.emlf" "module Main where\ndata Hidden = Hidden Int\nmain = printInt 42\n")
      UnitObject iface term <- right (compileUnit NoImplicitPrelude [] source)
      let forged = UnitObject iface (case term of X.WithData _ body -> body; _ -> term)
      _ <- right (Check.checkClosed (objectTerm forged))
      expect "datatype interface mismatch" (linkObjects [forged] "Main"))
  ,("separate object dependency parameters are checked even when unused", do
      source <- right (parseModule "Main.emlf" "module Main where\nmain = printInt 42\n")
      prelude@(UnitObject imported _) <- right builtinPrelude
      UnitObject iface term <- right (compileUnit ImplicitPrelude [imported] source)
      let strip (X.Abs _ _ body) = strip body
          strip body = body
          forged = UnitObject iface (case term of X.WithData ds body -> X.WithData ds (strip body); _ -> strip term)
      _ <- right (Check.checkClosed (objectTerm forged))
      expect "dependency parameter mismatch" (linkObjects [prelude,forged] "Main"))]
  where expect reason result = case result of
          Left message -> assert (reason `isInfixOf` message) message
          Right _ -> fail ("accepted forged object: " ++ reason)
