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

main = do
 env <- case D.validateDeclarations [] of T.Right e -> pure e; T.Left e -> fail (B.unpack e)
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
