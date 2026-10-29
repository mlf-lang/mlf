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
  checkedLibrary raw = do {
    validateRegistry raw;
    let { ifaces = interfaces raw; byName = Artifact.interfaceMap ifaces;
          objects = M.fromList compareString (map (\entry -> let { object = libraryObject entry }
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
  collision raw sources = let { protected = rawProtected raw; selected = map sourceName (librarySources raw) } in
    any (\source -> not (elem eqString (Modules.moduleIdentity source) selected) &&
      any (\name -> S.member compareString name protected &&
        not (D.sourceBuiltinType name || D.sourceBuiltinConstructor name)) (Modules.sourceUsed source)) sources;
  original mode sources names = mapEither (\compiled ->
    Compilation (Core.checkedTerm compiled) (Core.sourceType compiled) False names)
    (Compiler.compileLinked mode sources);
  compileLoaded registry mode loaded = let {
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
          case bindEither planned (Modules.resolveCratePlan (mixedNames raw)) of {
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
  instanceRows raw resolution values = let {
    ownership = owners raw;
    imported = M.fromList compareString (concatMap Artifact.crateInstances (interfaces raw));
    protected = S.union compareString (rawProtected raw)
      (S.fromList compareString (concatMap (compose Modules.sourceUsed Modules.resolvedSource)
        (Modules.resolvedCrateModules resolution)))
  } in traverseEither (\((,) index ((,) owner instanceValue)) ->
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
        closed <- Separate.closeInstance values instanceValue;
        let { name = fst (Modules.chooseName protected ("preparedUserInstance" ++ showInt index ++ "_") 0) };
        Right ((,) name closed)
      }
    }) (zip (range 0 (length (Modules.resolvedCrateInstances resolution) - 1))
      (Modules.resolvedCrateInstances resolution));
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
  nativeLibraryDeclarations raw = foldEither Separate.mergeDeclaration []
    (concatMap Artifact.crateLoweredData (interfaces raw));
  nativeExportSignatures raw = M.toList (M.fromList compareString
    (concatMap Artifact.crateBindings (interfaces raw)));
  nativeLibrary raw = do {
    admitted <- checkedLibrary raw;
    proof <- librarySpine admitted;
    declarations <- nativeLibraryDeclarations raw;
    Right ((,,) proof (nativeExportSignatures raw) declarations)
  };
  nativeHeaders raw = do {
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
  compileNativeRootUsing parseSource raw mode loaded = do {
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
        (Modules.resolveCrateWithAllocator mode M.empty (mixedNames raw) completed);
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
  nativeBuiltinState selected raw = case filter (\entry -> eqString
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
  compileNativeResolvedRoot raw resolution = do {
    let { display = Modules.displayNames (Modules.resolvedCrateDisplayNames resolution);
          sourcePhase phase result = Core.atPhase phase (mapLeft display result);
          resolved = Modules.resolvedCrateModules resolution;
          ownership = owners raw;
          own = filter (\entry -> not (M.member compareString
            (Modules.moduleIdentity (Modules.resolvedSource entry)) ownership)) resolved;
          values = concatMap (compose Modules.renamedValues Modules.resolvedContents) own;
          entryModule = last resolved;
          source = Modules.resolvedSource entryModule };
    entry <- sourcePhase ModuleResolution (case Modules.renamedBody (Modules.resolvedContents entryModule) of {
      Just expression -> Right expression;
      Nothing -> if any (\value -> eqString (Modules.valueName value) "main") (Modules.sourceValues source)
        then mapEither SVar (Modules.resolvedName (Modules.resolvedCrateNames resolution)
          (Modules.Entity (Modules.moduleIdentity source) "main" Modules.Value))
        else Modules.resolveExpr (Modules.resolvedCrateNames resolution) (Modules.resolvedScope entryModule) (SVar "main")
    });
    body <- sourcePhase ModuleResolution (Surface.bindValues values entry);
    parts <- sourcePhase Inference (canonicalParts resolution);
    instances <- sourcePhase Inference (instanceRows raw resolution values);
    let { signatures = M.fromList compareString (concatMap Artifact.crateBindings (interfaces raw));
          dictionaries = M.fromList compareString
            (map (\klass -> (,) ("Dict_" ++ Modules.className klass) (Modules.className klass)) (snd parts));
          sourceValues = S.fromList compareString (concatMap
            (\entry -> map (\((,,) name _ _) -> name) (Modules.renamedValues (Modules.resolvedContents entry)))
            (filter (\r -> M.member compareString (Modules.moduleIdentity (Modules.resolvedSource r)) ownership) resolved));
          externals = M.mapWithKey (\name ty -> if S.member compareString name sourceValues
            then Separate.sourceScheme dictionaries ty else Separate.sourceSchemeIn M.empty False ty) signatures };
    full <- sourcePhase Inference (Classes.lowerSeparateClassesWithScopes externals (map fst instances)
      (Modules.resolvedCrateValueScopes resolution) (Modules.resolvedCrateInstanceScopes resolution)
      (SClassProgram (fst parts) (snd parts) (map snd instances) body));
    selected <- sourcePhase Verification (Parameters.select signatures full);
    let { lowered = fst selected; selectedSignatures = snd selected;
          diagnostic = Modules.displayNames (M.union compareString (M.map display (snd lowered))
            (Modules.resolvedCrateDisplayNames resolution)) };
    compiled <- mapLeft (\(CompileError phase message) -> CompileError phase (diagnostic message))
      (Imported.finishCompilation selectedSignatures lowered);
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
  compilePrepared raw admitted resolution = do {
    let { linked = libraryState admitted;
          display = Modules.displayNames (Modules.resolvedCrateDisplayNames resolution);
          sourcePhase phase result = Core.atPhase phase (mapLeft display result);
          resolved = Modules.resolvedCrateModules resolution;
          ownership = owners raw;
          own = filter (\entry -> not (M.member compareString
            (Modules.moduleIdentity (Modules.resolvedSource entry)) ownership)) resolved;
          values = concatMap (compose Modules.renamedValues Modules.resolvedContents) own;
          entryModule = last resolved;
          source = Modules.resolvedSource entryModule };
    entry <- sourcePhase ModuleResolution (case Modules.renamedBody (Modules.resolvedContents entryModule) of {
      Just expression -> Right expression;
      Nothing -> if any (\value -> eqString (Modules.valueName value) "main") (Modules.sourceValues source)
        then mapEither SVar (Modules.resolvedName (Modules.resolvedCrateNames resolution)
          (Modules.Entity (Modules.moduleIdentity source) "main" Modules.Value))
        else Modules.resolveExpr (Modules.resolvedCrateNames resolution) (Modules.resolvedScope entryModule) (SVar "main")
    });
    body <- sourcePhase ModuleResolution (Surface.bindValues values entry);
    parts <- sourcePhase Inference (canonicalParts resolution);
    instances <- sourcePhase Inference (instanceRows raw resolution values);
    let { signatures = M.fromList compareString (concatMap Artifact.crateBindings (interfaces raw));
          dictionaries = M.fromList compareString
            (map (\klass -> (,) ("Dict_" ++ Modules.className klass) (Modules.className klass)) (snd parts));
          sourceValues = S.fromList compareString (concatMap
            (\entry -> map (\((,,) name _ _) -> name) (Modules.renamedValues (Modules.resolvedContents entry)))
            (filter (\r -> M.member compareString (Modules.moduleIdentity (Modules.resolvedSource r)) ownership) resolved));
          externals = M.mapWithKey (\name ty -> if S.member compareString name sourceValues
            then Separate.sourceScheme dictionaries ty else Separate.sourceSchemeIn M.empty False ty) signatures };
    full <- sourcePhase Inference (Classes.lowerSeparateClassesWithScopes externals (map fst instances)
      (Modules.resolvedCrateValueScopes resolution) (Modules.resolvedCrateInstanceScopes resolution)
      (SClassProgram (fst parts) (snd parts) (map snd instances) body));
    selected <- sourcePhase Verification (Parameters.select signatures full);
    let { lowered = fst selected; selectedSignatures = snd selected;
          diagnostic = Modules.displayNames (M.union compareString (M.map display (snd lowered))
            (Modules.resolvedCrateDisplayNames resolution)) };
    compiled <- mapLeft (\(CompileError phase message) -> CompileError phase (diagnostic message))
      (Imported.finishCompilation selectedSignatures lowered);
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
  }
}
