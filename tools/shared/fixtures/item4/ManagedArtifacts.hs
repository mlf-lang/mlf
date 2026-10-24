{-# LANGUAGE OverloadedStrings #-}
-- Focused transport/scope tests; full language and runtime parity are separate gates.
module Main where
import Prelude
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as S
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.Map as M
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.InferenceUnit as I
import qualified Bootstrap.Separate as U
import qualified Bootstrap.SourceEquality as E
import qualified MLF.Primitive as P

list = foldr T.Cons T.Nil
span0 = T.SourceSpan "package" "Module" "File.hs" 1 2 3 4
int = T.XCon "Int" T.Nil
raw = T.XCon "MLFCallStack" T.Nil
evidence = T.XCon "MLFStackEvidence" T.Nil
expected = T.SQualified (list [T.SPredicate "MLFHasCallStack" T.Nil]) (T.SCon "Int" T.Nil)
check name ok = if ok then putStrLn ("PASS " ++ name) else error name
main = do
  check "raw CallStack arrow remains an arrow" $ E.eqSType
    (U.sourceScheme (M.singleton "MLFCallStack" "MLFHasCallStack") (T.XArrow raw int))
    (T.SArrow (T.SCon "MLFCallStack" T.Nil) (T.SCon "Int" T.Nil))
  check "only private evidence recovers managed qualifier" $ E.eqSType
    (U.sourceScheme M.empty (T.XArrow evidence int)) expected
  check "already-lowered ABI retains explicit evidence arrow" $ E.eqSType
    (U.sourceSchemeIn M.empty False (T.XArrow evidence int))
    (T.SArrow (T.SCon "MLFStackEvidence" T.Nil) (T.SCon "Int" T.Nil))
  check "nested raw and evidence arrows do not become top-level qualifiers" $ E.eqSType
    (U.sourceScheme M.empty (T.XArrow (T.XArrow evidence int) int))
    (T.SArrow (T.SArrow (T.SCon "MLFStackEvidence" T.Nil) (T.SCon "Int" T.Nil)) (T.SCon "Int" T.Nil))
  let key s = Q.encodeExpression (T.SCallSite "a do statement" s (T.SVar "fail"))
      spans = [T.SourceSpan "other" "Module" "File.hs" 1 2 3 4,
               T.SourceSpan "package" "Other" "File.hs" 1 2 3 4,
               T.SourceSpan "package" "Module" "Other.hs" 1 2 3 4,
               T.SourceSpan "package" "Module" "File.hs" 2 2 3 4,
               T.SourceSpan "package" "Module" "File.hs" 1 3 3 4,
               T.SourceSpan "package" "Module" "File.hs" 1 2 4 4,
               T.SourceSpan "package" "Module" "File.hs" 1 2 3 5]
  check "every source-span component affects the query key" $ all (not . P.eqString (key span0) . key) spans
  check "call-site label affects the query key" $ not $ P.eqString (key span0)
    (Q.encodeExpression (T.SCallSite "other" span0 (T.SVar "fail")))
  let bind = T.SSharedBind (T.SDefaultPattern (T.Just "x")) (T.SVar "x") (T.SVar "x") (T.SVar "x") (T.SVar "x")
      canon = Q.canonicalExpression (M.singleton "x" "outer") 0 M.empty 0 bind
  check "shared bind canonicalizes scope only in continuation" $ E.eqSExpr canon
    (T.SSharedBind (T.SDefaultPattern (T.Just "local:0")) (T.SVar "outer") (T.SVar "local:0") (T.SVar "outer") (T.SVar "outer"))
  check "as and lazy pattern order remains distinct" $ not $ P.eqString
    (Q.encodePattern (T.SAsPattern "x" (T.SLazyPattern (T.SDefaultPattern T.Nothing))))
    (Q.encodePattern (T.SLazyPattern (T.SAsPattern "x" (T.SDefaultPattern T.Nothing))))
  let method = T.SForall T.Flexible "a" T.SBottom
        (T.SQualified (list [T.SPredicate "MLFHasCallStack" T.Nil])
          (T.SArrow (T.SCon "[]" (list [T.SCon "Char" T.Nil])) (T.STypeApp (T.STVar "m") (T.STVar "a"))))
      cls = T.SClassDecl "MonadFail" (list [T.Pair "m" (T.KArrow T.Star T.Star)])
        (list [T.SPredicate "Monad" (list [T.STVar "m"])]) (list [T.Pair "fail" method])
      iface = U.UnitInterface "Example" T.Nil T.Nil T.Nil (list [cls]) T.Nil T.Nil "object"
  check "qualified method metadata roundtrips" $ case U.decodeInterface (U.encodeInterface iface) of
    T.Right restored -> P.eqString (U.encodeInterface restored) (U.encodeInterface iface)
    _ -> False
  check "intrinsic callStack marker cannot be rebound by hygiene or key normalization" $
    P.eqString (U.hygieneName (M.singleton "$MLF.Stack.callStack" "shadow") "$MLF.Stack.callStack") "$MLF.Stack.callStack"
    && P.eqString (Q.canonicalReference (M.singleton "$MLF.Stack.callStack" "shadow") "$MLF.Stack.callStack") "$MLF.Stack.callStack"
  let managedEntity = Modules.Entity "MLF.Primitive" "HasCallStack" Modules.ManagedConstraint
  check "managed-constraint entity has distinct wire role" $ case U.decodeEntity (U.entityEncoding managedEntity) of
    T.Right restored -> Modules.compareEntity restored managedEntity == 0
    _ -> False
  check "managed aliases are stable only for exact builtin entities" $
    P.eqString (A.definitionName "crate" managedEntity) "MLFHasCallStack"
    && P.eqString (A.definitionName "crate" (Modules.Entity "MLF.Primitive" "CallStack" Modules.BuiltinType)) "MLFCallStack"
    && P.eqString (A.definitionName "crate" (Modules.Entity "MLF.Primitive" "callStack" Modules.Value)) "mlfCallStack"
    && not (P.eqString (A.definitionName "crate" (Modules.Entity "User" "HasCallStack" Modules.Class)) "MLFHasCallStack")
    && not (P.eqString (A.definitionName "crate" (Modules.Entity "MLF.Primitive" "HasCallStack" Modules.Class)) "MLFHasCallStack")
  check "forged managed constraint ownership rejected" $ case U.decodeEntity
    (U.entityEncoding (Modules.Entity "User" "HasCallStack" Modules.ManagedConstraint)) of
      T.Left _ -> True
      _ -> False
  let a = T.XTyVar 0
      ioErrorType = T.XForall a T.XBot
        (T.XArrow evidence (T.XArrow (T.XCon "IOError" T.Nil) (T.XCon "IO" (list [T.XVar a]))))
      ioInterface = U.UnitInterface "Example" T.Nil T.Nil T.Nil T.Nil T.Nil
        (list [T.Pair "ioError" ioErrorType]) "object"
  check "qualified public ioError interface roundtrips" $ case U.decodeInterface (U.encodeInterface ioInterface) of
    T.Right restored -> P.eqString (U.encodeInterface restored) (U.encodeInterface ioInterface)
    _ -> False
  check "additive-v2 interfaces now rejected" $ case U.unpack (U.encodeInterface ioInterface) of
    T.Right (T.Cons _ fields) -> case U.decodeInterface (U.pack (T.Cons "MLFI-2" fields)) of
      T.Left _ -> True
      _ -> False
    _ -> False
  let crate = A.CrateInterface "test" T.Nil T.Nil T.Nil T.Nil T.Nil T.Nil T.Nil T.Nil T.Nil "" "object"
  check "current crate contract accepted" $ case A.decodeInterface (A.encodeInterface crate) of
    T.Right _ -> True
    _ -> False
  check "additive-v2 crate interfaces now rejected" $ case U.unpack (A.encodeInterface crate) of
    T.Right (T.Cons _ fields) -> case A.decodeInterface (U.pack (T.Cons "MLFCI-2" fields)) of
      T.Left _ -> True
      _ -> False
    _ -> False
  let pattern0 = T.SAsPattern "whole" (T.SLazyPattern (T.SDefaultPattern (T.Just "part")))
      original = T.SLet "x" (T.SIntLit 1)
        (T.SSharedBind (T.SDefaultPattern (T.Just "x")) (T.SVar "x") (T.SVar "x") (T.SVar "x") (T.SVar "x"))
  check "as/lazy pattern canonicalizes bound names" $ E.eqSPattern
    (Q.canonicalPattern (M.fromList P.compareString (list [T.Pair "whole" "w", T.Pair "part" "p"])) M.empty 0 pattern0)
    (T.SAsPattern "w" (T.SLazyPattern (T.SDefaultPattern (T.Just "p"))))
  check "shared-bind hygiene preserves action and failure outer scope" $ case U.hygiene original of
    T.Right (T.SLet outer _ (T.SSharedBind (T.SDefaultPattern (T.Just inner))
      (T.SVar action) (T.SVar body) (T.SVar bindMethod) (T.SVar failure))) ->
        not (P.eqString outer inner) && P.eqString action outer && P.eqString body inner
          && P.eqString bindMethod outer && P.eqString failure outer
    _ -> False
  let chars = T.XCon "[]" (list [T.XCon "Char" T.Nil])
      dependency = U.UnitInterface "provider" T.Nil T.Nil T.Nil T.Nil T.Nil
        (list [T.Pair "who" (T.XArrow evidence chars)]) "metadata"
      stack = T.SApp (T.SConstructor "MLFStackEvidence") (T.SPrimitive T.PEmptyCallStack)
      expression = T.SApp (T.SPrimitive T.PTextFromChars) (T.SApp (T.SVar "who") stack)
  check "already-lowered external application does not receive evidence twice" $
    case I.compileLoweredGroup "consumer" (list [dependency]) T.Nil
      (list [T.Triple "main" T.Nothing expression]) of
        T.Right object -> case U.unitBindings (U.objectInterface object) of
          T.Cons (T.Pair "main" (T.XCon "String" T.Nil)) T.Nil -> True
          _ -> False
        T.Left _ -> False
  putStrLn "item4 managed artifact contracts: passed"
