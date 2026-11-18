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
bad (T.Left _) = True
bad _ = False
int = T.XCon "Int" []
bool = T.XCon "Bool" []
ty = T.XArrow int int
inputs i name = [(V.fromInt i, name, ty)]
member = memberWith "x"
memberWith binder dep owner arg name amount =
 [(V.fromInt owner, (name, T.Nothing,
   T.SDeclScope [V.fromInt arg] (T.SLam binder T.Nothing
    (T.SApp (T.SGlobal (V.fromInt dep) "ignored")
     (T.SApp (T.SApp (T.SPrimitive T.PAddInt) (T.SGlobal (V.fromInt arg) binder))
      (T.SIntLit amount))))))]

main = do
 let ps = inputs 3 "previous"
     first = member 3 10 11 "first" 1
     qs = inputs 23 "renamedPrevious"
     second = memberWith "renamed" 23 30 31 "second" 1
 (original, cache) <- right "first inferred fragment" (C.compileIndexedMemo "context" M.empty "first" ps [] first)
 need "unsigned monotype retains one checked template" (M.size cache == 1)
 (reused, cache2) <- right "renamed inferred fragment" (C.compileIndexedMemo "context" cache "second" qs [] second)
 need "renamed dependency, owner and local binder reuse one template" (M.size cache2 == 1)
 direct <- right "direct inference" (I.compileOpenGroupIndexed "second" qs [] second)
 audited <- right "audit reused proof" (O.audit reused)
 need "reused and direct erasures match" (X.equalErased (X.erase (O.closedTerm audited)) (X.erase (O.closedTerm direct)))
 a <- right "independent reused checker" (Independent.checkClosed (O.closedTerm audited))
 b <- right "independent direct checker" (Independent.checkClosed (O.closedTerm direct))
 need "independent types agree" (Y.alphaEq a b)
 need "exported monotype is unchanged" (case O.bindings reused of [(_,t)] -> Y.alphaEq t ty; _ -> False)
 key <- right "unsigned key" (C.inferenceTemplateKey "context" ps first)
 renamed <- right "renamed key" (C.inferenceTemplateKey "context" qs second)
 need "resolved identities normalize" (key == renamed)
 otherContext <- right "context key" (C.inferenceTemplateKey "different" ps first)
 need "datatype context participates in key" (key /= otherContext)
 changedLiteral <- right "literal key" (C.inferenceTemplateKey "context" qs (member 23 30 31 "second" 2))
 need "literal participates in key" (key /= changedLiteral)
 let returnsBool = [(V.fromInt 23,"renamedPrevious",T.XArrow int bool)]
 changedType <- right "changed dependency key" (C.inferenceTemplateKey "context" returnsBool second)
 need "dependency scheme participates in key" (key /= changedType)
 (newResult, cache3) <- right "changed result type" (C.compileIndexedMemo "context" cache "second" returnsBool [] second)
 need "scheme change creates a distinct template" (M.size cache3 == 2)
 need "changed dependency gets independently inferred result" (case O.bindings newResult of [(_,t)] -> Y.alphaEq t (T.XArrow int bool); _ -> False)
 _ <- right "independent changed checker" (Independent.checkClosed (O.closedTerm newResult))
 let wantsBool = [(V.fromInt 23,"renamedPrevious",T.XArrow bool int)]
 need "incompatible dependency rejects instead of reusing" (bad (C.compileIndexedMemo "context" cache "second" wantsBool [] second))
 need "open dependency scheme rejected" (bad (C.inferenceTemplateKey "context" [(V.fromInt 3,"previous",T.XVar (T.XTyVar 999))] first))
 need "owner cannot import itself" (bad (C.inferenceTemplateKey "context" (inputs 10 "previous") (member 10 10 11 "first" 1)))
 need "binder identity capture rejected" (bad (C.inferenceTemplateKey "context" ps (member 3 10 3 "bad" 1)))
 need "unknown resolved dependency rejected" (bad (C.inferenceTemplateKey "context" ps (member 99 10 11 "bad" 1)))
 need "duplicate dependency identity rejected" (bad (C.inferenceTemplateKey "context" (ps ++ [(V.fromInt 3,"other",ty)]) first))
 need "duplicate dependency name rejected" (bad (C.inferenceTemplateKey "context" (ps ++ [(V.fromInt 4,"previous",ty)]) first))
 need "multi-member recursive SCC is not a template" (bad (C.inferenceTemplateKey "context" ps (first ++ member 3 20 21 "other" 1)))
 need "independent unsigned roots keep ordinary admission" (bad (C.inferenceTemplateKey "context" [] [(V.fromInt 10,("root",T.Nothing,T.SIntLit 1))]))
 putStrLn "PASS inferred template reuse, independent types and erasure, scheme changes and admission rejection"
