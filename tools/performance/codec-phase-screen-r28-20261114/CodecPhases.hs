-- SOURCE ONLY. Not compiled; no throughput or allocation results yet.
{-# LANGUAGE NoImplicitPrelude, OverloadedStrings #-}
module Main where
import MLF.Primitive
import Bootstrap.Types
import qualified Bootstrap.Bitstream as W
import qualified Prelude as P
import qualified Control.Exception as E
import qualified System.Mem as Mem
import qualified GHC.Clock as Clock
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
main = do
  count <- getArgCount
  check (count == 4)
  let loop i = if i == count then ioReturn () else do
        path <- getArg i
        one i path
        loop (i+1)
  loop 0
  putStrLn "PASS codec-phases"
