-- Paper acceptance is transcribed from the MLF column of Figure 12,
-- page 26, of A Quick Look at Impredicativity (Serrano et al., ICFP 2020):
-- https://simon.peytonjones.org/assets/pdfs/impredicativity.pdf
-- Regression expectations differ for A8's explicit signature, which the
-- authors' camlf reference prototype also rejects.
-- See docs/figure12-results.txt for the source-language encoding and caveats.
module Figure12 (Case (..), cases, program, assumptions) where

import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import MLF.Parser (parseExpr)
import MLF.Desugar (desugarDo)
import qualified MLF.Syntax as S

data Case = Case
  { caseId :: String
  , expression :: String
  , paperAcceptance :: Bool
  , expectedAcceptance :: Bool
  , localSignatures :: [(String, String)]
  } deriving Show

-- These are hypotheses, not inferred implementations. In particular, using
-- an unannotated implementation of choose would change the question tested.
signatures :: [(String, String)]
signatures =
  [ ("id", "forall a. a -> a")
  , ("choose", "forall a. a -> a -> a")
  , ("nil", "forall p. List p")
  , ("ids", "List (forall a. a -> a)")
  , ("auto", "(forall a. a -> a) -> (forall a. a -> a)")
  , ("auto'", "forall b. (forall a. a -> a) -> b -> b")
  , ("poly", "(forall a. a -> a) -> Pair Int Bool")
  , ("app", "forall a b. (a -> b) -> a -> b")
  , ("revapp", "forall a b. a -> (a -> b) -> b")
  , ("runST", "forall d. (forall s. ST s d) -> d")
  , ("argST", "forall s. ST s Int")
  , ("length", "forall p. List p -> Int")
  , ("tail", "forall p. List p -> List p")
  , ("head", "forall p. List p -> p")
  , ("single", "forall p. p -> List p")
  , ("cons", "forall p. p -> List p -> List p")
  , ("append", "forall p. List p -> List p -> List p")
  , ("inc", "Int -> Int")
  , ("map", "forall p q. (p -> q) -> List p -> List q")
  , ("compose", "forall a b c. (b -> c) -> (a -> b) -> a -> c")
  , ("pair", "forall a b. a -> b -> Pair a b")
  ]

cases :: [Case]
cases =
  [ yes "A1" "\\x y -> y"
  , yes "A2" "choose id"
  , yes "A3" "choose nil ids"
  , yes "A4" "\\(x : forall a. a -> a) -> x x"
  , yes "A5" "id auto"
  , yes "A6" "id auto'"
  , yes "A7" "choose id auto"
  -- Preserve the table's acceptance claim separately from the regression
  -- expectation for forall b. (forall a. a -> a) -> b -> b.
  -- See docs/figure12-a8-reference.txt for the independent reproduction.
  , (yes "A8" "choose id auto'") { expectedAcceptance = False }
  , given [("f", "forall a. (a -> a) -> List a -> a")]
      (yes "A9" "f (choose id) ids")
  , yes "A10.1" "poly id"
  , yes "A10.2" "poly (\\x -> x)"
  , yes "A10.3" "id poly (\\x -> x)"
  , given [("k", "forall a. a -> List a -> Int"),
           ("xs", "List ((forall a. a -> a) -> Pair Int Bool)")]
      (no "A11" "k (\\f -> pair (f 1) (f True)) xs")
  , yes "A12.1" "poly id"
  , yes "A12.2" "app poly id"
  , yes "A12.3" "revapp id poly"
  , yes "A13.1" "app runST argST"
  , yes "A13.2" "revapp argST runST"
  , yes "B1.1" "length ids"
  , yes "B1.2" "tail ids"
  , yes "B1.3" "head ids"
  , yes "B1.4" "single id"
  , yes "B2" "cons id ids"
  , yes "B3" "cons (\\x -> x) ids"
  , yes "B4" "append (single inc) (single id)"
  , yes "B5" "append (single id) ids"
  , yes "B6" "map poly (single id)"
  , yes "B7.1" "map head (single ids)"
  , yes "B7.2" "head ids True"
  , no "C1a" "\\f -> pair (f 1) (f True)"
  , yes "C1b" "\\(f : forall a. a -> a) -> pair (f 1) (f True)"
  , given [("g", "((forall a. a -> a) -> Pair Int Bool) -> Char")]
      (no "C1c" "g (\\f -> pair (f 1) (f True))")
  , given [("r", "(forall a. a -> (forall b. b -> b)) -> Int")]
      (yes "C2" "r (\\x y -> y)")
  , given etaSignatures (no "E1a" "k h lst")
  , given etaSignatures (yes "E1b" "k (\\x -> h x) lst")
  , yes "E2a" "\\x -> poly x"
  , yes "E2b" "(\\x -> poly x) : (forall a. a -> a) -> Pair Int Bool"
  , yes "E3a" "app poly id"
  , yes "E3b" "app (\\x -> poly x) id"
  , yes "E4a" "map poly ids"
  , yes "E4b" "map (\\x -> poly x) ids"
  , yes "E5a" "compose poly head"
  , yes "E5b" "\\xs -> poly (head xs)"
  ]
  where
    yes n e = Case n e True True []
    no n e = Case n e False False []
    given ss c = c { localSignatures = ss }
    etaSignatures =
      [ ("k", "forall a. a -> List a -> a")
      , ("h", "Int -> (forall a. a -> a)")
      , ("lst", "List (forall a. Int -> a -> a)")
      ]

freeNames :: S.Expr -> Set.Set String
freeNames e = case e of
  S.Var x -> Set.singleton x
  S.Constructor _ -> Set.empty
  S.Lam x _ b -> Set.delete x (freeNames b)
  S.App a b -> freeNames a `Set.union` freeNames b
  S.Let x a b -> freeNames a `Set.union` Set.delete x (freeNames b)
  S.Ann a _ -> freeNames a
  S.IntLit _ -> Set.empty
  S.DoubleLit _ -> Set.empty
  S.BoolLit _ -> Set.empty
  S.StringLit _ -> Set.empty
  S.Primitive _ -> Set.empty
  S.Wanted _ candidates -> Set.fromList (map snd candidates)
  S.Checked _ a -> freeNames a
  S.Do _ _ -> freeNames (desugarDo e)
  S.LetRec ds b -> Set.unions (freeNames b : [freeNames a | (_,_,a) <- ds])
    `Set.difference` Set.fromList [n | (n,_,_) <- ds]
  S.Case a bs -> freeNames a `Set.union` Set.unions
    [freeNames b `Set.difference` Set.fromList (bound p) | S.Alternative p b <- bs]
    where
      bound (S.ConstructorPattern _ ns) = [n | Just n <- ns]
      bound (S.DefaultPattern n) = [x | Just x <- [n]]

assumptions :: Case -> Either String [(String, String)]
assumptions c = do
  e <- parseExpr (caseId c) (expression c)
  let env = Map.fromList (signatures ++ localSignatures c)
      lookupSignature x = case Map.lookup x env of
        Nothing -> Left ("fixture has no signature for " ++ x)
        Just s -> Right (x, s)
  mapM lookupSignature (Set.toAscList (freeNames e))

-- The compiler has a closed-term API. Closing with annotated lambda binders
-- supplies exactly the declared hypotheses, without annotating any local
-- lambda or application in the expression under test. The compiler desugars
-- each parameter annotation into a coercion and a polymorphic let binding.
-- This tests the whole wrapper as well as the expression, including erasure.
program :: Case -> Either String String
program c = do
  ss <- assumptions c
  pure (foldr (\(x,s) e -> "\\(" ++ x ++ " : " ++ s ++ ") ->\n" ++ e)
              (expression c) ss)
