{-# LANGUAGE OverloadedStrings, DeriveDataTypeable #-}
{-# OPTIONS_GHC -fno-cse -fno-full-laziness #-}
module Main where
import Prelude
import Control.Exception (Exception,SomeException,throw,try,evaluate,fromException,displayException)
import Control.Monad (unless,forM_)
import Data.Typeable (Typeable)
import Data.List (isInfixOf)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified Prototype.BulkExpansion as C

data Probe = Probe String deriving (Show,Typeable)
instance Exception Probe
data Variant = Total | NameProbe | Mismatch | TwoProbes deriving Eq
data Spec = Spec String Variant P.Int P.Int Bool Bool

-- The first three variants are the exact known-valid internal-hole fixture
-- from 74fc2a5. Translations preserve its graph relations. No fields are changed
-- after prepare. TwoProbes is differential-only, not a claimed literal oracle.
{-# NOINLINE input #-}
input :: Spec -> T.Graph
input spec@(Spec _ variant _ _ aliases exhausted) =
  T.Graph (G.nodesFromList [(ident spec i,renode v) | (i,v)<-base]) links fresh
  where
    n t b=T.Node t (T.Just b) T.Flexible
    sibling=case variant of Total->"Sibling"; _->throw (Probe "sibling")
    sourceName=if variant==TwoProbes then throw (Probe "source") else "New"
    base=[(0,T.Node (T.GGen 1) T.Nothing T.Flexible)
      ,(1,n (T.GArr 2 3) 0),(2,n (T.GArr 4 5) 0)
      ,(3,n (T.GTyCon sibling T.Star) 0),(4,n T.GBot 0)
      ,(5,n (if variant==Mismatch then T.GTyCon "Old" T.Star else T.GBot) 0)
      ,(6,n (T.GGen 7) 0),(7,n (T.GArr 8 9) 6),(8,n (T.GArr 10 11) 6)
      ,(9,n (if variant==Mismatch || variant==TwoProbes then T.GTyCon sourceName T.Star else T.GBot) 6)
      ,(10,n T.GBot 6),(11,n T.GBot 6)]
    renode (T.Node t b f)=T.Node (G.mapTag (ident spec) t)
      (case b of T.Nothing->T.Nothing; T.Just k->T.Just (ident spec k)) f
    -- Alias keys occupy gaps, never live identities; nextId exceeds them.
    links=if aliases then IM.fromList [(ident spec 0+1,ident spec 2),(ident spec 1+1,ident spec 0+1)] else IM.empty
    fresh=if exhausted then 9223372036854775806 else ident spec 12
ident :: Spec -> P.Int -> P.Int
ident (Spec _ _ offset stride _ _) i=offset+stride*i

physical :: (a -> String) -> T.IntMap a -> String
physical value (T.IntMap tree)=go tree where
  go T.IntMapNil="N"
  go (T.IntMapTip k v)="T("++show k++","++value v++")"
  go (T.IntMapBin count prefix l r)="B("++show count++","++show prefix++","++go l++","++go r++")"
setPhysical :: T.IntSet -> String
setPhysical (T.IntSet tree)=go tree where
  go T.IntSetNil="N"
  go (T.IntSetTip count prefix bitmap)="T("++show count++","++show prefix++","++show bitmap++")"
  go (T.IntSetBin count prefix l r)="B("++show count++","++show prefix++","++go l++","++go r++")"
node :: T.Node -> String
node v=P.textToChars (G.tagDescription (G.tag v))++";children="++show (G.children (G.tag v))
  ++";binder="++parent (G.binder v)++";flag="++flag (G.flag v)
  where
    parent T.Nothing="Nothing"
    parent (T.Just x)="Just "++show x
    flag T.Flexible="Flexible"
    flag T.Rigid="Rigid"
graphSnap :: T.Graph -> String
graphSnap g=unlines ["next="++show (G.nextId g),"nodes="++physical node (G.nodes g),"links="++physical show (G.links g)]
solverSnap :: T.Solver -> String
solverSnap s=graphSnap (S.graph s)++unlines
  ["parents="++physical setPhysical (S.structuralParents s)
  ,"children="++physical setPhysical (S.bindingChildren s)
  ,"intervals="++physical show intervals
  ,"jumps="++show (map (physical show) jumps)]
  where T.ScopeIndex intervals jumps=S.scopeIndex s

capture :: IO a -> IO (Either SomeException a)
capture=try
strictText :: String -> IO String
strictText text=do
  -- Force characters, not just the list spine, inside the exception boundary.
  _<-evaluate (foldr (\c z->c `seq` z) () text)
  unless (length text<=16384) (ioError (userError "finite sidecar limit"))
  pure text
classify :: SomeException -> String
classify ex=case fromException ex :: Maybe Probe of
  Just (Probe label)->"PROBE:"++label
  Nothing | "identity supply exhausted" `isInfixOf` displayException ex -> "IDENTITY_EXHAUSTED"
          | otherwise -> "OTHER:"++displayException ex
observe :: T.Either P.String a -> (a -> IO String) -> IO (String,String)
observe expression render=do
  result<-capture $ case expression of
    T.Left err->do text<-strictText (P.textToChars err);pure ("LEFT",text)
    T.Right value->do text<-render value >>= strictText;pure ("OK",text)
  pure $ case result of Left ex->(classify ex,"");Right value->value
whnfSolver :: T.Solver -> IO String
whnfSolver s=evaluate (G.strictGraph (S.graph s)) >> pure ""
whnfExpanded :: (P.Int,T.IntMap P.Int,[(P.Int,P.Int)],T.Graph) -> IO String
whnfExpanded (_,_,_,g)=evaluate (G.strictGraph g) >> pure ""
expandedSnap :: (P.Int,T.IntMap P.Int,[(P.Int,P.Int)],T.Graph) -> IO String
expandedSnap (root,copies,frontier,g)=pure ("root="++show root++"\ncopies="++physical show copies++"\nfrontier="++show frontier++"\n"++graphSnap g)

writeObservation :: String -> String -> String -> (String,String) -> IO ()
writeObservation name phase side (status,text)=do
  body<-strictText (status++"\n"++text)
  writeFile (name++"."++phase++"."++side++".txt") body
  appendFile "events.tsv" (name++"\t"++phase++"\t"++side++"\t"++status++"\n")
checkPair :: String -> String -> Maybe String -> IO (String,String) -> IO (String,String) -> IO ()
checkPair name phase expected left right=do
  a<-left;b<-right
  writeObservation name phase "A" a;writeObservation name phase "C" b
  unless (a==b) (ioError (userError (name++"/"++phase++": A/C mismatch")))
  case expected of Nothing->pure ();Just status->unless (fst a==status)
    (ioError (userError (name++"/"++phase++": literal status failed")))
  unless (not ("OTHER:" `isInfixOf` fst a)) (ioError (userError "unexpected exception"))

runCase :: Spec -> IO ()
runCase spec@(Spec name variant _ _ _ exhausted)=do
  let prepare action=G.bindE (S.prepare (input spec)) action
      source=ident spec 6; target=ident spec 2
      aExpand=prepare (S.expandedGraphPrepared source target)
      cExpand=prepare (C.expandedGraphPrepared source target)
      aFull=prepare (S.instantiateExpandedPrepared source target)
      cFull=prepare (C.instantiateExpandedPrepared source target)
      fullExpected=if exhausted then Just "IDENTITY_EXHAUSTED" else case variant of
        Total->Just "OK";NameProbe->Just "PROBE:sibling";Mismatch->Just "LEFT";TwoProbes->Nothing
  checkPair name "prepare" (Just "OK")
    (observe (S.prepare (input spec)) whnfSolver)
    (observe (C.prepare (input spec)) whnfSolver)
  checkPair name "expand-whnf" (Just (if exhausted then "IDENTITY_EXHAUSTED" else "OK"))
    (observe aExpand whnfExpanded) (observe cExpand whnfExpanded)
  checkPair name "full-whnf" fullExpected (observe aFull whnfSolver) (observe cFull whnfSolver)
  if variant==Mismatch && not exhausted then do
    actual<-observe aFull whnfSolver
    unless (snd actual=="type constructor mismatch: TyCon \"New\" (*) versus TyCon \"Old\" (*)")
      (ioError (userError "mismatch literal error failed"))
    else pure ()
  -- Deep snapshots are separate observations, total successful controls only.
  if variant==Total && not exhausted then do
    checkPair name "expanded-snapshot" (Just "OK") (observe aExpand expandedSnap) (observe cExpand expandedSnap)
    checkPair name "solver-snapshot" (Just "OK") (observe aFull (pure . solverSnap)) (observe cFull (pure . solverSnap))
    else pure ()

specs :: [Spec]
specs=[Spec "total" Total 0 1 False False
      ,Spec "name-probe" NameProbe 0 1 False False
      ,Spec "mismatch" Mismatch 0 1 False False
      ,Spec "signed" Total (-100) 1 False False
      ,Spec "signed-gapped" Total (-100) 4 False False
      ,Spec "prefix-cross" Total 250 1 False False
      ,Spec "aliases" Total 0 2 True False
      ,Spec "aliases-probe" NameProbe 0 2 True False
      ,Spec "two-probes" TwoProbes 0 1 False False
      ,Spec "identity-exhausted" Total 0 1 False True
      ,Spec "exhaust-before-poison" NameProbe 0 1 False True]
main :: IO ()
main=do
  writeFile "events.tsv" "case\tphase\tside\toutcome\n"
  forM_ specs runCase
  writeFile "complete.txt" "PASS bulk-publication finite 11 cases\n"
  putStrLn "PASS bulk-publication finite 11 cases"
