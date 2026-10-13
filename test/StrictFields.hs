-- Pointer representation facts are checked separately from observable behavior.
module StrictFields (strictFieldTests) where
import Control.Monad (unless)
import Data.List (isInfixOf,isPrefixOf)
import qualified Data.Map.Strict as M
import Backends (Backends,Entry(..),Input(..))
import qualified Backends as B
import MLF.Compiler (compile,compiledTerm)
import qualified MLF.Data as D
import qualified MLF.LLVM.Codegen as G
import qualified MLF.Primitive as P
import qualified MLF.X.Check as Check
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

observe :: Backends -> X.Term -> String -> IO ()
observe backends term expected = do
  result <- B.execute backends IOEntry (Input "" False) term
  either (fail . show) pure (B.outcome result)
  unless (B.output result == expected) (fail (show result))

strictFieldTests :: Backends -> [(String,IO ())]
strictFieldTests backends =
  [("strict constructor fields: checked lowering uses the pointer proof", do
      _ <- either fail pure (Check.checkClosed lowered)
      (entry,code) <- either fail pure (G.generate (M.fromList [("Unit",(0,0)),("Cell",(1,1))]) (X.erase lowered))
      case filter (("define private ptr " ++ entry ++ "(") `isPrefixOf`) code of
        [body] -> unless (not ("call ptr @mlf_force(" `isInfixOf` body))
          (fail "proven constructor field was forced")
        _ -> fail "missing strict-field lowering entry"
      observe backends lowered "42\n")
  , ("strict constructor fields: lazy, partial, mixed and recursive values", do
      term <- compiledTerm <$> either (fail . show) pure (compile "<strict fields>" source)
      observe backends term "6\n11\n7\n24\n24\n10\n20\n")]
  where
    source = unlines
      [ "data StrictTriple = StrictTriple Int Int Int"
      , "data LazyTriple = LazyTriple Int Int Int"
      , "data PartialTriple = PartialTriple Int Int Int"
      , "data Chain = Chain Int Chain Int"
      , "data Captured = Captured Int Int Int"
      , "data Mixed = Mixed Int Int Int"
      , ""
      , "strictTriple : Int -> Int -> Int -> Int -> StrictTriple"
      , "strictTriple count x y z = if count == 0 then seq x (seq y (seq z (StrictTriple x y z))) else strictTriple (count - 1) x y z"
      , "lazyTriple : Int -> Int -> LazyTriple"
      , "lazyTriple count x = if count == 0 then LazyTriple x (quotInt 1 0) 9 else lazyTriple (count - 1) x"
      , "partialTriple : Int -> Int -> Int -> PartialTriple"
      , "partialTriple count = if count == 0 then PartialTriple 4 else partialTriple (count - 1)"
      , "chain : Chain"
      , "chain = Chain 5 chain 7"
      , "capture x = seq x (\\ignored -> Captured x 8 10)"
      , "strictMixed : Int -> Int -> Mixed"
      , "strictMixed count x = if count == 0 then seq x (Mixed x 1 2) else strictMixed (count - 1) x"
      , "lazyMixed : Int -> Int -> Mixed"
      , "lazyMixed count x = if count == 0 then Mixed x (quotInt 1 0) 12 else lazyMixed (count - 1) x"
      , ""
      , "main = do"
      , "  case strictTriple 3 1 2 3 of"
      , "    StrictTriple x y z -> seq x (seq y (seq z (printInt (x + y + z))))"
      , "  case lazyTriple 3 2 of"
      , "    LazyTriple x poison z -> seq x (seq z (printInt (x + z)))"
      , "  case partialTriple 3 (quotInt 1 0) 3 of"
      , "    PartialTriple x poison z -> seq x (seq z (printInt (x + z)))"
      , "  case chain of"
      , "    Chain x rest z -> case rest of"
      , "      Chain y next w -> seq x (seq y (seq z (seq w (printInt (x + y + z + w)))))"
      , "  case capture 6 0 of"
      , "    Captured x y z -> seq x (seq y (seq z (printInt (x + y + z))))"
      , "  case strictMixed 3 7 of"
      , "    Mixed x y z -> seq x (seq y (seq z (printInt (x + y + z))))"
      , "  case lazyMixed 3 8 of"
      , "    Mixed x poison z -> seq x (seq z (printInt (x + z)))"
      ]

lowered :: X.Term
lowered = X.WithData [D.DataDecl "Cell" [] [D.ConstructorDecl "Cell" [D.Applied "Int" []]]] $
  X.Let function (X.Abs value int (sequenceWith cell (X.VarTerm value) (X.App (X.Constructor "Cell" []) (X.VarTerm value)))) $
  X.Case (X.App (X.VarTerm function) (X.IntTerm 42)) ioUnit
    [X.Alternative (X.ConstructorPattern "Cell" [Just field])
      (sequenceWith ioUnit (X.VarTerm field) (X.App (X.Primitive P.PrintInt []) (X.VarTerm field)))]
  where
    function = X.Name 0 "constructor"
    value = X.Name 1 "value"
    field = X.Name 2 "field"
    int = T.Con "Int" []
    cell = T.Con "Cell" []
    ioUnit = T.Con "IO" [T.Con "Unit" []]
    sequenceWith result a b = X.App (X.App (X.Primitive P.Seq [int,result]) a) b
