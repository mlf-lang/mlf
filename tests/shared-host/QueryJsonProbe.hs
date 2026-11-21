module Main where

import Prelude
import Control.Exception (evaluate, try)
import Control.Monad (forM_, unless, replicateM)
import Data.Char (chr, ord)
import Numeric (showHex)
import qualified Bootstrap.CrateQuery as Q
import qualified MLF.Host.Base as B

need label ok = unless ok (fail label)
escape c | c == '"' = "\\\""
         | c == '\\' = "\\\\"
         | ord c < 32 = "\\u00" ++ (if ord c < 16 then "0" else "") ++ showHex (ord c) ""
         | otherwise = [c]
oracle = concatMap escape
check text = do
 let input = B.literal text
 forM_ [0, length text `div` 2, length text, length text + 1] $ \position -> do
  let actual = B.unpack (Q.jsonFrom input (fromIntegral position))
      expected = oracle (drop position text)
  need "JSON suffix differs from independent oracle" (actual == expected)
 need "JSON quoting" (B.unpack (Q.jsonString input) == '"':oracle text ++ "\"")
fails label action = do
 result <- try (evaluate action)
 case result of
  Left (B.HostError message) -> need label (message == label)
  Right _ -> fail (label ++ ": missing failure")
main = do
 let alphabet = ['a','\0','\n','"','\\','é','中','😀']
     strings = concatMap (`replicateM` alphabet) [0..4] ++
       [replicate n 'a' ++ [c] ++ replicate n 'b' | n <- [31,256,4096], c <- alphabet]
 mapM_ check strings
 forM_ [0..0x10ffff] $ \code ->
  if code >= 0xd800 && code <= 0xdfff then pure () else do
   let text = [chr code]; input = B.literal text
   need "Unicode scalar JSON" (B.unpack (Q.jsonFrom input 0) == oracle text)
 forM_ [Q.jsonFrom] $ \from -> do
  fails "position-first" (B.v_stringLength (from (B.failure "value-second") (B.failure "position-first")))
  fails "value" (B.v_stringLength (from (B.failure "value") 0))
  fails "invalid Unicode scalar" (B.v_stringLength (from (B.literal ['\xd800']) 0))
 need "unused branch" (if True then True else B.v_stringLength (Q.jsonFrom (B.failure "unused") 0) > 0)
 let groups = [Q.GroupResult (B.literal "id\n") [B.literal "é",B.literal "\0"] False (B.literal "hash") (B.literal "key\\")]
     expected = "{\"format\":1,\"crate\":\"crate\",\"semantic_fingerprint\":\"sha\",\"inferred_groups\":1,\"reused_groups\":0,\"groups\":[{\"id\":\"id\\u000a\",\"members\":[\"é\",\"\\u0000\"],\"cached\":false,\"semantic_fingerprint\":\"hash\",\"query_key\":\"key\\\\\"}]}\n"
 need "literal complete report" (B.unpack (Q.reportJSON (B.literal "crate") (B.literal "sha") (Q.QueryReport 1 0 groups)) == expected)
 putStrLn ("PASS JSON: " ++ show (length strings) ++ " strings at four suffix positions; 1112064 Unicode scalars; 4 demand controls; independent literal report")
