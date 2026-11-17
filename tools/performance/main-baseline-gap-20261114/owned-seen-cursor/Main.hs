{-# LANGUAGE OverloadedStrings, DeriveDataTypeable #-}
module Main where
import Prelude
import Control.Exception (Exception, evaluate, throw, try)
import Data.Typeable (Typeable)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as A
import qualified Prototype.OwnedSeenSolver as C
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.IntRank as Rank

data Probe = Probe String deriving (Show, Typeable)
instance Exception Probe
type Visit = T.Solver -> [P.Int] -> T.Either P.String (T.IntMap T.Node,T.IntSet)
type Prepare = T.Graph -> T.Either P.String T.Solver
type Seek = P.Int -> T.IntMap T.Node -> T.Maybe (T.Node -> T.IntMap T.Node)
type Projection = (T.Graph,[(P.Int,P.Int)],[(P.Int,T.Node)],
                   (Rank.MapIndex T.Node,T.IntMap (T.Maybe P.Int),T.IntMap P.Int))
type Project = T.Solver -> T.Graph -> P.Int -> [(P.Int,T.Node)] ->
               [(P.Int,P.Int)] -> T.Either P.String Projection

node :: T.GTag -> T.Maybe P.Int -> T.Node
node t b = T.Node t b T.Flexible
root :: P.Int -> T.Node
root n = node (T.GGen n) T.Nothing
bot :: P.Int -> T.Node
bot n = node T.GBot (T.Just n)
graph :: [(P.Int,T.Node)] -> [(P.Int,P.Int)] -> P.Int -> T.Graph
graph ns ls fresh = T.Graph (IM.fromDistinctAscList ns) (IM.fromDistinctAscList ls) fresh
right :: T.Either P.String a -> a
right x = case x of { T.Left e -> error (P.textToChars e); T.Right v -> v }
kind :: T.Kind -> String
kind T.Star = "Star"
kind (T.KArrow a b) = "KArrow("++kind a++","++kind b++")"
tag :: T.GTag -> String
tag T.GBot = "Bot"
tag (T.GBotK k) = "BotK("++kind k++")"
tag (T.GArr a b) = "Arr"++show(a,b)
tag (T.GCon n xs) = "Con"++show(P.textToChars n,xs)
tag (T.GTyCon n k) = "TyCon"++show(P.textToChars n)++kind k
tag (T.GSkolem n k) = "Skolem"++show n++kind k
tag (T.GTyApp a b) = "App"++show(a,b)
tag (T.GGen n) = "Gen"++show n
maybeInt :: T.Maybe P.Int -> String
maybeInt T.Nothing = "None"
maybeInt (T.Just n) = "Just"++show n
flag :: T.Flag -> String
flag T.Flexible = "Flexible"
flag T.Rigid = "Rigid"
nodeText :: T.Node -> String
nodeText (T.Node t b f) = "Node("++tag t++","++maybeInt b++","++flag f++")"
tree :: (a -> String) -> T.IntMapTree a -> String
tree _ T.IntMapNil = "Nil"
tree value (T.IntMapTip n v) = "Tip("++show n++","++value v++")"
tree value (T.IntMapBin count prefix l r) =
  "Bin("++show(count,prefix)++","++tree value l++","++tree value r++")"
mapText :: (a -> String) -> T.IntMap a -> String
mapText value (T.IntMap t) = tree value t
setTree :: T.IntSetTree -> String
setTree T.IntSetNil = "SNil"
setTree (T.IntSetTip count prefix bits) = "STip"++show(count,prefix,bits)
setTree (T.IntSetBin count prefix l r) =
  "SBin("++show(count,prefix)++","++setTree l++","++setTree r++")"
setText :: T.IntSet -> String
setText (T.IntSet t) = setTree t
graphText :: T.Graph -> String
graphText (T.Graph ns ls n) =
  "Graph("++mapText nodeText ns++","++mapText show ls++","++show n++")"
scopeText :: T.ScopeIndex -> String
scopeText (T.ScopeIndex intervals jumps) =
  "Scopes("++mapText show intervals++","++show(map(mapText show)jumps)++")"
solverText :: T.Solver -> String
solverText (T.Solver g p d s) =
  graphText g++"|parents="++mapText setText p++"|children="++mapText setText d++"|"++scopeText s
logical :: T.Graph -> String
logical g = show[(n,nodeText v)|(n,v)<-IM.toList(G.nodes g)]
            ++"|"++show(IM.toList(G.links g),G.nextId g)
rankText :: Rank.MapIndex T.Node -> String
rankText (Rank.MapIndex t) = tree nodeText t
tupleText :: Projection -> String
tupleText (local,eqs,originals,(forward,scopes,stubs)) =
  graphText local++"|equations="++show eqs
  ++"|originals="++show[(k,nodeText v)|(k,v)<-originals]
  ++"|forward="++rankText forward++"|scopes="++mapText maybeInt scopes
  ++"|stubs="++mapText show stubs
outcome :: T.Either P.String T.Solver -> String
outcome x = case x of { T.Left e -> "Left "++P.textToChars e; T.Right s -> "Right "++solverText s }
summary :: T.Either P.String a -> String
summary x = case x of { T.Left e -> "Left "++P.textToChars e; T.Right _ -> "Right" }
route :: T.Graph -> String
route g = case G.denseBounds g of { T.Nothing -> "Sparse"; T.Just _ -> "Dense" }
forceText :: String -> String
forceText s = seq (foldr (\c n -> seq c (n+1)) (0::Int) s) s
observe :: String -> IO String
observe text = do
  got <- try (evaluate (forceText text)) :: IO (Either Probe String)
  pure (case got of { Left (Probe e) -> "Probe "++e; Right result -> result })

visitA, visitC :: Visit
visitA s starts = A.componentCanonicalNodesVisit s IM.empty IS.empty starts
visitC s starts = C.componentCanonicalNodesOwned s starts
family :: [P.Int] -> T.Graph
family keys = case keys of {
  [r,a,b,c] -> graph [(r,root a),(a,node (T.GArr b c) (T.Just r)),(b,bot a),(c,bot a)] [] (c+1);
  _ -> error "four literal keys required" }
base :: T.Graph
base = family [0,1,2,3]
handMerged :: T.Graph
handMerged = graph [(0,root 1),(1,node (T.GArr 2 2) (T.Just 0)),(2,bot 1)] [(3,2)] 4
componentObservation :: Prepare -> Visit -> [P.Int] -> String
componentObservation prepare visit keys =
  let g=family keys; s=right(prepare g); before=solverText s
      starts=[keys!!1,keys!!1,keys!!2,keys!!3,keys!!1]
  in case visit s starts of {
    T.Left e -> "Left "++P.textToChars e;
    T.Right (seen,scopes) ->
      let hand=show[(n,nodeText v)|(n,v)<-IM.toList seen]
               ==show[(n,nodeText v)|(n,v)<-IM.toList(G.nodes g)]
               && IS.toList scopes==[head keys]
      in "Right;keys="++show(IM.keys seen)++";scopes="++show(IS.toList scopes)
         ++";hand="++show hand++";snapshot="++show(before==solverText s)++";input-validation-route="++route g
         ++"\nseen="++mapText nodeText seen++"\nscopes="++setText scopes
         ++"\nbefore="++before++"\nafter="++solverText s }
keyObservation :: Visit -> T.Solver -> [P.Int] -> String
keyObservation visit s starts = case visit s starts of {
  T.Left e -> "Left "++P.textToChars e;
  T.Right (seen,scopes) -> "Right;keys="++show(IM.keys seen)++";scopes="++show(IS.toList scopes) }
rawSolver :: T.Graph -> T.Solver
rawSolver g = T.Solver g IM.empty IM.empty (throw(Probe "unused-scope"))
genBoundary :: T.Solver
genBoundary = T.Solver
  (T.Graph (IM.singleton 0 (node (T.GGen (throw(Probe "unused-gen-child")))
                                  (throw(Probe "unused-gen-binder"))))
           (throw(Probe "unused-links")) (throw(Probe "unused-next")))
  (throw(Probe "unused-parents")) (throw(Probe "unused-descendants")) (throw(Probe "unused-scope"))
unusedPayload :: T.Solver
unusedPayload = rawSolver (T.Graph
  (IM.fromDistinctAscList [(0,root 1),
    (1,node (T.GTyCon (throw(Probe "unused-name")) (throw(Probe "unused-kind"))) (T.Just 0))])
  (throw(Probe "unused-links")) (throw(Probe "unused-next")))
missingFirst :: T.Solver
missingFirst = rawSolver (T.Graph IM.empty (throw(Probe "unused-links")) (throw(Probe "unused-next")))
seekA :: Seek
seekA key seen = if IM.member key seen then T.Nothing else T.Just (\v -> IM.insert key v seen)
seekHit :: Seek -> String
seekHit seek = case seek 1 (IM.singleton 1 (throw(Probe "unused-hit-payload"))) of {
  T.Nothing -> "hit"; T.Just _ -> "miss" }
seekMissHead :: Seek -> String
seekMissHead seek = case seek (throw(Probe "deferred-key")) IM.empty of {
  T.Nothing -> "hit"; T.Just _ -> "miss" }
seekMissApply :: Seek -> String
seekMissApply seek = case seek (throw(Probe "deferred-key")) IM.empty of {
  T.Nothing -> "hit";
  T.Just build -> case build (bot 0) of { T.IntMap t -> seq t "built" } }
deferredObservation :: Seek -> IO String
deferredObservation seek = do
  first <- observe (seekMissHead seek)
  second <- observe (seekMissApply seek)
  pure (first++";"++second)
rawSeen :: T.IntMap T.Node
rawSeen = T.IntMap (T.IntMapBin (throw(Probe "unused-raw-count")) 10
  (T.IntMapTip 1 (throw(Probe "unused-raw-payload"))) (throw(Probe "unused-raw-offpath")))
rawOldA, rawOldC :: String
rawOldA = summary (A.componentCanonicalNodesVisit (throw(Probe "unused-solver")) rawSeen IS.empty [1])
rawOldC = summary (C.componentCanonicalNodesVisit (throw(Probe "unused-solver")) rawSeen IS.empty [1])

unifyObservation :: Prepare -> ([(P.Int,P.Int)] -> T.Solver -> T.Either P.String T.Solver) -> String
unifyObservation prepare unify =
  let s=right(prepare base); before=solverText s
  in case unify [(2,3)] s of {
    T.Left e -> "Left "++P.textToChars e;
    T.Right solved ->
      "Right;hand="++show(logical(A.graph solved)==logical handMerged)
      ++";snapshot="++show(before==solverText s)
      ++"\nsolved="++solverText solved++"\nbefore="++before++"\nafter="++solverText s }
restore :: T.Solver -> Projection -> T.Either P.String T.Solver
restore s (local,eqs,originals,(forward,scopes,stubs)) =
  G.bindE (G.unify eqs local) $ \solved ->
  G.bindE (G.mapE_ (\stub -> G.check
    (A.matchesNode (G.nodes solved) stub (G.nodeAt local stub) && G.resolve solved stub==stub)
    "local unification changed a hidden scope root") (IM.elems stubs)) $ \_ ->
  G.bindE (G.mapE_ (A.checkPreservedScope (A.graph s) solved forward scopes) originals) $ \_ ->
  A.restoreExpandedProjection s (A.graph s) 4 originals forward (fromIntegral(length originals)) solved
projectionObservation :: Prepare -> Project -> String
projectionObservation prepare project =
  let s=right(prepare base); before=solverText s
  in case project s (A.graph s) 4 [] [(2,3)] of {
    T.Left e -> "Left "++P.textToChars e;
    T.Right tuple@(local,eqs,originals,(forward,scopes,stubs)) ->
      let restored=restore s tuple
          hand=logical local==logical base && eqs==[(2,3)]
            && show[(k,nodeText v)|(k,v)<-originals]==show[(k,nodeText v)|(k,v)<-IM.toList(G.nodes base)]
            && rankText forward==tree nodeText (case G.nodes base of { T.IntMap t -> t })
            && mapText maybeInt scopes==mapText maybeInt(IM.singleton 0 T.Nothing) && IM.null stubs
          finalHand=case restored of { T.Left _ -> False; T.Right v -> logical(A.graph v)==logical handMerged }
      in "Right;hand="++show hand++";snapshot="++show(before==solverText s)
         ++";local-unify="++summary(G.unify eqs local)++";restore="++summary restored
         ++";final-hand="++show finalHand
         ++"\nprojection="++tupleText tuple++"\nlocal="++(case G.unify eqs local of {
              T.Left e -> "Left "++P.textToChars e; T.Right solved -> graphText solved })
         ++"\nrestored="++outcome restored++"\nbefore="++before++"\nafter="++solverText s }
projectionMissing :: Prepare -> Project -> String
projectionMissing prepare project =
  let s=right(prepare base)
  in summary(project s (throw(Probe "unused-current")) 100 (throw(Probe "unused-fresh")) [(99,99)])

record :: String -> String -> IO String -> IO String -> IO ()
record name expected oldAction newAction = do
  a <- oldAction
  writeFile (name++".A") (a++"\n")
  c <- newAction
  writeFile (name++".C") (c++"\n")
  writeFile (name++".expected") (expected++"\n")
  let ok=a==c && takeWhile (/='\n') a==expected
  writeFile (name++".result") (if ok then "PASS\n" else "FAIL\n")
  if ok then pure () else error ("finite mismatch: "++name)
pair :: String -> String -> String -> String -> IO ()
pair name expected a c = record name expected (observe a) (observe c)
main :: IO ()
main = do
  pair "component-contiguous" "Right;keys=[0,1,2,3];scopes=[0];hand=True;snapshot=True;input-validation-route=Dense"
    (componentObservation A.prepare visitA [0,1,2,3]) (componentObservation C.prepare visitC [0,1,2,3])
  pair "component-signed-gapped" "Right;keys=[-7,-2,3,9];scopes=[-7];hand=True;snapshot=True;input-validation-route=Dense"
    (componentObservation A.prepare visitA [-7,-2,3,9]) (componentObservation C.prepare visitC [-7,-2,3,9])
  pair "component-wide-ids" "Right;keys=[-1000,0,1000,9000];scopes=[-1000];hand=True;snapshot=True;input-validation-route=Sparse"
    (componentObservation A.prepare visitA [-1000,0,1000,9000])
    (componentObservation C.prepare visitC [-1000,0,1000,9000])
  pair "empty-does-not-demand-solver" "Right;keys=[];scopes=[]"
    (keyObservation visitA (throw(Probe "unused-solver")) [])
    (keyObservation visitC (throw(Probe "unused-solver")) [])
  pair "gen-boundary" "Right;keys=[0];scopes=[0]"
    (keyObservation visitA genBoundary [0,0]) (keyObservation visitC genBoundary [0,0])
  pair "missing-before-poison" "Left missing graph node 99"
    (keyObservation visitA missingFirst [99,throw(Probe "unused-pending")])
    (keyObservation visitC missingFirst [99,throw(Probe "unused-pending")])
  pair "unused-node-payload" "Right;keys=[0,1];scopes=[0]"
    (keyObservation visitA unusedPayload [1,1]) (keyObservation visitC unusedPayload [1,1])
  pair "seek-hit-payload-lazy" "hit" (seekHit seekA) (seekHit C.seekMissing)
  record "seek-miss-deferred" "miss;Probe deferred-key"
    (deferredObservation seekA) (deferredObservation C.seekMissing)
  pair "raw-old-helper-only" "Right" rawOldA rawOldC
  pair "unifyDistinct-success" "Right;hand=True;snapshot=True"
    (unifyObservation A.prepare A.unifyDistinct) (unifyObservation C.prepare C.unifyDistinct)
  pair "unifyDistinct-missing" "Left missing graph node 99"
    (summary(A.unifyDistinct [(2,99)] (right(A.prepare base))))
    (summary(C.unifyDistinct [(2,99)] (right(C.prepare base))))
  pair "preparedFallback-success" "Right;hand=True;snapshot=True;local-unify=Right;restore=Right;final-hand=True"
    (projectionObservation A.prepare A.preparedFallbackProjection)
    (projectionObservation C.prepare C.preparedFallbackProjection)
  pair "preparedFallback-missing" "Left missing graph node 99"
    (projectionMissing A.prepare A.preparedFallbackProjection)
    (projectionMissing C.prepare C.preparedFallbackProjection)
  putStr "PASS 14 owned seen cursor finite cases; no production qualification\n"
