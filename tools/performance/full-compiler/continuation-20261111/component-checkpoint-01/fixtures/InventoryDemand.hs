{-# LANGUAGE OverloadedStrings #-}
-- Compile only in separately admitted controls. No private CheckedTerm constructor.
module Main where
import Control.Monad (unless)
import qualified Bootstrap.Types as T
import qualified Bootstrap.X.Checked as K
import qualified Bootstrap.X.Check as C
import qualified Bootstrap.X.Type as Y
import qualified Bootstrap.OpenFragment as O
import qualified MLF.Host.Base as B
expectRight label value = case value of
  T.Right x -> pure x
  T.Left message -> fail (label ++ ": " ++ B.unpack message)
expectLeft label message value = case value of
  T.Left actual -> unless (B.v_eqString actual message) (fail (label ++ ": wrong rejection"))
  T.Right _ -> fail (label ++ ": accepted")
main = do
  checked <- expectRight "closed-type-success" (K.check (T.XIntTerm 42))
  unless (Y.alphaEq (K.typeOf checked) (T.XCon "Int" [])) (fail "closed type")
  expectLeft "independent-deferred-inventory" "invalid inference fragment: expected declarations ending in ()"
    (K.declarationBindings checked)
  let independent = (K.typeOf checked, C.closedBindingInventory [] (error "no-demand bottom"))
  unless (Y.alphaEq (fst independent) (T.XCon "Int" [])) (fail "inventory demanded")
  env <- expectRight "open-environment" (O.environment [])
  expectLeft "open-owned-inventory" "invalid inference fragment: expected declarations ending in ()"
    (O.check env [] (T.XIntTerm 42))
  expectLeft "open-invalid-export-type" "unbound type variable 99"
    (O.check env [] (T.XLetRec [(T.XName 1 "bad", T.XVar (T.XTyVar 99), T.XIntTerm 42)] (T.XConstructor "()" [])))
  putStrLn "PASS inventory-demand"
