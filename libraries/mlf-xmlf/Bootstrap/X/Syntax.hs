-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.X.Syntax where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Primitive as P;
  import Bootstrap.Kind;
  nameId (XName i _) = i;
  nameHint (XName _ hint) = hint;
  compareName a b =
    if (nameId a < nameId b) then (0 - 1) else if (nameId a == nameId b) then 0 else 1;
  equalName a b = (nameId a == nameId b);
  patternNames :: XPattern -> [] XName;
  patternNames (XConstructorPattern _ ns) = L.catMaybes ns;
  patternNames (XDefaultPattern n) = L.maybeToList n;
  compose :: XComputation -> XComputation -> XComputation;
  compose XRefl b = b;
  compose a XRefl = a;
  compose a b = XThen a b;
  instantiate :: XTerm -> XComputation -> XTerm;
  instantiate t XRefl = t;
  instantiate (XTypeApp t a) b = XTypeApp t (compose a b);
  instantiate t p = XTypeApp t p;
  typeApplication t = XThen (XInner (XBottom t)) XElim;
  erase :: XTerm -> XErased;
  erase term =
    case term of {
      XVarTerm n -> XEVar n;
      XAbs n _ b -> XEAbs n (erase b);
      XApp f a -> XEApp (erase f) (erase a);
      XTypeAbs _ _ b -> erase b;
      XTypeApp a _ -> erase a;
      XLet n a b -> XELet n (erase a) (erase b);
      XLetRec ds b -> XELetRec (L.map eraseBinding ds) (erase b);
      XIntTerm i -> XEInt i;
      XDoubleTerm d -> XEDouble d;
      XBoolTerm b -> XEBool b;
      XStringTerm s -> XEString s;
      XPrimitive p _ -> XEPrimitive p;
      XConstructor c _ -> XEConstructor c;
      XCase a _ alternatives -> XECase (erase a) (L.map eraseAlternative alternatives);
      XWithData _ b -> erase b
    };
  eraseBinding :: (,,) XName XType XTerm -> (,) XName XErased;
  eraseBinding ((,,) n _ a) = (,) n (erase a);
  eraseAlternative :: XAlternative -> XErasedAlternative;
  eraseAlternative (XAlternative p b) = XErasedAlternative p (erase b);
  equalMaybeName Nothing Nothing = True;
  equalMaybeName (Just a) (Just b) = equalName a b;
  equalMaybeName _ _ = False;
  equalPattern :: XPattern -> XPattern -> Bool;
  equalPattern (XConstructorPattern c ns) (XConstructorPattern d ms) =
    (eqString c d && equalList equalMaybeName ns ms);
  equalPattern (XDefaultPattern n) (XDefaultPattern m) = equalMaybeName n m;
  equalPattern _ _ = False;
  equalList :: forall a. (a -> a -> Bool) -> [] a -> [] a -> Bool;
  equalList eq [] [] = True;
  equalList eq ((:) a as) ((:) b bs) = (eq a b && equalList eq as bs);
  equalList eq _ _ = False;
  equalErased :: XErased -> XErased -> Bool;
  equalErased a b =
    case a of {
      XEVar n ->
        case b of {
          XEVar m -> equalName n m;
          _ -> False
        };
      XEAbs n body ->
        case b of {
          XEAbs m body2 -> (equalName n m && equalErased body body2);
          _ -> False
        };
      XEApp f x ->
        case b of {
          XEApp g y -> (equalErased f g && equalErased x y);
          _ -> False
        };
      XELet n x y ->
        case b of {
          XELet m z w -> (equalName n m && (equalErased x z && equalErased y w));
          _ -> False
        };
      XELetRec ds body ->
        case b of {
          XELetRec es body2 -> (equalList equalErasedBinding ds es && equalErased body body2);
          _ -> False
        };
      XEInt n ->
        case b of {
          XEInt m -> (n == m);
          _ -> False
        };
      XEDouble n ->
        case b of {
          XEDouble m -> eqDouble n m;
          _ -> False
        };
      XEBool n ->
        case b of {
          XEBool m -> if n then m else if m then False else True;
          _ -> False
        };
      XEString n ->
        case b of {
          XEString m -> eqString n m;
          _ -> False
        };
      XEPrimitive p ->
        case b of {
          XEPrimitive q -> (P.primitiveCode p == P.primitiveCode q);
          _ -> False
        };
      XEEvidenceHole i ->
        case b of {
          XEEvidenceHole j -> (i == j);
          _ -> False
        };
      XEConstructor c ->
        case b of {
          XEConstructor d -> eqString c d;
          _ -> False
        };
      XECase s as ->
        case b of {
          XECase t bs -> (equalErased s t && equalList equalErasedAlternative as bs);
          _ -> False
        }
    };
  equalErasedBinding :: (,) XName XErased -> (,) XName XErased -> Bool;
  equalErasedBinding ((,) n a) ((,) m b) = (equalName n m && equalErased a b);
  equalErasedAlternative :: XErasedAlternative -> XErasedAlternative -> Bool;
  equalErasedAlternative (XErasedAlternative p a) (XErasedAlternative q b) =
    (equalPattern p q && equalErased a b)
}
