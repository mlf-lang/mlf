-- Independent Haskell graph oracle. Fixed expectations guard future changes.
-- Optional validation/unification arguments emit every result for exact comparison
-- with GraphDenseProbe.emlf using the same arguments.
module Main (main) where

import Control.Monad (forM_)
import Data.Char (ord)
import Data.Either (isRight)
import Data.List (foldl', intercalate)
import qualified Data.IntMap.Strict as IM
import System.Environment (getArgs)
import MLF.Graph
import GraphValidation (smallGraphs)
import MLF.Kind
import MLF.Syntax (Flag(..))

showValidation :: Either String () -> String
showValidation = either id (const "ok")

showKind :: Kind -> String
showKind Star = "*"
showKind (KArrow a b) = "(" ++ showKind a ++ ">" ++ showKind b ++ ")"

showTag :: Tag -> String
showTag t = case t of
  Bot -> "b"
  BotK k -> "k" ++ showKind k
  Arr a b -> "a" ++ show a ++ "," ++ show b
  Con c ns -> "c" ++ c ++ "[" ++ intercalate "," (map show ns) ++ "]"
  TyCon c k -> "t" ++ c ++ showKind k
  Skolem n k -> "s" ++ show n ++ showKind k
  TyApp a b -> "p" ++ show a ++ "," ++ show b
  Gen n -> "g" ++ show n

showGraph :: Graph -> String
showGraph g = concatMap showNode (IM.toList (nodes g)) ++ "|" ++
  concatMap (\(n,p) -> show n ++ ":" ++ show p ++ ";") (IM.toList (links g)) ++ "|" ++ show (nextId g)
  where
    showNode (n,v) = show n ++ ":" ++ showTag (tag v) ++ ":" ++
      maybe "_" show (binder v) ++ ":" ++ (if flag v == Flexible then "f" else "r") ++ ";"

showUnification :: Either String Graph -> String
showUnification = either ('!':) showGraph

equations :: [[(Int,Int)]]
equations = [[],[(1,2)],[(1,3)],[(2,3)],[(2,2)],[(0,1)],[(1,2),(2,3)],[(2,3),(1,2)],[(3,2),(2,1)]]

unificationInputs :: [(Graph,[(Int,Int)])]
unificationInputs =
  [(g { nodes = IM.mapWithKey (\n v -> v { flag = case n of 1 -> a; 2 -> b; 3 -> c; _ -> flag v }) (nodes g) },eqs)
  | g <- filter (isRight . validateGraph) smallGraphs
  , a <- [Flexible,Rigid], b <- [Flexible,Rigid], c <- [Flexible,Rigid]
  , eqs <- equations]

hash :: Int -> String -> Int
hash = foldl' (\h c -> (h * 65599 + ord c) `rem` 2147483647)

stats :: (Either String a -> String) -> [Either String a] -> String
stats render outcomes = let (count,accepted,checksum) = foldl' step (0::Int,0::Int,0::Int) outcomes in
  intercalate "|" (map show [count,accepted,checksum])
  where
    step (n,accepted,checksum) value =
      let next = hash checksum (show n ++ ":" ++ render value ++ "\n")
      in next `seq` (n+1,accepted + if isRight value then 1 else 0,next)

validation :: [Either String ()]
validation = map validateGraph smallGraphs

unification :: [Either String Graph]
unification = [snd <$> runBuild g (unify eqs) | (g,eqs) <- unificationInputs]

main :: IO ()
main = do
  args <- getArgs
  case args of
    ["validation"] -> forM_ (zip [(0::Int)..] validation) $ \(n,value) -> putStrLn (show n ++ ":" ++ showValidation value)
    ["unification"] -> forM_ (zip [(0::Int)..] unification) $ \(n,value) -> putStrLn (show n ++ ":" ++ showUnification value)
    _ -> do
      putStrLn ("validation|" ++ stats showValidation validation)
      putStrLn ("unification|" ++ stats showUnification unification)
      putStrLn "dense offsets and sparse fallbacks: ok"
