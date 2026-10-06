module Computations (computationTests, hygieneTests) where

import Control.Monad (unless)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified MLF.X.Check as C
import qualified MLF.X.Syntax as X
import qualified MLF.X.Type as T

type Test = (String, IO ())

assert :: Bool -> String -> IO ()
assert p message = unless p (fail message)

reject :: Show a => Either e a -> IO ()
reject result = case result of Left _ -> pure (); Right value -> fail ("unexpected success: " ++ show value)

v :: Int -> T.Type
v = T.Var . T.TyVar
allT :: Int -> T.Type -> T.Type -> T.Type
allT = T.Forall . T.TyVar
int, bool, identity :: T.Type
int = T.Con "Int" []
bool = T.Con "Bool" []
identity = allT 0 T.Bot (T.Arrow (v 0) (v 0))

sameType :: T.Type -> T.Type -> IO ()
sameType actual expected = assert (T.alphaEq actual expected)
  ("expected " ++ show expected ++ ", got " ++ show actual)

computationTests :: [Test]
computationTests =
  [ computation "Inst-Reflex" Map.empty X.Refl identity identity
  , computation "Inst-Bot" Map.empty (X.Bottom identity) T.Bot identity
  , computation "Inst-Hyp" (Map.singleton b identity) (X.Hyp b) identity (T.Var b)
  , computation "Inst-Inner" Map.empty (X.Inner (X.Bottom int)) identity
      (T.Forall a int (T.Arrow (T.Var a) (T.Var a)))
  , computation "Inst-Outer" Map.empty (X.Outer a (X.typeApplication (T.Var a)))
      (allT 0 T.Bot (allT 1 T.Bot (T.Arrow (v 0) (v 1)))) identity
  , computation "Inst-Quant-Elim" Map.empty X.Elim
      (allT 0 int (T.Arrow (v 0) (v 0))) (T.Arrow int int)
  , computation "Inst-Quant-Intro" Map.empty (X.Intro a) int (T.Forall a T.Bot int)
  , computation "Inst-Trans / System F application" Map.empty (X.typeApplication int) identity (T.Arrow int int)
  , computation "outer alpha conversion" Map.empty (X.Outer b X.Refl) identity identity
  , ("Inst-Hyp checks its bound", reject (C.checkComputation (Map.singleton a int) (X.Hyp a) bool))
  , ("Inst-Hyp requires a binding", reject (C.checkComputation Map.empty (X.Hyp a) int))
  , ("Inst-Bot requires bottom source", reject (C.checkComputation Map.empty (X.Bottom bool) int))
  , ("elimination requires a quantifier", reject (C.checkComputation Map.empty X.Elim int))
  , ("inner does not cross arrows", reject (C.checkComputation Map.empty (X.Inner X.Elim) (T.Arrow identity identity)))
  , ("introduction cannot capture", reject (C.checkComputation (Map.singleton a T.Bot) (X.Intro a) (T.Var a)))
  , ("outer cannot capture", reject (C.checkComputation (Map.singleton b T.Bot) (X.Outer b X.Refl)
      (T.Forall a T.Bot (T.Arrow (T.Var a) (T.Var b)))))
  , ("cyclic environments rejected", reject (C.checkComputation (Map.fromList [(a,T.Var b),(b,T.Var a)]) X.Refl int))
  , ("malformed term environment rejected", reject (C.infer (C.Env Map.empty (Map.singleton (X.Name 0 "x") (T.Var a))) (X.VarTerm (X.Name 0 "x"))))
  ]
  where a = T.TyVar 0; b = T.TyVar 1

computation :: String -> C.TypeEnv -> X.Computation -> T.Type -> T.Type -> Test
computation label env phi source expected = (label,
  either fail (`sameType` expected) (C.checkComputation env phi source))

hygieneTests :: [Test]
hygieneTests =
  [ ("capture-avoiding substitution", do
      let t = T.substitute (T.TyVar 0) (v 1) (allT 1 T.Bot (T.Arrow (v 0) (v 1)))
      sameType t (allT 2 T.Bot (T.Arrow (v 1) (v 2)))
      assert (T.freeVars t == Set.singleton (T.TyVar 1)) "free variable captured")
  , ("quantifier does not scope over its own bound", do
      let t = T.substitute (T.TyVar 0) int (allT 0 (v 0) (v 0))
      sameType t (allT 0 int (v 0)))
  , ("alpha-equivalence tracks shadowing", do
      assert (T.alphaEq (allT 0 T.Bot (allT 0 T.Bot (v 0))) (allT 1 T.Bot (allT 2 T.Bot (v 2)))) "shadowing was not recognized"
      assert (not (T.alphaEq (allT 0 T.Bot (allT 0 T.Bot (v 0))) (allT 1 T.Bot (allT 2 T.Bot (v 1))))) "shadowing changed binding")
  , ("type quantifiers have lexical scope", do
      either fail pure (C.wellFormed (Map.singleton (T.TyVar 0) int) identity))
  , ("xMLF does not identify inert or alias bounds", do
      assert (not (T.alphaEq (allT 0 int (v 0)) int)) "unsound type equality"
      assert (not (T.alphaEq identity (allT 0 T.Bot (allT 1 (v 0) (T.Arrow (v 1) (v 0)))))) "alias bound erased")
  ]
