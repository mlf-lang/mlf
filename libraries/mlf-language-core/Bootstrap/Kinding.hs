-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Kinding where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Kind as K;
  import qualified Bootstrap.Data as D;
  kindOf :: DataEnv -> Map String Kind -> SType -> Either String Kind;
  kindOf ds env ty =
    case ty of {
      STVar name ->
        case M.lookup compareString name env of {
          Nothing -> Left ("unbound annotation type variable: " ++ name);
          Just k -> Right k
        };
      SBottom -> Right Star;
      SBottomKind k -> Right k;
      SArrow a b ->
        do {
          annotationType ds env a;
          annotationType ds env b;
          Right Star
        };
      SCon c args ->
        do {
          ks <- mapM (kindOf ds env) args;
          foldM K.applyKind (D.constructorKind ds c (length args)) ks
        };
      STypeApp f a ->
        do {
          kf <- kindOf ds env f;
          ka <- kindOf ds env a;
          K.applyKind kf ka
        };
      SForall _ a bound body ->
        do {
          k <- kindOf ds env bound;
          kindOf ds (M.insert compareString a k env) body
        };
      SQualified _ _ -> Left "class constraints must be translated before kind checking"
    };
  annotationType :: DataEnv -> Map String Kind -> SType -> Either String Unit;
  annotationType ds env ty =
    do {
      k <- kindOf ds env ty;
      if K.eqKind k Star
      then Right Unit
      else case ty of {
             SCon c args ->
               do {
                 D.checkArity ds c (length args);
                 Left "term annotation must have kind *"
               };
             _ -> Left "term annotation must have kind *"
           }
    }
}
