{-# OPTIONS_GHC -O0 #-}
module SessionOracle where
import Prelude
import Control.Monad (unless)
import Data.List (foldl')
import qualified Data.Map.Strict as HostMap
import qualified Data.Set as HostSet
import qualified MLF.Host.Base as B
import qualified OracleTypes as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.Graph as G
import qualified Bootstrap.Graph.Solver as S
import qualified FrozenGraph as FG
import qualified FrozenSolver as FS

assert :: String -> Bool -> IO ()
assert label condition=unless condition (errorWithoutStackTrace label)
right :: String -> T.Either B.String a -> IO a
right label answer=case answer of T.Left message->error (label++": "++B.unpack message);T.Right value->pure value
sameMaybe :: (a -> b -> Bool) -> T.Maybe a -> T.Maybe b -> Bool
sameMaybe _ T.Nothing T.Nothing=True
sameMaybe equal (T.Just a) (T.Just b)=equal a b
sameMaybe _ _ _=False
sameKind :: T.Kind -> T.Kind -> Bool
sameKind T.Star T.Star=True
sameKind (T.KArrow a b) (T.KArrow c d)=sameKind a c && sameKind b d
sameKind _ _=False
sameFlag :: T.Flag -> T.Flag -> Bool
sameFlag T.Flexible T.Flexible=True
sameFlag T.Rigid T.Rigid=True
sameFlag _ _=False
sameTag :: T.GTag -> T.GTag -> Bool
sameTag T.GBot T.GBot=True
sameTag (T.GBotK a) (T.GBotK b)=sameKind a b
sameTag (T.GArr a b) (T.GArr c d)=a==c && b==d
sameTag (T.GCon n as) (T.GCon m bs)=B.v_eqString n m && as==bs
sameTag (T.GTyCon n k) (T.GTyCon m l)=B.v_eqString n m && sameKind k l
sameTag (T.GSkolem n k) (T.GSkolem m l)=n==m && sameKind k l
sameTag (T.GTyApp a b) (T.GTyApp c d)=a==c && b==d
sameTag (T.GGen a) (T.GGen b)=a==b
sameTag _ _=False
sameNode :: T.Node -> T.Node -> Bool
sameNode (T.Node t b f) (T.Node u c g)=sameTag t u && sameMaybe (==) b c && sameFlag f g
sameList :: (a -> b -> Bool) -> [a] -> [b] -> Bool
sameList _ [] []=True
sameList equal (a:as) (b:bs)=equal a b && sameList equal as bs
sameList _ _ _=False
sameTree :: (a -> b -> Bool) -> T.Map B.Int a -> T.Map B.Int b -> Bool
sameTree _ T.MapEmpty T.MapEmpty=True
sameTree eq (T.MapNode n k v l r) (T.MapNode m j w a b)=
  n==m && k==j && eq v w && sameTree eq l a && sameTree eq r b
sameTree _ _ _=False
entries :: T.Map B.Int a -> [(B.Int,a)]
entries T.MapEmpty=[]
entries (T.MapNode _ key value left right)=entries left++[(key,value)]++entries right
mapEntries :: T.IntMap a -> [(B.Int,a)]
mapEntries=T.mapEntries
setEntries :: T.IntSet -> [B.Int]
setEntries=T.setEntries
sameMapPhysical :: (a -> b -> Bool) -> T.IntMap a -> T.IntMap b -> Bool
sameMapPhysical=T.sameMap
sameMapLogical :: (a -> b -> Bool) -> T.IntMap a -> T.IntMap b -> Bool
sameMapLogical eq a b=sameList (\(k,v) (j,w)->k==j && eq v w) (mapEntries a) (mapEntries b)
sameSetPhysical :: T.IntSet -> T.IntSet -> Bool
sameSetPhysical=T.sameSet
sameSetLogical :: T.IntSet -> T.IntSet -> Bool
sameSetLogical a b=setEntries a==setEntries b
sameScopesPhysical :: T.ScopeIndex -> T.ScopeIndex -> Bool
sameScopesPhysical (T.ScopeIndex a as) (T.ScopeIndex b bs)=
  sameMapPhysical (==) a b && sameList (sameMapPhysical (==)) as bs
sameGraphLogical :: T.Graph -> T.Graph -> Bool
sameGraphLogical (T.Graph a b c) (T.Graph d e f)=
  sameMapLogical sameNode a d && sameMapLogical (==) b e && c==f
sameGraphPhysical :: T.Graph -> T.Graph -> Bool
sameGraphPhysical (T.Graph a b c) (T.Graph d e f)=
  sameMapPhysical sameNode a d && sameMapPhysical (==) b e && c==f
sameSolverLogical :: T.Solver -> T.Solver -> Bool
sameSolverLogical (T.Solver g p b s) (T.Solver h q c t)=sameGraphPhysical g h &&
  sameMapLogical sameSetPhysical p q && sameMapLogical sameSetPhysical b c && sameScopesPhysical s t
sameSolverPhysical :: T.Solver -> T.Solver -> Bool
sameSolverPhysical (T.Solver g p b s) (T.Solver h q c t)=sameGraphPhysical g h &&
  sameMapPhysical sameSetPhysical p q && sameMapPhysical sameSetPhysical b c && sameScopesPhysical s t

cmp :: B.Int -> B.Int -> B.Int
cmp a b=if a<b then -1 else if a>b then 1 else 0
-- Independent exact cached-count/BST/delta3 constructor proof.
validTree :: T.Map B.Int a -> Bool
validTree tree=case go tree of Nothing->False;Just _->True
 where
  go T.MapEmpty=Just(0::B.Int,Nothing,Nothing)
  go(T.MapNode n k _ l r)=k `seq` do
   (lc,lo,lhi)<-go l
   (rc,rlo,hi)<-go r
   if n==1+lc+rc && maybe True(<k)lhi && maybe True(k<)rlo &&
      (lc+rc<=1 || (lc<=3*rc&&rc<=3*lc))
    then Just(1+lc+rc,Just(maybe k id lo),Just(maybe k id hi))
    else Nothing

validMap :: T.IntMap a -> Bool
validMap=T.validMap
validSet :: T.IntSet -> Bool
validSet=T.validSet
validIndex :: T.IntMap T.IntSet -> Bool
validIndex index=validMap index && all (\(_,v)->not(null(setEntries v))&&validSet v) (mapEntries index)
validScopes :: T.ScopeIndex -> Bool
validScopes (T.ScopeIndex intervals jumps)=validMap intervals && all validMap jumps
validSolverMaps :: T.Solver -> Bool
validSolverMaps (T.Solver (T.Graph ns aliases next) p b scopes)=
  validMap ns && validMap aliases && validIndex p && validIndex b && validScopes scopes &&
  all ((<next).fst) (mapEntries ns) && all ((<next).fst) (mapEntries aliases) &&
  all (\(key,values)->key<next && all (<next) (setEntries values)) (mapEntries p++mapEntries b)

-- Independently enumerate graph edges without using candidate Graph.children,
-- index accessors, fromList, or the implementation's validity predicate.
nodeChildren :: T.Node -> [B.Int]
nodeChildren (T.Node tag _ _)=case tag of
  T.GArr a b->[a,b]
  T.GTyApp a b->[a,b]
  T.GGen n->[n]
  T.GCon _ children->children
  _->[]
nodeBinder :: T.Node -> [B.Int]
nodeBinder (T.Node _ T.Nothing _) = []
nodeBinder (T.Node _ (T.Just parent) _) = [parent]
indexOracle :: [(B.Int,B.Int)] -> [(B.Int,[B.Int])]
indexOracle edges=HostMap.toAscList (HostMap.map HostSet.toAscList
  (foldl' (\m (key,value)->HostMap.insertWith HostSet.union key (HostSet.singleton value) m) HostMap.empty edges))
indexEntries :: T.IntMap T.IntSet -> [(B.Int,[B.Int])]
indexEntries index=[(key,setEntries values)|(key,values)<-mapEntries index]

auditLiveScopeState :: String -> T.Solver -> IO ()
auditLiveScopeState label value@(T.Solver graph _ _ _) = do
  checked <- right (label ++ " raw live index audit") (S.finish value)
  assert (label ++ " live finish preserves physical graph") (sameGraphPhysical graph checked)

-- The private openSession fixture hook imports its indexes verbatim. Adapt
-- only the input scope prefix of an independently audited historical state.
-- The live result must still pass its original raw audit after the operation.
compactHistoricalScopeInput :: T.Solver -> Maybe T.Solver
compactHistoricalScopeInput value@(T.Solver graph parents bindings (T.ScopeIndex intervals frozenJumps)) =
  case (FS.finish value, S.indexScopes graph) of
    (T.Right checked, T.ScopeIndex liveIntervals liveJumps)
      | sameGraphPhysical graph checked &&
        sameMapPhysical (==) intervals liveIntervals &&
        length liveJumps <= length frozenJumps &&
        and (zipWith (sameMapPhysical (==)) liveJumps frozenJumps) ->
          let compact = T.Solver graph parents bindings (T.ScopeIndex intervals (take (length liveJumps) frozenJumps))
          in case S.finish compact of
            T.Right admitted | sameGraphPhysical graph admitted -> Just compact
            _ -> Nothing
    _ -> Nothing

liveScopeInput :: T.Solver -> T.Solver
liveScopeInput value = case compactHistoricalScopeInput value of
  Just admitted -> admitted
  Nothing -> errorWithoutStackTrace "historical session input is not a valid live scope prefix"

-- Live indexes retain only the levels required by the scope depth.
-- Audit the raw state and use the frozen solver solely for the omitted tail.
withFrozenScopeTail :: String -> T.Solver -> IO T.Solver
withFrozenScopeTail label value@(T.Solver graph parents bindings (T.ScopeIndex intervals jumps)) =
  case FS.finish value of
    T.Right _ -> pure value
    T.Left _ -> do
      auditLiveScopeState label value
      frozen <- right (label ++ " independent frozen scope reconstruction") (FS.prepare graph)
      case frozen of
        T.Solver _ _ _ (T.ScopeIndex frozenIntervals frozenJumps) -> do
          assert (label ++ " exact frozen intervals") (sameMapPhysical (==) intervals frozenIntervals)
          assert (label ++ " exact retained frozen jump prefix")
            (length jumps < length frozenJumps && and (zipWith (sameMapPhysical (==)) jumps frozenJumps))
          pure (T.Solver graph parents bindings (T.ScopeIndex intervals (jumps ++ drop (length jumps) frozenJumps)))

frozenScopeComparison :: String -> T.Solver -> T.Solver -> IO (T.Solver, T.Solver)
frozenScopeComparison label old@(T.Solver _ _ _ a) new@(T.Solver _ _ _ b)
  | sameScopesPhysical a b = pure (old,new)
  | otherwise = do
      old' <- withFrozenScopeTail (label ++ " reference") old
      new' <- withFrozenScopeTail (label ++ " actual") new
      pure (old',new')

checkSolver :: String -> Bool -> T.Solver -> T.Solver -> IO ()
checkSolver label physical rawOld rawNew=do
  if physical then pure () else auditLiveScopeState label rawNew
  (old,new)<-frozenScopeComparison label rawOld rawNew
  assert (label++" exact nodes aliases indexes scopes and fresh counter")
    ((if physical then sameSolverPhysical else sameSolverLogical) old new)
  if physical then pure () else do
    assert (label++" original all map invariants") (validSolverMaps old)
    assert (label++" batch all map invariants") (validSolverMaps new)
    let T.Solver (T.Graph ns _ _) parents bindings _=new
        nodes=mapEntries ns
    assert (label++" independent structural reverse edges")
      (indexEntries parents==indexOracle [(child,n)|(n,node)<-nodes,child<-nodeChildren node])
    assert (label++" independent binder reverse edges")
      (indexEntries bindings==indexOracle [(parent,n)|(n,node)<-nodes,parent<-nodeBinder node])
    _<-right (label++" frozen graph validation") (FG.validateGraph (S.graph new))
    _<-right (label++" unchanged graph validation") (G.validateGraph (S.graph new))
    forAudit<-withFrozenScopeTail label new
    _<-right (label++" frozen final index audit") (FS.finish forAudit)
    pure ()

checkOutcome :: String -> Bool -> T.Either B.String T.Solver -> T.Either B.String T.Solver -> IO ()
checkOutcome label physical old new=case (old,new) of
  (T.Left a,T.Left b)->assert (label++" exact diagnostic") (B.v_eqString a b)
  (T.Right a,T.Right b)->checkSolver label physical a b
  (T.Left a,T.Right _)->errorWithoutStackTrace (label++" batch accepted original rejection: "++B.unpack a)
  (T.Right _,T.Left b)->errorWithoutStackTrace (label++" batch rejected original success: "++B.unpack b)
