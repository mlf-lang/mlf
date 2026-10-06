module MLF.Kinding (kindOf, annotationType) where

import Control.Monad (foldM, unless)
import qualified Data.Map.Strict as Map
import qualified MLF.Data as D
import MLF.Kind
import qualified MLF.Syntax as S

kindOf :: D.DataEnv -> Map.Map String Kind -> S.Type -> Either String Kind
kindOf ds env ty = case ty of
  S.TVar n -> maybe (Left ("unbound annotation type variable: " ++ n)) Right (Map.lookup n env)
  S.Bottom -> pure Star
  S.BottomKind k -> pure k
  S.Arrow a b -> do
    annotationType ds env a
    annotationType ds env b
    pure Star
  S.Con c args -> mapM (kindOf ds env) args >>= foldM applyKind (D.constructorKind ds c (length args))
  S.TypeApp f a -> do
    kf <- kindOf ds env f
    ka <- kindOf ds env a
    applyKind kf ka
  S.Forall _ a bound body -> do
    k <- kindOf ds env bound
    kindOf ds (Map.insert a k env) body
  S.Qualified _ _ -> Left "class constraints must be translated before kind checking"

annotationType :: D.DataEnv -> Map.Map String Kind -> S.Type -> Either String ()
annotationType ds env ty = do
  k <- kindOf ds env ty
  unless (k == Star) $ case ty of
    S.Con c args -> D.checkArity ds c (length args) >> Left "term annotation must have kind *"
    _ -> Left "term annotation must have kind *"
