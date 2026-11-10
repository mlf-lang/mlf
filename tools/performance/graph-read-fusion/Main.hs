{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Control.Exception (SomeException, try, evaluate, displayException)
import Control.Monad (forM_, unless)
import Data.List (isPrefixOf, isInfixOf, foldl')
import System.Environment (getArgs)
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified LegacyGraph as F
import qualified CandidateGraph as C
import qualified ReadDemand

check label expected actual = unless (expected == actual) $
  errorWithoutStackTrace (label ++ ": expected " ++ show expected ++ ", got " ++ show actual)
isRight (T.Right _) = True
isRight _ = False
unitText (T.Left e) = "Left " ++ B.unpack e
unitText (T.Right ()) = "Right ()"
observe text = do
  r <- try (evaluate (foldr (\c z -> fromEnum c+z) 0 text)) :: IO (Either SomeException Int)
  pure $ case r of Left e -> Left (displayException e); Right _ -> Right text
poison = errorWithoutStackTrace
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

smallGraphs :: [T.Graph]
smallGraphs=[T.Graph(IM.fromList
 [(0,T.Node(T.GGen 1)T.Nothing T.Flexible),(1,T.Node top parent T.Flexible),
  (2,T.Node left lp T.Flexible),(3,T.Node right rp T.Rigid)])aliases 6
 |top<-[T.GArr 2 3,T.GArr 2 2,T.GTyApp 2 3,T.GCon "Pair"[2,3],T.GArr 5 3],
 left<-[T.GBot,T.GTyCon "F"(T.KArrow T.Star T.Star),T.GArr 3 3,T.GGen 3],
 right<-[T.GBot,T.GTyCon "G"(T.KArrow T.Star T.Star),T.GArr 2 2,T.GArr 9 9],
 parent<-[T.Nothing,T.Just 0,T.Just 2],lp<-[T.Nothing,T.Just 0,T.Just 1,T.Just 3,T.Just 9],
 rp<-[T.Nothing,T.Just 0,T.Just 1,T.Just 2,T.Just 9],
 aliases<-[IM.empty,IM.fromList[(5,4),(4,2)]]]
equations :: [[(B.Int,B.Int)]]
equations=[[],[(1,2)],[(1,3)],[(2,3)],[(2,2)],[(0,1)],[(1,2),(2,3)],[(2,3),(1,2)],[(3,2),(2,1)]]
withFlags :: T.Graph -> T.Flag -> T.Flag -> T.Flag -> T.Graph
withFlags g a b c=T.Graph(IM.mapWithKey(\n v->T.Node(F.tag v)(F.binder v)
 (case n of 1->a;2->b;3->c;_->F.flag v))(F.nodes g))(F.links g)(F.nextId g)
inputs :: [(T.Graph,[(B.Int,B.Int)])]
inputs=[(withFlags g a b c,es)|g<-filter(isRight.F.validateGraph)smallGraphs,
 a<-[T.Flexible,T.Rigid],b<-[T.Flexible,T.Rigid],c<-[T.Flexible,T.Rigid],es<-equations]

rename image g = T.Graph
  (IM.fromList [(image n,T.Node (F.mapTag image (F.tag v))
     (F.mapMaybeInt image (F.binder v)) (F.flag v)) | (n,v)<-IM.toList (F.nodes g)])
  (IM.fromList [(image n,image v) | (n,v)<-IM.toList (F.links g)]) (image (F.nextId g))

-- Count only frozen successful rebinds and actual grafted representatives with
-- structural parents. This is coverage, not a runtime-frequency measurement.
coverage (g,es) = case F.validateGraph g of
 T.Left _ -> (0,0)
 T.Right () -> case F.checkedFirstOrder es g of
  T.Left _ -> (0,0)
  T.Right raw -> let sk=F.canonicalize raw in case F.rebind g sk of
   T.Left _ -> (0,0)
   T.Right _ -> let gs=F.graftedNodes g sk;ps=F.parentsIndex sk
               in (1,sum [length (IS.toList (IM.findWithDefault IS.empty n ps))
                          | n<-IM.keys (F.nodes sk),IS.member n gs])

-- State fixtures only observe arrays that densePlace can mutate. Poisoned
-- read-only inputs are intentionally not serialized after the operation.
data Fixture = Fixture String (Either String String) B.Int [B.Int]
  [(B.Int,B.Int)] [(B.Int,[B.Int])] [(B.Int,[B.Int])]
  [(B.Int,T.Maybe B.Int)] [(B.Int,B.Int)]
fixtures =
 [Fixture "graft zero still places parents" (Right "Right ()") 0 [1] [] [] [] [] []
 ,Fixture "graft one includes parents" (Right "Right ()") 1 [1] [] [] [] [] []
 ,Fixture "negative nonzero includes parents" (Right "Right ()") (-1) [1] [] [] [] [] []
 ,Fixture "duplicate structural parents" (Right "Right ()") 1 [1,1,1] [] [] [] [] []
 ,Fixture "empty structural parents" (Right "Right ()") 1 [] [] [] [] [] []
 ,Fixture "recursive parent completion" (Right "Right ()") 1 [1] [] [(1,[2])] [] [] []
 ,Fixture "already completed parent ignores poison" (Right "Right ()") 1 [1] [(1,2)] [(1,poison "unused ps")] [(1,poison "unused classes")] [] []
 ,Fixture "complete node ignores all payloads" (Right "Right ()") (poison "unused graft") (poison "unused parents") [(0,2)] [] [(0,poison "unused members")] [] []
 ,Fixture "graft parent cycle" (Right "Left cyclic structure/binding dependencies") 1 [0] [] [] [] [] []
 ,Fixture "out of bounds before tail" (Left "*") 1 (4:poison "late oob tail") [] [] [] [] []
 ,Fixture "successful prefix then bounds" (Left "*") 1 [1,4] [] [] [] [] []
 ,Fixture "negative index before tail" (Left "*") 0 ((-1):poison "late negative tail") [] [] [] [] []
 ,Fixture "graft zero parent cycle" (Right "Left cyclic structure/binding dependencies") 0 [0] [] [] [] [] []
 ,Fixture "candidate failure before graft" (Right "Left cyclic structure/binding dependencies") (poison "late graft") (poison "late parents") [] [] [(0,[0])] [(0,T.Just 0)] []
 ,Fixture "candidate failure before parent tail" (Right "Left cyclic structure/binding dependencies") 1 (0:poison "late tail") [] [] [] [] []
 ,Fixture "original candidate before ps" (Left "original binder") 1 (poison "parent list") [] [] [(0,[0])] [(0,poison "original binder")] []
 ,Fixture "graft demanded after original success" (Left "graft first") (poison "graft first") (poison "parents second") [] [] [] [] []
 ,Fixture "parent head before tail" (Left "parent first") 1 (poison "parent first":poison "tail second") [] [] [] [] []
 ,Fixture "parent tail required" (Left "tail needed") 1 (1:poison "tail needed") [] [] [] [] []
 ,Fixture "zero graft parent tail required" (Left "zero tail needed") 0 (1:poison "zero tail needed") [] [] [] [] []
 ]
scratch alias candidate (Fixture _ _ graft ps colourRows parentRows classRows binderRows imageRows) = P.runST $ do
  oldNodes<-P.newSTArray 4 T.Nothing;newNodes<-P.newSTArray 4 T.Nothing
  images<-P.newSTArray 4 0;classes<-P.newSTArray 4 [];flags<-P.newSTArray 4 T.Flexible
  parents<-P.newSTArray 4 [];tree<-P.newSTArray 4 T.Nothing;depths<-P.newSTArray 4 0
  colours0<-P.newSTArray 4 0;grafted0<-P.newSTArray 4 0
  let colours=if alias then depths else colours0;grafted=if alias then depths else grafted0
  oldBinders<-P.newSTArray 4 T.Nothing;raised<-P.newSTArray 4 T.Nothing
  P.writeSTArray grafted 0 graft;P.writeSTArray parents 0 ps
  if alias then P.writeSTArray colours 0 0 else pure ()
  forM_ colourRows $ \(n,v)->P.writeSTArray colours n v
  forM_ parentRows $ \(n,v)->P.writeSTArray parents n v
  forM_ classRows $ \(n,v)->P.writeSTArray classes n v
  forM_ binderRows $ \(n,v)->P.writeSTArray oldBinders n v
  forM_ imageRows $ \(n,v)->P.writeSTArray images n v
  let old=poison "unused old graph";sk=poison "unused skeleton"
  r<-if candidate
     then C.densePlace (C.DenseRebinding old sk 0 3 oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised) 0
     else F.densePlace (F.DenseRebinding old sk 0 3 oldNodes newNodes images classes flags parents tree depths colours grafted oldBinders raised) 0
  ts<-mapM (P.readSTArray tree) [0..3];ds<-mapM (P.readSTArray depths) [0..3];cs<-mapM (P.readSTArray colours) [0..3]
  pure (unitText r ++ "; tree="++show(map parentText ts)++" depths="++show ds++" colours="++show cs)

controls = do
 check "fixed validation inventory" 12000 (length smallGraphs)
 forM_ (zip [0::Int ..] smallGraphs) $ \(i,g)->
   check ("validation "++show i) (unitText(F.validateGraph g)) (unitText(C.validateGraph g))
 putStrLn "PASS 12000 exact validation outcomes"
 forM_ (zip [0::Int ..] inputs) $ \(i,(g,es))->
   check ("public unify "++show i) (resultText(F.unify es g)) (resultText(C.unify es g))
 let counts=map coverage inputs;success=sum(map fst counts);edges=sum(map snd counts)
 check "nonvacuous successful graft-parent coverage" True (success>0 && edges>0)
 putStrLn ("PASS public unification="++show(length inputs)++" frozen-successful-rebinds="++show success++" graft-parent-edges="++show edges)
 let layouts=[("negative",\n->n-37),("wide",\n->n+2^60),
              ("near-min",\n->n+(-2^63)+32),("near-max",\n->n+(2^63-1)-32),
              ("sparse",\n->n*100003-9001),
              ("cross-sign-span",\n->if n==0 then -2^63 else 2^63-1-n)]
 forM_ (zip [0::Int ..] (take 80 inputs)) $ \(i,(g,es))->forM_ layouts $ \(label,image)->
   check (label++show i) (resultText(F.unify (map(\(a,b)->(image a,image b))es)(rename image g)))
                       (resultText(C.unify (map(\(a,b)->(image a,image b))es)(rename image g)))
 putStrLn "PASS 480 signed-Int64 and sparse-layout public results"
 forM_ fixtures $ \f@(Fixture label expected _ _ _ _ _ _ _)->do
   a<-observe(scratch False False f);b<-observe(scratch False True f)
   check (label++" exact exception and scratch-state demand") a b
   case (expected,a) of
    (Left want,Left got)->if want=="*" then check(label++" bounds exception") True ("array index out of bounds" `isInfixOf` got) else check(label++" fixed exception")want got
    (Right want,Right got)->check(label++" fixed result")True(want `isPrefixOf` got)
    _->errorWithoutStackTrace(label++" wrong fixture outcome: "++show a)
 putStrLn "PASS 20 placement demand, failure and scratch-state controls"
 -- All same-type written integer arrays may alias in the public helper.
 forM_ [head fixtures,fixtures!!1,fixtures!!3,fixtures!!4,fixtures!!5] $ \f@(Fixture label _ _ _ _ _ _ _ _)->do
   a<-observe(scratch True False f);b<-observe(scratch True True f)
   check (label++" aliased depths/colours/grafted") a b
   case a of Right text->check(label++" aliased placement actually succeeds")True("Right ()" `isPrefixOf` text);_->errorWithoutStackTrace "alias fixture did not place"
 let cycleFixture=Fixture "aliased entry cycle" (Right "Left cyclic structure/binding dependencies") 1 [] [(0,1)] [] [] [] []
 a<-observe(scratch True False cycleFixture);b<-observe(scratch True True cycleFixture)
 check "alias entry cycle exact outcome" a b
 case a of Right text->check "alias entry cycle negative control" True ("Left cyclic structure/binding dependencies" `isPrefixOf` text);_->errorWithoutStackTrace "alias fixture did not reject"
 putStrLn "PASS 6 aliased scratch-array controls: 5 placements and 1 entry cycle"
 let normalInputs=take 40 (filter (isRight.F.validateGraph) smallGraphs)
 check "40 valid normalization source graphs" 40 (length normalInputs)
 forM_ normalInputs $ \g->forM_ [-12,0,2^60] $ \offset->do
   let graph=rename (\n->n+offset) g
   check "normalization input remains valid" "Right ()" (unitText(F.validateGraph graph))
   check "complete normalization graph" (graphText(F.normalize graph)) (graphText(C.normalize graph))
 putStrLn "PASS 120 valid complete normalization graphs"
 ReadDemand.controls

-- Every batch has distinct graph identities supplied by the runtime repetition
-- index. This avoids timing a shared pure result. The full output is consumed.
{-# NOINLINE batch #-}
batch candidate iteration = foldl' step 0 inputs
 where
  step total (g,es) =
   let { image n=n+fromIntegral(iteration*16)
       ; graph=rename image g
       ; pairs=map(\(a,b)->(image a,image b))es
       ; result=if candidate then C.unify pairs graph else F.unify pairs graph
       }
   in total+foldl' (\a c->a+fromEnum c) 0 (resultText result)

main = do
 args<-getArgs
 case args of
  [] -> controls
  ["bench",side,reps] | side `elem` ["base","candidate"] -> do
    let n=read reps::Int
    unless(n>0 && n<=1000)(errorWithoutStackTrace "invalid repetition count")
    score<-evaluate(foldl' (\a i->a+batch(side=="candidate") i) (0::Int) [1..n])
    print (length inputs*n,score)
  _ -> errorWithoutStackTrace "usage: controls [bench base|candidate repetitions]"
