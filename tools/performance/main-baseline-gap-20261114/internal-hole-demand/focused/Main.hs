{-# LANGUAGE OverloadedStrings, DeriveDataTypeable #-}
{-# OPTIONS_GHC -fno-cse -fno-full-laziness #-}
module Main where
import Prelude
import Control.Exception (Exception,SomeException,throw,try,evaluate,fromException,displayException)
import Control.Monad (unless)
import Data.Typeable (Typeable)
import System.Directory (doesFileExist)
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as L
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S

data Probe = Probe deriving (Show,Typeable)
instance Exception Probe
data Variant = Total | NameProbe | Mismatch deriving (Eq)

-- No graph or solver fields are changed after prepare. The source Gen is a
-- separate closed binding region; node 3 is outside the target's subtree.
{-# NOINLINE input #-}
input :: Variant -> T.Graph
input variant = T.Graph (G.nodesFromList
  [(0,T.Node (T.GGen 1) T.Nothing T.Flexible)
  ,(1,n (T.GArr 2 3) 0),(2,n (T.GArr 4 5) 0)
  ,(3,n (T.GTyCon sibling T.Star) 0),(4,n T.GBot 0)
  ,(5,n (if variant==Mismatch then T.GTyCon "Old" T.Star else T.GBot) 0)
  ,(6,n (T.GGen 7) 0),(7,n (T.GArr 8 9) 6),(8,n (T.GArr 10 11) 6)
  ,(9,n (if variant==Mismatch then T.GTyCon "New" T.Star else T.GBot) 6)
  ,(10,n T.GBot 6),(11,n T.GBot 6)]) IM.empty 12
  where
    n t b = T.Node t (T.Just b) T.Flexible
    sibling = if variant==Total then "Sibling" else throw Probe

capture :: IO a -> IO (Either SomeException a)
capture = try
bounded :: FilePath -> String -> IO ()
bounded path bytes = do
  -- At most 16,384 Unicode characters, hence at most 65,536 UTF-8 bytes.
  unless (length bytes <= 16384) (ioError (userError "diagnostic file limit"))
  writeFile path bytes
ensureFile :: FilePath -> String -> IO ()
ensureFile path bytes = do
  present <- doesFileExist path
  unless present (bounded path bytes)
event :: String -> String -> String -> String -> IO ()
event name phase status err = do
  bounded (name++"."++phase++".error") err
  appendFile "events.tsv" (name++"\t"++phase++"\t"++status++"\n")
skip :: String -> String -> IO (Maybe a)
skip name phase = event name phase "SKIP" "" >> pure Nothing
phase :: String -> String -> T.Either P.String a -> (a -> IO ()) -> IO (Maybe a)
phase name label expression force = do
  result <- capture $ case expression of
    T.Left err -> pure (Left err)
    T.Right value -> force value >> pure (Right value)
  case result of
    Left ex -> do
      let status=case fromException ex :: Maybe Probe of
            Just Probe -> "PROBE"
            Nothing -> "OTHER"
      event name label status (displayException ex)
      pure Nothing
    Right (Left err) -> do
      -- Rendering the lazy Left text is a separate collector boundary.
      rendered <- capture $ do
        let chars=P.textToChars err
        _ <- evaluate (length chars)
        pure chars
      case rendered of
        Right chars -> event name label "LEFT" chars
        Left ex -> do
          let status=case fromException ex :: Maybe Probe of
                Just Probe -> "LEFT_TEXT_PROBE"
                Nothing -> "LEFT_TEXT_OTHER"
          event name label status (displayException ex)
      pure Nothing
    Right (Right value) -> event name label "OK" "" >> pure (Just value)
after :: String -> String -> Maybe a -> (a -> T.Either P.String b) -> (b -> IO ()) -> IO (Maybe b)
after name label previous action force = case previous of
  Nothing -> skip name label
  Just value -> phase name label (action value) force
forceGraph :: T.Graph -> IO ()
forceGraph g = evaluate (G.strictGraph g) >> pure ()
forceSolver :: T.Solver -> IO ()
forceSolver s = forceGraph (S.graph s)
forceUnit :: () -> IO ()
forceUnit unit = evaluate unit >> pure ()

-- Snapshot only total successful results, never a Probe graph. This adds
-- observation demands after the measured semantic stages, not inside them.
snapshot :: T.Solver -> String
snapshot s = unlines
  ( ["next\t"++show (G.nextId g)]
  ++ ["node\t"++show i++"\t"++P.textToChars (G.tagDescription (G.tag v))
      ++"\t"++parent (G.binder v)++"\t"++flag (G.flag v) | (i,v)<-IM.toList (G.nodes g)]
  ++ ["alias\t"++show a++"\t"++show b | (a,b)<-IM.toList (G.links g)]
  ++ ["structural-parents\t"++show a++"\t"++show (IS.toList b) | (a,b)<-IM.toList (S.structuralParents s)]
  ++ ["binding-children\t"++show a++"\t"++show (IS.toList b) | (a,b)<-IM.toList (S.bindingChildren s)])
  where
    g=S.graph s
    parent T.Nothing="Nothing"
    parent (T.Just n)="Just "++show n
    flag T.Flexible="Flexible"
    flag T.Rigid="Rigid"

runCase :: String -> Variant -> IO Bool
runCase name variant = do
  prepared <- phase name "prepare" (S.prepare (input variant)) forceSolver
  expanded <- after name "expand" prepared
    (\s -> G.bindE (S.expandedGraphPrepared 6 2 s) (\e -> T.Right (s,e)))
    (\(_,(_,_,_,g)) -> forceGraph g)
  routed <- after name "prefix" expanded T.Right
    (\(s,(root,copies,frontier,g)) -> do
      let first=G.nextId (S.graph s)
          target=G.resolve g 2
          eligible=S.fallbackStageEligible first root target frontier g
          rejected=S.fallbackPrefixRejected g first (IM.fromList [(proxy,original) | (original,proxy)<-frontier]) [(root,target)]
      unless eligible (ioError (userError "fixture does not enter prepared fallback"))
      _ <- evaluate (S.forceExpansionEdges (S.allocatedNodes first (G.nextId g) (G.nodes g)))
      unless rejected (ioError (userError "fixture does not enter prepared fallback"))
      bounded (name++".copies") (show (IM.toList copies)++"\n"++show frontier++"\n"++show root++"\n"))
  case routed of
    Nothing -> ensureFile (name++".copies") "not_reached\n"
    Just _ -> pure ()
  projected <- after name "project" routed
    (\ctx@(s,(root,_,frontier,g)) ->
      let canonical=[(G.resolve g a,G.resolve g b) | (a,b)<-frontier++[(root,2)]]
          pending=filter (\(a,b)->a/=b) canonical
      in G.bindE (G.mapE_ (\n -> G.check (IM.member n (G.nodes g))
            ("missing graph node " P.++ P.showInt n))
            (L.concatMap G.equationNodes canonical)) (\_ ->
          case pending of
            [] -> T.Left "fixture: unexpectedly empty pending equations"
            _ -> G.bindE (S.preparedFallbackProjection s g (G.nextId (S.graph s))
              (S.allocatedNodes (G.nextId (S.graph s)) (G.nextId g) (G.nodes g)) pending)
              (\p -> T.Right (ctx,p))))
    (\(_, (local,_,originals,_)) -> do
      forceGraph local
      let selected=any (\(i,_)->i==3) originals
      bounded (name++".selected") (if selected then "node3-present\n" else "node3-absent\n")
      unless selected (ioError (userError "fixture node 3 not selected")))
  case projected of
    Nothing -> ensureFile (name++".selected") "not_completed\n"
    Just _ -> pure ()
  validated <- after name "validate" projected
    (\ctx@(_, (local,_,_,_)) -> G.bindE (G.validateGraph local) (\_ -> T.Right ctx))
    (\_ -> pure ())
  firstOrder <- after name "first-order" validated
    (\ctx@(_, (local,equations,_,_)) -> G.bindE (G.checkedFirstOrder equations local) (\sk -> T.Right (ctx,sk)))
    (\(_,sk) -> forceGraph sk)
  canonical <- after name "canonicalize" firstOrder
    (\(ctx,sk) -> T.Right (ctx,G.canonicalize sk)) (\(_,sk)->forceGraph sk)
  rebound <- after name "rebind" canonical
    (\(ctx@(_, (local,_,_,_)),sk) -> G.bindE (G.rebind local sk) (\rebuilt -> T.Right (ctx,rebuilt)))
    (\(_,g)->forceGraph g)
  postvalid <- after name "post-validate" rebound
    (\answer@(_,g) -> G.bindE (G.validateGraph g) (\_ -> T.Right answer)) (\_ -> pure ())
  checked <- after name "scope-check" postvalid
    (\answer@(((_,(_,_,_,current)),(local,_,originals,(forward,scopes,stubs))),solved) ->
      G.bindE (G.mapE_ (\stub -> G.check
        (S.matchesNode (G.nodes solved) stub (G.nodeAt local stub) && G.resolve solved stub==stub)
        "local unification changed a hidden scope root") (IM.elems stubs))
      (\_ -> G.bindE (G.mapE_ (S.checkPreservedScope current solved forward scopes) originals)
        (\_ -> T.Right answer))) (\_ -> pure ())
  restored <- after name "restore" checked
    (\(((s,(_,_,_,current)),(_,_,originals,(forward,_,_))),solved) ->
      S.restoreExpandedProjection s current (G.nextId (S.graph s)) originals forward (L.length originals) solved)
    forceSolver
  -- A new independent invocation, not resuming any failed staged state.
  full <- phase name "full-call"
    (G.bindE (S.prepare (input variant)) (S.instantiateExpandedPrepared 6 2)) forceSolver
  snap <- case (variant,restored,full) of
    (Total,Just a,Just b) -> phase name "snapshot" (T.Right ()) (\_ -> do
      let left=snapshot a;right=snapshot b
      bounded "total.staged.snapshot" left
      bounded "total.full.snapshot" right
      unless (left==right) (ioError (userError "staged/full total snapshots differ")))
    _ -> skip name "snapshot"
  case (variant,snap) of
    (Total,Just ()) -> pure True
    (Total,Nothing) -> do
      ensureFile "total.staged.snapshot" "unavailable\n"
      ensureFile "total.full.snapshot" "unavailable\n"
      pure False
    _ -> pure False

main :: IO ()
main = do
  bounded "events.tsv" "case\tphase\toutcome\n"
  qualified <- runCase "total" Total
  _ <- runCase "probe" NameProbe
  _ <- runCase "mismatch" Mismatch
  bounded "qualification.txt" (if qualified then "QUALIFIED_TOTAL_CONTROL\n" else "UNQUALIFIED_TOTAL_CONTROL\n")
  bounded "complete.txt" "COMPLETE\n"
  putStrLn "COMPLETE internal-hole demand diagnostic; inspect outcomes"
