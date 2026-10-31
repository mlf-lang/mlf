-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.X.Type where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Data as D;
  import Bootstrap.Kind;
  tyVarId (XTyVar i) = i;
  compareTyVar a b =
    if (tyVarId a < tyVarId b) then (0 - 1) else if (tyVarId a == tyVarId b) then 0 else 1;
  equalTyVar a b = (tyVarId a == tyVarId b);
  freeVars :: XType -> Set XTyVar;
  freeVars ty =
    case ty of {
      XVar a -> S.singleton a;
      XBot -> S.empty;
      XBotKind _ -> S.empty;
      XArrow a b -> S.union compareTyVar (freeVars a) (freeVars b);
      XCon _ ts -> L.foldr (S.union compareTyVar) S.empty (L.map freeVars ts);
      XApply f a -> S.union compareTyVar (freeVars f) (freeVars a);
      XForall a bound body ->
        S.union compareTyVar (freeVars bound) (S.delete compareTyVar a (freeVars body))
    };
  allVars :: XType -> Set XTyVar;
  allVars ty =
    case ty of {
      XVar a -> S.singleton a;
      XBot -> S.empty;
      XBotKind _ -> S.empty;
      XArrow a b -> S.union compareTyVar (allVars a) (allVars b);
      XCon _ ts -> L.foldr (S.union compareTyVar) S.empty (L.map allVars ts);
      XApply f a -> S.union compareTyVar (allVars f) (allVars a);
      XForall a bound body ->
        S.insert compareTyVar a (S.union compareTyVar (allVars bound) (allVars body))
    };
  freshNegative :: Set XTyVar -> Int -> XTyVar;
  freshNegative used i =
    if S.member compareTyVar (XTyVar i) used then freshNegative used (L.advanceIdentity i (-1)) else XTyVar i;
  substitute :: XTyVar -> XType -> XType -> XType;
  substitute a replacement ty =
    case ty of {
      XVar b -> if equalTyVar a b then replacement else ty;
      XBot -> XBot;
      XBotKind k -> XBotKind k;
      XArrow x y -> XArrow (substitute a replacement x) (substitute a replacement y);
      XCon c ts -> XCon c (L.map (substitute a replacement) ts);
      XApply f x -> apply (substitute a replacement f) (substitute a replacement x);
      XForall b bound body ->
        if (equalTyVar a b || L.not (S.member compareTyVar a (freeVars body)))
        then XForall b (substitute a replacement bound) body
        else if S.member compareTyVar b (freeVars replacement)
             then let {
                    used =
                      S.insert compareTyVar a
                        (S.union compareTyVar (allVars body) (allVars replacement))
                  } in
                  let {
                    fresh = freshNegative used (0 - 1)
                  } in
                  XForall fresh (substitute a replacement bound)
                    (substitute a replacement (substitute b (XVar fresh) body))
             else XForall b (substitute a replacement bound) (substitute a replacement body)
    };
  alphaEq :: XType -> XType -> Bool;
  alphaEq a b = alphaIn M.empty M.empty 0 a b;
  alphaIn :: Map XTyVar Int -> Map XTyVar Int -> Int -> XType -> XType -> Bool;
  alphaIn l r depth a b =
    case a of {
      XVar x ->
        case b of {
          XVar y ->
            case M.lookup compareTyVar x l of {
              Just i ->
                case M.lookup compareTyVar y r of {
                  Just j -> (i == j);
                  Nothing -> False
                };
              Nothing ->
                case M.lookup compareTyVar y r of {
                  Nothing -> equalTyVar x y;
                  Just _ -> False
                }
            };
          _ -> alphaApplications l r depth a b
        };
      XBot ->
        case b of {
          XBot -> True;
          XBotKind k -> eqKind k Star;
          _ -> False
        };
      XBotKind k ->
        case b of {
          XBot -> eqKind k Star;
          XBotKind j -> eqKind k j;
          _ -> False
        };
      XArrow x y ->
        case b of {
          XArrow z w -> (alphaIn l r depth x z && alphaIn l r depth y w);
          _ -> alphaApplications l r depth a b
        };
      XCon c xs ->
        case b of {
          XCon d ys -> (eqString c d && alphaList l r depth xs ys);
          _ -> alphaApplications l r depth a b
        };
      XApply f x ->
        case b of {
          XApply g y -> (alphaIn l r depth f g && alphaIn l r depth x y);
          _ -> alphaApplications l r depth a b
        };
      XForall x xb xt ->
        case b of {
          XForall y yb yt ->
            let {
              nextDepth = (depth + 1)
            } in
            (alphaIn l r depth xb yb &&
             seq nextDepth
               (alphaIn (M.insert compareTyVar x depth l) (M.insert compareTyVar y depth r)
                  nextDepth
                  xt
                  yt));
          _ -> alphaApplications l r depth a b
        }
    };
  alphaList :: Map XTyVar Int -> Map XTyVar Int -> Int -> [] XType -> [] XType -> Bool;
  alphaList l r depth [] [] = True;
  alphaList l r depth ((:) a as) ((:) b bs) =
    (alphaIn l r depth a b && alphaList l r depth as bs);
  alphaList l r depth _ _ = False;
  alphaApplications :: Map XTyVar Int -> Map XTyVar Int -> Int -> XType -> XType -> Bool;
  alphaApplications l r depth a b =
    case applicationView a of {
      Nothing -> False;
      Just ((,) f x) ->
        case applicationView b of {
          Nothing -> False;
          Just ((,) g y) -> (alphaIn l r depth f g && alphaIn l r depth x y)
        }
    };
  apply :: XType -> XType -> XType;
  apply (XCon c xs) x = XCon c (L.append xs ((:) x []));
  apply f x = XApply f x;
  applicationView :: XType -> Maybe ((,) XType XType);
  applicationView (XApply f x) = Just ((,) f x);
  applicationView (XCon c xs) =
    case L.reverse xs of {
      (:) x rest -> Just ((,) (XCon c (L.reverse rest)) x);
      [] -> Nothing
    };
  applicationView _ = Nothing;
  bottomKind Star = XBot;
  bottomKind k = XBotKind k;
  kindOf :: DataEnv -> Map XTyVar XType -> XType -> Either String Kind;
  kindOf ds bounds ty =
    do {
      kinds <- L.mapM (kindBinding ds bounds S.empty) (S.toList (freeVars ty));
      kindIn ds (M.fromList compareTyVar kinds) ty
    };
  kindBinding :: DataEnv ->
                 Map XTyVar XType -> Set XTyVar -> XTyVar -> Either String ((,) XTyVar Kind);
  kindBinding ds bounds seen a =
    do {
      k <- visitKind ds bounds seen a;
      return ((,) a k)
    };
  visitKind :: DataEnv -> Map XTyVar XType -> Set XTyVar -> XTyVar -> Either String Kind;
  visitKind ds bounds seen a =
    if S.member compareTyVar a seen
    then Left "cyclic type environment"
    else case M.lookup compareTyVar a bounds of {
           Nothing -> Left ("unbound type variable " ++ showInt (tyVarId a));
           Just b ->
             do {
               kinds <-
                 L.mapM (kindBinding ds bounds (S.insert compareTyVar a seen))
                   (S.toList (freeVars b));
               kindIn ds (M.fromList compareTyVar kinds) b
             }
         };
  kindIn :: DataEnv -> Map XTyVar Kind -> XType -> Either String Kind;
  kindIn ds env ty =
    case ty of {
      XVar a ->
        case M.lookup compareTyVar a env of {
          Nothing -> Left ("unbound type variable " ++ showInt (tyVarId a));
          Just k -> Right k
        };
      XBot -> Right Star;
      XBotKind k -> Right k;
      XArrow a b ->
        do {
          ka <- kindIn ds env a;
          kb <- kindIn ds env b;
          if (eqKind ka Star && eqKind kb Star)
          then Right Star
          else Left "function types require kind * arguments"
        };
      XCon c args ->
        do {
          ks <- L.mapM (kindIn ds env) args;
          L.foldM applyKind (D.constructorKind ds c (L.length args)) ks
        };
      XApply f a ->
        do {
          kf <- kindIn ds env f;
          ka <- kindIn ds env a;
          applyKind kf ka
        };
      XForall a bound body ->
        do {
          k <- kindIn ds env bound;
          kindIn ds (M.insert compareTyVar a k env) body
        }
    };
  instantiateField :: Map String XType -> Field -> Either String XType;
  instantiateField env field =
    case field of {
      Parameter a ->
        case M.lookup compareString a env of {
          Nothing -> Left ("unbound data type parameter: " ++ a);
          Just t -> Right t
        };
      Function a b ->
        do {
          x <- instantiateField env a;
          y <- instantiateField env b;
          return (XArrow x y)
        };
      Applied c args ->
        do {
          ts <- L.mapM (instantiateField env) args;
          return (XCon c ts)
        };
      Application f a ->
        do {
          ft <- instantiateField env f;
          at <- instantiateField env a;
          return (apply ft at)
        };
      Quantified n k b ->
        let {
          used = L.foldr (S.union compareTyVar) S.empty (L.map allVars (M.elems env))
        } in
        let {
          a = freshNegative used (0 - 1)
        } in
        do {
          body <- instantiateField (M.insert compareString n (XVar a) env) b;
          return (XForall a (bottomKind k) body)
        }
    }
}
