{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
module Main where
import Prelude
import Control.Exception (SomeException, try, evaluate, displayException)
import Control.Monad (forM_)
import Data.String (fromString)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.Constraint as C
import qualified Bootstrap.CompilerCore as Compiler
import qualified Bootstrap.Map as M
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.Graph as G
import qualified Bootstrap.X.Pretty as XP
import qualified SessionOracle as O
import qualified V1FrozenSession as F
import qualified V1SessionUnderTest as N

ident = T.SLam "x" T.Nothing (T.SVar "x")
app = T.SApp
var = T.SVar
lam n = T.SLam n T.Nothing
program = T.SProgram []
yes n e = (n, True, program e)
no n e = (n, False, program e)
cases =
 [yes "integer" (T.SIntLit 42)
 ,yes "boolean" (T.SBoolLit True)
 ,yes "identity" ident
 ,yes "identity applied" (app ident (T.SIntLit 1))
 ,yes "composition" (lam "f" (lam "g" (lam "x" (app (var "f") (app (var "g") (var "x"))))))
 ,yes "polymorphic let" (T.SLet "id" ident (T.SLet "a" (app (var "id") (T.SIntLit 1)) (app (var "id") (T.SBoolLit True))))
 ,yes "self instantiation" (T.SLet "id" ident (app (var "id") (var "id")))
 ,yes "captured scope" (lam "x" (T.SLet "k" (lam "y" (var "x")) (app (var "k") (T.SBoolLit True))))
 ,yes "shadowing" (lam "x" (app (lam "x" (var "x")) (T.SIntLit 0)))
 ,yes "higher order" (T.SLet "twice" (lam "f" (lam "x" (app (var "f") (app (var "f") (var "x"))))) (app (app (var "twice") ident) (T.SIntLit 2)))
 ,yes "unsigned recursion flush" (T.SLetRec [("f", T.InferRecursive, ident)] (app (var "f") (T.SIntLit 1)))
 ,yes "mutual recursion flush" (T.SLetRec [("f", T.InferRecursive, lam "x" (app (var "g") (var "x"))), ("g", T.InferRecursive, ident)] (app (var "f") (T.SBoolLit True)))
 ,no "unbound" (var "missing")
 ,no "first unbound" (app (var "firstMissing") (var "secondMissing"))
 ,no "integer application" (app (T.SIntLit 1) (T.SBoolLit True))
 ,no "higher order mismatch" (app (lam "x" (app (var "x") (T.SIntLit 1))) (T.SIntLit 0))]
 ++ [yes ("nested identity lets " ++ show n)
      (foldr (\i body -> T.SLet (fromString ("id"++show i)) ident body)
       (T.SIntLit 7) [1..n]) | n <- [2,8,32,64::Int]]

resultText answer = case answer of
 T.Left e -> "Left " ++ B.unpack (Compiler.prettyError e)
 T.Right c -> "Right " ++ B.unpack (XP.prettyTerm (Compiler.compiledTerm c))
             ++ " :: " ++ B.unpack (Compiler.sourceType c)
observe answer = do
 let text = resultText answer
 evaluated <- try (evaluate (foldr (\c z -> fromEnum c + z) 0 text)) :: IO (Either SomeException Int)
 pure $ case evaluated of Left e -> "exception " ++ displayException e; Right _ -> text

checkProgram (name, expected, p) = do
 let old = F.finishCompilation (p, M.empty)
     new = N.finishCompilation (p, M.empty)
 oldText <- observe old
 newText <- observe new
 O.assert (name ++ ": exact checked term/type/error") (oldText == newText)
 case old of
  T.Left _ -> O.assert (name ++ ": authored rejection") (not expected)
  T.Right a -> do
   O.assert (name ++ ": authored acceptance") expected
   case new of
    T.Left _ -> errorWithoutStackTrace (name ++ ": new rejection")
    T.Right b -> O.assert (name ++ ": raw presolution")
      (O.sameGraphPhysical (Compiler.presolution a) (Compiler.presolution b))
 case C.generateProgram p of
  T.Left _ -> pure ()
  T.Right c -> do
   O.checkOutcome (name ++ ": generated boundary") True (F.solvePrepared c) (N.solveGenerated c)
   O.checkOutcome (name ++ ": arbitrary entry retained") True (F.solvePrepared c) (N.solvePrepared c)
   let T.Constraints graph _ equations steps = c
       partial = T.Constraints graph (errorWithoutStackTrace "unused skeleton") equations steps
   O.checkOutcome (name ++ ": skeleton demand") True (F.solvePrepared partial) (N.solveGenerated partial)

main = do
 forM_ cases checkProgram
 let base = T.Graph (IM.fromList [(0,T.Node (T.GGen 1) T.Nothing T.Flexible),
                                 (1,T.Node T.GBot (T.Just 0) T.Flexible)]) IM.empty 2
     badGraphs = [T.Graph (G.nodes base) IM.empty (-1),
                  T.Graph (G.nodes base) (IM.singleton 0 1) 2,
                  T.Graph (IM.insert 1 (T.Node T.GBot (T.Just 99) T.Flexible) (G.nodes base)) IM.empty 2]
 forM_ (zip [0::Int ..] badGraphs) $ \(i,g) -> do
  let c = T.Constraints g (errorWithoutStackTrace "unused bad skeleton") [] []
  case F.solvePrepared c of
   T.Right _ -> errorWithoutStackTrace "malformed control unexpectedly valid"
   T.Left _ -> O.checkOutcome ("raw rejection " ++ show i) True (F.solvePrepared c) (N.solvePrepared c)
 let demand = [T.SClassProgram (errorWithoutStackTrace "unused class data") [] [] (errorWithoutStackTrace "unused class body"),
               T.SProgram (errorWithoutStackTrace "declarations first") (errorWithoutStackTrace "body second"),
               program (app (errorWithoutStackTrace "function first") (errorWithoutStackTrace "argument second")),
               program (T.SLet "unused" (errorWithoutStackTrace "rhs still demanded") (T.SIntLit 1))]
 forM_ (zip [0::Int ..] demand) $ \(i,p) -> do
  a <- observe (F.finishCompilation (p,M.empty))
  b <- observe (N.finishCompilation (p,M.empty))
  O.assert ("demand/order " ++ show i) (a == b)
 putStrLn "PASS validation reuse: 20 authored programs, raw solver states, skeleton demand, 3 raw rejections, 4 partial-value orders"
