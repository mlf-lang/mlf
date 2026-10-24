-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.Kernel where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Primitive as P;
  import qualified Bootstrap.LLVM.Analysis as A;
  import qualified Bootstrap.LLVM.Optimize as O;
  data CopyLoop = CopyLoop XName XName XName XName XName XName;
  primitiveIn :: Primitive -> [] Int -> Bool;
  primitiveIn p codes = L.any (\code -> (P.primitiveCode p == code)) codes;
  safeScalarPrimitive :: Primitive -> Bool;
  safeScalarPrimitive p =
    case p of {
      PAddInt -> True;
      PSubInt -> True;
      PMulInt -> True;
      PAndInt -> True;
      PEqInt -> True;
      PLtInt -> True;
      PIfThenElse -> True;
      PAddDouble -> True;
      PSubDouble -> True;
      PMulDouble -> True;
      PDivDouble -> True;
      PSqrtDouble -> True;
      PEqDouble -> True;
      PLtDouble -> True;
      PIntToDouble -> True;
      _ -> False
    };
  safeQuotient :: Primitive -> [] XErased -> Bool;
  safeQuotient p args =
    case p of {
      PQuotInt -> nonzeroDivisor args;
      PRemInt -> nonzeroDivisor args;
      _ -> False
    };
  nonzeroDivisor :: [] XErased -> Bool;
  nonzeroDivisor args =
    case args of {
      (:) a ((:) (XEInt n) []) -> (n /= 0);
      _ -> False
    };
  scalar :: Map XName A.WorkerFunction -> XErased -> Bool;
  scalar fs expression = scalarSeen fs S.empty expression;
  scalarSeen :: Map XName A.WorkerFunction -> Set XName -> XErased -> Bool;
  scalarSeen fs seen expression =
    case expression of {
      XEVar n -> L.not (M.member O.compareName n fs);
      XEInt n -> True;
      XEDouble n -> True;
      XEBool n -> True;
      XEString n -> True;
      XEConstructor n -> True;
      XELet n a b -> (scalarSeen fs seen a && scalarSeen fs seen b);
      _ ->
        case O.applications expression of {
          (,) (XEPrimitive p) args ->
            ((L.length args == P.primitiveArity p) &&
             (L.all (scalarSeen fs seen) args && (safeScalarPrimitive p || safeQuotient p args)));
          (,) (XEConstructor c) args -> L.all (scalarSeen fs seen) args;
          (,) (XEVar n) args ->
            case M.lookup O.compareName n fs of {
              Nothing -> False;
              Just f ->
                ((L.length args == L.length (A.parameters f)) &&
                 (L.not (S.member O.compareName n seen) &&
                  (L.all (scalarSeen fs seen) args &&
                   scalarSeen fs (S.insert O.compareName n seen) (A.functionBody f))))
            };
          _ -> False
        }
    };
  operation :: Primitive -> Bool;
  operation p =
    case p of {
      PIOReturn -> True;
      PIOBind -> True;
      PReadIntArray -> True;
      PWriteIntArray -> True;
      PLengthIntArray -> True;
      PReadDoubleArray -> True;
      PWriteDoubleArray -> True;
      PLengthDoubleArray -> True;
      PReadByteArray -> True;
      PWriteByteArray -> True;
      PLengthByteArray -> True;
      PReadIntTable -> True;
      PWriteIntTable -> True;
      PGetByteLine -> True;
      PNewByteArray -> True;
      PNewIntArray -> True;
      PNewDoubleArray -> True;
      PByteArrayFromString -> True;
      PPutBytes -> True;
      PNewIntTable -> True;
      _ -> False
    };
  anchored :: Map XName A.WorkerFunction -> Set XName -> XName -> Bool;
  anchored fs seen name =
    if S.member O.compareName name seen
    then False
    else case M.lookup O.compareName name fs of {
           Nothing -> False;
           Just f -> anchor fs (S.insert O.compareName name seen) (A.functionBody f)
         };
  anchor :: Map XName A.WorkerFunction -> Set XName -> XErased -> Bool;
  anchor fs seen expression =
    case expression of {
      XELet n a b -> anchor fs seen b;
      XELetRec ds b -> anchor fs seen b;
      _ ->
        case O.applications expression of {
          (,) (XEPrimitive PIfThenElse) args -> L.any (anchor fs seen) (L.drop 1 args);
          (,) (XEPrimitive p) args -> (operation p && (L.length args == P.primitiveArity p));
          (,) (XEVar n) args -> anchored fs seen n;
          _ -> False
        }
    };
  eligible :: Map XName A.WorkerFunction -> Set XName -> XErased -> Bool;
  eligible fs names expression =
    case expression of {
      XELet n a b -> (scalar fs a && eligible fs names b);
      XELetRec ds b ->
        (L.all
           (\entry ->
              case entry of {
                (,) n a -> M.member O.compareName n fs
              })
           ds &&
         eligible fs names b);
      _ ->
        case O.applications expression of {
          (,) (XEPrimitive PIOBind) ((:) a ((:) (XEAbs n b) [])) ->
            (eligible fs names a && eligible fs names b);
          (,) (XEPrimitive PIfThenElse) ((:) c ((:) a ((:) b []))) ->
            (scalar fs c && (eligible fs names a && eligible fs names b));
          (,) (XEPrimitive PIOBind) args -> False;
          (,) (XEPrimitive p) args ->
            (operation p && ((L.length args == P.primitiveArity p) && L.all (scalar fs) args));
          (,) (XEVar n) args ->
            case M.lookup O.compareName n fs of {
              Nothing -> False;
              Just f ->
                (S.member O.compareName n names &&
                 ((L.length args == L.length (A.parameters f)) && L.all (scalar fs) args))
            };
          _ -> False
        }
    };
  kernelFixed :: Map XName A.WorkerFunction -> Set XName -> Set XName;
  kernelFixed fs names =
    let {
      next =
        S.filter
          (\name ->
             case M.lookup O.compareName name fs of {
               Nothing -> False;
               Just f -> eligible fs names (A.functionBody f)
             })
          names
    } in
    if A.sameNames (S.toList names) (S.toList next) then names else kernelFixed fs next;
  kernels :: Map XName A.WorkerFunction -> Set XName;
  kernels fs =
    kernelFixed fs (S.fromList O.compareName (L.filter (anchored fs S.empty) (M.keys fs)));
  allocation :: Primitive -> Bool;
  allocation p =
    case p of {
      PGetByteLine -> True;
      PNewByteArray -> True;
      PNewIntArray -> True;
      PNewDoubleArray -> True;
      PByteArrayFromString -> True;
      PNewIntTable -> True;
      _ -> False
    };
  reaches :: Set XName -> XErased -> Bool;
  reaches previous expression =
    case O.applications expression of {
      (,) (XEPrimitive p) args ->
        if allocation p then True else reachesChildren previous expression;
      (,) (XEVar n) args ->
        if S.member O.compareName n previous then True else reachesChildren previous expression;
      _ -> reachesChildren previous expression
    };
  reachesChildren :: Set XName -> XErased -> Bool;
  reachesChildren previous expression =
    case expression of {
      XEAbs n b -> reaches previous b;
      XEApp a b -> (reaches previous a || reaches previous b);
      XELet n a b -> (reaches previous a || reaches previous b);
      XELetRec ds b -> reaches previous b;
      _ -> False
    };
  collectingFixed :: Map XName A.WorkerFunction -> Set XName -> Set XName -> Set XName;
  collectingFixed fs names previous =
    let {
      next =
        S.filter
          (\name ->
             case M.lookup O.compareName name fs of {
               Nothing -> False;
               Just f -> reaches previous (A.functionBody f)
             })
          names
    } in
    if A.sameNames (S.toList previous) (S.toList next)
    then previous
    else collectingFixed fs names next;
  collecting :: Map XName A.WorkerFunction -> Set XName -> Set XName;
  collecting fs names = collectingFixed fs names S.empty;
  byteCopy :: XName -> A.WorkerFunction -> Maybe ([] XName);
  byteCopy name f =
    if L.null (A.captures f)
    then case A.parameters f of {
           (:) source ((:) dest ((:) end ((:) offset ((:) index [])))) ->
             let {
               candidate = CopyLoop name source dest end offset index
             } in
             if copyBody candidate (A.functionBody f) then Just (A.parameters f) else Nothing;
           _ -> Nothing
         }
    else Nothing;
  copyBody :: CopyLoop -> XErased -> Bool;
  copyBody candidate expression =
    case O.applications expression of {
      (,) (XEPrimitive PIfThenElse) ((:) condition ((:) body ((:) done []))) ->
        (copyCondition candidate condition && (copyRead candidate body && copyDone done));
      _ -> False
    };
  copyCondition :: CopyLoop -> XErased -> Bool;
  copyCondition (CopyLoop name source dest end offset index) expression =
    case O.applications expression of {
      (,) (XEPrimitive PLtInt) ((:) (XEVar i) ((:) (XEVar n) [])) ->
        (O.eqName index i && O.eqName end n);
      _ -> False
    };
  copyDone :: XErased -> Bool;
  copyDone expression =
    case O.applications expression of {
      (,) (XEPrimitive PIOReturn) ((:) (XEConstructor unit) []) -> eqString unit "()";
      _ -> False
    };
  copyRead :: CopyLoop -> XErased -> Bool;
  copyRead candidate expression =
    case O.applications expression of {
      (,) (XEPrimitive PIOBind) ((:) action ((:) (XEAbs cell rest) [])) ->
        case O.applications action of {
          (,) (XEPrimitive PReadByteArray) ((:) (XEVar array) ((:) (XEVar i) [])) ->
            case candidate of {
              CopyLoop name source dest end offset index ->
                (O.eqName source array && (O.eqName index i && copyWrite candidate cell rest))
            };
          _ -> False
        };
      _ -> False
    };
  copyWrite :: CopyLoop -> XName -> XErased -> Bool;
  copyWrite candidate cell expression =
    case O.applications expression of {
      (,) (XEPrimitive PIOBind) ((:) action ((:) (XEAbs ignored tail) [])) ->
        case O.applications action of {
          (,) (XEPrimitive PWriteByteArray) ((:) (XEVar array) ((:) address ((:) (XEVar c) []))) ->
            case candidate of {
              CopyLoop name source dest end offset index ->
                (O.eqName dest array &&
                 (O.eqName cell c && (copyAddress candidate address && copyTail candidate tail)))
            };
          _ -> False
        };
      _ -> False
    };
  copyAddress :: CopyLoop -> XErased -> Bool;
  copyAddress (CopyLoop name source dest end offset index) expression =
    case O.applications expression of {
      (,) (XEPrimitive PAddInt) ((:) (XEVar o) ((:) (XEVar i) [])) ->
        (O.eqName offset o && O.eqName index i);
      _ -> False
    };
  copyTail :: CopyLoop -> XErased -> Bool;
  copyTail (CopyLoop name source dest end offset index) expression =
    case O.applications expression of {
      (,) (XEVar self) ((:) (XEVar a) ((:) (XEVar b) ((:) (XEVar n) ((:) (XEVar o) ((:) next []))))) ->
        (O.eqName name self &&
         (O.eqName source a &&
          (O.eqName dest b && (O.eqName end n && (O.eqName offset o && copyNext index next)))));
      _ -> False
    };
  copyNext :: XName -> XErased -> Bool;
  copyNext index expression =
    case O.applications expression of {
      (,) (XEPrimitive PAddInt) ((:) (XEVar i) ((:) (XEInt one) [])) ->
        (O.eqName index i && (one == 1));
      _ -> False
    }
}
