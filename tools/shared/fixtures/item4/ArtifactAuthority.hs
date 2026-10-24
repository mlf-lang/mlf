{-# LANGUAGE OverloadedStrings #-}
module Main where
import Prelude
import Data.List (isInfixOf)
import qualified Bootstrap.Types as T
import qualified Bootstrap.Std as S
import qualified Bootstrap.Map as M
import qualified Bootstrap.Set as Set
import qualified Bootstrap.Parser as P
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.Data as D
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.Separate as U
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as Prim

list = foldr (:) []
toList [] = []
toList ((:) x xs) = x : toList xs
check name ok = if ok then putStrLn ("PASS " ++ name) else error name
expect label result = case result of
  T.Left err -> error (label ++ ": " ++ B.unpack err)
  T.Right x -> pure x
prologue = "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\n"
resolve name text = do
  source <- expect "parse source authority fixture" (P.parseModule (B.literal (name ++ ".hs")) (B.literal (prologue ++ text)))
  crate <- expect "resolve source authority fixture" (Modules.resolveCrate T.NoImplicitPrelude M.empty (A.definitionName "authority") (list [source]))
  case filter (\r -> B.unpack (Modules.moduleIdentity (Modules.resolvedSource r)) == name) (toList (Modules.resolvedCrateModules crate)) of
    [resolved] -> pure resolved
    _ -> error "missing uniquely resolved module"
emptyIface ds = A.CrateInterface "forged" [] [] [] [] ds [] [] ds [] "" "object" []
main = do
  let malformedCons = Modules.Entity "Prelude" ":" (Modules.Constructor "Wrong")
      genuineCons = Modules.Entity "Prelude" ":" (Modules.Constructor "[]")
  check "canonical constructor identity includes its exact datatype parent" $
    Prim.eqString (U.stableName genuineCons) ":" &&
    Prim.eqString (A.definitionName "authority" genuineCons) ":" &&
    not (Prim.eqString (U.stableName malformedCons) ":") &&
    not (Prim.eqString (A.definitionName "authority" malformedCons) ":")
  ordinary <- resolve "User" "module User where\nimport MLF.Primitive hiding (HasCallStack)\nclass HasCallStack a where { witness :: a -> Int }\n"
  check "ordinary same-spelling class cannot become managed constraint" $ case Modules.renamedClasses (Modules.resolvedContents ordinary) of
    (:) (T.SClassDecl name _ _ _) [] -> not (Prim.eqString name "MLFHasCallStack")
    _ -> False
  private <- resolve "User" "module User (MLFStackEvidence(..)) where\nimport MLF.Primitive\ndata MLFStackEvidence = MLFStackEvidence Int\n"
  let ds = Modules.renamedDatatypes (Modules.resolvedContents private)
  check "same-spelling private type and constructor remain user-owned" $ case ds of
    (:) d [] -> not (Prim.eqString (D.datatypeName d) "MLFStackEvidence") &&
      S.all (\c -> not (Prim.eqString (D.constructorName c) "MLFStackEvidence")) (D.datatypeConstructors d)
    _ -> False
  env <- expect "validate distinct user declaration with intrinsic registry" (D.validateDeclarations ds)
  intrinsic <- expect "retrieve authentic private declaration" (D.lookupDatatype env "MLFStackEvidence")
  check "user declaration does not overwrite private evidence layout" $
    Prim.eqString (D.prettyDeclaration intrinsic) (D.prettyDeclaration D.stackEvidenceDeclaration)
  exported <- expect "resolve user private-name exports" (Modules.resolvedExports T.NoImplicitPrelude private)
  check "user private-name exports cannot claim intrinsic ownership" $
    S.all (\e -> not (A.isPrimitiveEntity e) && not (Prim.eqString (A.definitionName "authority" e) "MLFStackEvidence")) (Set.toList (Modules.visible exported))
  check "forged canonical evidence layout rejected at linker authority boundary" $ case A.validateLayouts (list [emptyIface (list [D.stackEvidenceDeclaration])]) of
    T.Left _ -> True
    _ -> False
  check "forged canonical frame layout rejected at linker authority boundary" $ case A.validateLayouts (list [emptyIface (list [D.stackFrameDeclaration])]) of
    T.Left _ -> True
    _ -> False
  let fakeClass = T.SClassDecl "MLFHasCallStack" (list [(,) "a" T.Star]) [] []
      fakeClassIface = A.CrateInterface "fake-class" [] [] [] [] [] (list [fakeClass]) [] [] [] "" "object" []
  check "ordinary class metadata cannot claim compiler-managed predicate" $ case A.validateLayouts (list [fakeClassIface]) of
    T.Left message -> "compiler-managed constraint, not a class" `isInfixOf` B.unpack message
    _ -> False
  let privateExports = list [Modules.Entity "MLF.Primitive" "MLFStackEvidence" Modules.BuiltinType,
                            Modules.Entity "MLF.Primitive" "MLFStackEvidence" (Modules.Constructor "MLFStackEvidence")]
      forgedExports = A.CrateInterface "forged-exports" [] (list ["User"])
        (list [(,) "User" privateExports]) (list [(,) "User" []])
        [] [] [] [] [] "" "object" []
  check "private intrinsic type and constructor exports require real ownership" $ case A.validateExportBoundary M.empty forgedExports of
    T.Left message -> "outside its dependency boundary" `isInfixOf` B.unpack message
    _ -> False
  check "source cannot claim builtin module ownership" $ case P.parseModule "Forge.hs"
    (B.literal (prologue ++ "module MLF.Primitive where\nvalue = 1\n")) of
      T.Left message -> "MLF.Primitive is a reserved native builtin module" `isInfixOf` B.unpack message
      T.Right forgedModule -> case Modules.resolveCrate T.NoImplicitPrelude M.empty (A.definitionName "forged") (list [forgedModule]) of
        T.Left message -> "built-in modules and cannot be redefined" `isInfixOf` B.unpack message
        _ -> False
  facade <- resolve "Facade" "module Facade (Stack.HasCallStack) where\nimport qualified MLF.Primitive as Stack (HasCallStack)\n"
  exposed <- expect "resolve managed reexport alias" (Modules.resolvedExports T.NoImplicitPrelude facade)
  let entities = Set.toList (Modules.visible exposed)
      managed = Modules.Entity "MLF.Primitive" "HasCallStack" Modules.ManagedConstraint
      facadeIface = A.CrateInterface "facade" [] (list ["Facade"])
        (list [(,) "Facade" entities]) (list [(,) "Facade" (list ["MLF.Primitive"])])
        [] [] [] [] [] "" "object" []
  check "qualified import reexport retains exact managed identity" $
    S.eqList (\a b -> Modules.compareEntity a b == 0) entities (list [managed])
  _ <- expect "managed reexport interface authority" (A.validateInterface facadeIface)
  _ <- expect "managed reexport dependency authority" (A.validateExportBoundary M.empty facadeIface)
  _ <- expect "managed reexport metadata roundtrip" (A.decodeInterface (A.encodeInterface facadeIface))
  let identity = "hidden"
      entity n role = Modules.Entity "Provider" n role
      typeEntity = entity "T" Modules.Datatype
      onlyEntity = entity "Only" (Modules.Constructor "T")
      otherEntity = entity "Other" (Modules.Constructor "T")
      ty = A.definitionName identity typeEntity
      only = A.definitionName identity onlyEntity
      other = A.definitionName identity otherEntity
      family = T.DataDecl ty [] (list [T.ConstructorDecl only [], T.ConstructorDecl other []])
      visible = list [typeEntity, onlyEntity]
      hiddenIface = A.CrateInterface identity [] (list ["Provider"])
        (list [(,) "Provider" visible]) (list [(,) "Provider" []])
        (list [family]) [] [] (list [family]) [] "" "object" []
  restored <- expect "decode restricted-constructor interface" (A.decodeInterface (A.encodeInterface hiddenIface))
  _ <- expect "validate complete hidden-constructor layout" (A.validateLayouts (list [restored]))
  check "hidden constructors survive interface refutability inventory" $ case A.crateData restored of
    (:) d [] -> S.eqList Prim.eqString (S.map D.constructorName (D.datatypeConstructors d)) (list [only,other])
    _ -> False
  check "hidden constructor remains absent from source export inventory" $
    not (S.any (\e -> Modules.compareEntity e otherEntity == 0) (S.concatMap S.snd (A.crateExports restored)))
  check "removing hidden family member changes inference key" $ not $ Prim.eqString
    (Q.queryKey identity "compiler" [] [] (A.crateData restored))
    (Q.queryKey identity "compiler" [] [] (list [T.DataDecl ty [] (list [T.ConstructorDecl only []])]))
  putStrLn "item4 artifact authority and hidden-family contracts: passed"
