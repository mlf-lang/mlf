module Main where
-- Actual source parsing, inference, elaboration and LLVM emission (not hand-built XTerm).
import Prelude
import System.Environment (getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Compiler as C
import qualified Bootstrap.LLVM as L
import qualified MLF.Host.Base as B
main :: IO ()
main = do
  args <- getArgs
  case args of
    [sourcePath, destination] -> do
      source <- readFile sourcePath
      case C.compile (B.literal sourcePath) (B.literal source) of
        T.Left e -> error (B.unpack (C.prettyError e))
        T.Right result -> case L.emitLLVMIO (C.compiledTerm result) of
          T.Left e -> error (B.unpack e)
          T.Right llvm -> writeFile destination (B.unpack llvm)
    _ -> error "expected source path and LLVM output path"
