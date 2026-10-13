-- Behavioral observations use the independent interpreter and native backend.
-- Structural checks separately prove that the new path runs without copying
-- a shared field computation or introducing duplicate binder identities.
module ConstructorProjection (constructorProjectionTests) where

import Control.Monad (unless, when)
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import Backends (Backends, Entry (..), Input (..))
import qualified Backends as B
import MLF.Compiler (compile, compiledTerm)
import qualified MLF.LLVM.Analysis as A
import qualified MLF.LLVM.Optimize as O
import qualified MLF.Primitive as P
import qualified MLF.X.Syntax as X

children :: X.Erased -> [X.Erased]
children expression = case expression of
  X.EAbs _ b -> [b]
  X.EApp f a -> [f,a]
  X.ELet _ a b -> [a,b]
  X.ELetRec ds b -> map snd ds ++ [b]
  X.ECase a branches -> a : [b | X.ErasedAlternative _ b <- branches]
  _ -> []

countPrimitive :: P.Primitive -> X.Erased -> Int
countPrimitive wanted expression = (case expression of
  X.EPrimitive primitive | primitive == wanted -> 1
  _ -> 0) + sum (map (countPrimitive wanted) (children expression))

countCase :: String -> X.Erased -> Int
countCase constructor expression = (case expression of
  X.ECase _ branches | any matches branches -> 1
  _ -> 0) + sum (map (countCase constructor) (children expression))
  where
    matches (X.ErasedAlternative (X.ConstructorPattern c _) _) = c == constructor
    matches _ = False

binders :: X.Erased -> [X.Name]
binders expression = (case expression of
  X.EAbs n _ -> [n]
  X.ELet n _ _ -> [n]
  X.ELetRec ds _ -> map fst ds
  X.ECase _ branches -> concat [X.patternNames p | X.ErasedAlternative p _ <- branches]
  _ -> []) ++ concatMap binders (children expression)

constructorProjectionTests :: Backends -> [(String,IO ())]
constructorProjectionTests backends =
  [("constructor projections: demanded field fails after preceding effects", do
      term <- compiledTerm <$> either (fail . show) pure (compile "<constructor projection failure>"
        ("data Box = Box Int; main = let box = Box (panic \"demanded field\") in " ++
         "do { putStrLn \"before\"; case box of { Box n -> printInt n } };"))
      result <- B.execute backends IOEntry (Input "" False) term
      unless (either ((== "demanded field") . show) (const False) (B.outcome result) &&
        B.events result == [B.Write "before\n"]) (fail (show result)))] ++
  [("constructor projections: " ++ label, do
      term <- compiledTerm <$> either (fail . show) pure (compile "<constructor projection>" source)
      let original = X.erase term
          optimized = O.optimize original
          names = binders optimized
      unless (Set.null (O.free optimized) && length names == Set.size (Set.fromList names))
        (fail "constructor projection changed scope or duplicated a binder identity")
      when (label == "shared fields and lazy poison") $ do
        unless (countCase "Cell" original == 2 && countCase "Cell" optimized == 0)
          (fail "known-constructor projection path did not remove both cases")
        unless (countPrimitive P.ReadInt optimized == 1)
          (fail "a shared field computation was duplicated or discarded")
      when (label == "captured function becomes a known worker") $ do
        unless (countCase "Ops" optimized == 0 && any capturedWorker (Map.elems (A.analyze optimized)))
          (fail "lifted function field did not expose a captured native worker")
        unless (countPrimitive P.ReadInt optimized == 1)
          (fail "function capture was duplicated")
      result <- B.execute backends IOEntry (Input "" False) term
      either (fail . show) pure (B.outcome result)
      unless (B.output result == expected) (fail (show result)))
    | (label,source,expected) <- sources]
  where
    capturedWorker f = not (null (A.captures f)) && length (A.parameters f) == 1 &&
      countPrimitive P.AddInt (A.functionBody f) >= 6
    sources =
      [ ("shared fields and lazy poison",
          "data Cell = Cell Int Int; main = let cell = Cell (readInt \"42\") (panic \"unused field\") in " ++
          "case cell of { Cell x _ -> case cell of { Cell y _ -> do { printInt x; printInt y } } };",
          "42\n42\n")
      , ("captured function becomes a known worker",
          "data Ops = Ops (Int -> Int); main = let saved = readInt \"19\" in " ++
          "let ops = Ops (\\n -> saved + n + 1 + 1 + 1 + 1 + 1) in " ++
          "case ops of { Ops f -> case ops of { Ops g -> do { putStrLn \"before\"; printInt (f 18); printInt (g 17) } } };",
          "before\n42\n41\n")
      , ("recursive data keeps its knot", unlines
          ["data Stream = Stream Int Stream", "ones : Stream", "ones = Stream (readInt \"42\") ones",
           "main = case ones of", "  Stream x next -> case next of", "    Stream y _ -> do", "      printInt x", "      printInt y"],
          "42\n42\n")
      , ("mutually recursive dictionary methods",
          "class Count a where { first : a -> Int; second : a -> Int }; " ++
          "instance Count Int where { first = \\n -> if n == 0 then 42 else second (n - 1); " ++
          "second = \\n -> if n == 0 then 42 else first (n - 1) }; " ++
          "main = do { printInt (first 10); printInt (second 11) };", "42\n42\n")
      , ("partial constructors remain lazy",
          "data Triple = Triple Int Int Int; main = let partial = Triple (panic \"unused partial field\") in " ++
          "do { seq partial (putStrLn \"partial\"); case partial 19 23 of { Triple _ a b -> printInt (a + b) } };",
          "partial\n42\n")
      , ("same spelling in disjoint scopes",
          "data Cell = Cell Int; main = let cell = Cell (readInt \"19\") in " ++
          "let pick = \\ignored -> case cell of { Cell x -> x } in " ++
          "let cell = Cell (readInt \"23\") in do { printInt (pick ()); case cell of { Cell y -> printInt y } };",
          "19\n23\n")
      , ("escaping constructor shares its fields",
          "data Cell = Cell Int Int; main = let cell = Cell (readInt \"42\") (panic \"unused escaping field\") in " ++
          "case cell of { Cell x _ -> do { printInt x; escaped <- return cell; case escaped of { Cell y _ -> printInt y } } };",
          "42\n42\n")
      , ("default branch preserves its bound constructor",
          "data Choice = One Int | Two Int; main = let choice = Two (readInt \"42\") in " ++
          "case choice of { One _ -> printInt 0; other -> case other of { Two n -> printInt n; _ -> printInt 1 } };",
          "42\n")
      ]
