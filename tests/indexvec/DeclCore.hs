{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Monad (unless)
import qualified Bootstrap.CompilerCore as Compiler
import qualified Bootstrap.Constraint as Constraints
import qualified Bootstrap.Surface as Surface
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.Map as M
import qualified Bootstrap.Types as T
import qualified Bootstrap.X.Pretty as Pretty
import qualified MLF.Host.Base as H

compile term = case Compiler.finishCompilation (T.SProgram [] term, M.empty) of
  T.Right result -> Right (H.unpack (Pretty.prettyType (Compiler.inferredType result)),
                           H.unpack (Pretty.prettyTerm (Compiler.compiledTerm result)))
  T.Left err -> Left (H.unpack (Compiler.diagnostic err))

check message test = unless test (error message)

main = do
  let i = V.fromInt 7
      j = V.fromInt 12
      global = T.SGlobal i
      decl slot name rhs body = T.SDeclScope [slot] (T.SLet name rhs body)
      ident = T.SLam "y" T.Nothing (T.SVar "y")
      apply rhs = T.SApp rhs (T.SIntLit 42)
      named = T.SLet "f" ident (apply (T.SVar "f"))
      typed = decl i "f" ident (apply (global "renamed"))
  check "global occurrence hint changed xMLF" (compile named == compile typed && either (const False) (const True) (compile typed))
  let nested readRef = decl i "x" (T.SIntLit 7) (T.SLet "x" (T.SBoolLit True) readRef)
  check "local binder captured global slot" (fmap fst (compile (nested (global "x"))) == Right "Int")
  check "global binder captured lexical occurrence" (fmap fst (compile (nested (T.SVar "x"))) == Right "Bool")
  check "missing slot fell through to lexical lookup"
    (compile (nested (T.SGlobal j "x")) == Left "unbound variable: x")
  let rec a b body = T.SDeclScope [i,j] (T.SLetRec
        [("a",T.InferRecursive,a),("b",T.InferRecursive,b)] body)
      -- j's reference carries i's spelling. Its target is still j.
      typedRec = rec (T.SGlobal j "a") ident (apply (T.SGlobal i "b"))
      namedRec = T.SLetRec [("a",T.InferRecursive,T.SVar "b"),("b",T.InferRecursive,ident)] (apply (T.SVar "a"))
  check "recursive subgroup changed type or xMLF" (compile typedRec == compile namedRec && fmap fst (compile typedRec) == Right "Int")
  check "invalid recursive slot inventory accepted"
    (compile (T.SDeclScope [j] (T.SLetRec [] (T.SIntLit 1))) == Left "recursive declaration slot inventory mismatch")
  let stringPat = T.SIndexedStringPattern (T.ScalarString "ok") (T.DeclRef i "same") (T.DeclRef j "same")
      branch = T.SCase (T.SVar "value") [T.SAlternative stringPat (T.SBoolLit True),
        T.SAlternative (T.SDefaultPattern T.Nothing) (T.SBoolLit False)]
  case Surface.lowerExpression branch of
    T.Right lowered -> check "pattern methods retain distinct slots through matrix lowering"
      ([V.toInt k | T.DeclRef k _ <- Constraints.recursiveRefs (Constraints.desugar lowered)] == [7,12])
    T.Left e -> error (H.unpack e)
  putStrLn "Core declaration slots, lexical shadowing, polymorphic imports and recursion passed"
