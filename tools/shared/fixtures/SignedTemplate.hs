{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad (unless)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.IndexVec as V
import qualified Bootstrap.CrateGraph as C
import qualified Bootstrap.InferenceUnit as I
import qualified Bootstrap.OpenFragment as O
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Type as Y
import qualified Tests.IndependentCheck as Independent

need label ok = unless ok (fail label)
right _ (T.Right x) = pure x
right label (T.Left e) = fail (label ++ ": " ++ B.unpack e)
int = T.SCon "Int" []
arrow = T.SArrow int int
ty = T.XArrow (T.XCon "Int" []) (T.XCon "Int" [])
inputs i name = [(V.fromInt i,name,ty)]
member dep owner arg name annotation amount =
 [(V.fromInt owner,(name,T.Just (T.SAnnotation [] annotation),
   T.SChecked annotation (T.SDeclScope [V.fromInt arg] (T.SLam "x" T.Nothing
    (T.SApp (T.SGlobal (V.fromInt dep) "ignored")
     (T.SApp (T.SApp (T.SPrimitive T.PAddInt) (T.SGlobal (V.fromInt arg) "x")) (T.SIntLit amount)))))))]

main = do
 let ps = inputs 3 "previous"
     first = member 3 10 11 "first" arrow 1
     second = member 23 30 31 "second" arrow 1
     qs = inputs 23 "renamedPrevious"
 (original,cache) <- right "first checked fragment" (C.compileIndexedMemo "context" M.empty "first" ps [] first)
 need "signed singleton must retain its checked template" (M.size cache == 1)
 (reused,cache2) <- right "second checked fragment" (C.compileIndexedMemo "context" cache "second" qs [] second)
 need "renamed dependency and owner must reuse one template" (M.size cache2 == 1)
 direct <- right "independent nonmemoized inference" (I.compileOpenGroupIndexed "second" qs [] second)
 audited <- right "audit reused proof" (O.audit reused)
 need "reused and direct erased terms are identical" (X.equalErased (X.erase (O.closedTerm audited)) (X.erase (O.closedTerm direct)))
 a <- right "independent reused checker" (Independent.checkClosed (O.closedTerm audited))
 b <- right "independent direct checker" (Independent.checkClosed (O.closedTerm direct))
 need "independent checked types agree" (Y.alphaEq a b)
 key <- right "signed key" (C.inferenceTemplateKey "context" ps first)
 renamed <- right "renamed key" (C.inferenceTemplateKey "context" qs second)
 need "resolved identities normalize consistently" (key == renamed)
 let wrong = member 23 30 31 "second" (T.SArrow int (T.SCon "Bool" [])) 1
 changed <- right "changed signature key" (C.inferenceTemplateKey "context" qs wrong)
 need "signature participates in template identity" (key /= changed)
 need "wrong signature cannot reuse a checked template"
  (case C.compileIndexedMemo "context" cache "second" qs [] wrong of T.Left _ -> True; _ -> False)
 literal <- right "changed literal key" (C.inferenceTemplateKey "context" qs (member 23 30 31 "second" arrow 2))
 need "literal participates in template identity" (literal /= key)
 need "binder identity capture is rejected"
  (case C.inferenceTemplateKey "context" ps (member 3 10 3 "bad" arrow 1) of T.Left _ -> True; _ -> False)
 need "unresolved dependency is rejected"
  (case C.inferenceTemplateKey "context" ps (member 99 10 11 "bad" arrow 1) of T.Left _ -> True; _ -> False)
 putStrLn "PASS signed template identity, exact erasure, independent checker and rejection controls"
