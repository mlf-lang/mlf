{-# LANGUAGE OverloadedStrings #-}
-- Private renamed codecs compare against the immutable checkpoint source.
module Main where
import Prelude
import qualified Control.Exception as E
import Control.Monad (forM_, unless, foldM)
import qualified Bootstrap.Types as T
import qualified MLF.Primitive as P
import qualified MLF.Host.Base as B
import qualified CandidateWire as C
import qualified LegacyWire as L
import qualified Bootstrap.Map as M

need label ok = unless ok (fail label)
expect label (T.Left e) = fail (label ++ ": " ++ B.unpack e)
expect _ (T.Right a) = pure a
old value = case value of
 C.VInt x -> L.VInt x
 C.VBits x -> L.VBits x
 C.VText x -> L.VText x
 C.VNode t xs -> L.VNode t (map old xs)
bytes array = P.lengthByteArray array >>= \n -> mapM (P.readByteArray array) [0..n-1]
sameBytes left right = do
 n <- P.lengthByteArray left
 m <- P.lengthByteArray right
 let loop i | i == n = pure True
            | otherwise = do
                a <- P.readByteArray left i
                b <- P.readByteArray right i
                if a == b then loop (i+1) else pure False
 if n == m then loop 0 else pure False
-- Independent CRC32/ISO-HDLC vectors generated with Python zlib.crc32.
-- The input byte at i is (37*i+seed) mod 256, with header bytes 76..79 zero.
crcVectors :: [(P.Int,P.Int,P.Int)]
crcVectors = [
 (0,11,0),
 (0,53,0),
 (1,11,1171273221),
 (1,53,2226203566),
 (7,11,4017044273),
 (7,53,2845095205),
 (75,11,1054614140),
 (75,53,2823205938),
 (76,11,3314257388),
 (76,53,332117138),
 (77,11,2071710291),
 (77,53,3423655505),
 (79,11,2885569725),
 (79,53,2378810651),
 (80,11,1736040176),
 (80,53,1491791780),
 (81,11,134557315),
 (81,53,3907998892),
 (1023,11,4291182421),
 (1023,53,1854776408),
 (1024,11,2157300612),
 (1024,53,2859182987),
 (1025,11,2944787703),
 (1025,53,4268825261),
 (16383,11,4105262987),
 (16383,53,3673467443),
 (16384,11,3790947135),
 (16384,53,1891592789),
 (16385,11,4082626171),
 (16385,53,2680172991),
 (16386,11,872358011),
 (16386,53,50149707),
 (16387,11,250027362),
 (16387,53,4088718849),
 (16388,11,3244331206),
 (16388,53,1951206412),
 (32769,11,417468052),
 (32769,53,3546315975),
 (65537,11,1141312188),
 (65537,53,2530153874),
 (131075,11,3768389109),
 (131075,53,2350599702)]
observeChecksum :: IO P.Int -> IO (Either String P.Int)
observeChecksum action = do
 result <- E.try (action >>= E.evaluate) :: IO (Either E.SomeException P.Int)
 pure (either (Left . takeWhile (/='\n') . E.displayException) Right result)
crcControls = forM_ crcVectors $ \(size,seed,wanted) -> do
 array <- P.newByteArray size 0
 forM_ [0..size-1] $ \i -> P.writeByteArray array i ((37*i+seed) `mod` 256)
 actual <- C.checksum array size
 frozen <- L.checksum array size
 need "CRC agrees with independent vectors and frozen recurrence" (actual==wanted && frozen==wanted)
 forM_ [76..min 79 (size-1)] $ \i -> P.writeByteArray array i 255
 changed <- C.checksum array size
 need "checksum field is logically zero" (changed==wanted)
 a <- observeChecksum (C.checksum array (size+7))
 b <- observeChecksum (L.checksum array (size+7))
 need "CRC keeps frozen short-buffer failure behavior" (a==b)

oldLimits (C.Limits a b c d e f g h) = L.Limits a b c d e f g h
limitControls = do
 let limits = [C.defaultLimits, C.Limits 79 8 16 32 32 32 8 128,
       C.Limits 256 0 16 32 32 32 8 128,
       C.Limits 256 1 16 32 32 32 8 128,
       C.Limits 256 8 1 32 32 32 8 128,
       C.Limits 256 8 4 4 32 32 8 128,
       C.Limits 256 8 16 32 0 32 8 128,
       C.Limits 256 8 16 32 1 32 8 128,
       C.Limits 256 8 16 32 32 0 8 128,
       C.Limits 256 8 16 32 32 2 1 128,
       C.Limits 256 8 16 32 32 32 8 0,
       C.Limits 256 8 16 32 32 32 8 7]
     values = [[], [C.VText "α😀"], [C.VText "a",C.VText "b"],
       replicate 8 (C.VText "α"), [C.VInt 1,C.VBits 1,C.VText "1"],
       [C.VNode 1 [C.VText "a",C.VText "a",C.VInt 1]],
       [C.VNode 1 [C.VNode 2 [C.VText "a"]]],
       [C.VNode (-1) []], [C.VNode 2147483648 []]]
 forM_ limits $ \bound -> forM_ values $ \roots -> do
  candidate <- C.encode bound 7 roots
  frozen <- L.encode (oldLimits bound) 7 (map old roots)
  case (candidate,frozen) of
   (T.Left a,T.Left b) -> need "finite limit diagnostic order" (a==b)
   (T.Right a,T.Right b) -> sameBytes a b >>= need "finite limit accepted bytes"
   _ -> fail "finite limit admission changed"

-- Exercise indexes beyond practical fixture sizes without allocating millions
-- of wire nodes. The frozen full-key comparator supplies independent IDs.
indexControls = do
 let tags = [0,1,1023,1024,65535,65536,2147483647]
     ids = [0,1,131071,131072,4194303,4194304,2147483646]
     children = [[]] ++ [[a] | a <- ids] ++ [[a,b] | a <- ids,b <- ids] ++
       [[a,b,c] | a <- ids,b <- ids,c <- ids] ++ [[0,1,2,3]]
     nodes = [C.ENode tag refs | tag <- tags,refs <- children]
     entries = [C.EInt 0,C.EBits 0,C.EText 0,C.EInt minBound,C.EBits minBound] ++ nodes
     legacy entry = case entry of
       C.EInt n -> L.EInt n
       C.EBits n -> L.EBits n
       C.EText n -> L.EText n
       C.ENode tag refs -> L.ENode tag refs
     step (current,frozen,next) entry =
       case (C.internNodeKey entry current,L.intern L.compareEntry (legacy entry) frozen) of
        (C.ExistingNode actual,L.Found expected) -> do
          need "exact indexed node identity" (actual==expected)
          pure (current,frozen,next)
        (C.MissingNode insert,L.Inserted fill) -> pure (insert next,fill next,next+1)
        _ -> fail "indexed node equality differs from frozen structural comparison"
 _ <- foldM step (C.emptyNodeIndex,M.empty,0) (entries ++ reverse entries ++ entries)
 pure ()

atomControls = do
 let hints = C.AtomShapes 70 31 81 32 1
     prim n = C.VNode 81 [C.VNode 32 [C.VInt n],C.VNode 1 []]
     name n t = C.VNode 70 [C.VNode 31 [C.VInt n,C.VText t]]
     x = name 0 "a"
     y = name 3 "同😀"
     varied = [x,y,prim 8,x,name 0 "other",prim 9,y,name 65 "a",name (-1) "a",prim 8,x]
     malformed = [C.VNode 70 [],C.VNode 70 [C.VNode 32 [C.VInt 0,C.VText "a"]],
       C.VNode 81 [C.VNode 32 [C.VInt 8],C.VNode 0 []],
       C.VNode 81 [C.VNode 32 [C.VInt 8],C.VNode 1 [C.VInt 0]],
       C.VNode 70 [C.VNode 31 [C.VBits 0,C.VText "a"]], C.VNode 70 [C.VNode 31 [C.VInt 0,C.VInt 5]],
       C.VNode 81 [C.VNode (-1) [],C.VInt 8],C.VNode 81 [C.VNode 32 [C.VInt 8],C.VNode 2147483648 []]]
     operator a b = C.VNode 72 [a,b]
     sets = [[],varied,[foldl1 operator (concat (replicate 8 varied))]] ++
       [[x,prim 8,y,t,prim 8,x] | t <- malformed] ++
       [[name i (B.literal (show i)) | i <- [0..80]]]
     ordinalRoots width = let leaves = [C.VInt (fromIntegral (2000+i)) | i <- [0..width-1::Int]]
                              wrap tag v = C.VNode tag [v]
                          in concat [[wrap 42 leaf,leaf,operator (wrap 42 leaf) x] | leaf <- leaves] ++
                             concat [[wrap 42 leaf,wrap 43 leaf,operator y (wrap 42 leaf)] | leaf <- reverse leaves]
     limits = [C.defaultLimits] ++ [C.Limits 65536 128 256 4096 1024 2048 1000 n | n <- [0..31]++[72,128,256,640]] ++
       [C.Limits 65536 128 256 4096 n m d 10240 | (n,m,d) <- [(1,128,12),(4,128,12),(11,128,12),(50,0,12),(50,2,12),(50,6,12),(50,128,1),(50,128,2),(50,128,3),(50,128,4)]] ++
       [C.Limits b sy word total 1024 2048 1000 10240 | (b,sy,word,total) <- [(79,128,256,4096),(128,128,256,4096),(65536,0,256,4096),(65536,1,256,4096),(65536,128,1,4096),(65536,128,256,4)]]
     compareWire l r = do
       a <- l; b <- r
       case (a,b) of
         (T.Left e,T.Left f) -> need "atom admission gives the frozen diagnostic" (e==f)
         (T.Right u,T.Right v) -> sameBytes u v >>= need "atom replay reproduces canonical bytes"
         _ -> fail "atom admission changed an outcome"
     currentStats result = case result of
       T.Left why -> Left (B.unpack why)
       T.Right (C.Tables _ _ roots symbols nodes count edges,work) -> Right (roots,symbols,nodes,count,edges,work)
     oldStats result = case result of
       T.Left why -> Left (B.unpack why)
       T.Right (L.Tables _ _ roots symbols nodes count edges,work) -> Right (roots,symbols,nodes,count,edges,work)
 forM_ [hints,C.AtomShapes 99 31 81 0 1] $ \layout -> forM_ limits $ \bound -> forM_ sets $ \roots -> do
   let fixed = map old roots
   compareWire (C.encodeAtoms layout bound 7 roots) (L.encode (oldLimits bound) 7 fixed)
   forM_ [12,512] $ \aggregate -> do
     let a = currentStats (C.planRootsWith (C.emptyAtomIds layout) bound aggregate roots)
         b = oldStats (L.planRootBounded (oldLimits bound) aggregate fixed)
     need "exact aggregate occurrence charges, roots, edges and symbols" (a==b)
   compareWire (C.encodeRootsWithAtoms layout bound 512 8 roots) (L.encodeRootBounded (oldLimits bound) 512 8 fixed)
 forM_ [0,1,31,32,63,64,65,127,128,129,257,1025] $ \width -> do
   let roots = ordinalRoots width
       fixed = map old roots
   compareWire (C.encodeAtoms hints C.defaultLimits 7 roots) (L.encode L.defaultLimits 7 fixed)
   compareWire (C.encodeRootsWithAtoms hints C.defaultLimits 1000000 8 roots)
     (L.encodeRootBounded L.defaultLimits 1000000 8 fixed)
 let failure action = do
       v <- E.try (E.evaluate action) :: IO (Either E.SomeException String)
       pure (either E.displayException id v)
     report (T.Left e) = B.unpack e
     report (T.Right _) = "success"
     bomb = errorWithoutStackTrace "unexpected node forced"
     bad = [C.VNode 81 (bomb : errorWithoutStackTrace "input spine failure"),
       C.VNode 81 [C.VNode (-1) bomb,bomb],C.VNode 70 [C.VNode (-1) bomb],
       C.VNode 70 [C.VNode 31 [C.VInt 0,C.VText bomb]],
       C.VNode 81 [C.VNode 32 [C.VInt bomb],bomb],
       C.VNode 81 [C.VNode 32 [C.VInt 8],C.VNode (-1) bomb]]
 forM_ limits $ \bound -> forM_ bad $ \t -> do
   let roots = [x,prim 8,t]
   a <- failure (report (C.planWith (C.emptyAtomIds hints) bound roots))
   b <- failure (report (L.plan (oldLimits bound) (map old roots)))
   need ("atom fallback changes demand order: "++a++" / "++b) (a==b)

main = do
 atomControls
 crcControls
 limitControls
 indexControls
 let scalars = [C.VInt x | x <- [minBound,-129,-128,-1,0,1,63,64,127,128,maxBound]] ++
       [C.VBits x | x <- [minBound,-1,0,1,0x7ff0000000000000,0x7ff8000000000001,maxBound]] ++
       [C.VText x | x <- ["","ascii","α😀\NUL","\x7f\x80\x7ff\x800\xd7ff\xe000\x10000\x10ffff"]]
     sets = [[],scalars] ++
       [[C.VNode (fromIntegral i) [C.VText (B.literal (show i)),C.VInt (fromIntegral i)] | i <- [1..n]]
          | n <- [1,2,3,4,7,8,9,15,16,17,255,256,257,512]] ++
       [[C.VNode 2147483647 (replicate n (C.VNode 17 scalars))] | n <- [0,1,7,128]]
 forM_ sets $ \values -> do
  current <- C.encode C.defaultLimits 7 values >>= expect "current encoder"
  baseline <- L.encode L.defaultLimits 7 (map old values) >>= expect "frozen encoder"
  x <- bytes current; y <- bytes baseline
  need "packed sections preserve every wire byte" (x == y)
  graph <- C.decodeGraph C.defaultLimits 7 current >>= expect "indexed decoder"
  full <- expect "independent full resource inventory" (C.graphResourceStats graph)
  work <- expect "root summary" (C.graphExpandedWork graph)
  need "summary retains expanded root charging" (work == C.resourceExpandedWork full)
 -- Cross the bounded bulk-text allocation threshold in both ASCII bytes and
 -- Unicode scalars. Include NUL and multibyte text; lengths are wire bytes.
 forM_ [replicate (4194304 + delta) 'a' | delta <- [-128,128]] $ \text -> do
  let values = [C.VText (B.literal text)]
  current <- C.encode C.defaultLimits 7 values >>= expect "large ASCII encoder"
  baseline <- L.encode L.defaultLimits 7 (map old values) >>= expect "frozen large ASCII encoder"
  sameBytes current baseline >>= need "bulk/streaming ASCII boundary preserves every byte"
 forM_ [concat (replicate (524288 + delta) "A\NULα😀") | delta <- [-16,16]] $ \text -> do
  let values = [C.VText (B.literal text)]
  current <- C.encode C.defaultLimits 7 values >>= expect "large Unicode encoder"
  baseline <- L.encode L.defaultLimits 7 (map old values) >>= expect "frozen large Unicode encoder"
  sameBytes current baseline >>= need "bulk/streaming Unicode boundary preserves every byte"
 -- Force collisions independently of the hash function, including equal
 -- prefixes and all four entry kinds. Then check the ordinary hash route too.
 let entries = [C.EInt (-1),C.EBits (-1),C.EText 0,C.ENode 0 [],C.ENode 0 [0],C.ENode 0 [0,1]] ++
       [C.ENode 9 [0,fromIntegral i] | i <- [1..128::Int]]
     insert index (key,entry) = case C.internIndexedAt 0 entry index of
      C.ExistingEntry _ -> fail "unexpected equal collision entry"
      C.MissingEntry fill -> pure (fill key)
 collisions <- foldM insert C.emptyEntryIndex (zip [0..] entries)
 forM_ (zip [0..] entries) $ \(wanted,entry) -> case C.internIndexedAt 0 entry collisions of
  C.ExistingEntry actual -> need "exact equality in balanced collision bucket" (actual == wanted)
  _ -> fail "lost colliding entry"
 let sameHash = [C.EInt (C.mixEntry 1 0),C.EBits (C.mixEntry 2 0),C.EText (C.mixEntry 3 0)]
 need "authored hash collision" (all ((== 0) . C.entryHash) sameHash)
 natural <- foldM (\index (key,entry) -> case C.internIndexed entry index of
    C.MissingEntry fill -> pure (fill key)
    _ -> fail "hash used as equality") C.emptyEntryIndex (zip [0..] sameHash)
 forM_ (zip [0..] sameHash) $ \(wanted,entry) -> case C.internIndexed entry natural of
  C.ExistingEntry actual -> need "ordinary hash collision lookup" (actual == wanted)
  _ -> fail "lost natural collision"
 putStrLn "PASS frozen wire bytes, reference widths, expanded work and exact hash collisions"
