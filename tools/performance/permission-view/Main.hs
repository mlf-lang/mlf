{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Exception (SomeException, try, evaluate, displayException)
import Control.Monad (forM_, unless)
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified LegacyGraph as F
import qualified CandidateGraph as C

type Entry = (B.Int,T.Node,T.Maybe B.Int)
check label expected actual = unless (expected == actual) $
  errorWithoutStackTrace (label ++ ": expected " ++ show expected ++ ", got " ++ show actual)
permission T.Green = 'G'
permission T.Orange = 'O'
permission T.Red = 'R'
permission T.Inert = 'I'

tables low high entries = do
  ns <- P.newSTArray (high-low+1) T.Nothing
  old <- P.newSTArray (high-low+1) T.Nothing
  new <- P.newSTArray (high-low+1) T.Nothing
  forM_ entries $ \(n,v,b) -> do
    F.writeDense low ns n (T.Just v)
    F.writeDense low old n (F.binder v)
    F.writeDense low new n b
  pure (ns,old,new,[(n,v)|(n,v,_)<-entries])

oldAnswers low high entries queries = P.runST $ do
  (ns,old,new,es) <- tables low high entries
  before <- F.newDensePermissions low high ns old es
  after <- F.newDensePermissions low high ns new es
  mapM (\(raised,n) -> fmap permission (F.densePermission (if raised then after else before) n)) queries
newAnswers low high entries queries = P.runST $ do
  (ns,old,new,es) <- tables low high entries
  before <- C.newDensePermissions low high ns old es
  after <- C.raisedDensePermissions before low high ns old new es
  mapM (\(raised,n) -> fmap permission (C.densePermission (if raised then after else before) n)) queries

admission low high entries = P.runST $ do
  (_,old,new,es) <- tables low high entries
  C.sameDensePermissionBindings low old new es

-- Test sharing by mutating a private memo cell after construction. Production
-- input arrays remain immutable; this mutation only observes cache identity.
shared low high entries = P.runST $ do
  (ns,old,new,es) <- tables low high entries
  before <- C.newDensePermissions low high ns old es
  after <- C.raisedDensePermissions before low high ns old new es
  case before of
    C.DensePermissions _ _ _ _ _ _ cache -> C.writeDense low cache low (T.Just T.Red)
  fmap permission (C.densePermission after low)

generated seed low =
  [(low+i,T.Node (tag i) (parent i) (flag i),after i) | i<-[0..7]]
  where
    tag i = case (seed+i) `mod` 4 of
      0 -> T.GBot
      1 -> T.GCon "C" []
      2 -> T.GGen (low+i)
      _ -> T.GBotK T.Star
    flag i = if (seed `div` 4+i) `mod` 3 == 0 then T.Rigid else T.Flexible
    parent 0 = T.Nothing
    parent i = T.Just (low + ((seed+i) `mod` i))
    after i | seed `mod` 3 == 0 = parent i
            | i==0 = T.Nothing
            | otherwise = case seed `mod` 3 of
                1 -> T.Nothing
                _ -> T.Just (low + ((seed `div` 3+i) `mod` i))

node b f = T.Node (T.GCon "C" []) b f
root = node T.Nothing T.Flexible
same = [(0,root,T.Nothing),(1,node (T.Just 0) T.Flexible,T.Just 0)]
changed = [(0,root,T.Nothing),(1,node (T.Just 0) T.Flexible,T.Nothing)]
rigidChanged = [(0,root,T.Nothing),(1,node (T.Just 0) T.Rigid,T.Nothing)]

observe text = do
  r <- try (evaluate (foldr (\c z -> fromEnum c+z) 0 text)) :: IO (Either SomeException Int)
  pure $ case r of Left e -> Left (displayException e); Right _ -> Right text
poison = errorWithoutStackTrace
demandCases =
  [("rigid binder contents unused",Right "II",
      [(0,root,T.Nothing),(1,node (T.Just (poison "old rigid")) T.Rigid,T.Just (poison "new rigid"))],[(False,0),(True,0)])
  ,("rigid binder constructor unused",Right "II",
      [(0,root,T.Nothing),(1,node (poison "old rigid maybe") T.Rigid,poison "new rigid maybe")],[(False,0),(True,0)])
  ,("tag unused when no query",Right "",
      [(0,T.Node (poison "unused tag") T.Nothing T.Flexible,T.Nothing)],[])
  ,("old parents load first",Left "old first",
      [(0,root,T.Nothing),(1,node (T.Just (poison "old first")) T.Flexible,T.Just (poison "new second"))],[])
  ,("raised parents retain order",Left "raised first",
      [(0,root,T.Nothing),(1,node (T.Just 0) T.Flexible,T.Just (poison "raised first")),
       (2,node (T.Just 0) T.Flexible,T.Just (poison "raised second"))],[])
  ,("changed prefix then raised error",Left "after changed edge",
      [(0,root,T.Nothing),(1,node (T.Just 0) T.Flexible,T.Nothing),
       (2,node (T.Just 0) T.Flexible,T.Just (poison "after changed edge"))],[])
  ,("queried tag before later tag",Left "queried tag",
      [(0,T.Node (poison "queried tag") T.Nothing T.Flexible,T.Nothing),
       (1,T.Node (poison "later tag") T.Nothing T.Flexible,T.Nothing)],[(True,0),(False,1)])
  ,("unqueried tag remains lazy",Right "I",
      [(0,root,T.Nothing),(1,T.Node (poison "unqueried") T.Nothing T.Rigid,T.Nothing)],[(True,0)])
  ,("bottom bypasses rigid path",Right "OO",
      [(0,T.Node T.GBot T.Nothing T.Rigid,T.Nothing)],[(False,0),(True,0)])
  ,("changed rigid parent preserves red",Right "RR",
      [(0,node T.Nothing T.Rigid,T.Nothing),
       (1,T.Node T.GBot (T.Just 0) T.Flexible,T.Just 0),
       (2,node (T.Just 0) T.Rigid,T.Nothing)],[(False,1),(True,1)])]

-- Independently serialize the entire public state, including Patricia shape.
tree value T.IntMapNil = "N"
tree value (T.IntMapTip k v) = "T"++show k++"("++value v++")"
tree value (T.IntMapBin n p l r) = "B"++show (n,p)++"("++tree value l++","++tree value r++")"
intMap value (T.IntMap t) = tree value t
parentText T.Nothing = "none"
parentText (T.Just n) = show n
kindText T.Star = "*"
kindText (T.KArrow a b) = "("++kindText a++","++kindText b++")"
tagText T.GBot = "bot"
tagText (T.GBotK k) = "botK"++kindText k
tagText (T.GArr a b) = "arr"++show (a,b)
tagText (T.GCon n xs) = "con"++show (B.unpack n,xs)
tagText (T.GTyCon n k) = "tycon"++show (B.unpack n)++kindText k
tagText (T.GSkolem n k) = "skolem"++show n++kindText k
tagText (T.GTyApp a b) = "app"++show (a,b)
tagText (T.GGen n) = "gen"++show n
nodeText (T.Node t b f) = tagText t++":"++parentText b++":"++(case f of T.Rigid->"R";T.Flexible->"F")
graphText (T.Graph ns ls n) = intMap nodeText ns++intMap show ls++show n
resultText (T.Left e) = "Left "++B.unpack e
resultText (T.Right g) = "Right "++graphText g

main = do
  forM_ [0..239] $ \seed -> forM_ [-12,0,2^60] $ \low -> do
    let entries=generated seed low;high=low+7
        queries=[(side,low+i)|i<-reverse [0..7],side<-[True,False,True]]
    check "complete permission values" (oldAnswers low high entries queries) (newAnswers low high entries queries)
    check "sufficient edge equality"
      (all (\(_,T.Node _ p f,q)->case f of T.Rigid->True; T.Flexible->F.equalMaybeInt p q) entries)
      (admission low high entries)
  putStrLn "PASS 720 permission views and admission decisions"
  check "unchanged guard" True (admission 0 1 same)
  check "changed guard" False (admission 0 1 changed)
  check "rigid-only changes admitted" True (admission 0 1 rigidChanged)
  check "admitted old memo shared" 'R' (shared 0 1 same)
  check "changed old memo isolated" 'I' (shared 0 1 changed)
  check "rigid-only change memo shared" 'R' (shared 0 1 rigidChanged)
  putStrLn "PASS admitted cache sharing and fallback isolation"
  forM_ demandCases $ \(label,expected,es,qs) -> do
    a<-observe (oldAnswers 0 2 es qs);b<-observe (newAnswers 0 2 es qs)
    check (label++" frozen demand") expected a
    check (label++" candidate demand") a b
  putStrLn "PASS 10 authored demand and exception-order cases"
  forM_ [0..119] $ \seed -> do
    let es=generated seed 0
        closeTag (T.Node (T.GGen _) b f) = T.Node (T.GCon "D" []) b f
        closeTag v = v
        g=T.Graph (F.nodesFromList [(n,closeTag v)|(n,v,_)<-es]) IM.empty 8
        pairs=[[],[(1,2)],[(1,2),(3,4)],[(2,1),(2,3)],[(1,1)]]
    forM_ pairs $ \eqs -> check "exact public unify result" (resultText (F.unify eqs g)) (resultText (C.unify eqs g))
    check "exact dense rebind" (resultText (F.rebind g g)) (resultText (C.rebind g g))
  putStrLn "PASS 720 exact public graph and first-error results"
