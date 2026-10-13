-- Fixed environment slots are checked independently of the optimizing pipeline;
-- execution still uses both independent backends and their collection profile.
module EnvironmentAccess (environmentAccessTests) where

import Control.Monad (unless)
import Data.List (isInfixOf, isPrefixOf, tails)
import qualified Data.Map.Strict as Map
import Backends (Backends, Entry (..), Input (..))
import qualified Backends as B
import MLF.Compiler (compile, compiledTerm)
import MLF.LLVM (emitLLVMIO)
import qualified MLF.Data as D
import qualified MLF.LLVM.Codegen as Codegen
import qualified MLF.X.Check as Check
import qualified MLF.X.Syntax as X

checked :: String -> IO X.Term
checked = either (fail . show) (pure . compiledTerm) . compile "<environment slots>"

observe :: Backends -> X.Term -> String -> IO ()
observe backends term expected = do
  result <- B.execute backends IOEntry (Input "" False) term
  either (fail . show) pure (B.outcome result)
  unless (B.output result == expected) (fail (show result))

directSlots :: String -> Bool
directSlots code = not ("call ptr @mlf_env_get(" `isInfixOf` code) &&
  not ("call void @mlf_env_set(" `isInfixOf` code) &&
  "store ptr " `isInfixOf` code && "load ptr," `isInfixOf` code &&
  "getelementptr i8, ptr %env, i64 24" `isInfixOf` code

environmentAccessTests :: Backends -> [(String,IO ())]
environmentAccessTests backends =
  [("environment slots: curried captures and constructor fields remain lazy", do
      term <- checked lazySource
      _ <- either fail pure (Check.checkClosed term)
      let declarations = case term of X.WithData ds _ -> ds; _ -> []
          constructors = Map.fromList (("Unit",(0,0)) :
            [(D.constructorName c,(i,length (D.constructorFields c))) |
              (i,c) <- zip [1..] (concatMap D.datatypeConstructors declarations)])
      (_,code) <- either fail pure (Codegen.generate constructors (X.erase term))
      let llvm = unlines code
      unless (directSlots llvm && "call ptr @mlf_constructor_new(" `isInfixOf` llvm &&
        "call ptr @mlf_closure(" `isInfixOf` llvm && "call ptr @mlf_thunk(" `isInfixOf` llvm)
        (fail "fixture did not directly initialize/read closure, thunk, and constructor environments")
      observe backends term "19\n42\n43\n")
  , ("environment slots: repeated native action preserves captures and laziness", do
      term <- checked nativeSource
      llvm <- either fail pure (emitLLVMIO term)
      let entries = [unlines (takeWhile (/= "}") body) | line:body <- tails (lines llvm),
                      "define private ptr @mlf.numeric.entry." `isPrefixOf` line]
      unless (directSlots llvm && any ("getelementptr i8, ptr %env, i64 24" `isInfixOf`) entries &&
        "call ptr @mlf_native_io(" `isInfixOf` llvm)
        (fail "fixture did not retain a native action with direct capture slots")
      observe backends term "before\n42\n42\n7\n")]

lazySource :: String
lazySource =
  "data Cell = Cell Int Int (Int -> Int); " ++
  "let make = \\base extra ignored -> let add = \\delta -> base + extra + delta in Cell base ignored add in " ++
  "do { base <- ioReturn (readInt \"19\"); partial <- ioReturn (make base 3); " ++
  "cell <- ioReturn (partial (panic \"unused constructor field\")); " ++
  "case cell of { Cell first _ add -> do { printInt first; printInt (add 20); printInt (add 21) } } }"

nativeSource :: String
nativeSource =
  "do { base <- ioReturn (readInt \"19\"); " ++
  "let make = \\n -> ioReturn (base + n + 1 + 1 + 1 + 1 + 1 + 1) in " ++
  "do { action <- ioReturn (make 17); " ++
  "putStrLn \"before\"; first <- action; printInt first; second <- action; printInt second; " ++
  "unused <- ioReturn (make (panic \"unused native argument\")); printInt 7 } }"
