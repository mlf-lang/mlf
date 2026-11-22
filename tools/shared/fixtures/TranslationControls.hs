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
 let select condition = C.indexUses (prim T.PIfThenElse [condition,
       T.XEApp (T.XEConstructor "A") (T.XEInt 9), T.XEApp (T.XEConstructor "B") poison])
     wildcard = (T.XDefaultPattern T.Nothing,C.indexUses (T.XEInt 17))
     matching = (T.XConstructorPattern "A" [T.Just (n 30)],C.indexUses (v 30))
 need "case distribution keeps a wildcard-only match lazy"
   (case C.selectConditionalConstructors (select poison) [wildcard] of T.Nothing -> True; _ -> False)
 forM_ [(T.XEBool True,Right 9),(T.XEBool False,Right 17),(poison,Left "field demanded")] $ \(condition,wanted) ->
   case C.selectConditionalConstructors (select condition) [matching,wildcard] of
    T.Nothing -> fail "exhaustive conditional constructor match was not reduced"
    T.Just chosen -> need "conditional constructor match preserves demand and selected fields" (result (C.useTerm chosen)==wanted)
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

checkComposition env = do
 let app = T.XEApp
     lam i = T.XEAbs (n i)
     compose = lam 20 (lam 21 (lam 22 (app (v 20) (app (v 21) (v 22)))))
     reversed = lam 20 (lam 21 (lam 22 (app (v 21) (app (v 20) (v 22)))))
     identity = lam 24 (v 24)
     step k = lam 25 (prim T.PAddInt [v 25,T.XEInt k])
     times k = lam 26 (prim T.PMulInt [v 26,T.XEInt k])
     scope definition amount = T.XELet (n 1) definition . T.XELet (n 2) (step amount) . T.XELet (n 3) identity
     pair f g = app (app (v 1) f) g
     early term = lastBody (fst (C.runFresh (C.checkedIdentities M.empty term) 1000))
     outcome term = case R.integer (R.evaluate env (R.REnv M.empty) term) of
       T.Left message -> Left (B.unpack message)
       T.Right value -> Right value
     check label wanted term = forM_ [term,C.optimizeChecked term] $ \version ->
       need label (outcome version == wanted)
     poison message = prim T.PPanic [T.XEString message]
 forM_ [1,3,32] $ \depth -> forM_ [minBound,-7,0,1,maxBound] $ \amount -> do
   let call arg = scope compose amount (app (iterate (pair (v 2)) (v 3) !! depth) arg)
       total = fromIntegral depth * amount
       expected = if total==0 then v 9 else prim T.PAddInt [v 9,T.XEInt total]
   need "fully applied composition folds before repeated substitution" (X.equalErased (early (call (v 9))) expected)
   forM_ [minBound,-1,0,7,maxBound] $ \x ->
     check "wrapped composed callbacks" (Right (x+total)) (call (T.XEInt x))
 let invoke definition = scope definition 3 (app (pair (v 2) (times 2)) (T.XEInt 4))
 check "noncommuting callbacks keep their order" (Right 11) (invoke compose)
 check "a reversed definition keeps its own order" (Right 14) (invoke reversed)
 check "a shadowing definition keeps its meaning" (Right 14)
   (scope compose 3 (T.XELet (n 1) reversed (app (pair (v 2) (times 2)) (T.XEInt 4))))
 let failure = poison "input"
     use f g = scope compose 1 (app (pair f g) failure)
 check "a lazy outer callback can discard both inner expressions" (Right 37)
   (use (lam 27 (T.XEInt 37)) (poison "inner"))
 check "the outer function is demanded first" (Left "outer") (use (poison "outer") (poison "inner"))
 check "the inner function can be the first error" (Left "inner") (use (v 2) (poison "inner"))
 check "canceling translations still demand the input" (Left "input") (use (v 2) (step (-1)))
 check "an unsaturated composition stays a function" (Right 41)
   (scope compose 1 (prim T.PSeq [pair (poison "outer") (poison "inner"),T.XEInt 41]))


checkConditionalCalls env = do
 let app = T.XEApp
     lit = T.XEInt
     call f = app (v f)
     choose c yes no = prim T.PIfThenElse [c,yes,no]
     local body = T.XELet (n 1) (T.XEAbs (n 3) body)
     selected right = choose (v 4) (call 1 (v 5)) (call right (prim T.PAddInt [v 5,lit 1]))
     bound value = T.XELet (n 6) value (v 6)
     shape checked term = C.useTerm (fst (C.runFresh (C.passOwnedFor checked term) 100))
     hasDecision term = case term of
       T.XEPrimitive T.PSeq -> True
       _ -> any hasDecision (C.subterms term)
     rhs = prim T.PRemInt [prim T.PAddInt [v 5,v 3],lit 97]
 forM_ [local rhs (selected 1),local rhs (bound (selected 1))] $ \term -> do
   need "checked adjacent callback shares one condition-ordered call" (hasDecision (shape True term))
   need "unchecked callback retains its original demand path" (not (hasDecision (shape False term)))
 forM_ [local rhs (selected 2),selected 1,T.XELet (n 1) (v 2) (selected 1)] $ \term ->
   need "other callee identities and nonlocal calls stay ordinary" (not (hasDecision (shape True term)))
 let poison text = prim T.PPanic [T.XEString text]
     apply body c yes no = local body (choose c (call 1 yes) (call 1 no))
     observe term = case R.integer (R.evaluate env (R.REnv M.empty) term) of
       T.Right value -> Right value
       T.Left message -> Left (B.unpack message)
     check expected term = forM_ [term,C.optimizeChecked term] $ \version ->
       need "conditional callback preserves first demand and selection" (observe version == expected)
 check (Left "condition") (apply (poison "callee") (poison "condition") (poison "left") (poison "right"))
 check (Right 41) (apply (lit 41) (T.XEBool True) (poison "ignored") (poison "unselected"))
 check (Right 42) (apply (v 3) (T.XEBool False) (poison "unselected") (lit 42))
 check (Left "selected") (apply (v 3) (T.XEBool True) (poison "selected") (poison "unselected"))
 check (Left "capture") (apply (prim T.PAddInt [poison "capture",v 3]) (T.XEBool False) (lit 0) (poison "operand"))

main = do
 env <- case D.validateDeclarations [] of T.Right e -> pure e; T.Left e -> fail (B.unpack e)
 checkIntSums env
 checkConditionalCalls env
 checkUnaryConstructors
 checkComposition env
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
