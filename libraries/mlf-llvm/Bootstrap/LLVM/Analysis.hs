-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.Analysis where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Primitive as P;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.LLVM.Optimize as O;
  -- Native worker information is computed by two monotone fixed points.
  data WorkerFunction = WorkerFunction ([] XName) XErased ([] XName) (Set XName);
  parameters :: WorkerFunction -> [] XName;
  parameters (WorkerFunction args body captured demanded) = args;
  functionBody :: WorkerFunction -> XErased;
  functionBody (WorkerFunction args body captured demanded) = body;
  captures :: WorkerFunction -> [] XName;
  captures (WorkerFunction args body captured demanded) = captured;
  strict :: WorkerFunction -> Set XName;
  strict (WorkerFunction args body captured demanded) = demanded;
  needed :: Map XName WorkerFunction -> XErased -> Set XName;
  needed functions expression =
    S.unions O.compareName (L.map (neededName functions) (S.toList (O.free expression)));
  neededName :: Map XName WorkerFunction -> XName -> Set XName;
  neededName functions name =
    case M.lookup O.compareName name functions of {
      Nothing -> S.singleton name;
      Just f -> S.fromList O.compareName (captures f)
    };
  children :: XErased -> [] XErased;
  children expression =
    case expression of {
      XEAbs n b -> (:) b [];
      XEApp f a -> (:) f ((:) a []);
      XELet n a b -> (:) a ((:) b []);
      XELetRec ds b ->
        (:) b
          (L.map
             (\entry ->
                case entry of {
                  (,) n a -> a
                })
             ds);
      XECase s branches ->
        (:) s
          (L.map
             (\branch ->
                case branch of {
                  XErasedAlternative p b -> b
                })
             branches);
      _ -> []
    };
  bindings :: XErased -> [] ((,) XName XErased);
  bindings expression =
    case expression of {
      XELet name a b -> (:) ((,) name a) [];
      XELetRec ds b -> ds;
      _ -> []
    };
  collectBinding :: (,) XName XErased -> Map XName WorkerFunction -> Map XName WorkerFunction;
  collectBinding ((,) name rhs) fs =
    case O.lambdas rhs of {
      (,) [] body -> fs;
      (,) args body -> M.insert O.compareName name (WorkerFunction args body [] S.empty) fs
    };
  collect :: XErased -> Map XName WorkerFunction;
  collect expression =
    M.unions O.compareName
      ((:) (L.foldr collectBinding M.empty (bindings expression))
         (L.map collect (children expression)));
  sameNames :: [] XName -> [] XName -> Bool;
  sameNames a b =
    case a of {
      [] -> L.null b;
      (:) n rest ->
        case b of {
          [] -> False;
          (:) m tail -> (O.eqName n m && sameNames rest tail)
        }
    };
  sameFunction :: WorkerFunction -> WorkerFunction -> Bool;
  sameFunction (WorkerFunction args body captured demanded) (WorkerFunction args2 body2 captured2 demanded2) =
    (sameNames args args2 &&
     (sameNames captured captured2 &&
      (sameNames (S.toList demanded) (S.toList demanded2) && X.equalErased body body2)));
  sameFunctions :: [] ((,) XName WorkerFunction) -> [] ((,) XName WorkerFunction) -> Bool;
  sameFunctions a b =
    case a of {
      [] -> L.null b;
      (:) ((,) n f) rest ->
        case b of {
          [] -> False;
          (:) ((,) m g) tail -> (O.eqName n m && (sameFunction f g && sameFunctions rest tail))
        }
    };
  -- Bodies and parameters stay fixed during capture propagation. Cache their
  -- lexical free names once; each iteration only changes the capture lists.
  captureFixed :: Map XName WorkerFunction -> Map XName WorkerFunction;
  captureFixed fs =
    captureIndexed
      (M.map
         (\f -> (,) (S.toList (O.free (functionBody f))) (S.fromList O.compareName (parameters f)))
         fs)
      fs;
  captureIndexed :: Map XName ((,) ([] XName) (Set XName)) ->
                    Map XName WorkerFunction -> Map XName WorkerFunction;
  captureIndexed inputs fs =
    let {
      next =
        M.mapWithKey
          (\name f ->
             case M.get O.compareName name inputs of {
               (,) names parameterNames ->
                 WorkerFunction (parameters f) (functionBody f)
                   (S.toList
                      (S.difference O.compareName
                         (S.unions O.compareName (L.map (neededName fs) names))
                         parameterNames))
                   (strict f)
             })
          fs
    } in
    if M.eqMap O.eqName (\a b -> sameNames (captures a) (captures b)) fs next
    then fs
    else captureIndexed inputs next;
  demandFixed :: Map XName WorkerFunction -> Map XName WorkerFunction;
  demandFixed fs =
    let {
      next =
        M.map
          (\f ->
             WorkerFunction (parameters f) (functionBody f) (captures f)
               (S.intersection O.compareName (demanded fs (functionBody f))
                  (S.fromList O.compareName (L.append (parameters f) (captures f)))))
          fs
    } in
    if M.eqMap O.eqName (\a b -> sameNames (S.toList (strict a)) (S.toList (strict b))) fs next
    then fs
    else demandFixed next;
  analyze :: XErased -> Map XName WorkerFunction;
  analyze expression = demandFixed (captureFixed (collect expression));
  substituteDemand :: Map XName WorkerFunction -> XName -> XErased -> Set XName -> Set XName;
  substituteDemand fs name value names =
    S.union O.compareName (S.delete O.compareName name names)
      (if S.member O.compareName name names then demanded fs value else S.empty);
  recursiveDemand :: Map XName WorkerFunction ->
                     [] ((,) XName XErased) -> Set XName -> Set XName;
  recursiveDemand fs bindings names =
    let {
      expanded =
        L.foldr
          (\entry rest ->
             case entry of {
               (,) n a -> substituteDemand fs n a rest
             })
          names
          bindings
    } in
    let {
      next = S.union O.compareName names expanded
    } in
    if sameNames (S.toList names) (S.toList next) then names else recursiveDemand fs bindings next;
  intersectAll :: [] (Set XName) -> Set XName;
  intersectAll sets =
    case sets of {
      [] -> S.empty;
      (:) first rest -> L.foldr (S.intersection O.compareName) first rest
    };
  demandedAlternative :: Map XName WorkerFunction -> XErasedAlternative -> Set XName;
  demandedAlternative fs (XErasedAlternative p b) =
    S.difference O.compareName (demanded fs b) (S.fromList O.compareName (X.patternNames p));
  demanded :: Map XName WorkerFunction -> XErased -> Set XName;
  demanded fs expression =
    case expression of {
      XEVar n -> if M.member O.compareName n fs then S.empty else S.singleton n;
      XELet n a b -> substituteDemand fs n a (demanded fs b);
      XELetRec ds b ->
        S.difference O.compareName (recursiveDemand fs ds (demanded fs b))
          (S.fromList O.compareName
             (L.map
                (\entry ->
                   case entry of {
                     (,) n a -> n
                   })
                ds));
      XECase s ((:) (XErasedAlternative (XDefaultPattern optional) b) []) ->
        case optional of {
          Nothing -> demanded fs b;
          Just n -> substituteDemand fs n s (demanded fs b)
        };
      XECase s branches ->
        S.union O.compareName (demanded fs s)
          (intersectAll (L.map (demandedAlternative fs) branches));
      XEApp f a -> demandedApplication fs expression;
      _ -> S.empty
    };
  demandedApplication :: Map XName WorkerFunction -> XErased -> Set XName;
  demandedApplication fs expression =
    case O.applications expression of {
      (,) (XEPrimitive PIfThenElse) ((:) c ((:) a ((:) b []))) ->
        S.union O.compareName (demanded fs c)
          (S.intersection O.compareName (demanded fs a) (demanded fs b));
      (,) (XEPrimitive PSeq) ((:) a ((:) b [])) ->
        S.union O.compareName (demanded fs a) (demanded fs b);
      (,) (XEPrimitive p) args ->
        if (L.length args == P.primitiveArity p)
        then if P.primitiveStrict p
             then S.unions O.compareName (L.map (demanded fs) args)
             else S.empty
        else S.empty;
      (,) (XEVar n) args ->
        case M.lookup O.compareName n fs of {
          Just f ->
            if (L.length args == L.length (parameters f))
            then S.union O.compareName
                   (S.intersection O.compareName (strict f) (S.fromList O.compareName (captures f)))
                   (S.unions O.compareName
                      (L.map
                         (\entry ->
                            case entry of {
                              (,) name arg ->
                                if S.member O.compareName name (strict f)
                                then demanded fs arg
                                else S.empty
                            })
                         (L.zip (parameters f) args)))
            else demanded fs (XEVar n);
          Nothing -> demanded fs (XEVar n)
        };
      (,) f args -> demanded fs f
    }
}
