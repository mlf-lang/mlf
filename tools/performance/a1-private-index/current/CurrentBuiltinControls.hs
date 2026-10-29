{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -O0 #-}
-- Current representation admission, not a replacement historical byte oracle.
module CurrentBuiltinControls where
import Prelude
import Control.Monad (unless, foldM)
import System.Environment (getArgs)
import qualified MLF.Host.Base as B
import qualified MLF.BuiltinPreludeData as Canonical
import qualified Bootstrap.Types as T
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as S
import qualified Bootstrap.Data as D
import qualified Bootstrap.Std as L
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.Separate as U
import qualified Bootstrap.BuiltinPreludeContext as C
import qualified Bootstrap.BuiltinPreludeLiteral as Literal
import qualified Bootstrap.X.Check as Check
import qualified Bootstrap.X.Type as Ty

right :: String -> T.Either B.String a -> IO a
right label result = case result of
 T.Left message -> errorWithoutStackTrace (label ++ ": " ++ B.unpack message)
 T.Right value -> pure value
assert :: String -> Bool -> IO ()
assert label ok = unless ok (errorWithoutStackTrace label)
reject :: String -> String -> T.Either B.String a -> IO ()
reject label expected result = case result of
 T.Left message -> assert (label ++ " failed for an unrelated reason") (B.unpack message == expected)
 T.Right _ -> errorWithoutStackTrace (label ++ " was accepted")

-- The canonical literal is a committed, producer-authenticated expectation.
-- Do not generate or update it here. In addition to exact constructor equality,
-- use the ordinary full checker, not a composition-derived CheckedTerm type.
validateRaw :: C.RawPrelude -> T.Either B.String ()
validateRaw raw = do
 L.ensure (B.v_eqString (Literal.rawPrelude raw) (Literal.rawPrelude Canonical.builtin))
   "decoded builtin differs from committed canonical literal"
 actual <- Check.checkClosed (C.rawTerm raw)
 L.ensure (Ty.alphaEq actual (T.XCon "()" [])) "builtin is not a checked declaration spine"
 C.checkCompilerPrelude raw
 T.Right ()

reconstruct :: A.CrateInterface -> A.CrateObject -> T.Either B.String C.RawPrelude
reconstruct iface object = do
 A.validateInterface iface
 let byName = A.interfaceMap [iface]
 A.validateDependencies byName iface
 A.validateExportBoundary byName iface
 A.validateLayouts [iface]
 let layouts = M.fromList B.v_compareString
       [(D.datatypeName d, A.datatypePart d) | d <- A.crateLoweredData iface]
 linked <- A.linkCrate byName layouts (A.FragmentState 0 M.empty [] [] S.empty) object
 body <- foldM (\continuation declarations -> U.graft declarations continuation)
           (T.XConstructor "()" []) (A.fragmentBodies linked)
 -- Only source metadata is reused from the fixed literal. All object-owned
 -- fields, including declarations, bindings and serial, come from disk.
 -- Exact interface equality and checkCompilerPrelude revalidate that metadata.
 case Canonical.builtin of
  C.RawPrelude identity count expectedIface _ _ _ names env values protected contracts witnesses -> do
   L.ensure (B.v_eqString (Literal.interface iface) (Literal.interface expectedIface))
     "decoded builtin interface differs from committed literal"
   T.Right (C.RawPrelude identity count iface
      (T.XWithData (A.fragmentData linked) body)
      (A.fragmentBindings linked) (A.fragmentSerial linked)
      names env values protected contracts witnesses)

main :: IO ()
main = do
 args <- getArgs
 prefix <- case args of [value] -> pure value; _ -> errorWithoutStackTrace "expected one builtin prefix"
 interfaceText <- B.literal <$> readFile (prefix ++ ".mlfci")
 objectText <- B.literal <$> readFile (prefix ++ ".mlfco")
 iface <- right "read builtin interface" (A.decodeInterface interfaceText)
 object <- right "read builtin object" (A.decodeObject iface objectText)
 assert "noncanonical interface bytes" (B.v_eqString interfaceText (A.encodeInterface iface))
 assert "noncanonical object bytes" (B.v_eqString objectText (A.encodeObject object))
 raw <- right "reconstruct full builtin" (reconstruct iface object)
 right "admit full builtin" (validateRaw raw)
 -- Authored corruption probes exercise both wire readers, pairing/checksums,
 -- and fixed structural admission; no expected data is learned from output.
 reject "malformed interface" "malformed module artifact framing" (A.decodeInterface "not-an-interface")
 reject "malformed object" "malformed crate object framing" (A.decodeObject iface "not-an-object")
 interfaceFields <- right "canonical interface fields" (U.unpack interfaceText)
 assert "expected full interface field inventory" (length interfaceFields == 14)
 reject "corrupt interface checksum" "crate metadata checksum mismatch"
   (A.decodeInterface (U.pack (init interfaceFields ++ ["wrong"])))
 fields <- right "canonical object fields" (A.canonicalFields objectText)
 case fields of
  [version, identity, metadata, payload] -> do
   reject "corrupt object payload checksum" "crate object checksum mismatch"
     (A.decodeObject iface (U.pack [version, identity, metadata, payload `B.v_concatString` "x"]))
   reject "corrupt interface pairing checksum" "crate object metadata mismatch"
     (A.decodeObject iface (U.pack [version, identity, "wrong", payload]))
  _ -> errorWithoutStackTrace "expected canonical four-field object"
 case raw of
  C.RawPrelude identity count actualIface term available serial names env values protected contracts witnesses -> do
   let different = C.RawPrelude identity count actualIface
         (T.XWithData [] (T.XConstructor "()" [])) available serial names env values protected contracts witnesses
       missingExports = C.RawPrelude identity count actualIface term M.empty serial
         names env values protected contracts witnesses
   -- The alternate term is independently well-typed; its rejection must be
   -- due to fixed expected semantics, not failure to parse/typecheck anything.
   right "valid alternate term" (Check.checkClosed (C.rawTerm different))
   reject "valid but different declaration term" "decoded builtin differs from committed canonical literal" (validateRaw different)
   reject "different export inventory" "decoded builtin differs from committed canonical literal" (validateRaw missingExports)
 putStrLn "PASS current builtin: canonical literal, full check, exact wire, 7 malformed/mismatch rejections"
