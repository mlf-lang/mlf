{-# LANGUAGE OverloadedStrings #-}
-- Host-only actual binary publication checks, separate from the projected
-- historical text writer. Header/CRC inspection below does not call the codec.
module BinaryP2WriterControls where
import Prelude
import Control.Exception (SomeException, displayException, try)
import Control.Monad (forM_, unless)
import Data.Bits
import qualified Data.ByteString as BS
import qualified Data.ByteString.Char8 as BC
import Data.IORef
import Data.List (isInfixOf)
import qualified Data.Map.Strict as Map
import Data.Word (Word32)
import System.Directory (createDirectory, doesFileExist, doesPathExist)
import System.Environment (getArgs)
import System.FilePath ((</>))
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.ArtifactStorage as Storage
import qualified Bootstrap.ArtifactStructure as Structure
import qualified Bootstrap.Bitstream as Wire
import qualified Bootstrap.Types as T
import qualified Bootstrap.Separate as S
import qualified MLF.Host.Base as H
import qualified RetainedP2Controls as Legacy
import qualified FrozenFingerprint as Old

check ref group label ok = do
 unless ok (fail ("binary P2 writer: " ++ label))
 modifyIORef' ref (Map.insertWith (+) group (1::Int))
right label result = case result of
 T.Left message -> fail (label ++ ": " ++ H.unpack message)
 T.Right value -> pure value
crc32 :: BS.ByteString -> Word32
crc32 bytes = complement (BS.foldl' step 0xffffffff bytes)
 where
 step crc byte = bits 8 (crc `xor` fromIntegral byte)
 bits 0 crc = crc
 bits n crc = bits (n-1) (if crc .&. 1 == 1 then (crc `shiftR` 1) `xor` 0xedb88320 else crc `shiftR` 1)
word raw offset = sum [toInteger (BS.index raw (offset+i)) `shiftL` (8*i) | i <- [0..3]]
width count = max 1 (go (count-1)) where go n = if n <= 0 then 0 else 1 + go (n `div` 2)
envelope schema raw = BS.length raw >= 80 && BS.take 8 raw == BC.pack "MLFBIN\r\n" &&
 word raw 8 == 1 && word raw 12 == 0 && word raw 16 == schema && word raw 20 == 80 &&
 word raw 24 == toInteger (BS.length raw) && word raw 32 == 80 &&
 word raw 44 == 80 + word raw 36 && word raw 60 == word raw 44 + word raw 48 &&
 word raw 24 == word raw 60 + word raw 64 && word raw 56 == 1 &&
 word raw 68 == width (word raw 40) && word raw 72 == width (word raw 28) &&
 word raw 64 == (word raw 56 * word raw 68 + 7) `div` 8 &&
 toInteger (crc32 (BS.take 76 raw <> BS.replicate 4 0 <> BS.drop 80 raw)) == word raw 76
frame ref label schema raw = check ref "independent-envelope" label (envelope schema raw)
graph schema path = do
 bytes <- Storage.readRaw (H.literal path) >>= right "read raw bytes"
 Wire.decodeGraph Wire.defaultLimits schema bytes >>= right "canonical production graph decode"
rawInterface ref path expected = do
 g <- graph 3 path
 roots <- case Wire.graphRoots g of [v] -> pure v; _ -> fail "interface roots"
 fields <- right "typed raw interface" (Structure.fromGraphCrateInterfaceFields g roots)
 iface <- right "interface fields" (A.fromBinaryInterfaceFields fields)
 check ref "raw-interface" path (H.utf8 (Old.oldEncodeInterface iface) == H.utf8 (Old.oldEncodeInterface expected))
rawObject ref path expected = do
 g <- graph 4 path
 root <- case Wire.graphRoots g of [v] -> pure v; _ -> fail "object roots"
 fields <- right "typed raw object" (Structure.fromGraphCrateObjectFields g root)
 object <- case fields of
  Structure.CrateObjectFields legacy metadata fragments -> do
   iface <- right "raw metadata" (A.fromBinaryInterfaceFields metadata)
   pure (if legacy then A.LegacyCrateObject iface fragments else A.CrateObject iface fragments)
 check ref "raw-object" path (H.utf8 (Old.oldEncodeObject object) == H.utf8 (Old.oldEncodeObject expected))
publicRead ref prefix expected = do
 iface <- A.readInterface (H.literal (prefix ++ ".mlfci")) >>= right "public interface"
 check ref "public-interface" prefix (H.utf8 (Old.oldEncodeInterface iface) == H.utf8 (Old.oldEncodeInterface (A.objectInterface expected)))
 object <- A.readObject (H.literal (prefix ++ ".mlfco")) iface >>= right "public object"
 check ref "public-object" prefix (H.utf8 (Old.oldEncodeObject object) == H.utf8 (Old.oldEncodeObject expected))
write mode prefix object = if mode == (0::Int) then A.writeObject (H.literal prefix) object
 else A.writeObjectWithPayload (H.literal prefix) object (error "binary paired writer forced unused text payload")
reject ref label wanted result = check ref "corruption-rejection" label $ case result of
 T.Left message -> H.unpack message == wanted
 T.Right _ -> False
expectFailure ref label reason action = do
 result <- try action :: IO (Either SomeException ())
 check ref "publication-failure" label $ case result of
  Left err -> reason `isInfixOf` displayException err
  Right _ -> False
main = do
 args <- getArgs
 directory <- case args of [d] -> pure (d </> "binary-public"); _ -> fail "binary writer output argument"
 createDirectory directory
 count <- newIORef Map.empty
 check count "crc-vector" "independent standard CRC vector" (crc32 (BC.pack "123456789") == 0xcbf43926)
 let iface = Legacy.base "write:λ\x1f642"
     cases = [(label, Old.oldMakeObject iface fragments, A.makeObject iface fragments) | (label,fragments) <- Legacy.fragmentCases]
     legacyIface = A.withObjectFingerprint (Legacy.base "legacy") (A.legacyFragmentFingerprint [])
     legacy = A.LegacyCrateObject legacyIface []
     allCases = cases ++ [("legacy",legacy,legacy)]
     -- Historical unequal header/body contexts are RAW wire cases only here.
     -- They are not relabeled as successful semantic admission.
     publicSuccess = ["empty","int","unicode","shared-layout","checked","legacy"]
 forM_ (zip [0::Int ..] allCases) $ \(i,(label,expected,actual)) -> do
  let root = directory </> show i
      oldPrefix = root ++ "-old"
  Old.oldWriteObject (H.literal oldPrefix) expected
  forM_ [0::Int,1] $ \mode -> do
   let prefix = root ++ "-" ++ show mode
   write mode prefix actual
   forM_ [(".mlfci",3),(".mlfco",4)] $ \(suffix,schema) -> do
    bytes <- BS.readFile (prefix ++ suffix)
    old <- BS.readFile (oldPrefix ++ suffix)
    frame count (label ++ suffix) schema bytes
    check count "new-wire-not-legacy" (label ++ suffix) (bytes /= old)
   rawInterface count (prefix ++ ".mlfci") (A.objectInterface expected)
   rawObject count (prefix ++ ".mlfco") expected
  forM_ [".mlfci",".mlfco"] $ \suffix -> do
   first <- BS.readFile (root ++ "-0" ++ suffix)
   second <- BS.readFile (root ++ "-1" ++ suffix)
   check count "paired-byte-equality" label (first == second)
  if label `elem` publicSuccess then forM_ [oldPrefix,root ++ "-0",root ++ "-1"] $ \prefix -> publicRead count prefix expected else pure ()
 let expected = Old.oldMakeObject iface []
     actual = A.makeObject iface []
     baseline = directory </> "0-0"
 forM_ [0::Int,1] $ \mode -> do
  let blocked = directory </> ("blocked-object-" ++ show mode)
  createDirectory (blocked ++ ".mlfco")
  expectFailure count "first write" "artifact destination is a directory"
   (write mode blocked (error "blocked first file forced object"))
  exists <- doesFileExist (blocked ++ ".mlfci")
  check count "first-write-no-interface" blocked (not exists)
  temporary <- doesPathExist (blocked ++ ".mlfco.new")
  check count "temporary-cleanup" blocked (not temporary)
  let second = directory </> ("blocked-interface-" ++ show mode)
  createDirectory (second ++ ".mlfci")
  expectFailure count "second write" "artifact destination is a directory" (write mode second actual)
  bytes <- BS.readFile (second ++ ".mlfco")
  frame count "complete first file after second failure" 4 bytes
  rawObject count (second ++ ".mlfco") expected
  temporary2 <- doesPathExist (second ++ ".mlfci.new")
  check count "temporary-cleanup" second (not temporary2)
  expectFailure count "NUL before object/payload demand" "file path contains NUL"
   (write mode (directory ++ "/bad\0path") (error "NUL path forced object"))
 input <- BS.readFile (baseline ++ ".mlfci")
 let mutate at value = BS.take at input <> BS.singleton value <> BS.drop (at+1) input
 forM_ [("version",mutate 8 2,"unsupported binary format version"),
        ("crc",mutate 76 (BS.index input 76 `xor` 1),"binary checksum mismatch")] $ \(label,bytes,reason) -> do
  let path = directory </> label
  BS.writeFile path bytes
  result <- A.readInterface (H.literal path)
  reject count label (path ++ ": " ++ reason) result
 schema <- A.readInterface (H.literal (baseline ++ ".mlfco"))
 reject count "schema" (baseline ++ ".mlfco: binary artifact schema mismatch") schema
 let wrongIface = A.withObjectFingerprint (A.objectInterface actual) "wrong-body-fingerprint"
     wrong = A.CrateObject wrongIface []
     wrongPrefix = directory </> "wrong-pair"
 A.writeObject (H.literal wrongPrefix) wrong
 paired <- A.readObject (H.literal (wrongPrefix ++ ".mlfco")) (A.objectInterface actual)
 reject count "metadata pairing" (wrongPrefix ++ ".mlfco: crate object metadata mismatch") paired
 body <- A.readObject (H.literal (wrongPrefix ++ ".mlfco")) wrongIface
 reject count "body fingerprint" (wrongPrefix ++ ".mlfco: crate object checksum mismatch") body
 observed <- readIORef count
 let expectedCounts = Map.fromList [("crc-vector",1),("independent-envelope",38),("raw-interface",18),
       ("raw-object",20),("new-wire-not-legacy",36),("paired-byte-equality",18),
       ("public-interface",18),("public-object",18),("corruption-rejection",5),
       ("publication-failure",6),("first-write-no-interface",2),("temporary-cleanup",4)]
 unless (observed == expectedCounts) (fail ("binary writer control inventory: " ++ show observed))
 putStrLn "PASS actual binary P2 writers: 184 checks; 9 raw cases, 6 public-reader successes, 5 corruptions, 6 publication failures; independent envelope/CRC and frozen semantic bytes"
