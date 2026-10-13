module Main (main) where

import Control.Monad (unless)
import System.Environment (getArgs)
import System.Exit (die)
import qualified MLF.X.Check as Check
import qualified MLF.X.Parser as Parser
import qualified MLF.X.Pretty as Pretty
import qualified MLF.X.Type as Type

-- Independent seed checker for the candidate compiler's serialized output.
-- Checking and type comparison never trust the candidate's --type response.
main :: IO ()
main = getArgs >>= run
  where
    run [targetFile,expectedFile] = do
      target <- readFile targetFile
      expected <- readFile expectedFile
      term <- either die pure (Parser.parseTerm targetFile target)
      actual <- either die pure (Check.checkClosed term)
      expectedType <- either die pure (Parser.parseType expected)
      unless (Type.alphaEq actual expectedType) $ die
        ("inferred type mismatch\nexpected: " ++ Pretty.prettyType expectedType ++
         "\nactual: " ++ Pretty.prettyType actual)
    run _ = die "Usage: check-bootstrap-target TARGET.xmlf EXPECTED.type"
