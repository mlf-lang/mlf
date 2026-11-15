{-# LANGUAGE OverloadedStrings, DeriveDataTypeable #-}
module Main where
import Prelude
import Control.Exception (Exception,evaluate,throw,try)
import Data.Typeable (Typeable)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.Map as M
import qualified Bootstrap.InferenceUnit as C
import qualified DiagnosticBaseline.InferenceUnit as A
import qualified Bootstrap.OpenFragment as O
import qualified Bootstrap.ArtifactStructure as Structure
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Type as XT

data Probe = Probe String deriving (Eq,Show,Typeable)
instance Exception Probe
sameValue (W.VInt a) (W.VInt b) = a==b
sameValue (W.VBits a) (W.VBits b) = a==b
sameValue (W.VText a) (W.VText b) = P.eqString a b
sameValue (W.VNode a as) (W.VNode b bs) = a==b && length as==length bs && and (zipWith sameValue as bs)
sameValue _ _ = False
sameOwned as bs = length as==length bs && and (zipWith (\(a,ta) (b,tb)->X.equalName a b && P.eqString (X.nameHint a) (X.nameHint b) && XT.alphaEq ta tb) as bs)
assert message b = if b then pure () else error message
dumpValue (W.VInt i) = "I"++show i++";"
dumpValue (W.VBits i) = "B"++show i++";"
dumpValue (W.VText t) = "T"++show (P.textToChars t)++";"
dumpValue (W.VNode i xs) = "N"++show i++"["++concatMap dumpValue xs++"]"
saveSide path result = case result of
  T.Left message -> writeFile (path++".outcome") ("Left "++show (P.textToChars message)++"\n")
  T.Right fragment -> do
    writeFile (path++".outcome") "Right\n"
    writeFile (path++".raw") (dumpValue (O.encodeBody "raw" "fixture" fragment))
    writeFile (path++".typed") (dumpValue (Structure.toXTerm (O.closedTerm fragment)))
-- Same short-circuit comparison order as v1; errors become diagnostic text first.
verdict label expectedRight a b = case (a,b) of
  (T.Left x,T.Left y)->if not expectedRight && P.eqString x y then Right ()
    else Left (label++": expected Right or exact error mismatch")
  (T.Right x,T.Right y)->
    if not expectedRight then Left (label++": unexpected Right")
    else if not (sameValue (O.encodeBody "raw" "fixture" x) (O.encodeBody "raw" "fixture" y)) then Left (label++": raw mismatch")
    else if not (sameValue (Structure.toXTerm (O.closedTerm x)) (Structure.toXTerm (O.closedTerm y))) then Left (label++": typed mismatch")
    else if not (sameOwned (O.bindings x) (O.bindings y) && sameOwned (O.parameters x) (O.parameters y)) then Left (label++": ordered interface mismatch")
    else case (O.audit x,O.audit y) of
      (T.Right _,T.Right _)->Right ()
      _->Left (label++": audit failed")
  _->Left (label++": outcome mismatch")
check label expectedRight a b = do
  result <- evaluate (verdict label expectedRight a b)
  -- Only after the original verdict has been demanded; a/b are shared results,
  -- not repeated calls to source inference. Exceptions are not intercepted.
  writeFile (label++".result") (case result of Left e->"FAIL "++e++"\n";Right _->"PASS\n")
  saveSide (label++"-A") a
  saveSide (label++"-C") b
  case result of Left e->error e;Right _->pure ()

ann=T.Just (T.SAnnotation [] (T.SCon "Int" []))
member annotation body=[(V.fromInt 1,("value",annotation,body))]
indexed label ok ps ds ms = check label ok
  (A.compileOpenGroupIndexed "fixture" ps ds ms) (C.compileOpenGroupIndexed "fixture" ps ds ms)
finish label ok names ds body = check label ok
  (A.finishOpenGroup M.empty names (T.SProgram ds body,M.empty))
  (C.finishOpenGroup M.empty names (T.SProgram ds body,M.empty))
main = do
  indexed "unsigned literal" True [] [] (member T.Nothing (T.SIntLit 7))
  indexed "signed literal" True [] [] (member ann (T.SIntLit 7))
  let tv=T.XTyVar 0; poly=T.XForall tv T.XBot (T.XArrow (T.XVar tv) (T.XVar tv))
      ps=[(V.fromInt 0,"identity",poly)]
      use=T.SApp (T.SGlobal (V.fromInt 0) "identity") (T.SIntLit 7)
  indexed "imports fallback" True ps [] (member ann use)
  let recursive=T.SAnnotation [] (T.SArrow (T.SCon "Int" []) (T.SCon "Int" []))
      recbody=T.SLam "x" T.Nothing (T.SApp (T.SGlobal (V.fromInt 1) "value") (T.SVar "x"))
  indexed "signed recursive" True [] [] (member (T.Just recursive) recbody)
  indexed "datatype" True [] [T.DataDecl "Box" [] [T.ConstructorDecl "Box" []]]
    (member T.Nothing (T.SConstructor "Box"))
  indexed "empty" False [] [] []
  indexed "annotation mismatch" False [] [] (member ann (T.SBoolLit True))
  indexed "duplicate parameter before body" False
    [(V.fromInt 0,"same",T.XCon "Int" []),(V.fromInt 2,"same",T.XCon "Int" [])] []
    (member T.Nothing (throw (Probe "body")))
  finish "owned label mismatch" False [("wrong",T.Nothing,T.SIntLit 7)] []
    (T.SLet "value" (T.SIntLit 7) (T.SConstructor "()"))
  finish "root unit fallback" True [] [] (T.SConstructor "()")
  -- Central deferred-inventory failure: compilation can succeed, but this
  -- declaration spine ends in Int rather than (). Require the exact inventory
  -- error, so an unrelated earlier Left cannot impersonate this coverage.
  let inventoryProgram=T.SProgram [] (T.SLet "value" (T.SIntLit 7) (T.SIntLit 8))
      inventoryNames=[("value",T.Nothing,T.SIntLit 7)]
      inventoryA=A.finishOpenGroup M.empty inventoryNames (inventoryProgram,M.empty)
      inventoryC=C.finishOpenGroup M.empty inventoryNames (inventoryProgram,M.empty)
      inventoryLabel="deferred inventory nonunit tail"
      inventoryError="invalid inference fragment: expected declarations ending in ()"
      inventoryVerdict=case verdict inventoryLabel False inventoryA inventoryC of
        Left e -> Left e
        Right () -> case (inventoryA,inventoryC) of
          (T.Left x,T.Left y) | P.eqString x inventoryError && P.eqString y inventoryError -> Right ()
          _ -> Left (inventoryLabel++": expected exact deferred inventory error")
  inventoryResult <- evaluate inventoryVerdict
  writeFile (inventoryLabel++".result") (case inventoryResult of Left e->"FAIL "++e++"\n";Right _->"PASS\n")
  saveSide (inventoryLabel++"-A") inventoryA
  saveSide (inventoryLabel++"-C") inventoryC
  case inventoryResult of Left e->error e;Right _->pure ()
  -- Compiler failure must precede demand of members/ownership (both are bottom).
  let bad=T.SProgram [] (T.SVar "absent")
  check "compiler error before ownership" False
    (A.finishOpenGroup M.empty (throw (Probe "members")) (bad,M.empty))
    (C.finishOpenGroup M.empty (throw (Probe "members")) (bad,M.empty))
  -- Same tagged synchronous exception at the original source demand; never catch async.
  a<-try (evaluate (A.finishOpenGroup M.empty [] (throw (Probe "source")))) :: IO (Either Probe (T.Either P.String O.Fragment))
  c<-try (evaluate (C.finishOpenGroup M.empty [] (throw (Probe "source")))) :: IO (Either Probe (T.Either P.String O.Fragment))
  let renderProbe result = case result of
        Left probe -> "Probe "++show probe++"\n"
        Right (T.Left message) -> "Returned Left "++show (P.textToChars message)++"\n"
        Right (T.Right _) -> "Returned Right\n"
      matched = case (a,c) of (Left (Probe "source"),Left (Probe "source"))->True;_->False
  writeFile "source-demand-A.outcome" (renderProbe a)
  writeFile "source-demand-C.outcome" (renderProbe c)
  writeFile "source-demand.result" (if matched then "PASS\n" else "FAIL source demand\n")
  assert "source demand" matched
  putStrLn "PASS ordinary checked reuse raw typed interface and error differential"
