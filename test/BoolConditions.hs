-- Raw checked lowering proves that the ordinary condition path is active;
-- independent interpreter/native observations cover its evaluation boundary.
module BoolConditions (boolConditionTests) where

import Control.Monad (unless)
import Data.List (isInfixOf)
import qualified Data.Map.Strict as Map
import Backends (Backends, Entry (..), Input (..))
import qualified Backends as B
import MLF.Compiler (compile, compiledTerm)
import qualified MLF.LLVM.Codegen as Codegen
import qualified MLF.Primitive as P
import qualified MLF.X.Check as Check
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

checked :: String -> IO X.Term
checked = either (fail . show) (pure . compiledTerm) . compile "<Boolean condition>"

observe :: Backends -> Input -> X.Term -> String -> IO ()
observe backends input term expected = do
  result <- B.execute backends IOEntry input term
  either (fail . show) pure (B.outcome result)
  unless (B.output result == expected) (fail (show result))

boolConditionTests :: Backends -> [(String,IO ())]
boolConditionTests backends =
  [("Boolean conditions: checked ordinary branches compare forced canonical Bool", do
      _ <- either fail pure (Check.checkClosed ordinaryCondition)
      (_,code) <- either fail pure (Codegen.generate (Map.singleton "Unit" (0,0)) (X.erase ordinaryCondition))
      let llvm = unlines code
      unless ("call ptr @mlf_force(ptr %arg)" `isInfixOf` llvm &&
        any (\line -> "icmp eq ptr " `isInfixOf` line && ", inttoptr (i64 6 to ptr)" `isInfixOf` line) (lines llvm) &&
        not ("call i64 @mlf_truth(" `isInfixOf` llvm) &&
        not ("define private ptr @mlf.numeric." `isInfixOf` llvm))
        (fail "ordinary conditional did not force and compare its canonical Boolean")
      observe backends (Input "" False) ordinaryCondition "yes\n")
  , ("Boolean conditions: runtime producers agree on both branches", do
      term <- checked producerSource
      observe backends (Input "same\n" False) term (concat (replicate 7 "true\nfalse\n")))
  , ("Boolean conditions: lazy fields captures and partial primitives", do
      term <- checked lazySource
      observe backends (Input "" False) term "before\nyes\nno\ncaptured\npartial\nfield true\nfield false\nafter\n")
  ] ++
  [("Boolean conditions: " ++ label, do
      term <- checked source
      result <- B.execute backends IOEntry (Input "" False) term
      unless (either ((== message) . show) (const False) (B.outcome result) &&
        B.events result == [B.Write "before\n"]) (fail (show result)))
    | (label,source,message) <-
      [("condition failure follows preceding IO",
        "do { putStrLn \"before\"; flag <- ioReturn (panic \"condition failure\"); " ++
        "if flag then putStrLn \"selected\" else putStrLn \"other\"; putStrLn \"after\" }",
        "condition failure")
      , ("selected branch failure follows preceding IO",
        "do { putStrLn \"before\"; flag <- ioReturn true; " ++
        "if flag then panic \"selected failure\" else panic \"unselected failure\"; putStrLn \"after\" }",
        "selected failure")]]

ordinaryCondition :: X.Term
ordinaryCondition = X.App (X.Abs flag (T.Con "Bool" []) body) comparison
  where
    flag = X.Name 0 "flag"
    ioUnit = T.Con "IO" [T.Con "Unit" []]
    output = X.App (X.Primitive P.PutStrLn []) . X.StringTerm
    body = X.App (X.App (X.App (X.Primitive P.IfThenElse [ioUnit]) (X.VarTerm flag)) (output "yes")) (output "no")
    comparison = X.App (X.App (X.Primitive P.EqString []) (X.StringTerm "same")) (X.StringTerm "same")

producerSource :: String
producerSource =
  "let showBool = \\flag -> if flag then putStrLn \"true\" else putStrLn \"false\" in " ++
  "do { yes <- ioReturn true; no <- ioReturn false; showBool yes; showBool no; " ++
  "small <- ioReturn (readInt \"1\"); large <- ioReturn (readInt \"123456789012345678901234567890\"); " ++
  "showBool (eqInt small small); showBool (eqInt small large); showBool (ltInt small large); " ++
  "showBool (ltInt large small); d <- ioReturn (readDouble \"1.5\"); " ++
  "showBool (eqDouble d d); showBool (eqDouble d 2.5); showBool (ltDouble d 2.5); showBool (ltDouble 2.5 d); " ++
  "line <- getLine; showBool (eqString line \"same\"); showBool (eqString line \"other\"); " ++
  "path <- getExecutablePath; present <- fileExists path; showBool present; " ++
  "absent <- fileExists \"\"; showBool absent }"

lazySource :: String
lazySource =
  "data Flags = Flags Bool Bool Bool; " ++
  "let select = \\flag left right -> if flag then left else right in " ++
  "do { yes <- ioReturn true; no <- ioReturn false; " ++
  "putStrLn \"before\"; putStrLn (select yes \"yes\" (panic \"unused false\")); " ++
  "putStrLn (select no (panic \"unused true\") \"no\"); " ++
  "capture <- ioReturn (if yes then (\\text -> select no (panic \"captured unused\") text) " ++
  "else (panic \"unused closure\")); putStrLn (capture \"captured\"); " ++
  "opaque <- ioReturn ifThenElse; putStrLn (opaque yes \"partial\" (panic \"unused generic\")); " ++
  "flags <- ioReturn (Flags yes (panic \"unused field\") no); " ++
  "case flags of { Flags first _ third -> do { " ++
  "putStrLn (if first then \"field true\" else panic \"wrong first\"); " ++
  "putStrLn (if third then panic \"wrong third\" else \"field false\") } }; " ++
  "putStrLn \"after\" }"
