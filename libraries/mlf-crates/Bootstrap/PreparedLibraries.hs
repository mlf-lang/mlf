-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.PreparedLibraries
  (LibrarySource(..), LibraryObject(..), RawLibrary(..), Compilation,
   librarySchema, prepareFresh, admitLibrary, inputIdentity, librarySources, libraryObjects,
   sourceName, sourcePath, sourceText, sourceHash, sourceSyntax,
   metadataHash, objectHash, libraryInterface, readLibraryObject, readLibraryObjects, compileLoaded, checkedTerm,
   sourceType, reused, nameMap, dictionaryIdentities, nativeCrateInputsUsing) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Lexer as Lexer;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Primitive as Primitive;
  import qualified Bootstrap.CompilerCore as Core;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.BuiltinPreludeLiteral as Literal;
  import qualified Bootstrap.CrateSession as Session;
  import qualified Bootstrap.SourceCrate as Source;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.SourceEquality as SourceEquality;
  import qualified Bootstrap.X.Checked as Checked;

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
  -- A generated registry stores its exact sealed image beside a readable
  -- interface. It cannot supply an independent checked body for those bytes.
  -- In-memory producers may retain the original opaque checked object.
  data LibraryObject = LibraryObject String String Artifact.CrateObject |
    EncodedLibraryObject String String Artifact.CrateInterface ((,) String String);
  metadataHash value = case value of {
    LibraryObject hash _ _ -> hash;
    EncodedLibraryObject hash _ _ _ -> hash
  };
  objectHash value = case value of {
    LibraryObject _ hash _ -> hash;
    EncodedLibraryObject _ hash _ _ -> hash
  };
  libraryInterface value = case value of {
    LibraryObject _ _ object -> Artifact.objectInterface object;
    EncodedLibraryObject _ _ iface _ -> iface
  };
  readLibraryObject :: [] Artifact.CrateInterface -> LibraryObject -> IO (Either String Artifact.CrateObject);
  readLibraryObject available recorded = case recorded of {
    LibraryObject _ _ object -> ioReturn (Right object);
    EncodedLibraryObject _ expectedHash iface image -> do {
      decoded <- Literal.openCompilerImage image;
      case decoded of {
        Left message -> ioReturn (Left message);
        Right bytes -> do {
          actualHash <- byteArrayDigest bytes;
          if not (eqString actualHash expectedHash) then
            ioReturn (Left ("prepared library object SHA-256 mismatch: " ++ Artifact.crateId iface))
          else Artifact.decodeObjectWithOpenReader Nothing
            (\input expected -> Artifact.decodeOpenObject input expected
              (Artifact.openInterfaceDependencies available expected)) iface bytes
        }
      }
    }
  };
  data RawLibrary = RawLibrary String String PreludeMode ([] LibrarySource) ([] LibraryObject) ([] SourceModule);
  inputIdentity (RawLibrary value _ _ _ _ _) = value;
  librarySources (RawLibrary _ _ _ value _ _) = value;
  libraryObjects (RawLibrary _ _ _ _ value _) = value;
  libraryMode (RawLibrary _ _ value _ _ _) = value;
  librarySchema = "mlf-prepared-libraries/1/" ++ Lexer.frontendSemanticVersion ++ "/" ++
    Lexer.builtinInterfaceVersion ++ "/" ++ showInt (length Primitive.allPrimitives);
  data Compilation = Compilation Source.Compilation Bool;
  checkedTerm (Compilation value _) = Source.checkedTerm value;
  sourceType (Compilation value _) = Source.sourceType value;
  reused (Compilation _ value) = value;
  nameMap (Compilation value _) = Source.nameMap value;
  dictionaryIdentities (Compilation value _) = Source.dictionaryIdentities value;
  sameMode left right = case (,) left right of {
    (,) ImplicitPrelude ImplicitPrelude -> True;
    (,) NoImplicitPrelude NoImplicitPrelude -> True;
    _ -> False
  };
  sameSyntax left right = eqString (Lexer.sourceSyntaxName left) (Lexer.sourceSyntaxName right);
  digest value = stringLength value == 64 && all (\index -> let {
    code = stringCodeAt value index
  } in (code >= 48 && code <= 57) || (code >= 97 && code <= 102)) (range 0 63);
  interfaces raw = map libraryInterface (libraryObjects raw);
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
  -- Installed and package dependencies have the same checked open-object
  -- contract. Admission examines the actual objects; it never converts them
  -- into a legacy whole-program spine or trusts their source hash alone.
  admitLibrary :: RawLibrary -> IO (Either String ());
  admitLibrary raw = do {
    admitted <- readLibraryObjects raw;
    ioReturn (mapEither (\_ -> ()) admitted)
  };
  readRecordedObjects available recorded = case recorded of {
    [] -> ioReturn (Right []);
    (:) first rest -> do {
      object <- readLibraryObject available first;
      case object of {
        Left message -> ioReturn (Left message);
        Right value -> do {
          remaining <- readRecordedObjects available rest;
          ioReturn (mapEither ((:) value) remaining)
        }
      }
    }
  };
  -- Decode and admit once; callers that close a source root or emit native
  -- providers reuse these exact objects instead of reconstructing a body.
  readLibraryObjects :: RawLibrary -> IO (Either String ([] Artifact.CrateObject));
  readLibraryObjects raw = case nativeHeaders raw of {
    Left message -> ioReturn (Left message);
    Right () -> do {
      decoded <- readRecordedObjects (interfaces raw) (libraryObjects raw);
      ioReturn (do {
        objects <- decoded;
        let { roots = map Artifact.crateId (interfaces raw) };
        Artifact.validateKnownObjectHeaders objects roots;
        Artifact.linkKnownObjectsWithSpine objects roots
          ((,) (Artifact.FragmentState 0 M.empty [] [] S.empty) (Right Checked.emptySpine));
        Right objects
      })
    }
  };
  nativeHeaders raw = do {
    validateRegistry raw;
    let { objects = concatMap (\recorded -> case recorded of {
            LibraryObject _ _ object -> [object];
            EncodedLibraryObject _ _ _ _ -> []
          }) (libraryObjects raw);
          external = concatMap (\recorded -> case recorded of {
            LibraryObject _ _ _ -> [];
            EncodedLibraryObject _ _ iface _ -> [iface]
          }) (libraryObjects raw) };
    Artifact.envelopePrepareObjectInputs external objects
      (map Artifact.crateId (interfaces raw)) True;
    Right ()
  };
  prepareFresh :: String -> PreludeMode -> [] LibrarySource -> [] LibraryObject -> IO (Either String RawLibrary);
  prepareFresh identity mode sources objects = do {
    let { raw = RawLibrary identity librarySchema mode sources objects [Modules.preludeSource, Modules.primitiveSource] };
    admitted <- admitLibrary raw;
    ioReturn (mapEither (\_ -> raw) admitted)
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
  canonicalHeaders resolved = Classes.canonicalSourceHeaders S.empty [] []
    (concatMap (compose Modules.renamedDatatypes Modules.resolvedContents) resolved)
    (concatMap (compose Modules.renamedClasses Modules.resolvedContents) resolved);
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
    (,) ds cs <- canonicalHeaders imported;
    ensure (Artifact.sameDeclarations ds (concatMap Artifact.crateData (interfaces raw)))
      "prepared library source datatype mismatch";
    ensure (eqString (Artifact.sourceMetadata [] cs [])
      (Artifact.sourceMetadata [] (concatMap Artifact.crateClasses (interfaces raw)) []))
      "prepared library source class mismatch"
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
  nativeClosedSources sources = let {
    names = map Modules.moduleIdentity sources
  } in length names == length (nubBy eqString names) && all
    (\source -> all (\entry -> let { name = Modules.importedModule entry } in
      Modules.isBuiltinModule name || elem eqString name names) (Modules.sourceImports source)) sources;
  -- Source admission precedes either checked or native dependency selection.
  -- Validate module visibility on the original reads, then compare resolved
  -- headers with the closed interfaces generated for the installation.
  admitNativeSources parseSource raw mode loaded = do {
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
      Right prepared
    } };
    case attempt of {
      Right value -> Right value;
      Left failure -> do { Core.atPhase ModuleResolution ordinary; Left failure }
    }
  };
  nativeCrateInputsUsing :: (String -> String -> Either String SourceModule) -> RawLibrary ->
    PreludeMode -> Modules.LoadedModules ->
    Either CompileError ((,) ([] SourceModule) ([] ((,) String Artifact.CrateInterface)));
  nativeCrateInputsUsing parseSource raw mode loaded = do {
    resolved <- admitNativeSources parseSource raw mode loaded;
    let { sources = Modules.loadedSources loaded;
          ownership = owners raw;
          present = S.fromList compareString (map Modules.moduleIdentity sources);
          -- The package checker sees the entire installed crate. Its extra
          -- instance heads must not invalidate the loaded program's own heads.
          missingOwner name = not (Modules.isBuiltinModule name || S.member compareString name present);
          localInstances = map snd (filter (\entry -> not (M.member compareString (fst entry) ownership))
            (Modules.resolvedCrateInstances resolved));
          absent iface ((,) name instanceDecl) = do {
            owner <- Artifact.instanceOwner iface name;
            Right (if missingOwner owner then [instanceDecl] else [])
          };
          label iface = "/prepared/" ++ inputIdentity raw ++ "/" ++
            Separate.compactName (Artifact.crateId iface) ++ ".mlfci";
          inputs selected = let {
            supplied = S.fromList compareString (concatMap Artifact.crateModules selected);
            own = filter (\source -> not (S.member compareString (Modules.moduleIdentity source) supplied)) sources
          } in (,) own (map (\iface -> (,) (label iface) iface) selected);
          available = interfaces raw };
    if null localInstances then Right (inputs available) else do {
      inherited <- Core.atPhase Verification (traverseEither
        (\iface -> traverseEither (absent iface) (Artifact.crateInstances iface)) available);
      let { extras = concat (concat inherited) };
      case traverseEither (\inst -> traverseEither (\extra -> Classes.checkOverlap [inst,extra]) extras) localInstances of {
        Right _ -> Right (inputs available);
        -- The combined library cannot be linked coherently with this source.
        -- Compile the actual loaded modules and keep their checked builtin
        -- dependency. Visible conflicting heads still meet in source inference.
        Left _ -> Right (inputs (filter (\iface -> eqString (Artifact.crateId iface) Artifact.builtinCrateIdentity) available))
      }
    }
  };
  -- A prepared registry only selects dependency objects. The user source
  -- enters exactly the same crate session as an uncached source/AST request.
  -- Namespace errors still precede registry admission, and a source mismatch
  -- still falls back before inspecting an unrelated installed object.
  compileLoaded :: [] RawLibrary -> PreludeMode -> Modules.LoadedModules -> IO (Either CompileError Compilation);
  compileLoaded registry mode loaded = let {
    sources = Modules.loadedSources loaded;
    entries = Modules.loadedEntries loaded;
    candidates = sortBy (\a b -> compareInt (length (librarySources b)) (length (librarySources a)))
      (filter (matches mode entries) registry);
    planned = Modules.prepareCrateResolution mode M.empty sources;
    resolution = bindEither planned (Modules.resolveCratePlan Modules.freshNames);
    result used compiled = Compilation compiled used;
    fallback = do {
      compiled <- Source.compileClosed Session.MemoryQueries mode sources;
      ioReturn (mapEither (result False) compiled)
    };
    prepared raw = do {
      admitted <- readLibraryObjects raw;
      case Core.atPhase Verification admitted of {
        Left err -> ioReturn (Left err);
        Right objects -> case nativeCrateInputsUsing Parser.parseModule raw mode loaded of {
          Left err -> ioReturn (Left err);
          Right ((,) own metadata) -> do {
            root <- Source.compile Session.MemoryQueries mode own metadata;
            ioReturn (mapEither (result True) (bindEither root (Source.close objects)))
          }
        }
      }
    }
  } in case candidates of {
    [] -> fallback;
    (:) raw _ -> case Core.atPhase ModuleResolution resolution of {
      Left err -> ioReturn (Left err);
      Right _ -> if collision raw sources then fallback else
        case bindEither planned (resolvePreparedPlan raw) of {
          Left _ -> fallback;
          Right resolved -> case validatePrepared raw resolved of {
            Left _ -> fallback;
            Right () -> prepared raw
          }
        }
    }
  }
}
