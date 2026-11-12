{-# LANGUAGE OverloadedStrings #-}
-- SOURCE-ONLY, UNCOMPILED, UNRUN. No production code is changed.
-- This module does not construct CheckedTerm, Environment, or Fragment.
module Main (main) where

import Control.Monad (forM_, unless)
import Data.List (nubBy, sort)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as S
import qualified Bootstrap.CompilerCore as Compiler
import qualified Bootstrap.X.Check as Check
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Type as Type
import qualified Bootstrap.OpenFragment as Open
import qualified Bootstrap.ArtifactStructure as Structure
import qualified Bootstrap.Bitstream as Wire
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as Primitive

-- Host-side phase tags assert the intended failing seam, not just Left/Right.
-- Verification formatting is the original Compiler.prettyError; this fixture
-- does NOT claim to run constraints, solving, elaboration, or erasure agreement.
data Seam = Verification | Wrapper | Environment | OpenAdmission | Ownership | Lemma
  deriving (Eq, Show)
data Failure = Failure Seam String deriving (Eq, Show)
type External = T.Map B.String T.XType
type Owned = [(T.XName, T.XType)]

liftAt :: Seam -> T.Either B.String a -> Either Failure a
liftAt at result = case result of
  T.Left message -> Left (Failure at (B.unpack message))
  T.Right value -> Right value

ensureAt :: Seam -> String -> Bool -> Either Failure ()
ensureAt at message condition = if condition then Right () else Left (Failure at message)

checkedReceipt :: T.XTerm -> Either Failure Checked.CheckedTerm
checkedReceipt source = case Checked.check source of
  T.Left message -> Left (Failure Verification
    (B.unpack (Compiler.prettyError (T.CompileError T.Verification message))))
  T.Right checked -> Right checked

-- Independent reference seam: literal ordering of compileGroupBody's extraction
-- and finishOpenGroup's environment -> Open.check -> ownership sequence.
-- It never calls projectCandidate or projectedOwned.
baselineParts :: External -> T.XTerm -> Either Failure ([T.DataDecl], Owned, T.XTerm)
baselineParts external source = do
  let (declarations, core) = case source of
        T.XWithData ds body -> (ds, body)
        body -> ([], body)
  (parameters, body) <- if M.null external then Right ([], core) else case core of
    T.XLetRec bindings rest -> do
      ensureAt Wrapper "inference parameter order mismatch"
        (map (B.unpack . X.nameHint . first3) bindings == map B.unpack (M.keys external))
      forM_ bindings $ \(name, actual, _) ->
        ensureAt Wrapper ("dependency scheme changed during inference: " ++ B.unpack (X.nameHint name))
          (case M.lookup B.v_compareString (X.nameHint name) external of
             T.Nothing -> False
             T.Just expected -> Type.alphaEq actual expected)
      Right ([(name, ty) | (name, ty, _) <- bindings], rest)
    _ -> Left (Failure Wrapper "inference did not retain external parameters")
  Right (declarations, parameters, body)
  where first3 (name, _, _) = name

ownership :: [B.String] -> Owned -> Either Failure ()
ownership members owned = ensureAt Ownership "inference fragment changed declaration ownership"
  (sort (map (B.unpack . X.nameHint . fst) owned) == sort (map B.unpack members))

baseline :: External -> [B.String] -> Checked.CheckedTerm -> Either Failure Open.Fragment
baseline external members checked = do
  (ds, ps, body) <- baselineParts external (Checked.term checked)
  env <- liftAt Environment (Open.environment ds)
  fragment <- liftAt OpenAdmission (Open.check env ps body)
  ownership members (Open.bindings fragment)
  Right fragment

-- Private FIXTURE observation, never a checked Fragment or production API.
-- All fields and the cut count are derived from this genuine receipt's root.
-- No caller-supplied DataEnv, body, inventory, or arbitrary cut count is accepted.
data Cut = KeepWhole | CutRoot Int | RejectLeadingLambda
data Projection = Projection Checked.CheckedTerm [T.DataDecl] Owned T.XTerm Cut

projectCandidate :: External -> Checked.CheckedTerm -> Either Failure Projection
projectCandidate external checked =
  let (ds, core) = case Checked.term checked of
        T.XWithData declarations body -> (declarations, body)
        body -> ([], body)
  in if M.null external
     then Right (Projection checked ds [] core (case core of
            T.XAbs _ _ _ -> RejectLeadingLambda
            _ -> KeepWhole))
     else case core of
       T.XLetRec entries rest -> do
         let ps = [(name, ty) | (name, ty, _) <- entries]
         ensureAt Wrapper "inference parameter order mismatch"
           (map (B.unpack . X.nameHint . fst) ps == map B.unpack (M.keys external))
         forM_ ps $ \(name, actual) -> do
           let matches = case M.lookup B.v_compareString (X.nameHint name) external of
                 T.Just expected -> Type.alphaEq actual expected
                 T.Nothing -> False
           ensureAt Wrapper ("dependency scheme changed during inference: " ++ B.unpack (X.nameHint name)) matches
         Right (Projection checked ds ps rest (CutRoot (length entries)))
       _ -> Left (Failure Wrapper "inference did not retain external parameters")

shapeError :: Failure
shapeError = Failure OpenAdmission "invalid inference fragment: expected declarations ending in ()"

-- Total exact prefix cut. A mismatch is a FIXTURE lemma failure, not a new
-- language diagnostic. It cannot silently truncate or filter/reorder bindings.
cutExact :: Int -> Owned -> Either Failure (Owned, Owned)
cutExact 0 values = Right ([], values)
cutExact n ((name, ty):rest) | n > 0 = do
  (prefix, suffix) <- cutExact (n - 1) rest
  Right ((name, ty):prefix, suffix)
cutExact _ _ = Left (Failure Lemma "checked inventory is shorter than its exact root prefix")

projectedOwned :: Projection -> Either Failure Owned
projectedOwned (Projection checked _ ps _ cut) = case cut of
  RejectLeadingLambda -> Left shapeError
  KeepWhole -> liftAt OpenAdmission (Checked.declarationBindings checked)
  CutRoot count -> do
    whole <- liftAt OpenAdmission (Checked.declarationBindings checked)
    (prefix, suffix) <- cutExact count whole
    ensureAt Lemma "exact root inventory prefix changed IDs/hints/type syntax" (sameOwned prefix ps)
    Right suffix

-- Explicit Open parameter/closed-export checks remain, at their original point.
-- This only produces an inventory observation, never an unchecked Fragment.
candidateObservation :: External -> [B.String] -> Checked.CheckedTerm
                     -> Either Failure (Projection, Owned)
candidateObservation external members checked = do
  projection@(Projection _ ds ps _ _) <- projectCandidate external checked
  env <- liftAt Environment (Open.environment ds)
  let names = map fst ps
  ensureAt OpenAdmission "duplicate open-fragment parameter"
    (length names == length (nubBy X.equalName names))
  forM_ (map snd ps) $ \ty -> liftAt OpenAdmission (Check.termType (Open.dataEnvironment env) M.empty ty)
  owned <- projectedOwned projection
  ensureAt OpenAdmission "open fragment exports an open type" (all (S.null . Type.freeVars . snd) owned)
  ownership members owned
  Right (projection, owned)

-- Safe byte-preserving adapter: obtain a real Fragment through unchanged check.
-- The projected inventory is NOT supplied to Open.check or any constructor.
admitWithOriginalCheck :: Projection -> Either Failure Open.Fragment
admitWithOriginalCheck (Projection _ ds ps body _) = do
  env <- liftAt Environment (Open.environment ds)
  liftAt OpenAdmission (Open.check env ps body)

-- Complete safe-adapter route for independent assertions on BOTH accepted and
-- rejected inputs. An inventory observation alone could mask a corrupted body
-- when the original receipt's inventory already fails.
safeAdapter :: External -> [B.String] -> Checked.CheckedTerm
            -> Either Failure Open.Fragment
safeAdapter external members checked = do
  projection <- projectCandidate external checked
  fragment <- admitWithOriginalCheck projection
  ownership members (Open.bindings fragment)
  Right fragment

-- Exact structural comparison, not pretty printing, normalization, or alphaEq.
-- ArtifactStructure preserves constructor tags, name IDs/hints, binder syntax,
-- declaration order, and multiplicity. All fields are demanded only in tests.
sameValue :: Wire.Value -> Wire.Value -> Bool
sameValue first second = case (first, second) of
  (Wire.VInt a, Wire.VInt b) -> a == b
  (Wire.VBits a, Wire.VBits b) -> a == b
  (Wire.VText a, Wire.VText b) -> B.v_eqString a b
  (Wire.VNode a xs, Wire.VNode b ys) -> a == b && length xs == length ys && and (zipWith sameValue xs ys)
  _ -> False

ownedValue :: Owned -> Wire.Value
ownedValue = Structure.toList (Structure.toPair Structure.toXName Structure.toXType)
sameOwned :: Owned -> Owned -> Bool
sameOwned a b = sameValue (ownedValue a) (ownedValue b)

snapshot :: Open.Fragment -> [Wire.Value]
snapshot fragment =
  [ Structure.toList Structure.toDataDecl (Open.declarations (Open.context fragment))
  , ownedValue (Open.parameters fragment)
  , Structure.toXTerm (Open.body fragment)
  , ownedValue (Open.bindings fragment)
  , Structure.toList Structure.toXName (Open.usedParameters fragment)
  , Wire.VText (Open.fingerprint fragment)
  , Open.encodeBody "Inference" "projection-prototype" fragment
  ]

right :: String -> Either Failure a -> IO a
right label result = case result of
  Left failure -> fail (label ++ ": " ++ show failure)
  Right value -> pure value

compareBytes :: String -> Wire.Value -> Wire.Value -> IO ()
compareBytes label first second = do
  encodedFirst <- Wire.encode Wire.defaultLimits 6 [first]
  encodedSecond <- Wire.encode Wire.defaultLimits 6 [second]
  a <- right label (liftAt Lemma encodedFirst)
  b <- right label (liftAt Lemma encodedSecond)
  na <- Primitive.lengthByteArray a
  nb <- Primitive.lengthByteArray b
  unless (na == nb) (fail (label ++ ": encoded lengths changed"))
  forM_ [0 .. na - 1] $ \i -> do
    x <- Primitive.readByteArray a i
    y <- Primitive.readByteArray b i
    unless (x == y) (fail (label ++ ": encoded byte changed at " ++ show i))

nameKey :: T.XName -> (B.Int, String)
nameKey name = (X.nameId name, B.unpack (X.nameHint name))
data Expected = Pass [T.XName] [T.XName] [T.XName] | Reject Failure
data Case = Case String T.XTerm [(B.String, T.XType)] [B.String] Expected

unit :: T.XTerm
unit = T.XConstructor "()" []
int, bool :: T.XType
int = T.XCon "Int" []
bool = T.XCon "Bool" []
e, f, m, n, local :: T.XName
e = T.XName 10 "a"
f = T.XName 20 "b"
m = T.XName 100 "m"
n = T.XName 200 "n"
local = T.XName 300 "local"
one rhs tailBody = T.XLetRec [(e, int, rhs)] tailBody
owned = T.XLet m (T.XIntTerm 1) unit
expectedShape = Reject shapeError
expectedWrapper message = Reject (Failure Wrapper message)
expectedVerification message = Reject (Failure Verification ("Verification: " ++ message))
expectedOwnership = Reject (Failure Ownership "inference fragment changed declaration ownership")
poly a = T.XForall (T.XTyVar a) T.XBot
  (T.XArrow (T.XVar (T.XTyVar a)) (T.XVar (T.XTyVar a)))
polyRhs = T.XTypeAbs (T.XTyVar 7) T.XBot
  (T.XAbs local (T.XVar (T.XTyVar 7)) (T.XVarTerm local))
polyField = T.DataDecl "Poly" [] [T.ConstructorDecl "Poly"
  [T.Quantified "a" T.Star (T.Function (T.Parameter "a") (T.Parameter "a"))]]

cases :: [Case]
cases =
  [ Case "p1-plain" owned [] ["m"] (Pass [] [m] [])
  , Case "p1-data-empty" (T.XWithData [] owned) [] ["m"] (Pass [] [m] [])
  , Case "p2-external-used" (one (T.XIntTerm 9) (T.XLet m (T.XVarTerm e) unit))
      [("a",int)] ["m"] (Pass [e] [m] [e])
  , Case "p2-external-unused" (one (T.XIntTerm 9) owned)
      [("a",int)] ["m"] (Pass [e] [m] [])
  , Case "p3-two-ordered" (T.XLetRec [(e,int,T.XIntTerm 1),(f,int,T.XIntTerm 2)]
      (T.XLet m (T.XVarTerm e) (T.XLet n (T.XVarTerm f) unit)))
      [("b",int),("a",int)] ["n","m"] (Pass [e,f] [m,n] [e,f])
  , Case "p3-alpha-annotation-retained" (T.XLetRec [(e,poly 17,polyRhs)] owned)
      [("a",poly 5)] ["m"] (Pass [e] [m] [])
  , Case "p4-owned-mutual-then-let" (T.XLetRec [(m,int,T.XVarTerm n),(n,int,T.XVarTerm m)]
      (T.XLet local (T.XVarTerm m) unit)) [] ["local","n","m"] (Pass [] [m,n,local] [])
  , Case "p4-rhs-local-let" (one (T.XIntTerm 9)
      (T.XLet m (T.XLet local (T.XVarTerm e) (T.XVarTerm local)) unit))
      [("a",int)] ["m"] (Pass [e] [m] [e])
  , Case "p4-rhs-local-lambda" (T.XLet m (T.XAbs local int (T.XVarTerm local)) unit)
      [] ["m"] (Pass [] [m] [])
  , Case "p4-rhs-local-rec" (T.XLet m (T.XLetRec [(local,int,T.XIntTerm 3)] (T.XVarTerm local)) unit)
      [] ["m"] (Pass [] [m] [])
  , Case "p5-owned-root-rec" (T.XLetRec [(m,int,T.XIntTerm 1)] unit)
      [] ["m"] (Pass [] [m] [])
  , Case "p5-empty-owned-rec" (T.XLetRec [] owned) [] ["m"] (Pass [] [m] [])
  , Case "p6-quantified-field-negative-id" (T.XWithData [polyField]
      (T.XLet (T.XName (-7) "m") (T.XConstructor "Poly" []) unit))
      [] ["m"] (Pass [] [T.XName (-7) "m"] [])
  , Case "p6-spaced-ids" (T.XLetRec [(T.XName (-20) "a",int,T.XIntTerm 1)]
      (T.XLet (T.XName 900000 "m") (T.XVarTerm (T.XName (-20) "a")) unit))
      [("a",int)] ["m"] (Pass [T.XName (-20) "a"] [T.XName 900000 "m"] [T.XName (-20) "a"])
  , Case "p7-integer-nonfragment" (T.XIntTerm 1) [] [] expectedShape
  , Case "p7-function-nonfragment" (T.XAbs e int (T.XVarTerm e)) [] [] expectedShape
  , Case "p7-external-nonfragment" (one (T.XIntTerm 1) (T.XIntTerm 2)) [("a",int)] [] expectedShape
  , Case "n1-no-external-leading-lambda" (T.XAbs e int unit) [] [] expectedShape
  , Case "n1-lambda-after-owned-let" (T.XLet m (T.XIntTerm 1) (T.XAbs e int unit)) [] ["m"] expectedShape
  , Case "n1-lambda-after-cut" (one (T.XIntTerm 1) (T.XAbs f int unit)) [("a",int)] [] expectedShape
  , Case "n2-missing-root" owned [("a",int)] ["m"]
      (expectedWrapper "inference did not retain external parameters")
  , Case "n2-leading-lambda" (T.XAbs e int owned) [("a",int)] ["m"]
      (expectedWrapper "inference did not retain external parameters")
  , Case "n2-leading-type-lambda" (T.XTypeAbs (T.XTyVar 5) T.XBot unit) [("a",int)] []
      (expectedWrapper "inference did not retain external parameters")
  , Case "n2-leading-type-application" (T.XTypeApp (T.XTypeAbs (T.XTyVar 5) T.XBot unit) T.XRefl) [("a",int)] []
      (expectedWrapper "inference did not retain external parameters")
  , Case "n3-same-hints-distinct-ids" (T.XLetRec [(e,int,T.XIntTerm 1),(T.XName 11 "a",int,T.XIntTerm 2)] unit)
      [("a",int)] [] (expectedWrapper "inference parameter order mismatch")
  , Case "n3-count" (one (T.XIntTerm 1) owned) [("a",int),("b",int)] ["m"]
      (expectedWrapper "inference parameter order mismatch")
  , Case "n3-order-before-tail" (T.XLetRec [(f,int,T.XIntTerm 2),(e,int,T.XIntTerm 1)] (T.XIntTerm 0))
      [("a",int),("b",int)] ["wrong"] (expectedWrapper "inference parameter order mismatch")
  , Case "n3-hint" (T.XLetRec [(T.XName 10 "different",int,T.XIntTerm 1)] owned)
      [("a",int)] ["m"] (expectedWrapper "inference parameter order mismatch")
  , Case "n4-scheme-before-tail" (one (T.XIntTerm 1) (T.XIntTerm 0)) [("a",bool)] ["wrong"]
      (expectedWrapper "dependency scheme changed during inference: a")
  , Case "n5-duplicate-id-different-hints" (T.XLetRec [(e,int,T.XIntTerm 1),(T.XName 10 "b",int,T.XIntTerm 2)] unit)
      [("a",int),("b",int)] [] (expectedVerification "duplicate recursive binder")
  , Case "n5-body-shadows-external" (one (T.XIntTerm 1) (T.XLet e (T.XIntTerm 2) unit))
      [("a",int)] ["a"] (expectedVerification "term binder already in scope")
  , Case "n6-invalid-unused-rhs-before-wrapper" (one (T.XBoolTerm True) owned) [("wrong",int)] ["m"]
      (expectedVerification "recursive definition does not have its declared type")
  , Case "n6-unbound-unused-rhs" (one (T.XVarTerm (T.XName 999 "absent")) owned) [("a",int)] ["m"]
      (expectedVerification "unbound term variable absent")
  , Case "n7-unbound-annotation" (T.XLetRec [(e,T.XVar (T.XTyVar 99),T.XIntTerm 1)] unit)
      [("a",int)] [] (expectedVerification "unbound type variable 99")
  , Case "n8-nested-data" (one (T.XIntTerm 1) (T.XWithData [] owned)) [("a",int)] ["m"]
      (expectedVerification "data declarations must be at the outermost level")
  , Case "n10-missing-member" owned [] [] expectedOwnership
  , Case "n10-extra-member" owned [] ["m","extra"] expectedOwnership
  , Case "n10-renamed-member" owned [] ["renamed"] expectedOwnership
  , Case "e3-shape-before-ownership" (T.XIntTerm 1) [] ["wrong"] expectedShape
  ]

audit :: Case -> IO ()
audit (Case label source pairs members expected) = do
  let external = M.fromList B.v_compareString pairs
      reference = checkedReceipt source >>= baseline external members
      candidate = checkedReceipt source >>= candidateObservation external members
      adapted = checkedReceipt source >>= safeAdapter external members
  case expected of
    Reject failure -> do
      case reference of
        Left actual -> unless (actual == failure) (fail (label ++ ": baseline wrong first error: " ++ show actual))
        Right _ -> fail (label ++ ": baseline unexpectedly accepted")
      case candidate of
        Left actual -> unless (actual == failure) (fail (label ++ ": candidate wrong first error: " ++ show actual))
        Right _ -> fail (label ++ ": candidate unexpectedly accepted")
      case adapted of
        Left actual -> unless (actual == failure) (fail (label ++ ": safe adapter wrong first error: " ++ show actual))
        Right _ -> fail (label ++ ": safe adapter unexpectedly accepted")
    Pass ps bs used -> do
      before <- right label reference
      (Projection _ ds projectedParameters projectedBody _, inventory) <- right label candidate
      after <- right label adapted
      unless (sameOwned inventory (Open.bindings before)) (fail (label ++ ": projected suffix differs"))
      unless (map (nameKey . fst) (Open.parameters before) == map nameKey ps &&
              map (nameKey . fst) (Open.bindings before) == map nameKey bs &&
              map nameKey (Open.usedParameters before) == map nameKey used)
        (fail (label ++ ": fixture did not exercise prescribed ownership/use route"))
      unless (sameValue (Structure.toList Structure.toDataDecl ds)
                 (Structure.toList Structure.toDataDecl (Open.declarations (Open.context before))) &&
              sameOwned projectedParameters (Open.parameters before) &&
              sameValue (Structure.toXTerm projectedBody) (Structure.toXTerm (Open.body before)))
        (fail (label ++ ": extraction changed exact fields"))
      forM_ (zip3 [0 :: Int ..] (snapshot before) (snapshot after)) $ \(index, first, second) -> do
        unless (sameValue first second) (fail (label ++ ": exact snapshot changed at " ++ show index))
        compareBytes (label ++ " field " ++ show index) first second
  putStrLn ("PASS " ++ label)

-- Genuine checked receipts with different raw inventory behavior: integer
-- rejects, but a leading lambda over unit succeeds with an empty inventory
-- because Checked peels parameters. Both unpeeled open projections must reject.
-- Observe pending projection/type/body first, then witness the raw receipt
-- branch explicitly before projected inventory. No arbitrary-bottom proof.
demandCases :: IO ()
demandCases = forM_ [("integer",T.XIntTerm 1),("leading-lambda",T.XAbs e int unit)] $ \(label, source) -> do
  checked <- right label (checkedReceipt source)
  projection@(Projection _ _ ps body _) <- right label (projectCandidate M.empty checked)
  unless (sameValue (Structure.toXTerm body) (Structure.toXTerm source) && null ps)
    (fail (label ++ ": pending projection changed"))
  let expectedType = case source of T.XAbs _ _ _ -> T.XArrow int (T.XCon "()" []); _ -> int
  unless (sameValue (Structure.toXType (Checked.typeOf checked)) (Structure.toXType expectedType))
    (fail (label ++ ": independent type access changed"))
  case (source, Checked.declarationBindings checked) of
    (T.XIntTerm _, T.Left message) ->
      unless (B.unpack message == "invalid inference fragment: expected declarations ending in ()")
        (fail (label ++ ": raw integer inventory error changed"))
    (T.XAbs _ _ _, T.Right []) -> pure ()
    _ -> fail (label ++ ": raw receipt did not exercise its prescribed inventory branch")
  case projectedOwned projection of
    Left actual -> unless (actual == shapeError) (fail (label ++ ": inventory error changed"))
    Right _ -> fail (label ++ ": nonfragment inventory accepted")
  putStrLn ("PASS deferred-projection-" ++ label)

rawControls :: IO ()
rawControls = do
  env <- right "raw environment" (liftAt Environment (Open.environment []))
  let bad = T.XVar (T.XTyVar 99)
      casesRaw =
        [("duplicate-before-type",[(e,bad),(T.XName 10 "other",int)],T.XIntTerm 0,"duplicate open-fragment parameter")
        ,("bad-type-before-shape",[(e,bad)],T.XIntTerm 0,"unbound type variable 99")]
  forM_ casesRaw $ \(label, ps, body, expected) -> do
    case Open.check env ps body of
      T.Left actual -> unless (B.unpack actual == expected) (fail (label ++ ": wrong raw error"))
      T.Right _ -> fail (label ++ ": raw check accepted")
    putStrLn ("PASS raw-" ++ label)

main :: IO ()
main = do
  forM_ cases audit
  demandCases
  rawControls
  putStrLn ("Projection fixture: " ++ show (length cases + 4) ++ " checks passed")
