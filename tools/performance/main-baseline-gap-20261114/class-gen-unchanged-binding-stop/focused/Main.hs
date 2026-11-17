{-# LANGUAGE OverloadedStrings, DeriveDataTypeable #-}
{-# OPTIONS_GHC -fno-cse -fno-full-laziness #-}
module Main where
import Prelude
import Control.Exception (Exception,SomeException,throw,throwIO,try,evaluate,fromException,displayException)
import Control.Monad (unless)
import Data.Typeable (Typeable)
import Data.IORef
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as L
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified Prototype.ClassGenTrial as C

data Probe = NameProbe | KindProbe deriving (Show,Typeable)
instance Exception Probe
data GraphLeft = GraphLeft P.String deriving (Typeable)
instance Show GraphLeft where show _="GraphLeft"
instance Exception GraphLeft
data Entity = GraphEntity T.Graph | SolverEntity T.Solver
data Observation = Observation String String String String (Maybe String) (Maybe Entity)
data Case = Case String ([(P.Int,P.Int)],T.Graph) Bool String
type Trace = IORef (Maybe (C.TrialRoute,T.Maybe P.String))
capture :: IO a -> IO (Either SomeException a)
capture=try
requireE :: T.Either P.String a -> IO a
requireE value=case value of T.Left e -> throwIO (GraphLeft e); T.Right a -> pure a
bounded :: FilePath -> String -> IO ()
bounded path text=do
  unless (length text<=16384) (ioError (userError "fixture file limit"))
  writeFile path text
forceEntity :: Entity -> IO ()
forceEntity (GraphEntity g)=evaluate (G.strictGraph g)>>pure ()
forceEntity (SolverEntity s)=evaluate (G.strictGraph (S.graph s))>>pure ()
probeStatus :: SomeException -> String
probeStatus ex=case fromException ex :: Maybe Probe of Just _ -> "PROBE"; Nothing -> "OTHER"
renderLeft :: P.String -> IO (String,String)
renderLeft e=do
  r<-capture $ do
    let text=P.textToChars e
    _<-evaluate (length text)
    pure text
  pure $ case r of
    Right text -> ("LEFT",text)
    Left ex -> ("LEFT_TEXT_"++probeStatus ex,displayException ex)
observe :: String -> IO Entity -> IO Observation
observe prefix action=do
  answer<-capture (action >>= \e -> forceEntity e >> pure e)
  case answer of
    Left ex -> do
      (status,detail)<-case fromException ex :: Maybe GraphLeft of
        Just (GraphLeft e)->renderLeft e
        Nothing->pure (probeStatus ex,displayException ex)
      bounded (prefix++".call") (status++"\n"++detail)
      bounded (prefix++".encode") "SKIP\n"
      bounded (prefix++".snapshot") "UNAVAILABLE\n"
      pure (Observation status detail "SKIP" "" Nothing Nothing)
    Right entity -> do
      bounded (prefix++".call") "RIGHT\n"
      encoded<-capture $ do
        let text=encodeEntity entity
        _<-evaluate (length text)
        unless (length text<=16384) (ioError (userError "snapshot file limit"))
        pure text
      case encoded of
        Left ex->do
          let status=probeStatus ex;detail=displayException ex
          bounded (prefix++".encode") (status++"\n"++detail)
          bounded (prefix++".snapshot") "UNAVAILABLE\n"
          pure (Observation "RIGHT" "" status detail Nothing (Just entity))
        Right text->do
          bounded (prefix++".encode") "ENCODED\n"
          bounded (prefix++".snapshot") text
          pure (Observation "RIGHT" "" "ENCODED" "" (Just text) (Just entity))
skipObservation :: String -> IO Observation
skipObservation prefix=do
  bounded (prefix++".call") "SKIP\n"
  bounded (prefix++".encode") "SKIP\n"
  bounded (prefix++".snapshot") "UNAVAILABLE\n"
  pure (Observation "SKIP" "" "SKIP" "" Nothing Nothing)
equalObservation :: Observation -> Observation -> Bool
equalObservation (Observation a b c d e _) (Observation f g h i j _)=(a,b,c,d,e)==(f,g,h,i,j)
completeObservation :: Observation -> Bool
completeObservation (Observation "RIGHT" "" "ENCODED" "" (Just _) _)=True
completeObservation _=False
callStatus :: Observation -> String
callStatus (Observation x _ _ _ _ _)=x
callDetail :: Observation -> String
callDetail (Observation _ x _ _ _ _)=x
encoderIsNameProbe :: Observation -> Bool
encoderIsNameProbe (Observation "RIGHT" "" "PROBE" "NameProbe" Nothing _)=True
encoderIsNameProbe _=False

-- Complete physical maps/sets, not toList views. Encoding is a separate
-- post-call observation and may throw on opaque payloads in successful graphs.
encMap :: (a->String) -> T.IntMap a -> String
encMap encode (T.IntMap tree)="IntMap("++go tree++")"
  where
    go T.IntMapNil="Nil"
    go (T.IntMapTip k v)="Tip("++show k++","++encode v++")"
    go (T.IntMapBin c p l r)="Bin("++show c++","++show p++","++go l++","++go r++")"
encSet :: T.IntSet -> String
encSet (T.IntSet tree)="IntSet("++go tree++")"
  where
    go T.IntSetNil="Nil"
    go (T.IntSetTip a b c)="Tip("++show a++","++show b++","++show c++")"
    go (T.IntSetBin a b l r)="Bin("++show a++","++show b++","++go l++","++go r++")"
encKind :: T.Kind -> String
encKind T.Star="Star"
encKind (T.KArrow a b)="KArrow("++encKind a++","++encKind b++")"
encParent :: T.Maybe P.Int -> String
encParent T.Nothing="Nothing"
encParent (T.Just n)="Just("++show n++")"
encFlag :: T.Flag -> String
encFlag T.Flexible="Flexible"
encFlag T.Rigid="Rigid"
encTag :: T.GTag -> String
encTag T.GBot="Bot"
encTag (T.GBotK k)="BotK("++encKind k++")"
encTag (T.GArr a b)="Arr("++show a++","++show b++")"
encTag (T.GCon n xs)="Con("++show (P.textToChars n)++","++show xs++")"
encTag (T.GTyCon n k)="TyCon("++show (P.textToChars n)++","++encKind k++")"
encTag (T.GSkolem n k)="Skolem("++show n++","++encKind k++")"
encTag (T.GTyApp a b)="TyApp("++show a++","++show b++")"
encTag (T.GGen n)="Gen("++show n++")"
encNode :: T.Node -> String
encNode (T.Node t b f)="Node("++encTag t++","++encParent b++","++encFlag f++")"
encGraph :: T.Graph -> String
encGraph (T.Graph ns ls next)="Graph("++encMap encNode ns++","++encMap show ls++","++show next++")"
encodeEntity :: Entity -> String
encodeEntity (GraphEntity g)=encGraph g++"\n"
encodeEntity (SolverEntity (T.Solver g ps bs (T.ScopeIndex intervals jumps)))=
  "Solver("++encGraph g++","++encMap encSet ps++","++encMap encSet bs++",ScopeIndex("
  ++encMap show intervals++",["++join (map (encMap show) jumps)++"]))\n"
  where join []="";join [x]=x;join (x:xs)=x++","++join xs

trialOp :: Trace -> [(P.Int,P.Int)] -> T.Graph -> IO (T.Either P.String T.Graph)
trialOp trace equations graph=do
  observed<-evaluate (C.trialUnify equations graph)
  case observed of
    C.TrialObservation route err result->do
      writeIORef trace (Just (route,err))
      pure result
routeName :: C.TrialRoute -> String
routeName C.TrialAccepted="ACCEPT"
routeName C.TrialCertificateRejected="CERT_REJECT"
routeName C.TrialPostRejected="POST_REJECT"
routeName C.TrialSparse="SPARSE"
routeName C.TrialPrecheck="PRECHECK"

-- Real prepared expansion/projection and untouched hidden-scope/restore calls.
-- The separate O lane calls the original full instantiateExpandedPrepared.
preparedCall :: ([(P.Int,P.Int)]->T.Graph->IO (T.Either P.String T.Graph)) -> T.Graph -> IO Entity
preparedCall operation input=do
  solver<-requireE (S.prepare input)
  (root,_,frontier,current)<-requireE (S.expandedGraphPrepared 6 2 solver)
  _<-evaluate (G.strictGraph current)
  let first=G.nextId (S.graph solver)
      fresh=S.allocatedNodes first (G.nextId current) (G.nodes current)
      target=G.resolve current 2
  unless (S.fallbackStageEligible first root target frontier current)
    (ioError (userError "fixture: prepared eligibility false"))
  _<-evaluate (S.forceExpansionEdges fresh)
  unless (S.fallbackPrefixRejected current first (IM.fromList [(proxy,old) | (old,proxy)<-frontier]) [(root,target)])
    (ioError (userError "fixture: prefix not rejected"))
  let canonical=[(G.resolve current a,G.resolve current b) | (a,b)<-frontier++[(root,2)]]
      pending=filter (\(a,b)->a/=b) canonical
  _<-requireE (G.mapE_ (\n->G.check (IM.member n (G.nodes current)) ("missing graph node " P.++ P.showInt n)) (L.concatMap G.equationNodes canonical))
  unless (not (null pending)) (ioError (userError "fixture: no pending equations"))
  (local,eqs,originals,(forward,scopes,stubs))<-requireE (S.preparedFallbackProjection solver current first fresh pending)
  unless (any (\(n,_)->n==3) originals) (ioError (userError "fixture: nonlocal node 3 absent"))
  solved<-operation eqs local >>= requireE
  _<-requireE (G.mapE_ (\stub->G.check
    (S.matchesNode (G.nodes solved) stub (G.nodeAt local stub) && G.resolve solved stub==stub)
    "local unification changed a hidden scope root") (IM.elems stubs))
  _<-requireE (G.mapE_ (S.checkPreservedScope current solved forward scopes) originals)
  restored<-requireE (S.restoreExpandedProjection solver current first originals forward (L.length originals) solved)
  pure (SolverEntity restored)

node :: T.GTag -> P.Int -> T.Node
node t p=T.Node t (T.Just p) T.Flexible
mk :: [(P.Int,T.Node)] -> P.Int -> T.Graph
mk ns next=T.Graph (G.nodesFromList ns) IM.empty next
{-# NOINLINE preparedInput #-}
preparedInput :: Int -> T.Graph
preparedInput variant=mk
  [(0,T.Node (T.GGen 1) T.Nothing T.Flexible)
  ,(1,node (T.GArr 2 3) 0),(2,node (T.GArr 4 5) 0)
  ,(3,node (T.GTyCon (if variant==0 then "Sibling" else throw NameProbe) T.Star) 0)
  ,(4,node T.GBot 0),(5,node (if variant==2 then T.GTyCon "Old" T.Star else T.GBot) 0)
  ,(6,node (T.GGen 7) 0),(7,node (T.GArr 8 9) 6),(8,node (T.GArr 10 11) 6)
  ,(9,node (if variant==2 then T.GTyCon "New" T.Star else T.GBot) 6)
  ,(10,node T.GBot 6),(11,node T.GBot 6)] 12
multi :: T.Graph
multi=mk [(0,T.Node (T.GGen 1) T.Nothing T.Flexible),(1,node (T.GArr 2 3) 0)
  ,(2,node T.GBot 0),(3,node T.GBot 0),(4,node (T.GGen 5) 0)
  ,(5,node (T.GArr 6 7) 4),(6,node T.GBot 4),(7,node T.GBot 4)] 8
rename :: (P.Int->P.Int) -> P.Int -> T.Graph -> T.Graph
rename f next g=T.Graph (G.nodesFromList
  [(f i,T.Node (G.mapTag f (G.tag v)) (G.mapMaybeInt f (G.binder v)) (G.flag v)) | (i,v)<-IM.toList (G.nodes g)])
  (IM.fromList [(f a,f b) | (a,b)<-IM.toList (G.links g)]) next
cycleInput :: T.Graph
cycleInput=mk [(0,T.Node (T.GGen 1) T.Nothing T.Flexible),(1,node (T.GArr 2 3) 0),(2,node T.GBot 0),(3,node T.GBot 0)] 4
rigidInput :: T.Graph
rigidInput=T.Graph (G.insertNodeMap 2 (T.Node T.GBot (T.Just 0) T.Rigid) (G.nodes multi)) IM.empty 8
aliasInput :: T.Graph
aliasInput=T.Graph (G.nodes multi) (IM.fromList [(8,2)]) 9
appInput :: T.Graph
appInput=mk [(0,T.Node (T.GGen 1) T.Nothing T.Flexible),(1,node (T.GTyApp 2 3) 0)
  ,(2,node (T.GTyCon "F" (T.KArrow T.Star T.Star)) 0),(3,node T.GBot 0),(4,node T.GBot 0)] 5
dispatchInput :: T.Graph
dispatchInput=mk ([(0,T.Node (T.GGen 1) T.Nothing T.Flexible)]
  ++[(i,node T.GBot 0) | i<-[1..25]]
  ++[(26,node (T.GTyCon (throw NameProbe) (throw KindProbe)) 0)]) 27
cases :: [Case]
cases=
  [Case "prepared-total" ([],preparedInput 0) True "ACCEPT"
  ,Case "prepared-name" ([],preparedInput 1) True "ACCEPT"
  ,Case "prepared-mismatch" ([],preparedInput 2) True "PRECHECK"
  ,Case "signed-gen" ([(-2,-1),(2,3)],rename (\i->i-4) 4 multi) False "ACCEPT"
  ,Case "cycle" ([(1,2)],cycleInput) False "POST_REJECT"
  ,Case "cross-gen" ([(2,6)],multi) False "CERT_REJECT"
  ,Case "rigid" ([(2,3)],rigidInput) False "CERT_REJECT"
  ,Case "sparse" ([(200,300)],rename (\i->i*100) 701 multi) False "SPARSE"
  ,Case "aliases" ([(2,3)],aliasInput) False "CERT_REJECT"
  ,Case "tyapp" ([(3,4)],appInput) False "CERT_REJECT"
  ,Case "dispatch-poison" ([(1,i) | i<-[2..25]],dispatchInput) False "ACCEPT"]

recordPost :: FilePath -> Maybe (C.TrialRoute,T.Maybe P.String) -> IO ()
recordPost path Nothing=bounded path "UNAVAILABLE\n"
recordPost path (Just (_,T.Nothing))=bounded path "NONE\n"
recordPost path (Just (_,T.Just err))=do
  (status,detail)<-renderLeft err
  bounded path ((if status=="LEFT" then "TEXT" else status)++"\n"++detail)

runCase :: Case -> IO (Bool,Bool,Bool)
runCase (Case name (equations,input) prepared expectedRoute)=do
  trace<-newIORef Nothing
  let actionA=if prepared then preparedCall (\es g->pure (G.unify es g)) input
              else GraphEntity <$> requireE (G.unify equations input)
      actionB=if prepared then preparedCall (trialOp trace) input
              else GraphEntity <$> (trialOp trace equations input >>= requireE)
  a<-observe (name++".A") actionA
  b<-observe (name++".B") actionB
  original<-if prepared
    then observe (name++".O") (SolverEntity <$> requireE (G.bindE (S.prepare input) (S.instantiateExpandedPrepared 6 2)))
    else skipObservation (name++".O")
  recorded<-readIORef trace
  let route=maybe "UNAVAILABLE" (routeName.fst) recorded
  bounded (name++".B.route") (route++"\n")
  -- Only now, after A/B/O call+encoding outcomes are fixed, render trial Left.
  recordPost (name++".B.post-error") recorded
  let same=equalObservation a b && (not prepared || equalObservation a original)
      fully=same && completeObservation a && completeObservation b
      demandOnly=same && not fully
      dispatchOK=if name/="dispatch-poison" then True else
        case b of
          Observation "RIGHT" "" _ _ _ (Just (GraphEntity actual)) ->
            case (G.denseBounds input,G.denseBounds actual) of
              (T.Just _,T.Nothing) -> IM.keys (G.nodes actual)==[0,1,26] && G.nextId actual==27
              _ -> False
          _ -> False
      expectedOutcome=case name of
        "prepared-total" -> fully
        "signed-gen" -> fully
        "cycle" -> callStatus a=="LEFT"
        "prepared-mismatch" -> callStatus a=="LEFT"
        "prepared-name" -> callStatus a=="PROBE" && callDetail a=="NameProbe"
        "dispatch-poison" -> encoderIsNameProbe a && encoderIsNameProbe b
        _ -> completeObservation a || callStatus a=="LEFT"
      coverage=route==expectedRoute && dispatchOK && expectedOutcome
      result=if not same then "DIFFERENT" else if fully then "MATCH_COMPLETE" else "MATCH_DEMAND_ONLY"
  bounded (name++".compare") (result++"\n"++if coverage then "COVERAGE_PASS\n" else "COVERAGE_FAIL\n")
  appendFile "summary.tsv" (name++"\t"++result++"\t"++route++"\t"++(if coverage then "PASS" else "FAIL")++"\n")
  pure (same && coverage,fully,demandOnly)
main :: IO ()
main=do
  bounded "summary.tsv" "case\tcomparison\troute\tcoverage\n"
  results<-mapM runCase cases
  let qualified=all (\(ok,_,_)->ok) results
      completeCount=length [() | (_,True,_)<-results]
      demandCount=length [() | (_,_,True)<-results]
  bounded "qualification.txt" ((if qualified then "QUALIFIED_FINITE_ONLY" else "UNQUALIFIED")
    ++"\ncomplete_equal="++show completeCount++"\ndemand_only_equal="++show demandCount++"\n")
  bounded "complete.txt" "COMPLETE\n"
  putStrLn "COMPLETE class-gen validator demand comparison; inspect qualification"
