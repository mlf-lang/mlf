-- Query boundary regressions for sharing-preserving LLVM simplification.
module OptimizerQueries (optimizerQueryTests) where

import Control.Monad (forM_, unless)
import qualified MLF.LLVM.Optimize as O
import qualified MLF.X.Syntax as X

name :: Int -> X.Name
name n = X.Name n "reused"

-- The body is a value, so the optimizer cannot erase the binding merely
-- because the consumer does not use its fields.
pair :: X.Erased -> X.Erased -> X.Erased
pair a b = X.EApp (X.EApp (X.EConstructor "Pair") a) b

function :: Int -> X.Erased
function nodes = foldr (X.EAbs . name) (X.EVar (name 1)) [1 .. nodes - 1]

lets :: X.Erased -> Int
lets expression = case expression of
  X.EAbs _ b -> lets b
  X.EApp f a -> lets f + lets a
  X.ELet _ a b -> 1 + lets a + lets b
  X.ELetRec ds b -> length ds + sum (map (lets . snd) ds) + lets b
  X.ECase a bs -> lets a + sum [lets b | X.ErasedAlternative _ b <- bs]
  _ -> 0

optimizerQueryTests :: [(String, IO ())]
optimizerQueryTests =
  [ ("optimizer queries: inclusive small-lambda size boundary", forM_ [20..28] $ \nodes -> do
      let f = name 100
          term = X.ELet f (function nodes) (pair (X.EVar f) (X.EVar f))
          wanted = if nodes <= 24 then 0 else 1
      unless (lets (O.optimize term) == wanted)
        (fail ("lambda size threshold changed at " ++ show nodes)))
  , ("optimizer queries: zero, one, and multiple lambda uses", forM_ [0..5] $ \uses -> do
      let f = name 100
          body = foldr pair (X.EInt 42) (replicate uses (X.EVar f))
          term = X.ELet f (function 80) body
          wanted = if uses <= 1 then 0 else 1
      unless (lets (O.optimize term) == wanted)
        (fail ("lambda occurrence count changed at " ++ show uses)))
  , ("optimizer queries: disjoint scopes reuse an identity", do
      let n = name 0
          term = X.ELet n (X.EApp (X.EConstructor "Keep") (X.EInt 19))
            (X.ELet n (X.EInt 42) (X.EVar n))
      unless (O.optimize term == X.EInt 42) (fail "a shadowed outer binding survived"))
  , ("optimizer queries: captured and recursive uses remain shared", do
      let f = name 100
          loop = name 101
          argument = name 102
          rhs = X.EAbs argument (pair (X.EVar f) (X.EApp (X.EVar loop) (X.EVar argument)))
          term = X.ELet f (function 80)
            (X.ELetRec [(loop,rhs)] (pair (X.EVar f) (X.EVar loop)))
      unless (lets (O.optimize term) == 2) (fail "a multiply captured lambda was duplicated"))
  , ("optimizer queries: pattern binders keep their own identity", do
      let n = name 0
          term = X.ELet n (function 80) (X.ECase (X.EVar (name 1))
            [X.ErasedAlternative (X.ConstructorPattern "Keep" [Just n]) (X.EVar n)])
      unless (lets (O.optimize term) == 0) (fail "a pattern occurrence retained an unrelated binding"))
  ]
