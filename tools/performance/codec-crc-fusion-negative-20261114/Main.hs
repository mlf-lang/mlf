-- SOURCE ONLY. Common fresh A/B Main; controls then fixed phase observation.
{-# LANGUAGE NoImplicitPrelude, OverloadedStrings #-}
module Main where
import MLF.Primitive
import Bootstrap.Types
import qualified Bootstrap.Bitstream as W
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
record index stage (allocated,elapsed) =
  P.putStrLn (P.show index P.++ "\t" P.++ stage P.++ "\t" P.++ P.show allocated P.++ "\t" P.++ P.show elapsed)
one index path = do
  (err,bytes) <- readByteFileOrError path 268435456
  check (err == "")
  values <- W.decode W.defaultLimits 6 bytes >>= right
  E.evaluate (forceValues values)
  (_,emptyBefore) <- observe (ioReturn ())
  (tables,planStats) <- observe (planned values)
  (_,forceTablesStats) <- observe (E.evaluate (forceTables tables))
  (geometry,layoutStats) <- observe (laidOut tables)
  (blob,writeStats) <- observe (W.encodeTables 6 geometry tables >>= right)
  equalBytes bytes blob
  size <- lengthByteArray blob
  (crc,crcStats) <- observe (W.checksum blob size >>= E.evaluate)
  -- Check standalone checksum matches the existing stored checksum, outside
  -- the measured interval; checksum intentionally treats bytes76..79 as0.
  c0 <- readByteArray blob 76
  c1 <- readByteArray blob 77
  c2 <- readByteArray blob 78
  c3 <- readByteArray blob 79
  check (crc == c0 + shiftLInt c1 8 + shiftLInt c2 16 + shiftLInt c3 24)
  (_,emptyAfter) <- observe (ioReturn ())
  record index "empty-before" emptyBefore
  record index "plan" planStats
  record index "force-tables-control" forceTablesStats
  record index "layout" layoutStats
  record index "writer-plus-crc" writeStats
  record index "standalone-crc" crcStats
  record index "empty-after" emptyAfter

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
controlOne :: Int -> String -> IO ()
controlOne _ path = do
  (err,bytes) <- readByteFileOrError path 268435456
  check (err == "")
  roundtrip bytes
fixedPayloads action =
  let loop i = if i == 4 then ioReturn () else do
        path <- getArg (i+1)
        action i path
        loop (i+1)
  in loop 0
main = do
  count <- getArgCount
  check (count == 5)
  mode <- getArg 0
  if mode == "controls" then do
    finite
    fixedPayloads controlOne
    putStrLn "PASS codec-control"
    crcBoundaryControls
    putStrLn "PASS crc-boundaries"
  else if mode == "phases" then do
    fixedPayloads one
    putStrLn "PASS codec-phases"
  else panic "expected controls or phases plus four fixed payloads"
