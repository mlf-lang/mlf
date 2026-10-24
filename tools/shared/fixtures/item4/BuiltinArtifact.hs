{-# LANGUAGE OverloadedStrings #-}
-- Actual builtin class lowering, compilation, interface/object decoding and link.
module Main where
import Prelude
import qualified Bootstrap.Types as T
import qualified Bootstrap.CrateArtifact as A
import qualified MLF.Host.Base as B
import qualified Bootstrap.Module as M
import qualified Bootstrap.Std as S
import qualified MLF.Primitive as P
import qualified Bootstrap.Crate as C
import qualified Bootstrap.Parser as Parser
expect label result = case result of
  T.Left err -> error (label ++ ": " ++ B.unpack err)
  T.Right x -> putStrLn ("PASS " ++ label) >> pure x
main = do
  object <- expect "compile builtin Prelude" A.builtinPrelude
  iface <- expect "decode builtin interface" (A.decodeInterface (A.encodeInterface (A.objectInterface object)))
  let exports name = S.fromMaybe [] (S.lookup P.eqString name (A.crateExports iface))
      reach name = S.fromMaybe [] (S.lookup P.eqString name (A.crateImports iface))
      check label ok = if ok then putStrLn ("PASS " ++ label) else error label
  check "decoded Prelude exports exact canonical facade entities" (not (null (exports "Prelude")) && S.eqList (\a b -> M.compareEntity a b == 0) (exports "Prelude") (exports "MLF.Primitive"))
  check "decoded Prelude reach includes canonical instance owner" (S.elem P.eqString "MLF.Primitive" (reach "Prelude"))
  check "decoded Prelude carries canonical public class identities" (all (\name -> any (\entity -> P.eqString (M.owner entity) "MLF.Primitive" && P.eqString (M.spelling entity) name && M.isRole M.Class entity) (exports "Prelude")) ["Eq", "IsString", "Monad"])
  check "decoded facade does not expose private stack authority" (all (\entity -> all (\private -> not (P.eqString (M.spelling entity) private)) ["MLFStackEvidence", "MLFStackFrame", "MLFLegacyUnit"]) (exports "Prelude"))
  let changeIdentity name modules (A.CrateInterface _ deps _ es reach ds cs instances lowered bindings entry objectHash protection) = A.CrateInterface name deps modules es reach ds cs instances lowered bindings entry objectHash protection
      rejects label diagnostic mutated = check label (case A.decodeInterface (A.encodeInterface mutated) of { T.Left message -> P.eqString message diagnostic; T.Right _ -> False })
  rejects "stale builtin7 rejected on metadata decode" "stale or forged builtin crate identity" (changeIdentity "mlf:builtin-shared-haskell-v1:7" (A.crateModules iface) iface)
  rejects "user crate cannot own builtin modules" "stale or forged builtin crate identity" (changeIdentity "user-forgery" (A.crateModules iface) iface)
  rejects "builtin missing owner rejected" "builtin crate must own exactly Prelude and MLF.Primitive" (changeIdentity A.builtinCrateIdentity ["Prelude"] iface)
  rejects "builtin extra owner rejected" "builtin crate must own exactly Prelude and MLF.Primitive" (changeIdentity A.builtinCrateIdentity ["Prelude", "MLF.Primitive", "User"] iface)
  source <- expect "parse decoded facade dependency consumer" (Parser.parseModule "Consumer.emlf" "module Consumer where\nimport Prelude\nmain = 42\n")
  let stale = changeIdentity "mlf:builtin-shared-haskell-v1:7" (A.crateModules iface) iface
      spec = C.CrateSpec "consumer" "Consumer" T.NoImplicitPrelude [] ["not-opened.mlfci"] "not-used" "not-used"
  staleSelection <- C.withPrelude spec [source] [("not-opened.mlfci", stale)]
  check "stale builtin dependency rejected before shortcut file access" (case staleSelection of { T.Left message -> P.eqString message "stale or forged builtin crate identity"; T.Right _ -> False })
  restored <- expect "decode builtin object" (A.decodeObject iface (A.encodeObject object))
  _ <- expect "link restored builtin object" (A.linkCheckedObjects ((:) restored []) (A.crateId iface))
  putStrLn "item4 builtin artifact end-to-end: passed"
