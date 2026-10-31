{-# LANGUAGE OverloadedStrings #-}
-- Host-only mutation controls for canonical source witnesses and prepared
-- metadata. A fresh ordinary preparation is required to pass before mutation.
module Main where

import Prelude hiding (Either(..), Maybe(..))
import Bootstrap.Types
import qualified Bootstrap.BuiltinPreludeContext as Context
import qualified Bootstrap.CrateArtifact as Artifact
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as S
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.SourceEquality as Equality
import qualified Bootstrap.SourceInference as Source
import qualified MLF.Primitive as P
import qualified System.IO as IO
import System.Exit (exitFailure)

data Fields = Fields
  { sourceIdentity :: P.String
  , primitiveCount :: P.Int
  , crateInterface :: Artifact.CrateInterface
  , closedTerm :: XTerm
  , available :: Map P.String (XName, XType)
  , nextSerial :: P.Int
  , sourceNames :: Modules.Names
  , sourceEnvironment :: Modules.Interface
  , sourceValues :: Set P.String
  , protectedNames :: Set P.String
  , sourceContracts :: Map P.String Source.SourceContract
  , sourceWitnesses :: [SourceModule]
  }

unpack :: Context.RawPrelude -> Fields
unpack (Context.RawPrelude identity count iface term bindings serial names environment values protected contracts witnesses) =
  Fields identity count iface term bindings serial names environment values protected contracts witnesses

pack :: Fields -> Context.RawPrelude
pack f = Context.RawPrelude (sourceIdentity f) (primitiveCount f) (crateInterface f) (closedTerm f)
  (available f) (nextSerial f) (sourceNames f) (sourceEnvironment f) (sourceValues f)
  (protectedNames f) (sourceContracts f) (sourceWitnesses f)

failControl :: String -> String -> IO a
failControl label message = IO.hPutStrLn IO.stderr ("FAIL " ++ label ++ ": " ++ message) >> exitFailure

pass :: String -> IO ()
pass label = putStrLn ("PASS " ++ label)

reject :: Fields -> (String, Fields -> Fields, P.String) -> IO ()
reject baseline (label, change, expected) =
  case Context.checkCompilerPrelude (pack (change baseline)) of
    Left actual | P.eqString actual expected -> pass label
    Left actual -> failControl label ("wrong diagnostic: " ++ P.textToChars actual)
    Right _ -> failControl label "altered compiler context was accepted"

firstValue :: (a -> a) -> Map P.String a -> Map P.String a
firstValue change values = case M.toList values of
  [] -> error "control setup requires a nonempty map"
  (key, value) : _ -> M.insert P.compareString key (change value) values

mapSize :: Map a b -> Map a b
mapSize values = case values of
  MapEmpty -> error "control setup requires a nonempty map node"
  MapNode size key value left right -> MapNode (size + 1) key value left right

setSize :: Set a -> Set a
setSize (Set values) = Set (mapSize values)

changePrimitiveWitness :: (SourceModule -> SourceModule) -> [SourceModule] -> [SourceModule]
changePrimitiveWitness change modules = case modules of
  [prelude, primitive] -> [prelude, change primitive]
  _ -> error "control setup requires exactly Prelude and MLF.Primitive witnesses"

withWitness :: (SourceModule -> SourceModule) -> Fields -> Fields
withWitness change f = f { sourceWitnesses = changePrimitiveWitness change (sourceWitnesses f) }

changeBody :: SourceModule -> SourceModule
changeBody (SourceModule path name exports imports datatypes classes instances values body syntax) =
  case values of
    [] -> error "canonical primitive witness must contain a source binding"
    (n, annotation, _) : rest -> SourceModule path name exports imports datatypes classes instances
      ((n, annotation, SIntLit 736274) : rest) body syntax

changeClass :: SourceModule -> SourceModule
changeClass (SourceModule path name exports imports datatypes classes instances values body syntax) =
  case classes of
    [] -> error "canonical primitive witness must contain a class"
    SClassDecl n parameters parents methods : rest ->
      SourceModule path name exports imports datatypes
        (SClassDecl n parameters parents (("staleMethod", SCon "Int" []) : methods) : rest)
        instances values body syntax

changeInstance :: SourceModule -> SourceModule
changeInstance (SourceModule path name exports imports datatypes classes instances values body syntax) =
  case instances of
    [] -> error "canonical primitive witness must contain an instance"
    SInstanceDecl variables predicates n arguments methods : rest ->
      SourceModule path name exports imports datatypes classes
        (SInstanceDecl variables predicates n arguments (("staleMethod", SIntLit 8) : methods) : rest)
        values body syntax

withSpan :: SourceSpan -> SourceModule -> SourceModule
withSpan span (SourceModule path name exports imports datatypes classes instances values body syntax) =
  SourceModule path name exports imports datatypes classes instances values
    (Just (SCallSite "witnessSpan" span (SIntLit 1))) syntax

changeSyntax :: SourceModule -> SourceModule
changeSyntax (SourceModule path name exports imports datatypes classes instances values body syntax) =
  let changed = case syntax of SharedHaskellV1 -> MetadataSyntax; _ -> SharedHaskellV1
  in SourceModule path name exports imports datatypes classes instances values body changed

changePath :: SourceModule -> SourceModule
changePath (SourceModule path name exports imports datatypes classes instances values body syntax) =
  SourceModule (path P.++ ".stale") name exports imports datatypes classes instances values body syntax

changeModuleName :: SourceModule -> SourceModule
changeModuleName (SourceModule path _ exports imports datatypes classes instances values body syntax) =
  SourceModule path (Just "Stale.Primitive") exports imports datatypes classes instances values body syntax

changeExports :: SourceModule -> SourceModule
changeExports (SourceModule path name _ imports datatypes classes instances values body syntax) =
  SourceModule path name (Just [ExportValue "staleExport"]) imports datatypes classes instances values body syntax

changeImports :: SourceModule -> SourceModule
changeImports (SourceModule path name exports imports datatypes classes instances values body syntax) =
  SourceModule path name exports (Import "Stale.Dependency" True (Just "Stale") (Only []) : imports)
    datatypes classes instances values body syntax

changeData :: SourceModule -> SourceModule
changeData (SourceModule path name exports imports datatypes classes instances values body syntax) =
  SourceModule path name exports imports (DataDecl "StaleData" [] [] : datatypes) classes instances values body syntax

changeNames :: Modules.Names -> Modules.Names
changeNames (Modules.Names names) = case M.toList names of
  [] -> error "canonical names must be nonempty"
  (entity, value) : _ -> Modules.Names (M.insert Modules.compareEntity entity (value P.++ "_stale") names)

changeNamesSize :: Modules.Names -> Modules.Names
changeNamesSize (Modules.Names names) = Modules.Names (mapSize names)

changeEnvironmentSize :: Modules.Interface -> Modules.Interface
changeEnvironmentSize (Modules.Interface environment) = Modules.Interface (mapSize environment)

changeEnvironmentSetSize :: Modules.Interface -> Modules.Interface
changeEnvironmentSetSize (Modules.Interface environment) = case environment of
  MapEmpty -> error "canonical environment must be nonempty"
  MapNode size key value left right -> Modules.Interface (MapNode size key (setSize value) left right)

checkSpanFields :: [SourceModule] -> IO ()
checkSpanFields witnesses = case witnesses of
  [_, canonical] -> do
    let base = SourceSpan "package" "module" "file" 1 2 3 4
        reference = withSpan base canonical
        alternatives =
          [ ("span-package", SourceSpan "other" "module" "file" 1 2 3 4)
          , ("span-module", SourceSpan "package" "other" "file" 1 2 3 4)
          , ("span-file", SourceSpan "package" "module" "other" 1 2 3 4)
          , ("span-start-line", SourceSpan "package" "module" "file" 9 2 3 4)
          , ("span-start-column", SourceSpan "package" "module" "file" 1 9 3 4)
          , ("span-end-line", SourceSpan "package" "module" "file" 1 2 9 4)
          , ("span-end-column", SourceSpan "package" "module" "file" 1 2 3 9)
          ]
    if Equality.eqSourceModule reference (withSpan base canonical)
      then pass "source-witness-equality-positive"
      else failControl "source-witness-equality-positive" "identical source modules compare unequal"
    mapM_ (\(label, changed) ->
      if Equality.eqSourceModule reference (withSpan changed canonical)
        then failControl label "source-module equality ignored a span field"
        else pass label) alternatives
  _ -> failControl "span-fixture" "canonical witness inventory changed"

main :: IO ()
main = case Context.prepareFresh "context-mutation-controls" of
  Left message -> failControl "fresh-preparation" (P.textToChars message)
  Right raw -> do
    case Context.checkCompilerPrelude raw of
      Left message -> failControl "fresh-admission" (P.textToChars message)
      Right _ -> pass "fresh-admission"
    let base = unpack raw
        witnessError = "prepared Prelude canonical source witness is stale"
        namesError = "prepared Prelude source names are inconsistent"
        environmentError = "prepared Prelude source environment is inconsistent"
        valuesError = "prepared Prelude source value inventory is inconsistent"
        protectedError = "prepared Prelude protected inventory is inconsistent"
        contractsError = "prepared Prelude source contracts are inconsistent"
        controls =
          [ ("empty-source-witness", \f -> f { sourceWitnesses = [] }, witnessError)
          , ("reordered-source-witnesses", \f -> f { sourceWitnesses = reverse (sourceWitnesses f) }, witnessError)
          , ("duplicated-source-witnesses", \f -> f { sourceWitnesses = sourceWitnesses f ++ sourceWitnesses f }, witnessError)
          , ("changed-source-binding-body", withWitness changeBody, witnessError)
          , ("changed-source-class", withWitness changeClass, witnessError)
          , ("changed-source-instance", withWitness changeInstance, witnessError)
          , ("injected-source-span", withWitness (withSpan (SourceSpan "stale" "module" "file" 1 1 1 2)), witnessError)
          , ("changed-source-syntax", withWitness changeSyntax, witnessError)
          , ("changed-source-path", withWitness changePath, witnessError)
          , ("changed-source-module-name", withWitness changeModuleName, witnessError)
          , ("changed-source-exports", withWitness changeExports, witnessError)
          , ("changed-source-imports", withWitness changeImports, witnessError)
          , ("changed-source-datatypes", withWitness changeData, witnessError)
          , ("changed-source-name", \f -> f { sourceNames = changeNames (sourceNames f) }, namesError)
          , ("changed-source-name-map-size", \f -> f { sourceNames = changeNamesSize (sourceNames f) }, namesError)
          , ("missing-source-environment", \f -> f { sourceEnvironment = Modules.Interface M.empty }, environmentError)
          , ("changed-source-environment-map-size", \f -> f { sourceEnvironment = changeEnvironmentSize (sourceEnvironment f) }, environmentError)
          , ("changed-source-environment-set-size", \f -> f { sourceEnvironment = changeEnvironmentSetSize (sourceEnvironment f) }, environmentError)
          , ("missing-source-values", \f -> f { sourceValues = S.empty }, valuesError)
          , ("changed-source-values-set-size", \f -> f { sourceValues = setSize (sourceValues f) }, valuesError)
          , ("missing-protected-names", \f -> f { protectedNames = S.empty }, protectedError)
          , ("changed-protected-set-size", \f -> f { protectedNames = setSize (protectedNames f) }, protectedError)
          , ("missing-source-contracts", \f -> f { sourceContracts = M.empty }, contractsError)
          , ("changed-contract-map-size", \f -> f { sourceContracts = mapSize (sourceContracts f) }, contractsError)
          , ("changed-contract-type", \f -> f { sourceContracts = firstValue
              (\(Source.SourceContract ty classes protected) -> Source.SourceContract (XArrow ty ty) classes protected)
              (sourceContracts f) }, contractsError)
          , ("changed-contract-class-list", \f -> f { sourceContracts = firstValue
              (\(Source.SourceContract ty classes protected) -> Source.SourceContract ty ("StaleClass" : classes) protected)
              (sourceContracts f) }, contractsError)
          , ("changed-contract-protection", \f -> f { sourceContracts = firstValue
              (\(Source.SourceContract ty classes protected) -> Source.SourceContract ty classes (not protected))
              (sourceContracts f) }, contractsError)
          , ("missing-source-identity", \f -> f { sourceIdentity = "" }, "prepared Prelude lacks a source identity")
          , ("stale-primitive-count", \f -> f { primitiveCount = primitiveCount f + 1 }, "prepared Prelude primitive ABI is stale")
          , ("overlapping-fresh-serial", \f -> f { nextSerial = 0 }, "prepared Prelude fresh serial overlaps its checked term")
          ]
    mapM_ (reject base) controls
    checkSpanFields (sourceWitnesses base)
    putStrLn ("PASS all " ++ show (length controls + 9) ++ " builtin context controls")
