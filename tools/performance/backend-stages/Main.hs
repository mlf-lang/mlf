{-# LANGUAGE OverloadedStrings #-}
-- Diagnostic only. The production backend is linked unchanged. Explicit
-- traversals move lazy work to visible boundaries and perturb allocation/GC;
-- these intervals are not ordinary compilation latency or an additive profile.
module Main where

import Prelude
import Control.Exception (SomeException, evaluate, try)
import Data.List (isInfixOf)
import Control.Monad (forM, forM_)
import GHC.Clock (getMonotonicTimeNSec)
import System.Environment (getArgs)
import System.IO (hPutStrLn, stderr)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.Data as D
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.X.Checked as Checked
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.LLVM as LLVM
import qualified Bootstrap.LLVM.Optimize as O
import qualified Bootstrap.LLVM.StrictWrappers as W
import qualified Bootstrap.LLVM.Codegen as C

ok value = case value of
  T.Left message -> error (P.textToChars message)
  T.Right result -> pure result

mark label = do
  now <- getMonotonicTimeNSec
  hPutStrLn stderr ("MLF_BACKEND_PHASE " ++ label ++ " " ++ show now)

-- A fresh call traverses the same result again, recording forcing overhead.
-- The pinned GHC 9.14 OPAQUE boundary forbids inlining, specialization and
-- worker/wrapper transformation here. NOINLINE alone would still permit
-- transformations that expose the pure traversal at its calling sites.
{-# OPAQUE forceAt #-}
forceAt label force value = do
  _ <- evaluate (force value)
  mark label

forced label force value = do
  forceAt label force value
  forceAt (label ++ "-forced-again") force value
  pure value

forceList f = foldr (\x rest -> f x `seq` rest) ()
scalar value = value `seq` ()
-- Force the host String representation and scalar count, not a byte scan or
-- its lazy scalar-offset index. Output bytes are checked separately by run.py.
string value = P.stringLength value `seq` ()
name (T.XName identity hint) = identity `seq` string hint
variable (T.XTyVar identity) = scalar identity
kind T.Star = ()
kind (T.KArrow a b) = kind a `seq` kind b
optional f T.Nothing = ()
optional f (T.Just x) = f x
field value = case value of
  T.Parameter n -> string n
  T.Function a b -> field a `seq` field b
  T.Applied n fs -> string n `seq` forceList field fs
  T.Application a b -> field a `seq` field b
  T.Quantified n k f -> string n `seq` kind k `seq` field f
constructor (T.ConstructorDecl n fs) = string n `seq` forceList field fs
declaration value = case value of
  T.DataDecl n ps cs -> string n `seq` forceList string ps `seq` forceList constructor cs
  T.DataDeclK n ps cs -> string n `seq` forceList (\(p,k) -> string p `seq` kind k) ps `seq` forceList constructor cs
xtype value = case value of
  T.XVar v -> variable v
  T.XBot -> ()
  T.XBotKind k -> kind k
  T.XArrow a b -> xtype a `seq` xtype b
  T.XCon n ts -> string n `seq` forceList xtype ts
  T.XApply a b -> xtype a `seq` xtype b
  T.XForall v a b -> variable v `seq` xtype a `seq` xtype b
computation value = case value of
  T.XRefl -> ()
  T.XBottom t -> xtype t
  T.XHyp v -> variable v
  T.XInner c -> computation c
  T.XOuter v c -> variable v `seq` computation c
  T.XElim -> ()
  T.XIntro v -> variable v
  T.XIntroKind v k -> variable v `seq` kind k
  T.XThen a b -> computation a `seq` computation b
patternValue value = case value of
  T.XConstructorPattern n ns -> string n `seq` forceList (optional name) ns
  T.XDefaultPattern n -> optional name n
term value = case value of
  T.XVarTerm n -> name n
  T.XAbs n t b -> name n `seq` xtype t `seq` term b
  T.XApp f a -> term f `seq` term a
  T.XTypeAbs v t b -> variable v `seq` xtype t `seq` term b
  T.XTypeApp b c -> term b `seq` computation c
  T.XLet n a b -> name n `seq` term a `seq` term b
  T.XLetRec ds b -> forceList (\(n,t,r) -> name n `seq` xtype t `seq` term r) ds `seq` term b
  T.XIntTerm x -> scalar x
  T.XDoubleTerm x -> scalar x
  T.XBoolTerm x -> scalar x
  T.XStringTerm x -> string x
  T.XPrimitive p ts -> scalar p `seq` forceList xtype ts
  T.XConstructor n ts -> string n `seq` forceList xtype ts
  T.XCase s t as -> term s `seq` xtype t `seq` forceList (\(T.XAlternative p b) -> patternValue p `seq` term b) as
  T.XWithData ds b -> forceList declaration ds `seq` term b
erased value = case value of
  T.XEVar n -> name n
  T.XEAbs n b -> name n `seq` erased b
  T.XEApp f a -> erased f `seq` erased a
  T.XELet n a b -> name n `seq` erased a `seq` erased b
  T.XEInt x -> scalar x
  T.XEDouble x -> scalar x
  T.XEBool x -> scalar x
  T.XEString x -> string x
  T.XEPrimitive p -> scalar p
  T.XELetRec ds b -> forceList (\(n,r) -> name n `seq` erased r) ds `seq` erased b
  T.XEEvidenceHole x -> scalar x
  T.XEConstructor n -> string n
  T.XECase s as -> erased s `seq` forceList (\(T.XErasedAlternative p b) -> patternValue p `seq` erased b) as

-- Diagnostic copy of LLVM.entryConstructors (which is private). The runner
-- pins the production owner and requires byte-identical ordinary LLVM output.
constructors declarations = M.fromList P.compareString (zipWith LLVM.constructorEntry [0..] allConstructors)
  where
    builtins = concatMap LLVM.dataConstructors D.builtinDeclarations
    builtinNames = map D.constructorName builtins
    users = filter (\c -> not (any (P.eqString (D.constructorName c)) builtinNames))
      (concatMap LLVM.dataConstructors declarations)
    allConstructors = builtins ++ users

inputPath path = do
  let chars = P.textToChars path
  if any (\c -> c == '\r' || c == '\n') chars then error "newline in input path is unsupported" else putStrLn chars

-- Bottom controls verify that the checkpoint visitors demand nested payloads,
-- list tails and type-only nodes, rather than just each outer constructor.
selfTest = do
  let bad = error "backend-force-sentinel"
      n = T.XName 1 "name"
      checks =
        [ ("scalar", scalar (bad :: Int))
        , ("string", string bad)
        , ("list-tail", forceList scalar (() : bad))
        , ("name-identity", name (T.XName bad "hint"))
        , ("name-hint", name (T.XName 1 bad))
        , ("kind", kind (T.KArrow T.Star bad))
        , ("field", field (T.Quantified "a" T.Star (T.Applied "T" [bad])))
        , ("declaration", declaration (T.DataDeclK "T" [("a",bad)] []))
        , ("constructor", constructor (T.ConstructorDecl "C" [bad]))
        , ("type", xtype (T.XForall (T.XTyVar 0) T.XBot (T.XCon "T" [bad])))
        , ("type-variable", variable (T.XTyVar bad))
        , ("computation", computation (T.XThen T.XRefl (T.XIntroKind (T.XTyVar 0) bad)))
        , ("pattern", patternValue (T.XConstructorPattern "C" [T.Just bad]))
        , ("term-type", term (T.XAbs n bad (T.XIntTerm 0)))
        , ("term-computation", term (T.XTypeApp (T.XIntTerm 0) bad))
        , ("term-let", term (T.XLet n (T.XIntTerm 0) bad))
        , ("term-rec", term (T.XLetRec [(n,T.XBot,bad)] (T.XIntTerm 0)))
        , ("term-case", term (T.XCase (T.XIntTerm 0) T.XBot [T.XAlternative (T.XDefaultPattern T.Nothing) bad]))
        , ("term-data", term (T.XWithData [bad] (T.XIntTerm 0)))
        , ("erased-app", erased (T.XEApp (T.XEInt 0) bad))
        , ("erased-let", erased (T.XELet n (T.XEInt 0) bad))
        , ("erased-rec", erased (T.XELetRec [(n,bad)] (T.XEInt 0)))
        , ("erased-case", erased (T.XECase (T.XEInt 0) [T.XErasedAlternative (T.XDefaultPattern T.Nothing) bad]))
        , ("erased-pattern", erased (T.XECase (T.XEInt 0) [T.XErasedAlternative bad (T.XEInt 0)]))
        , ("erased-string", erased (T.XEString bad))
        , ("erased-primitive", erased (T.XEPrimitive bad))
        ]
  forM_ checks $ \(label, value) -> do
    result <- try (evaluate value) :: IO (Either SomeException ())
    case result of
      Left exception | "backend-force-sentinel" `isInfixOf` show exception -> pure ()
      _ -> error ("checkpoint did not force " ++ label)
  _ <- evaluate (term (T.XLet n (T.XIntTerm 1) (T.XVarTerm n)))
  _ <- evaluate (erased (T.XELet n (T.XEString "λ") (T.XEVar n)))
  putStrLn "PASS 26 nested forcing controls and 2 total controls"

main = do
  arguments <- getArgs
  case arguments of
    ["self-test"] -> selfTest
    ["inputs", path] -> do
      interfaces <- A.loadInterfaces [P.textFromChars path] >>= ok
      forM_ interfaces $ \(metadata,_) -> inputPath metadata >> inputPath (A.objectPath metadata)
    ["profile", path] -> do
      mark "start"
      interfaces <- A.loadInterfaces [P.textFromChars path] >>= ok
      if null interfaces then error "empty crate graph" else pure ()
      objects <- forM interfaces $ \(metadata,iface) -> A.readObject (A.objectPath metadata) iface >>= ok
      checked <- ok (A.linkCheckedObjects objects (A.crateId (snd (last interfaces))))
      _ <- forced "load-link-checked" (\c -> term (Checked.term c) `seq` xtype (Checked.typeOf c)) checked
      let checkedTerm = Checked.term checked
          declarations = case checkedTerm of { T.XWithData ds _ -> ds; _ -> [] }
          cs = constructors declarations
      _ <- forced "constructors" (forceList (\(n,(tag,arity)) -> string n `seq` tag `seq` scalar arity) . M.toList) cs
      raw <- forced "erase" erased (X.erase checkedTerm)
      optimized <- forced "optimize" erased (O.optimizeOwned raw)
      lowered <- forced "representation" erased (W.optimize declarations cs optimized)
      generated <- ok (C.generate cs lowered)
      (entry,code) <- forced "generate" (\(e,ls) -> string e `seq` forceList string ls) generated
      let output = ["; Generated from independently checked xMLF.", "source_filename = \"emlf\"", ""]
            ++ code ++ LLVM.entryCode entry (LLVM.ioType (Checked.typeOf checked))
      mapM_ (\line -> P.putStr (line P.++ "\n")) output
      mark "write"
    _ -> error "usage: backend-stages inputs|profile ROOT.mlfci"
