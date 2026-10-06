-- | Hygienic, syntax-only lowering of do blocks. The in-scope 'bind' operation
-- is resolved by the ordinary language and class machinery afterwards.
module MLF.Desugar (desugarDo) where

import Control.Monad.State.Strict
import Data.Char (isAlphaNum)
import qualified Data.Set as Set
import MLF.Syntax

desugarDo :: Expr -> Expr
desugarDo expression = evalState (go expression) (0 :: Int, used)
  where
    used = Set.fromList (words (map token (show expression)))
    token c | isAlphaNum c || c `elem` "_'" = c
            | otherwise = ' '

    fresh :: State (Int,Set.Set String) String
    fresh = do
      (i,names) <- get
      let name = "doValue" ++ show i
      put (i+1,Set.insert name names)
      if name `Set.member` names then fresh else pure name

    go e = case e of
      Lam n annotation body -> Lam n annotation <$> go body
      App f a -> App <$> go f <*> go a
      Let n a b -> Let n <$> go a <*> go b
      Ann a ty -> (`Ann` ty) <$> go a
      Case a branches -> Case <$> go a <*> mapM (\(Alternative p b) -> Alternative p <$> go b) branches
      Do statements result -> go result >>= block statements
      LetRec definitions body -> LetRec <$> mapM (\(n,ty,a) -> (\a' -> (n,ty,a')) <$> go a) definitions <*> go body
      Checked ty a -> Checked ty <$> go a
      _ -> pure e

    block [] result = pure result
    block (statement:rest) result = do
      continuation <- block rest result
      case statement of
        DoLet n annotation value -> do
          value' <- go value
          pure (Let n (maybe value' (Ann value') annotation) continuation)
        DoThen action -> fresh >>= \n -> binding (DefaultPattern (Just n)) action continuation
        DoBind pattern' action -> binding pattern' action continuation

    binding pattern' action continuation = do
      action' <- go action
      (n,body) <- case pattern' of
        DefaultPattern (Just name) -> pure (name,continuation)
        DefaultPattern Nothing -> fresh >>= \name -> pure (name,continuation)
        ConstructorPattern _ _ -> do
          name <- fresh
          pure (name,Case (Var name) [Alternative pattern' continuation])
      pure (App (App (Var "bind") action') (Lam n Nothing body))
