{-# LANGUAGE OverloadedStrings, DeriveDataTypeable #-}
module Main where
import Prelude
import Control.Exception (Exception, evaluate, throw, try)
import Data.Typeable (Typeable)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as A
import qualified Candidate.Graph as C
import qualified Bootstrap.IntMap as IM

data Probe = Probe String deriving (Show,Typeable)
instance Exception Probe
node t b = A.mkNode t b T.Flexible
graph ps ls n = A.mkGraph (A.nodesFromDistinctAscList ps) (IM.fromDistinctAscList ls) n
bind T.Nothing=Nothing
bind (T.Just n)=Just n
tree f T.IntMapNil="Nil"
tree f (T.IntMapTip k v)="Tip "++show k++" "++f v
tree f (T.IntMapBin count prefix l r)="Bin "++show(count,prefix)++" ("++tree f l++") ("++tree f r++")"
mapTree f (T.IntMap t)=tree f t
renderNode n=show(P.textToChars(A.tagDescription(A.tag n)),bind(A.binder n),case A.flag n of T.Flexible->"F";T.Rigid->"R")
render g=mapTree renderNode(A.nodes g)++"|"++mapTree show(A.links g)++"|"++show(A.nextId g)
out x = case x of T.Left e -> "Left "++show(P.textToChars e); T.Right g -> "Right "++render g
unit x = case x of T.Left e -> "Left "++show(P.textToChars e); T.Right () -> "Right ()"
check label expected a c = do
  writeFile (label++".A") (a++"\n")
  writeFile (label++".C") (c++"\n")
  writeFile (label++".expected") (expected++"\n")
  let ok=a==expected && c==expected
  writeFile (label++".result") (if ok then "PASS\n" else "FAIL\n")
  pure ()
root n=node (T.GGen n) T.Nothing
bot b=node T.GBot (T.Just b)
arr a b p=node (T.GArr a b) (T.Just p)
-- All same-typed alias choices use real Primitive arrays. No hidden graph model.
direct candidate mode = P.runST $ do
  old <- P.newSTArray 2 T.Nothing
  new <- P.newSTArray 2 T.Nothing
  colours <- P.newSTArray 2 0
  independentImages <- P.newSTArray 2 0
  independentDepths <- P.newSTArray 2 0
  independentGrafted <- P.newSTArray 2 0
  classes <- P.newSTArray 2 []
  flags <- P.newSTArray 2 T.Flexible
  parents <- P.newSTArray 2 []
  tree <- P.newSTArray 2 T.Nothing
  independentBinders <- P.newSTArray 2 T.Nothing
  raised <- P.newSTArray 2 T.Nothing
  let images=if mode=="images" then colours else independentImages
      depths=if mode=="depths" then colours else independentDepths
      grafted=if mode=="grafted" then colours else independentGrafted
      binders=if mode=="tree" then tree else independentBinders
  P.writeSTArray parents 0 [1]
  if mode=="grafted" || mode=="zero" then pure () else P.writeSTArray grafted 0 1
  let answer=if candidate
        then C.densePlace (C.DenseRebinding A.emptyGraph A.emptyGraph 0 1 old new images classes flags parents tree depths colours grafted binders raised) 0
        else A.densePlace (A.DenseRebinding A.emptyGraph A.emptyGraph 0 1 old new images classes flags parents tree depths colours grafted binders raised) 0
  result <- answer
  os <- mapM (P.readSTArray old) [0,1]
  ns <- mapM (P.readSTArray new) [0,1]
  is <- mapM (P.readSTArray images) [0,1]
  cs <- mapM (P.readSTArray classes) [0,1]
  fs <- mapM (P.readSTArray flags) [0,1]
  ps <- mapM (P.readSTArray parents) [0,1]
  ts <- mapM (P.readSTArray tree) [0,1]
  ds <- mapM (P.readSTArray depths) [0,1]
  co <- mapM (P.readSTArray colours) [0,1]
  gs <- mapM (P.readSTArray grafted) [0,1]
  bs <- mapM (P.readSTArray binders) [0,1]
  rs <- mapM (P.readSTArray raised) [0,1]
  let maybeNode T.Nothing="Nothing";maybeNode(T.Just v)="Just "++render(graph[(0,v)][]0)
      flag T.Flexible="F";flag T.Rigid="R"
  pure (unit result++"|old="++show(map maybeNode os)++"|new="++show(map maybeNode ns)
    ++"|images="++show is++"|classes="++show cs++"|flags="++show(map flag fs)++"|parents="++show ps
    ++"|tree="++show(map bind ts)++"|depths="++show ds++"|colours="++show co++"|grafted="++show gs
    ++"|binders="++show(map bind bs)++"|raised="++show(map bind rs))
expectedState mode = "Right ()|old=[\"Nothing\",\"Nothing\"]|new=[\"Nothing\",\"Nothing\"]|images="
  ++(if mode=="images" then "[2,2]" else "[0,0]")
  ++"|classes=[[],[]]|flags=[\"F\",\"F\"]|parents=[[1],[]]|tree="
  ++(if mode=="zero" then "[Nothing,Nothing]" else "[Just 1,Nothing]")
  ++"|depths="++(if mode=="depths" then "[2,2]" else if mode=="zero" then "[0,0]" else "[1,0]")
  ++"|colours=[2,2]|grafted="++(if mode=="grafted" then "[2,2]" else if mode=="zero" then "[0,0]" else "[1,0]")
  ++"|binders="++(if mode=="tree" then "[Just 1,Nothing]" else "[Nothing,Nothing]")++"|raised=[Nothing,Nothing]"
-- Early colour gates must not inspect any other state field.
early candidate colour = P.runST $ do
  colours <- P.newSTArray 1 colour
  let poison=throw (Probe "irrelevant-state")
  r <- if candidate
    then C.densePlace (C.DenseRebinding poison poison 0 0 poison poison poison poison poison poison poison poison colours poison poison poison) 0
    else A.densePlace (A.DenseRebinding poison poison 0 0 poison poison poison poison poison poison poison poison colours poison poison poison) 0
  actual <- P.readSTArray colours 0
  pure (unit r++"|colour="++show actual)
-- Poison ps must be demanded on BOTH nonzero-candidate and retained zero paths.
poisonParents candidate graft = P.runST $ do
  colours <- P.newSTArray 1 0
  gs <- P.newSTArray 1 graft
  ps <- P.newSTArray 1 (throw (Probe "parents"))
  cs <- P.newSTArray 1 []
  let poison=throw(Probe "later-state")
  r <- if candidate
    then C.densePlace (C.DenseRebinding poison poison 0 0 poison poison poison cs poison ps poison poison colours gs poison poison) 0
    else A.densePlace (A.DenseRebinding poison poison 0 0 poison poison poison cs poison ps poison poison colours gs poison poison) 0
  pure(unit r)
observe value = do
  r <- try (evaluate (length value)) :: IO (Either Probe Int)
  pure (case r of Left(Probe name)->"Probe "++name;Right _->value)
regressionMain = do
  let input=graph[(0,root 1),(1,arr 2 3 0),(2,bot 1),(3,arr 4 5 1),(4,bot 3),(5,bot 3)][]6
      ownedInput=graph[(0,root 1),(1,arr 2 3 0),(2,arr 4 5 1),(3,arr 6 7 1),(4,arr 8 9 2),(5,bot 2),(6,arr 10 11 3),(7,bot 3),(8,bot 4),(9,bot 4),(10,bot 6),(11,bot 6)][]12
      expected=graph[(0,root 1),(1,arr 2 3 0),(2,arr 4 5 1),(3,arr 6 7 1),(4,arr 8 9 2),(5,bot 2),(6,arr 8 11 3),(7,bot 3),(8,bot 1),(9,bot 4),(11,bot 6)][(10,8)]12
  -- Cross-branch Bot/Bot merge reaches real owned (6,4)->(3,2)->(1,1).
  check "unify-owned-multihop" ("Right "++render expected) (out(A.unify[(8,10)]ownedInput)) (out(C.unify[(8,10)]ownedInput))
  check "unify-gen-error" "Left \"cannot unify generalization nodes\"" (out(A.unify[(0,1)]input)) (out(C.unify[(0,1)]input))
  let mismatch=graph[(0,root 1),(1,arr 2 3 0),(2,node(T.GTyCon "Int" T.Star)(T.Just 1)),(3,node(T.GTyCon "Bool" T.Star)(T.Just 1))][]4
      err="Left "++show("type constructor mismatch: TyCon \"Int\" (*) versus TyCon \"Bool\" (*)" :: String)
  check "unify-constructor-error" err (out(A.unify[(2,3)]mismatch)) (out(C.unify[(2,3)]mismatch))
  mapM_ (\mode->check ("state-"++mode) (expectedState mode) (direct False mode) (direct True mode)) ["normal","zero","depths","images","grafted","tree"]
  check "colour-complete" "Right ()|colour=2" (early False 2) (early True 2)
  check "colour-cycle" "Left \"cyclic structure/binding dependencies\"|colour=1" (early False 1) (early True 1)
  a <- mapM (observe . poisonParents False) [0,1]
  c <- mapM (observe . poisonParents True) [0,1]
  check "poison-parents" (show ["Probe parents","Probe parents"]) (show a) (show c)
  putStrLn "COMPLETE retained densePlace raw-contract differential"

-- Read-only LCA fixtures construct independent arrays and fixed parent/depth pairs.
lca candidate low poisonDepth poisonRight a b = P.runST $ do
  ts <- P.newSTArray 6 T.Nothing
  ds <- P.newSTArray 6 0
  let parents=[T.Nothing,T.Just low,T.Just(low+1),T.Just low,T.Just(low+3),T.Just(low+4)]
  mapM_ (\(i,p)->P.writeSTArray ts i p) (zip [0..] parents)
  mapM_ (\(i,d)->P.writeSTArray ds i d) (zip [0..] [0,1,2,1,2,3])
  if poisonDepth then P.writeSTArray ds 0 (throw(Probe "initial-depth")) else pure ()
  if poisonRight then do
    P.writeSTArray ts 1 (throw(Probe "right-parent"))
    P.writeSTArray ds 1 0
  else pure ()
  let poison=throw(Probe "unused-state")
  x <- if candidate
    then C.denseCommonPlaced (C.DenseRebinding poison poison low (low+5) poison poison poison poison poison poison ts ds poison poison poison poison) a b
    else A.denseCommon (A.DenseRebinding poison poison low (low+5) poison poison poison poison poison poison ts ds poison poison poison poison) a b
  pure (case x of T.Left e->"Left "++show(P.textToChars e);T.Right n->"Right "++show n)
same candidate = P.runST $ do
  let poison=throw(Probe "same-id-state")
  x <- if candidate then C.denseCommonPlaced poison 7 7 else A.denseCommon poison 7 7
  pure(case x of T.Left e->"Left "++show(P.textToChars e);T.Right n->"Right "++show n)
manyShort candidate single = P.runST $ do
  let poison=throw(Probe "short-many-state")
      xs=if single then [7] else []
  x <- if candidate then C.denseCommonManyPlaced poison xs else A.denseCommonMany poison xs
  pure(case x of T.Left e->"Left "++show(P.textToChars e);T.Right n->show(bind n))
baseMain = do
  regressionMain
  check "cursor-siblings" "Right 0" (lca False 0 False False 2 5) (lca True 0 False False 2 5)
  check "cursor-ancestor" "Right 4" (lca False 0 False False 4 5) (lca True 0 False False 4 5)
  check "cursor-uneven" "Right 1" (lca False 0 False False 2 1) (lca True 0 False False 2 1)
  check "cursor-signed" "Right -3" (lca False (-3) False False (-1) 2) (lca True (-3) False False (-1) 2)
  check "cursor-forest-first-error" "Left \"binders have no common ancestor\""
    (lca False 0 False True 0 1) (lca True 0 False True 0 1)
  a <- observe (lca False 0 True False 0 1)
  c <- observe (lca True 0 True False 0 1)
  check "cursor-initial-depth-probe" "Probe initial-depth" a c
  a2 <- observe(same False)
  c2 <- observe(same True)
  check "cursor-same-id-lazy" "Right 7" a2 c2
  check "cursor-empty-many" "Nothing" (manyShort False False) (manyShort True False)
  check "cursor-single-many" "Just 7" (manyShort False True) (manyShort True True)
  putStrLn "COMPLETE finite depth-cursor differential"

-- NEW finite public-Graph cases. No candidate algorithm change.
graftInput = graph
  [(0,root 1),(1,arr 2 3 0),(2,arr 4 5 1),(3,arr 6 7 1),
   (4,arr 8 9 2),(5,bot 2),(6,arr 10 11 3),(7,bot 3),
   (8,bot 4),(9,bot 4),(10,arr 12 13 6),(11,bot 6),
   (12,bot 10),(13,bot 10)] [] 14
-- Hand-written result: class8 has original binders6,4 ->3,2 ->1.
-- Grafted children12/13 inherit image8 of old binder10.
graftExpected = graph
  [(0,root 1),(1,arr 2 3 0),(2,arr 4 5 1),(3,arr 6 7 1),
   (4,arr 8 9 2),(5,bot 2),(6,arr 8 11 3),(7,bot 3),
   (8,arr 12 13 1),(9,bot 4),(11,bot 6),
   (12,bot 8),(13,bot 8)] [(10,8)] 14
renameTag f t = case t of
  T.GBot -> T.GBot
  T.GArr a b -> T.GArr (f a) (f b)
  T.GGen n -> T.GGen (f n)
  _ -> error "renameTag fixture outside closed tag vocabulary"
renameBinder f b = case b of T.Nothing -> T.Nothing; T.Just n -> T.Just (f n)
renameFixture f g = graph
  [(f k,A.mkNode (renameTag f (A.tag v)) (renameBinder f (A.binder v)) (A.flag v))
    | (k,v) <- IM.toList (A.nodes g)]
  [(f k,f v) | (k,v) <- IM.toList (A.links g)] (f (A.nextId g))
withAliases g aliases fresh = A.mkGraph (A.nodes g) (IM.fromDistinctAscList aliases) fresh
bounds g = show (bind (A.denseBounds g))
qualifyCase label ev eb input expectedGraph expected left right = do
  let av=unit(A.validateGraph input)
      cv=unit(C.validateGraph input)
      ab=bounds input
      cb=show(bind(C.denseBounds input))
      ea=case expectedGraph of Nothing->"NOT_APPLICABLE";Just g->unit(A.validateGraph g)
      ec=case expectedGraph of Nothing->"NOT_APPLICABLE";Just g->unit(C.validateGraph g)
      ee=case expectedGraph of Nothing->"NOT_APPLICABLE";Just _->"Right ()"
      ok=av==ev && cv==ev && ab==eb && cb==eb && ea==ee && ec==ee
      report=(if ok then "PASS\n" else "FAIL\n")
        ++"validate.A="++av++"\nvalidate.C="++cv++"\nvalidate.expected="++ev
        ++"\nbounds.A="++ab++"\nbounds.C="++cb++"\nbounds.expected="++eb
        ++"\noutput.validate.A="++ea++"\noutput.validate.C="++ec
        ++"\noutput.validate.expected="++ee++"\n"
  writeFile (label++".qualification") report
  if ok then check label expected left right
        else check label expected "QUALIFICATION_FAILED_NOT_RUN" "QUALIFICATION_FAILED_NOT_RUN"
graftMain = do
  let good="Right ()"
      right g="Right "++render g
  qualifyCase "graft-dense" good "Just (0,13)" graftInput (Just graftExpected)
    (right graftExpected) (out(A.unify[(8,10)]graftInput)) (out(C.unify[(8,10)]graftInput))
  let f i=2*i-17
      signed=renameFixture f graftInput
      signedExpected=renameFixture f graftExpected
  qualifyCase "graft-signed-gapped" good "Just (-17,9)" signed (Just signedExpected)
    (right signedExpected) (out(A.unify[(f 8,f 10)]signed)) (out(C.unify[(f 8,f 10)]signed))
  let h i=1000*i-17
      sparse=renameFixture h graftInput
      sparseExpected=renameFixture h graftExpected
  qualifyCase "graft-sparse" good "Nothing" sparse (Just sparseExpected)
    (right sparseExpected) (out(A.unify[(h 8,h 10)]sparse)) (out(C.unify[(h 8,h 10)]sparse))
  let aliasInput=withAliases graftInput [(20,10)] 21
      -- canonicalize maps node tags, but deliberately retains link chains.
      aliasExpected=withAliases graftExpected [(10,8),(20,10)] 21
  qualifyCase "graft-disjoint-alias" good "Just (0,13)" aliasInput (Just aliasExpected)
    (right aliasExpected) (out(A.unify[(8,20)]aliasInput)) (out(C.unify[(8,20)]aliasInput))
  let overlap=graph [(0,node T.GBot T.Nothing),(1,node T.GBot T.Nothing)] [(0,1)] 2
      rootsError="Left \"graph must have one binding root\""
  -- Explicit INVALID graph: covers eligibility/root error, not rebindSparse or successful graft.
  qualifyCase "overlap-dispatch-first-error" rootsError "Nothing" overlap Nothing rootsError
    (out(A.unify [] overlap)) (out(C.unify [] overlap))
  let rigid=A.setNode 8 (A.mkNode T.GBot (T.Just 4) T.Rigid) graftInput
      rigidError="Left \"cannot instantiate a rigid or protected type variable\""
  qualifyCase "graft-rigid-error" good "Just (0,13)" rigid Nothing rigidError
    (out(A.unify[(8,10)]rigid)) (out(C.unify[(8,10)]rigid))
  let missingError="Left \"missing graph node 999\""
  qualifyCase "graft-eager-first-error" good "Just (0,13)" graftInput Nothing missingError
    (out(A.unify[(0,1),(999,1)]graftInput)) (out(C.unify[(0,1),(999,1)]graftInput))
  let invalid=graph[(0,node T.GBot T.Nothing)][]1
      invalidError="Left \"binding root must be a gen node\""
      poisonEquations=throw(Probe "equations-must-not-be-demanded")
  qualifyCase "invalid-before-equations" invalidError "Just (0,0)" invalid Nothing invalidError
    (out(A.unify poisonEquations invalid)) (out(C.unify poisonEquations invalid))
  putStrLn "COMPLETE finite public graft and dispatch differential"
main = do
  baseMain
  graftMain
