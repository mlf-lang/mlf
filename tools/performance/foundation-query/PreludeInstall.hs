{-# LANGUAGE OverloadedStrings #-}
module Main where

import Prelude
import Control.Monad (unless)
import System.Environment (getArgs)
import qualified Bootstrap.Crate as Crate
import qualified Bootstrap.BuiltinPreludeContext as Context
import qualified Bootstrap.BuiltinPreludeLiteral as Literal
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.Types as T
import qualified MLF.BuiltinPreludeData as Builtin
import qualified MLF.Host.Base as Host
import qualified MLF.Primitive as P

expect (T.Right x) = pure x
expect (T.Left msg) = error (Host.unpack msg)
reject (T.Left _) = pure ()
reject (T.Right _) = error "unexpectedly admitted a different builtin"

-- Keep the original compiler identity, interface, exports and sources. Add
-- one type-correct, unexported binding to the complete linked target.
alter raw = case raw of
  Context.RawPrelude identity count iface (T.XWithData ds body) available serial names env values protected contracts witnesses ->
    let changed = T.XLet (T.XName serial "added") (T.XIntTerm 41) body
    in Context.RawPrelude identity count iface (T.XWithData ds changed) available (serial + 1) names env values protected contracts witnesses
  _ -> error "missing closed datatype context"

main = do
  original <- expect (Context.checkCompilerPrelude Builtin.builtin)
  object <- expect (Literal.checkedCrateObject original Builtin.builtinObject)
  unless (Artifact.encodeObject object == Builtin.builtinObject) (error "different split representation")
  reject (Literal.checkedCrateObject original "wrong")
  let oversized = iterate (\text -> P.concatString text text) "a" !! 23
  case Literal.checkedCrateObject original oversized of
    T.Left message | message == "prepared Prelude object exceeds literal limit" -> pure ()
    _ -> error "oversized embedded input bypassed its admission limit"
  changed <- expect (Context.checkCompilerPrelude (alter Builtin.builtin))
  case Literal.checkedCrateObject changed Builtin.builtinObject of
    T.Left message | message == "prepared Prelude object differs from its checked linked witness" -> pure ()
    _ -> error "same identity and interface admitted a different linked target"
  [prefix] <- getArgs
  _ <- Crate.ensureBuiltinWith (T.Just (original, "wrong")) (Host.literal prefix) >>= expect
  iface <- Artifact.readInterface (Host.literal (prefix ++ ".mlfci")) >>= expect
  recovered <- Artifact.readObject (Host.literal (prefix ++ ".mlfco")) iface >>= expect
  unless (Artifact.encodeObject recovered == Builtin.builtinObject) (error "invalid embedded object was installed")
  putStrLn "PASS embedded split object, corrupted encoding, forged witness and fresh repair"
