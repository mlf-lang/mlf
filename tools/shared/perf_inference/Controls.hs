{-# LANGUAGE OverloadedStrings #-}
module Main where
import MLF.Host.IO (runEntry)
import qualified MLF.Tests.SharedFrontend as S
import qualified MLF.Tests.ClassDemand as Q
main = runEntry $ do
  S.recursiveRight "planner exact controls" Q.checkAll
  S.qualifiedRecursiveChecks
  S.frontendRepairProvenanceChecks
  S.frontendRepairParameterFieldChecks
  S.frontendRepairSourceFieldChecks
  S.frontendRepairSourceClassChecks
  putStrLn "PASS targeted planner, recursive classes, provenance, capture/skolem, raw/canonical controls"
