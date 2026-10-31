-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}
module FrozenIdentityInventory where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.X.Syntax as X;
  typeIdentities :: XType -> Set Int -> Set Int;
  typeIdentities ty seen =
    case ty of {
      XVar (XTyVar a) -> Set.insert compareInt a seen;
      XArrow a b -> typeIdentities b (typeIdentities a seen);
      XCon _ ts -> foldl (\acc t -> typeIdentities t acc) seen ts;
      XApply a b -> typeIdentities b (typeIdentities a seen);
      XForall (XTyVar a) bound b ->
        typeIdentities b (typeIdentities bound (Set.insert compareInt a seen));
      _ -> seen
    };
  computationIdentities :: XComputation -> Set Int -> Set Int;
  computationIdentities p seen =
    case p of {
      XBottom t -> typeIdentities t seen;
      XHyp (XTyVar a) -> Set.insert compareInt a seen;
      XInner q -> computationIdentities q seen;
      XOuter (XTyVar a) q -> computationIdentities q (Set.insert compareInt a seen);
      XIntro (XTyVar a) -> Set.insert compareInt a seen;
      XIntroKind (XTyVar a) _ -> Set.insert compareInt a seen;
      XThen a b -> computationIdentities b (computationIdentities a seen);
      _ -> seen
    };
  termIdentities :: XTerm -> Set Int -> Set Int;
  termIdentities term seen =
    case term of {
      XVarTerm n -> Set.insert compareInt (X.nameId n) seen;
      XAbs n ty b -> termIdentities b (typeIdentities ty (Set.insert compareInt (X.nameId n) seen));
      XApp a b -> termIdentities b (termIdentities a seen);
      XTypeAbs (XTyVar a) bound b ->
        termIdentities b (typeIdentities bound (Set.insert compareInt a seen));
      XTypeApp a p -> computationIdentities p (termIdentities a seen);
      XLet n a b -> termIdentities b (termIdentities a (Set.insert compareInt (X.nameId n) seen));
      XLetRec bs b ->
        termIdentities b
          (foldl
             (\acc ((,,) n t a) ->
                termIdentities a (typeIdentities t (Set.insert compareInt (X.nameId n) acc)))
             seen
             bs);
      XPrimitive _ ts -> foldl (\acc t -> typeIdentities t acc) seen ts;
      XConstructor _ ts -> foldl (\acc t -> typeIdentities t acc) seen ts;
      XCase a t bs ->
        foldl
          (\acc (XAlternative p b) ->
             termIdentities b
               (foldl (\ids n -> Set.insert compareInt (X.nameId n) ids) acc (X.patternNames p)))
          (typeIdentities t (termIdentities a seen))
          bs;
      XWithData _ b -> termIdentities b seen;
      _ -> seen
    };
}
