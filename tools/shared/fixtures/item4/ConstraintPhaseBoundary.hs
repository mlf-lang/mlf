{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import qualified Bootstrap.Types as T
import qualified Bootstrap.Constraint as Q
import qualified Bootstrap.Compiler as C
import qualified Bootstrap.Data as D
import qualified Bootstrap.X.Check as Check
import qualified MLF.Host.Base as B
import Data.List (isInfixOf)
import Control.Exception (try,evaluate,SomeException)
nodeCases = [("source",T.SSourceDefinition (T.SIntLit 42)),("site",T.SCallSite "f" (T.SourceSpan "p" "M" "f" 1 1 1 2) (T.SIntLit 42)),("bind",T.SSharedBind (T.SDefaultPattern T.Nothing) (T.SIntLit 0) (T.SIntLit 42) (T.SLam "x" T.Nothing (T.SLam "k" T.Nothing (T.SApp (T.SVar "k") (T.SVar "x")))) (T.SVar "fail"))]
expected label | "source" `isInfixOf` label = "source definition provenance escaped class lowering"
               | "site" `isInfixOf` label = "source call site escaped class lowering"
               | otherwise = "shared pattern bind escaped surface lowering"
reject label result = case result of
 T.Left e -> if expected label == B.unpack e then putStrLn ("PASS "++label++" REJECT "++B.unpack e) else error ("wrong diagnostic: "++B.unpack e)
 T.Right _ -> error ("accepted "++label)
accept label p = case C.compileProgram p of
 T.Left e -> error (label++" "++B.unpack (C.prettyError e))
 T.Right c -> case Check.checkClosed (C.compiledTerm c) of
  T.Left e -> error (B.unpack e)
  T.Right _ -> putStrLn ("PASS "++label)
main = do
 mapM_ (\(label,e)->do
   reject (label++"-unused-let") (Q.validateAnnotations D.emptyDataEnv (T.SLet "unused" e (T.SIntLit 42)))
   reject (label++"-validate") (Q.validateAnnotations D.emptyDataEnv e)
   if label == "bind" then case Q.generateProgram (T.SProgram [] e) of {T.Right _ -> putStrLn "PASS bind-generate-surface-lowered"; T.Left err -> error (B.unpack err)} else reject (label++"-generate") (Q.generateProgram (T.SProgram [] e))
   v <- try (evaluate (Q.desugar e)) :: IO (Either SomeException T.Core)
   case v of {Left err -> if expected label `isInfixOf` show err then putStrLn ("PASS "++label++"-desugar REJECT "++show err) else error (show err); Right _ -> error (label++" desugar accepted")}) nodeCases
 accept "ordinary-core" (T.SProgram [] (T.SIntLit 42))
 mapM_ (\(label,e)->accept (label++"-compiler") (T.SProgram [] e)) nodeCases
 negative "distinct-list" "data List a = Nil | Cons a (List a)\nf :: List Int -> Int\nf _ = 0\nmain = f [1]" "inference" "type constructor mismatch"
 negative "missing-eq" "data Key = Key Int\ninstance IsString Key where { fromString _ = Key 0 }\nf :: Key -> Int\nf \"x\" = 1\nf _ = 0\nmain = f (Key 0)" "resolution" "no instance or given constraint for MLF.Primitive.Eq Key"



negative label body expectedPhase needle = case C.compile "Negative.emlf" (B.literal body) of
 T.Right _ -> error (label++" accepted")
 T.Left e@(T.CompileError phase msg) -> if phaseOK expectedPhase phase && needle `isInfixOf` B.unpack msg then putStrLn ("PASS "++label++" "++B.unpack (C.prettyError e)) else error (B.unpack (C.prettyError e))
phaseOK "inference" T.Inference = True
phaseOK "resolution" T.Resolution = True
phaseOK _ _ = False
