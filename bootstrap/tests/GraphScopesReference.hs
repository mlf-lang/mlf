module Main where
import Control.Monad (forM_, unless)
import Data.List (intercalate)
import qualified Data.IntMap.Strict as IM
import qualified Data.IntSet as IS
import qualified Data.Map.Strict as Map
import qualified Data.Set as Set
import qualified MLF.Graph as G
import qualified MLF.Graph.Solver as Solver
import MLF.Kind
import MLF.Syntax (Flag(..))

showKind :: Kind -> String
showKind Star = "*"
showKind (KArrow a b) = "(" ++ showKind a ++ ">" ++ showKind b ++ ")"
showTag :: G.Tag -> String
showTag t = case t of
  G.Bot -> "b"; G.BotK k -> "k" ++ showKind k
  G.Arr a b -> "a" ++ show a ++ "," ++ show b
  G.Con c xs -> "c" ++ c ++ "[" ++ intercalate "," (map show xs) ++ "]"
  G.TyCon c k -> "t" ++ c ++ showKind k
  G.Skolem n k -> "s" ++ show n ++ showKind k
  G.TyApp a b -> "p" ++ show a ++ "," ++ show b
  G.Gen n -> "g" ++ show n
showIds :: IM.IntMap Int -> String
showIds table = concat [show n ++ ":" ++ show p ++ ";" | (n,p) <- IM.toList table]
showGraph :: G.Graph -> String
showGraph g = concat [show n ++ ":" ++ showTag (G.tag v) ++ ":" ++ maybe "_" show (G.binder v) ++ ":" ++ (if G.flag v == Flexible then "f" else "r") ++ ";" | (n,v) <- IM.toList (G.nodes g)] ++ "|" ++ showIds (G.links g) ++ "|" ++ show (G.nextId g)
result :: String -> Either String G.Graph -> IO ()
result label outcome = putStrLn (label ++ "|" ++ either (const "!") showGraph outcome)
scoped :: G.Graph
scoped = G.Graph (IM.fromList
  [(0,G.Node (G.Gen 1) Nothing Flexible),(1,G.Node (G.Con "Unit" []) (Just 0) Rigid)
  ,(2,G.Node (G.Gen 3) (Just 0) Flexible),(3,G.Node (G.Arr 4 5) (Just 2) Rigid)
  ,(4,G.Node G.Bot (Just 3) Rigid),(5,G.Node G.Bot (Just 3) Flexible)
  ,(6,G.Node (G.Gen 7) (Just 0) Flexible),(7,G.Node (G.Arr 8 9) (Just 6) Flexible)
  ,(8,G.Node G.Bot (Just 7) Flexible),(9,G.Node (G.Con "Int" []) (Just 7) Rigid)]) IM.empty 10
frontier :: G.Graph
frontier = scoped { G.nodes = IM.adjust (\v -> v { G.binder = Just 0, G.flag = Flexible }) 4 (G.nodes scoped) }
branching :: G.Graph
branching = G.Graph (IM.fromList (concat
  [[(2*n,G.Node (G.Gen (2*n+1)) (fmap (*2) (parent n)) Flexible)
   ,(2*n+1,G.Node G.Bot (Just (2*n)) Flexible)] | n <- [0..50]])) IM.empty 102
  where parent n | n == 0 = Nothing
                 | n == 41 = Just 0
                 | n == 31 = Just 4
                 | otherwise = Just (n-1)
closed :: Flag -> Int -> String -> G.Graph
closed f b rightName = G.Graph (IM.fromList
  [(0,G.Node (G.Gen 1) Nothing Flexible),(1,G.Node (G.Con "Unit" []) (Just 0) Rigid)
  ,(2,G.Node (G.Gen 3) (Just 0) Flexible),(3,G.Node (G.Arr 4 4) (Just 2) Flexible)
  ,(4,G.Node G.Bot (Just b) f),(5,G.Node (G.Gen 6) (Just 0) Flexible)
  ,(6,G.Node (G.Arr 7 8) (Just 5) Flexible),(7,G.Node (G.Con "Int" []) (Just 6) Rigid)
  ,(8,G.Node (G.Con rightName []) (Just 6) Rigid)]) IM.empty 9
closedGraft :: G.Graph
closedGraft = G.Graph (IM.fromList
  [(0,G.Node (G.Gen 1) Nothing Flexible),(1,G.Node (G.Con "Unit" []) (Just 0) Rigid)
  ,(2,G.Node (G.Gen 3) (Just 0) Flexible),(3,G.Node (G.Arr 4 5) (Just 2) Rigid)
  ,(4,G.Node (G.Con "Int" []) (Just 3) Rigid),(5,G.Node (G.Con "Bool" []) (Just 3) Rigid)
  ,(6,G.Node (G.Gen 7) (Just 0) Flexible),(7,G.Node G.Bot (Just 6) Flexible)]) IM.empty 8
graftChain :: Flag -> G.Graph
graftChain parentFlag = closedGraft { G.nodes = IM.union (IM.fromList
  [(6,G.Node (G.Gen 8) (Just 0) Flexible),(7,G.Node G.Bot (Just 8) Flexible)
  ,(8,G.Node (G.Arr 7 9) (Just 6) parentFlag),(9,G.Node (G.Con "Int" []) (Just 8) Rigid)])
  (G.nodes closedGraft), G.nextId = 10 }
replaceTarget :: G.Node -> G.Graph
replaceTarget value = closedGraft { G.nodes = IM.insert 7 value (G.nodes closedGraft) }
checkDemand :: IO ()
checkDemand = do
  unless (not (G.inert closedGraft 7) && not (G.inert (replaceTarget (G.Node (G.BotK (KArrow Star Star)) (Just 6) Flexible)) 7))
    (fail "bottom inertness changed")
  putStrLn "bottom short-circuit: ok"
  unless (G.permission closedGraft 7 == G.Green && G.permission (graftChain Flexible) 7 == G.Green &&
          G.permission (graftChain Rigid) 7 == G.Red && G.permission (replaceTarget (G.Node G.Bot (Just 6) Rigid)) 7 == G.Orange)
    (fail "graft permission cases changed")
  case Solver.prepare (replaceTarget (G.Node G.Bot Nothing Flexible)) of
    Left _ -> pure ()
    Right _ -> fail "unbound graft target was accepted"
  putStrLn "graft guards: ok"
  let a = G.Node G.Bot Nothing Flexible
      b = G.Node (G.Con "Int" []) Nothing Rigid
      table = IM.fromList [(0,a),(2,a),(3,a),(8,a),(10,b)]
  unless (IM.toAscList (snd (IM.split 7 table)) == [(8,a),(10,b)] && IM.null (snd (IM.split 11 table)))
    (fail "fresh interval reference changed")
  putStrLn "fresh interval demand: ok"
rename :: (Int -> Int) -> G.Graph -> G.Graph
rename f g = G.Graph (IM.fromList [(f n,G.Node (rt (G.tag v)) (fmap f (G.binder v)) (G.flag v)) | (n,v) <- IM.toList (G.nodes g)]) (IM.fromList [(f n,f p) | (n,p) <- IM.toList (G.links g)]) (f (G.nextId g))
 where rt t = case t of G.Arr a b -> G.Arr (f a) (f b); G.Gen n -> G.Gen (f n); G.Con c ns -> G.Con c (map f ns); G.TyApp a b -> G.TyApp (f a) (f b); _ -> t

-- Translation preserves order, minimum representatives, and fresh-id
-- increments. Compute with the independent seed, then lift every graph
-- identity to Integer for an oracle beyond the seed's machine Int range.
shiftedGraph :: Integer -> G.Graph -> String
shiftedGraph amount graph = concat
  [identity n ++ ":" ++ tag (G.tag value) ++ ":" ++ maybe "_" identity (G.binder value) ++ ":" ++
   (if G.flag value == Flexible then "f" else "r") ++ ";" | (n,value) <- IM.toAscList (G.nodes graph)] ++ "|" ++
  concat [identity n ++ ":" ++ identity parent ++ ";" | (n,parent) <- IM.toAscList (G.links graph)] ++ "|" ++ identity (G.nextId graph)
  where
    identity n = show (toInteger n + amount)
    tag value = case value of
      G.Arr a b -> "a" ++ identity a ++ "," ++ identity b
      G.Gen n -> "g" ++ identity n
      G.Con name ns -> "c" ++ name ++ "[" ++ intercalate "," (map identity ns) ++ "]"
      G.TyApp a b -> "p" ++ identity a ++ "," ++ identity b
      _ -> showTag value

shiftedResult :: String -> Integer -> Either String G.Graph -> IO ()
shiftedResult label amount resultGraph = putStrLn (label ++ "|" ++ either (const "!") (shiftedGraph amount) resultGraph)

checkAscendingNodes :: IO ()
checkAscendingNodes = do
  let huge = 10 ^ (30 :: Int) :: Integer
      entries = [(key,G.Node (G.Arr 3 5) (Just 7) Flexible) | key <- [-huge,-7,0,1,huge]]
  unless (Map.toAscList (Map.fromDistinctAscList entries) == entries) (fail "ascending Integer keys changed")
  forM_ [0..100] $ \count -> do
    let nodes = [(3*n-70,G.Node (G.Gen n) Nothing Flexible) | n <- [0..count-1]]
    unless (IM.fromDistinctAscList nodes == IM.fromList nodes) (fail "ascending graph node reference changed")
  -- Mirror Node's existing shallow strictness; these fields remain unused.
  let deferred = G.Node (G.Con "Unused" (error "forced constructor arguments")) (Just (error "forced binder identity")) Rigid
  unless (IM.size (IM.fromDistinctAscList [(0,deferred)]) == 1) (fail "ascending graph node demand changed")
  putStrLn "ascending graph nodes: ok"

-- Independently check the containment corpus using Integer keys and a
-- worklist search. The seed's complete reachability supplies each oracle;
-- translation covers the two fixtures outside its machine-Int domain.
checkContainment :: IO ()
checkContainment = do
  let graph seed = G.Graph (IM.fromList
        [(n,G.Node (G.Con "T" [m | m <- keys, (n*13+m*17+seed*(n+1)) `rem` 97 < 24]) Nothing Flexible)
        | n <- keys]) (IM.fromList (concat [[(n+100,n),(n+200,n+100)] | n <- keys])) 300
      keys = [3,10..45]
      fixtures = [(seed,0) | seed <- [0..31]] ++ [(7,10^(30::Int)),(19,negate (10^(30::Int)))]
      rows = [let g = graph seed
                  move n = toInteger n + shift
                  adjacency = Map.fromList
                    [(move n,map move (G.children (G.tag v))) | (n,v) <- IM.toList (G.nodes g)]
                  aliases = Map.fromList [(move n,move p) | (n,p) <- IM.toList (G.links g)]
                  sources = IM.keys (G.nodes g) ++ IM.keys (G.links g)
              in [(reaches adjacency aliases (move source) (move target),
                    IS.member (G.resolve g target) (G.reachable g source))
                  | source <- sources, target <- sources ++ [999]]
             | (seed,shift) <- fixtures]
      comparisons = concat rows
  unless (length comparisons == 15708 && all (uncurry (==)) comparisons &&
          any snd comparisons && any (not . snd) comparisons)
    (fail "structural containment corpus changed")
  putStrLn "structural containment oracle: 15708 comparisons passed"
  unless (reaches (Map.fromList [(0,1:error "forced an unvisited branch"),(1,[])]) Map.empty 0 1)
    (fail "structural containment demand changed")
  putStrLn "structural containment demand: ok"
  where
    reaches adjacency aliases source target = visit Set.empty [resolve source]
      where
        resolve n = maybe n resolve (Map.lookup n aliases)
        wanted = resolve target
        visit _ [] = False
        visit seen (n:pending)
          | n == wanted = True
          | Set.member n seen = visit seen pending
          | otherwise = visit (Set.insert n seen)
              (map resolve (Map.findWithDefault [] n adjacency) ++ pending)

main :: IO ()
main = do
  putStrLn (concatMap (\n -> show (G.permission scoped n)) [0..9])
  result "normalize" (Right (G.normalize scoped))
  let first = Solver.prepare scoped >>= Solver.unify [(4,8)]
  result "merge" (first >>= Solver.finish)
  result "rigid" (first >>= Solver.unify [(8,9)] >>= Solver.finish)
  result "protected" (first >>= Solver.unify [(5,9)] >>= Solver.finish)
  forM_ [1,100000] $ \scale -> forM_ [0,-30] $ \shift -> do
    let f n = scale*n + shift
    result "renamed" (Solver.prepare (rename f scoped) >>= Solver.unify [(f 4,f 8)] >>= Solver.finish)
  forM_ [scoped,frontier] $ \g -> do
    case G.runBuild g (G.expand 2 0) of
      Left _ -> putStrLn "expand|!"
      Right ((root,copies,edges),next) -> putStrLn ("expand|" ++ show root ++ "|" ++ showIds copies ++ "|" ++ showIds (IM.fromList edges) ++ "|" ++ showGraph next)
    forM_ [3,8] $ \target -> do
      result "instance" (Solver.prepare g >>= Solver.instantiate 2 target >>= Solver.finish)
      case Solver.prepare g >>= Solver.witness 2 target of
        Left _ -> putStrLn "witness|!"
        Right (copies,solver) -> case Solver.finish solver of
          Left message -> fail message
          Right final -> putStrLn ("witness|" ++ showIds copies ++ "|" ++ showGraph final)
  let points = [0,1,4,7,15,30,31,40,41,50]
  forM_ [(a,b) | a <- points,b <- points,a < b] $ \(a,b) ->
    result "branch" (Solver.prepare branching >>= Solver.unify [(2*a+1,2*b+1)] >>= Solver.finish)
  forM_ [closed Flexible 2 "Bool",closed Rigid 2 "Int",closed Flexible 0 "Int",closed Flexible 2 "Int"] $ \g ->
    result "closed" (Solver.prepare g >>= Solver.instantiateClosed 2 6 >>= Solver.finish)
  result "graft" (Solver.prepare closedGraft >>= Solver.instantiateClosed 2 7 >>= Solver.finish)
  checkDemand
  result "graft-flexible-parent" (Solver.prepare (graftChain Flexible) >>= Solver.instantiateClosed 2 7 >>= Solver.finish)
  result "graft-rigid-parent" (Solver.prepare (graftChain Rigid) >>= Solver.instantiateClosed 2 7 >>= Solver.finish)
  result "graft-rigid-target" (Solver.prepare (replaceTarget (G.Node G.Bot (Just 6) Rigid)) >>= Solver.instantiateClosed 2 7 >>= Solver.finish)
  result "graft-kind-mismatch" (Solver.prepare (replaceTarget (G.Node (G.BotK (KArrow Star Star)) (Just 6) Flexible)) >>= Solver.instantiateClosed 2 7 >>= Solver.finish)
  forM_ [1,100000] $ \scale -> forM_ [0,-30] $ \shift -> do
    let f n = scale*n + shift
    result "fresh-renamed" (Solver.prepare (rename f scoped) >>= Solver.instantiate (f 2) (f 3) >>= Solver.finish)
  checkAscendingNodes
  let swap n | n == 4 = 8
             | n == 8 = 4
             | otherwise = n
  result "permuted-projection" (Solver.prepare (rename swap scoped) >>= Solver.unify [(swap 4,swap 8)] >>= Solver.finish)
  let sparse n = 100003*n-9001
  result "sparse-branch" (Solver.prepare (rename sparse branching) >>= Solver.unify [(sparse 63,sparse 101)] >>= Solver.finish)
  forM_ [10^(30::Int), negate (10^(30::Int))] $ \amount -> do
    shiftedResult "huge-projection" amount (Solver.prepare branching >>= Solver.unify [(63,101)] >>= Solver.finish)
    shiftedResult "huge-expansion" amount (Solver.prepare scoped >>= Solver.instantiate 2 3 >>= Solver.finish)
    shiftedResult "huge-graft" amount (Solver.prepare closedGraft >>= Solver.instantiateClosed 2 7 >>= Solver.finish)
  checkContainment
