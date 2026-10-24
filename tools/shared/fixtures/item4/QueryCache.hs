{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import System.Environment (getArgs)
import qualified Bootstrap.Types as T
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.Separate as U
import qualified Bootstrap.X.Pretty as Pretty
import qualified MLF.Host.Base as B
expect label result = case result of
  T.Left err -> error (label ++ ": " ++ B.unpack err)
  T.Right x -> pure x
check label b = if b then putStrLn ("PASS " ++ label) else error label
members n = (:) ((,,) "main" T.Nothing
  (T.SApp (T.SApp (T.SConstructor ":") (T.SIntLit n)) (T.SConstructor "[]"))) []
main = do
  [path] <- getArgs
  let compile n = Q.compileGroups "item4:cache" (B.literal path) [] [] (members n)
  (,) objects cold <- compile 41 >>= expect "cold inference"
  check "cold inference count" (Q.inferredCount cold == 1 && Q.reusedCount cold == 0)
  check "inferred canonical list result" $ case objects of
    (:) o [] -> case U.unitBindings (U.objectInterface o) of
      (:) ((,) _ ty) [] -> B.unpack (Pretty.prettyType ty) == "[] Int"
      _ -> False
    _ -> False
  (,) _ warm <- compile 41 >>= expect "warm cache"
  check "warm cache reuse" (Q.inferredCount warm == 0 && Q.reusedCount warm == 1)
  (,) _ changed <- compile 42 >>= expect "changed literal"
  check "literal mutation invalidates cache" (Q.inferredCount changed == 1 && Q.reusedCount changed == 0)
  putStrLn "item4 query cold/warm controls: passed"
