{-# LANGUAGE OverloadedStrings #-}
-- Independent exact controls for callback code sharing. Environments are never interned.
module Main where
import System.Environment (getArgs)
import System.Exit (exitSuccess)
import Prelude
import Data.List (isInfixOf)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as S
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as Set
import qualified Bootstrap.LLVM.Build as B
import qualified Bootstrap.LLVM.Codegen as C
import qualified Bootstrap.LLVM.Analysis as A
import qualified Bootstrap.LLVM.Kernel as K
import qualified Bootstrap.LLVM.Optimize as O
import qualified MLF.Primitive as P
n i = T.XName i "test"
a = n 10; b = n 20; x = n 30; y = n 40; f = n 50; g = n 60
state = B.Output 0 [] "entry" [] [] M.empty (B.FunctionScope M.empty M.empty)
 Set.empty M.empty Set.empty Set.empty Set.empty M.empty True M.empty M.empty
 M.empty M.empty M.empty Set.empty M.empty M.empty M.empty
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
 args <- getArgs
 selected <- case args of
  [] -> pure Nothing
  ["--exact", label] -> pure (Just label)
  _ -> fail "usage: callback-sharing-audit [--exact LABEL]"
 let check label condition = case selected of
      Nothing -> assert label condition
      Just target -> if target == label then assert label condition >> exitSuccess else pure ()
 let var = T.XEVar; app = T.XEApp; prim = T.XEPrimitive; add u v = app (app (prim T.PAddInt) u) v
     k = key state False [a] T.Nothing (var a)
     worker = A.WorkerFunction [] (var a) [a] Set.empty (A.EntryDemand [] False)
     fs = M.fromList O.compareName [(f,worker),(g,worker)]
     workers = B.withFunctions fs state
 check "capture alpha equivalence" (same k (key state False [b] T.Nothing (var b)))
 check "capture order differs" (not (same (key state False [a,b] T.Nothing (add (var a) (var b))) (key state False [b,a] T.Nothing (add (var a) (var b)))))
 check "argument alpha equivalence" (same (key state False [a] (T.Just x) (add (var a) (var x))) (key state False [b] (T.Just y) (add (var b) (var y))))
 check "argument presence differs" (not (same k (key state False [a] (T.Just x) (var a))))
 check "capture count differs" (not (same k (key state False [a,b] T.Nothing (var a))))
 check "clear mode differs" (not (same k (key state True [a] T.Nothing (var a))))
 check "primitive mode differs" (not (same k (key (B.withInlinePrimitives False state) False [a] T.Nothing (var a))))
 check "static worker differs" (not (same (key workers False [a] T.Nothing (var f)) (key workers False [a] T.Nothing (var g))))
 check "implicit worker capture slots differ" (not (same (key workers False [a,b] T.Nothing (var f)) (key workers False [b,a] T.Nothing (var f))))
 check "unused capture identity is irrelevant" (same (key workers False [a,b] T.Nothing (var f)) (key workers False [a,y] T.Nothing (var f)))
 check "case binders alpha equivalence" (same (key state False [a] T.Nothing (T.XECase (var a) [T.XErasedAlternative (T.XDefaultPattern (T.Just x)) (var x)])) (key state False [b] T.Nothing (T.XECase (var b) [T.XErasedAlternative (T.XDefaultPattern (T.Just y)) (var y)])))
 check "double signed zero distinct" (not (same (key state False [] T.Nothing (T.XEDouble 0.0)) (key state False [] T.Nothing (T.XEDouble (-0.0)))))
 check "string token boundary exact" (not (same (key state False [] T.Nothing (T.XEString "apply")) (key state False [] T.Nothing (T.XEString "applylocal"))))
 check "global identity same hint differs" (not (same (key state False [] T.Nothing (var a)) (key state False [] T.Nothing (var b))))
 check "primitive identities differ" (not (same (key state False [] T.Nothing (prim T.PAddInt)) (key state False [] T.Nothing (prim T.PSubInt))))
 check "local let alpha equivalence" (same (key state False [a] T.Nothing (T.XELet x (var a) (var x))) (key state False [b] T.Nothing (T.XELet y (var b) (var y))))
 check "bound worker refused" (case key workers False [a] T.Nothing (T.XELet f (var a) (var f)) of { T.Nothing -> True; _ -> False })
 check "worker argument refused" (case key workers False [] (T.Just f) (var f) of { T.Nothing -> True; _ -> False })
 check "recursive group refused" (case key state False [] T.Nothing (T.XELetRec [(a,var a)] (var a)) of { T.Nothing -> True; _ -> False })
 check "ignored pattern field differs" (not (same (key state False [a] T.Nothing (T.XECase (var a) [T.XErasedAlternative (T.XDefaultPattern T.Nothing) (T.XEInt 1)])) (key state False [a] T.Nothing (T.XECase (var a) [T.XErasedAlternative (T.XDefaultPattern (T.Just x)) (T.XEInt 1)]))))
 check "branch order differs" (not (same (key state False [a] T.Nothing (T.XECase (var a) [T.XErasedAlternative (T.XConstructorPattern "A" []) (T.XEInt 1),T.XErasedAlternative (T.XConstructorPattern "B" []) (T.XEInt 2)])) (key state False [a] T.Nothing (T.XECase (var a) [T.XErasedAlternative (T.XConstructorPattern "B" []) (T.XEInt 2),T.XErasedAlternative (T.XConstructorPattern "A" []) (T.XEInt 1)]))))
 if maybe True (`elem` ["reuses completed callback", "one definition per distinct key"]) selected
  then do
   case B.runBuild (do { one <- C.callbackWithClear False [a] T.Nothing (var a); two <- C.callbackWithClear False [b] T.Nothing (var b); three <- C.callbackWithClear True [b] T.Nothing (var b); B.cgPure (one,two,three) }) state of
    T.Left _ -> error "callback build"
    T.Right ((one,two,three),out) -> do
     check "reuses completed callback" (P.eqString one two && not (P.eqString two three))
     check "one definition per distinct key" (length (B.definitions out) == 2)
  else pure ()
 check "small worker retains inline choice" (not ("noinline" `isInfixOf` definitionHeader state "@mlf.worker.10" 63))
 check "large worker bounds cloning" ("noinline" `isInfixOf` definitionHeader state "@mlf.worker.10" 64)
 check "large numeric worker stays inline" ("alwaysinline" `isInfixOf` definitionHeader state "@mlf.numeric.10" 64)
 check "collecting numeric worker stays ordinary" (not ("alwaysinline" `isInfixOf` definitionHeader (B.withCollectingKernels (Set.singleton (n 10)) state) "@mlf.numeric.10" 64))
 let unary body = A.WorkerFunction [x] body [] Set.empty (A.EntryDemand [] False)
     binary body = A.WorkerFunction [x,y] body [] Set.empty (A.EntryDemand [] False)
     use name = app (var name) (var x)
     branch predicate yes no = app (app (app (prim T.PIfThenElse) predicate) yes) no
     action = app (prim T.PIOReturn) (var x)
     graph = M.fromList O.compareName
       [(a,unary (use b)), (b,unary (branch (var x) (use a) action)),
        (f,unary (use g)), (g,unary (branch action (use f) (var x))),
        (n 70,unary (T.XELet y action (use g))), (n 80,unary (prim T.PIOReturn))]
     namesEqual expected actual = S.eqList O.eqName (Set.toList (Set.fromList O.compareName expected)) (Set.toList actual)
     targets = M.fromList O.compareName [(f,unary (var x)),(g,binary (var x))]
     escaping = C.escapingWorkers targets Set.empty
     ordinary = B.withFunctions targets state
     branches = branch (var x) (T.XEInt 42) (use f)
 check "kernel anchors reach whole cycle" (namesEqual [a,b] (K.anchoredWorkers graph))
 check "kernel anchors match per-root traversal"
   (all (\name -> Set.member O.compareName name (K.anchoredWorkers graph) == K.anchored graph Set.empty name) (M.keys graph))
 check "saturated nested workers need no closure"
   (namesEqual [] (escaping (app (var f) (app (app (var g) (var x)) (var y)))))
 check "partial nested workers retain closure" (namesEqual [g] (escaping (app (var f) (use g))))
 check "escaping and oversaturated workers retain closures"
   (namesEqual [f,g] (escaping (T.XEAbs y (app (app (var f) (var g)) (var y)))))
 check "branched peer tail transfer" (C.hasBranchTailTransfer ordinary g 1 branches)
 check "self or different ABI keeps inline choice"
   (not (C.hasBranchTailTransfer ordinary f 1 branches || C.hasBranchTailTransfer ordinary g 2 branches))
 check "specialized or straight line calls keep inline choice"
   (not (C.hasBranchTailTransfer (B.withNumericKernels (Set.singleton f) ordinary) g 1 branches ||
         C.hasBranchTailTransfer ordinary g 1 (use f)))
 if selected == Nothing then pure () else fail "unknown callback-sharing case"
 putStrLn "Independent callback sharing audit: 35 checks passed"
