-- | Whole-program constructor slots that always store canonical WHNF pointers.
-- These are representation facts, not new evaluation demands. The traversal
-- mirrors Codegen's thunk/worker boundary: named workers receive their strict
-- parameters and captures, while anonymous callbacks read unknown pointers.
-- A partial or escaping constructor invalidates every slot. Recursive holes
-- remain unknown even after a seq; an updated indirection is not a WHNF pointer.
module MLF.LLVM.StrictFields (infer) where

import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified MLF.LLVM.Analysis as A
import MLF.LLVM.Optimize (applications)
import qualified MLF.Primitive as P
import qualified MLF.X.Syntax as X

data Work = Evaluate (Set.Set X.Name) X.Erased | Suspend (Set.Set X.Name) X.Erased

infer :: Map.Map String Int -> A.Functions -> X.Erased -> Map.Map String [Bool]
infer cs fs expression = go Map.empty
  (Evaluate Set.empty expression :
   [Evaluate (A.strict f) (A.functionBody f) | f <- Map.elems fs])
  where
    constructorArity c = Map.findWithDefault (-1) c cs
    record c flags = Map.insertWith (zipWith (&&)) c flags
    escaped c = record c (replicate (max 0 (constructorArity c)) False)
    atom known e = case e of
      X.EVar n -> Set.member n known || Map.member n fs
      X.EInt _ -> True
      X.EDouble _ -> True
      X.EBool _ -> True
      X.EString _ -> True
      X.EPrimitive _ -> True
      X.EConstructor _ -> True
      X.EAbs _ _ -> True
      _ -> case applications e of
        (X.EConstructor c,args) -> length args == constructorArity c
        _ -> False
    go facts [] = facts
    go facts (Suspend known e : rest)
      | atom known e = go facts (Evaluate known e : rest)
      | otherwise = go facts (Evaluate Set.empty e : rest)
    go facts (Evaluate known e : rest) = case e of
      X.EAbs _ body -> go facts (Evaluate Set.empty body : rest)
      X.ELet n rhs body
        | Map.member n fs -> go facts (Evaluate known body : rest)
        | Set.member n (A.demanded fs body) ->
            go facts (Evaluate known rhs : Evaluate (Set.insert n known) body : rest)
        | otherwise -> go facts (Suspend known rhs : Evaluate (Set.delete n known) body : rest)
      X.ELetRec bindings body ->
        let local = known `Set.difference` Set.fromList (map fst bindings)
        in go facts ([Suspend local rhs | (n,rhs) <- bindings, Map.notMember n fs]
                     ++ Evaluate local body : rest)
      X.ECase scrutinee [X.ErasedAlternative (X.DefaultPattern name) body] ->
        go facts (Suspend known scrutinee : Evaluate (maybe known (`Set.delete` known) name) body : rest)
      X.ECase scrutinee alternatives ->
        go facts (Evaluate known scrutinee :
          [Evaluate (case pattern' of
             X.DefaultPattern name -> maybe known (`Set.insert` known) name
             X.ConstructorPattern _ names -> known `Set.difference` Set.fromList [n | Just n <- names]) body
          | X.ErasedAlternative pattern' body <- alternatives] ++ rest)
      X.EConstructor c
        | constructorArity c == 0 -> go (record c [] facts) rest
        | otherwise -> go (escaped c facts) rest
      X.EApp f a -> case applications e of
        (X.EConstructor c,args) | length args == constructorArity c ->
          go (record c (map (atom known) args) facts)
             (map (Suspend known) args ++ rest)
        (X.EPrimitive P.IfThenElse,[condition,yes,no]) ->
          go facts (map (Evaluate known) [condition,yes,no] ++ rest)
        (X.EPrimitive P.Seq,[first,second]) ->
          go facts (map (Evaluate known) [first,second] ++ rest)
        (X.EPrimitive p,args) | length args == A.primitiveArity p ->
          go facts (map (if P.primitiveStrict p then Evaluate known else Suspend known) args ++ rest)
        (X.EVar n,args) | Just fn <- Map.lookup n fs, length args == length (A.parameters fn) ->
          go facts ([if Set.member parameter (A.strict fn) then Evaluate known arg else Suspend known arg
                    | (parameter,arg) <- zip (A.parameters fn) args] ++ rest)
        (X.EConstructor c,_) ->
          go (escaped c facts) (Suspend known f : Suspend known a : rest)
        _ -> go facts (Suspend known f : Suspend known a : rest)
      _ -> go facts rest
