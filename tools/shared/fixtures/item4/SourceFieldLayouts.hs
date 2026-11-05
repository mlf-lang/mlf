{-# LANGUAGE OverloadedStrings #-}
-- Focused host contract for the fresh-source/checked-layout boundary. This is
-- deliberately not a native, full-corpus, or compiler-publication receipt.
module Main where

import Prelude
import Control.Monad (unless, forM_, void)
import Data.IORef (newIORef, modifyIORef', readIORef)
import Data.List (isInfixOf, sort)
import System.Directory (createDirectoryIfMissing, removeFile)
import System.Environment (getArgs)
import System.IO (hSetBuffering, stdout, BufferMode(LineBuffering))
import qualified Bootstrap.Types as T
import qualified Bootstrap.Data as D
import qualified Bootstrap.Crate as C
import qualified Bootstrap.CrateArtifact as A
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.InferenceUnit as I
import qualified Bootstrap.SourceInference as SI
import qualified Bootstrap.SourceEquality as E
import qualified Bootstrap.Module as Modules
import qualified Bootstrap.Separate as U
import qualified Bootstrap.Map as M
import qualified Bootstrap.Runtime as R
import qualified Bootstrap.X.Check as Check
import qualified Bootstrap.X.Parser as XP
import qualified Bootstrap.X.Pretty as Pretty
import qualified Bootstrap.X.Syntax as X
import qualified Bootstrap.X.Type as XT
import qualified Tests.IndependentCheck as Frozen
import qualified Tests.IndependentType as FrozenType
import qualified MLF.Host.Base as B

right label result = case result of
  T.Left message -> error (label ++ ": " ++ B.unpack message)
  T.Right value -> pure value
require label condition = unless condition (error label)
rejects fragment result = case result of
  T.Left message -> fragment `isInfixOf` B.unpack message
  T.Right _ -> False
sameData a b = map D.prettyDeclaration a == map D.prettyDeclaration b
sameInventory a b = sort (map (B.unpack . D.prettyDeclaration) a) ==
  sort (map (B.unpack . D.prettyDeclaration) b)
int = T.XCon "Int" []
unit = T.XCon "()" []
intField = T.Applied "Int" []
forallInt = T.XForall (T.XTyVar 0) T.XBot int
vacantField = T.Quantified "dead" T.Star intField
entity owner spelling role = Modules.Entity owner spelling role
symbol identity owner spelling role = A.definitionName identity (entity owner spelling role)
valueScheme iface owner spelling = case lookup
  (symbol (A.crateId iface) owner spelling Modules.Value) (A.crateBindings iface) of
    Just ty -> ty
    Nothing -> error ("missing exported scheme: " ++ B.unpack spelling)
layout name declarations = case filter ((== name) . D.datatypeName) declarations of
  [declaration] -> declaration
  _ -> error ("missing or duplicate layout: " ++ B.unpack name)
fieldOf declaration = case D.datatypeConstructors declaration of
  [T.ConstructorDecl _ [field]] -> field
  _ -> error "expected a one-field constructor"
-- This is the exact target wire contract, including every Quantified node.
-- DataDeclK with only Star parameters prints as the equivalent DataDecl.
containsLayout declaration declarations =
  any ((== D.prettyDeclaration declaration) . D.prettyDeclaration) declarations
one label values = case values of
  [value] -> value
  _ -> error (label ++ ": expected exactly one value")

-- The prescribed type is independent of inference. Check the emitted target,
-- its textual reload, and erasure with both production and frozen checkers.
checkedTarget label expected term = do
  current <- right (label ++ " production") (Check.checkClosed term)
  frozen <- right (label ++ " frozen") (Frozen.checkClosed term)
  require (label ++ " prescribed type")
    (XT.alphaEq current expected && FrozenType.alphaEq frozen expected)
  restored <- right (label ++ " target parse")
    (XP.parseTerm "<source-field-layout-roundtrip>" (Pretty.prettyTerm term))
  current2 <- right (label ++ " roundtrip production") (Check.checkClosed restored)
  frozen2 <- right (label ++ " roundtrip frozen") (Frozen.checkClosed restored)
  require (label ++ " roundtrip prescribed type")
    (XT.alphaEq current2 expected && FrozenType.alphaEq frozen2 expected)
  require (label ++ " roundtrip erasure")
    (X.equalErased (X.erase term) (X.erase restored))
checkFragments label object = forM_ (A.objectFragments object) $ \fragment -> do
  let parameters = fst (U.splitParameters (U.objectBody fragment))
      expected = foldr (T.XArrow . snd) unit parameters
  checkedTarget label expected (U.objectTerm fragment)
  require (label ++ " exact header/payload layouts")
    (sameData (U.unitData (U.objectInterface fragment)) (U.objectContext fragment))

source name body = B.literal ("module " ++ name ++ " where\n" ++ body ++ "\n")
prepare base name entry body dependencyPaths = do
  let path = B.literal (base ++ "/" ++ name ++ ".emlf")
      spec = C.CrateSpec (B.literal ("item4:source-fields:" ++ name))
        (B.literal entry) T.NoImplicitPrelude [(B.literal name,path)]
        dependencyPaths (B.literal (base ++ "/cache-" ++ name))
        (B.literal (base ++ "/builtin"))
  writeFile (B.unpack path) (B.unpack (source name body))
  imported <- A.loadInterfaces dependencyPaths >>= right "load saved metadata only"
  own <- C.loadSourcesInPackage (C.specIdentity spec) (C.specSources spec)
    >>= right "load own source only"
  prepared <- right "prepare source-owned layouts" (C.prepareCrate spec imported own)
  pure (spec,imported,prepared)
compile spec imported prepared =
  C.compilePrepared spec imported prepared >>= right "compile actual crate query route"
saveReload base name object = do
  let metadata = B.literal (base ++ "/" ++ name ++ ".mlfci")
      payload = B.literal (base ++ "/" ++ name ++ ".mlfco")
  writeFile (B.unpack metadata) (B.unpack (A.encodeInterface (A.objectInterface object)))
  writeFile (B.unpack payload) (B.unpack (A.encodeObject object))
  iface <- A.readInterface metadata >>= right "reload saved crate metadata"
  restored <- A.readObject payload iface >>= right "reload saved pooled crate object"
  require "saved object bytes changed" (A.encodeObject restored == A.encodeObject object)
  pure (metadata,restored)
sourcePlan prepared = case C.preparedSourcePlan prepared of
  T.Just plan -> plan
  T.Nothing -> error "fixture unexpectedly chose whole-program fallback"
fallback prepared = case prepared of
  C.PreparedCrate r ds cs instances lowered entry reach _ ->
    C.PreparedCrate r ds cs instances lowered entry reach T.Nothing
fallbackSpec spec = case spec of
  C.CrateSpec identity entry mode sources deps cache prelude ->
    C.CrateSpec identity entry mode sources deps (B.v_concatString cache "-fallback") prelude
cold report = Q.inferredCount report > 0 && Q.reusedCount report == 0
warm report objects = Q.inferredCount report == 0 &&
  Q.reusedCount report == fromIntegral (length (A.objectFragments objects))
linkedInt label objects root = do
  term <- right (label ++ " link saved objects")
    (A.linkObjects objects (A.crateId (A.objectInterface root)))
  checkedTarget label int term
  (env,_) <- right (label ++ " runtime preparation") (R.prepare False term)
  result <- right (label ++ " erased runtime")
    (R.evaluate env (R.REnv M.empty) (X.erase term))
  require (label ++ " prescribed value") (case result of R.RInteger 42 -> True; _ -> False)


-- Legacy vacuous selector contracts are valid target ABIs, but today's source
-- entry adapter cannot reconstruct them. A library view uses the same checked
-- fragments and exact layouts, without asking that adapter to re-infer them.
libraryView object =
  let iface = case A.objectInterface object of
        A.CrateInterface identity deps modules exports reach ds cs instances lowered bindings _ digest protection ->
          A.CrateInterface identity deps modules exports reach ds cs instances lowered bindings "" digest protection
  in A.makeObject iface (A.objectFragments object)
linkedLibrary label dependencies object expectedLayouts = do
  let root = libraryView object
  term <- right (label ++ " exact library link")
    (A.linkObjects (dependencies ++ [root]) (A.crateId (A.objectInterface root)))
  checkedTarget label unit term
  let layouts = case term of T.XWithData ds _ -> ds; _ -> []
  require (label ++ " preserves expected exact layouts")
    (all (`containsLayout` layouts) expectedLayouts)

-- This artifact is constructed and independently target-checked, never passed
-- through a source datatype canonicalizer. Its old nominal field and its old
-- class dictionary intentionally contain a vacuous universal. The selector is
-- already checked, so consumers must import it rather than regenerate its ABI.
legacyCrate retainMethodQuantifier = do
  let identity = "item4:source-fields:legacy"
      owner = "Legacy"
      dataName = symbol identity owner "Legacy" Modules.Datatype
      constructorName = symbol identity owner "Legacy" (Modules.Constructor "Legacy")
      className = symbol identity owner "LegacyTag" Modules.Class
      methodName = symbol identity owner "legacyMethod" (Modules.Method "LegacyTag")
      dictionaryName = B.v_concatString "Dict_" className
      dictionaryCtor = B.v_concatString "Make_" className
      selectorName = B.v_concatString "select_" methodName
      constructorValue = symbol identity owner "legacyConstructor" Modules.Value
      storedValue = symbol identity owner "legacyValue" Modules.Value
      declaration = T.DataDecl dataName [] [T.ConstructorDecl constructorName [vacantField]]
      ordinaryMethod = T.SArrow (T.STVar "a") (T.SCon "Int" [])
      methodType = if retainMethodQuantifier
        then T.SForall T.Flexible "dead" T.SBottom ordinaryMethod else ordinaryMethod
      klass = T.SClassDecl className [("a",T.Star)] [] [(methodName,methodType)]
      ordinaryField = T.Function (T.Parameter "a") intField
      methodField = if retainMethodQuantifier
        then T.Quantified "dead" T.Star ordinaryField else ordinaryField
      dictionary = T.DataDeclK dictionaryName [("a",T.Star)]
        [T.ConstructorDecl dictionaryCtor [methodField]]
      layouts = [declaration,dictionary]
      a = T.XTyVar 10
      d = T.XName 11 "dictionary"
      f = T.XName 12 "method"
      ordinarySelectedType = T.XArrow (T.XVar a) int
      selectedType = if retainMethodQuantifier
        then T.XForall (T.XTyVar 0) T.XBot ordinarySelectedType else ordinarySelectedType
      selector = T.XTypeAbs a T.XBot
        (T.XAbs d (T.XCon dictionaryName [T.XVar a])
          (T.XCase (T.XVarTerm d) selectedType
            [T.XAlternative (T.XConstructorPattern dictionaryCtor [T.Just f]) (T.XVarTerm f)]))
      value = T.XApp (T.XConstructor constructorName [])
        (T.XTypeAbs (T.XTyVar 1) T.XBot (T.XIntTerm 42))
      body = T.XLet (T.XName 20 constructorValue) (T.XConstructor constructorName [])
        (T.XLet (T.XName 21 storedValue) value
          (T.XLet (T.XName 22 selectorName) selector (T.XConstructor "()" [])))
      term = T.XWithData layouts body
  checkedTarget "manually checked legacy payload" unit term
  dataEnv <- right "legacy layout validation" (D.validateDeclarations layouts)
  found <- right "legacy checked binding inventory"
    (U.collectBindings dataEnv (T.XEnv M.empty M.empty) body)
  let bindings = U.sortBindings [(X.nameHint name,U.normalType ty) | (name,ty) <- found]
      fragment = U.UnitObject
        (U.UnitInterface "LegacyFragment" [] [] layouts [] [] bindings
          (U.fingerprint (Pretty.prettyTerm term))) term
      exports = [entity owner "Legacy" Modules.Datatype,
        entity owner "Legacy" (Modules.Constructor "Legacy"),
        entity owner "legacyConstructor" Modules.Value,
        entity owner "legacyValue" Modules.Value,
        entity owner "LegacyTag" Modules.Class,
        entity owner "legacyMethod" (Modules.Method "LegacyTag")]
      iface = A.CrateInterface identity [] [owner] [(owner,exports)] [(owner,[])]
        [declaration] [klass] [] layouts bindings "" "pending"
        [(name,False) | (name,_) <- bindings]
      object = A.makeObject iface [fragment]
  void (right "legacy interface validation" (A.validateInterface (A.objectInterface object)))
  void (right "legacy class ABI reconstruction" (A.validateLayouts [A.objectInterface object]))
  pure (object,declaration,dictionary,klass)

-- The payload remains well typed under either layout, so these failures cannot
-- be explained by an ill-typed body, a stale checksum, or a broken wire frame.
forgeryChecks check = do
  let quantified = T.DataDecl "Forged" [] [T.ConstructorDecl "Forged" [vacantField]]
      canonical = T.DataDecl "Forged" [] [T.ConstructorDecl "Forged" [intField]]
      forged header payload =
        let term = T.XWithData [payload] (T.XConstructor "()" [])
            iface = U.UnitInterface "ForgedFragment" [] [] [header] [] [] []
              (U.fingerprint (Pretty.prettyTerm term))
        in U.UnitObject iface term
      crate header lowered fragments = A.makeObject
        (A.CrateInterface "item4:source-fields:forged" [] [] [] [] [header] [] []
          [lowered] [] "" "pending" []) fragments
  check "checked-layout key retains dead quantifiers"
    (Q.queryKey "forged" "compiler" [] [] [quantified] /=
      Q.queryKey "forged" "compiler" [] [] [canonical])
  forM_ [("quantified header / canonical payload",quantified,canonical),
         ("canonical header / quantified payload",canonical,quantified)] $ \(label,header,payload) -> do
    let object = forged header payload
        key = Q.queryKey "forged" "compiler" [] [] [header]
        artifact = crate header header [object]
        matching = forged payload payload
    checkedTarget (label ++ " valid target control") unit (U.objectTerm object)
    check (label ++ ": exact cache context rejects")
      (rejects "cached datatype context mismatch"
        (Q.validateCached "ForgedFragment" [] [header] [] object))
    check (label ++ ": encoded cache rejects")
      (rejects "cached datatype context mismatch"
        (Q.decodeCached key "ForgedFragment" [] [header] [] (Q.encodeCached key object)))
    check (label ++ ": expected cache metadata rejects opposite layout")
      (rejects "cached datatype metadata mismatch"
        (Q.validateCached "ForgedFragment" [] [header] [] matching))
    check (label ++ ": pooled object rejects")
      (rejects "duplicate crate pooled datatype"
        (A.decodeObject (A.objectInterface artifact) (A.encodeObject artifact)))
    check (label ++ ": linker rejects exact header/payload mismatch")
      (rejects "inference fragment datatype context mismatch"
        (A.linkObjects [artifact] (A.crateId (A.objectInterface artifact))))
    check (label ++ ": source/lowered metadata mismatch rejects")
      (rejects "crate lowered datatype metadata mismatch"
        (A.validateLayouts [A.objectInterface (crate header payload [])]))


-- Fresh class ownership crosses the same real crate/metadata/cache boundaries
-- as fresh datatype ownership. Do not normalize these headers in the fixture:
-- Crate.prepareCrate must transform the original parsed source before building
-- its SourcePlan, generated dictionary inventory and legacy lowering recipe.
freshSourceClassChecks check base builtinPath savedBuiltin = do
  let body = unlines
        ["class SourceTag a where { leading :: forall dead. a -> Int; nested :: a -> (forall unused. Int) }",
         "instance SourceTag Int where { leading x = x; nested x = x }",
         "answer = leading (nested 42)"]
      ordinaryMethod = T.SArrow (T.STVar "a") (T.SCon "Int" [])
      rawClass = T.SClassDecl "SourceTag" [("a",T.Star)] []
        [("leading",T.SForall T.Flexible "dead" T.SBottom ordinaryMethod),
         ("nested",T.SArrow (T.STVar "a")
           (T.SForall T.Flexible "unused" T.SBottom (T.SCon "Int" [])))]
      builtinLayouts = A.crateLoweredData (A.objectInterface savedBuiltin)
  (spec,imports,prepared) <- prepare base "ClassProducer" "" body [builtinPath]
  rawSources <- C.loadSourcesInPackage (C.specIdentity spec) (C.specSources spec)
    >>= right "reload original fresh class source"
  check "fresh source class parser retains leading and nested dead method forall"
    (case concatMap Modules.sourceClasses rawSources of
      [actual] -> E.eqSClassDecl actual rawClass
      _ -> False)
  let className = symbol (C.specIdentity spec) "ClassProducer" "SourceTag" Modules.Class
      leadingName = symbol (C.specIdentity spec) "ClassProducer" "leading" (Modules.Method "SourceTag")
      nestedName = symbol (C.specIdentity spec) "ClassProducer" "nested" (Modules.Method "SourceTag")
      dictionaryName = B.v_concatString "Dict_" className
      dictionaryCtor = B.v_concatString "Make_" className
      canonicalClass = T.SClassDecl className [("a",T.Star)] []
        [(leadingName,ordinaryMethod),(nestedName,ordinaryMethod)]
      canonicalDictionary = T.DataDeclK dictionaryName [("a",T.Star)]
        [T.ConstructorDecl dictionaryCtor
          [T.Function (T.Parameter "a") intField,T.Function (T.Parameter "a") intField]]
      exactLayouts = builtinLayouts ++ [canonicalDictionary]
      canonicalHeader headers = case headers of
        [actual] -> E.eqSClassDecl actual canonicalClass
        _ -> False
  check "fresh source class own header is canonical before planning"
    (null (C.preparedData prepared) && canonicalHeader (C.preparedClasses prepared))
  check "fresh source class plan dictionary is canonical before cache keys"
    (sameInventory (SI.planData (sourcePlan prepared)) exactLayouts)
  check "fresh source class fallback dictionary uses the same canonical contract"
    (sameInventory (I.loweredData (C.preparedLowered prepared)) exactLayouts)
  (producer,coldProducer) <- compile spec imports prepared
  (producerWarm,warmProducer) <- compile spec imports prepared
  check "fresh source class producer cold/warm artifacts are byte-identical"
    (cold coldProducer && warm warmProducer producer &&
      A.encodeObject producerWarm == A.encodeObject producer)
  let iface = A.objectInterface producer
      a = T.XTyVar 0
      selectorType = T.XForall a T.XBot
        (T.XArrow (T.XCon dictionaryName [T.XVar a]) (T.XArrow (T.XVar a) int))
      selectorAgrees method = case lookup (B.v_concatString "select_" method) (A.crateBindings iface) of
        Just ty -> XT.alphaEq ty selectorType
        Nothing -> False
  checkFragments "fresh source class producer fragments" producer
  check "fresh source class emitted header dictionary and selector schemes agree"
    (canonicalHeader (A.crateClasses iface) &&
      sameData (A.crateLoweredData iface) [canonicalDictionary] &&
      selectorAgrees leadingName && selectorAgrees nestedName &&
      XT.alphaEq (valueScheme iface "ClassProducer" "answer") int)
  (producerPath,savedProducer) <- saveReload base "ClassProducer" producer
  let savedIface = A.objectInterface savedProducer
  check "fresh source class saved producer preserves canonical ABI"
    (canonicalHeader (A.crateClasses savedIface) &&
      sameData (A.crateLoweredData savedIface) [canonicalDictionary] &&
      A.semanticFingerprint savedIface == A.semanticFingerprint iface)
  removeFile (base ++ "/ClassProducer.emlf")
  (consumerSpec,consumerImports,consumerPrepared) <- prepare base "ClassConsumer" "ClassConsumer"
    "import ClassProducer\nmain = leading (nested 42)\ncopied = answer\n" [producerPath]
  check "fresh source class metadata-only consumer retains canonical imported dictionary"
    (null (C.preparedData consumerPrepared) && null (C.preparedClasses consumerPrepared) &&
      sameInventory (SI.planData (sourcePlan consumerPrepared)) exactLayouts)
  (consumer,coldConsumer) <- compile consumerSpec consumerImports consumerPrepared
  (consumerWarm,warmConsumer) <- compile consumerSpec consumerImports consumerPrepared
  check "fresh source class consumer cold/warm artifacts are byte-identical"
    (cold coldConsumer && warm warmConsumer consumer &&
      A.encodeObject consumerWarm == A.encodeObject consumer &&
      XT.alphaEq (valueScheme (A.objectInterface consumer) "ClassConsumer" "main") int &&
      XT.alphaEq (valueScheme (A.objectInterface consumer) "ClassConsumer" "copied") int)
  (_,savedConsumer) <- saveReload base "ClassConsumer" consumer
  checkFragments "fresh source class consumer fragments" savedConsumer
  linkedInt "fresh source class saved method applications"
    [savedBuiltin,savedProducer,savedConsumer] savedConsumer
  check "fresh source class saved method applications check and evaluate to 42" True

main = do
  hSetBuffering stdout LineBuffering
  args <- getArgs
  let base = one "work directory argument" args
  createDirectoryIfMissing True base
  count <- newIORef (0 :: Int)
  let check label condition = do
        require label condition
        modifyIORef' count (+1)
        putStrLn ("PASS " ++ label)
      producerBody = unlines
        ["data V = V (forall a. Int)",
         "made = V 42", "constructor = V",
         "extract v = case v of { V n -> n }",
         "extracted = extract made"]
  builtin <- right "compile checked builtin dependency" A.builtinPrelude
  (builtinPath,savedBuiltin) <- saveReload base "Builtin" builtin
  let builtinLayouts = A.crateLoweredData (A.objectInterface savedBuiltin)
  (producerSpec,producerImports,producerPrepared) <-
    prepare base "Producer" "" producerBody [builtinPath]
  let plan = sourcePlan producerPrepared
      canonical = one "producer layout" (C.preparedData producerPrepared)
      expectedCanonical = T.DataDecl
        (symbol (C.specIdentity producerSpec) "Producer" "V" Modules.Datatype) []
        [T.ConstructorDecl
          (symbol (C.specIdentity producerSpec) "Producer" "V" (Modules.Constructor "V"))
          [intField]]
      vtype = T.XCon (D.datatypeName canonical) []
  require ("producer exact layout: expected " ++ B.unpack (D.prettyDeclaration expectedCanonical) ++
    "; actual " ++ B.unpack (D.prettyDeclaration canonical))
    (D.prettyDeclaration canonical == D.prettyDeclaration expectedCanonical)
  check "fresh producer ownData has exactly canonical Int field"
    (D.prettyDeclaration canonical == D.prettyDeclaration expectedCanonical)
  check "source plan uses identical canonical ownData"
    (sameInventory (SI.planData plan) (builtinLayouts ++ [canonical]))
  check "legacy lowering recipe uses identical canonical ownData"
    (sameInventory (I.loweredData (C.preparedLowered producerPrepared)) (builtinLayouts ++ [canonical]))
  (producer,coldProducer) <- compile producerSpec producerImports producerPrepared
  check "producer source SCC cache is cold" (cold coldProducer)
  let producerIface = A.objectInterface producer
  check "producer public and lowered layouts agree exactly"
    (sameData (A.crateData producerIface) [canonical] &&
      sameData (A.crateLoweredData producerIface) [canonical])
  check "construction, constructor-as-value and extraction have canonical contracts"
    (XT.alphaEq (valueScheme producerIface "Producer" "made") vtype &&
      XT.alphaEq (valueScheme producerIface "Producer" "constructor") (T.XArrow int vtype) &&
      XT.alphaEq (valueScheme producerIface "Producer" "extract") (T.XArrow vtype int) &&
      XT.alphaEq (valueScheme producerIface "Producer" "extracted") int)
  checkFragments "producer fragments" producer
  check "producer targets pass production/frozen/roundtrip/erasure" True
  (producerWarm,warmProducer) <- compile producerSpec producerImports producerPrepared
  check "producer warm source cache reuses every fragment" (warm warmProducer producer)
  check "producer cold/warm objects are byte-identical" (A.encodeObject producerWarm == A.encodeObject producer)
  (producerPath,savedProducer) <- saveReload base "Producer" producer
  check "saved producer preserves exact canonical layout"
    (sameData (A.crateData (A.objectInterface savedProducer)) [canonical])
  (fallbackProducer,coldFallback) <- compile (fallbackSpec producerSpec) producerImports (fallback producerPrepared)
  (fallbackWarm,warmFallback) <- compile (fallbackSpec producerSpec) producerImports (fallback producerPrepared)
  check "actual fallback query route has cold/warm reuse"
    (cold coldFallback && warm warmFallback fallbackProducer)
  check "fallback public/lowered layouts remain canonical"
    (sameData (A.crateData (A.objectInterface fallbackProducer)) [canonical] &&
      sameData (A.crateLoweredData (A.objectInterface fallbackProducer)) [canonical])
  check "fallback constructor and extraction schemes equal source SCC schemes"
    (all (\name -> XT.alphaEq (valueScheme (A.objectInterface fallbackProducer) "Producer" name)
      (valueScheme producerIface "Producer" name)) ["made","constructor","extract","extracted"])
  checkFragments "fallback producer fragments" fallbackProducer
  check "fallback targets pass production/frozen/roundtrip/erasure and warm parity"
    (A.encodeObject fallbackWarm == A.encodeObject fallbackProducer)
  removeFile (base ++ "/Producer.emlf")
  let consumerBody = "import Producer\nmain = extract (constructor 42)\ncopy = extracted\n"
  (consumerSpec,consumerImports,consumerPrepared) <-
    prepare base "Consumer" "Consumer" consumerBody [producerPath]
  check "metadata-only consumer uses unchanged imported layout"
    (null (C.preparedData consumerPrepared) &&
      containsLayout canonical (SI.planData (sourcePlan consumerPrepared)))
  (consumer,coldConsumer) <- compile consumerSpec consumerImports consumerPrepared
  (consumerWarm,warmConsumer) <- compile consumerSpec consumerImports consumerPrepared
  check "consumer source SCC cache has cold/warm reuse"
    (cold coldConsumer && warm warmConsumer consumer)
  check "consumer cold/warm bytes and imported schemes remain exact"
    (A.encodeObject consumerWarm == A.encodeObject consumer &&
      XT.alphaEq (valueScheme (A.objectInterface consumer) "Consumer" "main") int)
  (_,savedConsumer) <- saveReload base "Consumer" consumer
  linkedInt "saved producer/consumer" [savedBuiltin,savedProducer,savedConsumer] savedConsumer
  check "saved producer/consumer link, check, roundtrip and erase to 42" True
  (legacy,legacyData,legacyDictionary,legacyClass) <- legacyCrate True
  (legacyPath,savedLegacy) <- saveReload base "Legacy" legacy
  let legacyIface = A.objectInterface savedLegacy
      legacyBytes = A.encodeInterface legacyIface
      legacyFingerprint = A.semanticFingerprint legacyIface
  check "manual legacy import retains quantified constructor contract"
    (XT.alphaEq (valueScheme legacyIface "Legacy" "legacyConstructor")
      (T.XArrow forallInt (T.XCon (D.datatypeName legacyData) [])) &&
      E.eqField (fieldOf (one "legacy public datatype" (A.crateData legacyIface))) vacantField)
  check "manual legacy class signature and dictionary preserve dead quantifier"
    (map U.prettyClass (A.crateClasses legacyIface) == [U.prettyClass legacyClass] &&
      containsLayout legacyDictionary (A.crateLoweredData legacyIface))
  let mixedBody = unlines
        ["import Legacy", "data Local = Local (forall unused. Int)",
         "wrap = Local 42", "extractLocal v = case v of { Local n -> n }",
         "main = extractLocal wrap", "old = legacyValue"]
  (mixedSpec,mixedImports,mixedPrepared) <- prepare base "Mixed" "Mixed" mixedBody [legacyPath,builtinPath]
  let local = one "mixed local layout" (C.preparedData mixedPrepared)
      mixedPlan = sourcePlan mixedPrepared
      expectedLocal = T.DataDecl
        (symbol (C.specIdentity mixedSpec) "Mixed" "Local" Modules.Datatype) []
        [T.ConstructorDecl
          (symbol (C.specIdentity mixedSpec) "Mixed" "Local" (Modules.Constructor "Local"))
          [intField]]
  check "mixed source boundary normalizes only its fresh local declaration"
    (D.prettyDeclaration local == D.prettyDeclaration expectedLocal &&
      containsLayout legacyData (SI.planData mixedPlan) &&
      containsLayout legacyDictionary (SI.planData mixedPlan))
  check "mixed fallback recipe also retains exact imported dictionary and datatype"
    (containsLayout legacyData (I.loweredData (C.preparedLowered mixedPrepared)) &&
      containsLayout legacyDictionary (I.loweredData (C.preparedLowered mixedPrepared)) &&
      containsLayout local (I.loweredData (C.preparedLowered mixedPrepared)))
  (mixed,coldMixed) <- compile mixedSpec mixedImports mixedPrepared
  (mixedWarm,warmMixed) <- compile mixedSpec mixedImports mixedPrepared
  check "mixed exact-context source cache has cold/warm reuse"
    (cold coldMixed && warm warmMixed mixed && A.encodeObject mixedWarm == A.encodeObject mixed)
  check "mixed owned artifact does not re-export or rewrite imported layouts"
    (sameData (A.crateData (A.objectInterface mixed)) [local] &&
      sameData (A.crateLoweredData (A.objectInterface mixed)) [local])
  (_,savedMixed) <- saveReload base "Mixed" mixed
  let legacyEntryReason = "entry parameter type mismatch: select_" ++
        B.unpack (symbol (A.crateId legacyIface) "Legacy" "legacyMethod" (Modules.Method "LegacyTag"))
  check "legacy selector entry adaptation rejects instead of rewriting checked ABI"
    (rejects legacyEntryReason (A.linkObjects [savedBuiltin,savedLegacy,savedMixed]
      (A.crateId (A.objectInterface savedMixed))))
  linkedLibrary "legacy/local saved library" [savedBuiltin,savedLegacy] savedMixed
    [legacyData,legacyDictionary,local]
  check "legacy/local saved library links with both exact checked layouts" True
  (mixedFallback,coldMixedFallback) <- compile (fallbackSpec mixedSpec) mixedImports (fallback mixedPrepared)
  (mixedFallbackWarm,warmMixedFallback) <- compile (fallbackSpec mixedSpec) mixedImports (fallback mixedPrepared)
  check "mixed fallback query route has cold/warm reuse"
    (cold coldMixedFallback && warm warmMixedFallback mixedFallback &&
      A.encodeObject mixedFallbackWarm == A.encodeObject mixedFallback)
  require "fallback entry must not silently rewrite legacy selector ABI"
    (rejects legacyEntryReason (A.linkObjects [savedBuiltin,savedLegacy,mixedFallback]
      (A.crateId (A.objectInterface mixedFallback))))
  linkedLibrary "legacy/local fallback library" [savedBuiltin,savedLegacy] mixedFallback
    [legacyData,legacyDictionary,local]
  check "mixed fallback preserves legacy ABI through checked library linking" True
  reloadedLegacy <- A.readInterface legacyPath >>= right "reread unchanged legacy metadata"
  check "imported metadata, semantic fingerprint and class ABI remain byte-exact"
    (A.encodeInterface reloadedLegacy == legacyBytes &&
      A.semanticFingerprint reloadedLegacy == legacyFingerprint &&
      map U.prettyClass (A.crateClasses reloadedLegacy) == [U.prettyClass legacyClass])
  -- A separate positive closure differs only in the imported method's dead
  -- quantifier. The original saved legacy metadata above is never rewritten.
  (ordinary,ordinaryData,ordinaryDictionary,ordinaryClass) <- legacyCrate False
  (ordinaryPath,savedOrdinary) <- saveReload base "OrdinaryLegacy" ordinary
  (ordinarySpec,ordinaryImports,ordinaryPrepared) <- prepare base "OrdinaryConsumer"
    "OrdinaryConsumer" "import Legacy\nmain = 42\nold = legacyValue\n" [ordinaryPath,builtinPath]
  (ordinaryConsumer,ordinaryCold) <- compile ordinarySpec ordinaryImports ordinaryPrepared
  (_,savedOrdinaryConsumer) <- saveReload base "OrdinaryConsumer" ordinaryConsumer
  linkedInt "ordinary imported-selector entry"
    [savedBuiltin,savedOrdinary,savedOrdinaryConsumer] savedOrdinaryConsumer
  check "ordinary imported-selector entry adaptation succeeds with exact checked ABI"
    (cold ordinaryCold && containsLayout ordinaryData (SI.planData (sourcePlan ordinaryPrepared)) &&
      containsLayout ordinaryDictionary (SI.planData (sourcePlan ordinaryPrepared)) &&
      map U.prettyClass (A.crateClasses (A.objectInterface savedOrdinary)) == [U.prettyClass ordinaryClass])
  let invalid = T.DataDecl "Invalid" [] [T.ConstructorDecl "Invalid"
        [T.Quantified "unused" T.Star (T.Applied "Int" [intField])]]
  check "fresh-source canonicalizer validates original ill-kinded fields"
    (case D.canonicalSourceDeclarations [] [invalid] of T.Left _ -> True; _ -> False)
  check "fresh-source canonicalizer validates original checked context"
    (case D.canonicalSourceDeclarations [invalid] [local] of T.Left _ -> True; _ -> False)
  forgeryChecks check
  freshSourceClassChecks check base builtinPath savedBuiltin
  total <- readIORef count
  require "source field-layout fixture check inventory changed" (total == 55)
  putStrLn "item4 source field layouts: passed (55 checks; source/fallback, saved imports, cold/warm, exact legacy ABI, bidirectional forgery rejection, fresh source classes)"
