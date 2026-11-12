{-# LANGUAGE OverloadedStrings, DeriveDataTypeable #-}
-- SOURCE ONLY: NOT COMPILED OR RUN. No compiler source is changed.
-- Reuse this exact Main source in separately admitted baseline/delete/spine builds.
-- Only public APIs are used. No CheckedTerm, Environment or Fragment is forged.
module Main (main) where

import Control.Exception (AsyncException, Exception, SomeException, evaluate,
                          fromException, throw, throwIO, try)
import Control.Monad (forM, forM_, unless)
import Data.IORef (IORef, modifyIORef', newIORef, readIORef)
import Data.Typeable (Typeable)
import Numeric (showHex)
import System.Exit (exitFailure)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.X.Check as Check
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Type as Type
import qualified Bootstrap.OpenFragment as Open
import qualified Bootstrap.ArtifactStructure as Structure
import qualified Bootstrap.Bitstream as Wire
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as Primitive

type Owned = [(T.XName, T.XType)]
type Log = IORef [String]

data ProbeException = FixtureFailure String | LatentBinder String
  deriving (Show, Typeable)
instance Exception ProbeException

data CaseSpec = CaseSpec String (Log -> IO ())

abort :: String -> IO a
abort = throwIO . FixtureFailure

record :: Log -> String -> String -> IO ()
record logRef observation payload = modifyIORef' logRef
  ((observation ++ "=" ++ payload) :)

tryAny :: IO a -> IO (Either SomeException a)
tryAny = try

rethrowAsync :: SomeException -> IO ()
rethrowAsync exception = case (fromException exception :: Maybe AsyncException) of
  Just asynchronous -> throwIO asynchronous
  Nothing -> pure ()

-- This observes only the requested value's WHNF. It records no allocation or
-- return-before-spine claim, and does not catch/display a host call stack.
observeWHNF :: Log -> String -> a -> IO a
observeWHNF logRef observation value = do
  answer <- evaluate value
  record logRef observation "whnf"
  pure answer

requireRight :: Log -> String -> T.Either B.String a -> IO a
requireRight logRef phase result = do
  observed <- observeWHNF logRef (phase ++ ".either") result
  case observed of
    T.Left message -> abort (phase ++ ": unexpected Left: " ++ B.unpack message)
    T.Right value -> do
      record logRef (phase ++ ".branch") "right"
      pure value

requireLeft :: Log -> String -> String -> T.Either B.String a -> IO ()
requireLeft logRef phase expected result = do
  observed <- observeWHNF logRef (phase ++ ".either") result
  case observed of
    T.Left message -> do
      let actual = B.unpack message
      unless (actual == expected) (abort (phase ++ ": wrong error: " ++ actual))
      record logRef (phase ++ ".error") actual
    T.Right _ -> abort (phase ++ ": unexpectedly accepted")

assertThat :: String -> Bool -> IO ()
assertThat label condition = unless condition (abort label)

sameValue :: Wire.Value -> Wire.Value -> Bool
sameValue a b = case (a, b) of
  (Wire.VInt x, Wire.VInt y) -> x == y
  (Wire.VBits x, Wire.VBits y) -> x == y
  (Wire.VText x, Wire.VText y) -> B.v_eqString x y
  (Wire.VNode tag xs, Wire.VNode other ys) ->
    tag == other && length xs == length ys && and (zipWith sameValue xs ys)
  _ -> False

ownedValue :: Owned -> Wire.Value
ownedValue = Structure.toList (Structure.toPair Structure.toXName Structure.toXType)

sameOwned :: Owned -> Owned -> Bool
sameOwned xs ys = sameValue (ownedValue xs) (ownedValue ys)

nameKey :: T.XName -> (B.Int, String)
nameKey name = (X.nameId name, B.unpack (X.nameHint name))

hexByte :: B.Int -> String
hexByte value = let text = showHex value ""
               in if length text == 1 then '0' : text else text

-- Actual encoded bytes, not an AST hash or pretty/alpha-equivalence surrogate.
-- This is used only on deliberately total observations, never the partial term.
recordBytes :: Log -> String -> Wire.Value -> IO ()
recordBytes logRef field value = do
  encoded <- Wire.encode Wire.defaultLimits 6 [value]
  bytes <- requireRight logRef (field ++ ".encode") encoded
  count <- Primitive.lengthByteArray bytes
  chunks <- forM [0 .. count - 1] $ \index -> do
    byte <- Primitive.readByteArray bytes index
    assertThat (field ++ ": invalid encoded byte") (byte >= 0 && byte <= 255)
    pure (hexByte byte)
  record logRef (field ++ ".bytes") (show count ++ ":" ++ concat chunks)

snapshot :: Open.Fragment -> [(String, Wire.Value)]
snapshot fragment =
  [ ("declarations", Structure.toList Structure.toDataDecl
      (Open.declarations (Open.context fragment)))
  , ("parameters", ownedValue (Open.parameters fragment))
  , ("body", Structure.toXTerm (Open.body fragment))
  , ("bindings", ownedValue (Open.bindings fragment))
  , ("used-parameters", Structure.toList Structure.toXName (Open.usedParameters fragment))
  , ("fingerprint", Wire.VText (Open.fingerprint fragment))
  , ("encoded-body", Open.encodeBody "Inference" "duplicate-guard-public-api" fragment)
  ]

assertSnapshots :: String -> Open.Fragment -> Open.Fragment -> IO ()
assertSnapshots label before after = do
  let left = snapshot before
      right = snapshot after
  assertThat (label ++ ": snapshot field count") (length left == length right)
  forM_ (zip left right) $ \((name, a), (other, b)) ->
    assertThat (label ++ ": snapshot differs at " ++ name)
      (name == other && sameValue a b)

-- Explicit consumer observations only. A successful length observation proves
-- that full traversal completed HERE, not that it happened before Open.check's
-- Right/Fragment constructor. No pure-value spine-timing claim is made.
observeBindings :: Log -> Owned -> IO ()
observeBindings logRef owned = do
  values <- observeWHNF logRef "bindings.whnf" owned
  case values of
    [] -> record logRef "bindings.head-pair" "empty"
    pair : _ -> do
      _ <- observeWHNF logRef "bindings.head-pair" pair
      pure ()
  count <- observeWHNF logRef "bindings.length" (length owned)
  record logRef "bindings.count" (show count)

unit :: T.XTerm
unit = T.XConstructor "()" []

intType, unitType :: T.XType
intType = T.XCon "Int" []
unitType = T.XCon "()" []

e, m, n, local, absent :: T.XName
e = T.XName 10 "a"
m = T.XName 100 "m"
n = T.XName 200 "n"
local = T.XName 300 "local"
absent = T.XName 999 "absent"

good :: T.XTyVar
good = T.XTyVar 7

polyType :: T.XType
polyType = T.XForall good T.XBot (T.XArrow (T.XVar good) (T.XVar good))

polyRhs :: T.XTerm
polyRhs = T.XTypeAbs good T.XBot
  (T.XAbs local (T.XVar good) (T.XVarTerm local))

shapeError, openTypeError :: String
shapeError = "invalid inference fragment: expected declarations ending in ()"
openTypeError = "inference binding has an open type"

emptyEnvironment :: Log -> IO Open.Environment
emptyEnvironment logRef = requireRight logRef "environment" (Open.environment [])

data Positive = Positive String Owned T.XTerm Owned [T.XName]

positives :: [Positive]
positives =
  [ Positive "p-empty" [] unit [] []
  , Positive "p-let" [] (T.XLet m (T.XIntTerm 1) unit) [(m, intType)] []
  , Positive "p-external-used" [(e, intType)]
      (T.XLet m (T.XVarTerm e) unit) [(m, intType)] [e]
  , Positive "p-mixed-empty-rec" []
      (T.XLetRec [(m, intType, T.XVarTerm n), (n, intType, T.XVarTerm m)]
        (T.XLetRec [] (T.XLet local (T.XVarTerm m) unit)))
      [(m, intType), (n, intType), (local, intType)] []
  , Positive "p-rhs-local" []
      (T.XLet m (T.XLet local (T.XIntTerm 3) (T.XVarTerm local)) unit)
      [(m, intType)] []
  , Positive "p-polymorphic-rhs" [] (T.XLet m polyRhs unit) [(m, polyType)] []
  ]

positiveCase :: Positive -> CaseSpec
positiveCase (Positive label parameters source expectedOwned expectedUsed) = CaseSpec label $ \logRef -> do
  env <- emptyEnvironment logRef
  fragment <- requireRight logRef "open" (Open.check env parameters source)
  _ <- observeWHNF logRef "fragment.whnf" fragment
  _ <- observeWHNF logRef "body.whnf" (Open.body fragment)
  _ <- observeWHNF logRef "parameters.whnf" (Open.parameters fragment)
  observeBindings logRef (Open.bindings fragment)
  assertThat "parameter structure changed" (sameOwned (Open.parameters fragment) parameters)
  assertThat "body structure changed"
    (sameValue (Structure.toXTerm (Open.body fragment)) (Structure.toXTerm source))
  assertThat "owned structure/order changed" (sameOwned (Open.bindings fragment) expectedOwned)
  assertThat "used-parameter order changed"
    (map nameKey (Open.usedParameters fragment) == map nameKey expectedUsed)
  forM_ (snapshot fragment) $ \(field, value) -> recordBytes logRef field value
  normalized <- requireRight logRef "normalize" (Open.normalize fragment source)
  assertSnapshots "normalize" fragment normalized
  record logRef "normalize.snapshot" "equal"
  audited <- requireRight logRef "audit" (Open.audit fragment)
  assertSnapshots "audit" fragment audited
  record logRef "audit.snapshot" "equal"

data Negative = Negative String Owned T.XTerm String

negatives :: [Negative]
negatives =
  [ Negative "n-duplicate-parameter-before-type"
      [(e, T.XVar (T.XTyVar 99)), (T.XName 10 "other", intType)]
      (T.XVarTerm absent) "duplicate open-fragment parameter"
  , Negative "n-parameter-type-before-body" [(e, T.XVar (T.XTyVar 99))]
      (T.XVarTerm absent) "unbound type variable 99"
  , Negative "n-unbound-body" [] (T.XVarTerm absent) "unbound term variable absent"
  , Negative "n-duplicate-recursive-before-annotation" []
      (T.XLetRec [(m, T.XVar (T.XTyVar 99), T.XIntTerm 1),
                 (T.XName 100 "other", intType, T.XBoolTerm True)] unit)
      "duplicate recursive binder"
  , Negative "n-recursive-rhs-before-shape" []
      (T.XLetRec [(m, intType, T.XBoolTerm True)] (T.XIntTerm 0))
      "recursive definition does not have its declared type"
  , Negative "n-integer-nonfragment" [] (T.XIntTerm 0) shapeError
  , Negative "n-leading-lambda-nonfragment" [] (T.XAbs e intType unit) shapeError
  , Negative "n-lambda-after-let" []
      (T.XLet m (T.XIntTerm 1) (T.XAbs e intType unit)) shapeError
  , Negative "n-let-shadows-parameter" [(e, intType)]
      (T.XLet e (T.XIntTerm 1) unit) "term binder already in scope"
  , Negative "n-recursive-shadows-parameter" [(e, intType)]
      (T.XLetRec [(e, intType, T.XIntTerm 1)] unit) "recursive binder already in scope"
  ]

negativeCase :: Negative -> CaseSpec
negativeCase (Negative label parameters source expected) = CaseSpec label $ \logRef -> do
  env <- emptyEnvironment logRef
  requireLeft logRef "open" expected (Open.check env parameters source)

-- A public raw-checker environment, not an opaque checked receipt. Validate it
-- through inferWithData before using it for the two-Either-layer controls.
rawEnvironment :: Log -> IO (T.DataEnv, T.XEnv)
rawEnvironment logRef = do
  env <- emptyEnvironment logRef
  let variable = T.XTyVar 91
      scope = T.XEnv (M.singleton variable T.XBot)
                    (M.singleton e (T.XVar variable))
      dataEnv = Open.dataEnvironment env
  answer <- requireRight logRef "raw-context-validation" (Check.inferWithData dataEnv scope unit)
  assertThat "raw environment did not infer unit"
    (sameValue (Structure.toXType answer) (Structure.toXType unitType))
  pure (dataEnv, scope)

rawInventoryCase :: String -> T.XTerm -> T.XType -> String -> CaseSpec
rawInventoryCase label source expectedType expectedError = CaseSpec label $ \logRef -> do
  (dataEnv, scope) <- rawEnvironment logRef
  answer <- requireRight logRef "raw-inference" (Check.inferDeclarationSpine dataEnv scope source)
  _ <- observeWHNF logRef "raw-answer-pair.whnf" answer
  actualType <- observeWHNF logRef "raw-type.whnf" (fst answer)
  assertThat "raw inferred type changed"
    (sameValue (Structure.toXType actualType) (Structure.toXType expectedType))
  recordBytes logRef "raw-type" (Structure.toXType actualType)
  -- This is intentionally AFTER independent inference/type observations.
  requireLeft logRef "raw-inventory" expectedError (snd answer)

rawCases :: [CaseSpec]
rawCases =
  [ CaseSpec "r-body-type-before-outer-open-inventory" $ \logRef -> do
      (dataEnv, scope) <- rawEnvironment logRef
      requireLeft logRef "raw-inference" "unbound term variable absent"
        (Check.inferDeclarationSpine dataEnv scope
          (T.XLet m (T.XVarTerm e) (T.XVarTerm absent)))
  , rawInventoryCase "r-outer-open-before-terminal-shape"
      (T.XLet m (T.XVarTerm e) (T.XIntTerm 0)) intType openTypeError
  , rawInventoryCase "r-closed-prefix-then-shape"
      (T.XLet m (T.XIntTerm 1) (T.XIntTerm 0)) intType shapeError
  , rawInventoryCase "r-closed-prefix-then-inner-open"
      (T.XLet m (T.XIntTerm 1) (T.XLet n (T.XVarTerm e) unit)) unitType openTypeError
  ]

checkedNonfragment :: String -> T.XTerm -> T.XType -> Bool -> CaseSpec
checkedNonfragment label source expectedType inventorySucceeds = CaseSpec label $ \logRef -> do
  receipt <- requireRight logRef "checked" (Checked.check source)
  _ <- observeWHNF logRef "receipt.whnf" receipt
  _ <- observeWHNF logRef "checked-term.whnf" (Checked.term receipt)
  actual <- observeWHNF logRef "checked-type.whnf" (Checked.typeOf receipt)
  assertThat "checked nonfragment type changed"
    (sameValue (Structure.toXType actual) (Structure.toXType expectedType))
  recordBytes logRef "checked-type" (Structure.toXType actual)
  if inventorySucceeds then do
    owned <- requireRight logRef "checked-inventory" (Checked.declarationBindings receipt)
    observeBindings logRef owned
    assertThat "lambda-peeled inventory is not empty" (null owned)
  else requireLeft logRef "checked-inventory" shapeError (Checked.declarationBindings receipt)
  env <- emptyEnvironment logRef
  requireLeft logRef "unpeeled-open" shapeError (Open.check env [] source)

-- Pure host exception sentinel, NOT the language's XBot. Different tags give
-- the checked and open routes separate source expressions. No error callstack
-- or machine path is printed by the stable observation protocol.
partialSource :: String -> T.XTerm
partialSource tag =
  let bad = T.XTyVar (throw (LatentBinder tag))
      rhs = T.XTypeAbs bad T.XBot (T.XAbs local polyType (T.XVarTerm local))
  in T.XLet m rhs unit

expectSentinel :: Log -> String -> B.Int -> IO ()
expectSentinel logRef expected value = do
  outcome <- tryAny (evaluate value)
  case outcome of
    Right _ -> abort "latent binder ID unexpectedly total"
    Left exception -> do
      rethrowAsync exception
      case (fromException exception :: Maybe ProbeException) of
        Just (LatentBinder actual) -> do
          assertThat "wrong latent binder sentinel" (actual == expected)
          record logRef "owned-binder-id.final-probe" ("sentinel:" ++ actual)
        _ -> abort "wrong exception in final latent binder probe"

observePartialOwned :: Log -> String -> Owned -> IO ()
observePartialOwned logRef tag owned = do
  observeBindings logRef owned
  case owned of
    [(name, ty)] -> do
      assertThat "partial owned name changed" (nameKey name == nameKey m)
      _ <- observeWHNF logRef "owned-type.whnf" ty
      case ty of
        T.XForall binder T.XBot (T.XArrow left right) -> do
          assertThat "partial type's total children changed"
            (sameValue (Structure.toXType left) (Structure.toXType polyType) &&
             sameValue (Structure.toXType right) (Structure.toXType polyType))
          _ <- observeWHNF logRef "owned-binder-constructor.whnf" binder
          record logRef "owned-type.safe-shape" "forall-unused-id.(poly->poly)"
          -- Last observation only: proves the OUTPUT binder really retains the
          -- partial ID. Nothing encodes the partial type/body/stamp afterwards.
          expectSentinel logRef tag (Type.tyVarId binder)
        _ -> abort "partial owned type has wrong outer structure"
    _ -> abort "partial inventory is not exactly one owned binding"

partialChecked :: CaseSpec
partialChecked = CaseSpec "h-partial-unused-binder-checked" $ \logRef -> do
  let tag = "checked-unused-binder-id"
  receipt <- requireRight logRef "checked" (Checked.check (partialSource tag))
  _ <- observeWHNF logRef "receipt.whnf" receipt
  _ <- observeWHNF logRef "checked-term.whnf" (Checked.term receipt)
  actual <- observeWHNF logRef "checked-type.whnf" (Checked.typeOf receipt)
  assertThat "partial declaration program did not infer unit"
    (sameValue (Structure.toXType actual) (Structure.toXType unitType))
  recordBytes logRef "checked-type" (Structure.toXType actual)
  owned <- requireRight logRef "checked-inventory" (Checked.declarationBindings receipt)
  observePartialOwned logRef tag owned

partialOpen :: CaseSpec
partialOpen = CaseSpec "h-partial-unused-binder-open" $ \logRef -> do
  let tag = "open-unused-binder-id"
  env <- emptyEnvironment logRef
  fragment <- requireRight logRef "open" (Open.check env [] (partialSource tag))
  _ <- observeWHNF logRef "fragment.whnf" fragment
  _ <- observeWHNF logRef "body.whnf" (Open.body fragment)
  parameters <- observeWHNF logRef "parameters.whnf" (Open.parameters fragment)
  assertThat "partial fragment acquired parameters" (null parameters)
  -- Deliberately no snapshot, fingerprint, usedParameters, normalize or audit:
  -- their partial-input demand is outside this minimal safe observation list.
  observePartialOwned logRef tag (Open.bindings fragment)

allCases :: [CaseSpec]
allCases = map positiveCase positives ++ map negativeCase negatives ++ rawCases ++
  [ checkedNonfragment "c-integer-type-before-inventory"
      (T.XIntTerm 1) intType False
  , checkedNonfragment "c-lambda-raw-inventory-vs-open"
      (T.XAbs e intType unit) (T.XArrow intType unitType) True
  , partialChecked
  , partialOpen
  ]

failureText :: SomeException -> String
failureText exception = case (fromException exception :: Maybe ProbeException) of
  Just (FixtureFailure detail) -> "assertion: " ++ detail
  Just (LatentBinder tag) -> "unexpected early latent binder demand: " ++ tag
  Nothing -> "unexpected host exception (details suppressed; no path/callstack output)"

-- Test-output forcing only, AFTER the case's explicit observations. Demanding
-- characters as well as cons cells keeps lazy rendering exceptions inside the
-- per-case catch; it is not production forcing or a spine-timing observation.
forceString :: String -> ()
forceString [] = ()
forceString (character : rest) = character `seq` forceString rest

failureLine :: String -> SomeException -> IO String
failureLine label exception = do
  rendered <- tryAny $ do
    let line = "FAIL\t" ++ label ++ "\t" ++ show (failureText exception)
    _ <- evaluate (forceString line)
    pure line
  case rendered of
    Right line -> pure line
    Left renderingException -> do
      rethrowAsync renderingException
      -- The label comes from the fixed total source case list, not host data.
      pure ("FAIL\t" ++ label ++ "\t" ++
            show ("failure-detail rendering failed; details suppressed" :: String))

runCase :: CaseSpec -> IO Bool
runCase (CaseSpec label action) = do
  logRef <- newIORef []
  result <- tryAny $ do
    action logRef
    observations <- reverse <$> readIORef logRef
    let line = "PASS\t" ++ label ++ "\t" ++ show (unlines observations)
    _ <- evaluate (forceString line)
    pure line
  case result of
    Right line -> do
      putStrLn line
      pure True
    Left exception -> do
      rethrowAsync exception
      line <- failureLine label exception
      putStrLn line
      pure False

main :: IO ()
main = do
  results <- mapM runCase allCases
  let total = length results
      passed = length (filter id results)
  putStrLn ("SUMMARY\t" ++ show total ++ "\t" ++ show passed)
  unless (total == passed) exitFailure
