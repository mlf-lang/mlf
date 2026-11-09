module Main where
import Prelude
import qualified Bootstrap.Map as C
import qualified FrozenMap as F
import qualified BaselineMap as B
import qualified Bootstrap.Types as T
import Control.Exception
import Control.Monad (forM_, unless)

data Shape = Empty | Node Integer Integer Integer Shape Shape deriving (Eq,Show)
shape :: T.Map Integer Integer -> Shape
shape T.MapEmpty = Empty
shape (T.MapNode n k v l r) = Node n k v (shape l) (shape r)
check :: (Eq a, Show a) => String -> a -> a -> IO ()
check label expected actual = unless (expected==actual) $ error (label ++ ": expected " ++ show expected ++ ", got " ++ show actual)
cmp :: Integer -> Integer -> Integer
cmp a b = case compare a b of LT -> -1; EQ -> 0; GT -> 1
leaf :: Integer -> T.Map Integer Integer
leaf k = T.MapNode 1 k (k*3) T.MapEmpty T.MapEmpty
mk :: Integer -> Int -> Integer -> T.Map Integer Integer
mk n style k = case style of
  0 -> T.MapNode n k 7 T.MapEmpty T.MapEmpty
  1 -> T.MapNode n k 7 (leaf (k-10)) T.MapEmpty
  2 -> T.MapNode n k 7 T.MapEmpty (T.MapNode 3 (k+10) 8 (leaf (k+5)) (leaf (k+15)))
  _ -> T.MapNode n k 7 (T.MapNode 7 (k-10) 8 (leaf (k-15)) (leaf (k-5))) (leaf (k+10))
rawShapes :: IO Int
rawShapes = do
  let sizes = [-8..24] ++ [negate (2^128),negate (2^64),negate (2^63)-1,2^63,2^64,2^128]
      left = T.MapEmpty:[mk n style (-100) | n<-sizes,style<-[0..3]]
      right = T.MapEmpty:[mk n style 100 | n<-sizes,style<-[0..3]]
  forM_ left $ \l -> forM_ right $ \r ->
    check "raw complete tree shape" (shape (F.balance 0 42 l r)) (shape (C.balance 0 42 l r))
  return (length left * length right)

traces :: IO Int
traces = go 0 B.empty C.empty
  where
    go i old new | i==400 = return i
                 | otherwise = do
      let k=toInteger ((i*37) `mod` 97-48); v=toInteger i
          both f g = (f old,g new)
          (a,b)=case i `mod` 6 of
            0 -> both (B.delete cmp k) (C.delete cmp k)
            1 -> both (B.insertWith cmp (+) k v) (C.insertWith cmp (+) k v)
            2 -> both (B.adjust cmp (+3) k) (C.adjust cmp (+3) k)
            3 -> both (\m -> B.unionWith cmp (+) m (B.fromList cmp [(k,v),(k+1,v+7)]))
                      (\m -> C.unionWith cmp (+) m (C.fromList cmp [(k,v),(k+1,v+7)]))
            _ -> both (B.insert cmp k v) (C.insert cmp k v)
      check "mutation exact shape" (shape a) (shape b)
      check "old mutation is valid" True (F.valid cmp a)
      check "candidate mutation is valid" True (C.valid cmp b)
      go (i+1) a b

type Tree=T.Map Integer Integer
type Balance=Integer -> Integer -> Tree -> Tree -> Tree
bottom :: String -> a
bottom=errorWithoutStackTrace
{-# NOINLINE bottom #-}
headOnly :: Tree -> Bool
headOnly T.MapEmpty=False
headOnly (T.MapNode _ _ _ _ _)=True
node :: Integer -> Integer -> Tree -> Tree -> Tree
node n k=T.MapNode n k (bottom "unused payload")
cases :: [(String,Either String Bool,Balance -> Bool)]
cases =
  [ ("empty children",Right True,\f->headOnly(f 0 1 T.MapEmpty T.MapEmpty))
  , ("root payload lazy",Right True,\f->headOnly(f 0 (bottom "value") T.MapEmpty T.MapEmpty))
  , ("root key required",Left "root",\f->headOnly(f (bottom "root") 1 T.MapEmpty T.MapEmpty))
  , ("left before right",Left "left",\f->headOnly(f 0 1 (bottom "left") (bottom "right")))
  , ("right required",Left "right",\f->headOnly(f 0 1 T.MapEmpty (bottom "right")))
  , ("left count before right",Left "left-count",\f->headOnly(f 0 1 (node (bottom "left-count") 1 T.MapEmpty T.MapEmpty) (node (bottom "right-count") 2 T.MapEmpty T.MapEmpty)))
  , ("right count required",Left "right-count",\f->headOnly(f 0 1 (leaf 1) (node (bottom "right-count") 2 T.MapEmpty T.MapEmpty)))
  , ("balanced left key lazy",Right True,\f->headOnly(f 0 1 (node 2 (bottom "left-key") T.MapEmpty T.MapEmpty) (mk 2 0 2)))
  , ("balanced right key lazy",Right True,\f->headOnly(f 0 1 (mk 2 0 (-2)) (node 2 (bottom "right-key") T.MapEmpty T.MapEmpty)))
  , ("balanced descendants lazy",Right True,\f->headOnly(f 0 1 (node 2 1 (bottom "ll") (bottom "lr")) (node 2 2 (bottom "rl") (bottom "rr"))))
  , ("signed cancelling sizes",Right True,\f->headOnly(f 0 1 (node (2^128) 1 (bottom "ll") (bottom "lr")) (node (1-2^128) 2 (bottom "rl") (bottom "rr"))))
  , ("right rotation child order",Left "rl",\f->headOnly(f 0 1 T.MapEmpty (node 3 2 (bottom "rl") (bottom "rr"))))
  , ("left rotation child order",Left "lr",\f->headOnly(f 0 1 (node 3 (-2) (bottom "ll") (bottom "lr")) T.MapEmpty))
  , ("right rotation root before promotion",Left "root",\f->headOnly(f (bottom "root") 1 T.MapEmpty (node 3 (bottom "promoted") T.MapEmpty T.MapEmpty)))
  , ("left rotation root before promotion",Left "root",\f->headOnly(f (bottom "root") 1 (node 3 (bottom "promoted") T.MapEmpty T.MapEmpty) T.MapEmpty))
  , ("right promotion key required",Left "promoted",\f->headOnly(f 0 1 T.MapEmpty (node 3 (bottom "promoted") T.MapEmpty T.MapEmpty)))
  , ("left promotion key required",Left "promoted",\f->headOnly(f 0 1 (node 3 (bottom "promoted") T.MapEmpty T.MapEmpty) T.MapEmpty))
  , ("right rotation payloads lazy",Right True,\f->headOnly(f 0 (bottom "root-value") T.MapEmpty (node 3 2 T.MapEmpty T.MapEmpty)))
  , ("left rotation payloads lazy",Right True,\f->headOnly(f 0 (bottom "root-value") (node 3 (-2) T.MapEmpty T.MapEmpty) T.MapEmpty))
  , ("right double pivot required",Left "pivot",\f->headOnly(f 0 1 T.MapEmpty (node 3 3 (node 1 (bottom "pivot") T.MapEmpty T.MapEmpty) T.MapEmpty)))
  , ("left double pivot required",Left "pivot",\f->headOnly(f 0 1 (node 3 (-3) T.MapEmpty (node 1 (bottom "pivot") T.MapEmpty T.MapEmpty)) T.MapEmpty))
  , ("right double descendant order",Left "rll",\f->headOnly(f 0 1 T.MapEmpty (node 3 3 (node 1 2 (bottom "rll") (bottom "rlr")) T.MapEmpty)))
  , ("left double descendant order",Left "lrl",\f->headOnly(f 0 1 (node 3 (-3) T.MapEmpty (node 1 (-2) (bottom "lrl") (bottom "lrr"))) T.MapEmpty))
  , ("negative metadata leaves child key lazy",Right True,\f->headOnly(f 0 1 (node (-3) (bottom "unused-key") T.MapEmpty T.MapEmpty) (node 6 3 T.MapEmpty T.MapEmpty)))
  , ("initial left tree before root key",Left "left",\f->headOnly(f (bottom "root") 1 (bottom "left") (bottom "right")))
  , ("initial right tree before root key",Left "right",\f->headOnly(f (bottom "root") 1 T.MapEmpty (bottom "right")))
  , ("initial left count before root key",Left "left-count",\f->headOnly(f (bottom "root") 1 (node (bottom "left-count") 1 T.MapEmpty T.MapEmpty) T.MapEmpty))
  , ("initial right count before root key",Left "right-count",\f->headOnly(f (bottom "root") 1 (leaf 1) (node (bottom "right-count") 2 T.MapEmpty T.MapEmpty)))
  , ("right child order before root key",Left "rl",\f->headOnly(f (bottom "root") 1 T.MapEmpty (node 3 2 (bottom "rl") (bottom "rr"))))
  , ("left child order before root key",Left "lr",\f->headOnly(f (bottom "root") 1 (node 3 (-2) (bottom "ll") (bottom "lr")) T.MapEmpty))
  ]
observe :: Bool -> IO (Either String Bool)
observe x=(Right <$> evaluate x) `catch` \e->return(Left(displayException(e::ErrorCall)))
main :: IO ()
main=do
  n<-rawShapes
  t<-traces
  forM_ cases $ \(label,expected,action)->do
    old<-observe(action F.balance); new<-observe(action C.balance)
    check (label++" frozen manual expectation") expected old
    check (label++" candidate manual expectation") expected new
  putStrLn("Balance controls: "++show n++" raw-shape pairs; "++show t++" mutation steps; "++show(length cases)++" independent demand/order cases passed")
