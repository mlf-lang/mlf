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
  -- A closed projection's only nonlocal reference in the arrow spine is
  -- the final result. Resolve it on the way back through the argument
  -- binders, so its position respects the closest lexical binding.
  projectionTypeLayout :: XType -> Maybe ((,) Int Int);
  projectionTypeLayout ty = let {
    walk index source = case source of {
      XForall a XBot (XForall r bound (XArrow (XVar input) (XVar output))) ->
        if equalTyVar a input && equalTyVar r output && L.not (equalTyVar a r)
        then case walk (index + 1) bound of {
          Just ((,,) width target selected) -> Just ((,,) width target
            (if selected < 0 && equalTyVar a target then index else selected));
          Nothing -> Nothing
        } else Nothing;
      XForall a XBot (XArrow (XVar input) (XVar output)) ->
        if equalTyVar a input then Just ((,,) (index + 1) output
          (if equalTyVar a output then index else (-1))) else Nothing;
      _ -> Nothing
    }
  } in case walk 0 ty of {
    Just ((,,) width _ selected) -> if width >= 2 && selected >= 0 then Just ((,) width selected) else Nothing;
    Nothing -> Nothing
  };
  freeVars :: XType -> Set XTyVar;
  freeVars = typeVariableSetUsing True (\variable bound body ->
    unionVariables bound (seq body (M.delete compareTyVar variable body)));
  allVars :: XType -> Set XTyVar;
  allVars = typeVariableSet (\variable bound body ->
    let { both = unionVariables bound body } in seq both (M.insert compareTyVar variable () both));
  -- Set union evaluates the left inventory before the right one. Preserve
  -- that order on partially defined types and delayed constructor arguments.
  unionVariables left right = seq left (seq right (M.union compareTyVar left right));
  -- Both inventories use the same ordered tree. Keep the binder operation
  -- explicit and wrap the finished tree once, at the public set boundary.
  typeVariableSet :: (XTyVar -> Map XTyVar () -> Map XTyVar () -> Map XTyVar ()) -> XType -> Set XTyVar;
  typeVariableSet = typeVariableSetUsing False;
  -- In forall a. forall (r >= t). a -> r the two arrow variables
  -- are locally bound. Only t can contribute a free variable.
  typeVariableSetUsing free quantify ty = let {
    variables term = case term of {
      XVar a -> M.singleton a ();
      XBot -> M.empty;
      XBotKind _ -> M.empty;
      XArrow a b -> unionVariables (variables a) (variables b);
      XCon _ arguments -> L.foldr (\argument rest -> unionVariables (variables argument) rest) M.empty arguments;
      XApply f a -> unionVariables (variables f) (variables a);
      XForall a bound body -> let {
        ordinary = quantify a (variables bound) (variables body)
      } in if free then case (,) bound body of {
        (,) XBot (XForall r tail (XArrow (XVar input) (XVar output))) ->
          if equalTyVar a input && equalTyVar r output then
            let { found = variables tail } in seq found (M.delete compareTyVar a found)
          else ordinary;
        _ -> ordinary
      } else ordinary
    }
  } in S.wrap (variables ty);
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
               (alphaForallBodies (M.insert compareTyVar x depth l) (M.insert compareTyVar y depth r)
                  nextDepth x y xt yt));
          _ -> alphaApplications l r depth a b
        }
    };
  alphaForallBodies l r depth a b left right = case (,) left right of {
    (,) (XForall x xb xt) (XForall y yb yt) ->
      alphaIn l r depth xb yb && case (,) xt yt of {
        (,) (XArrow (XVar ix) (XVar rx)) (XArrow (XVar iy) (XVar ry)) ->
          if equalTyVar ix a && equalTyVar iy b && equalTyVar rx x && equalTyVar ry y
          then equalTyVar a x == equalTyVar b y
          else alphaIn (M.insert compareTyVar x depth l) (M.insert compareTyVar y depth r) (depth + 1) xt yt;
        _ -> alphaIn (M.insert compareTyVar x depth l) (M.insert compareTyVar y depth r) (depth + 1) xt yt
      };
    _ -> alphaIn l r depth left right
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
    case ty of {
      XVar a -> seq a (visitKind ds bounds S.empty a);
      XBot -> Right Star;
      XBotKind k -> Right k;
      XCon name [] -> Right (D.constructorKind ds name 0);
      _ -> case projectionTypeLayout ty of {
        Just _ -> Right Star;
        Nothing -> kindFromVariables ds bounds S.empty ty
      }
    };
  -- The free-variable set already has distinct ordered keys. Resolve them
  -- in ascending order so competing environment errors keep their priority.
  kindFromVariables ds bounds seen ty = let {
    resolve tree = case tree of {
      MapEmpty -> Right M.empty;
      MapNode size variable _ left right -> do {
        before <- resolve left;
        kind <- visitKind ds bounds seen variable;
        after <- resolve right;
        Right (M.node size variable kind before after)
      }
    }
  } in case freeVars ty of { Set variables -> do {
    kinds <- resolve variables;
    kindIn ds kinds ty
  } };
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
           Just b -> case b of {
             XBot -> Right Star;
             XBotKind k -> Right k;
             XCon name [] -> Right (D.constructorKind ds name 0);
             _ -> kindFromVariables ds bounds (S.insert compareTyVar a seen) b
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
      XCon c ((:) arg []) -> unaryConstructorKinds ds env ((:) c []) arg;
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
          let { scope = M.insert compareTyVar a k env };
          case body of {
            XForall r tail inner -> do {
              result <- kindIn ds scope tail;
              let { ordinary = kindIn ds (M.insert compareTyVar r result scope) inner };
              case inner of {
                XArrow (XVar input) (XVar output) ->
                  if equalTyVar a input && equalTyVar r output then
                    if eqKind result Star && (equalTyVar a r || eqKind k Star)
                    then Right Star else Left "function types require kind * arguments"
                  else ordinary;
                _ -> ordinary
              }
            };
            _ -> kindIn ds scope body
          }
        }
    };
  -- Check the spine's argument first, then apply constructors from the
  -- inside out. Applying a constructor to its own result once validates
  -- all later adjacent repetitions because its codomain is fixed.
  unaryConstructorKinds ds env names ty = case ty of {
    XCon name ((:) arg []) -> unaryConstructorKinds ds env ((:) name names) arg;
    _ -> do {
      base <- kindIn ds env ty;
      applyUnaryKinds ds base names
    }
  };
  applyUnaryKinds ds base names = case names of {
    [] -> Right base;
    (:) name rest -> let { constructor = D.constructorKind ds name 1 } in do {
      result <- applyKind constructor base;
      case rest of {
        (:) next more -> if eqString name next then do {
          repeated <- applyKind constructor result;
          applyUnaryKinds ds repeated (L.dropWhile (eqString name) more)
        } else applyUnaryKinds ds result rest;
        [] -> Right result
      }
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
