{-# LANGUAGE OverloadedStrings #-}
module Main where
import Control.Monad (unless, forM_)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Data as D
import qualified Bootstrap.Runtime as R
import qualified MLF.Host.Base as B
import qualified Bootstrap.LLVM.Optimize as O
import qualified Bootstrap.LLVM.Analysis as A
import qualified Bootstrap.Set as S
import qualified Bootstrap.Map as M
import qualified Bootstrap.X.Syntax as X

n :: Integer -> T.XName
n i = T.XName i "same-hint"
v :: Integer -> T.XErased
v = T.XEVar . n
app :: T.XErased -> [T.XErased] -> T.XErased
app = foldl T.XEApp
f :: [T.XErased] -> T.XErased
f = app (v 0)
pair :: T.XErased -> T.XErased -> T.XErased
pair a b = app (T.XEConstructor "(,)") [a,b]
rhs :: T.XErased
rhs = T.XEAbs (n 1) (app (T.XEPrimitive T.PConcatString) [v 1,v 90])
rhs2 :: T.XErased
rhs2 = T.XEAbs (n 1) (T.XEAbs (n 2) (pair (v 1) (v 2)))
check :: String -> Bool -> T.XErased -> T.XErased -> IO ()
check label wanted value body = do
 let result = fst (O.runFresh (O.specializeSharedValue (n 0) (O.indexUses value) (O.indexUses body)) 1000)
 case result of
  T.Nothing -> unless (not wanted) (fail (label ++ ": unexpectedly refused"))
  T.Just indexed -> do
   unless wanted (fail (label ++ ": unexpectedly admitted"))
   let output = O.useTerm indexed
       old = T.XELet (n 0) value body
   unless (A.sameNames (S.toList (O.free old)) (S.toList (O.free output)))
     (fail (label ++ ": changed free identities"))
   let expectedCounts = O.useCounts (O.indexUses output)
   unless (M.size (O.useCounts indexed) == M.size expectedCounts && all (\(key,count) -> M.findWithDefault O.compareName 0 key expectedCounts == count) (M.toList (O.useCounts indexed)))
     (fail (label ++ ": stale cached use counts"))
   case output of
    T.XELet actual _ _ -> unless (O.eqName actual (n 0)) (fail (label ++ ": changed original binder"))
    _ -> fail (label ++ ": lost lazy let boundary")
 putStrLn ("PASS " ++ label)
primitive :: T.Primitive -> [T.XErased] -> T.XErased
primitive p = app (T.XEPrimitive p)
ret :: T.XErased -> T.XErased
ret a = primitive T.PIOReturn [a]
bind :: T.XErased -> Integer -> T.XErased -> T.XErased
bind action binder body = primitive T.PIOBind [action,T.XEAbs (n binder) body]
rawSemantics :: String -> T.XErased -> T.XErased -> T.XErased -> Maybe String -> IO ()
rawSemantics label initial value body expectedError = do
 ds <- case D.validateDeclarations [] of
  T.Left message -> fail (B.unpack message)
  T.Right env -> pure env
 let original = T.XELet (n 10) initial (T.XELet (n 0) value body)
 contracted <- case fst (O.runFresh (O.specializeSharedValue (n 0) (O.indexUses value) (O.indexUses body)) 1000) of
  T.Nothing -> fail (label ++ ": transformation was not exercised")
  T.Just indexed -> pure (T.XELet (n 10) initial (O.useTerm indexed))
 forM_ [original,contracted,O.optimize contracted] $ \term -> do
  result <- R.runAction [] ds (R.evaluate ds (R.REnv M.empty) term)
  case (result,expectedError) of
   (T.Left actual,Just expected) -> unless (B.unpack actual == expected) (fail (label ++ ": wrong failure order"))
   (T.Right answer,Nothing) -> case R.integer answer of
    T.Right 0 -> pure ()
    _ -> fail (label ++ ": wrong integer observation")
   _ -> fail (label ++ ": changed action outcome")
 putStrLn ("PASS " ++ label)

main :: IO ()
main = do
 let two args = pair (f args) (f args)
 forM_
  [ ("identical-outer-vector",True,rhs,two [v 10])
  , ("different-identity-same-hint",False,rhs,pair (f [v 10]) (f [v 11]))
  , ("inner-lambda-variable",False,rhs,T.XEAbs (n 10) (two [v 10]))
  , ("separate-inner-lambdas",False,rhs,pair (T.XEAbs (n 10) (f [v 10])) (T.XEAbs (n 11) (f [v 11])))
  , ("inner-let-variable",False,rhs,T.XELet (n 10) (v 11) (two [v 10]))
  , ("inner-recursive-variable",False,rhs,T.XELetRec [(n 10,v 11)] (two [v 10]))
  , ("inner-case-variable",False,rhs,T.XECase (v 20) [T.XErasedAlternative (T.XDefaultPattern (T.Just (n 10))) (two [v 10])])
  , ("outer-variable-under-lambdas",True,rhs,pair (T.XEAbs (n 11) (f [v 10])) (T.XEAbs (n 12) (f [v 10])))
  , ("single-use-forwarding",True,rhs,f [v 10])
  , ("escaping-bare-function",False,rhs,pair (f [v 10]) (v 0))
  , ("seq-observes-function",False,rhs,app (T.XEPrimitive T.PSeq) [v 0,two [v 10]])
  , ("partial-application",False,rhs2,two [v 10])
  , ("oversaturated-application",False,rhs,two [v 10,v 11])
  , ("literal-argument-conservative",False,rhs,two [T.XEInt 1])
  , ("computed-argument-conservative",False,rhs,two [app (v 10) [v 11]])
  , ("non-lambda-rhs",False,v 99,two [v 10])
  , ("exact-two-parameter-vector",True,rhs2,two [v 10,v 11])
  , ("reversed-parameter-vector",False,rhs2,pair (f [v 10,v 11]) (f [v 11,v 10]))
  , ("self-argument-refused",False,rhs,two [v 0])
  ] $ \(label,wanted,value,body) -> check label wanted value body
 let expected = T.XELet (n 0) (app (T.XEPrimitive T.PConcatString) [v 10,v 90]) (pair (v 0) (v 0))
 case fst (O.runFresh (O.specializeSharedValue (n 0) (O.indexUses rhs) (O.indexUses (two [v 10]))) 1000) of
  T.Just actual -> unless (X.equalErased (O.useTerm actual) expected) (fail "exact lazy contraction changed")
  T.Nothing -> fail "exact lazy contraction missing"
 putStrLn "PASS exact-lazy-contraction"
 let plusOne = T.XEAbs (n 1) (primitive T.PAddInt [v 1,T.XEInt 1])
     repeated = primitive T.PAddInt [f [v 10],f [v 10]]
 rawSemantics "raw-unused-bottom-laziness"
   (primitive T.PPanic [T.XEString "unused argument"]) plusOne
   (primitive T.PIfThenElse [T.XEBool False,ret repeated,ret (T.XEInt 0)]) Nothing
 rawSemantics "raw-earlier-failure-order"
   (primitive T.PPanic [T.XEString "late argument"]) plusOne
   (bind (primitive T.PPanic [T.XEString "first failure"]) 20 (ret repeated)) (Just "first failure")
 let allocate = T.XEAbs (n 1) (primitive T.PNewIntArray [T.XEInt 1,v 1])
     twoArrays = bind (f [v 10]) 20
       (bind (f [v 10]) 21
         (bind (primitive T.PWriteIntArray [v 20,T.XEInt 0,T.XEInt 42]) 22
           (primitive T.PReadIntArray [v 21,T.XEInt 0])))
 rawSemantics "raw-fresh-arrays-each-execution" (T.XEInt 0) allocate twoArrays Nothing
 putStrLn "Independent common-call audit: 23 checks passed"
