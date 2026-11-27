-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.PreparedCompiler
  (Source(..), readSource, Compilation, compileSource, compileFileWithPrelude, compileSourceWithImports, compileProgramWithPrelude,
   checkedTerm, compiledTerm, sourceType, reused, dictionaryIdentities, verifyBuiltin, verifyBuiltinImages, installCompilerPrelude, cratePrelude, linkCrateFile, linkCrateFileProfiled, linkCompiledCrate, linkCompiledCrateRetaining,
   emitNativeFileChunks, emitNativeSourceChunks, nativeInstallInfo,
   NativeCompilation, compileNative, compileNativeFile, compileNativeSource,
   nativeChunks, nativeManifest, nativeExportCount, nativeInlineCount, nativeFallback, nativeInputs,
   emitNativeLibraryChunks, nativeLibraryMetadata) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Host as Host;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Standalone as Standalone;
  import qualified Bootstrap.Prelude as Prelude;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Compiler as Compiler;
  import qualified Bootstrap.CompilerCore as Core;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.Crate as Crate;
  import qualified Bootstrap.CrateSession as Session;
  import qualified Bootstrap.CrateQuery as Query;
  import qualified Bootstrap.ArtifactStorage as Storage;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.ImportParameters as Parameters;
  import qualified Bootstrap.ImportedRoot as Imported;
  import qualified Bootstrap.BuiltinPreludeContext as Context;
  import qualified Bootstrap.BuiltinPreludeLiteral as Literal;
  import qualified MLF.BuiltinPreludeData as Builtin;
  import qualified Bootstrap.PreparedLibraries as Libraries;
  import qualified MLF.PreparedLibraryData as LibraryData;
  import qualified MLF.PreparedNativeData as NativeData;
  import qualified Bootstrap.LLVM as LLVM;
  import qualified Bootstrap.LLVM.Library as NativeLLVM;
  import qualified Bootstrap.Constraint as Constraint;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Package.Json as Json;
  import qualified Package.OS as OS;

  -- The native installation is compiler-owned immutable expected metadata.
  -- None of these checks accept a caller's manifest or its claimed digest.
  nativeExportABI :: String;
  nativeExportABI = "mlf-native-typed-tuple/2";
  fixedNativeLibrary :: Either String Libraries.RawLibrary;
  fixedNativeLibrary = case LibraryData.libraries of {
    -- Preserve manifest/identity demand here. Actual object admission belongs
    -- to the consumers: nativeLayout uses nativeLibraryDeclarations, emission
    -- uses nativeLibrary, and root compilation uses compileNativeRootUsing.
    [raw] -> Right raw;
    _ -> Left "native installation requires exactly one fixed prepared library"
  };
  nativeLayout :: Libraries.RawLibrary -> Either String NativeLLVM.ExportLayout;
  nativeLayout raw = do {
    installed <- Libraries.nativeInstalledIds raw;
    nativeLayoutFor raw installed
  };
  nativeLayoutFor raw bindings = do {
    ensure (eqList Separate.sameSignature (map snd bindings) (Libraries.nativeExportSignatures raw))
      "native declaration mapping differs from installed export keys or types";
    declarations <- Libraries.nativeLibraryDeclarations raw;
    base <- NativeLLVM.prepareLayoutIds (Libraries.inputIdentity raw)
      (map (\((,) d ((,) key ty)) -> (,) d ((,,) key (Constraint.targetNameHint key) ty)) bindings) declarations;
    NativeLLVM.withTypeNames base NativeData.reservedTypeNames
  };
  emitNativeLibraryChunks :: Either String ([] String);
  emitNativeLibraryChunks = do {
    raw <- fixedNativeLibrary;
    layout <- nativeLayout raw;
    checked <- Libraries.nativeLibrary raw;
    case checked of { (,,) spine _ _ -> NativeLLVM.emitLibrary layout spine }
  };
  nativeLibraryMetadata :: Either String String;
  nativeLibraryMetadata = do {
    raw <- fixedNativeLibrary;
    layout <- nativeLayout raw;
    let { exports = Libraries.nativeExportSignatures raw };
    declarations <- Libraries.nativeLibraryDeclarations raw;
    Right (Json.render (Json.object [
      (,) "format" (Json.str "MLF-NATIVE-LIBRARY-2"),
      (,) "identity" (Json.str (Libraries.inputIdentity raw)),
      (,) "export_abi" (Json.str nativeExportABI),
      (,) "runtime_abi" (Json.str LLVM.runtimeAbi),
      (,) "reserved_type_names" (Json.stringArray (NativeLLVM.reservedTypeNames layout)),
      (,) "exports" (Json.array (map (\((,) slot ((,) key ty)) -> Json.object [
        (,) "key" (Json.str key), (,) "hint" (Json.str (Constraint.targetNameHint key)),
        (,) "type" (Json.str (Pretty.prettyType ty)), (,) "slot" (Json.num slot)])
        (zip (range 0 (length exports - 1)) exports))),
      (,) "declarations" (Json.stringArray (map D.prettyDeclaration declarations)),
      (,) "constructor_tags" (Json.array (map (\((,) name ((,) tag arity)) -> Json.object [
        (,) "name" (Json.str name), (,) "tag" (Json.num tag), (,) "arity" (Json.num arity)])
        (M.toList (NativeLLVM.constructorTags layout))))
    ]))
  };
  checkNativeFile ((,) path expected) = do {
    present <- fileExists path;
    if not present then ioReturn (Left ("installed native file is missing: " ++ path)) else do {
      actual <- fileDigest path;
      ioReturn (ensure (eqString actual expected) ("installed native file digest mismatch: " ++ path))
    }
  };
  validateNativeFiles files = case files of {
    [] -> ioReturn (Right ());
    (:) entry rest -> do {
      result <- checkNativeFile entry;
      case result of { Left message -> ioReturn (Left message); Right () -> validateNativeFiles rest }
    }
  };
  nativeLinkInputs :: Json.Json -> Either String ([] ((,) String String));
  nativeLinkInputs manifest = do {
    arguments <- case Json.get "link_args" manifest of {
      Json.Array values -> traverseEither (\value -> case value of {
        Json.String argument -> do {
          ensure (eqString argument "-lm" || OS.absolute argument)
            "installed native link dependency must use an absolute path";
          Right argument
        };
        _ -> Left "invalid installed native link argument"
      }) values;
      _ -> Left "installed native link arguments are missing"
    };
    files <- case Json.get "link_inputs" manifest of {
      Json.Array values -> traverseEither (\value -> case value of {
        Json.Object _ -> case (,) (Json.get "path" value) (Json.get "sha256" value) of {
          (,) (Json.String path) (Json.String digest) -> do {
            ensure (OS.absolute path && stringLength digest == 64)
              "invalid installed native link input";
            Right ((,) path digest)
          };
          _ -> Left "invalid installed native link input"
        };
        _ -> Left "invalid installed native link input"
      }) values;
      _ -> Left "installed native link input inventory is missing"
    };
    let { paths = map fst files;
          dependencies = filter (\argument -> not (eqString argument "-lm")) arguments };
    ensure (length paths == length (nubBy eqString paths)) "duplicate installed native link input";
    ensure (eqList eqString (sortBy compareString paths) (sortBy compareString dependencies))
      "installed native link arguments differ from their authenticated input inventory";
    Right files
  };
  data InstalledNative = InstalledNative String Libraries.RawLibrary ([] String);
  installationManifest (InstalledNative text _ _) = text;
  nativeInstallInfo :: IO (Either String String);
  nativeInstallInfo = do {
    installed <- loadNativeInstallation;
    ioReturn (mapEither installationManifest installed)
  };
  loadNativeInstallation :: IO (Either String InstalledNative);
  loadNativeInstallation = if not NativeData.enabled then ioReturn (Left "native installation is disabled") else do {
    files <- validateNativeFiles ((:) ((,) NativeData.manifestPath NativeData.manifestSHA) NativeData.objectPaths);
    case files of {
      Left message -> ioReturn (Left message);
      Right () -> do {
        text <- readFile NativeData.manifestPath;
        afterRead <- fileDigest NativeData.manifestPath;
        let { inspected = do {
          ensure (eqString afterRead NativeData.manifestSHA) "installed native manifest changed while reading";
          raw <- fixedNativeLibrary;
          ensure (eqString NativeData.identity (Libraries.inputIdentity raw)) "installed native library identity mismatch";
          ensure (eqString NativeData.exportABI nativeExportABI) "installed native export ABI mismatch";
          ensure (not (null NativeData.objectPaths)) "installed native object inventory is empty";
          manifest <- Json.parse text;
          traverseEither (\((,) field expected) -> ensure
            (eqString (Json.getText field "" manifest) expected) ("installed native manifest mismatch: " ++ field))
            [(,) "identity" NativeData.identity, (,) "target_triple" NativeData.targetTriple,
             (,) "data_layout" NativeData.dataLayout, (,) "primitive_abi" NativeData.primitiveABI,
             (,) "export_abi" NativeData.exportABI, (,) "runtime_abi" LLVM.runtimeAbi];
          -- The compiled manifest hash binds the layout produced and checked
          -- during independent installation regeneration. Reconstructing the
          -- full export schema here repeats that proof on every invocation;
          -- user wrappers still undergo their own checked layout validation.
          ensure (eqString (Json.getText "format" "" manifest) "MLF-NATIVE-LIBRARY-2")
            "installed native manifest format mismatch";
          let { objectRows = Json.array (map (\((,) path digest) -> Json.object
            [(,) "path" (Json.str path), (,) "sha256" (Json.str digest)]) NativeData.objectPaths) };
          ensure (eqString (Json.render (Json.get "objects" manifest)) (Json.render objectRows))
            "installed native object inventory mismatch";
          linkInputs <- nativeLinkInputs manifest;
          Right ((,) (InstalledNative text raw (Json.getStrings "source_roots" manifest)) linkInputs)
        } };
        case inspected of {
          Left message -> ioReturn (Left message);
          Right ((,) installed linkInputs) -> do {
            valid <- validateNativeFiles linkInputs;
            ioReturn (mapEither (\_ -> installed) valid)
          }
        }
      }
    }
  };
  data NativeCompilation = NativeCompilation String ([] String) Int Int String ([] ((,) String String));
  nativeManifest (NativeCompilation manifest _ _ _ _ _) = manifest;
  nativeChunks (NativeCompilation _ chunks _ _ _ _) = chunks;
  nativeExportCount (NativeCompilation _ _ count _ _ _) = count;
  nativeInlineCount (NativeCompilation _ _ _ count _ _) = count;
  nativeFallback (NativeCompilation _ _ _ _ reason _) = reason;
  nativeInputs (NativeCompilation _ _ _ _ _ inputs) = inputs;
  compileNativeFile :: PreludeMode -> [] String -> String -> IO (Either CompileError NativeCompilation);
  compileNativeFile mode paths file = compileNative mode paths (SourceFile file);
  compileNativeSource :: PreludeMode -> [] String -> String -> String -> IO (Either CompileError NativeCompilation);
  compileNativeSource mode paths file input = compileNative mode paths (SourceText file input);
  compileNative :: PreludeMode -> [] String -> Source -> IO (Either CompileError NativeCompilation);
  compileNative mode paths source = withSource source (\input ->
    if not NativeData.enabled then ioReturn (Left (CompileError Verification
      "standard native installation is unavailable; build the compiler with tools/shared/build.py")) else do {
      installed <- loadNativeInstallation;
      case installed of {
        Left message -> ioReturn (Left (CompileError Verification message));
        Right dependency -> do {
          loaded <- loadSourceRoot paths (Just dependency) input;
          case loaded of {
            Left err@(CompileError ModuleResolution _) -> do {
              reportNativeFallback err;
              ioReturn (Left err)
            };
            Left err -> ioReturn (Left err);
            Right (SourceRoot _ graph) -> emitNativeRoot mode dependency graph
          }
        }
      }
    });
  reportNativeFallback err = putErr ("native library fallback: " ++ Core.prettyError err ++ "\n");
  emitNativeRoot mode (InstalledNative manifest raw _) graph = let {
    inputs = map (\entry -> (,) (Modules.sourcePath (Modules.loadedSource entry))
      (Modules.loadedText entry)) (Modules.loadedEntries graph);
    candidate = do {
      compiled <- Libraries.compileNativeRootUsing LibraryData.parseLibrary raw mode graph;
      layout <- Core.atPhase Verification (nativeLayoutFor raw (Libraries.nativeLayoutIds compiled));
      chunks <- Core.atPhase Verification (NativeLLVM.emitRootIds layout
        (Libraries.nativeSelectedIds compiled) (Libraries.nativeCheckedWrapper compiled));
      Right (NativeCompilation manifest chunks (length (M.keys (Libraries.nativeSignatures compiled)))
        (Libraries.nativeBuiltinCount compiled) "" inputs)
    }
  } in case candidate of {
    Right compiled -> ioReturn (Right compiled);
    Left err -> do {
      reportNativeFallback err;
      ioReturn (do {
        ordinary <- compileCheckedModules mode graph;
        chunks <- Core.atPhase Verification (LLVM.emitCheckedChunks False (checkedTerm ordinary));
        Right (NativeCompilation manifest chunks 0 0 (Core.prettyError err) inputs)
      })
    }
  };
  emitNativeFileChunks :: PreludeMode -> [] String -> String -> IO (Either CompileError ([] String));
  emitNativeFileChunks mode paths file = do {
    compiled <- compileNativeFile mode paths file;
    ioReturn (mapEither nativeChunks compiled)
  };
  emitNativeSourceChunks :: PreludeMode -> [] String -> String -> String -> IO (Either CompileError ([] String));
  emitNativeSourceChunks mode paths file input = do {
    compiled <- compileNativeSource mode paths file input;
    ioReturn (mapEither nativeChunks compiled)
  };

  -- A prepared root has no ordinary presolution graph for the linked library.
  -- Keep the checked result/source rendering in a distinct result wrapper.
  data Compilation = Compilation Checked.CheckedTerm String Bool (Map String String);
  checkedTerm (Compilation checked _ _ _) = checked;
  compiledTerm value = Checked.term (checkedTerm value);
  sourceType (Compilation _ rendered _ _) = rendered;
  reused (Compilation _ _ value _) = value;
  dictionaryIdentities (Compilation _ _ _ values) = values;
  ordinary compiled = Compilation (Core.checkedTerm compiled) (Core.sourceType compiled) False M.empty;
  original mode program = mapEither ordinary (Compiler.compileProgramWithPrelude mode program);
  prepared = Context.checkCompilerPrelude Builtin.builtin;
  cratePrelude = case prepared of { Right witness -> Just ((,) witness Builtin.builtinObject); Left _ -> Nothing };
  verifyBuiltinImages = case Artifact.builtinPrelude of {
    Left message -> ioReturn (Left message);
    Right object -> do {
      images <- Literal.imageTexts object;
      case images of {
        Left message -> ioReturn (Left message);
        Right ((,) meta unit) -> let {
          check encoded fields = do {
            expected <- decodeCompilerImage encoded;
            actual <- Literal.openCompilerImage fields;
            case (,) expected actual of {
              (,) (Right a) (Right b) -> Storage.sameBytes a b;
              _ -> ioReturn False
            }
          };
          error = "prepared Prelude binary images differ from fresh complete preparation"
        } in if not (eqString meta Builtin.interfaceImage && eqString unit Builtin.objectImage)
          then ioReturn (Left error) else do {
            iface <- check meta Builtin.interfaceOctets;
            body <- if iface then check unit Builtin.objectOctets else ioReturn False;
            ioReturn (ensure (iface && body) error)
          }
      }
    }
  };
  -- Only the fixed generator's physically verified images enter this route.
  -- The build compares both byte encodings against fresh ordinary preparation.
  -- At runtime a hit requires every byte of both bounded files to match.
  -- Caller-provided witnesses and differing installed formats use full admission.
  installCompilerPrelude prefix = let { fallback = \_ -> Crate.ensureBuiltinWith cratePrelude prefix } in
    case prepared of {
      Left _ -> fallback ();
      Right _ -> do {
        images <- compilerPreludeImages;
        case images of {
          Left _ -> fallback ();
          Right ((,) iface body) -> do {
            code <- Query.cacheCommand ["/bin/mkdir", "-p", Crate.parentDirectory prefix];
            if code /= 0 then ioReturn (Left "cannot create shared Prelude directory") else do {
              lock <- acquireFileLock (prefix ++ ".lock");
              result <- installedImages prefix iface body;
              releaseFileLock lock;
              case result of { Nothing -> fallback (); Just outcome -> ioReturn outcome }
            }
          }
        }
      }
    };
  compilerPreludeImages = do {
    first <- Literal.openCompilerImage Builtin.interfaceOctets;
    second <- Literal.openCompilerImage Builtin.objectOctets;
    ioReturn (do { meta <- first; body <- second; Right ((,) meta body) })
  };
  decodeCompilerImage text = if stringLength text > 2796204
    then ioReturn (Left "prepared Prelude binary image exceeds its limit") else Storage.decodeBase64 text;
  installedImages prefix iface body = do {
    let { metadata = prefix ++ ".mlfci"; executable = prefix ++ ".mlfco" };
    hasInterface <- fileExists metadata; hasObject <- fileExists executable;
    if not hasInterface && not hasObject then do {
      written <- Storage.writeRawAtomic executable body;
      case written of {
        Left message -> ioReturn (Just (Left message));
        Right () -> do {
          published <- Storage.writeRawAtomic metadata iface;
          ioReturn (Just (mapEither (\_ -> metadata) published))
        }
      }
    } else if not (hasInterface && hasObject) then ioReturn Nothing else do {
      sameInterface <- exactImage metadata iface;
      sameObject <- if sameInterface then exactImage executable body else ioReturn False;
      ioReturn (if sameInterface && sameObject then Just (Right metadata) else Nothing)
    }
  };
  exactImage = exactImageProfiled Nothing;
  exactImageProfiled profile path expected = Host.phaseIO profile "validate_ms" (do {
    limit <- lengthByteArray expected;
    acquired <- Host.phaseIO profile "read_ms" (readByteFileOrError path limit);
    case acquired of { (,) message bytes -> if eqString message ""
      then Storage.sameBytes bytes expected else ioReturn False }
  });
  -- The fixed literal is independently checked at runtime and both physical
  -- images are verified against fresh preparation by the producer build. A
  -- disk hit must match every byte, as installation does. All other artifacts
  -- retain ordinary admission, including the envelope's cumulative bounds.
  linkCrateFile = linkCrateFileProfiled Nothing;
  linkCrateFileProfiled profile = Artifact.linkCheckedFileUsing profile (admitLinkedPrelude profile);
  linkCompiledCrate = linkCompiledCrateRetaining M.empty;
  linkCompiledCrateRetaining :: Map String Artifact.CrateObject -> Session.CompiledCrate ->
    IO (Either String Checked.CheckedTerm);
  linkCompiledCrateRetaining retained compiled =
    Artifact.linkCheckedClosure Nothing (admitLinkedPrelude Nothing) retained
      (Session.compiledInterfaces compiled) (Just (Session.compiledObject compiled));
  admitLinkedPrelude profile metadata iface = do {
    checked <- Host.phaseValue profile "prelude_check_ms" (Host.phaseEither (\w -> seq w ())) prepared;
    case checked of {
      Left _ -> ioReturn Nothing;
      Right witness -> do {
        images <- Host.phaseIO profile "image_decode_ms" compilerPreludeImages;
        exact <- Host.phaseIO profile "validate_ms" (case images of {
          Left _ -> ioReturn False;
          Right ((,) header body) -> do {
            matches <- exactImageProfiled profile metadata header;
            matchesBody <- if matches then exactImageProfiled profile (Artifact.objectPath metadata) body
              else ioReturn False;
            ioReturn (matchesBody && Artifact.sameAdmittedInterface iface (Context.interface witness))
          }
        });
        ioReturn (if exact then Just (Artifact.linkCheckedObjectsV1Profiled profile
          (Context.finishLinked witness) (Context.linked witness) [Context.interface witness])
          else Nothing)
      }
    }
  };
  rawNames = case Builtin.builtin of { Context.RawPrelude _ _ _ _ _ _ value _ _ _ _ _ -> value };
  rawEnvironment = case Builtin.builtin of { Context.RawPrelude _ _ _ _ _ _ _ value _ _ _ _ -> value };
  rawProtected = case Builtin.builtin of { Context.RawPrelude _ _ _ _ _ _ _ _ _ value _ _ -> value };
  verifyBuiltin identity = do {
    ensure (eqString identity (Context.inputIdentity Builtin.builtin)) "prepared Prelude build source identity is stale";
    prepared;
    fresh <- Context.prepareFresh identity;
    ensure (eqString (Literal.rawPrelude fresh) (Literal.rawPrelude Builtin.builtin))
      "prepared Prelude differs from fresh complete preparation";
    object <- Artifact.builtinPrelude;
    ensure (eqString (Artifact.encodeObject object) Builtin.builtinObject)
      "prepared Prelude split object differs from fresh complete preparation"
  };
  data Source = SourceFile String | SourceText String String | SourceStdin;
  readSource :: Source -> IO (Either String ((,) String String));
  readSource source = case source of {
    SourceFile path -> do {
      present <- fileExists path;
      if present then do {
        input <- readFile path;
        ioReturn (Right ((,) path input))
      } else ioReturn (Left ("file does not exist: " ++ path))
    };
    SourceText path input -> ioReturn (Right ((,) path input));
    SourceStdin -> do {
      input <- getContents;
      ioReturn (Right ((,) "<stdin>" input))
    }
  };
  withSource :: forall a. Source -> (((,) String String) -> IO (Either CompileError a)) ->
    IO (Either CompileError a);
  withSource source use = do {
    result <- readSource source;
    case result of {
      Left message -> ioReturn (Left (CompileError ModuleResolution message));
      Right input -> use input
    }
  };
  data SourceRoot = SourceRoot SourceModule Modules.LoadedModules;
  -- The graph retains the exact buffers used to resolve imports. Both checked
  -- inference and native library admission consume that same closure.
  loadSourceRoot :: [] String -> Maybe InstalledNative -> (,) String String ->
    IO (Either CompileError SourceRoot);
  loadSourceRoot paths installed ((,) file input) =
    case Core.atPhase Parsing (Parser.parseModule file input) of {
      Left err -> ioReturn (Left err);
      Right root -> do {
        loaded <- case installed of {
          Nothing -> Modules.loadModuleFilesWithEvidenceUsing LibraryData.parseLibrary paths root input;
          Just (InstalledNative _ _ defaults) ->
            Modules.loadModuleFilesWithEvidenceUsingFallback LibraryData.parseLibrary paths defaults root input
        };
        ioReturn (mapEither (SourceRoot root) (Core.atPhase ModuleResolution loaded))
      }
    };
  compileFileWithPrelude mode paths file = compileSource mode paths (SourceFile file);
  compileSourceWithImports mode paths file input = compileSource mode paths (SourceText file input);
  compileSource :: PreludeMode -> [] String -> Source -> IO (Either CompileError Compilation);
  compileSource mode paths source = withSource source (\input -> do {
    loaded <- loadSourceRoot paths Nothing input;
    ioReturn (do {
      SourceRoot root graph <- loaded;
      if Compiler.standalone root then do {
        program <- Core.atPhase Parsing (Parser.standaloneProgram root);
        compileProgramWithPrelude mode program
      } else compileCheckedModules mode graph
    })
  });
  compileCheckedModules mode graph = do {
    result <- Libraries.compileLoaded LibraryData.libraries mode graph;
    Right (Compilation (Libraries.checkedTerm result) (Libraries.sourceType result)
      (Libraries.reused result) M.empty)
  };
  compileProgramWithPrelude mode program = case mode of {
    NoImplicitPrelude -> original mode program;
    ImplicitPrelude ->
      if collides rawProtected program then original mode program else
      case Standalone.rewriteRootWithNames mode rawNames rawEnvironment program of {
        -- Cheap admission uses fixed raw metadata only. Its rejection must not
        -- manufacture a user error before the current context is checked.
        Left _ -> original mode program;
        Right root -> if not (Standalone.rewrittenNeeded root) || ownSupportCollision rawProtected root
          then original mode program else do {
            context <- Core.atPhase Verification prepared;
            compilePrepared context root program
          }
      }
  };
  sourcePhase phase root result = Core.atPhase phase
    (mapLeft (Modules.displayNames (Standalone.rewrittenDisplay root)) result);
  finishImported root signatures = Compiler.finishWithSourceNames
    (Standalone.rewrittenDisplay root) (Imported.finishSelected signatures);
  -- Conservative namespace admission. Intrinsic tuple/list syntax does not
  -- declare a replaceable imported value. Other canonical-name occurrences
  -- may conservatively fall back, never count as installed-root successes.
  collides protected program = any (\name ->
    S.member compareString name protected &&
      not (D.sourceBuiltinType name || D.sourceBuiltinConstructor name)) (Standalone.programNames program);
  ownSupportNames root = case Prelude.programParts (Standalone.rewrittenProgram root) of {
    (,,,) _ classes _ _ -> concatMap (\klass -> append
      ((:) ("Dict_" ++ Modules.className klass) ((:) ("Make_" ++ Modules.className klass) []))
      (append (map (\method -> "select_" ++ fst method) (Modules.classMethods klass))
        (map (\i -> "super_" ++ Modules.className klass ++ "_" ++ showInt i)
          (range 0 (length (Modules.superclasses klass) - 1))))) classes
  };
  ownSupportCollision protected root = let {
    support = ownSupportNames root;
    used = S.union compareString protected (S.fromList compareString
      (append (Standalone.programNames (Standalone.rewrittenOriginal root))
        (Standalone.programNames (Standalone.rewrittenProgram root))))
  } in length support /= length (nubBy eqString support) ||
    any (\name -> S.member compareString name used) support;
  userInstanceNames used instances = fst (foldl (\((,) names index) _ ->
    case Modules.chooseName used "installedUserInstance" index of {
      (,) name next -> (,) (snoc names name) next
    }) ((,) [] 0) instances);
  compilePrepared context root program = do {
    let { iface = Context.interface context;
          linked = Context.linked context;
          sourceValues = Context.sourceValues context;
          protected = Context.protectedNames context };
        let {
          parts = Prelude.programParts (Standalone.rewrittenProgram root);
          ds = case parts of { (,,,) value _ _ _ -> value };
          cs = case parts of { (,,,) _ value _ _ -> value };
          instances = case parts of { (,,,) _ _ value _ -> value };
          body = case parts of { (,,,) _ _ _ value -> value };
          builtinData = Artifact.crateData iface;
          builtinClasses = Artifact.crateClasses iface;
          builtinInstances = Artifact.crateInstances iface;
          signatures = M.fromList compareString (Artifact.crateBindings iface);
          externals = Context.sourceExternals iface sourceValues;
          used = S.union compareString protected (S.fromList compareString (Standalone.programNames program));
          instanceNames = append (map fst builtinInstances) (userInstanceNames used instances)
        };
        -- Imported checked declarations are ABI CONTEXT, never rewrite input.
        (,) ownData ownClasses <- sourcePhase Inference root
          (Classes.canonicalSourceHeaders S.empty builtinData builtinClasses ds cs);
        fullLowered <- sourcePhase Inference root (Classes.lowerSeparateClasses externals instanceNames
          (SClassProgram (append builtinData ownData) (append builtinClasses ownClasses)
            (append (map snd builtinInstances) instances) body));
        selected <- Core.atPhase Verification
          (Parameters.selectNamed (Parameters.namedImports signatures) fullLowered);
        let { lowered = fst selected; selectedSignatures = Parameters.project (snd selected) };
        compiled <- finishImported root (snd selected) lowered;
        let {
          fresh = snd (Separate.freshObject (Artifact.fragmentSerial linked) (Checked.term (Imported.checkedWrapper compiled)));
          rootData = case fresh of { XWithData declarations _ -> declarations; _ -> [] }
        };
        actualRoot <- Core.atPhase Verification
          (Imported.remove selectedSignatures (Artifact.fragmentBindings linked) fresh);
        declarations <- Core.atPhase Verification
          (foldEither Separate.mergeDeclaration rootData (Artifact.fragmentData linked));
        Core.atPhase Verification (ensure (length declarations == length rootData)
          "prepared Prelude added an unowned datatype layout");
        grafted <- Core.atPhase Verification
          (foldEither (\rootBody declarationSpine -> Separate.graft declarationSpine rootBody)
            actualRoot (Artifact.fragmentBodies linked));
        checked <- Core.atPhase Verification (Checked.check (XWithData declarations grafted));
        Core.atPhase Verification (ensure (T.alphaEq (Checked.typeOf checked) (Imported.inferredType compiled))
          "installed Prelude graft changed actual root type");
        Right (Compilation checked (Modules.displayNames (Standalone.rewrittenDisplay root)
          (Imported.sourceType compiled)) True
          (M.map (Modules.displayNames (Standalone.rewrittenDisplay root)) (snd lowered)))
  }
}
