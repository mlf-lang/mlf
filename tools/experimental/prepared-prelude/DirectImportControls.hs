{-# LANGUAGE OverloadedStrings #-}
-- Host-only independent controls for the opt-in direct import prototype.
-- These use the unchanged synthetic-prefix compiler as the principal-type
-- oracle; malformed boundary controls additionally assert exact diagnostics.
module Main where

import Prelude hiding (Either(..), Maybe(..))
import Bootstrap.Types hiding (Import)
import qualified Bootstrap.CompilerCore as Core
import qualified Bootstrap.PreparedImportedCore as Imported
import qualified Bootstrap.Map as M
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Type as T
import qualified Bootstrap.X.Pretty as Pretty
import qualified MLF.Primitive as P
import qualified System.IO as IO
import System.Exit (exitFailure)

type Import = (P.String, SType, XType)

failControl :: String -> String -> IO a
failControl label message = do
  IO.hPutStrLn IO.stderr ("FAIL " ++ label ++ ": " ++ message)
  exitFailure

pass :: String -> IO ()
pass label = putStrLn ("PASS " ++ label)

text = P.textToChars
renderType = text . Pretty.prettyType
renderError = text . Core.prettyError

signatures :: [Import] -> Map P.String XType
signatures imports = M.fromList P.compareString [(name, ty) | (name, _, ty) <- imports]

placeholder :: Import -> (P.String, RecursiveMode, SExpr)
placeholder (name, ty, _) =
  (name, CheckRecursive (SAnnotation [] ty),
   SChecked ty (SApp (SPrimitive PPanic) (SStringLit "unlinked module parameter")))

program :: [Import] -> SExpr -> SProgram
program imports body = SProgram []
  (if null imports then body else SLetRec (map placeholder imports) body)

ordinary imports body = Core.finishCompilation (program imports body, M.empty)
direct imports body = Imported.finishCompilation (signatures imports) (program imports body, M.empty)

positive :: String -> [Import] -> SExpr -> IO ()
positive label imports body = case (ordinary imports body, direct imports body) of
  (Right before, Right after) -> do
    if T.alphaEq (Core.inferredType before) (Imported.inferredType after)
      then pure ()
      else failControl label ("principal types differ: " ++ renderType (Core.inferredType before) ++
                             " / " ++ renderType (Imported.inferredType after))
    -- This checks the independently closed import wrapper again. Its result is
    -- deliberately compared with import arrows, not the user-only type.
    let expected = foldr XArrow (Imported.inferredType after) (M.elems (signatures imports))
    case Checked.check (Checked.term (Imported.checkedWrapper after)) of
      Left message -> failControl label ("wrapper recheck failed: " ++ text message)
      Right checked ->
        if T.alphaEq expected (Checked.typeOf checked)
          then pass label
          else failControl label "checked wrapper lost its exact import prefix"
  (Left before, _) -> failControl label ("positive reference rejected: " ++ renderError before)
  (_, Left after) -> failControl label ("positive direct route rejected: " ++ renderError after)

negativeSource :: String -> [Import] -> SExpr -> P.String -> IO ()
negativeSource label imports body expected = case (ordinary imports body, direct imports body) of
  (Left before, Left after) ->
    if P.eqString (Core.prettyError before) expected && P.eqString (Core.prettyError after) expected
      then pass label
      else failControl label ("unexpected source diagnostics: " ++ renderError before ++ " / " ++ renderError after)
  _ -> failControl label "both routes must reject the source"

negativeImported :: String -> Map P.String XType -> SProgram -> P.String -> IO ()
negativeImported label contracts source expected =
  case Imported.finishCompilation contracts (source, M.empty) of
    Left actual | P.eqString (Core.prettyError actual) expected -> pass label
    Left actual -> failControl label ("unexpected admission diagnostic: " ++ renderError actual)
    Right _ -> failControl label "malformed import boundary was accepted"

closeAvailable :: Map P.String (XName, XType) -> XTerm -> XTerm
closeAvailable available term = foldr (\(name, ty) body -> XAbs name ty body) term (M.elems available)

positiveRemove :: String -> Map P.String XType -> Map P.String (XName, XType) -> XTerm -> XTerm -> IO ()
positiveRemove label contracts available wrapper expected =
  case Imported.remove contracts available wrapper of
    Left message -> failControl label (text message)
    Right actual -> do
      if X.equalErased (X.erase actual) (X.erase expected)
        then pure () else failControl label "removal changed exact erased identity/binder structure"
      case (Checked.check (closeAvailable available actual), Checked.check (closeAvailable available expected)) of
        (Right first, Right second) | T.alphaEq (Checked.typeOf first) (Checked.typeOf second) -> pass label
        (Left message, _) -> failControl label ("substituted result failed checker: " ++ text message)
        (_, Left message) -> failControl label ("control expectation failed checker: " ++ text message)
        _ -> failControl label "removal changed result type abstractions"

negativeRemove :: String -> Map P.String XType -> Map P.String (XName, XType) -> XTerm -> P.String -> IO ()
negativeRemove label contracts available wrapper expected =
  case Imported.remove contracts available wrapper of
    Left actual | P.eqString actual expected -> pass label
    Left actual -> failControl label ("unexpected removal diagnostic: " ++ text actual)
    Right _ -> failControl label "malformed wrapper was accepted"

sInt = SCon "Int" []
sBool = SCon "Bool" []
xInt = XCon "Int" []
xBool = XCon "Bool" []
sIdentity = SForall Flexible "a" SBottom (SArrow (STVar "a") (STVar "a"))
-- Deliberately unrelated negative IDs test alpha-equivalence against the
-- graph-allocated declaration/proof IDs, including nested bounded schemes.
xIdentity = XForall (XTyVar (-701)) XBot (XArrow (XVar (XTyVar (-701))) (XVar (XTyVar (-701))))
identityImport = ("external", sIdentity, xIdentity)
integerImport = ("external", sInt, xInt)
identity = SLam "x" Nothing (SVar "x")

main :: IO ()
main = do
  let boundedSource = SForall Flexible "a" sIdentity (SArrow (STVar "a") (STVar "a"))
      boundedTarget = XForall (XTyVar (-702)) xIdentity
        (XArrow (XVar (XTyVar (-702))) (XVar (XTyVar (-702))))
      higherSource = SArrow sIdentity sBool
      higherTarget = XArrow xIdentity xBool
      kindSource = SForall Flexible "f" (SBottomKind (KArrow Star Star))
        (SForall Flexible "a" SBottom
          (SArrow (STypeApp (STVar "f") (STVar "a")) (STypeApp (STVar "f") (STVar "a"))))
      applied = XApply (XVar (XTyVar (-703))) (XVar (XTyVar (-704)))
      kindTarget = XForall (XTyVar (-703)) (XBotKind (KArrow Star Star))
        (XForall (XTyVar (-704)) XBot (XArrow applied applied))
      constantSource = SForall Flexible "a" SBottom
        (SForall Flexible "b" SBottom (SArrow (STVar "a") (SArrow (STVar "b") (STVar "a"))))
      constantTarget = XForall (XTyVar (-705)) XBot
        (XForall (XTyVar (-706)) XBot
          (XArrow (XVar (XTyVar (-705))) (XArrow (XVar (XTyVar (-706))) (XVar (XTyVar (-705))))))

  positive "polymorphic-independent-uses" [identityImport]
    (SLet "first" (SApp (SVar "external") (SIntLit 1)) (SApp (SVar "external") (SBoolLit True)))
  positive "polymorphic-import-returned" [identityImport] (SVar "external")
  positive "higher-rank-import-application" [("external", higherSource, higherTarget)]
    (SApp (SVar "external") identity)
  positive "bounded-import-returned" [("external", boundedSource, boundedTarget)] (SVar "external")
  positive "bounded-import-application" [("external", boundedSource, boundedTarget)]
    (SApp (SVar "external") identity)
  positive "higher-kinded-import-returned" [("external", kindSource, kindTarget)] (SVar "external")
  positive "nested-polymorphic-import" [("external", constantSource, constantTarget)]
    (SApp (SApp (SVar "external") (SIntLit 7)) (SBoolLit True))
  positive "unused-higher-rank-import" [("external", higherSource, higherTarget)] identity
  positive "local-source-shadowing" [identityImport] (SLam "external" Nothing (SVar "external"))
  positive "let-source-shadowing" [identityImport] (SLet "external" (SIntLit 4) (SVar "external"))
  positive "returned-user-lambda" [identityImport]
    (SLet "used" (SApp (SVar "external") (SBoolLit True)) identity)
  positive "returned-user-constant-lambda" [identityImport]
    (SLet "used" (SApp (SVar "external") (SBoolLit True))
      (SLam "x" Nothing (SLam "y" Nothing (SVar "x"))))
  positive "zero-imports-polymorphic-root" [] identity
  positive "zero-imports-empty-user-group" [] (SLetRec [] identity)
  negativeSource "unused-invalid-user-rhs-retained" [identityImport]
    (SLet "unused" (SVar "missing") (SIntLit 0)) "Inference: unbound variable: missing"
  negativeSource "invalid-user-body-retained" [identityImport]
    (SVar "missing") "Inference: unbound variable: missing"

  let one = signatures [integerImport]
      two = signatures [("a", sInt, xInt), ("b", sInt, xInt)]
      pInt = placeholder integerImport
      pA = placeholder ("a", sInt, xInt)
      pB = placeholder ("b", sInt, xInt)
  negativeImported "missing-source-prefix" one (SProgram [] (SIntLit 0))
    "Inference: direct import parameters are missing from lowered root"
  negativeImported "missing-source-parameter" one (SProgram [] (SLetRec [] (SIntLit 0)))
    "Inference: direct import parameter inventory mismatch"
  negativeImported "duplicate-source-parameter" one (SProgram [] (SLetRec [pInt, pInt] (SIntLit 0)))
    "Inference: direct import parameter inventory mismatch"
  negativeImported "source-parameter-order" two (SProgram [] (SLetRec [pB, pA] (SIntLit 0)))
    "Inference: direct import parameter inventory mismatch"
  negativeImported "non-placeholder-rhs" one
    (SProgram [] (SLetRec [("external", CheckRecursive (SAnnotation [] sInt), SChecked sInt (SIntLit 1))] (SIntLit 0)))
    "Inference: direct import parameter is not an authenticated placeholder"
  negativeImported "wrong-placeholder-message" one
    (SProgram [] (SLetRec [("external", CheckRecursive (SAnnotation [] sInt),
      SChecked sInt (SApp (SPrimitive PPanic) (SStringLit "different")))] (SIntLit 0)))
    "Inference: direct import parameter is not an authenticated placeholder"
  negativeImported "open-target-contract" (M.fromList P.compareString [("external", XVar (XTyVar 9))])
    (program [integerImport] (SIntLit 0)) "Inference: direct import contract is not closed"
  negativeImported "wrong-target-contract" (M.fromList P.compareString [("external", xBool)])
    (program [integerImport] (SIntLit 0)) "Verification: direct import declaration changed its contract: external"
  -- Source annotation validation precedes import inventory validation.
  negativeImported "source-error-before-inventory" one
    (SProgram [] (SLetRec [("bad", CheckRecursive (SAnnotation [] (STVar "unbound")), SIntLit 0)] (SIntLit 0)))
    "Inference: unbound annotation type variable: unbound"

  let importedName = XName 10 "external"
      exportedName = XName 1000 "libraryExport"
      userName = XName 11 "external"
      available = M.fromList P.compareString [("external", (exportedName, xInt))]
      empty = M.empty
      wrap body = XAbs importedName xInt (XLetRec [] body)
      userLambda = XAbs userName xInt (XVarTerm userName)
      typeName = XTyVar 50
      typeLambda = XTypeAbs typeName XBot (XAbs userName (XVar typeName) (XVarTerm userName))
  positiveRemove "remove-exact-one-returned-lambda" one available (wrap userLambda) userLambda
  positiveRemove "remove-import-reference" one available (wrap (XVarTerm importedName)) (XVarTerm exportedName)
  positiveRemove "remove-preserves-user-type-abstraction" one available
    (XAbs importedName xInt (XTypeAbs typeName XBot (XLetRec [] (XAbs userName (XVar typeName) (XVarTerm userName)))))
    typeLambda
  positiveRemove "remove-preserves-type-application" one available
    (XAbs importedName xInt (XTypeApp (XLetRec [] (XIntTerm 1)) XRefl))
    (XTypeApp (XIntTerm 1) XRefl)
  positiveRemove "zero-remove-keeps-user-group" empty empty (XLetRec [] userLambda) (XLetRec [] userLambda)
  positiveRemove "zero-remove-keeps-user-type-abstraction" empty empty typeLambda typeLambda
  negativeRemove "missing-target-wrapper" one available (XIntTerm 1) "direct import wrapper lost a parameter"
  negativeRemove "wrong-target-wrapper-name" one available
    (XAbs (XName 10 "other") xInt (XLetRec [] (XIntTerm 1))) "direct import wrapper mismatch: external"
  negativeRemove "wrong-target-wrapper-type" one available
    (XAbs importedName xBool (XLetRec [] (XIntTerm 1))) "direct import wrapper mismatch: external"
  negativeRemove "polymorphic-wrapper-type-mismatch" one available
    (XAbs importedName xIdentity (XLetRec [] (XIntTerm 1))) "direct import wrapper mismatch: external"
  negativeRemove "missing-synthetic-empty-group" one available (XAbs importedName xInt (XIntTerm 1))
    "direct import elaboration lost its empty scope wrapper"
  negativeRemove "nonempty-user-group-not-synthetic" one available
    (XAbs importedName xInt (XLetRec [(userName, xInt, XIntTerm 1)] (XVarTerm userName)))
    "direct import elaboration lost its empty scope wrapper"
  negativeRemove "missing-export" one empty (wrap (XIntTerm 1)) "missing direct import symbol: external"
  negativeRemove "wrong-export-type" one (M.fromList P.compareString [("external", (exportedName, xBool))])
    (wrap (XIntTerm 1)) "direct import symbol type mismatch: external"
  negativeRemove "capture-existing-user-identity" one (M.fromList P.compareString [("external", (userName, xInt))])
    (wrap userLambda) "direct import substitution would capture an identity: external"
  negativeRemove "capture-existing-type-identity" one (M.fromList P.compareString [("external", (XName 50 "export", xInt))])
    (wrap typeLambda) "direct import substitution would capture an identity: external"
  negativeRemove "nested-binder-reuses-import-identity" one available
    (wrap (XAbs importedName xInt (XVarTerm importedName))) "direct import body rebinds a parameter identity"
  let availableTwo = M.fromList P.compareString [("a", (XName 1000 "ea", xInt)), ("b", (XName 1001 "eb", xInt))]
      aName = XName 10 "a"
      bName = XName 11 "b"
  positiveRemove "remove-exact-two-returned-lambda" two availableTwo
    (XAbs aName xInt (XAbs bName xInt (XLetRec [] (XAbs (XName 12 "b") xInt (XVarTerm (XName 12 "b"))))))
    (XAbs (XName 12 "b") xInt (XVarTerm (XName 12 "b")))
  negativeRemove "target-wrapper-order" two availableTwo
    (XAbs bName xInt (XAbs aName xInt (XLetRec [] (XIntTerm 1)))) "direct import wrapper mismatch: a"
  negativeRemove "duplicate-target-wrapper-identities" two availableTwo
    (XAbs aName xInt (XAbs (XName 10 "b") xInt (XLetRec [] (XIntTerm 1))))
    "direct import wrapper reused a binder identity"
  let ambiguous = M.fromList P.compareString [("x!", xInt), ("mlfInternal_120_33", xInt)]
  negativeRemove "noninjective-display-hints" ambiguous empty (XIntTerm 1)
    "direct import source hints are ambiguous"
  putStrLn "PASS all independent direct import controls"
