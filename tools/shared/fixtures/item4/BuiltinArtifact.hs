{-# LANGUAGE OverloadedStrings #-}
-- Actual builtin class lowering, compilation, interface/object decoding and link.
module Main where
import Prelude
import qualified Bootstrap.Types as T
import qualified Bootstrap.CrateArtifact as A
import qualified MLF.Host.Base as B
expect label result = case result of
  T.Left err -> error (label ++ ": " ++ B.unpack err)
  T.Right x -> putStrLn ("PASS " ++ label) >> pure x
main = do
  object <- expect "compile builtin Prelude" A.builtinPrelude
  iface <- expect "decode builtin interface" (A.decodeInterface (A.encodeInterface (A.objectInterface object)))
  restored <- expect "decode builtin object" (A.decodeObject iface (A.encodeObject object))
  _ <- expect "link restored builtin object" (A.linkCheckedObjects (T.Cons restored T.Nil) (A.crateId iface))
  putStrLn "item4 builtin artifact end-to-end: passed"
