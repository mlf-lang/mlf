{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Monad (forM_, unless)
import System.Environment (getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Data as D
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as S
import qualified Bootstrap.X.Check as C
import qualified Bootstrap.X.Checked as K
import qualified Bootstrap.X.Pretty as P
import qualified Bootstrap.X.Type as Y
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.Separate as O
import qualified Bootstrap.CrateArtifact as A
import qualified MLF.Host.Base as B

right label result = case result of
  T.Left message -> fail (label ++ ": " ++ B.unpack message)
  T.Right value -> pure value

sameResult label equal first second = case (first, second) of
  (T.Left a, T.Left b) -> unless (B.v_eqString a b) (fail (label ++ ": rejection changed"))
  (T.Right a, T.Right b) -> unless (equal a b) (fail (label ++ ": result changed"))
  (T.Left message, T.Right _) -> fail (label ++ ": accepted: " ++ B.unpack message)
  (T.Right _, T.Left message) -> fail (label ++ ": rejected: " ++ B.unpack message)

sameBindings left rightBindings = length left == length rightBindings &&
  and [X.compareName a b == 0 && B.v_eqString (X.nameHint a) (X.nameHint b) && Y.alphaEq t u
      | ((a,t),(b,u)) <- zip left rightBindings]

referenceBindings source = case source of
  T.XWithData declarations body -> case D.validateDeclarations declarations of
    T.Left message -> T.Left message
    T.Right ds -> collect ds body
  _ -> collect D.emptyDataEnv source
  where
    collect ds body = let (parameters, implementation) = O.splitParameters body
      in O.collectBindings ds (T.XEnv M.empty (M.fromList X.compareName parameters)) implementation

unit = T.XConstructor "()" []
int = T.XCon "Int" []
name n = T.XName n "value"
withUnit = T.XWithData []
identity n = T.XAbs (name n) int (T.XVarTerm (name n))
polyField = T.DataDecl "Poly" [] [T.ConstructorDecl "Poly"
  [T.Quantified "a" T.Star (T.Function (T.Parameter "a") (T.Parameter "a"))]]

cases =
  [ ("empty", withUnit unit)
  , ("one-let", withUnit (T.XLet (name 1) (T.XIntTerm 2) unit))
  , ("ordered-lets", withUnit (T.XLet (name 7) (T.XIntTerm 2)
      (T.XLet (name 3) (T.XVarTerm (name 7)) unit)))
  , ("rhs-local-excluded", withUnit (T.XLet (name 1)
      (T.XLet (name 2) (T.XIntTerm 4) (T.XVarTerm (name 2))) unit))
  , ("lambda-rhs", withUnit (T.XLet (name 1) (identity 2) unit))
  , ("recursive", withUnit (T.XLetRec [(name 1,int,T.XVarTerm (name 1))] unit))
  , ("mutual-recursive", withUnit (T.XLetRec
      [(name 1,int,T.XVarTerm (name 2)),(name 2,int,T.XVarTerm (name 1))] unit))
  , ("let-after-recursive", withUnit (T.XLetRec [(name 1,int,T.XIntTerm 4)]
      (T.XLet (name 2) (T.XVarTerm (name 1)) unit)))
  , ("empty-recursive", withUnit (T.XLetRec [] unit))
  , ("import-parameter", withUnit (T.XAbs (name 1) int
      (T.XLet (name 2) (T.XVarTerm (name 1)) unit)))
  , ("two-import-parameters", withUnit (T.XAbs (name 1) int
      (T.XAbs (name 2) int (T.XLet (name 3) (T.XVarTerm (name 2)) unit))))
  , ("polymorphic-rhs", withUnit (T.XLet (name 1)
      (T.XTypeAbs (T.XTyVar 5) T.XBot
        (T.XAbs (name 2) (T.XVar (T.XTyVar 5)) (T.XVarTerm (name 2)))) unit))
  , ("quantified-field-fresh-negative-id", T.XWithData [polyField]
      (T.XLet (name 1) (T.XConstructor "Poly" []) unit))
  , ("quantified-field-and-negative-term-id", T.XWithData [polyField]
      (T.XLet (name (-1)) (T.XConstructor "Poly" []) unit))
  , ("valid-nonfragment", T.XIntTerm 1)
  , ("valid-lambda-nonfragment", identity 1)
  , ("lambda-after-declaration", withUnit (T.XLet (name 1) (T.XIntTerm 3)
      (T.XAbs (name 2) int unit)))
  , ("type-abstraction-nonfragment", withUnit (T.XTypeAbs (T.XTyVar 4) T.XBot unit))
  , ("unbound-rhs", withUnit (T.XLet (name 1) (T.XVarTerm (name 90)) unit))
  , ("late-unbound-rhs", withUnit (T.XLet (name 1) (T.XIntTerm 2)
      (T.XLet (name 2) (T.XVarTerm (name 90)) unit)))
  , ("duplicate-let-priority", withUnit (T.XAbs (name 1) int
      (T.XLet (name 1) (T.XVarTerm (name 90)) unit)))
  , ("duplicate-import", withUnit (T.XAbs (name 1) int (T.XAbs (name 1) int unit)))
  , ("open-import-type", withUnit (T.XAbs (name 1) (T.XVar (T.XTyVar 90)) unit))
  , ("duplicate-recursive-priority", withUnit (T.XLetRec
      [(name 1,T.XVar (T.XTyVar 90),T.XIntTerm 1),(name 1,int,T.XIntTerm 2)] unit))
  , ("recursive-shadow-priority", withUnit (T.XAbs (name 1) int (T.XLetRec
      [(name 1,T.XVar (T.XTyVar 90),T.XIntTerm 1)] unit)))
  , ("bad-recursive-signature", withUnit (T.XLetRec [(name 1,int,identity 2)] unit))
  , ("unbound-recursive-rhs", withUnit (T.XLetRec [(name 1,int,T.XVarTerm (name 90))] unit))
  , ("unknown-constructor", withUnit (T.XLet (name 1) (T.XConstructor "Absent" []) unit))
  , ("bad-unit-arguments", withUnit (T.XConstructor "()" [int]))
  , ("nested-data", withUnit (T.XLet (name 1) (withUnit unit) unit))
  , ("duplicate-datatype", T.XWithData [polyField,polyField] unit)
  , ("bad-tail-after-let", withUnit (T.XLet (name 1) (T.XIntTerm 1) (T.XVarTerm (name 90))))
  ]

audit expectedAccepted (label, source) = do
  let ordinary = C.checkClosed source
      checked = K.check source
      projected = case checked of T.Left message -> T.Left message; T.Right value -> T.Right (K.typeOf value)
  sameResult label Y.alphaEq ordinary projected
  unless (expectedAccepted == (case ordinary of T.Right _ -> True; T.Left _ -> False))
    (fail (label ++ ": fixture did not exercise its prescribed acceptance route"))
  case checked of
    T.Left _ -> pure ()
    T.Right value -> do
      sameResult (label ++ " inventory") sameBindings (referenceBindings source) (K.declarationBindings value)
      forM_ [-20,-1,0,41,1000000000000000000000000000000] $ \serial -> do
        let (oldNext,oldTerm) = O.freshObject serial source
            (newNext,newTerm,bindings) = O.freshCheckedObject serial value
        unless (oldNext == newNext && B.v_eqString (P.prettyTerm oldTerm) (P.prettyTerm newTerm))
          (fail (label ++ ": changed fresh term or counter"))
        sameResult (label ++ " fresh inventory") sameBindings (referenceBindings oldTerm) bindings
      let iface = O.UnitInterface "Fixture" [] [] [] [] [] [] ""
      raw <- right label (O.objectChecked (O.UnitObject iface source))
      sameResult (label ++ " raw inventory") sameBindings (K.declarationBindings value) (K.declarationBindings raw)
  putStrLn ("PASS " ++ label)

linkControls = do
  let source = withUnit (T.XLet (T.XName 1 "answer") (T.XIntTerm 4) unit)
      declarations = []
      schemes = [("answer",int)]
      iface = O.UnitInterface "Fixture" [] [] declarations [] [] schemes (O.fingerprint (P.prettyTerm source))
      layouts = M.fromList B.v_compareString [(D.datatypeName d,A.datatypePart d) | d <- declarations]
      emptyState = A.FragmentState 41 M.empty [] [] S.empty
      link object = A.linkFragment layouts S.empty (M.fromList B.v_compareString schemes) emptyState object
  checked <- right "checked fragment" (K.check source)
  raw <- right "raw link" (link (O.UnitObject iface source))
  cached <- right "checked link" (link (O.CheckedUnitObject iface checked))
  unless (map (B.unpack . P.prettyTerm) (A.fragmentBodies raw) == map (B.unpack . P.prettyTerm) (A.fragmentBodies cached))
    (fail "checked fragment changed linked bodies")
  unless (A.fragmentSerial raw == A.fragmentSerial cached) (fail "checked fragment changed link serial")
  let malformed = withUnit (T.XLet (name 2) (T.XVarTerm (name 99)) unit)
      rejected label expected result = case result of
        T.Left actual -> unless (B.v_eqString expected actual) (fail (label ++ ": wrong rejection: " ++ B.unpack actual))
        T.Right _ -> fail (label ++ ": accepted malformed fragment")
      badHash = O.UnitInterface "Fixture" [] [] declarations [] [] schemes "wrong"
      wrongScheme = O.UnitInterface "Fixture" [] [] declarations [] [] [("answer",T.XCon "String" [])]
        (O.fingerprint (P.prettyTerm source))
  rejected "raw unchecked object" "unbound term variable value" (link (O.UnitObject badHash malformed))
  rejected "checked metadata checksum" "inference fragment checksum mismatch" (link (O.CheckedUnitObject badHash checked))
  rejected "checked metadata signature" "crate fragment binding scheme mismatch" (link (O.CheckedUnitObject wrongScheme checked))
  rejected "metadata before invalid term" "duplicate crate inference fragment"
    (A.linkFragment layouts S.empty M.empty (A.FragmentState 0 M.empty [] [] (S.singleton "Fixture"))
      (O.UnitObject badHash malformed))
  putStrLn "PASS checked-link-and-metadata-controls"

main = do
  arguments <- getArgs
  case arguments of
    [] -> do
      forM_ (zip [0 :: Int ..] cases) $ \(index, value) -> audit (index < 18) value
      linkControls
      putStrLn "Checked binding inventory audit: 33 checks passed"
    ["--crate", interfacePath, objectPath] -> do
      metadata <- readFile interfacePath
      bytes <- readFile objectPath
      interface <- right "real interface" (A.decodeInterface (B.v_textFromChars metadata))
      object <- right "real object" (A.decodeObject interface (B.v_textFromChars bytes))
      let fragments = A.objectFragments object
      unless (not (null fragments)) (fail "real crate has no fragments")
      forM_ (zip [0 :: Int ..] fragments) $ \(index, fragment) ->
        audit True ("crate-fragment-" ++ show index, O.objectTerm fragment)
      putStrLn ("Checked real crate binding inventory audit: " ++ show (length fragments) ++ " fragments passed")
    _ -> fail "expected no arguments or --crate INTERFACE OBJECT"
