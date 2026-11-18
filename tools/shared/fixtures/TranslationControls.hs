{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Monad (forM_, unless)
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.Runtime as R
import qualified Bootstrap.Data as D
import qualified Bootstrap.LLVM.Optimize as C

need label ok = unless ok (fail label)
n i = T.XName i "hint"
v = T.XEVar . n
prim op = foldl T.XEApp (T.XEPrimitive op)
chain count amount op input = foldr definition (T.XEApp (v count) input) [1..count]
 where definition i body = T.XELet (n i) (T.XEAbs (n (1000+i))
         (let value = prim op [v (1000+i),T.XEInt amount]
          in if i==1 then value else T.XEApp (v (i-1)) value)) body
lastBody (T.XELet _ _ b) = lastBody b
lastBody b = b

checkIntSums env = do
 let add a b = prim T.PAddInt [a,b]
     mul a b = prim T.PMulInt [a,b]
     lit = T.XEInt
     x = v 1
     eval t = R.integer (R.evaluate env (R.REnv M.empty) t)
     run input t = eval (T.XELet (n 1) (lit input) t)
     poison msg = prim T.PPanic [T.XEString msg]
 forM_ [(1,1), (-1,1), (minBound,minBound), (maxBound,2), (7,-11)] $ \(a,b) ->
  forM_ [(0,0), (maxBound,1), (minBound,-1), (-19,8)] $ \(c,d) -> do
   let left = add (mul x (lit a)) (lit c)
       right = add (lit d) (mul x (lit b))
   reduced <- case C.combineIntSummands left right of
    T.Just result -> pure result
    T.Nothing -> fail "summands with the same binding were missed"
   forM_ [minBound,maxBound,-1,0,7] $ \input -> do
    let expected = (a*input+c)+(b*input+d)
    forM_ [add left right,reduced] $ \term -> case run input term of
     T.Right value -> need "sum wraps like independent machine Int arithmetic" (value==expected)
     T.Left err -> fail (B.unpack err)
 let reject a b = case C.combineIntSummands a b of T.Nothing -> True; _ -> False
 need "distinct binding identities with identical names stay distinct" (reject x (v 2))
 need "a division or an effectful operand is never moved"
   (reject (prim T.PQuotInt [x,lit 2]) x && reject x (poison "right"))
 let canceled = T.XELet (n 1) (poison "canceled input") (add x (mul x (lit (-1))))
     leftFirst = T.XELet (n 1) (poison "left") (T.XELet (n 2) (poison "right") (add x (v 2)))
     letBody = T.XELet (n 8) (poison "bound value") (v 8)
 forM_ [(canceled,"canceled input"),(leftFirst,"left"),(letBody,"bound value")] $ \(term,msg) ->
  forM_ [term,C.optimizeChecked term] $ \version -> case eval version of
   T.Left err -> need "first demanded error is preserved" (err==msg)
   T.Right _ -> fail "demanded error was lost"
 let lazy = prim T.PIfThenElse [T.XEBool False,canceled,lit 42]
 need "unselected canceled sum stays lazy" (case eval (C.optimizeChecked lazy) of T.Right 42 -> True; _ -> False)
 need "a let returning its binder disappears" (X.equalErased (C.optimizeChecked letBody) (poison "bound value"))
 putStrLn "PASS 100 wrapped sum cases, binder identity, let result and demand controls"

checkUnaryConstructors = do
 let builder tag parameter = T.XEAbs parameter (T.XEApp (T.XEConstructor tag) (T.XEVar parameter))
     selector tag parameter = T.XEAbs parameter (T.XECase (T.XEVar parameter)
       [T.XErasedAlternative (T.XConstructorPattern tag [T.Just (n 30)]) (v 30)])
     wrap f g body = T.XELet (n 1) f (T.XELet (n 2) g body)
     call x = T.XEApp (v 2) (T.XEApp (v 1) x)
     pair = wrap (builder "A" (n 10)) (selector "A" (n 20))
     poison = prim T.PPanic [T.XEString "field demanded"]
     declared = [T.DataDecl "Choice" ["a"] [T.ConstructorDecl c [T.Parameter "a"] | c <- ["A","B"]]]
 env <- case D.validateDeclarations declared of T.Right e -> pure e; T.Left e -> fail (B.unpack e)
 let result term = case R.integer (R.evaluate env (R.REnv M.empty) term) of
       T.Left message -> Left (B.unpack message)
       T.Right value -> Right value
     agree term = result term == result (C.optimizeChecked term)
     early term = fst (C.runFresh (C.checkedIdentities M.empty term) 1000)
     unmatched = wrap (builder "A" (n 10)) (selector "B" (n 20)) (call (T.XEInt 9))
     capture = T.XEAbs (n 10) (T.XEApp (T.XEConstructor "A") (v 11))
     wrongSubject = T.XEAbs (n 20) (T.XECase (v 21)
       [T.XErasedAlternative (T.XConstructorPattern "A" [T.Just (n 30)]) (v 30)])
     wrongField = T.XEAbs (n 20) (T.XECase (v 20)
       [T.XErasedAlternative (T.XConstructorPattern "A" [T.Just (n 30)]) (v 20)])
     wrongArity = T.XEAbs (n 20) (T.XECase (v 20)
       [T.XErasedAlternative (T.XConstructorPattern "A" [T.Just (n 30),T.Nothing]) (v 30)])
     defaultCase = T.XEAbs (n 20) (T.XECase (v 20)
       [T.XErasedAlternative (T.XDefaultPattern (T.Just (n 30))) (v 30)])
 forM_ [minBound,-1,0,9,maxBound] $ \value -> do
   let term = pair (call (T.XEInt value))
   need "matching constructor and selector cancel early" (X.equalErased (lastBody (early term)) (T.XEInt value))
   need "constructor-field result matches independent evaluator" (agree term && result term==Right value)
 forM_ [capture,wrongSubject,wrongField,wrongArity,defaultCase] $ \term ->
   need "capture, altered result, default and wrong arity stay ordinary" (case C.unaryConstructorUse term of T.Nothing -> True; _ -> False)
 need "mismatched constructor still fails" (agree unmatched && case result unmatched of Left _ -> True; _ -> False)
 let demanded = pair (call poison)
     unused = pair (prim T.PIfThenElse [T.XEBool False,call poison,T.XEInt 42])
     shadowed = pair (T.XELet (n 2) (T.XEAbs (n 40) (T.XEInt 8)) (call poison))
 need "demanded field keeps its error" (agree demanded && result demanded==Left "field demanded")
 need "unselected field stays lazy" (agree unused && result unused==Right 42)
 need "shadowed selector with the same numeric id is handled after freshening" (agree shadowed && result shadowed==Right 8)
 let identity term = T.XEApp (T.XEAbs (n 40) (v 40)) term
     aliased parameter alias body = identity (T.XEAbs (n parameter)
       (T.XELet (n alias) (identity (v parameter)) body))
     wrappedBuilder tag = aliased 10 11 (T.XEApp (T.XEConstructor tag) (identity (v 11)))
     wrappedSelector tag field = aliased 20 21 (T.XECase (identity (v 21))
       [T.XErasedAlternative (T.XConstructorPattern tag [T.Just (n 21)]) (identity (v field))])
     wrappedPair = wrap (wrappedBuilder "A") (wrappedSelector "A" 21)
     sumOfCalls = prim T.PAddInt [call (v 50),call (prim T.PAddInt [v 50,T.XEInt 7])]
     checked = C.foldScopedFields M.empty (wrappedPair sumOfCalls)
     close input = T.XELet (n 50) (T.XEInt input)
 need "identity-wrapped aliases expose a common affine argument"
   (not (X.equalErased (lastBody checked) sumOfCalls))
 forM_ [minBound,-3,0,9,maxBound] $ \input ->
   forM_ [wrappedPair sumOfCalls,checked] $ \term ->
     need "constructor projection through aliases preserves wrapping" (result (close input term)==Right (input+input+7))
 need "a field pattern shadows the argument alias with the same numeric id"
   (case C.scopedUnaryUse (wrappedSelector "A" 20) of T.Nothing -> True; _ -> False)
 let different = wrap (wrappedBuilder "A") (wrappedSelector "B" 21) sumOfCalls
 need "a different constructor still follows the case failure path"
   (X.equalErased (lastBody (C.foldScopedFields M.empty different)) sumOfCalls &&
    case result (close 9 different) of Left _ -> True; _ -> False)
 putStrLn "PASS unary constructor and selector, binding scopes, mismatches and field demand"

main = do
 env <- case D.validateDeclarations [] of T.Right e -> pure e; T.Left e -> fail (B.unpack e)
 checkIntSums env
 checkUnaryConstructors
 let eval = R.evaluate env (R.REnv M.empty)
     integer t = case R.integer (eval t) of T.Right x -> pure x; T.Left e -> fail (B.unpack e)
 forM_ [1,2,17] $ \count -> forM_ [minBound,maxBound,-3,0,1] $ \amount ->
  forM_ [minBound,maxBound,-1,0,7] $ \input -> forM_ [T.PAddInt,T.PSubInt] $ \op -> do
   let term = chain count amount op (T.XEInt input)
       simplified = C.simplifyTranslations M.empty term
       action = case op of T.PAddInt -> (+); _ -> (-)
       expected = foldl action input (replicate (fromIntegral count) amount)
   a <- integer term; b <- integer simplified; c <- integer (C.optimizeChecked term)
   need "translation preserves wrapped arithmetic" (a==expected && b==expected && c==expected)
   need "real dependent call is removed" (not (X.equalErased (lastBody term) (lastBody simplified)))
 let bad = [T.XEAbs (n 2) (prim T.PQuotInt [v 2,T.XEInt 2]),
            T.XEAbs (n 2) (prim T.PAddInt [v 3,T.XEInt 1]),
            T.XEAbs (n 2) (prim T.PNewIntArray [T.XEInt 1,v 2]),
            T.XEAbs (n 2) (T.XEInt 0)]
 forM_ bad $ \term -> need "unsupported, captured, effectful and constant bodies are not translations"
  (case C.translationSummary M.empty term of T.Nothing -> True; _ -> False)
 let summary = M.singleton (n 1) 3
     call = T.XEApp (v 1) (T.XEInt 7)
     shadowed = [T.XEAbs (n 1) call,T.XELet (n 1) (v 9) call,
                 T.XELetRec [(n 1,v 9)] call,
                 T.XECase (v 9) [T.XErasedAlternative (T.XDefaultPattern (T.Just (n 1))) call]]
 forM_ shadowed $ \term -> need "all binding forms mask summaries" (X.equalErased term (C.simplifyTranslations summary term))
 let poison = chain 3 0 T.PAddInt (prim T.PPanic [T.XEString "translation input"])
 forM_ [poison,C.optimizeChecked poison] $ \term -> need "zero translation preserves demanded failure"
  (case R.integer (eval term) of T.Left e -> e=="translation input"; _ -> False)
 value <- integer (C.optimizeChecked (prim T.PIfThenElse [T.XEBool False,poison,T.XEInt 42]))
 need "unselected branch stays lazy" (value==42)
 let dropUnused = fst . C.liveDeclarationSpine
     hidden = T.XName 1 "same identity, another hint"
     keepOuter = T.XELet (n 1) (T.XEInt 7) (T.XELet hidden (v 1) (T.XEVar hidden))
     keepRec = T.XELet (n 1) (T.XEInt 7) (T.XELetRec [(n 2,v 1)] (v 2))
     harmless = T.XELet (n 1) poison (T.XEInt 5)
 need "unused initializer drops before renaming" (X.equalErased (dropUnused harmless) (T.XEInt 5))
 need "nonrecursive RHS sees the outer identity" (X.equalErased (dropUnused keepOuter) keepOuter)
 need "recursive RHS keeps its outer dependency" (X.equalErased (dropUnused keepRec) keepRec)
 need "an inner binder masks an identically numbered outer name"
   (X.equalErased (dropUnused (T.XELet (n 1) poison (T.XELet hidden (T.XEInt 8) (T.XEVar hidden))))
                  (T.XELet hidden (T.XEInt 8) (T.XEVar hidden)))
 putStrLn "PASS 150 translation cases at three stages, independent evaluation, scopes and fallbacks"
