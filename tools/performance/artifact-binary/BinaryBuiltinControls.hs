{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
-- Binary is the primary disk path. The frozen text controls run separately.
module BinaryBuiltinControls where
import Prelude
import Control.Monad (forM_)
import System.Environment (getArgs, withArgs)
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P
import qualified Bootstrap.Types as T
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.ArtifactStructure as Structure
import qualified Bootstrap.ArtifactStorage as Storage
import qualified Bootstrap.Bitstream as Wire
import qualified CurrentBuiltinControls as Frozen

-- Copy before mutation: never modify the snapshot used for canonical checks.
mutateByte :: P.ByteArray -> P.Int -> P.Int -> IO P.ByteArray
mutateByte input index value = do
 size <- P.lengthByteArray input
 Frozen.assert "bounded binary mutation index" (index >= 0 && index < size)
 output <- P.newByteArray size 0
 let copy i = if i == size then pure () else do
       byte <- P.readByteArray input i
       P.writeByteArray output i byte
       copy (i + 1)
 copy 0
 P.writeByteArray output index value
 pure output

requireBinary :: String -> P.Int -> P.ByteArray -> IO Wire.Graph
requireBinary label schema bytes = do
 magic <- Wire.hasMagic bytes
 Frozen.assert (label ++ " is actual binary, not a text projection") magic
 Wire.decodeGraph Wire.defaultLimits schema bytes >>= Frozen.right label

main :: IO ()
main = do
 args <- getArgs
 prefix <- case args of
  [value] -> pure value
  _ -> errorWithoutStackTrace "expected one builtin prefix"
 let interfacePath = prefix ++ ".mlfci"
     objectPath = prefix ++ ".mlfco"
 iface <- A.readInterface (B.literal interfacePath) >>= Frozen.right "public binary interface reader"
 object <- A.readObject (B.literal objectPath) iface >>= Frozen.right "public binary object reader"
 interfaceBytes <- Storage.readRaw (B.literal interfacePath) >>= Frozen.right "raw binary interface"
 objectBytes <- Storage.readRaw (B.literal objectPath) >>= Frozen.right "raw binary object"
 _ <- requireBinary "schema 3 interface" 3 interfaceBytes
 _ <- requireBinary "schema 4 object" 4 objectBytes
 canonicalInterface <- Storage.encode 3 [Structure.toCrateInterfaceFields (A.binaryInterfaceFields iface)] >>= Frozen.right "canonical binary interface"
 canonicalObject <- Storage.encode 4 [Structure.toCrateObjectFields (A.binaryObjectFields object)] >>= Frozen.right "canonical binary object"
 Storage.sameBytes interfaceBytes canonicalInterface >>= Frozen.assert "noncanonical binary interface bytes"
 Storage.sameBytes objectBytes canonicalObject >>= Frozen.assert "noncanonical binary object bytes"
 raw <- Frozen.right "reconstruct full binary builtin" (Frozen.reconstruct iface object)
 Frozen.right "admit full binary builtin" (Frozen.validateRaw raw)

 -- Real raw-byte corruptions go through the public disk reader, with exact
 -- diagnostics. Full magic remains present: no legacy fallback is possible.
 versionBytes <- mutateByte interfaceBytes 8 2
 crc <- P.readByteArray interfaceBytes 76
 crcBytes <- mutateByte interfaceBytes 76 (if crc == 0 then 1 else 0)
 forM_ [("version", versionBytes, "unsupported binary format version"),
        ("crc", crcBytes, "binary checksum mismatch")] $ \(name, bytes, reason) -> do
  let path = prefix ++ ".binary-negative-" ++ name
  Storage.writeRaw (B.literal path) bytes >>= Frozen.right "save corrupt binary witness"
  result <- A.readInterface (B.literal path)
  Frozen.reject ("binary " ++ name) (path ++ ": " ++ reason) result
 schemaResult <- Wire.decodeGraph Wire.defaultLimits 4 interfaceBytes
 Frozen.reject "binary schema separation" "binary artifact schema mismatch" schemaResult

 -- Re-encode well-formed wire (including a fresh CRC) to reach semantic
 -- metadata/body pairing checks rather than accepting an unrelated wire error.
 let wrongIface = A.withObjectFingerprint iface "wrong-binary-object-fingerprint"
     wrongObject = case object of
       A.CrateObject _ fragments -> A.CrateObject wrongIface fragments
       A.LegacyCrateObject _ fragments -> A.LegacyCrateObject wrongIface fragments
     wrongPath = prefix ++ ".binary-negative-pairing"
 wrongBytes <- Storage.encode 4 [Structure.toCrateObjectFields (A.binaryObjectFields wrongObject)] >>= Frozen.right "encode semantic binary corruption"
 Storage.writeRaw (B.literal wrongPath) wrongBytes >>= Frozen.right "save semantic binary corruption"
 pairing <- A.readObject (B.literal wrongPath) iface
 Frozen.reject "binary metadata pairing" (wrongPath ++ ": crate object metadata mismatch") pairing
 body <- A.readObject (B.literal wrongPath) wrongIface
 Frozen.reject "binary body fingerprint" (wrongPath ++ ": crate object checksum mismatch") body

 -- Explicit legacy compatibility branch, not the primary path. The original
 -- fixture is copied unchanged and runs its exact seven frozen negative cases.
 -- These additional files neither replace nor rename the actual binary pair.
 let legacyPrefix = prefix ++ ".explicit-legacy"
 writeFile (legacyPrefix ++ ".mlfci") (B.unpack (A.encodeInterface iface))
 writeFile (legacyPrefix ++ ".mlfco") (B.unpack (A.encodeObject object))
 withArgs [legacyPrefix] Frozen.main
 -- Re-read original binary bytes after all probes: the input pair is immutable.
 afterInterface <- Storage.readRaw (B.literal interfacePath) >>= Frozen.right "original interface after probes"
 afterObject <- Storage.readRaw (B.literal objectPath) >>= Frozen.right "original object after probes"
 Storage.sameBytes interfaceBytes afterInterface >>= Frozen.assert "original binary interface changed"
 Storage.sameBytes objectBytes afterObject >>= Frozen.assert "original binary object changed"
 putStrLn "PASS binary builtin: public readers, canonical bytes, fixed literal/full check, 5 binary rejections, separate frozen legacy 7"
