{-# LANGUAGE OverloadedStrings #-}
-- Authored against f9bdb40a659bfdff4cbb782d438afbb0417dd2e1.
-- Source-only preparation: this fixture has not been compiled or executed.
module Main where

import Prelude
import Control.Exception
  (Exception, SomeException, SomeAsyncException, evaluate, fromException,
   throw, throwIO, tryJust)
import Control.Monad (unless)
import System.Exit (exitFailure)
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.Graph as G

type I = P.Int

-- Total finite observations serialize every logical node field, ordered alias
-- entry and fresh counter. No digest, lossy pretty-printer or kind-only oracle.
data KindView = StarV | ArrowV KindView KindView deriving (Eq, Show)
data TagView = BotV | BotKV KindView | ArrV I I | ConV String [I]
             | TyConV String KindView | SkolemV I KindView
             | AppV I I | GenV I deriving (Eq, Show)
data FlagView = FlexibleV | RigidV deriving (Eq, Show)
data NodeView = NodeV TagView (Maybe I) FlagView deriving (Eq, Show)
data GraphView = GraphV [(I, NodeView)] [(I, I)] I deriving (Eq, Show)

kindView :: T.Kind -> KindView
kindView T.Star = StarV
kindView (T.KArrow a b) = ArrowV (kindView a) (kindView b)
tagView :: T.GTag -> TagView
tagView t = case t of
  T.GBot -> BotV
  T.GBotK k -> BotKV (kindView k)
  T.GArr a b -> ArrV a b
  T.GCon name args -> ConV (B.unpack name) args
  T.GTyCon name k -> TyConV (B.unpack name) (kindView k)
  T.GSkolem n k -> SkolemV n (kindView k)
  T.GTyApp f a -> AppV f a
  T.GGen n -> GenV n
nodeView :: T.Node -> NodeView
nodeView (T.Node t b f) = NodeV (tagView t)
  (case b of T.Nothing -> Nothing; T.Just n -> Just n)
  (case f of T.Flexible -> FlexibleV; T.Rigid -> RigidV)
graphView :: T.Graph -> GraphView
graphView (T.Graph ns aliases fresh) = GraphV
  [(n, nodeView value) | (n, value) <- IM.toList ns] (IM.toList aliases) fresh

data Sentinel = Sentinel String deriving Show
instance Exception Sentinel
data FixtureFailure = FixtureFailure String deriving Show
instance Exception FixtureFailure

-- Do not swallow async cancellation or claim an async-timing equivalence test.
trySync :: IO a -> IO (Either SomeException a)
trySync = tryJust synchronous
  where synchronous e = case (fromException e :: Maybe SomeAsyncException) of
          Just _ -> Nothing
          Nothing -> Just e

forceString :: String -> ()
forceString [] = ()
forceString (x:xs) = x `seq` forceString xs
forced :: String -> IO String
forced text = evaluate (forceString text) >> pure text
need :: Bool -> String -> IO ()
need okay detail = unless okay (throwIO (FixtureFailure detail))

inRoute :: Bool -> T.Graph -> IO String -> IO String
inRoute dense input action = do
  let actual = case G.denseBounds input of T.Nothing -> False; T.Just _ -> True
  need (actual == dense) "authored dense/sparse precondition changed"
  text <- action
  pure ((if dense then "route=dense;" else "route=sparse;") ++ text)

expectRight :: [(I,I)] -> T.Graph -> T.Graph -> IO String
expectRight equations input expected = case G.unify equations input of
  T.Left message -> throwIO (FixtureFailure ("unexpected Left " ++ B.unpack message))
  T.Right actual -> do
    actualText <- forced (show (graphView actual))
    expectedText <- forced (show (graphView expected))
    need (actualText == expectedText)
      ("expected Right " ++ expectedText ++ "; actual Right " ++ actualText)
    pure ("Right " ++ actualText)

expectLeft :: [(I,I)] -> T.Graph -> String -> IO String
expectLeft equations input expected = case G.unify equations input of
  T.Left message -> do
    actual <- forced (B.unpack message)
    need (actual == expected) ("expected Left " ++ show expected ++ "; actual Left " ++ show actual)
    pure ("Left " ++ show actual)
  T.Right actual -> do
    text <- forced (show (graphView actual))
    throwIO (FixtureFailure ("expected Left " ++ show expected ++ "; actual Right " ++ text))

expectSentinel :: String -> IO a -> IO ()
expectSentinel wanted action = do
  answer <- trySync action
  case answer of
    Right _ -> throwIO (FixtureFailure ("expected Sentinel " ++ wanted))
    Left e -> case (fromException e :: Maybe Sentinel) of
      Just (Sentinel actual) -> need (actual == wanted) "wrong Sentinel"
      Nothing -> throwIO e

graph :: [(I,T.Node)] -> [(I,I)] -> I -> T.Graph
graph ns aliases fresh = T.Graph (IM.fromList ns) (IM.fromList aliases) fresh
root :: I -> T.Node
root child = T.Node (T.GGen child) T.Nothing T.Flexible
flex :: I -> T.GTag -> T.Node
flex parent tag = T.Node tag (T.Just parent) T.Flexible
simple :: I -> I -> I -> I -> T.Graph
simple r b c fresh = graph [(r,root b),(b,flex r T.GBot),(c,flex r (T.GCon "Int" []))] [] fresh
merged :: I -> I -> I -> I -> T.Graph
merged r b c fresh = graph [(r,root b),(b,flex r (T.GCon "Int" []))] [(c,b)] fresh

base :: T.Graph
base = simple 0 1 2 3
mismatch :: T.Graph
mismatch = graph [(0,root 1),(1,flex 0 (T.GCon "Int" [])),(2,flex 0 (T.GCon "Bool" []))] [] 3
aliasBase :: T.Graph
aliasBase = graph [(0,root 10),(1,flex 0 T.GBot),(2,flex 0 (T.GCon "Int" []))] [(10,1)] 11
aliasMismatch :: T.Graph
aliasMismatch = graph [(0,root 10),(1,flex 0 (T.GCon "Int" [])),(2,flex 0 (T.GCon "Bool" []))] [(10,1)] 11
higherNodes :: [(I,T.Node)]
higherNodes = [(0,root 3),(1,flex 0 (T.GTyCon "F" (T.KArrow T.Star T.Star))),
               (2,flex 0 (T.GCon "Int" [])),(3,flex 0 (T.GTyApp 1 2))]
higher :: T.Graph
higher = graph (higherNodes ++ [(4,flex 0 T.GBot)]) [] 5
missingBinder :: T.Graph
missingBinder = graph [(0,root 1),(1,flex 99 T.GBot)] [] 2
badKindAndBinder :: I -> I -> I -> I -> I -> T.Graph
badKindAndBinder r a f missing fresh = graph
  [(r,root a),(a,flex r (T.GArr f f)),
   (f,flex missing (T.GTyCon "F" (T.KArrow T.Star T.Star)))] [] fresh
minIdentity, maxIdentity :: I
minIdentity = -9223372036854775808
maxIdentity = 9223372036854775807

poisonEquations :: [(I,I)]
poisonEquations = throw (Sentinel "equations")

unusedNameDemand :: IO String
unusedNameDemand = do
  let input = graph [(0,root 1),(1,flex 0 (T.GCon (throw (Sentinel "unused-name")) []))] [] 2
      answer = G.unify [] input
  -- The order here is intentional. Do not serialize the graph before the
  -- constructor/WHNF/counter observations, or poison the observation itself.
  whnf <- evaluate answer
  case whnf of
    T.Left _ -> throwIO (FixtureFailure "unused-name case rejected before full observation")
    T.Right result -> do
      _ <- evaluate result
      n <- evaluate (G.nextId result)
      need (n == 2) "unused-name fresh counter changed"
      expectSentinel "unused-name" (forced (show (graphView result)))
      pure "Either=Right;Graph=WHNF;nextId=2;full-view=Sentinel unused-name"

cases :: [(String, IO String)]
cases =
  [ ("dense-empty", inRoute True base (expectRight [] base base))
  , ("dense-self", expectRight [(1,1)] base base)
  , ("dense-merge", expectRight [(1,2)] base (merged 0 1 2 3))
  , ("signed-dense-merge", inRoute True (simple (-3) (-2) (-1) 0)
      (expectRight [(-2,-1)] (simple (-3) (-2) (-1) 0) (merged (-3) (-2) (-1) 0)))
  , ("sparse-merge", inRoute False (simple 0 100 10000 10001)
      (expectRight [(100,10000)] (simple 0 100 10000 10001) (merged 0 100 10000 10001)))
  , ("extreme-span-merge", inRoute False (simple minIdentity 0 maxIdentity maxIdentity)
      (expectRight [(0,maxIdentity)] (simple minIdentity 0 maxIdentity maxIdentity)
       (merged minIdentity 0 maxIdentity maxIdentity)))
  , ("alias-empty-canonicalization", expectRight [] aliasBase
      (graph [(0,root 1),(1,flex 0 T.GBot),(2,flex 0 (T.GCon "Int" []))] [(10,1)] 11))
  , ("alias-merge", expectRight [(10,2)] aliasBase
      (graph [(0,root 1),(1,flex 0 (T.GCon "Int" []))] [(2,1),(10,1)] 11))
  , ("higher-app-merge", expectRight [(3,4)] higher (graph higherNodes [(4,3)] 5))
  , ("higher-kind-mismatch", expectLeft [(1,2)] higher
      "kind mismatch during unification: KArrow Star Star versus Star")
  , ("dense-constructor-mismatch", expectLeft [(1,2)] mismatch
      "type constructor mismatch: Con \"Int\" [] versus Con \"Bool\" []")
  , ("late-endpoint-fast-priority", expectLeft [(1,2),(99,1)] mismatch "missing graph node 99")
  , ("late-endpoint-alias-priority", expectLeft [(10,2),(99,10)] aliasMismatch "missing graph node 99")
  , ("rigid-bottom-rejection", expectLeft [(1,2)]
      (graph [(0,root 1),(1,T.Node T.GBot (T.Just 0) T.Rigid),(2,flex 0 (T.GCon "Int" []))] [] 3)
      "cannot instantiate a rigid or protected type variable")
  , ("disconnected-binding-cycle", expectLeft []
      (graph [(0,root 1),(1,flex 0 T.GBot),(2,flex 3 T.GBot),(3,flex 2 T.GBot)] [] 4)
      "cyclic binding tree")
  , ("structural-occurs-cycle", expectLeft []
      (graph [(0,root 1),(1,flex 0 (T.GArr 1 1))] [] 2) "infinite type (occurs check)")
  , ("non-gen-binding-root", expectLeft []
      (graph [(0,T.Node (T.GCon "Unit" []) T.Nothing T.Flexible)] [] 1) "binding root must be a gen node")
  , ("dense-binder-before-kind", expectLeft [] (badKindAndBinder 0 1 2 99 3) "missing binder")
  , ("sparse-kind-before-binder", expectLeft [] (badKindAndBinder 0 10 100 999 101)
      "function types require kind * arguments")
  , ("invalid-application-arity", expectLeft []
      (graph [(0,root 3),(1,flex 0 (T.GTyCon "F" T.Star)),
              (2,flex 0 (T.GCon "Int" [])),(3,flex 0 (T.GTyApp 1 2))] [] 4)
      "invalid type constructor arity: a type of kind * cannot be applied")
  , ("invalid-input-before-poison-equations", expectLeft poisonEquations missingBinder "missing binder")
  , ("valid-input-demands-poison-equations", do
      expectSentinel "equations" (evaluate (G.unify poisonEquations base))
      pure "Either-WHNF=Sentinel equations")
  , ("unused-name-demand-boundaries", unusedNameDemand)
  ]

failureText :: SomeException -> String
failureText e = case (fromException e :: Maybe FixtureFailure) of
  Just (FixtureFailure detail) -> detail
  Nothing -> case (fromException e :: Maybe Sentinel) of
    Just (Sentinel name) -> "unexpected Sentinel " ++ name
    Nothing -> "unexpected synchronous exception"

runCase :: (String, IO String) -> IO Bool
runCase (name, action) = do
  -- Include complete lazy payload rendering in the same exception boundary.
  -- This forces observations only after the case has performed its ordered
  -- probes. It does not force the production graph before those probes.
  observed <- trySync (action >>= forced . show)
  case observed of
    Right payload -> putStrLn ("PASS\t" ++ name ++ "\t" ++ payload) >> pure True
    Left e -> do
      detail <- trySync (forced (show (failureText e)))
      let payload = case detail of Right text -> text; Left _ -> show ("unrenderable failure" :: String)
      putStrLn ("FAIL\t" ++ name ++ "\t" ++ payload)
      pure False

main :: IO ()
main = do
  passed <- mapM runCase cases
  let count = length cases
      successes = length (filter id passed)
  putStrLn ("SUMMARY\t" ++ show count ++ "\t" ++ show successes)
  unless (successes == count) exitFailure
