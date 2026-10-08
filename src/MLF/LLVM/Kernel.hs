-- | Conservative eligibility for first-order numeric IO regions. These rules
-- inspect resolved primitives and identities, never names or workload sources.
-- Pure operands must terminate without raising an error once their free
-- variables are values. This permits eager scalar temporaries while retaining
-- lazy arguments at the boundary (the generated entry checks, never forces).
module MLF.LLVM.Kernel (kernels, scalar) where

import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified MLF.LLVM.Analysis as A
import MLF.LLVM.Optimize (applications)
import qualified MLF.Primitive as P
import qualified MLF.X.Syntax as X

scalar :: A.Functions -> X.Erased -> Bool
scalar fs = go Set.empty
  where
    go seen e = case e of
      X.EVar n -> Map.notMember n fs
      X.EInt _ -> True
      X.EDouble _ -> True
      X.EBool _ -> True
      X.EConstructor _ -> True
      X.ELet _ a b -> go seen a && go seen b
      _ -> case applications e of
        (X.EPrimitive p,args) -> length args == P.primitiveArity p && all (go seen) args &&
          (p `elem` [P.AddInt,P.SubInt,P.MulInt,P.EqInt,P.LtInt,P.IfThenElse,
                     P.AddDouble,P.SubDouble,P.MulDouble,P.DivDouble,P.SqrtDouble,
                     P.EqDouble,P.LtDouble,P.IntToDouble] ||
           (p `elem` [P.QuotInt,P.RemInt] && case args of [_,X.EInt n] -> n /= 0; _ -> False))
        (X.EConstructor _,args) -> all (go seen) args
        (X.EVar n,args) | Just f <- Map.lookup n fs ->
          length args == length (A.parameters f) && Set.notMember n seen &&
          all (go seen) args && go (Set.insert n seen) (A.functionBody f)
        _ -> False

kernels :: A.Functions -> Set.Set X.Name
kernels fs = fixed candidates
  where
    -- A concrete IO primitive must anchor the result, even through recursive
    -- calls. An unproductive polymorphic pure loop is not evidence of IO.
    candidates = Set.fromList [n | n <- Map.keys fs, anchored Set.empty n]
    anchored seen n | Set.member n seen = False
    anchored seen n = maybe False (anchor (Set.insert n seen) . A.functionBody) (Map.lookup n fs)
    anchor seen e = case e of
      X.ELet _ _ b -> anchor seen b
      X.ELetRec _ b -> anchor seen b
      _ -> case applications e of
        (X.EPrimitive p,args) | p == P.IfThenElse -> any (anchor seen) (drop 1 args)
        (X.EPrimitive p,args) -> p `elem` operations && length args == P.primitiveArity p
        (X.EVar n,_) -> anchored seen n
        _ -> False
    operations = [P.IOReturn,P.IOBind,P.ReadIntArray,P.WriteIntArray,P.LengthIntArray,
                  P.ReadDoubleArray,P.WriteDoubleArray,P.LengthDoubleArray,
                  P.ReadByteArray,P.WriteByteArray,P.LengthByteArray]
    fixed ns = let next = Set.filter (eligible ns . A.functionBody . (fs Map.!)) ns
               in if next == ns then ns else fixed next
    eligible ns e = case e of
      X.ELet _ a b -> scalar fs a && eligible ns b
      X.ELetRec ds b -> all (\(n,_) -> Map.member n fs) ds && eligible ns b
      _ -> case applications e of
        (X.EPrimitive P.IOBind,[a,X.EAbs _ b]) -> eligible ns a && eligible ns b
        (X.EPrimitive P.IfThenElse,[c,a,b]) -> scalar fs c && eligible ns a && eligible ns b
        (X.EPrimitive p,args) -> p `elem` operations && p /= P.IOBind &&
          length args == P.primitiveArity p && all (scalar fs) args
        (X.EVar n,args) | Just f <- Map.lookup n fs -> Set.member n ns &&
          length args == length (A.parameters f) && all (scalar fs) args
        _ -> False
