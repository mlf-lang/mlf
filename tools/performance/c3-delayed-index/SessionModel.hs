module SessionModel (Action(..), Trace(..), trace, component) where

import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified Bootstrap.Graph.Solver as Solver
import qualified Bootstrap.IntMap as IM
import qualified Bootstrap.IntSet as IS
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as B
import qualified SessionOracle as O

data Action = Instance B.Int B.Int | Equality [(B.Int, B.Int)]
data Trace = Trace [T.Solver] (T.Either B.String T.Solver) (Maybe T.Solver)

-- The immutable public solver supplies the expected graph and diagnostic. Build
-- reverse indexes independently from the edges of the graph that was published.
withIndexes :: T.Graph -> T.Solver -> T.Solver
withIndexes (T.Graph nodes _ _) (T.Solver graph _ _ scopes) =
  T.Solver graph (index O.nodeChildren) (index O.nodeBinder) scopes
  where
    index edges = IM.fromDistinctAscList
      [(key, IS.fromDistinctAscList owners) | (key, owners) <- O.indexOracle
        [(key, owner) | (owner, node) <- O.mapEntries nodes, key <- edges node]]

trace :: T.Solver -> [Action] -> Trace
trace initial = go [] initial
  where
    go saved state actions =
      let snapshots = state : saved
          advance result onFailure rest = case result of
            T.Left message -> Trace (reverse snapshots) (T.Left message) (Just onFailure)
            T.Right next -> go snapshots (withIndexes (Solver.graph next) next) rest
      in case actions of
        [] -> Trace (reverse snapshots) (T.Right state) Nothing
        Equality pairs : rest -> advance (Solver.solverUnify pairs state) state rest
        Instance source target : rest ->
          -- If expansion succeeded before rejection, aliases, counter and scopes
          -- still belong to the old handle. Its store includes the expansion edges.
          let failed = case Solver.expanded source target state of
                T.Left _ -> state
                T.Right (_, _, _, expanded) -> withIndexes (Solver.graph expanded) state
          in advance (Solver.instantiateClosed source target state) failed rest

-- Walk the graph in both directions, stopping at generalization nodes. Build
-- incoming edges by enumeration so this expectation needs no session indexes.
component :: T.Graph -> [B.Int] -> (T.IntMap T.Node, T.IntSet)
component (T.Graph nodes _ _) seeds = visit Set.empty Set.empty seeds
  where
    entries = O.mapEntries nodes
    table = Map.fromList entries
    neighbors node = O.nodeChildren node ++ O.nodeBinder node
    incoming = Map.fromListWith (++)
      [(key, [owner]) | (owner, node) <- entries, key <- neighbors node]
    visit seen scopes [] =
      (IM.fromDistinctAscList [(key, table Map.! key) | key <- Set.toAscList seen],
       IS.fromDistinctAscList (Set.toAscList scopes))
    visit seen scopes (key : rest)
      | Set.member key seen = visit seen scopes rest
      | otherwise = case table Map.! key of
          T.Node (T.GGen _) _ _ -> visit found (Set.insert key scopes) rest
          node -> visit found scopes (neighbors node ++ Map.findWithDefault [] key incoming ++ rest)
      where found = Set.insert key seen
