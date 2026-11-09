{-# OPTIONS_GHC -O0 #-}
module CurrentC4TransactionOracle where
import Prelude
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
import qualified Bootstrap.Graph as G
import qualified FrozenGraph as FG
import qualified FrozenSolver as FS
import qualified SessionOracle as O

-- Only the two reverse maps and their bucket trees may rebalance differently.
-- Every graph Node, alias tree, counter, and scope-index tree remains physical.
sameTransactional :: T.Solver -> T.Solver -> Bool
sameTransactional (T.Solver g p b s) (T.Solver h q c t) =
  O.sameGraphPhysical g h && O.sameScopesPhysical s t &&
  O.sameMapLogical O.sameSetLogical p q && O.sameMapLogical O.sameSetLogical b c

checkOne :: String -> T.Solver -> IO ()
checkOne label value@(T.Solver graph@(T.Graph ns _ _) parents bindings _) = do
  O.assert (label ++ " independently valid BST/size/balance/nonempty buckets") (O.validSolverMaps value)
  let nodes = O.mapEntries ns
  O.assert (label ++ " independent complete structural edge enumeration")
    (O.indexEntries parents == O.indexOracle [(child,n) | (n,node) <- nodes, child <- O.nodeChildren node])
  O.assert (label ++ " independent complete binding edge enumeration")
    (O.indexEntries bindings == O.indexOracle [(parent,n) | (n,node) <- nodes, parent <- O.nodeBinder node])
  _ <- O.right (label ++ " frozen validation") (FG.validateGraph graph)
  _ <- O.right (label ++ " unchanged public validation") (G.validateGraph graph)
  checked <- O.right (label ++ " full frozen finish") (FS.finish value)
  O.assert (label ++ " finish did not rewrite graph") (O.sameGraphPhysical graph checked)

checkTransactional :: String -> T.Solver -> T.Solver -> IO ()
checkTransactional label old new = do
  O.assert (label ++ " exact graph/aliases/counter/scopes plus complete ordered reverse-edge sets")
    (sameTransactional old new)
  checkOne (label ++ " frozen") old
  checkOne (label ++ " candidate") new

checkTransactionalOutcome :: String -> T.Either B.String T.Solver -> T.Either B.String T.Solver -> IO ()
checkTransactionalOutcome label expected actual = case (expected,actual) of
  (T.Left a,T.Left b) -> O.assert (label ++ " exact first diagnostic") (B.v_eqString a b)
  (T.Right a,T.Right b) -> checkTransactional label a b
  (T.Left e,T.Right _) -> errorWithoutStackTrace (label ++ " accepted frozen rejection: " ++ B.unpack e)
  (T.Right _,T.Left e) -> errorWithoutStackTrace (label ++ " rejected frozen success: " ++ B.unpack e)
