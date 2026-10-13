-- Behavior is checked by both backends. The direct checked lowering assertion
-- proves that the reuse path is active even if later optimizers inline a call.
module ForceReuse (forceReuseTests) where

import Control.Monad (unless)
import Data.List (isInfixOf, isPrefixOf, tails)
import qualified Data.Map.Strict as Map
import Backends (Backends, Entry (..), Input (..))
import qualified Backends as B
import MLF.Compiler (compile, compiledTerm)
import qualified MLF.LLVM.Codegen as Codegen
import qualified MLF.Primitive as P
import qualified MLF.X.Check as Check
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

observe :: Backends -> X.Term -> String -> IO ()
observe backends term expected = do
  result <- B.execute backends IOEntry (Input "" False) term
  either (fail . show) pure (B.outcome result)
  unless (B.output result == expected) (fail (show result))

forceReuseTests :: Backends -> [(String,IO ())]
forceReuseTests backends =
  [("force reuse: dominated uses emit one force", do
      _ <- either fail pure (Check.checkClosed repeated)
      (_,code) <- either fail pure (Codegen.generate (Map.singleton "Unit" (0,0)) (X.erase repeated))
      let definitions = [takeWhile (/= "}") body | line:body <- tails (lines (unlines code)),
                          "define private ptr @mlf.worker.0(" `isPrefixOf` line]
      case definitions of
        [body] -> unless (length (filter ("call ptr @mlf_force(ptr %a1)" `isInfixOf`) body) == 1)
          (fail "a repeated conditional operand did not reuse its dominating WHNF")
        _ -> fail "force-reuse fixture did not retain its known worker"
      observe backends repeated "84\n")
  , ("force reuse: selected exceptions follow preceding IO", do
      term <- compiledTerm <$> either (fail . show) pure (compile "<force reuse failure>"
        ("let pick = \\flag x y -> if flag then x + x else y + y in " ++
         "do { putStrLn \"before\"; printInt (pick true (panic \"selected force\") " ++
         "(panic \"unused force\")); putStrLn \"after\" }"))
      result <- B.execute backends IOEntry (Input "" False) term
      unless (either ((== "selected force") . show) (const False) (B.outcome result) &&
        B.events result == [B.Write "before\n"]) (fail (show result)))] ++
  [("force reuse: " ++ label, do
      term <- compiledTerm <$> either (fail . show) pure (compile "<force reuse>" source)
      observe backends term expected) | (label,source,expected) <- sources]
  where
    sources =
      [("branch joins retain conditional laziness",
        "let joined = \\flag x y -> (if flag then seq x 3 else seq y 4) + " ++
        "(if flag then x + x else y + y) in do { flag <- ioReturn true; other <- ioReturn false; " ++
        "printInt (joined flag (readInt \"7\") (panic \"unused right after join\")); " ++
        "printInt (joined other (panic \"unused left after join\") (readInt \"8\")) }", "17\n20\n")
      , ("case alternatives isolate forced operands",
        "data Decision = LeftSide | RightSide; let mixed = \\side flag x -> case side of { " ++
        "LeftSide -> x + x; RightSide -> if flag then x * x else 0 } in " ++
        "do { left <- ioReturn LeftSide; right <- ioReturn RightSide; " ++
        "printInt (mixed left false (readInt \"5\")); printInt (mixed right true (readInt \"7\")); " ++
        "printInt (mixed right false (panic \"unselected case subbranch\")) }", "10\n49\n0\n")
      , ("escaping closures preserve forcing and repeated actions",
        "let capture = \\flag x -> if flag then seq x (\\n -> x + n) else (\\n -> n * 2) in " ++
        "do { flag <- ioReturn true; other <- ioReturn false; " ++
        "saved <- ioReturn (capture flag (readInt \"21\")); printInt (saved 4); " ++
        "printInt (capture other (panic \"unused closure capture\") 4); " ++
        "action <- ioReturn (putStrLn \"again\"); action; action }", "25\n8\nagain\nagain\n")]

repeated :: X.Term
repeated = X.Let function (X.Abs flag bool (X.Abs value int body)) $
  X.App (X.Primitive P.PrintInt []) (X.App (X.App (X.VarTerm function) (X.BoolTerm True)) (X.IntTerm 42))
  where
    function = X.Name 0 "repeat"
    flag = X.Name 1 "flag"
    value = X.Name 2 "value"
    int = T.Con "Int" []
    bool = T.Con "Bool" []
    twice = X.App (X.App (X.Primitive P.AddInt []) (X.VarTerm value)) (X.VarTerm value)
    body = X.App (X.App (X.App (X.Primitive P.IfThenElse [int]) (X.VarTerm flag)) twice) (X.IntTerm 0)
