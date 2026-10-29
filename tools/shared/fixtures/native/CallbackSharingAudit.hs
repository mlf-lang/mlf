{-# LANGUAGE OverloadedStrings #-}
-- Independent exact controls for callback code sharing. Environments are never interned.
module Main where
import Prelude
import Data.List (isInfixOf)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as S
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as Set
import qualified Bootstrap.LLVM.Build as B
import qualified Bootstrap.LLVM.Codegen as C
import qualified Bootstrap.LLVM.Analysis as A
import qualified Bootstrap.LLVM.Optimize as O
import qualified MLF.Primitive as P
n i = T.XName i "test"
a = n 10; b = n 20; x = n 30; y = n 40; f = n 50; g = n 60
state = B.Output 0 [] "entry" [] [] M.empty M.empty Set.empty M.empty Set.empty Set.empty Set.empty M.empty True M.empty M.empty M.empty M.empty M.empty Set.empty M.empty M.empty M.empty
key st clear caps arg expr = C.callbackKey st clear caps arg expr
same a b = case (a,b) of { (T.Just x,T.Just y) -> S.eqList P.eqString x y; _ -> False }
assert label value = if value then putStrLn ("PASS "++label) else error label
definitionHeader st name count = case B.runBuild
 (B.definitionBody name [] (mapM_ (\_ -> B.emit "  ; audit instruction") [1..count])) st of
 T.Left _ -> error "definition build"
 T.Right (_,out) -> case B.definitions out of
  [text] -> case lines (P.textToChars text) of
   first:_ -> first
   [] -> error "empty definition"
  _ -> error "definition inventory"
main = do
 let var = T.XEVar; app = T.XEApp; prim = T.XEPrimitive; add u v = app (app (prim T.PAddInt) u) v
     k = key state False [a] T.Nothing (var a)
     worker = A.WorkerFunction [] (var a) [a] Set.empty (A.EntryDemand [] False)
     fs = M.fromList O.compareName [(f,worker),(g,worker)]
     workers = B.withFunctions fs state
 assert "capture alpha equivalence" (same k (key state False [b] T.Nothing (var b)))
 assert "capture order differs" (not (same (key state False [a,b] T.Nothing (add (var a) (var b))) (key state False [b,a] T.Nothing (add (var a) (var b)))))
 assert "argument alpha equivalence" (same (key state False [a] (T.Just x) (add (var a) (var x))) (key state False [b] (T.Just y) (add (var b) (var y))))
 assert "argument presence differs" (not (same k (key state False [a] (T.Just x) (var a))))
 assert "capture count differs" (not (same k (key state False [a,b] T.Nothing (var a))))
 assert "clear mode differs" (not (same k (key state True [a] T.Nothing (var a))))
 assert "primitive mode differs" (not (same k (key (B.withInlinePrimitives False state) False [a] T.Nothing (var a))))
 assert "static worker differs" (not (same (key workers False [a] T.Nothing (var f)) (key workers False [a] T.Nothing (var g))))
 assert "implicit worker capture slots differ" (not (same (key workers False [a,b] T.Nothing (var f)) (key workers False [b,a] T.Nothing (var f))))
 assert "unused capture identity is irrelevant" (same (key workers False [a,b] T.Nothing (var f)) (key workers False [a,y] T.Nothing (var f)))
 assert "case binders alpha equivalence" (same (key state False [a] T.Nothing (T.XECase (var a) [T.XErasedAlternative (T.XDefaultPattern (T.Just x)) (var x)])) (key state False [b] T.Nothing (T.XECase (var b) [T.XErasedAlternative (T.XDefaultPattern (T.Just y)) (var y)])))
 assert "double signed zero distinct" (not (same (key state False [] T.Nothing (T.XEDouble 0.0)) (key state False [] T.Nothing (T.XEDouble (-0.0)))))
 assert "string token boundary exact" (not (same (key state False [] T.Nothing (T.XEString "apply")) (key state False [] T.Nothing (T.XEString "applylocal"))))
 assert "global identity same hint differs" (not (same (key state False [] T.Nothing (var a)) (key state False [] T.Nothing (var b))))
 assert "primitive identities differ" (not (same (key state False [] T.Nothing (prim T.PAddInt)) (key state False [] T.Nothing (prim T.PSubInt))))
 assert "local let alpha equivalence" (same (key state False [a] T.Nothing (T.XELet x (var a) (var x))) (key state False [b] T.Nothing (T.XELet y (var b) (var y))))
 assert "bound worker refused" (case key workers False [a] T.Nothing (T.XELet f (var a) (var f)) of { T.Nothing -> True; _ -> False })
 assert "worker argument refused" (case key workers False [] (T.Just f) (var f) of { T.Nothing -> True; _ -> False })
 assert "recursive group refused" (case key state False [] T.Nothing (T.XELetRec [(a,var a)] (var a)) of { T.Nothing -> True; _ -> False })
 assert "ignored pattern field differs" (not (same (key state False [a] T.Nothing (T.XECase (var a) [T.XErasedAlternative (T.XDefaultPattern T.Nothing) (T.XEInt 1)])) (key state False [a] T.Nothing (T.XECase (var a) [T.XErasedAlternative (T.XDefaultPattern (T.Just x)) (T.XEInt 1)]))))
 assert "branch order differs" (not (same (key state False [a] T.Nothing (T.XECase (var a) [T.XErasedAlternative (T.XConstructorPattern "A" []) (T.XEInt 1),T.XErasedAlternative (T.XConstructorPattern "B" []) (T.XEInt 2)])) (key state False [a] T.Nothing (T.XECase (var a) [T.XErasedAlternative (T.XConstructorPattern "B" []) (T.XEInt 2),T.XErasedAlternative (T.XConstructorPattern "A" []) (T.XEInt 1)]))))
 case B.runBuild (do { one <- C.callbackWithClear False [a] T.Nothing (var a); two <- C.callbackWithClear False [b] T.Nothing (var b); three <- C.callbackWithClear True [b] T.Nothing (var b); B.cgPure (one,two,three) }) state of
  T.Left _ -> error "callback build"
  T.Right ((one,two,three),out) -> do
   assert "reuses completed callback" (P.eqString one two && not (P.eqString two three))
   assert "one definition per distinct key" (length (B.definitions out) == 2)
 assert "small worker retains inline choice" (not ("noinline" `isInfixOf` definitionHeader state "@mlf.worker.10" 63))
 assert "large worker bounds cloning" ("noinline" `isInfixOf` definitionHeader state "@mlf.worker.10" 64)
 assert "large numeric worker stays inline" ("alwaysinline" `isInfixOf` definitionHeader state "@mlf.numeric.10" 64)
 assert "collecting numeric worker stays ordinary" (not ("alwaysinline" `isInfixOf` definitionHeader (B.withCollectingKernels (Set.singleton (n 10)) state) "@mlf.numeric.10" 64))
 putStrLn "Independent callback sharing audit: 27 checks passed"
