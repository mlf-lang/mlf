{-# OPTIONS_GHC -O0 #-}
module SessionOracle where
import Prelude
import Control.Monad (unless)
import Data.List (foldl')
import qualified Data.Map.Strict as HostMap
import qualified Data.Set as HostSet
import qualified MLF.Host.Base as B
import qualified Bootstrap.Types as T
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
sameTree :: (a -> b -> Bool) -> T.Map Integer a -> T.Map Integer b -> Bool
sameTree _ T.MapEmpty T.MapEmpty=True
sameTree eq (T.MapNode n k v l r) (T.MapNode m j w a b)=
  n==m && k==j && eq v w && sameTree eq l a && sameTree eq r b
sameTree _ _ _=False
entries :: T.Map Integer a -> [(Integer,a)]
entries T.MapEmpty=[]
entries (T.MapNode _ key value left right)=entries left++[(key,value)]++entries right
mapEntries :: T.IntMap a -> [(Integer,a)]
mapEntries (T.IntMap t)=entries t
setEntries :: T.IntSet -> [Integer]
setEntries (T.IntSet t)=map fst (entries t)
sameMapPhysical :: (a -> b -> Bool) -> T.IntMap a -> T.IntMap b -> Bool
sameMapPhysical eq (T.IntMap a) (T.IntMap b)=sameTree eq a b
sameMapLogical :: (a -> b -> Bool) -> T.IntMap a -> T.IntMap b -> Bool
sameMapLogical eq a b=sameList (\(k,v) (j,w)->k==j && eq v w) (mapEntries a) (mapEntries b)
sameSetPhysical :: T.IntSet -> T.IntSet -> Bool
sameSetPhysical (T.IntSet a) (T.IntSet b)=sameTree (==) a b
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

cmp :: Integer -> Integer -> Integer
cmp a b=if a<b then -1 else if a>b then 1 else 0
-- Independent exact cached-count/BST/delta3 constructor proof.
validTree :: T.Map Integer a -> Bool
validTree tree=case go tree of Nothing->False;Just _->True
 where
  go T.MapEmpty=Just(0::Integer,Nothing,Nothing)
  go(T.MapNode n k _ l r)=k `seq` do
   (lc,lo,lhi)<-go l
   (rc,rlo,hi)<-go r
   if n==1+lc+rc && maybe True(<k)lhi && maybe True(k<)rlo &&
      (lc+rc<=1 || (lc<=3*rc&&rc<=3*lc))
    then Just(1+lc+rc,Just(maybe k id lo),Just(maybe k id hi))
    else Nothing

validMap :: T.IntMap a -> Bool
validMap (T.IntMap tree)=validTree tree && M.valid cmp tree
validSet :: T.IntSet -> Bool
validSet (T.IntSet tree)=validTree tree && M.valid cmp tree && all ((==()).snd) (entries tree)
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
nodeChildren :: T.Node -> [Integer]
nodeChildren (T.Node tag _ _)=case tag of
  T.GArr a b->[a,b]
  T.GTyApp a b->[a,b]
  T.GGen n->[n]
  T.GCon _ children->children
  _->[]
nodeBinder :: T.Node -> [Integer]
nodeBinder (T.Node _ T.Nothing _) = []
nodeBinder (T.Node _ (T.Just parent) _) = [parent]
indexOracle :: [(Integer,Integer)] -> [(Integer,[Integer])]
indexOracle edges=HostMap.toAscList (HostMap.map HostSet.toAscList
  (foldl' (\m (key,value)->HostMap.insertWith HostSet.union key (HostSet.singleton value) m) HostMap.empty edges))
indexEntries :: T.IntMap T.IntSet -> [(Integer,[Integer])]
indexEntries index=[(key,setEntries values)|(key,values)<-mapEntries index]
checkSolver :: String -> Bool -> T.Solver -> T.Solver -> IO ()
checkSolver label physical old new=do
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
    _<-right (label++" frozen final index audit") (FS.finish new)
    pure ()

checkOutcome :: String -> Bool -> T.Either B.String T.Solver -> T.Either B.String T.Solver -> IO ()
checkOutcome label physical old new=case (old,new) of
  (T.Left a,T.Left b)->assert (label++" exact diagnostic") (B.v_eqString a b)
  (T.Right a,T.Right b)->checkSolver label physical a b
  (T.Left a,T.Right _)->errorWithoutStackTrace (label++" batch accepted original rejection: "++B.unpack a)
  (T.Right _,T.Left b)->errorWithoutStackTrace (label++" batch rejected original success: "++B.unpack b)
