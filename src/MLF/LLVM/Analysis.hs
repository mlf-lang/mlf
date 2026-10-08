-- | Conservative demand analysis for native workers. The least fixed point
-- proves which arguments must be evaluated whenever a saturated call returns
-- a value. Non-strict fields, branches and IO operands stay lazy.
module MLF.LLVM.Analysis
  ( Function (..), Functions, analyze, needed, demanded, primitiveArity ) where

import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified MLF.Primitive as P
import qualified MLF.X.Syntax as X
import MLF.LLVM.Optimize (free, applications, lambdas)

data Function = Function
  { parameters :: [X.Name], functionBody :: X.Erased
  , captures :: [X.Name], strict :: Set.Set X.Name
  } deriving (Eq, Show)
type Functions = Map.Map X.Name Function

primitiveArity :: P.Primitive -> Int
primitiveArity = P.primitiveArity

needed :: Functions -> X.Erased -> Set.Set X.Name
needed functions expression = Set.unions
  [maybe (Set.singleton n) (Set.fromList . captures) (Map.lookup n functions) | n <- Set.toList (free expression)]

analyze :: X.Erased -> Functions
analyze expression = demandFixed (captureFixed (collect expression))
  where
    collect e = Map.unions (bindings e : map collect (children e))
    bindings e = Map.fromList [(n,Function args body [] Set.empty) |
      (n,rhs) <- case e of X.ELet n a _ -> [(n,a)]; X.ELetRec ds _ -> ds; _ -> [],
      let (args,body) = lambdas rhs, not (null args)]
    captureFixed fs =
      let next = Map.map (\f -> f { captures = Set.toAscList
                   (needed fs (functionBody f) `Set.difference` Set.fromList (parameters f)) }) fs
      in if next == fs then fs else captureFixed next
    demandFixed fs =
      let next = Map.map (\f -> f { strict = demanded fs (functionBody f) `Set.intersection`
                                      Set.fromList (parameters f ++ captures f) }) fs
      in if next == fs then fs else demandFixed next

children :: X.Erased -> [X.Erased]
children e = case e of
  X.EAbs _ b -> [b]
  X.EApp f a -> [f,a]
  X.ELet _ a b -> [a,b]
  X.ELetRec ds b -> b : map snd ds
  X.ECase s bs -> s : [b | X.ErasedAlternative _ b <- bs]
  _ -> []

demanded :: Functions -> X.Erased -> Set.Set X.Name
demanded fs expression = case expression of
  X.EVar n | Map.member n fs -> Set.empty
           | otherwise -> Set.singleton n
  X.ELet n a b -> substituteDemand n a (go b)
  X.ELetRec ds b ->
    let expand ns = foldr (uncurry substituteDemand) ns ds
        fixed ns = let next = ns `Set.union` expand ns in if next == ns then ns else fixed next
    in fixed (go b) `Set.difference` Set.fromList (map fst ds)
  X.ECase s [X.ErasedAlternative (X.DefaultPattern n) b] ->
    maybe (go b) (\v -> substituteDemand v s (go b)) n
  X.ECase s bs -> go s `Set.union` intersect
    [go b `Set.difference` Set.fromList (X.patternNames p) | X.ErasedAlternative p b <- bs]
  X.EApp _ _ -> case applications expression of
    (X.EPrimitive P.IfThenElse,[c,a,b]) -> go c `Set.union` (go a `Set.intersection` go b)
    (X.EPrimitive p,args) | length args == primitiveArity p ->
      if P.primitiveStrict p
        then Set.unions (map go args) else Set.empty
    (X.EVar n,args) | Just f <- Map.lookup n fs, length args == length (parameters f) ->
      (strict f `Set.intersection` Set.fromList (captures f)) `Set.union`
      Set.unions [go a | (n',a) <- zip (parameters f) args, Set.member n' (strict f)]
    (f,_) -> go f
  _ -> Set.empty
  where
    go = demanded fs
    substituteDemand n a ns = Set.delete n ns `Set.union` (if Set.member n ns then go a else Set.empty)
    intersect [] = Set.empty
    intersect (a:as) = foldr Set.intersection a as
