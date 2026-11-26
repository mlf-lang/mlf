{-# LANGUAGE OverloadedStrings #-}
module Main where

import Control.Exception (evaluate, try)
import Control.Monad (forM_, unless, when)
import qualified Data.ByteString as BS
import System.Mem (performGC)
import qualified Bootstrap.ArtifactStructure as Artifact
import qualified Bootstrap.Primitive as Meta
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as B
import qualified MLF.Host.IO as Host
import qualified EqualGC as GC

need :: String -> Bool -> IO ()
need label yes = unless yes (fail label)

observe :: IO a -> IO (Either String ())
observe action = do
  outcome <- try (action >> pure ())
  pure $ case outcome of
    Left (B.HostError message) -> Left message
    Right () -> Right ()

metadata = do
  need "append-only primitive inventory" (map Meta.primitiveCode Meta.allPrimitives == [0..137])
  need "existing opcode retained" (Meta.primitiveCode T.PStringUtf8Length == 136)
  need "binary IO primitive metadata" (Meta.primitiveCode T.PByteArrayEqual == 137 &&
    Meta.primitiveArity T.PByteArrayEqual == 2 && not (Meta.primitiveStrict T.PByteArrayEqual))
  need "primitive name" (B.unpack (Meta.primitiveName T.PByteArrayEqual) == "byteArrayEqual")
  need "primitive name lookup" (case Meta.lookupTargetPrimitive "byteArrayEqual" of
    T.Just T.PByteArrayEqual -> True; _ -> False)
  need "primitive signature" (case Meta.primitiveSignature T.PByteArrayEqual of
    ([],T.Function (T.Applied a []) (T.Function (T.Applied b []) (T.Applied io [T.Applied boolean []]))) ->
      map B.unpack [a,b,io,boolean] == ["ByteArray","ByteArray","IO","Bool"]
    _ -> False)
  need "artifact opcode roundtrip" (case Artifact.fromPrimitive (Artifact.toPrimitive T.PByteArrayEqual) of
    T.Right T.PByteArrayEqual -> True; _ -> False)

checkPair make equal writeAt leftBytes rightBytes = do
  left <- make leftBytes
  right <- make rightBytes
  let action = equal left right
  evaluate action
  performGC
  first <- action
  need "independent exact byte oracle" (first == (leftBytes == rightBytes))
  when (not (BS.null leftBytes)) $ do
    let initial = BS.head leftBytes
        changed = initial + 1
        changedBytes = BS.cons changed (BS.tail leftBytes)
    writeAt left 0 (fromIntegral changed)
    second <- action
    need "reused action observes subsequent mutation" (second == (changedBytes == rightBytes))
    writeAt left 0 (fromIntegral initial)
    third <- action
    need "restored contents compare again" (third == first)
    let delayed = equal left right
    evaluate delayed
    writeAt left 0 (fromIntegral changed)
    late <- delayed
    need "new action observes mutation before first execution" (late == (changedBytes == rightBytes))
  aliased <- equal left left
  need "same owner compares equal" aliased

-- The GC-injected borrow has sole ownership of both temporary byte arrays.
-- The independent expected ByteString does not retain either pinned owner.
{-# NOINLINE transient #-}
transient count = do
  left <- GC.bytesArray (BS.pack (take count (cycle [0,17,255,39])))
  right <- GC.bytesArray (BS.pack (take count (cycle [0,17,255,39])))
  GC.v_byteArrayEqual left right

demand = do
  let badLeft = B.failure "left-demand"
      badRight = B.failure "right-demand"
  built <- observe (evaluate (Host.v_byteArrayEqual badLeft badRight))
  need "IO construction leaves both arrays lazy" (built == Right ())
  failed <- observe (Host.v_byteArrayEqual badLeft badRight)
  need "left array is demanded first" (failed == Left "left-demand")
  empty <- Host.bytesArray BS.empty
  failedRight <- observe (Host.v_byteArrayEqual empty badRight)
  need "right array is demanded even beside an empty left array" (failedRight == Left "right-demand")

main = do
  metadata
  let sizes = [0,1,2,7,31,32,63,64,255,256,4095,4096,4097,65537,1048583]
  forM_ sizes $ \size -> do
    let bytes = BS.pack (take size (cycle [0,255,17,39,128,0,11]))
        different = [BS.take i bytes <> BS.singleton (BS.index bytes i + 1) <> BS.drop (i+1) bytes
          | i <- if size == 0 then [] else [0,size `div` 2,size-1]]
        others = bytes : (bytes <> BS.singleton 0) : BS.take (max 0 (size-1)) bytes : different
    forM_ others $ \other -> do
      checkPair Host.bytesArray Host.v_byteArrayEqual Host.v_writeByteArray bytes other
      checkPair GC.bytesArray GC.v_byteArrayEqual GC.v_writeByteArray bytes other
  forM_ [0,1,65537,1048583] $ \size -> transient size >>= need "temporary pinned owners survive GC during borrow"
  demand
  putStrLn "PASS byte-array equality: independent exact bytes, mutation, metadata, lazy IO, and pinned-owner GC"
