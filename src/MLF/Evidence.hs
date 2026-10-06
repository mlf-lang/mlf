-- | Dictionary proof search. This module never instantiates the inference
-- graph: a wanted predicate must already determine a matching instance head.
module MLF.Evidence (resolveDictionary) where

import Control.Monad (foldM, unless)
import Data.List (find)
import Data.Maybe (mapMaybe)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified MLF.Data as D
import MLF.Kind
import MLF.Syntax (EvidenceRole (..))
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T
import qualified MLF.X.Check as C
import MLF.X.Pretty (prettyType)

type Candidate = (EvidenceRole, X.Name, T.Type)

resolveDictionary :: D.DataEnv -> C.TypeEnv -> [Candidate] -> T.Type -> Either String X.Term
resolveDictionary ds gamma candidates wanted = do
  term <- search [] wanted
  actual <- C.inferWithData ds (C.Env gamma (Map.fromList [(n,t) | (_,n,t) <- candidates])) term
  unless (T.alphaEq actual wanted) (Left "dictionary evidence has the wrong type")
  pure term
  where
    search seen goal
      | any (T.alphaEq goal) seen = Left ("cyclic dictionary resolution: " ++ prettyType goal)
      | otherwise = case matches GivenEvidence goal of
          (t,[]):_ -> pure t
          _ -> case find (T.alphaEq goal . snd) givenProofs of
            Just (term,_) -> pure term
            Nothing -> case matches InstanceEvidence goal of
              [] -> missing goal
              [(t,context)] -> foldM (\f p -> X.App f <$> search (goal:seen) p) t context
              _ -> Left ("overlapping dictionary instances: " ++ prettyType goal)
    -- Project forward from complete given dictionaries. Matching only a
    -- superclass result loses parameters: MonadState s m => Monad m must
    -- obtain s from the given dictionary, not guess it from Monad m.
    givenProofs = close [] [(X.VarTerm n,t,Set.empty) | (GivenEvidence,n,t) <- candidates]
    close _ [] = []
    close seen ((proof,ty,path):rest)
      | any (T.alphaEq ty) seen = close seen rest
      | otherwise = (proof,ty) : close (ty:seen) (rest ++ projections)
      where
        projections = mapMaybe project [(n,t) | (SuperclassEvidence,n,t) <- candidates, n `Set.notMember` path]
        project candidate@(name,_) = either (const Nothing) Just $ do
          (selector,context,result) <- specializeAt superclassArgument ty candidate
          case context of
            [argument] | T.alphaEq argument ty -> pure (X.App selector proof,result,Set.insert name path)
            _ -> Left "invalid superclass selector"
    superclassArgument [argument] _ = pure argument
    superclassArgument _ _ = Left "superclass selectors require exactly one dictionary"
    missing goal = Left ("no instance or given constraint for " ++ prettyType goal ++ "; ambiguous uses need a type annotation")
    matches role goal = mapMaybe (specialize goal) [(n,t) | (r,n,t) <- candidates, r == role]
    specialize goal candidate = either (const Nothing) Just $ do
      (term,context,_) <- specializeAt (\_ headType -> pure headType) goal candidate
      pure (term,context)
    specializeAt select actual (name,scheme) = do
      let (variables,body) = quantifiers scheme
          (context,headType) = arguments body
          flexible = Map.fromList variables
      patternType <- select context headType
      substitution <- match flexible Map.empty patternType actual
      types <- mapM (\(a,_) -> maybe (Left "undetermined instance parameter") Right (Map.lookup a substitution)) variables
      let occupied = Set.unions (T.allVars body : map T.allVars types)
          freshVariables = take (length variables) [a | i <- [-1,-2..], let a = T.TyVar i, a `Set.notMember` occupied]
          -- Rename before replacing, so one argument cannot be rewritten by
          -- a later substitution when caller and scheme binder IDs coincide.
          replace t =
            let renamed = foldl (\b ((a,_),fresh) -> T.substitute a (T.Var fresh) b) t (zip variables freshVariables)
            in foldl (\b (a,value) -> T.substitute a value b) renamed (zip freshVariables types)
          term = foldl (\t a -> X.instantiate t (X.typeApplication a)) (X.VarTerm name) types
      pure (term,map replace context,replace headType)
    quantifiers (T.Forall a bound body)
      | Just k <- bottom bound = let (vs,t) = quantifiers body in ((a,k):vs,t)
    quantifiers t = ([],t)
    bottom T.Bot = Just Star
    bottom (T.BotKind k) = Just k
    bottom _ = Nothing
    arguments (T.Arrow a b) = let (as,result) = arguments b in (a:as,result)
    arguments t = ([],t)
    match flexible substitution patternType actual = case patternType of
      T.Var a | Just expectedKind <- Map.lookup a flexible -> do
        k <- T.kindOf ds gamma actual
        unless (k == expectedKind) (Left "instance parameter kind mismatch")
        case Map.lookup a substitution of
          Nothing -> pure (Map.insert a actual substitution)
          Just previous -> if T.alphaEq previous actual then pure substitution else Left "instance parameter mismatch"
      _ | T.alphaEq patternType actual && Set.null (T.freeVars patternType `Set.intersection` Map.keysSet flexible) -> pure substitution
      T.Con c xs | T.Con d ys <- actual, c == d, length xs == length ys ->
        foldM (\s (a,b) -> match flexible s a b) substitution (zip xs ys)
      T.Arrow a b | T.Arrow c d <- actual -> match flexible substitution a c >>= \s -> match flexible s b d
      _ | Just (f,a) <- T.applicationView patternType, Just (g,b) <- T.applicationView actual ->
        match flexible substitution f g >>= \s -> match flexible s a b
      _ -> Left "instance head does not match"
