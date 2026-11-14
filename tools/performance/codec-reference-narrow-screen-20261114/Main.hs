-- SOURCE ONLY. Qualified putVar baseline versus private narrow-reference writer.
{-# LANGUAGE NoImplicitPrelude, OverloadedStrings #-}
module Main where
import MLF.Primitive
import Bootstrap.Types
import qualified Bootstrap.Bitstream as W
import qualified Bootstrap.Std as Std
import qualified Prelude as P
import qualified Control.Exception as E
import qualified System.Mem as Mem
import qualified GHC.Clock as Clock
import qualified Data.Bits as Bits
import qualified Data.Word as Word
import qualified Data.List as List
import qualified MLF.Host.Base as Host
right x = case x of { Left e -> panic e; Right v -> ioReturn v }
check ok = if ok then ioReturn () else panic "codec control failed"
forceValues xs = case xs of
  [] -> ()
  v:vs -> forceValue v `seq` forceValues vs
forceValue v = case v of
  W.VInt n -> n `seq` ()
  W.VBits n -> n `seq` ()
  W.VText t -> forceText t 0
  W.VNode tag children -> tag `seq` forceValues children
forceText t i = if i == stringLength t then () else stringCodeAt t i `seq` forceText t (i+1)
equalBytes a b = do
  na <- lengthByteArray a
  nb <- lengthByteArray b
  check (na == nb)
  let loop i = if i == na then ioReturn () else do
        x <- readByteArray a i
        y <- readByteArray b i
        check (x == y)
        loop (i+1)
  loop 0

forceInts xs = case xs of { [] -> (); x:rest -> x `seq` forceInts rest }
forceSymbols xs = case xs of
  [] -> ()
  W.Symbol t n:rest -> t `seq` n `seq` forceSymbols rest
forceEntries xs = case xs of
  [] -> ()
  e:rest -> forceEntry e `seq` forceEntries rest
forceEntry e = case e of
  W.EInt n -> n `seq` ()
  W.EBits n -> n `seq` ()
  W.EText n -> n `seq` ()
  W.ENode tag children -> tag `seq` forceInts children
forceTables (W.Tables syms entries roots sc nc rc edges) =
  forceSymbols syms `seq` forceEntries entries `seq` forceInts roots `seq`
  sc `seq` nc `seq` rc `seq` edges `seq` ()
forceLayout (W.Layout a b c d e f g h i j k l) =
  a `seq` b `seq` c `seq` d `seq` e `seq` f `seq` g `seq`
  h `seq` i `seq` j `seq` k `seq` l `seq` ()
{-# NOINLINE planned #-}
planned values = do
  tables <- right (W.plan W.defaultLimits values)
  E.evaluate (forceTables tables)
  ioReturn tables
{-# NOINLINE laidOut #-}
laidOut tables = do
  geometry <- right (W.layout W.defaultLimits tables)
  E.evaluate (forceLayout geometry)
  ioReturn geometry
-- action is opaque to this NOINLINE observer. Same-build Core/STG must still
-- verify argument evaluation stays inside the observation, not assume it.
{-# NOINLINE observe #-}
observe action = do
  before <- Mem.getAllocationCounter
  t0 <- Clock.getMonotonicTimeNSec
  value <- action
  t1 <- Clock.getMonotonicTimeNSec
  after <- Mem.getAllocationCounter
  let allocated = before P.- after
      elapsed = t1 P.- t0
  E.evaluate allocated
  E.evaluate elapsed
  ioReturn (value,(allocated,elapsed))
-- Retained original CodecControl roundtrip/reject/finite definitions.
roundtrip bytes = do
  values <- W.decode W.defaultLimits 6 bytes >>= right
  forceValues values `seq` ioReturn ()
  -- Future measured encode interval starts only AFTER this forcing.
  blob <- W.encode W.defaultLimits 6 values >>= right
  -- Interval ends BEFORE comparison/decoding/digest or printing.
  equalBytes bytes blob
reject x = case x of { Left _ -> ioReturn (); Right _ -> panic "expected rejection" }
finite = do
  let values = [W.VInt (-1),W.VBits (-1),W.VText "",W.VText "aé中😀",W.VNode 7 [W.VText "shared",W.VText "shared"],W.VNode 8 []]
  forceValues values `seq` ioReturn ()
  bytes <- W.encode W.defaultLimits 6 values >>= right
  roundtrip bytes
  W.decode W.defaultLimits 5 bytes >>= reject
  blank <- newByteArray 0 0
  W.decode W.defaultLimits 6 blank >>= reject
  W.encode W.defaultLimits (-1) values >>= reject
  -- Mutate only fixture-owned output, never corpus bytes.
  crc <- readByteArray bytes 76
  writeByteArray bytes 76 (xorInt crc 1)
  W.decode W.defaultLimits 6 bytes >>= reject

-- Independent bit-at-a-time CRC32/ISO-HDLC recurrence, adapted from the
-- existing BinaryP2WriterControls.crc32. Never calls any Bitstream CRC helper.
refStep :: Word.Word32 -> Int -> Word.Word32
refStep previous byte = bits 8 (Bits.xor previous (P.fromIntegral byte))
  where
    bits :: P.Int -> Word.Word32 -> Word.Word32
    bits n crc = if n P.== 0 then crc else bits (n P.- 1)
      (if (Bits..&.) crc 1 P.== 1
       then Bits.xor (Bits.shiftR crc 1) 0xedb88320
       else Bits.shiftR crc 1)
referenceAt :: [Int] -> Int -> Int -> Word.Word32 -> Int
referenceAt values end position seed = P.fromIntegral (Bits.xor final 0xffffffff)
  where
    selected = P.take (P.fromIntegral (end-position))
      (P.drop (P.fromIntegral position) values)
    final = List.foldl' step seed (P.zip (P.enumFrom position) selected)
    step crc (i,byte) = refStep crc (if i >= 76 && i < 80 then 0 else byte)
reference :: [Int] -> Int
reference values = referenceAt values (P.fromIntegral (P.length values)) 0 0xffffffff
assertInt :: String -> Int -> Int -> IO ()
assertInt label wanted got = if wanted == got then ioReturn () else panic label
makeBytes :: [Int] -> IO ByteArray
makeBytes values = do
  bytes <- newByteArray (P.fromIntegral (P.length values)) 0
  let fill i xs = case xs of
        [] -> ioReturn ()
        x:rest -> writeByteArray bytes i x >> fill (i+1) rest
  fill 0 values
  ioReturn bytes
readBytes :: ByteArray -> IO [Int]
readBytes bytes = do
  n <- lengthByteArray bytes
  let go i = if i == n then ioReturn [] else do
        b <- readByteArray bytes i
        rest <- go (i+1)
        ioReturn (b:rest)
  go 0
patternBytes :: Int -> [Int]
patternBytes n = P.take (P.fromIntegral n) (P.cycle [0,255,1,128,127,42])
parity :: [Int] -> IO ()
parity values = do
  bytes <- makeBytes values
  let size = P.fromIntegral (P.length values)
      expected = reference values
  W.checksum bytes size >>= assertInt "checksum/reference mismatch" expected
  W.checksumAt bytes size 0 4294967295 >>= assertInt "checksumAt/reference mismatch" expected

crcFinite :: IO ()
crcFinite = do
  let vector = P.map (\c -> P.fromIntegral (P.fromEnum c)) ("123456789" :: P.String)
  assertInt "independent known CRC vector" 3421780262 (reference vector)
  assertInt "independent empty CRC" 0 (reference [])
  parity []
  parity vector
  P.mapM_ (parity P.. patternBytes) [75,76,79,80,81,1023,1024,1025,4096]
  bytes <- makeBytes (patternBytes 81)
  P.mapM_ (\position -> P.mapM_ (\seed -> do
      actual <- W.checksumAt bytes 81 position (P.fromIntegral seed)
      assertInt "checksumAt absolute-position/seed mismatch"
        (referenceAt (patternBytes 81) 81 position seed) actual)
    ([0,0xffffffff] :: [Word.Word32])) [0,75,76,79,80,81]

crcMutation :: IO ()
crcMutation = do
  bytes <- makeBytes (patternBytes 1025)
  let action = W.checksum bytes 1025
  first <- action >>= E.evaluate
  assertInt "mutable first" (reference (patternBytes 1025)) first
  P.mapM_ (\i -> readByteArray bytes i >>= \v -> writeByteArray bytes i (xorInt v 255)) [76,77,78,79]
  action >>= assertInt "masked mutation changed checksum" first
  P.mapM_ (\i -> do
      v <- readByteArray bytes i
      writeByteArray bytes i (xorInt v 1)
      values <- readBytes bytes
      action >>= assertInt "saved IO action ignored write" (reference values)) [75,80]

data Sentinel = Sentinel P.String deriving (P.Show)
instance E.Exception Sentinel
poison :: P.String -> a
poison name = E.throw (Sentinel name)
expectSentinel :: P.String -> IO Int -> IO ()
expectSentinel wanted action = do
  result <- E.try (action >>= E.evaluate)
  case result of
    P.Left (Sentinel actual) -> if wanted P.== actual then ioReturn () else panic "wrong sentinel"
    P.Right _ -> panic "missing sentinel"
-- Catch only the specified HostError type. Async/unknown exceptions escape.
expectBounds :: IO Int -> IO ()
expectBounds action = do
  result <- E.try (action >>= E.evaluate)
  case result of
    P.Left (Host.HostError actual) -> if actual P.== "array index out of bounds"
      then ioReturn () else panic "wrong host bounds error"
    P.Right _ -> panic "missing bounds error"
crcDemand :: IO ()
crcDemand = do
  W.checksum (poison "unused-empty") 0 >>= assertInt "empty demanded bytes" 0
  W.checksumAt (poison "unused-equal") 81 81 0 >>= assertInt "equal bound demanded bytes" 4294967295
  W.checksumAt (poison "unused-mask") 80 76 4294967295 >>=
    assertInt "mask-only demanded bytes" (referenceAt (patternBytes 80) 80 76 0xffffffff)
  expectSentinel "size-first" (W.checksum (poison "array-second") (poison "size-first"))
  expectSentinel "byte-first" (W.checksumAt (poison "byte-first") 1 0 (poison "seed-second"))
  expectSentinel "seed-only" (W.checksumAt (poison "unused-mask") 80 76 (poison "seed-only"))
  expectSentinel "first-unmasked" (W.checksumAt (poison "first-unmasked") 81 79 4294967295)
  bytes <- makeBytes (patternBytes 1024)
  expectBounds (W.checksum bytes 1025)

expectLeft :: String -> Either String a -> IO ()
expectLeft wanted result = case result of
  Left actual -> check (actual == wanted)
  Right _ -> panic "expected exact decoder Left"
repairCRC :: ByteArray -> IO ()
repairCRC bytes = do
  values <- readBytes bytes
  let crc = reference values
  P.mapM_ (\i -> writeByteArray bytes (76+i)
    (andInt (unsignedShiftRInt crc (i*8)) 255)) [0,1,2,3]

-- One small concrete symbol-table shape. No extra production instrumentation
-- or claimed exhaustive decoder coverage. Geometry selects the scan route;
-- hints force the original fallback. Invalid UTF8 makes the attempted scan decline.
decoderBoundaries :: IO ()
decoderBoundaries = do
  let text = textFromChars (P.replicate 1536 'x')
      values = [W.VText text,W.VNode 7 [W.VText text],W.VInt (-1),W.VBits (-1)]
  forceValues values `seq` ioReturn ()
  tables <- right (W.plan W.defaultLimits values)
  geometry <- right (W.layout W.defaultLimits tables)
  case geometry of
    W.Layout total symbols section _ _ _ _ _ _ _ _ _ ->
      check (total >= 1024 && symbols == 1 && section <= 65536)
  bytes <- W.encode W.defaultLimits 6 values >>= right
  graph <- W.decodeGraph W.defaultLimits 6 bytes >>= right
  fallback <- W.decodeGraphWithText ["force-original-reader"] W.defaultLimits 6 bytes >>= right
  check (W.graphNodeCount graph == W.graphNodeCount fallback)
  -- Confirm the expected two-byte length prefix before mutating fixture output.
  assertInt "long-symbol varint width" 2 (W.varBytes 1536)
  first <- readByteArray bytes 82
  assertInt "fixture first symbol byte" 120 first
  writeByteArray bytes 82 255
  W.decodeGraph W.defaultLimits 6 bytes >>= expectLeft "binary checksum mismatch"
  W.decodeGraphWithGate W.defaultLimits 6
    (\_ _ -> ioReturn (Left "gate-first")) bytes >>= expectLeft "gate-first"
  W.decodeGraphWithGate W.defaultLimits 5
    (\_ _ -> poison "unexpected-schema-gate") bytes >>=
    expectLeft "binary artifact schema mismatch"
  repairCRC bytes
  W.decodeGraph W.defaultLimits 6 bytes >>= expectLeft "invalid binary UTF-8 leading byte"
  W.decodeGraphWithText ["force-original-reader"] W.defaultLimits 6 bytes >>=
    expectLeft "invalid binary UTF-8 leading byte"
  W.decodeGraph (W.Limits 79 1 1 1 1 1 1 1) 6 (poison "invalid-limits-read") >>=
    expectLeft "invalid binary codec limits"
  short <- newByteArray 79 0
  W.decodeGraph W.defaultLimits 6 short >>=
    expectLeft "binary file byte limit exceeded or truncated header"

crcBoundaryControls :: IO ()
crcBoundaryControls = crcFinite >> crcMutation >> crcDemand >> decoderBoundaries
-- Original public algorithm used as a distinct reference; unchanged putBits only.
originalPutVar :: ByteArray -> Int -> Int -> IO Int
originalPutVar bytes position bits = do
  let final = unsignedLtInt bits 128
      byte = orInt (andInt bits 127) (if final then 0 else 128)
  next <- W.putBits bytes position 8 byte
  if final then ioReturn next else originalPutVar bytes next (unsignedShiftRInt bits 7)

-- Pure unsigned base-128 byte oracle, independent of putBits and putVar.
varintOracle :: Int -> [Int]
varintOracle bits = go (P.toInteger (P.fromIntegral bits :: Word.Word64))
  where
    go n = let low=P.fromInteger (P.mod n 128)
           in if n P.< 128 then [low] else (low+128):go (P.div n 128)
byteOracle :: [Int] -> Int -> [Int] -> [Int]
byteOracle initial position encoded = P.foldl writeOne initial (P.zip [0..] encoded)
  where
    offset=P.fromIntegral (position % 8) :: P.Int
    base=P.fromIntegral (position / 8) :: P.Int
    set index f values = P.zipWith (\i old -> if i P.== index then f old else old) [0..] values
    writeOne values (n,byte)
      | offset P.== 0 = set (base P.+ n) (\_ -> byte) values
      | P.otherwise =
          let lower=Bits.shiftL ((Bits..&.) byte (Bits.shiftL 1 (8 P.- offset) P.- 1)) offset
              upper=Bits.shiftR byte (8 P.- offset)
          in set (base P.+ n P.+ 1) (\old -> (Bits..|.) old upper)
               (set (base P.+ n) (\old -> (Bits..|.) old lower) values)
assertByteList :: ByteArray -> [Int] -> IO ()
assertByteList bytes wanted = do
  actual <- readBytes bytes
  if actual P.== wanted then ioReturn () else panic "putVar byte oracle mismatch"
putVarFinite :: IO ()
putVarFinite = P.mapM_ one [(offset,len,fill) | offset<-[0..7],len<-[1..10],fill<-[0,165]]
  where
    one (offset,len,fill) = do
      let bits = if len == 1 then 0 else shiftLInt 1 (7*(len-1))
          encoded=varintOracle bits
          initial=P.replicate 16 fill
      assertInt "varint byte length" len (P.fromIntegral (P.length encoded))
      a <- makeBytes initial
      b <- makeBytes initial
      endA <- originalPutVar a offset bits
      endB <- W.putVar b offset bits
      assertInt "putVar return" (offset+8*len) endA
      assertInt "putVar return parity" endA endB
      equalBytes a b
      assertByteList b (byteOracle initial offset encoded)

-- Catch exactly these synchronous fixture/host errors, never async exceptions.
data PutOutcome = PutDone Int | PutBounds P.String | PutPoison P.String
  deriving (P.Eq,P.Show)
putOutcome :: IO Int -> IO PutOutcome
putOutcome action = E.catches
  (do value <- action >>= E.evaluate; ioReturn (PutDone value))
  [E.Handler (\(Sentinel name) -> ioReturn (PutPoison name)),
   E.Handler (\(Host.HostError name) -> ioReturn (PutBounds name))]
assertOutcome :: P.String -> PutOutcome -> PutOutcome -> IO ()
assertOutcome label wanted actual = if wanted P.== actual then ioReturn () else
  P.error ("putVar case=" P.++ label P.++ " expected=" P.++ P.show wanted P.++ " actual=" P.++ P.show actual)
-- Fixed failing/successful buffer cases verify the entire surviving buffer,
-- including writes that preceded a later failing read/write.
putVarBoundaryBuffers :: IO ()
putVarBoundaryBuffers = P.mapM_ one
  [(0,0,0,PutBounds "array index out of bounds"),
   (1,1,129,PutBounds "array index out of bounds"),
   (1,0,128,PutBounds "array index out of bounds"),
   (2,7,16384,PutBounds "array index out of bounds"),
   (16,0,-1,PutDone 80),
   (16,-1,0,PutBounds "integer shift overflow"),
   (16,-8,0,PutBounds "array index out of bounds"),
   (16,9223372036854775800,0,PutBounds "array index out of bounds"),
   (16,9223372036854775807,0,PutBounds "array index out of bounds")]
  where
    one (size,position,bits,wanted) = do
      a <- newByteArray size 165
      b <- newByteArray size 165
      oa <- putOutcome (originalPutVar a position bits)
      ob <- putOutcome (W.putVar b position bits)
      assertOutcome ("buffer/reference " P.++ P.show (size,position,bits)) wanted oa
      assertOutcome ("buffer/candidate " P.++ P.show (size,position,bits)) oa ob
      equalBytes a b
      -- Known partial-write sentinels independent of reference implementation.
      if size == 1 && position == 1 then readByteArray b 0 >>= assertInt "first unaligned byte before OOB" 167 else ioReturn ()
      if size == 1 && position == 0 then readByteArray b 0 >>= assertInt "aligned overwrite before OOB" 128 else ioReturn ()
putVarPoison :: IO ()
putVarPoison = do
  -- Evaluating an IO action to WHNF alone must not demand operands.
  _ <- E.evaluate (originalPutVar (poison "array") (poison "position") (poison "bits"))
  _ <- E.evaluate (W.putVar (poison "array") (poison "position") (poison "bits"))
  empty <- newByteArray 0 0
  bytes <- newByteArray 2 0
  let checkBoth label array position bits wanted = do
        oa <- putOutcome (originalPutVar array position bits)
        ob <- putOutcome (W.putVar array position bits)
        assertOutcome (label P.++ "/reference") wanted oa
        assertOutcome (label P.++ "/candidate") oa ob
  checkBoth "poison-1" empty 0 (poison "bits") (PutBounds "array index out of bounds")
  checkBoth "poison-2" empty 1 (poison "bits") (PutBounds "array index out of bounds")
  checkBoth "poison-3" (poison "array") 0 (poison "bits") (PutPoison "array")
  checkBoth "poison-4" (poison "array") (poison "position") (poison "bits") (PutPoison "position")
  checkBoth "poison-5" bytes 0 (poison "bits") (PutPoison "bits")
  checkBoth "poison-6" bytes 1 (poison "bits") (PutPoison "bits")
putVarControls :: IO ()
putVarControls = putVarFinite >> putVarBoundaryBuffers >> putVarPoison

payloads :: [(String,P.String,Int)]
payloads = [
  ("inputs/00.bin","8eaf20dd6413d531919d116f1abe49040d550e002b014b65621a6dbbb9f8e3b2",91),
  ("inputs/01.bin","dd99703e6016b3dd276ba46e251d0a28b48044c8606f78603a279b59839bd242",1510),
  ("inputs/02.bin","3aeadffde86e259c20cba46f9bc63ed9aa6c8a266c456aa9a7b939074968f420",56187),
  ("inputs/03.bin","4d3413140c61f886804351b99fb1f0f621864eaafd9df181e3f17ba75720f077",406975)
  ]

-- Exact public reference route: deliberately calls unchanged generic putBits.
originalPutReferences :: ByteArray -> Int -> Int -> [Int] -> IO Int
originalPutReferences bytes position width references = case references of
  [] -> ioReturn position
  index:rest -> do
    next <- W.putBits bytes position width index
    originalPutReferences bytes next width rest
originalPutEntry :: ByteArray -> Int -> Int -> Int -> W.Entry -> IO Int
originalPutEntry bytes position nodeWidth symbolWidth entry = do
  next <- W.putBits bytes position 2 (W.entryKind entry)
  case entry of
    W.EInt value -> W.putVar bytes next (W.zigzag value)
    W.EBits bits -> W.putBits bytes next 64 bits
    W.EText index -> W.putBits bytes next symbolWidth index
    W.ENode tag children -> do
      more <- W.putVar bytes next tag
      last <- W.putVar bytes more (Std.length children)
      originalPutReferences bytes last nodeWidth children

ignoredOutcome :: IO a -> IO PutOutcome
ignoredOutcome action = E.catches
  (action >> ioReturn (PutDone 0))
  [E.Handler (\(Sentinel name) -> ioReturn (PutPoison name)),
   E.Handler (\(Host.HostError name) -> ioReturn (PutBounds name))]
whnfOutcome :: IO a -> IO PutOutcome
whnfOutcome action = ignoredOutcome (E.evaluate action)

compareReferences label initial position width values = do
  a <- makeBytes initial
  b <- makeBytes initial
  oa <- putOutcome (originalPutReferences a position width values)
  ob <- putOutcome (W.putReferences b position width values)
  assertOutcome label oa ob
  equalBytes a b
  ioReturn (ob,b)
compareEntry label initial position nodeWidth symbolWidth entry = do
  a <- makeBytes initial
  b <- makeBytes initial
  oa <- putOutcome (originalPutEntry a position nodeWidth symbolWidth entry)
  ob <- putOutcome (W.putEntry b position nodeWidth symbolWidth entry)
  assertOutcome label oa ob
  equalBytes a b
  ioReturn (ob,b)

-- Independent low-bit byte oracle, not a call to either writer. Every logical
-- field is split at byte boundaries: full bytes overwrite, partial bytes OR.
referenceOracle :: [Int] -> Int -> Int -> [Int] -> [Int]
referenceOracle initial position width values = P.snd (List.foldl' field (position,initial) values)
  where
    field (position,bytes) value = chunks position width value bytes
    chunks position width value bytes = if width == 0 then (position,bytes) else
      let offset=position%8; take=if width < 8-offset then width else 8-offset
          mask=shiftLInt 1 take-1; piece=shiftLInt (andInt value mask) offset
          target=P.fromIntegral (position/8) :: P.Int
          updated=P.zipWith (\i old -> if i P.== target then
            (if take==8 then piece else orInt old piece) else old) [0..] bytes
      in chunks (position+take) (width-take) (unsignedShiftRInt value take) updated

narrowFinite :: IO ()
narrowFinite = P.mapM_ one [(offset,width,fill) | offset<-[0..7],width<-[1..16],fill<-[0,165]]
  where
    values=[0,1,127,128,(-1),(-9223372036854775808),9223372036854775807]
    one (offset,width,fill) = do
      let initial=P.replicate 24 fill
      (out,bytes) <- compareReferences "finite" initial offset width values
      assertOutcome "finite-position" (PutDone (offset+width*7)) out
      assertByteList bytes (referenceOracle initial offset width values)

narrowBounds :: IO ()
narrowBounds = do
  P.mapM_ (\(size,fill,position,width) -> do
    _ <- compareReferences "public boundary" (P.replicate size fill) position width [(-1),0]
    ioReturn ()) [(size,fill,position,width) | size<-[0,1,2,3],fill<-[0,85],
      position<-[-9,-8,-1,0,1,2,3,4,5,6,7,9223372036854775791,9223372036854775792,9223372036854775807],
      width<-[-1,0,1,7,8,9,15,16,17,63,64,65]]
  -- Explicit independent partial-side-effect sentinels at each fragment boundary.
  P.mapM_ (\(width,initial,wanted,result) -> do
    (actual,bytes) <- compareReferences "offset7 fragments" initial 7 width [(-1)]
    assertOutcome "offset7 result" result actual
    assertByteList bytes wanted)
    [(1,[85],[213],PutDone 8),
     (8,[85],[213],PutBounds "array index out of bounds"),
     (8,[85,85],[213,127],PutDone 15),
     (9,[85,85],[213,255],PutDone 16),
     (16,[85],[213],PutBounds "array index out of bounds"),
     (16,[85,85],[213,255],PutBounds "array index out of bounds"),
     (16,[85,85,85],[213,255,127],PutDone 23)]
  (out,bytes) <- compareReferences "write-before-next-bounds" [0] 0 8 [5,poison "later-index"]
  assertOutcome "next bounds beats next index" (PutBounds "array index out of bounds") out
  assertByteList bytes [5]

narrowDemand :: IO ()
narrowDemand = do
  -- Public IO action construction, execution ignoring result, forced result.
  P.mapM_ (\(label,bytes,position,width,values,whnfWanted,ignoredWanted,forcedWanted) -> do
    wa <- whnfOutcome (originalPutReferences bytes position width values)
    wb <- whnfOutcome (W.putReferences bytes position width values)
    assertOutcome (label P.++ "/whnf-original") whnfWanted wa
    assertOutcome (label P.++ "/whnf-candidate") whnfWanted wb
    ia <- ignoredOutcome (originalPutReferences bytes position width values)
    ib <- ignoredOutcome (W.putReferences bytes position width values)
    assertOutcome (label P.++ "/ignore-original") ignoredWanted ia
    assertOutcome (label P.++ "/ignore-candidate") ignoredWanted ib
    fa <- putOutcome (originalPutReferences bytes position width values)
    fb <- putOutcome (W.putReferences bytes position width values)
    assertOutcome (label P.++ "/result-original") forcedWanted fa
    assertOutcome (label P.++ "/result-candidate") forcedWanted fb)
    [("empty",poison "bytes",poison "position",poison "width",[],PutDone 0,PutDone 0,PutPoison "position"),
     ("zero-width",poison "bytes",poison "position",0,[poison "index"],PutDone 0,PutDone 0,PutPoison "position"),
     ("zero-width-tail",poison "bytes",poison "position",0,poison "index":poison "tail",PutDone 0,PutPoison "tail",PutPoison "tail"),
     ("spine-first",poison "bytes",poison "position",poison "width",poison "spine",PutPoison "spine",PutPoison "spine",PutPoison "spine"),
     ("width-first",poison "bytes",poison "position",poison "width",[poison "index"],PutDone 0,PutPoison "width",PutPoison "width"),
     ("position-first",poison "bytes",poison "position",1,[poison "index"],PutDone 0,PutPoison "position",PutPoison "position"),
     ("buffer-first",poison "bytes",0,1,[poison "index"],PutDone 0,PutPoison "bytes",PutPoison "bytes")]
  P.mapM_ (\(size,position,width,values,wanted,prefix) -> do
    (out,bytes) <- compareReferences "poison/write ordering" (P.replicate size 0) position width values
    assertOutcome "poison/write ordering result" wanted out
    assertByteList bytes prefix)
    [(0,0,1,[poison "bits"],PutBounds "array index out of bounds",[]),
     (0,0,8,[poison "bits"],PutBounds "array index out of bounds",[]),
     (1,0,1,[poison "bits"],PutPoison "bits",[0]),
     (1,0,8,[poison "bits"],PutPoison "bits",[0]),
     (2,0,8,5:poison "tail",PutPoison "tail",[5,0]),
     (2,0,8,[5,poison "bits"],PutPoison "bits",[5,0])]

narrowEntry :: IO ()
narrowEntry = do
  P.mapM_ (\(initial,nodeWidth,entry,wanted,prefix) -> do
    (out,bytes) <- compareEntry "ENode prefix" initial 0 nodeWidth (poison "unused-symbolWidth") entry
    assertOutcome "ENode prefix result" wanted out
    assertByteList bytes prefix)
    [([0,0,0,0],12,W.ENode 7 (poison "children"),PutPoison "children",[31,0,0,0]),
     ([0,0,0,0],12,W.ENode 7 (0:poison "tail-before-refs"),PutPoison "tail-before-refs",[31,0,0,0]),
     ([0,0,0,0],12,W.ENode 7 [poison "child-index"],PutPoison "child-index",[31,4,0,0]),
     ([0],12,W.ENode 7 (poison "later-children"),PutBounds "array index out of bounds",[31]),
     ([0,0,0],poison "unused-nodeWidth",W.ENode 7 [],PutDone 18,[31,0,0])]
  empty <- newByteArray 0 0
  a <- whnfOutcome (originalPutEntry (poison "bytes") (poison "pos") (poison "nw") (poison "sw") (poison "entry"))
  b <- whnfOutcome (W.putEntry (poison "bytes") (poison "pos") (poison "nw") (poison "sw") (poison "entry"))
  assertOutcome "putEntry action WHNF original" (PutDone 0) a
  assertOutcome "putEntry action WHNF candidate" (PutDone 0) b
  oa <- putOutcome (originalPutEntry empty 0 1 1 (poison "entry"))
  ob <- putOutcome (W.putEntry empty 0 1 1 (poison "entry"))
  assertOutcome "putEntry bounds before entry original" (PutBounds "array index out of bounds") oa
  assertOutcome "putEntry bounds before entry candidate" (PutBounds "array index out of bounds") ob

loadPayload (path,_,wanted) = do
  (err,input) <- readByteFileOrError path 268435456
  check (err=="")
  size <- lengthByteArray input
  check (size==wanted)
  ioReturn input
realPayloadControls = P.mapM_ (\payload -> loadPayload payload >>= roundtrip) payloads
{-# NOINLINE prepareWriter #-}
prepareWriter input = do
  values <- W.decode W.defaultLimits 6 input >>= right
  E.evaluate (forceValues values)
  tables <- planned values
  geometry <- laidOut tables
  ioReturn (tables,geometry)
{-# NOINLINE wholeWriter #-}
wholeWriter geometry tables = W.encodeTables 6 geometry tables >>= right
validStats (allocated,elapsed) = allocated P.>= 0 P.&& elapsed P.<= 20000000000
statsFields (allocated,elapsed)=[P.show allocated,P.show elapsed]
measureOne index payload@(_,digest,bytes) = do
  input <- loadPayload payload
  (tables,geometry) <- prepareWriter input
  (_,before) <- observe (ioReturn ())
  (output,writer) <- observe (wholeWriter geometry tables)
  equalBytes input output
  (_,after) <- observe (ioReturn ())
  check (validStats before P.&& validStats writer P.&& validStats after)
  check (P.fst before P.== 0 P.&& P.fst after P.== 0 P.&& P.fst writer P.> 0)
  P.putStrLn (List.intercalate "\t" (["MEASURE",P.show index,digest,P.show bytes] P.++
    statsFields before P.++ statsFields writer P.++ statsFields after P.++ ["1"]))

main :: IO ()
main = do
  count <- getArgCount
  check (count==1)
  mode <- getArg 0
  if mode=="controls" then do
    finite
    P.putStrLn "PASS codec-control"
    crcBoundaryControls
    P.putStrLn "PASS crc-boundaries"
    putVarControls
    P.putStrLn "PASS putvar-controls"
    narrowFinite
    P.putStrLn "PASS narrow-finite"
    narrowBounds
    P.putStrLn "PASS narrow-bounds"
    narrowDemand
    P.putStrLn "PASS narrow-demand"
    narrowEntry
    P.putStrLn "PASS narrow-entry"
    realPayloadControls
    P.putStrLn "PASS real-payloads"
    P.putStrLn "SUMMARY\tcontrols\t8"
  else if mode=="measure" then do
    P.mapM_ (\(index,payload) -> measureOne index payload) (P.zip [(0::P.Int)..] payloads)
    P.putStrLn "SUMMARY\tmeasure\t4\t464763"
  else panic "expected controls or measure"
