module CurrentMapPolicyControls where

import Prelude
import Data.Int (Int64)
import Data.List (foldl')
import Control.Exception (ErrorCall, catch, displayException, evaluate)
import Control.Monad (forM, forM_, unless)
import qualified Bootstrap.Map as C
import qualified Bootstrap.Types as T
import qualified HistoricalMap as H
import qualified BaselineMap as B
import qualified FrozenMap as F
import qualified RetainedBalanceControls as R
import qualified HistoricalBalanceControls as Historical

-- This is shared-source GHC/Int64 qualification, not native producer evidence.
-- The runner authenticates all original and generated sources before compiling.
type Tree = T.Map Int64 Int64
check :: (Eq a, Show a) => String -> a -> a -> IO ()
check label expected actual = unless (expected == actual) $
  error (label ++ ": expected " ++ show expected ++ ", got " ++ show actual)
cmp :: Ord a => a -> a -> Int64
cmp a b = case compare a b of LT -> -1; EQ -> 0; GT -> 1

-- Independent sorted association-list specification; no Map operation used.
put :: (k -> k -> Int64) -> (v -> v -> v) -> k -> v -> [(k,v)] -> [(k,v)]
put order combine k v [] = [(k,v)]
put order combine k v xs@((q,w):rest)
  | order k q < 0 = (k,v):xs
  | order k q == 0 = (k,combine v w):rest
  | otherwise = (q,w):put order combine k v rest
modelFrom :: (k -> k -> Int64) -> (v -> v -> v) -> [(k,v)] -> [(k,v)]
modelFrom order combine = foldl' (\xs (k,v) -> put order combine k v xs) []
-- Authenticated fc300 union preserves the LEFT representative in BOTH size
-- branches: inserting left into right uses insertWith's incoming key; inserting
-- right into left uses insertRightWith's existing key. Both combine(left,right).
-- Current singleton/split-join branches promise the same observable contract.
-- Thus comparison below intentionally checks the full key, not only cmp == 0.
modelUnion :: (k -> k -> Int64) -> (v -> v -> v) -> [(k,v)] -> [(k,v)] -> [(k,v)]
modelUnion _ _ [] ys = ys
modelUnion _ _ xs [] = xs
modelUnion order f xs@((k,v):ks) ys@((q,w):qs)
  | order k q < 0 = (k,v):modelUnion order f ks ys
  | order k q > 0 = (q,w):modelUnion order f xs qs
  | otherwise = (k,f v w):modelUnion order f ks qs

-- Traverse the representation independently of Map.toList/size/valid.
entries :: T.Map k v -> [(k,v)]
entries T.MapEmpty = []
entries (T.MapNode _ k v l r) = entries l ++ [(k,v)] ++ entries r
audit :: (k -> k -> Int64) -> T.Map k v -> Either String Int64
audit order = go Nothing Nothing
  where
    go _ _ T.MapEmpty = Right 0
    go lo hi (T.MapNode n k _ l r) = do
      a <- go lo (Just k) l
      b <- go (Just k) hi r
      if maybe False (\q -> order q k >= 0) lo || maybe False (\q -> order k q >= 0) hi
        then Left "ordering" else
        if n /= 1+a+b then Left "cached count" else
        if a+b > 1 && (a > 3*b || b > 3*a) then Left "balance" else Right n
qualify :: (Eq k, Show k, Eq v, Show v) => String -> (k -> k -> Int64) -> [(k,v)] -> T.Map k v -> IO ()
qualify label order expected tree = do
  check (label ++ " content") expected (entries tree)
  check (label ++ " independent audit") (Right (fromIntegral (length expected))) (audit order tree)
  check (label ++ " live size") (fromIntegral (length expected)) (C.size tree)
  check (label ++ " live valid") True (C.valid order tree)

step :: Int -> Tree -> Tree
step i m = let k=fromIntegral ((i*37) `mod` 97-48); v=fromIntegral i in
  case i `mod` 6 of
    0 -> C.delete cmp k m
    1 -> C.insertWith cmp (+) k v m
    2 -> C.adjust cmp (+3) k m
    3 -> C.unionWith cmp (+) m (C.fromList cmp [(k,v),(k+1,v+7)])
    _ -> C.insert cmp k v m
oldStep :: Int -> Tree -> Tree
oldStep i m = let k=fromIntegral ((i*37) `mod` 97-48); v=fromIntegral i in
  case i `mod` 6 of
    0 -> H.delete cmp k m
    1 -> H.insertWith cmp (+) k v m
    2 -> H.adjust cmp (+3) k m
    3 -> H.unionWith cmp (+) m (H.fromList cmp [(k,v),(k+1,v+7)])
    _ -> H.insert cmp k v m
modelStep :: Int -> [(Int64,Int64)] -> [(Int64,Int64)]
modelStep i xs = let k=fromIntegral ((i*37) `mod` 97-48); v=fromIntegral i in
  case i `mod` 6 of
    0 -> filter ((/=k).fst) xs
    1 -> put cmp (+) k v xs
    2 -> map (\(q,w) -> (q,if q==k then w+3 else w)) xs
    3 -> modelUnion cmp (+) xs [(k,v),(k+1,v+7)]
    _ -> put cmp const k v xs

sameInput :: Int -> Tree -> IO ()
sameInput i tree = do
  let k=fromIntegral ((i*37) `mod` 97-48); v=fromIntegral i
      pairs = [("insert",B.insert cmp k v tree,C.insert cmp k v tree),
               ("insertWith",B.insertWith cmp (-) k v tree,C.insertWith cmp (-) k v tree),
               ("delete",B.delete cmp k tree,C.delete cmp k tree),
               ("adjust",B.adjust cmp (+3) k tree,C.adjust cmp (+3) k tree)]
  forM_ pairs $ \(label,a,b) -> check ("same-input "++label++" step "++show i) (R.shape a) (R.shape b)

traceControls :: IO ()
traceControls = go 0 [] C.empty H.empty
  where
    go 400 _ _ _ = return ()
    go i model current historical = do
      sameInput i current
      sameInput i historical
      let expected=modelStep i model; new=step i current; old=oldStep i historical
      qualify ("live trace "++show i) cmp expected new
      qualify ("historical trace "++show i) cmp expected old
      if i < 21 then check ("pre-witness shape "++show i) (R.shape old) (R.shape new) else return ()
      if i == 21 then witness old new else return ()
      go (i+1) expected new old

-- Full literal witness is installed from the authenticated CI stderr, not
-- computed from the implementations under test (see witness below).
witness :: Tree -> Tree -> IO ()
witness old new = do
  check "witness nodes old" (Right 18) (audit cmp old)
  check "witness nodes new" (Right 18) (audit cmp new)
  check "witness old/new content" (entries old) (entries new)
  check "historical exact-shape equivalence is false" False (R.shape old == R.shape new)
  check "authenticated step-21 complete historical shape" expectedOld (R.shape old)
  check "authenticated step-21 complete current shape" expectedNew (R.shape new)
  putStrLn "PASS witness step21/full-shape/valid/content; historical exact-shape equivalence is false"
  where
    -- Transcribed verbatim structurally from artifact 14305006218 stderr,
    -- SHA256 b215997082bc1b1e850df4d109b1f8214d89cc539fcffbb11dbaaae9c5d65f58.
    -- Shared branches are literal data, not generated by a Map function.
    expectedOld = R.Node 18 3 4 (left (R.Node 4 (-38) 16
      (R.Node 2 (-47) 21 R.Empty (R.Node 1 (-46) 28 R.Empty R.Empty))
      (R.Node 1 (-34) 3 R.Empty R.Empty))) right
    expectedNew = R.Node 18 3 4 (left (R.Node 4 (-46) 28
      (R.Node 1 (-47) 21 R.Empty R.Empty)
      (R.Node 2 (-38) 16 R.Empty (R.Node 1 (-34) 3 R.Empty R.Empty)))) right
    left changed = R.Node 11 (-11) 1
      (R.Node 7 (-33) 10 changed
        (R.Node 2 (-29) 11 R.Empty (R.Node 1 (-24) 19 R.Empty R.Empty)))
      (R.Node 3 (-5) 16 (R.Node 1 (-6) 9 R.Empty R.Empty) (R.Node 1 (-1) 17 R.Empty R.Empty))
    right = R.Node 6 31 10
      (R.Node 3 22 15 (R.Node 1 17 7 R.Empty R.Empty) (R.Node 1 23 22 R.Empty R.Empty))
      (R.Node 2 40 5 R.Empty (R.Node 1 45 13 R.Empty R.Empty))

combine :: Int64 -> Int64 -> Int64
combine a b = a*17-b*3 -- deliberately noncommutative and nonassociative
datasets :: [[(Int64,Int64)]]
datasets = [[],[(0,9)],[(k,k*3) | k<-[-40..40]],[(k,k*3) | k<-[40,39..(-40)]],
  [(k,fromIntegral i) | (i,k)<-zip [0::Int ..] ([0..20]++[30,29..10]++[-9..3]++[2,2,1,0])],
  [(0,11),(0,7),(0,5),(1,2),(0,3)],[(minBound,1),(maxBound,2),(0,3),(minBound,4)]]
contentControls :: IO ()
contentControls = do
  forM_ (zip [0::Int ..] datasets) $ \(i,xs) -> do
    forM_ [("live",C.fromList cmp xs),("historical",H.fromList cmp xs)] $ \(name,t) ->
      qualify (name++" fromList "++show i) cmp (modelFrom cmp const xs) t
    forM_ [("live",C.fromListWith cmp combine xs),("historical",H.fromListWith cmp combine xs)] $ \(name,t) ->
      qualify (name++" fromListWith "++show i) cmp (modelFrom cmp combine xs) t
    forM_ (zip [0::Int ..] datasets) $ \(j,ys) -> do
      let expected=modelUnion cmp combine (modelFrom cmp const xs) (modelFrom cmp const ys)
      qualify ("live union "++show(i,j)) cmp expected (C.unionWith cmp combine (C.fromList cmp xs) (C.fromList cmp ys))
      qualify ("historical union "++show(i,j)) cmp expected (H.unionWith cmp combine (H.fromList cmp xs) (H.fromList cmp ys))
  let order (a,_) (b,_) = cmp (a::Int64) b
      xs=[((1,11::Int64),3),((2,20),4),((1,12),7),((0,0),8)]
      ys=[((1,99),9),((3,30),10),((2,29),6)]
  forM_ [("live",C.fromList order xs),("historical",H.fromList order xs)] $ \(name,t) ->
    qualify (name++" representative fromList") order (modelFrom order const xs) t
  forM_ [("live",C.fromListWith order combine xs),("historical",H.fromListWith order combine xs)] $ \(name,t) ->
    qualify (name++" representative fromListWith") order (modelFrom order combine xs) t
  let expected=modelUnion order combine (modelFrom order const xs) (modelFrom order const ys)
  qualify "live representative union" order expected (C.unionWith order combine (C.fromList order xs) (C.fromList order ys))
  qualify "historical representative union" order expected (H.unionWith order combine (H.fromList order xs) (H.fromList order ys))
  forM_ [(xs,take 1 ys),(take 1 xs,ys),(ys,xs),([],ys),(xs,[])] $ \(as,bs) -> do
    let want=modelUnion order combine (modelFrom order const as) (modelFrom order const bs)
    qualify ("live representative union boundaries "++show(as,bs)) order want
      (C.unionWith order combine (C.fromList order as) (C.fromList order bs))
    qualify ("historical representative union boundaries "++show(as,bs)) order want
      (H.unionWith order combine (H.fromList order as) (H.fromList order bs))

data API = API
  { from :: (Int64 -> Int64 -> Int64) -> [(Int64,Int64)] -> Tree
  , fromWith :: (Int64 -> Int64 -> Int64) -> (Int64 -> Int64 -> Int64) -> [(Int64,Int64)] -> Tree
  , union :: (Int64 -> Int64 -> Int64) -> (Int64 -> Int64 -> Int64) -> Tree -> Tree -> Tree }
currentAPI, historicalAPI :: API
currentAPI=API C.fromList C.fromListWith C.unionWith
historicalAPI=API H.fromList H.fromListWith H.unionWith
bot :: String -> a
bot = errorWithoutStackTrace
{-# NOINLINE bot #-}
forceValues :: Tree -> Bool
forceValues t = foldr (\(_,v) rest -> v `seq` rest) True (entries t)
demandCases :: [(String, API -> Bool)]
demandCases =
  [("empty ignores comparator",\a -> C.size (from a (bot "cmp") []) == 0),
   ("singleton ignores comparator and payload",\a -> C.size (from a (bot "cmp") [(1,bot "payload")]) == 1),
   ("singleton forces key",\a -> C.size (from a cmp [(bot "key",bot "payload")]) == 1),
   ("duplicates keep last lazy value",\a -> forceValues (from a cmp [(1,bot "old-value"),(1,7)])),
   ("list tail versus key",\a -> C.size (from a cmp ((bot "key",1):bot "tail")) > 0),
   ("comparator versus later key",\a -> C.size (from a (\_ _ -> bot "cmp") [(1,1),(2,2),(bot "later-key",3)]) > 0),
   ("ascending run lazy values",\a -> C.size (from a cmp [(1,bot "one"),(2,bot "two"),(3,bot "three")])==3),
   ("descending run lazy values",\a -> C.size (from a cmp [(3,bot "three"),(2,bot "two"),(1,bot "one")])==3),
   ("mixed run first demanded value",\a -> forceValues (from a cmp [(3,bot "three"),(1,bot "one"),(2,bot "two")])) ,
   ("fromListWith duplicate lazy combine",\a -> C.size (fromWith a cmp (\_ _ -> bot "combine") [(1,bot "old"),(1,bot "new")])==1),
   ("fromListWith demanded combine",\a -> forceValues (fromWith a cmp (\_ _ -> bot "combine") [(1,bot "old"),(1,bot "new")])) ,
   ("fromListWith select new discard old",\a -> forceValues (fromWith a cmp (\new _ -> new) [(1,bot "old"),(1,7)])),
   ("fromListWith select old discard new",\a -> forceValues (fromWith a cmp (\_ old -> old) [(1,7),(1,bot "new")])),
   ("fromListWith new before old",\a -> forceValues (fromWith a cmp (+) [(1,bot "old"),(1,bot "new")])) ,
   ("fromListWith distinct ignores combiner",\a -> forceValues (fromWith a cmp (bot "combine") [(1,7),(2,8),(3,9)])),
   ("both tree bottoms",\a -> R.headOnly (union a cmp (+) (bot "left") (bot "right"))),
   ("empty left right bottom",\a -> R.headOnly (union a cmp (+) T.MapEmpty (bot "right"))),
   ("union empty ignores comparator and combine",\a -> C.size (union a (bot "cmp") (bot "combine") (from a cmp [(1,bot "payload")]) T.MapEmpty)==1),
   ("union lazy combine",\a -> C.size (union a cmp (\_ _ -> bot "combine") (from a cmp [(1,bot "left-value")]) (from a cmp [(1,bot "right-value")]))==1),
   ("union demanded combine",\a -> forceValues (union a cmp (\_ _ -> bot "combine") (from a cmp [(1,bot "left-value")]) (from a cmp [(1,bot "right-value")]))),
   ("union comparator versus values",\a -> forceValues (union a (\_ _ -> bot "cmp") (+) (from a cmp [(1,bot "left-value")]) (from a cmp [(2,bot "right-value")]))),
   ("union left value before right",\a -> forceValues (union a cmp (+) (from a cmp [(1,bot "left-value")]) (from a cmp [(1,bot "right-value")]))),
   ("union right value selected",\a -> forceValues (union a cmp (\_ r -> r) (from a cmp [(1,bot "left-value")]) (from a cmp [(1,bot "right-value")]))),
   ("multi-node union lazy values",\a -> C.size (union a cmp (\_ _ -> bot "combine") (from a cmp [(1,bot "one"),(3,bot "three"),(5,bot "five")]) (from a cmp [(2,bot "two"),(3,bot "rhs-three"),(4,bot "four")]))==5),
   ("multi-node comparator versus values",\a -> forceValues (union a (\_ _ -> bot "cmp") (+) (from a cmp [(1,bot "one"),(3,bot "three"),(5,bot "five")]) (from a cmp [(2,bot "two"),(3,bot "rhs-three"),(4,bot "four")])))]

retainedLiveControls :: IO ()
retainedLiveControls = do
  n <- R.rawShapes
  check "retained raw count" 24649 n
  check "retained demand count" 30 (length R.cases)
  forM_ R.cases $ \(label,expected,action) -> do
    frozen <- R.observe (action F.balance)
    current <- R.observe (action C.balance)
    check (label++" original frozen expectation") expected frozen
    check (label++" original live expectation") expected current

runCase :: String -> IO () -> IO [String]
runCase label action = (action >> putStrLn ("PASS "++label) >> return []) `catch` \e ->
  return [label++": "++displayException (e::ErrorCall)]
main :: IO ()
main = do
  groups <- forM [("complete historical 24649/400/30",Historical.main),
                  ("retained live raw/demand",retainedLiveControls),
                  ("400-step live/model/historical trace",traceControls),
                  ("independent policy contents",contentControls)] $ uncurry runCase
  demands <- forM demandCases $ \(label,action) -> runCase ("demand "++label) $ do
    old <- R.observe (action historicalAPI)
    new <- R.observe (action currentAPI)
    putStrLn ("Demand observation "++label++": historical="++show old++" current="++show new)
    check ("historical/current demand "++label) old new
  let failures=concat (groups++demands)
  mapM_ putStrLn failures
  unless (null failures) $ error (show(length failures)++" Map policy qualification group(s) failed; differences retained, not waived")
  putStrLn "Current Map policy controls passed; historical exact-shape equivalence explicitly does not hold at step 21"
