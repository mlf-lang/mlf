-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.PreparedLibraries
  (LibrarySource(..), LibraryObject(..), RawLibrary(..), Compilation,
   librarySchema, prepareFresh, inputIdentity, librarySources, libraryObjects,
   sourceName, sourcePath, sourceText, sourceHash, sourceSyntax,
   metadataHash, objectHash, libraryObject, compileLoaded, checkedTerm,
   sourceType, reused, nameMap, NativeRoot, nativeCheckedWrapper, nativeSignatures,
   nativeSourceType, nativeInferredType, nativeDeclarations, nativeBuiltinCount, compileNativeRoot, compileNativeRootUsing,
   nativeLibrary, nativeLibraryDeclarations, nativeExportSignatures) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Lexer as Lexer;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Primitive as Primitive;
  import qualified Bootstrap.Compiler as Compiler;
  import qualified Bootstrap.CompilerCore as Core;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.SourceEquality as SourceEquality;
  import qualified Bootstrap.ImportParameters as Parameters;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.ImportedRoot as Imported;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Type as T;

  -- These constructors are compiler-owned generated data, never a cache wire
  -- format. The build pins the source and artifact SHA256s and regenerates the
  -- literal independently. A running compiler compares the exact parser read
  -- to sourceText, then independently admits every checked implementation.
  -- SHA field formatting alone authenticates no arbitrary RawLibrary: only the
  -- compiler's generated literal registry reaches the normal entry adapter.
  -- There is deliberately no external raw-registry/cache loader here.
  -- Package provenance is deliberately fixed to Parser.parseModule's "main";
  -- lexical paths are exact. Target string literals are never relocated.
  data LibrarySource = LibrarySource String String String String SourceSyntax;
  sourceName (LibrarySource value _ _ _ _) = value;
  sourcePath (LibrarySource _ value _ _ _) = value;
  sourceText (LibrarySource _ _ value _ _) = value;
  sourceHash (LibrarySource _ _ _ value _) = value;
  sourceSyntax (LibrarySource _ _ _ _ value) = value;
  data LibraryObject = LibraryObject String String Artifact.CrateObject;
  metadataHash (LibraryObject value _ _) = value;
  objectHash (LibraryObject _ value _) = value;
  libraryObject (LibraryObject _ _ value) = value;
  data RawLibrary = RawLibrary String String PreludeMode ([] LibrarySource) ([] LibraryObject) ([] SourceModule);
  inputIdentity (RawLibrary value _ _ _ _ _) = value;
  librarySources (RawLibrary _ _ _ value _ _) = value;
  libraryObjects (RawLibrary _ _ _ _ value _) = value;
  libraryMode (RawLibrary _ _ value _ _ _) = value;
  librarySchema = "mlf-prepared-libraries/1/" ++ Lexer.frontendSemanticVersion ++ "/" ++
    Lexer.builtinInterfaceVersion ++ "/" ++ showInt (length Primitive.allPrimitives);
  data Compilation = Compilation Checked.CheckedTerm String Bool Modules.Names;
  checkedTerm (Compilation value _ _ _) = value;
  sourceType (Compilation _ value _ _) = value;
  reused (Compilation _ _ value _) = value;
  nameMap (Compilation _ _ _ (Modules.Names value)) = value;
  sameMode left right = case (,) left right of {
    (,) ImplicitPrelude ImplicitPrelude -> True;
    (,) NoImplicitPrelude NoImplicitPrelude -> True;
    _ -> False
  };
  sameSyntax left right = eqString (Lexer.sourceSyntaxName left) (Lexer.sourceSyntaxName right);
  digest value = stringLength value == 64 && all (\index -> let {
    code = stringCodeAt value index
  } in (code >= 48 && code <= 57) || (code >= 97 && code <= 102)) (range 0 63);
  interfaces raw = map (compose Artifact.objectInterface libraryObject) (libraryObjects raw);
  owners raw = M.fromList compareString (concatMap (\iface ->
    map (\name -> (,) name (Artifact.crateId iface)) (Artifact.crateModules iface)) (interfaces raw));
  rawProtected raw = S.fromList compareString (concatMap (\iface ->
    append (map fst (Artifact.crateBindings iface))
      (append (map fst (Artifact.crateInstances iface))
        (append (concatMap (\d -> (:) (D.datatypeName d) (map D.constructorName (D.datatypeConstructors d)))
          (append (Artifact.crateData iface) (Artifact.crateLoweredData iface)))
          (append (map Modules.className (Artifact.crateClasses iface))
            (concatMap (\klass -> map fst (Modules.classMethods klass)) (Artifact.crateClasses iface))))))
    (interfaces raw));
  validateRegistry raw@(RawLibrary identity schema _ sources objects witnesses) = do {
    ensure (digest identity && eqString schema librarySchema) "prepared library build identity is stale";
    ensure (eqList SourceEquality.eqSourceModule witnesses [Modules.preludeSource, Modules.primitiveSource])
      "prepared library canonical builtin source witness is stale";
    ensure (not (null sources) && not (null objects)) "prepared library inventory is empty";
    Artifact.uniqueNames "prepared library source" (map sourceName sources);
    Artifact.uniqueNames "prepared library source path" (map sourcePath sources);
    Artifact.uniqueNames "prepared library crate" (map Artifact.crateId (interfaces raw));
    Artifact.uniqueNames "prepared library module owner" (concatMap Artifact.crateModules (interfaces raw));
    traverseEither (\source -> ensure (digest (sourceHash source))
      "prepared library source lacks a SHA256 commitment") sources;
    traverseEither (\object -> ensure (digest (metadataHash object) && digest (objectHash object))
      "prepared library object lacks a SHA256 commitment") objects;
    ensure (eqList eqString (sortBy compareString (map sourceName sources))
      (sortBy compareString (filter (\name -> not (Modules.isBuiltinModule name))
        (concatMap Artifact.crateModules (interfaces raw)))))
      "prepared library source/object module inventory mismatch";
    ensure (length (filter (\iface -> eqString (Artifact.crateId iface) Artifact.builtinCrateIdentity)
      (interfaces raw)) == 1) "prepared library lacks its exact builtin dependency";
    traverseEither (\iface -> ensure (eqString (Artifact.crateEntry iface) "")
      "prepared library object contains a user entry") (interfaces raw)
  };
  -- Runtime admission uses the same fragment checker, dependency boundary and
  -- capture-free freshening as ordinary .mlfco linking. SHA fields authenticate
  -- the fixed build artifact; they do not replace independent target checking.
  data CheckedLibrary = CheckedLibrary Artifact.FragmentState (Either String Checked.LinkedSpine);
  libraryState (CheckedLibrary state _) = state;
  librarySpine (CheckedLibrary _ proof) = proof;
  checkedLibraryV1 raw = do {
    validateRegistry raw;
    let { ifaces = interfaces raw; byName = Artifact.interfaceMap ifaces;
          -- The installed native literal ABI still consumes closed CheckedTerm
          -- spines. Conversion is confined to this legacy prepared-library ABI;
          -- ordinary open-object loading/linking uses explicit environments.
          objects = M.fromList compareString (map (\entry -> let { object = Artifact.legacyObject (libraryObject entry) }
            in (,) (Artifact.crateId (Artifact.objectInterface object)) object) (libraryObjects raw)) };
    ordered <- Artifact.dependencyClosure byName [] [] (map Artifact.crateId ifaces);
    traverseEither (Artifact.validateDependencies byName) ordered;
    traverseEither (Artifact.validateExportBoundary byName) ordered;
    Artifact.validateLayouts ordered;
    let { layouts = M.fromList compareString (map (\d ->
      (,) (D.datatypeName d) (Artifact.datatypePart d)) (concatMap Artifact.crateLoweredData ordered)) };
    linked <- foldEither (\state iface -> case M.lookup compareString (Artifact.crateId iface) objects of {
      Nothing -> Left "prepared library object disappeared";
      Just object -> Artifact.linkCrateWithSpine byName layouts state object
    }) ((,) (Artifact.FragmentState 0 M.empty [] [] S.empty) (Right Checked.emptySpine)) ordered;
    Right (CheckedLibrary (fst linked) (snd linked))
  };
  prepareFresh identity mode sources objects = do {
    let { raw = RawLibrary identity librarySchema mode sources objects [Modules.preludeSource, Modules.primitiveSource] };
    checkedLibrary raw;
    Right raw
  };
  sourceMatches entries recorded = case find (\entry ->
    eqString (Modules.moduleIdentity (Modules.loadedSource entry)) (sourceName recorded)) entries of {
    Nothing -> False;
    Just entry -> let { source = Modules.loadedSource entry } in
      eqString (Modules.sourcePath source) (sourcePath recorded) &&
      eqString (Modules.loadedText entry) (sourceText recorded) &&
      sameSyntax (Modules.sourceSyntax source) (sourceSyntax recorded) &&
      not (isJust (Modules.sourceBody source))
  };
  matches mode entries raw = if null entries then False else let {
    selected = map sourceName (librarySources raw);
    rootName = Modules.moduleIdentity (Modules.loadedSource (last entries));
    dependencies source = all (\entry -> Modules.isBuiltinModule (Modules.importedModule entry) ||
      elem eqString (Modules.importedModule entry) selected) (Modules.sourceImports source)
  } in sameMode mode (libraryMode raw) && not (elem eqString rootName selected) &&
    all (sourceMatches entries) (librarySources raw) &&
    all (\entry -> not (elem eqString (Modules.moduleIdentity (Modules.loadedSource entry)) selected) ||
      dependencies (Modules.loadedSource entry)) entries;
  mixedNames raw modules entities = let {
    ownership = owners raw;
    used = S.union compareString (rawProtected raw) (S.fromList compareString (concatMap Modules.sourceUsed modules));
    allocate state entity = case M.lookup compareString (Modules.owner entity) ownership of {
      Nothing -> Modules.allocateName used state entity;
      Just identity -> (,) (M.insert Modules.compareEntity entity
        (Artifact.definitionName identity entity) (fst state)) (snd state)
    }
  } in Modules.Names (fst (foldl allocate ((,) M.empty 0) (S.toList entities)));
  mixedKey raw entity = case M.lookup compareString (Modules.owner entity) (owners raw) of {
    Just identity -> Artifact.definitionName identity entity;
    Nothing -> Modules.termIdentity entity
  };
  resolvePreparedPlan raw = Modules.resolvePlanWithKey (mixedNames raw) (mixedKey raw);
  collision raw sources = let { protected = rawProtected raw; selected = map sourceName (librarySources raw) } in
    any (\source -> not (elem eqString (Modules.moduleIdentity source) selected) &&
      any (\name -> S.member compareString name protected &&
        not (D.sourceBuiltinType name || D.sourceBuiltinConstructor name)) (Modules.sourceUsed source)) sources;
  original mode sources names = mapEither (\compiled ->
    Compilation (Core.checkedTerm compiled) (Core.sourceType compiled) False names)
    (Compiler.compileLinked mode sources);
  compileLoadedV1 registry mode loaded = let {
    sources = Modules.loadedSources loaded;
    entries = Modules.loadedEntries loaded;
    candidates = sortBy (\a b -> compareInt (length (librarySources b)) (length (librarySources a)))
      (filter (matches mode entries) registry);
    planned = Modules.prepareCrateResolution mode M.empty sources;
    resolution = bindEither planned (Modules.resolveCratePlan Modules.freshNames);
    -- The normal result does not force this qualification-only name inventory.
    -- An ineligible program must not pay for a second module resolution.
    ordinaryNames = case resolution of {
      Left _ -> Modules.Names M.empty;
      Right value -> Modules.resolvedCrateNames value
    };
    fallback = original mode sources ordinaryNames
  } in
    case candidates of {
      [] -> fallback;
      (:) raw _ -> do {
        -- Cheap byte matching above is only rejection. Even a perfect match
        -- cannot bypass ordinary namespace checking before artifact admission.
        Core.atPhase ModuleResolution resolution;
        if collision raw sources then fallback else
          case bindEither planned (resolvePreparedPlan raw) of {
            Left _ -> fallback;
            Right prepared -> case validatePrepared raw prepared of {
              Left _ -> fallback;
              Right () -> do {
                linked <- Core.atPhase Verification (checkedLibrary raw);
                compilePrepared raw linked prepared
              }
            }
          }
      }
    };
  canonicalParts resolution = do {
    let { resolved = Modules.resolvedCrateModules resolution };
    ds <- D.canonicalSourceDeclarations []
      (concatMap (compose Modules.renamedDatatypes Modules.resolvedContents) resolved);
    cs <- Classes.canonicalSourceClasses S.empty ds []
      (concatMap (compose Modules.renamedClasses Modules.resolvedContents) resolved);
    Right ((,) ds cs)
  };
  supportNames klass = append ["Dict_" ++ Modules.className klass, "Make_" ++ Modules.className klass]
    (append (map (\method -> "select_" ++ fst method) (Modules.classMethods klass))
      (map (\index -> "super_" ++ Modules.className klass ++ "_" ++ showInt index)
        (range 0 (length (Modules.superclasses klass) - 1))));
  validatePrepared raw resolution = do {
    validateRegistry raw;
    let { ownership = owners raw;
          imported = filter (\entry -> M.member compareString
            (Modules.moduleIdentity (Modules.resolvedSource entry)) ownership)
            (Modules.resolvedCrateModules resolution);
          own = filter (\entry -> not (M.member compareString
            (Modules.moduleIdentity (Modules.resolvedSource entry)) ownership))
            (Modules.resolvedCrateModules resolution);
          support = concatMap supportNames (concatMap (compose Modules.renamedClasses Modules.resolvedContents) own);
          occupied = S.union compareString (rawProtected raw)
            (S.fromList compareString (concatMap (compose Modules.sourceUsed Modules.resolvedSource) own)) };
    ensure (length support == length (nubBy eqString support) &&
      all (\name -> not (S.member compareString name occupied)) support)
      "prepared library support identity collision";
    -- Exact source header correspondence is checked independently of the
    -- opaque bodies. The full fresh order below remains the layout authority.
    ds <- D.canonicalSourceDeclarations [] (concatMap (compose Modules.renamedDatatypes Modules.resolvedContents) imported);
    cs <- Classes.canonicalSourceClasses S.empty ds []
      (concatMap (compose Modules.renamedClasses Modules.resolvedContents) imported);
    ensure (Artifact.sameDeclarations ds (concatMap Artifact.crateData (interfaces raw)))
      "prepared library source datatype mismatch";
    ensure (eqString (Artifact.sourceMetadata [] cs [])
      (Artifact.sourceMetadata [] (concatMap Artifact.crateClasses (interfaces raw)) []))
      "prepared library source class mismatch"
  };
  instanceRows raw resolution bindings = let {
    closeLocal = Surface.closeResolvedInstance (Surface.helperScope bindings);
    rows = Modules.resolvedInstanceRows resolution;
    ownership = owners raw;
    imported = M.fromList compareString (concatMap Artifact.crateInstances (interfaces raw));
    protected = S.union compareString (rawProtected raw)
      (S.fromList compareString (concatMap (compose Modules.sourceUsed Modules.resolvedSource)
        (Modules.resolvedCrateModules resolution)))
  } in traverseEither (\((,) index ((,) owner inst)) -> let { instanceValue = Modules.instanceValue resolution inst } in
    case M.lookup compareString owner ownership of {
      Just identity -> let { name = Artifact.instanceName identity owner instanceValue } in
        case M.lookup compareString name imported of {
          Nothing -> Left "prepared library instance identity mismatch";
          Just recorded -> do {
            ensure (eqString (Separate.prettyInstance (Separate.stripInstance instanceValue))
              (Separate.prettyInstance recorded)) "prepared library instance contract mismatch";
            Right ((,) name recorded)
          }
        };
      Nothing -> do {
        closed <- closeLocal inst;
        let { name = fst (Modules.chooseName protected ("preparedUserInstance" ++ showInt index ++ "_") 0) };
        Right ((,) name closed)
      }
    }) (zip (range 0 (length rows - 1)) rows);
  -- This value authenticates the freshly checked user wrapper only. Installed
  -- native code identity and file pins are enforced by the compiler consumer.
  -- Raw library metadata does not manufacture a checked library implementation.
  data NativeRoot = NativeRoot Checked.CheckedTerm (Map String XType) String XType ([] DataDecl) Int;
  nativeCheckedWrapper (NativeRoot value _ _ _ _ _) = value;
  nativeSignatures (NativeRoot _ value _ _ _ _) = value;
  nativeSourceType (NativeRoot _ _ value _ _ _) = value;
  nativeInferredType (NativeRoot _ _ _ value _ _) = value;
  nativeDeclarations (NativeRoot _ _ _ _ value _) = value;
  nativeBuiltinCount (NativeRoot _ _ _ _ _ value) = value;
  nativeLibraryDeclarationsV1 raw = foldEither Separate.mergeDeclaration []
    (concatMap Artifact.crateLoweredData (interfaces raw));
  nativeExportSignatures raw = M.toList (M.fromList compareString
    (concatMap Artifact.crateBindings (interfaces raw)));
  nativeLibraryV1 raw = do {
    admitted <- checkedLibrary raw;
    proof <- librarySpine admitted;
    declarations <- nativeLibraryDeclarations raw;
    Right ((,,) proof (nativeExportSignatures raw) declarations)
  };
  nativeHeadersV1 raw = do {
    validateRegistry raw;
    let { ifaces = interfaces raw; byName = Artifact.interfaceMap ifaces };
    ordered <- Artifact.dependencyClosure byName [] [] (map Artifact.crateId ifaces);
    traverseEither Artifact.validateInterface ordered;
    traverseEither (Artifact.validateDependencies byName) ordered;
    traverseEither (Artifact.validateExportBoundary byName) ordered;
    Artifact.validateLayouts ordered;
    Right ()
  };
  -- Completion supplies only the fixed installed implementation's namespace
  -- metadata. Actual loaded modules are checked before any missing module is
  -- filled; user declarations and import reach remain the visibility authority.
  nativeLoadedMatches raw mode loaded = let {
    entries = Modules.loadedEntries loaded;
    recorded = librarySources raw;
    selected = map sourceName recorded
  } in sameMode mode (libraryMode raw) && not (null entries) &&
    not (elem eqString (Modules.moduleIdentity (Modules.loadedSource (last entries))) selected) &&
    all (\entry -> let { name = Modules.moduleIdentity (Modules.loadedSource entry) } in
      case find (\source -> eqString name (sourceName source)) recorded of {
        Nothing -> True;
        Just source -> sourceMatches [entry] source
      }) entries;
  -- Missing installed modules supply nominal and export namespace metadata,
  -- but their instances are not part of the actual imported program. Class
  -- lowering checks overlap globally before per-owner scope filtering, so
  -- retaining those absent instances would reject otherwise legal programs.
  nativeNamespaceOnly (SourceModule path name exports imports declarations classes _ values body syntax) =
    SourceModule path name exports imports declarations classes [] values body syntax;
  completeNativeSources parseSource raw loaded = do {
    let { entries = Modules.loadedEntries loaded;
          selected = map sourceName (librarySources raw) };
    installed <- traverseEither (\recorded -> case find (\entry ->
      eqString (Modules.moduleIdentity (Modules.loadedSource entry)) (sourceName recorded)) entries of {
      Just actual -> Right (Modules.loadedSource actual);
      Nothing -> do {
        parsed <- parseSource (sourcePath recorded) (sourceText recorded);
        ensure (eqString (Modules.moduleIdentity parsed) (sourceName recorded) &&
          eqString (Modules.sourcePath parsed) (sourcePath recorded) &&
          sameSyntax (Modules.sourceSyntax parsed) (sourceSyntax recorded) &&
          not (isJust (Modules.sourceBody parsed))) "installed source completion identity mismatch";
        Right (nativeNamespaceOnly parsed)
      }
    }) (librarySources raw);
    -- Recorded fixed modules are already in the producer's dependency order.
    -- Keeping all actual noninstalled entries afterward preserves the real
    -- user's root-last contract and does not add any import edge.
    Right (append installed (map Modules.loadedSource (filter (\entry ->
      not (elem eqString (Modules.moduleIdentity (Modules.loadedSource entry)) selected)) entries)))
  };
  compileNativeRoot raw mode loaded = compileNativeRootUsing Parser.parseModule raw mode loaded;
  nativeClosedSources sources = let {
    names = map Modules.moduleIdentity sources
  } in length names == length (nubBy eqString names) && all
    (\source -> all (\entry -> let { name = Modules.importedModule entry } in
      Modules.isBuiltinModule name || elem eqString name names) (Modules.sourceImports source)) sources;
  compileNativeRootUsingV1 parseSource raw mode loaded = do {
    let { sources = Modules.loadedSources loaded;
      ordinary = Modules.resolveCrateWithAllocator mode M.empty Modules.freshNames sources };
    Core.atPhase Verification (ensure (nativeLoadedMatches raw mode loaded)
      "installed native library requires exact loaded library source reads");
    if nativeClosedSources sources then Right () else do {
      Core.atPhase ModuleResolution ordinary;
      Right ()
    };
    let { attempt = do {
      Core.atPhase Verification (ensure (not (collision raw sources)) "installed native library source identity collision");
      completed <- Core.atPhase Verification (completeNativeSources parseSource raw loaded);
      prepared <- Core.atPhase ModuleResolution
        (bindEither (Modules.prepareCrateResolution mode M.empty completed) (resolvePreparedPlan raw));
      Core.atPhase Verification (validatePrepared raw prepared);
      Core.atPhase Verification (nativeHeaders raw);
      compileNativeResolvedRoot raw prepared
    } };
    case attempt of {
      Right value -> Right value;
      Left failure -> do { Core.atPhase ModuleResolution ordinary; Left failure }
    }
  };
  -- Only the canonical builtin crate is eligible for local materialization.
  -- Ownership comes from validated crate metadata, never a spelling or hint.
  nativeBuiltinStateV1 selected raw = case filter (\entry -> eqString
      (Artifact.crateId (Artifact.objectInterface (libraryObject entry))) Artifact.builtinCrateIdentity)
      (libraryObjects raw) of {
    [entry] -> let { object = libraryObject entry; iface = Artifact.objectInterface object;
      layouts = M.fromList compareString (map (\d -> (,) (D.datatypeName d) (Artifact.datatypePart d))
        (Artifact.crateLoweredData iface)) } in do {
      Artifact.validateInterface iface;
      Artifact.validateLayouts [iface];
      Artifact.linkSelectedCrateWithSpine selected (Artifact.interfaceMap [iface]) layouts
        ((,) (Artifact.FragmentState 0 M.empty [] [] S.empty) (Right Checked.emptySpine)) object
    };
    _ -> Left "native library requires one canonical builtin implementation"
  };
  -- Only entities owned by the imported interface may fill an existing
  -- source slot. An equal printed name in the user crate is a different slot.
  externalParameters resolution signatures = let {
    symbols = Modules.bindingSymbols (Modules.resolvedCrateBindings resolution)
  } in Parameters.admit symbols (Dependency.symbolKeyIndex symbols) signatures;
  compileNativeResolvedRootV1 raw resolution = do {
    let { display = Modules.displayNames (Modules.resolvedCrateDisplayNames resolution);
          sourcePhase phase result = Core.atPhase phase (mapLeft display result);
          resolved = Modules.resolvedCrateModules resolution;
          ownership = owners raw;
          own = filter (\entry -> not (M.member compareString
            (Modules.moduleIdentity (Modules.resolvedSource entry)) ownership)) resolved;
          bindings = Modules.boundIn resolution own;
          entryModule = last resolved };
    entry <- sourcePhase ModuleResolution (Modules.entryExpr resolution entryModule);
    body <- sourcePhase ModuleResolution (Surface.bindResolvedExpr bindings entry);
    parts <- sourcePhase Inference (canonicalParts resolution);
    instances <- sourcePhase Inference (instanceRows raw resolution bindings);
    let { signatures = M.fromList compareString (concatMap Artifact.crateBindings (interfaces raw));
          dictionaries = M.fromList compareString
            (map (\klass -> (,) ("Dict_" ++ Modules.className klass) (Modules.className klass)) (snd parts));
          sourceValues = S.fromList compareString (concatMap
            (compose Modules.renamedValueNames Modules.resolvedContents)
            (filter (\r -> M.member compareString (Modules.moduleIdentity (Modules.resolvedSource r)) ownership) resolved));
          externals = M.mapWithKey (\name ty -> if S.member compareString name sourceValues
            then Separate.sourceScheme dictionaries ty else Separate.sourceSchemeIn M.empty False ty) signatures };
    full <- sourcePhase Inference (Classes.lowerSeparateClassesInScopes externals (map fst instances)
      (Modules.resolvedCrateValueScopes resolution) (Modules.resolvedCrateInstanceScopes resolution)
      (SClassProgram (fst parts) (snd parts) (map snd instances) body));
    selected <- sourcePhase Verification (Parameters.select (externalParameters resolution signatures) full);
    let { lowered = fst selected; selectedSignatures = Parameters.project (snd selected);
          diagnostic = Modules.displayNames (M.union compareString (M.map display (snd lowered))
            (Modules.resolvedCrateDisplayNames resolution)) };
    compiled <- mapLeft (\(CompileError phase message) -> CompileError phase (diagnostic message))
      (Imported.finishSelected (snd selected) lowered);
    let { wrapper = Imported.checkedWrapper compiled;
          declarations = case Checked.term wrapper of { XWithData ds _ -> ds; _ -> [] } };
    Core.atPhase Verification (do {
      combined <- foldEither Separate.mergeDeclaration declarations
        (concatMap Artifact.crateLoweredData (interfaces raw));
      ensure (length combined == length declarations) "installed native library added an unowned datatype layout";
      -- Fresh user declarations are checked in the wrapper. The native backend
      -- additionally checks their names against the installation's sealed
      -- nominal-use census before extending its fixed constructor-tag prefix.
      Right ()
    });
    usedSignatures <- sourcePhase Verification (Imported.usedImportSignatures selectedSignatures compiled);
    let { builtinKeys = S.fromList compareString (concatMap (\iface ->
      if eqString (Artifact.crateId iface) Artifact.builtinCrateIdentity
        then map fst (Artifact.crateBindings iface) else []) (interfaces raw));
      needsBuiltin = any (\key -> S.member compareString key builtinKeys) (M.keys usedSignatures) };
    local <- if not needsBuiltin then sourcePhase Verification
      (Imported.materializeLinked Checked.emptySpine selectedSignatures compiled) else do {
      admitted <- sourcePhase Verification (nativeBuiltinState (filter (\key -> S.member compareString key builtinKeys) (M.keys usedSignatures)) raw);
      let { builtins = fst admitted;
        fallback = Imported.materializeImports selectedSignatures compiled
          (Artifact.fragmentSerial builtins) (Artifact.fragmentBindings builtins) (Artifact.fragmentBodies builtins) };
      sourcePhase Verification (case snd admitted of {
        Left _ -> fallback;
        Right proof -> case Imported.materializeLinked proof selectedSignatures compiled of {
          Left _ -> fallback;
          Right result -> Right result
        }
      })
    };
    Right (NativeRoot (fst local) (snd local) (display (Imported.sourceType compiled))
      (Imported.inferredType compiled) declarations (length (filter (\key -> S.member compareString key builtinKeys) (M.keys usedSignatures))))
  };
  compilePreparedV1 raw admitted resolution = do {
    let { linked = libraryState admitted;
          display = Modules.displayNames (Modules.resolvedCrateDisplayNames resolution);
          sourcePhase phase result = Core.atPhase phase (mapLeft display result);
          resolved = Modules.resolvedCrateModules resolution;
          ownership = owners raw;
          own = filter (\entry -> not (M.member compareString
            (Modules.moduleIdentity (Modules.resolvedSource entry)) ownership)) resolved;
          bindings = Modules.boundIn resolution own;
          entryModule = last resolved };
    entry <- sourcePhase ModuleResolution (Modules.entryExpr resolution entryModule);
    body <- sourcePhase ModuleResolution (Surface.bindResolvedExpr bindings entry);
    parts <- sourcePhase Inference (canonicalParts resolution);
    instances <- sourcePhase Inference (instanceRows raw resolution bindings);
    let { signatures = M.fromList compareString (concatMap Artifact.crateBindings (interfaces raw));
          dictionaries = M.fromList compareString
            (map (\klass -> (,) ("Dict_" ++ Modules.className klass) (Modules.className klass)) (snd parts));
          sourceValues = S.fromList compareString (concatMap
            (compose Modules.renamedValueNames Modules.resolvedContents)
            (filter (\r -> M.member compareString (Modules.moduleIdentity (Modules.resolvedSource r)) ownership) resolved));
          externals = M.mapWithKey (\name ty -> if S.member compareString name sourceValues
            then Separate.sourceScheme dictionaries ty else Separate.sourceSchemeIn M.empty False ty) signatures };
    full <- sourcePhase Inference (Classes.lowerSeparateClassesInScopes externals (map fst instances)
      (Modules.resolvedCrateValueScopes resolution) (Modules.resolvedCrateInstanceScopes resolution)
      (SClassProgram (fst parts) (snd parts) (map snd instances) body));
    selected <- sourcePhase Verification (Parameters.select (externalParameters resolution signatures) full);
    let { lowered = fst selected; selectedSignatures = Parameters.project (snd selected);
          diagnostic = Modules.displayNames (M.union compareString (M.map display (snd lowered))
            (Modules.resolvedCrateDisplayNames resolution)) };
    compiled <- mapLeft (\(CompileError phase message) -> CompileError phase (diagnostic message))
      (Imported.finishSelected (snd selected) lowered);
    let { fresh = snd (Separate.freshObject (Artifact.fragmentSerial linked)
            (Checked.term (Imported.checkedWrapper compiled)));
          rootData = case fresh of { XWithData declarations _ -> declarations; _ -> [] } };
    actual <- sourcePhase Verification (Imported.remove selectedSignatures (Artifact.fragmentBindings linked) fresh);
    declarations <- sourcePhase Verification (foldEither Separate.mergeDeclaration rootData (Artifact.fragmentData linked));
    sourcePhase Verification (ensure (length declarations == length rootData)
      "prepared library added an unowned datatype layout");
    grafted <- sourcePhase Verification (foldEither (\rest spine -> Separate.graft spine rest)
      actual (Artifact.fragmentBodies linked));
    let { ordinaryCheck = Checked.check (XWithData declarations grafted);
          composed = case librarySpine admitted of {
            Left _ -> ordinaryCheck;
            Right spine -> case Imported.finishLinked spine selectedSignatures compiled of {
              Left _ -> ordinaryCheck;
              Right proof -> Right proof
            }
          } };
    checked <- sourcePhase Verification composed;
    sourcePhase Verification (ensure (T.alphaEq (Checked.typeOf checked) (Imported.inferredType compiled))
      "prepared library graft changed the user root type");
    Right (Compilation checked (display (Imported.sourceType compiled)) True (Modules.resolvedCrateNames resolution))
  };
  -- N7 object-known dispatch. A constructor selects policy, never admission.
  -- Every marked operation enters Artifact through the ACTUAL object list.
  knownLibraryObjects raw = map (compose Artifact.legacyObject libraryObject) (libraryObjects raw);
  hasEnvelopeLibraryObjects raw = any Artifact.envelopeMarked (knownLibraryObjects raw);
  -- Registry identity and witness errors precede object policy inspection.
  -- The marker selects fresh actual-object admission, never a proof shortcut.
  checkedLibrary raw = do {
    validateRegistry raw;
    if hasEnvelopeLibraryObjects raw then checkedKnownLibrary raw else checkedLibraryV1 raw
  };
  checkedKnownLibrary raw = do {
    validateRegistry raw;
    linked <- Artifact.linkKnownObjectsWithSpine (knownLibraryObjects raw)
      (map Artifact.crateId (interfaces raw))
      ((,) (Artifact.FragmentState 0 M.empty [] [] S.empty) (Right Checked.emptySpine));
    Right (CheckedLibrary (fst linked) (snd linked))
  };
  -- Preserve the original left-to-right legacy merge, including an error
  -- before a later object is demanded. Enter the known-object operation only
  -- when an actual marked object is reached; it retains caller declaration order.
  nativeLibraryDeclarations raw = nativeDeclarationsDispatch raw [] (libraryObjects raw);
  nativeDeclarationsDispatch :: RawLibrary -> [] DataDecl -> [] LibraryObject -> Either String ([] DataDecl);
  nativeDeclarationsDispatch raw declarations remaining = case remaining of {
    [] -> Right declarations;
    (:) entry rest -> let { object = libraryObject entry } in
      if Artifact.envelopeMarked object then Artifact.knownObjectDeclarations (knownLibraryObjects raw)
      else do {
        merged <- foldEither Separate.mergeDeclaration declarations
          (Artifact.crateLoweredData (Artifact.objectInterface object));
        nativeDeclarationsDispatch raw merged rest
      }
  };
  -- One admission context owns both linking and caller-order declarations.
  -- Do not reset a second ledger by calling nativeLibraryDeclarations here.
  nativeLibrary raw = do {
    validateRegistry raw;
    if hasEnvelopeLibraryObjects raw then nativeKnownLibrary raw else nativeLibraryV1 raw
  };
  nativeKnownLibrary raw = do {
    validateRegistry raw;
    linked <- Artifact.linkKnownObjectsWithSpineAndDeclarations (knownLibraryObjects raw)
      (map Artifact.crateId (interfaces raw))
      ((,) (Artifact.FragmentState 0 M.empty [] [] S.empty) (Right Checked.emptySpine));
    proof <- snd (fst linked);
    Right ((,,) proof (nativeExportSignatures raw) (snd linked))
  };
  nativeHeaders raw = do {
    validateRegistry raw;
    if hasEnvelopeLibraryObjects raw then
      Artifact.validateKnownObjectHeaders (knownLibraryObjects raw)
        (map Artifact.crateId (interfaces raw))
    else nativeHeadersV1 raw
  };
  nativeBuiltinState selected raw = if hasEnvelopeLibraryObjects raw
    then nativeKnownBuiltinState selected raw else nativeBuiltinStateV1 selected raw;
  nativeKnownBuiltinState selected raw = case filter (\entry -> eqString
      (Artifact.crateId (Artifact.objectInterface (libraryObject entry))) Artifact.builtinCrateIdentity)
      (libraryObjects raw) of {
    [entry] -> Artifact.linkKnownSelectedObjectWithSpine selected (libraryObject entry)
      ((,) (Artifact.FragmentState 0 M.empty [] [] S.empty) (Right Checked.emptySpine));
    _ -> Left "native library requires one canonical builtin implementation"
  };
  -- Keep the original compiler demand/error order. In particular, candidate
  -- matching and ordinary namespace failures do not inspect library objects.
  -- Selected objects still undergo fresh admission at checkedLibrary/nativeHeaders
  -- in the original pipeline. Downstream inference, naming and wrapper work use
  -- the existing compiler/process guards; these are not a whole-compilation
  -- envelope render ledger or an aggregate dependency-closure memory bound.
  compileLoaded :: [] RawLibrary -> PreludeMode -> Modules.LoadedModules -> Either CompileError Compilation;
  compileLoaded registry mode loaded = compileLoadedV1 registry mode loaded;
  compileNativeRootUsing :: (String -> String -> Either String SourceModule) -> RawLibrary ->
    PreludeMode -> Modules.LoadedModules -> Either CompileError NativeRoot;
  compileNativeRootUsing parseSource raw mode loaded = compileNativeRootUsingV1 parseSource raw mode loaded;
  compileNativeResolvedRoot :: RawLibrary -> Modules.ResolvedCrate -> Either CompileError NativeRoot;
  compileNativeResolvedRoot raw resolution = compileNativeResolvedRootV1 raw resolution;
  compilePrepared :: RawLibrary -> CheckedLibrary -> Modules.ResolvedCrate -> Either CompileError Compilation;
  compilePrepared raw admitted resolution = compilePreparedV1 raw admitted resolution;
}
