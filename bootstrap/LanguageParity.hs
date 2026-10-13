-- Native compiler acceptance/type parity against the maintained Haskell seed.
-- Usage: runghc -isrc -itest bootstrap/LanguageParity.hs PATH_TO_STAGE [--core-only]
import qualified Figure12 as F
import MLF.Compiler
import qualified MLF.Syntax as S
import qualified MLF.X.Parser as XP
import qualified MLF.X.Check as XC
import qualified MLF.X.Type as XT
import MLF.X.Pretty (prettyType)
import System.Process
import System.Exit
import System.IO
import System.Environment (getArgs)
import System.Timeout
import Control.Monad
import Data.List
import Control.Exception

pp t = case t of
  S.TVar n -> n
  S.Bottom -> "bot"
  S.Arrow a b -> "(" ++ pp a ++ " -> " ++ pp b ++ ")"
  S.Con c ts -> "(" ++ unwords (c:map pp ts) ++ ")"
  S.Forall S.Flexible n S.Bottom b -> "(forall " ++ n ++ ". " ++ pp b ++ ")"
  S.Forall _ n a b -> "(forall (" ++ n ++ " >= " ++ pp a ++ "). " ++ pp b ++ ")"
  _ -> error "fixture type unsupported"
annotated = concat [ [ "((\\x -> x) : " ++ pp (S.Arrow t t) ++ ")"
                    , "\\(x : " ++ pp t ++ ") -> x"
                    , "let f = ((\\x -> x) : " ++ pp (S.Arrow t t) ++ ") in f"] | t <- nested]
  where
    identity = S.Forall S.Flexible "a" S.Bottom (S.Arrow (S.TVar "a") (S.TVar "a"))
    ts = [S.Bottom,S.Con "Int" [],S.Con "Bool" [],identity,
          S.Forall S.Flexible "a" S.Bottom (S.Con "List" [S.TVar "a"]),
          S.Forall S.Flexible "a" identity (S.Arrow (S.TVar "a") (S.TVar "a"))]
    nested = ts ++ [S.Arrow a b | a <- ts,b <- ts]

check stage label source expected = do
  outcome <- timeout 60000000 (readProcessWithExitCode stage ["--expr",source] "")
  let result = case outcome of
        Nothing -> Left "native compilation exceeded 60 seconds"
        Just (status,out,err) -> case expected of
          Left original ->
            let protected = "cannot raise a protected type variable" `isInfixOf` diagnostic original
                expectedReason = if protected then "cannot raise a protected type variable" else "type constructor mismatch:"
                details = protected || all (`isInfixOf` err) ["Bool","Int"]
            in if status /= ExitSuccess && "Inference:" `isPrefixOf` err && phase original == Inference && expectedReason `isInfixOf` err && details
              then Right () else Left ("rejection mismatch: "++show status++"\n"++err++out)
          Right seed -> if status /= ExitSuccess then Left ("native rejected: "++err) else do
            term <- XP.parseTerm label out
            actual <- XC.checkClosed term
            if XT.alphaEq actual (inferredType seed) then Right () else Left ("type mismatch\nseed "++prettyType(inferredType seed)++"\nstage1 "++prettyType actual)
  case result of
    Left err -> putStrLn ("FAIL "++label++"\n"++err++"\nSOURCE "++source) >> pure False
    Right () -> putStrLn ("PASS "++label) >> pure True

moduleCase stage file = do
  expected <- compileFile [] file
  result <- timeout 60000000 (readProcessWithExitCode stage [file] "")
  let checked = case (expected,result) of
        (Left e,_) -> Left ("seed rejected: "++show e)
        (_,Nothing) -> Left "native module exceeded 60 seconds"
        (Right seed,Just (status,out,err)) -> if status/=ExitSuccess then Left err else do
          target <- XP.parseTerm file out
          actual <- XC.checkClosed target
          if XT.alphaEq actual (inferredType seed) then Right () else Left ("type mismatch: "++prettyType actual++" vs "++prettyType(inferredType seed))
  case checked of
    Left e -> putStrLn ("FAIL module "++file++"\n"++e) >> pure False
    Right () -> putStrLn ("PASS module "++file) >> pure True

main = do
  hSetBuffering stdout LineBuffering
  arguments <- getArgs
  (stage,coreOnly) <- case arguments of
    [path] -> pure (path,False)
    [path,"--core-only"] -> pure (path,True)
    _ -> fail "Usage: LanguageParity.hs PATH_TO_STAGE [--core-only]"
  unless (length F.cases == 43 && length annotated == 126) (fail "parity corpus coverage changed")
  fs <- forM F.cases $ \c -> case F.program c of
    Left e -> putStrLn ("fixture failure "++e) >> pure False
    Right source -> do
      let baseline = compile (F.caseId c) source
          accepted = either (const False) (const True) baseline
      if accepted /= F.expectedAcceptance c then putStrLn ("FAIL seed expectation "++F.caseId c) >> pure False
      else check stage ("Figure12/"++F.caseId c) source baseline
  as <- forM (zip [1::Int ..] annotated) $ \(i,source) -> case compile "annotation" source of
    Left error -> putStrLn ("FAIL seed annotation "++show i++": "++show error) >> pure False
    Right baseline -> check stage ("Annotation/"++show i) source (Right baseline)
  ms <- if coreOnly then pure [] else mapM (moduleCase stage) ["examples/modules/Main.emlf","examples/multiparameter.emlf","examples/monad-state-do.emlf","examples/recursive-data.emlf","examples/io-hello.emlf"]
  putStrLn ("TOTAL Figure12 "++show(length(filter id fs))++"/"++show(length fs)++", annotation "++show(length(filter id as))++"/"++show(length as)++", modules "++show(length(filter id ms))++"/"++show(length ms))
  unless (and(fs++as++ms)) exitFailure
