module StrictFieldAnalysis (strictFieldAnalysisTests) where
import Control.Monad (unless)
import qualified Data.Map.Strict as M
import qualified MLF.LLVM.Analysis as A
import qualified MLF.Primitive as P
import qualified MLF.X.Syntax as X
import qualified MLF.LLVM.StrictFields as F
n :: Int -> X.Name
n i = X.Name i "probe"
v :: Int -> X.Erased
v = X.EVar . n
apps :: X.Erased -> [X.Erased] -> X.Erased
apps = foldl X.EApp
con :: String -> [X.Erased] -> X.Erased
con c = apps (X.EConstructor c)
seqE :: X.Erased -> X.Erased -> X.Erased
seqE a b = apps (X.EPrimitive P.Seq) [a,b]
absE :: Int -> X.Erased -> X.Erased
absE = X.EAbs . n
letE :: Int -> X.Erased -> X.Erased -> X.Erased
letE = X.ELet . n
recE :: [(Int,X.Erased)] -> X.Erased -> X.Erased
recE bs = X.ELetRec [(n i,e) | (i,e) <- bs]
cs :: M.Map String Int
cs = M.fromList [("C",3),("One",1),("Wrap",1),("Empty",0)]
poison :: X.Erased
poison = apps (X.EPrimitive P.Panic) [X.EString "unused"]
strictFunction :: X.Erased
strictFunction = absE 1 (absE 2 (absE 3 (seqE (v 1) (seqE (v 3) (con "C" [v 1,v 2,v 3])))))
worker :: X.Erased
worker = letE 0 strictFunction (apps (v 0) [X.EInt 1,poison,X.EInt 3])
cases :: [(String,String,X.Erased,Maybe [Bool])]
cases =
 [ ("strict worker, lazy value", "C", worker, Just [True,False,True])
 , ("partial escape invalidates all", "C", letE 4 (X.EConstructor "C") worker, Just [False,False,False])
 , ("literal and constructor atoms", "C", con "C" [X.EInt 1,con "One" [poison],X.EAbs (n 9) poison], Just [True,True,True])
 , ("meet across sites", "C", letE 8 worker (con "C" [poison,X.EInt 2,X.EInt 3]), Just [False,False,True])
 , ("anonymous callback drops capture facts", "One", letE 0 (absE 1 (seqE (v 1) (absE 2 (con "One" [v 1])))) (apps (v 0) [X.EInt 1]), Just [False])
 , ("compound suspension drops capture facts", "One", letE 0 (absE 1 (seqE (v 1) (con "Wrap" [seqE (X.EInt 1) (con "One" [v 1])])) ) (apps (v 0) [X.EInt 1]), Just [False])
 , ("strict let canonical result", "One", letE 1 (apps (X.EPrimitive P.AddInt) [X.EInt 1,X.EInt 2]) (seqE (v 1) (con "One" [v 1])), Just [True])
 , ("recursive hole remains unknown", "One", recE [(1,X.EInt 1)] (seqE (v 1) (con "One" [v 1])), Just [False])
 , ("unused constructor has no vacuous fact", "C", X.EInt 0, Nothing)
 , ("pattern fields remain unknown", "One", X.ECase (con "C" [X.EInt 1,X.EInt 2,X.EInt 3]) [X.ErasedAlternative (X.ConstructorPattern "C" [Just (n 1),Nothing,Nothing]) (con "One" [v 1])], Just [False])
 , ("lazy default binder remains unknown", "One", X.ECase (X.EInt 1) [X.ErasedAlternative (X.DefaultPattern (Just (n 1))) (con "One" [v 1])], Just [False])
 , ("checked default binder is canonical", "One", X.ECase (X.EConstructor "Empty") [X.ErasedAlternative (X.ConstructorPattern "Empty" []) (con "One" [X.EInt 1]),X.ErasedAlternative (X.DefaultPattern (Just (n 1))) (con "One" [v 1])], Just [True])
 ]
strictFieldAnalysisTests :: [(String,IO ())]
strictFieldAnalysisTests =
  [("strict constructor fields: " ++ label, do
      let actual = M.lookup constructor (F.infer cs (A.analyze expression) expression)
      unless (actual == expected) (fail (show actual ++ " expected " ++ show expected)))
   | (label,constructor,expression,expected) <- cases]
