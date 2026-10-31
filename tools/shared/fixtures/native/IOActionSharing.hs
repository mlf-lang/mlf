{-# LANGUAGE OverloadedStrings #-}
-- Focused host driver. Uses the maintained compiler, both target checkers,
-- parser, interpreter, optimizer and LLVM emitter; no copied implementation.
module Main where

import Control.Monad (forM_, unless)
import System.Environment (getArgs)
import System.IO (BufferMode(LineBuffering), hSetBuffering, stdout)
import qualified Bootstrap.Compiler as C
import qualified Bootstrap.LLVM as LLVM
import qualified Bootstrap.LLVM.Analysis as A
import qualified Bootstrap.LLVM.Kernel as K
import qualified Bootstrap.LLVM.Optimize as O
import qualified Bootstrap.Map as M
import qualified Bootstrap.Runtime as R
import qualified Bootstrap.Set as S
import qualified Bootstrap.Types as T
import qualified Bootstrap.X.Check as Check
import qualified Bootstrap.X.Parser as Parse
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Type as Type
import qualified MLF.Host.Base as B
import qualified Tests.IndependentCheck as Frozen
import qualified Tests.IndependentType as FrozenType

ensure :: Bool -> String -> IO ()
ensure condition label = unless condition (fail label)
right :: T.Either B.String a -> IO a
right (T.Left message) = fail (B.unpack message)
right (T.Right value) = pure value

name :: Integer -> T.XName
name n = T.XName n "same"
v :: Integer -> T.XErased
v = T.XEVar . name
p :: T.Primitive -> [T.XErased] -> T.XErased
p primitive = foldl T.XEApp (T.XEPrimitive primitive)
ret :: T.XErased -> T.XErased
ret a = p T.PIOReturn [a]
bind :: T.XErased -> Integer -> T.XErased -> T.XErased
bind action n body = p T.PIOBind [action, T.XEAbs (name n) body]
zero :: T.XErased
zero = T.XEInt 0
unit :: T.XErased
unit = T.XEConstructor "()"
readCell :: T.XErased
readCell = p T.PReadIntArray [v 7, zero]

walk :: T.XErased -> [T.XErased]
walk term = term : concatMap walk (O.subterms term)
keeps :: T.XName -> T.XErased -> Bool
keeps sought = any isBinding . walk where
  isBinding (T.XELet actual _ _) = O.eqName sought actual
  isBinding _ = False
pass :: T.XErased -> T.XErased
pass term = fst (O.runFresh (O.pass term) (O.maxIdentity term + 1))
shape :: String -> Bool -> T.XErased -> IO ()
shape label expected term = do
  ensure (keeps (name 0) (pass term) == expected) label
  putStrLn ("PASS shape: " ++ label)

shapeChecks :: IO ()
shapeChecks = do
  let with body = T.XELet (name 0) readCell body
      used = bind (v 0) 1 (ret unit)
  shape "exact bind action exposes single use" False (with used)
  shape "exact bind continuation exposes single use" False
    (with (bind (ret unit) 1 (v 0)))
  shape "two-use action remains shared" True
    (with (bind (v 0) 1 (bind (v 0) 2 (ret unit))))
  shape "partial bind remains opaque" True (with (p T.PIOBind [v 0]))
  shape "non-lambda bind continuation remains opaque" True
    (with (p T.PIOBind [v 0, v 8]))
  shape "unrelated bind does not license substitution" True
    (with (p T.PSeq [bind (ret unit) 1 (ret unit), v 0]))
  shape "ordinary lambda remains a sharing boundary" True
    (with (T.XEAbs (name 2) used))
  shape "recursive group remains a sharing boundary" True
    (with (T.XELetRec [(name 2, T.XEApp (v 2) used)] (v 2)))
  shape "unknown call remains a sharing boundary" True
    (with (T.XEApp (v 8) used))
  shape "computed call remains a sharing boundary" True
    (with (T.XEApp (p T.PIfThenElse [v 9, v 8, v 7]) used))
  shape "partial seq remains opaque" True (with (p T.PSeq [used]))
  shape "two-use pure construction remains shared" True
    (T.XELet (name 0) (p T.PAddInt [T.XEInt 19, T.XEInt 23])
      (bind (ret (v 0)) 1 (ret (v 0))))
  shape "pure construction under ordinary lambda remains shared" True
    (T.XELet (name 0) (p T.PAddInt [T.XEInt 19, T.XEInt 23])
      (T.XEAbs (name 2) (bind (ret unit) 1 (ret (v 0)))))
  shape "scalar under write remains shared" True
    (T.XELet (name 0) (p T.PAddInt [T.XEInt 19, T.XEInt 23])
      (bind (ret unit) 1 (p T.PWriteIntArray [v 7, zero, v 0])))
  shape "scalar under return remains shared" True
    (T.XELet (name 0) (p T.PAddInt [T.XEInt 19, T.XEInt 23])
      (bind (ret unit) 1 (ret (v 0))))
  shape "unused bottom is eliminated without demand" False
    (T.XELet (name 0) (p T.PPanic [T.XEString "unused"]) (ret unit))
  ensure (A.sameNames (S.toList (O.free (with used)))
                     (S.toList (O.free (pass (with used)))))
    "substitution changed same-hint captured identities"
  putStrLn "PASS shape: substitution preserves same-hint captured identities"
  let eligible body = K.eligible M.empty S.empty body
  ensure (not (eligible (with used)) && eligible (pass (with used)))
    "bind action substitution must restore kernel eligibility"
  putStrLn "PASS shape: single-use action restores kernel eligibility"
  ensure (not (eligible (p T.PIOReturn [p T.PQuotInt [T.XEInt 1, zero]])))
    "unsafe quotient unexpectedly became scalar"
  putStrLn "PASS shape: unsafe divisor remains ineligible"

source :: String -> B.String
source body = B.literal $ unlines
  [ "-- mlf:syntax shared-haskell-v1"
  , "{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}"
  , "module IOActionSharing where"
  , "import MLF.Primitive"
  , body
  ]

-- Expected observations live independently in the Python runner as well.
-- Keeping failures as values lets all original/serialized/optimized variants
-- run, without host exception handling changing guest action demand.
data Case = Case String String (Maybe String) Bool

loop :: String -> String
loop action = unlines
  [ "loop :: IntArray -> Int -> IO ()"
  , "loop array n = if n == 0 then ioReturn () else do { " ++ action ++ "; loop array (n - 1) }"
  , "main :: IO ()"
  , "main = do { array <- newIntArray 1 0; loop array 3; answer <- readIntArray array 0; printInt answer }"
  ]

box :: String
box = unlines
  [ "data Box a = Box a"
  , "instance Functor Box where { fmap f (Box x) = Box (f x) }"
  , "instance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }"
  , "unBox (Box x) = x"
  ]

cases :: [Case]
cases =
  [ Case "ground-string-sharing"
      "main = do { source <- ioReturn (\"seed\" :: String); let { text = concatString \"prefix\" source }; printInt (stringLength text); printInt (stringLength text) }" Nothing False
  , Case "different-class-instances" (unlines
      [ "class Choice a where { choice :: a -> Int }"
      , "instance Choice Int where { choice x = 1 }"
      , "instance Choice String where { choice x = 2 }"
      , "pick x = choice x"
      , "main = do { printInt (pick (41 :: Int)); printInt (pick (\"s\" :: String)) }"
      ]) Nothing False
  , Case "common-call-unused-bottom"
      "main = let { argument = (panic \"unused argument\" :: Int); calculate x = addInt x 1 } in if False then do { printInt (calculate argument); printInt (calculate argument) } else putStrLn \"ok\"" Nothing False
  , Case "common-call-fresh-arrays"
      "main = let { initial = 0; allocate x = newIntArray 1 x } in do { first <- allocate initial; second <- allocate initial; writeIntArray first 0 42; answer <- readIntArray second 0; printInt answer }" Nothing False
  , Case "bare-do-loop" (loop "writeIntArray array 0 (n + 41)") Nothing True
  , Case "explicit-bind-loop" (loop "ignored <- writeIntArray array 0 (n + 41)") Nothing True
  , Case "shared-action-twice" (unlines
      [ "run array = let { action = do { old <- readIntArray array 0; writeIntArray array 0 (old + 1); putStrLn \"tick\" } } in do { action; action; answer <- readIntArray array 0; printInt answer }"
      , "main = do { array <- newIntArray 1 0; run array }"
      ]) Nothing False
  , Case "pure-construction-sharing"
      "main = let { answer = addInt 19 23 } in do { printInt answer; printInt answer }" Nothing False
  , Case "unused-bottom"
      "main = let { unused = (panic \"unused action\" :: IO ()) } in putStrLn \"ok\"" Nothing False
  , Case "early-failure-before-late-bottom"
      "main = let { later = (panic \"late bottom\" :: IO ()) } in do { putStrLn \"before\"; (panic \"first failure\" :: IO ()); later }"
      (Just "first failure") False
  , Case "late-bottom-after-effect"
      "main = let { later = (panic \"late bottom\" :: IO ()) } in do { putStrLn \"before\"; later }"
      (Just "late bottom") False
  , Case "seq-action-does-not-execute"
      "main = let { action = putStrLn \"not executed\" } in seq action (putStrLn \"ok\")" Nothing False
  , Case "partial-bind-stays-lazy"
      "main = seq (ioBind (panic \"partial bind\" :: IO ()) :: (() -> IO ()) -> IO ()) (putStrLn \"ok\")" Nothing False
  , Case "partial-sequence-stays-lazy"
      "main = seq (((>>) (panic \"partial sequence\" :: IO ())) :: IO () -> IO ()) (putStrLn \"ok\")" Nothing False
  , Case "capture-avoiding-substitution"
      "run outer = let { later = ioReturn outer } in ioBind (ioReturn 99) (\\outer -> ioBind later printInt)\nmain = run 42" Nothing False
  , Case "ignored-return-payload"
      "main = do { ioReturn (panic \"unused return payload\" :: Int); putStrLn \"ok\" }" Nothing False
  , Case "custom-sequence-override"
      (box ++ "instance Monad Box where { (>>=) (Box x) f = f x; (>>) _ _ = panic \"overridden sequence\" }\nmain = printInt (unBox (do { Box 1; Box 2 }))")
      (Just "overridden sequence") False
  , Case "custom-sequence-ignores-first"
      (box ++ "instance Monad Box where { (>>=) (Box x) f = f x; (>>) _ b = b }\nmain = printInt (unBox (do { (panic \"ignored custom action\" :: Box ()); pure 42 }))") Nothing False
  ]

checkTarget :: T.XTerm -> IO ()
checkTarget term = do
  current <- right (Check.checkClosed term)
  frozen <- right (Frozen.checkClosed term)
  let expected = T.XCon "IO" [T.XCon "()" []]
  ensure (Type.alphaEq current expected && FrozenType.alphaEq frozen expected)
    "source entry must independently check as IO ()"

loopKernel :: T.XErased -> Bool
loopKernel term =
  let functions = A.analyze term
      kernels = K.kernels functions
  in any (\n -> case M.lookup O.compareName n functions of
       T.Just worker -> containsWrite (A.functionBody worker)
       T.Nothing -> False) (S.toList kernels)
  where
    containsWrite = any match . walk
    match (T.XEPrimitive T.PWriteIntArray) = True
    match _ = False

observe :: String -> T.DataEnv -> T.XErased -> Maybe String -> IO ()
observe label declarations term expected = do
  putStrLn ("BEGIN " ++ label)
  result <- R.runAction [] declarations (R.evaluate declarations (R.REnv M.empty) term)
  case (result, expected) of
    (T.Left actual, Just wanted) -> do
      ensure (B.unpack actual == wanted) (label ++ ": unexpected failure " ++ B.unpack actual)
      putStrLn ("OUTCOME error: " ++ wanted)
    (T.Right _, Nothing) -> putStrLn "OUTCOME ok"
    (T.Left actual, Nothing) -> fail (label ++ ": " ++ B.unpack actual)
    (T.Right _, Just wanted) -> fail (label ++ ": missing failure " ++ wanted)

runCase :: FilePath -> Case -> IO ()
runCase destination (Case label body expected wantKernel) = do
  compiled <- case C.compile (B.literal (label ++ ".hs")) (source body) of
    T.Left err -> fail (label ++ ": " ++ B.unpack (C.prettyError err))
    T.Right result -> pure (C.compiledTerm result)
  checkTarget compiled
  let serialized = Pretty.prettyTerm compiled
  parsed <- right (Parse.parseTerm "<IO action sharing roundtrip>" serialized)
  checkTarget parsed
  (declarations, _) <- right (R.prepare True compiled)
  (parsedDeclarations, _) <- right (R.prepare True parsed)
  let original = X.erase compiled
      optimized = O.optimize original
      reparsed = X.erase parsed
  if wantKernel then do
    ensure (loopKernel optimized) (label ++ ": lost native array loop kernel")
    ensure (loopKernel (O.optimize reparsed)) (label ++ ": serialized kernel lost")
    putStrLn ("PASS kernel: " ++ label)
  else pure ()
  llvm <- right (LLVM.emitLLVMIO compiled)
  roundtrip <- right (LLVM.emitLLVMIO parsed)
  ensure (B.unpack llvm == B.unpack roundtrip) (label ++ ": serialization changed LLVM")
  writeFile (destination ++ "/" ++ label ++ ".ll") (B.unpack llvm)
  writeFile (destination ++ "/" ++ label ++ ".xmlf") (B.unpack serialized)
  observe (label ++ "/original") declarations original expected
  observe (label ++ "/serialized") parsedDeclarations reparsed expected
  observe (label ++ "/optimized-erased") declarations optimized expected
  putStrLn ("PASS semantics: " ++ label)

main :: IO ()
main = do
  hSetBuffering stdout LineBuffering
  arguments <- getArgs
  case arguments of
    [destination] -> do
      shapeChecks
      forM_ cases (runCase destination)
      putStrLn "IO action sharing: passed (19 shape checks, 18 source cases, 3 execution forms)"
    _ -> fail "usage: io-action-sharing OUTPUT_DIRECTORY"
