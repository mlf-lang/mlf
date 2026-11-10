{-# LANGUAGE OverloadedStrings #-}
module ReadDemand (controls) where
import Prelude
import Control.Exception (SomeException, try, evaluate, displayException)
import Control.Monad (forM_, unless)
import Data.List (isInfixOf)
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified LegacyGraph as F
import qualified CandidateGraph as C

poison = errorWithoutStackTrace
check name want got = unless (want==got) (errorWithoutStackTrace(name++": "++show(want,got)))
observe text = do
 r<-try(evaluate(foldr(\c z->fromEnum c+z)0 text))::IO(Either SomeException Int)
 pure(case r of Left e->Left(displayException e);Right _->Right text)

-- All unused state fields are poisoned. Only the actual changed read sites in
-- denseContains are called, not the unchanged exported readDense helper.
data Case = Case String (Either String String) Bool B.Int B.Int B.Int Bool Bool [B.Int] [B.Int]
cases =
 [Case "action seq is lazy" (Right "constructed") True (poison "low") (poison "ancestor") (poison "parent") True True [] []
 ,Case "array before identity" (Left "starts array") False (poison "low") (poison "ancestor") 1 True False [] []
 ,Case "identity before low" (Left "ancestor") False (poison "low") (poison "ancestor") 1 False False [] []
 ,Case "low when identity defined" (Left "low") False (poison "low") 0 1 False False [] []
 ,Case "second array before first cell" (Left "ends array") False 0 0 1 False True [poison "first cell",1,2] []
 ,Case "parent index before first cell" (Left "parent") False 0 0 (poison "parent") False False [poison "first cell",1,2] [3,3,3]
 ,Case "parent cell before first interval cell" (Left "parent cell") False 0 0 1 False False [poison "first cell",poison "parent cell",2] [3,3,3]
 ,Case "first interval cell after defined parent" (Left "first cell") False 0 0 1 False False [poison "first cell",1,2] [3,3,3]
 ,Case "parent cell before end cell" (Left "parent cell") False 0 0 1 False False [0,poison "parent cell",2] [poison "end cell",3,3]
 ,Case "failed first comparison skips end cell" (Right "False") False 0 0 1 False False [2,1,poison "unused hole"] [poison "unused end",3,3]
 ,Case "successful comparison reads end" (Left "end cell") False 0 0 1 False False [0,1,2] [poison "end cell",3,3]
 ,Case "untouched holes stay lazy" (Right "True") False 0 0 1 False False [0,1,poison "unused hole"] [3,poison "unused end hole",3]
 ,Case "negative dense offset" (Right "True") False (-10) (-10) (-9) False False [0,1,2] [3,3,3]
 ,Case "Int64 wrapped positive offset" (Right "True") False (2^63-1) (-2^63) (-2^63) False False [0,1,2] [3,3,3]
 ,Case "Int64 wrapped negative offset" (Left "*") False (-2^63) (2^63-1) (2^63-1) False False [0,1,2] [3,3,3]
 ,Case "wide dense offset" (Right "True") False (2^60) (2^60) (2^60+1) False False [0,1,2] [3,3,3]
 ]
run candidate (Case _ _ onlySeq low ancestor parent badStarts badEnds startCells endCells) = P.runST $ do
 starts0<-P.newSTArray 3 0;ends0<-P.newSTArray 3 3
 forM_ (zip [0..] startCells) $ \(n,v)->P.writeSTArray starts0 n v
 forM_ (zip [0..] endCells) $ \(n,v)->P.writeSTArray ends0 n v
 let starts=if badStarts then poison "starts array" else starts0
     ends=if badEnds then poison "ends array" else ends0
     action=if candidate
       then C.denseContains (C.DenseValidation (poison "graph") low (poison "high") (poison "table") (poison "descendants") (poison "colours") (poison "kinds") starts ends (poison "visited")) ancestor parent
       else F.denseContains (F.DenseValidation (poison "graph") low (poison "high") (poison "table") (poison "descendants") (poison "colours") (poison "kinds") starts ends (poison "visited")) ancestor parent
 if onlySeq then pure(action `seq` "constructed") else fmap show action

-- The colour-2 read is required but must not force a cached Kind value when the
-- caller ignores it. A poisoned kinds array must still reject the actual read.
kindRead candidate badArray forced = P.runST $ do
 colours<-P.newSTArray 1 2
 kinds0<-P.newSTArray 1 (poison "cached kind")
 let kinds=if badArray then poison "kind array" else kinds0
     action=if candidate
       then C.denseKind (C.DenseValidation (poison "graph") 0 0 (poison "table") (poison "descendants") colours kinds (poison "starts") (poison "ends") (poison "visited")) 0 (poison "unused Node")
       else F.denseKind (F.DenseValidation (poison "graph") 0 0 (poison "table") (poison "descendants") colours kinds (poison "starts") (poison "ends") (poison "visited")) 0 (poison "unused Node")
 r<-action
 pure(case r of T.Left e->B.unpack e;T.Right k->if forced then k `seq` "kind" else "ignored")
sharedRead candidate empty = P.runST $ do
 starts<-P.newSTArray (if empty then 0 else 2) 0
 ends<-P.newSTArray 2 3
 if empty then pure () else P.writeSTArray starts 1 1
 let action=if candidate
       then C.denseContains (C.DenseValidation (poison "graph") 0 1 (poison "table") (poison "descendants") (poison "colours") (poison "kinds") starts ends (poison "visited")) 0 1
       else F.denseContains (F.DenseValidation (poison "graph") 0 1 (poison "table") (poison "descendants") (poison "colours") (poison "kinds") starts ends (poison "visited")) 0 1
 first<-action
 if empty then pure(show first) else do
  P.writeSTArray starts 1 5
  second<-action
  pure(show(first,second))

controls = do
 forM_ cases $ \c@(Case name want _ _ _ _ _ _ _ _)->do
  a<-observe(run False c);b<-observe(run True c)
  case (want,a) of
   (Left "*",Left e)->check(name++" actual bounds exception")True("array index out of bounds" `isInfixOf` e)
   _->check (name++" fixed oracle") want a
  check (name++" candidate") a b
 forM_ [("lazy cached kind",False,False,Right "ignored"),("forced cached kind",False,True,Left "cached kind"),("cached array still required",True,False,Left "kind array")] $ \(name,bad,forced,want)->do
  a<-observe(kindRead False bad forced);b<-observe(kindRead True bad forced)
  check (name++" fixed oracle") want a;check(name++" candidate")a b
 a<-observe(sharedRead False False);b<-observe(sharedRead True False)
 check "shared action re-reads after mutation" (Right "(True,False)") a
 check "shared action candidate" a b
 c<-observe(sharedRead False True);d<-observe(sharedRead True True)
 check "short array exact exception" c d
 case c of Left e->check "short array is bounds rejection" True ("array index out of bounds" `isInfixOf` e);_->errorWithoutStackTrace "short array accepted"
 putStrLn "PASS 21 read action, offset, array/cell demand, sharing and cached-kind controls"
