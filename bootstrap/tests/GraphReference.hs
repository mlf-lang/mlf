-- Independent oracle from the maintained Haskell graph and reference unifier.
-- Compare stdout byte-for-byte with GraphConformance.emlf on both backends.
module Main where
import Control.Monad (forM_)
import Data.Either (isRight)
import Data.List (intercalate)
import qualified Data.IntMap.Strict as IM
import MLF.Graph
import MLF.Kind
import MLF.Syntax (Flag(..))
import GraphValidation (smallGraphs)
import GraphUnificationReference (referenceUnify)

showKind :: Kind -> String
showKind Star = "*"
showKind (KArrow a b) = "(" ++ showKind a ++ ">" ++ showKind b ++ ")"
showTag :: Tag -> String
showTag t = case t of
  Bot -> "b"
  BotK k -> "k" ++ showKind k
  Arr a b -> "a" ++ show a ++ "," ++ show b
  Con c xs -> "c" ++ c ++ "[" ++ intercalate "," (map show xs) ++ "]"
  TyCon c k -> "t" ++ c ++ showKind k
  Skolem n k -> "s" ++ show n ++ showKind k
  TyApp a b -> "p" ++ show a ++ "," ++ show b
  Gen n -> "g" ++ show n
showGraph :: Graph -> String
showGraph g = concat [show n ++ ":" ++ showTag (tag v) ++ ":" ++ maybe "_" show (binder v) ++ ":" ++ (if flag v == Flexible then "f" else "r") ++ ";" | (n,v) <- IM.toList (nodes g)] ++ "|" ++ concat [show n ++ ":" ++ show p ++ ";" | (n,p) <- IM.toList (links g)] ++ "|" ++ show (nextId g)

variants :: Graph -> [Graph]
variants g = [g { nodes = IM.mapWithKey (\n v -> v { flag = case n of 1 -> a; 2 -> b; 3 -> c; _ -> flag v }) (nodes g) } | a <- [Flexible,Rigid], b <- [Flexible,Rigid], c <- [Flexible,Rigid]]
equations :: [[(Int,Int)]]
equations = [[],[(1,2)],[(1,3)],[(2,3)],[(2,2)],[(0,1)],[(1,2),(2,3)],[(2,3),(1,2)],[(3,2),(2,1)]]
main :: IO ()
main = do
  putStrLn (map (\g -> if isRight (validateGraph g) then 'v' else 'x') smallGraphs)
  forM_ [g | base <- smallGraphs, isRight (validateGraph base), g <- variants base] $ \g ->
    forM_ equations $ \eqs -> case runBuild g (referenceUnify eqs) of
      Left _ -> putStrLn "!"
      Right (_,result) -> putStrLn (showGraph result)
