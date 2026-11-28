-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.PreparedCompiler
  (Source(..), readSource, Compilation, compileSource, compileSourceWithDecisions, compileSourceAndDecisions, compileFileWithPrelude, compileSourceWithImports,
   checkedTerm, compiledTerm, sourceType, reused, dictionaryIdentities, verifyBuiltin, verifyBuiltinImages, installCompilerPrelude, cratePrelude, linkCrateFile, linkCrateFileProfiled, linkCompiledCrate, linkCompiledCrateRetaining,
   emitNativeFileChunks, emitNativeSourceChunks, nativeInstallInfo,
   NativeCompilation, compileNative, compileNativeWithDecisions, compileNativeFile, compileNativeSource,
   NativeLink(..), nativeLink, nativeChunks, nativeManifest, nativeInstallation, nativeProviders, nativeFallback, nativeInputs, nativeDecisions,
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
  import qualified Bootstrap.SourceFrontend as Compiler;
  import qualified Bootstrap.CompilerCore as Core;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.Crate as Crate;
  import qualified Bootstrap.CrateCodegen as CrateCodegen;
  import qualified Bootstrap.CrateSession as Session;
  import qualified Bootstrap.SourceCrate as SourceCrate;
  import qualified Bootstrap.CrateQuery as Query;
  import qualified Bootstrap.ArtifactStorage as Storage;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.BuiltinPreludeContext as Context;
  import qualified Bootstrap.BuiltinPreludeLiteral as Literal;
  import qualified MLF.BuiltinPreludeData as Builtin;
  import qualified Bootstrap.PreparedLibraries as Libraries;
  import qualified MLF.PreparedLibraryData as LibraryData;
  import qualified MLF.PreparedNativeData as NativeData;
  import qualified Bootstrap.LLVM as LLVM;
  import qualified Bootstrap.NativeCrate as NativeCrate;
  import qualified MLF.CrateNativeCommand as NativeCommand;
  import qualified Package.NativeArtifact as NativeArtifact;
  import qualified Package.Json as Json;
  import qualified Package.DependencyMode as Mode;
  import qualified Package.OS as OS;

  -- Installation is an authenticated provider store. Its libraries use the
  -- same boxed crate contracts and factory emitter as package dependencies.
  nativeLibraryObjects :: Libraries.RawLibrary -> [] Libraries.LibraryObject;
  nativeLibraryObjects raw = filter (\entry -> not (eqString Artifact.builtinCrateIdentity
    (Artifact.crateId (Libraries.libraryInterface entry)))) (Libraries.libraryObjects raw);
  preparedNativeLibrary :: IO (Either String ((,) ([] String) NativeCrate.Contract));
  preparedNativeLibrary = case LibraryData.libraries of {
    [raw] -> do {
      admitted <- Libraries.readLibraryObjects raw;
      ioReturn (do {
        objects <- admitted;
        case nativeLibraryObjects raw of {
          [recorded] -> do {
            let { owner = Artifact.crateId (Libraries.libraryInterface recorded) };
            object <- maybe (Left "prepared native crate is missing") Right
              (find (\value -> eqString owner (Artifact.crateId (Artifact.objectInterface value))) objects);
            result <- NativeCrate.emitLibrary (Libraries.objectHash recorded)
              (map Artifact.objectInterface objects) object;
            result
          };
          _ -> Left "native library emission requires one crate; use the installation producer for a provider set"
        }
      })
    };
    _ -> ioReturn (Left "native library emission requires one prepared source inventory")
  };
  emitNativeLibraryChunks :: IO (Either String ([] String));
  emitNativeLibraryChunks = do {
    result <- preparedNativeLibrary;
    ioReturn (mapEither fst result)
  };
  nativeLibraryMetadata :: IO (Either String String);
  nativeLibraryMetadata = do {
    result <- preparedNativeLibrary;
    ioReturn (mapEither (compose Json.render (compose NativeCommand.nativeContract snd)) result)
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
  data NativeLink = NativeLink ([] ((,) String String)) ([] ((,) String String)) ([] String);
  readNativeLink :: Json.Json -> Either String NativeLink;
  readNativeLink manifest = do {
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
    Right (NativeLink NativeData.objectPaths files arguments)
  };
  nativeFileRecord :: Json.Json -> Either String ((,) String String);
  nativeFileRecord value = case (,) (Json.get "path" value) (Json.get "sha256" value) of {
    (,) (Json.String path) (Json.String digest) -> do {
      ensure (OS.absolute path && CrateCodegen.validDigest digest) "invalid installed native file record";
      Right ((,) path digest)
    };
    _ -> Left "invalid installed native file record"
  };
  data InstalledNative = InstalledNative String Json.Json (Either String Libraries.RawLibrary)
    NativeLink ([] NativeArtifact.Pinned);
  installationManifest (InstalledNative text _ _ _ _) = text;
  installationData (InstalledNative _ manifest _ _ _) = manifest;
  installationLibrary (InstalledNative _ _ raw _ _) = raw;
  installationPins (InstalledNative _ _ _ _ pins) = pins;
  nativeInstallInfo :: IO (Either String String);
  nativeInstallInfo = do {
    installed <- loadNativeInstallation;
    ioReturn (mapEither installationManifest installed)
  };
  installedProvider expected row = let {
    saved = Json.get "contract" row;
    owner = Json.getText "crate_id" "" saved;
    identity = Json.getText "identity" "" saved;
    checked = do {
      entries <- expected;
      ensure (any (\entry -> eqString owner
        (Artifact.crateId (Libraries.libraryInterface entry)) &&
        eqString identity (Libraries.objectHash entry)) entries)
        "installed native provider differs from its checked crate";
      ensure (eqString NativeData.exportABI NativeCrate.nativeABI) "installed native export ABI mismatch";
      contract <- NativeArtifact.validateContract LLVM.runtimeAbi owner identity saved;
      ensure (eqString (Json.getText "status" "" contract) "eligible")
        (Json.getText "reason" "native provider is unavailable" contract);
      file <- nativeFileRecord (Json.get "object" row);
      Right ((,) contract file)
    };
    pinned result = NativeArtifact.Pinned owner identity Nothing result
  } in case checked of {
    Left reason -> ioReturn (pinned (Left reason));
    Right ((,) contract file) -> do {
      valid <- checkNativeFile file;
      ioReturn (pinned (mapEither (\_ -> (,) contract file) valid))
    }
  };
  loadNativeInstallation :: IO (Either String InstalledNative);
  loadNativeInstallation = if not NativeData.enabled then ioReturn (Left "native installation is disabled") else do {
    files <- checkNativeFile ((,) NativeData.manifestPath NativeData.manifestSHA);
    case files of {
      Left message -> ioReturn (Left message);
      Right () -> do {
        text <- readFile NativeData.manifestPath;
        afterRead <- fileDigest NativeData.manifestPath;
        let { inspected = do {
          ensure (eqString afterRead NativeData.manifestSHA) "installed native manifest changed while reading";
          let { raw = case filter (\candidate -> eqString NativeData.identity (Libraries.inputIdentity candidate))
                  LibraryData.libraries of {
                  [candidate] -> Right candidate;
                  _ -> Left "installed native library identity mismatch"
                } };
          manifest <- Json.parse text;
          traverseEither (\((,) field expected) -> ensure
            (eqString (Json.getText field "" manifest) expected) ("installed native manifest mismatch: " ++ field))
            [(,) "format" "MLF-NATIVE-INSTALLATION-1", (,) "identity" NativeData.identity,
             (,) "target_triple" NativeData.targetTriple, (,) "data_layout" NativeData.dataLayout,
             (,) "primitive_abi" NativeData.primitiveABI, (,) "runtime_abi" LLVM.runtimeAbi,
             (,) "export_abi" NativeData.exportABI];
          rows <- case Json.get "providers" manifest of {
            Json.Array values -> Right values;
            _ -> Left "installed native provider inventory is missing"
          };
          runtime <- nativeFileRecord (Json.get "runtime" manifest);
          native <- traverseEither (compose nativeFileRecord (Json.get "object"))
            (filter (\row -> not (Json.equal (Json.get "object" row) Json.Null)) rows);
          let { objects = snoc native runtime;
                objectRows = Json.array (map (\((,) path digest) -> Json.object
                  [(,) "path" (Json.str path), (,) "sha256" (Json.str digest)]) objects) };
          ensure (eqList (eqPair eqString eqString) objects NativeData.objectPaths &&
            Json.equal (Json.get "objects" manifest) objectRows)
            "installed native object inventory mismatch";
          ensure (length objects == length (nubBy (eqPair eqString eqString) objects))
            "duplicate installed native object";
          NativeLink _ inputs flags <- readNativeLink manifest;
          Right ((,,,) raw manifest rows (NativeLink [runtime] inputs flags))
        } };
        case inspected of {
          Left message -> ioReturn (Left message);
          Right ((,,,) raw manifest rows link@(NativeLink runtime inputs _)) -> do {
            valid <- validateNativeFiles (append runtime inputs);
            case valid of {
              Left message -> ioReturn (Left message);
              Right () -> do {
                let { expected = mapEither Libraries.libraryObjects raw };
                pins <- mapM (installedProvider expected) rows;
                ioReturn (Right (InstalledNative text manifest raw link pins))
              }
            }
          }
        }
      }
    }
  };
  data NativeCompilation = NativeCompilation InstalledNative NativeCommand.Program String
    ([] ((,) String String)) ([] Mode.Decision);
  nativeLink (NativeCompilation (InstalledNative _ _ _ (NativeLink runtime inputs flags) _) program _ _ _) =
    NativeLink (append (map (\row -> (,) (Json.getText "path" "" row) (Json.getText "sha256" "" row))
      (NativeCommand.programObjects program)) runtime) inputs flags;
  nativeManifest (NativeCompilation installed _ _ _ _) = installationManifest installed;
  nativeInstallation (NativeCompilation installed _ _ _ _) = installationData installed;
  nativeChunks (NativeCompilation _ program _ _ _) = NativeCommand.programChunks program;
  nativeProviders (NativeCompilation _ program _ _ _) = NativeCommand.programObjects program;
  nativeFallback (NativeCompilation _ _ reason _ _) = reason;
  nativeInputs (NativeCompilation _ _ _ inputs _) = inputs;
  nativeDecisions (NativeCompilation _ _ _ _ rows) = rows;
  compileNativeFile :: PreludeMode -> [] String -> String -> IO (Either CompileError NativeCompilation);
  compileNativeFile mode paths file = compileNative mode paths (SourceFile file);
  compileNativeSource :: PreludeMode -> [] String -> String -> String -> IO (Either CompileError NativeCompilation);
  compileNativeSource mode paths file input = compileNative mode paths (SourceText file input);
  compileNative :: PreludeMode -> [] String -> Source -> IO (Either CompileError NativeCompilation);
  compileNative = compileNativeWithDecisions (\_ -> ioReturn ());
  compileNativeWithDecisions :: (Mode.Decision -> IO ()) -> PreludeMode -> [] String -> Source -> IO (Either CompileError NativeCompilation);
  compileNativeWithDecisions report mode paths source = withSource source (\input ->
    if not NativeData.enabled then ioReturn (Left (CompileError Verification
      "standard native installation is unavailable; build the compiler with tools/shared/build.py")) else do {
      installed <- loadNativeInstallation;
      case installed of {
        Left message -> ioReturn (Left (CompileError Verification message));
        Right dependency -> do {
          loaded <- loadSourceGraph paths (Just dependency) input;
          case loaded of {
            Left err@(CompileError ModuleResolution _) -> do {
              reportNativeFallback err;
              ioReturn (Left err)
            };
            Left err -> ioReturn (Left err);
            Right graph -> compileLoadedSource report source mode paths (Just dependency) graph (emitNativeRoot dependency graph)
          }
        }
      }
    });
  reportNativeFallback err = putErr ("native library fallback: " ++ Core.prettyError err ++ "\n");
  emitNativeRoot installed graph (CompiledRoot root dependencies admission input interfaces) = let {
    inputs = map (\entry -> (,) (Modules.sourcePath (Modules.loadedSource entry))
      (Modules.loadedText entry)) (Modules.loadedEntries graph);
    selected = do {
      verified <- Core.atPhase Verification (installationLibrary installed);
      raw <- admission;
      Core.atPhase Verification (ensure (eqString (Libraries.inputIdentity verified) (Libraries.inputIdentity raw))
        "selected checked library has no installed native provider");
      Right (installationPins installed)
    };
    pins = either (\_ -> []) id selected;
    sourceReason = either Core.prettyError (\_ -> "") selected;
    checkedObject object = (,) (Artifact.crateId (Artifact.objectInterface object)) (Right object);
    objects = case dependencies of {
      CheckedObjects values -> map checkedObject values;
      SourcePrelude object -> [checkedObject object];
      FixedPrelude witness -> [(,) Artifact.builtinCrateIdentity
        (Artifact.decodeObject (Context.interface witness) Builtin.builtinObject)];
      LibraryDependencies _ -> []
    };
    byCrate = M.fromList compareString objects;
    load ((,) owner why) = case dependencies of {
      LibraryDependencies raw -> case find
          (\entry -> eqString owner (Artifact.crateId (Libraries.libraryInterface entry)))
          (Libraries.libraryObjects raw) of {
        Nothing -> ioReturn (Left (owner ++ ": " ++ why ++ "; no checked implementation is available"));
        Just recorded -> Libraries.readLibraryObject (map snd interfaces) recorded
      };
      _ -> ioReturn (case M.lookup compareString owner byCrate of {
        Nothing -> Left (owner ++ ": " ++ why ++ "; no checked implementation is available");
        Just object -> object
      })
    };
    initial = Session.rootObject root;
    headers = (:) (Artifact.objectInterface initial) (map snd interfaces);
    reported row = case (,) dependencies row of {
      (,) (SourcePrelude _) (Mode.Decision owner Mode.CheckedIR _) ->
        if eqString owner Artifact.builtinCrateIdentity then Mode.Decision owner Mode.Source "compiled builtin Prelude" else row;
      _ -> row
    };
    rejected choices = mapMaybe (\row -> case row of {
      Mode.Decision owner Mode.CheckedIR why -> if any
        (\pin -> eqString owner (NativeArtifact.pinnedCrate pin)) pins then Just why else Nothing;
      _ -> Nothing
    }) choices
  } in do {
    emitted <- NativeCommand.emitDependencies pins headers load initial;
    ioReturn (do {
      program <- Core.atPhase Verification emitted;
      let { choices = map reported (NativeCommand.programDecisions program);
            reasons = rejected choices;
            fallback = if not (eqString sourceReason "") then sourceReason
              else case reasons of { [] -> ""; (:) reason _ -> reason };
            rows = append choices (sourceRows input sourceReason) };
      Right ((,) (NativeCompilation installed program fallback inputs rows) rows)
    })
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
  -- Keep the exact source buffers used for admission and native build receipts.
  loadSourceGraph :: [] String -> Maybe InstalledNative -> (,) String String ->
    IO (Either CompileError Modules.LoadedModules);
  loadSourceGraph paths installed ((,) file input) =
    case Core.atPhase Parsing (Parser.parseModule file input) of {
      Left err -> ioReturn (Left err);
      Right root -> do {
        loaded <- case installed of {
          Nothing -> Modules.loadModuleFilesWithEvidenceUsing LibraryData.parseLibrary paths root input;
          Just dependency -> Modules.loadModuleFilesWithEvidenceUsingFallback LibraryData.parseLibrary
            paths (Json.getStrings "source_roots" (installationData dependency)) root input
        };
        ioReturn (Core.atPhase ModuleResolution loaded)
      }
    };
  data RootSource = ModuleSources ([] SourceModule) | PreparedScript SourceModule Context.PreparedPrelude;
  data CheckedDependencies = CheckedObjects ([] Artifact.CrateObject) | FixedPrelude Context.PreparedPrelude | SourcePrelude Artifact.CrateObject | LibraryDependencies Libraries.RawLibrary;
  data RootPlan = RootPlan RootSource ([] ((,) String Artifact.CrateInterface))
    CheckedDependencies (Either CompileError Libraries.RawLibrary);
  data CompiledRoot = CompiledRoot Session.SourceRoot CheckedDependencies (Either CompileError Libraries.RawLibrary)
    RootSource ([] ((,) String Artifact.CrateInterface));
  builtinMetadata :: Artifact.CrateInterface -> [] ((,) String Artifact.CrateInterface);
  builtinMetadata iface = [(,) "/mlf/implicit-dependencies/builtin.mlfci" iface];
  closeSourceRoot :: CheckedDependencies -> Session.SourceRoot -> IO (Either CompileError SourceCrate.Compilation);
  closeSourceRoot dependencies root = case dependencies of {
    CheckedObjects objects -> ioReturn (SourceCrate.close objects root);
    SourcePrelude object -> ioReturn (SourceCrate.close [object] root);
    LibraryDependencies raw -> do {
      loaded <- Libraries.readLibraryObjects raw;
      ioReturn (bindEither (Core.atPhase Verification loaded) (\objects -> SourceCrate.close objects root))
    };
    FixedPrelude witness -> ioReturn (let { object = Session.rootObject root;
      iface = Artifact.objectInterface object } in if null (Artifact.crateDependencies iface)
      then SourceCrate.close [] root else do {
        checked <- Core.atPhase Verification (Artifact.linkCheckedObjectsV1Using
          (Context.finishLinked witness) (Context.linked witness) [Context.interface witness]
          [object] (Artifact.crateId iface));
        Right (SourceCrate.finish root checked)
      })
  };
  sourcePlan mode graph candidate = let {
    sources = Modules.loadedSources graph;
    ordinary err = if not (SourceCrate.needsBuiltin mode sources)
      then Right (RootPlan (ModuleSources sources) [] (CheckedObjects []) (Left err)) else case prepared of {
        Right witness -> Right (RootPlan (ModuleSources sources) (builtinMetadata (Context.interface witness))
          (FixedPrelude witness) (Left err));
        Left _ -> do {
          object <- Core.atPhase Verification Artifact.builtinPrelude;
          Right (RootPlan (ModuleSources sources) (builtinMetadata (Artifact.objectInterface object))
            (SourcePrelude object) (Left err))
        }
      };
    select selection = case selection of {
      Left err -> ordinary err;
      Right raw -> do {
        (,) own interfaces <- Libraries.nativeCrateInputsUsing LibraryData.parseLibrary raw mode graph;
        Right (RootPlan (ModuleSources own) interfaces
          (LibraryDependencies raw) (Right raw))
      }
    }
  } in do {
    plan <- select candidate;
    case plan of {
      RootPlan (ModuleSources [source]) interfaces _ admission ->
        if not (Compiler.standalone source) then Right plan else do {
          program <- Core.atPhase Parsing (Parser.standaloneProgram source);
          let { lexical = RootPlan (ModuleSources [source]) [] (CheckedObjects []) admission };
          case preparedScriptRoot mode program of {
            Nothing -> Right lexical;
            Just _ -> case prepared of {
              Left _ -> Right lexical;
              Right witness -> let { iface = Context.interface witness;
                compatible = case admission of {
                  Left _ -> True;
                  Right _ -> any (compose (Artifact.sameAdmittedInterface iface) snd) interfaces
                } } in if compatible then Right (RootPlan (PreparedScript source witness)
                  (builtinMetadata iface) (FixedPrelude witness) admission) else Right lexical
            }
          }
        };
      _ -> Right plan
    }
  };
  sourceStorage source mode paths defaults interfaces = case source of {
    SourceFile file -> do {
      path <- canonicalPath file;
      cwd <- canonicalPath ".";
      override <- getEnv "MLF_SOURCE_CACHE_DIR";
      let { prelude = case mode of { ImplicitPrelude -> "implicit"; NoImplicitPrelude -> "explicit" };
            dependencies = map (\((,) label iface) -> Separate.pack
              [label, Artifact.crateId iface, Artifact.semanticFingerprint iface]) interfaces };
      scope <- Query.sourceInputHash (Separate.pack [cwd, path, file, prelude,
        Separate.pack paths, Separate.pack defaults, Separate.pack dependencies]);
      let { useDefault = eqString override "";
            base = if useDefault then ".mlf-build/cache/source-roots" else override;
            directory = OS.join (OS.join cwd base) scope };
      ioReturn (if useDefault then Session.DefaultFileQueries directory else Session.FileQueries directory)
    };
    _ -> ioReturn Session.MemoryQueries
  };
  rootSources input = case input of { ModuleSources sources -> sources; PreparedScript script _ -> [script] };
  sourceRows input rejected = let { sources = rootSources input; root = Modules.moduleIdentity (last sources) } in
    map (\item -> let { name = Modules.moduleIdentity item } in Mode.Decision name Mode.Source
      (if eqString name root then "root input" else if eqString rejected "" then "local source input" else rejected)) sources;
  dependencyModes graph (CompiledRoot root dependencies admission input interfaces) nativeKeys reason = let {
    sourceReason = case admission of {
      Left (CompileError Verification "no installed checked library") -> "no admitted dependency artifact";
      Left err -> Core.prettyError err;
      Right _ -> "no admitted dependency artifact"
    };
    loaded = S.fromList compareString (map Modules.moduleIdentity (Modules.loadedSources graph));
    direct = map Artifact.dependencyId (Artifact.crateDependencies (Artifact.objectInterface (Session.rootObject root)));
    choose ((,) _ iface) = let {
      name = Artifact.crateId iface;
      native = any (\binding -> M.member compareString (fst binding) nativeKeys) (Artifact.crateBindings iface);
      present = any (\value -> S.member compareString value loaded) (Artifact.crateModules iface);
      irReason = if eqString reason "" then "checked dependency" else reason
    } in if native then [Mode.Decision name Mode.Native "linked exports"]
      else if elem eqString name direct && (present || eqString name Artifact.builtinCrateIdentity)
        then case dependencies of {
          SourcePrelude _ -> [Mode.Decision name Mode.Source "compiled builtin Prelude"];
          _ -> [Mode.Decision name Mode.CheckedIR irReason]
        } else []
  } in append (concatMap choose interfaces) (sourceRows input sourceReason);
  compileLoadedSource :: forall a. (Mode.Decision -> IO ()) -> Source -> PreludeMode -> [] String -> Maybe InstalledNative -> Modules.LoadedModules ->
    (CompiledRoot -> IO (Either CompileError ((,) a ([] Mode.Decision)))) -> IO (Either CompileError a);
  compileLoadedSource report source mode paths installed graph use = let {
    loaded = S.fromList compareString (map Modules.moduleIdentity (Modules.loadedSources graph));
    relevant raw = any (\entry -> S.member compareString (Libraries.sourceName entry) loaded)
      (Libraries.librarySources raw);
    preferred raw = case installed of {
      Nothing -> False;
      Just _ -> eqString (Libraries.inputIdentity raw) NativeData.identity
    };
    sorted = sortBy (\a b -> compareInt (length (Libraries.librarySources b))
      (length (Libraries.librarySources a))) LibraryData.libraries;
    candidates = append (filter preferred sorted) (filter (\raw -> not (preferred raw) && relevant raw) sorted);
    defaults = case installed of {
      Nothing -> [];
      Just dependency -> Json.getStrings "source_roots" (installationData dependency)
    };
    attempt remaining reason = let {
      selection = case remaining of { [] -> Left reason; (:) raw _ -> Right raw };
      next err = case remaining of { [] -> ioReturn (Left err); (:) _ rest -> attempt rest err }
    } in case sourcePlan mode graph selection of {
      Left err -> next err;
      Right (RootPlan input interfaces dependencies admission) -> do {
        storage <- sourceStorage source mode paths defaults interfaces;
        compiled <- case input of {
          ModuleSources sources -> SourceCrate.compile storage mode sources interfaces;
          PreparedScript script witness -> SourceCrate.compileScriptWith storage script interfaces
            (lowerPreparedScript mode witness)
        };
        case compiled of {
          Left err -> case (,) err remaining of {
            (,) (CompileError Verification _) ((:) _ _) -> next err;
            _ -> do { mapM_ report (sourceRows input "no admitted dependency artifact"); ioReturn (Left err) }
          };
          Right root -> do {
            used <- use (CompiledRoot root dependencies admission input interfaces);
            case used of {
              Left err -> next err;
              Right ((,) result rows) -> do { mapM_ report rows; ioReturn (Right result) }
            }
          }
        }
      }
    }
  } in attempt candidates (CompileError Verification "no installed checked library");
  compileFileWithPrelude mode paths file = compileSource mode paths (SourceFile file);
  compileSourceWithImports mode paths file input = compileSource mode paths (SourceText file input);
  compileSource :: PreludeMode -> [] String -> Source -> IO (Either CompileError Compilation);
  compileSource = compileSourceWithDecisions (\_ -> ioReturn ());
  compileSourceWithDecisions :: (Mode.Decision -> IO ()) -> PreludeMode -> [] String -> Source -> IO (Either CompileError Compilation);
  compileSourceWithDecisions report = compileSourceResult report (\value _ -> value);
  compileSourceAndDecisions :: PreludeMode -> [] String -> Source -> IO (Either CompileError ((,) Compilation ([] Mode.Decision)));
  compileSourceAndDecisions = compileSourceResult (\_ -> ioReturn ()) (,);
  compileSourceResult report result mode paths source = withSource source (\input -> do {
    loaded <- loadSourceGraph paths Nothing input;
    case loaded of {
      Left err -> ioReturn (Left err);
      Right graph -> compileLoadedSource report source mode paths Nothing graph
        (\compiled@(CompiledRoot root dependencies _ _ _) -> do {
          linked <- closeSourceRoot dependencies root;
          ioReturn (do {
            closed <- linked;
            let { usesDependencies = not (null (Artifact.crateDependencies
                    (Artifact.objectInterface (Session.rootObject root)))) };
            let { value = Compilation (SourceCrate.checkedTerm closed) (SourceCrate.sourceType closed)
                    usesDependencies (SourceCrate.dictionaryIdentities closed);
                  decisions = dependencyModes graph compiled M.empty "" };
            Right ((,) (result value decisions) decisions)
          })
        })
    }
  });
  preparedScriptRoot mode program = case mode of {
    NoImplicitPrelude -> Nothing;
    ImplicitPrelude -> if collides rawProtected program then Nothing else
      case Standalone.rewriteRootWithNames mode rawNames rawEnvironment program of {
        Right root -> if Standalone.rewrittenNeeded root && not (ownSupportCollision rawProtected root)
          then Just root else Nothing;
        Left _ -> Nothing
      }
  };
  lowerPreparedScript mode witness program = do {
    root <- Core.atPhase ModuleResolution (Standalone.rewriteRootWithNames mode rawNames rawEnvironment program);
    (,) headers lowered <- lowerPrepared witness root program;
    Right ((,,) (Standalone.rewrittenDisplay root) (Just headers) lowered)
  };
  sourcePhase phase root result = Core.atPhase phase
    (mapLeft (Modules.displayNames (Standalone.rewrittenDisplay root)) result);
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
  lowerPrepared context root program = do {
    let { iface = Context.interface context;
          parts = Prelude.programParts (Standalone.rewrittenProgram root);
          ds = case parts of { (,,,) value _ _ _ -> value };
          cs = case parts of { (,,,) _ value _ _ -> value };
          instances = case parts of { (,,,) _ _ value _ -> value };
          body = case parts of { (,,,) _ _ _ value -> value };
          builtinData = Artifact.crateData iface;
          builtinClasses = Artifact.crateClasses iface;
          builtinInstances = Artifact.crateInstances iface;
          externals = Context.sourceExternals iface (Context.sourceValues context);
          used = S.union compareString (Context.protectedNames context)
            (S.fromList compareString (Standalone.programNames program));
          instanceNames = append (map fst builtinInstances) (userInstanceNames used instances)
        };
    (,) ownData ownClasses <- sourcePhase Inference root
      (Classes.canonicalSourceHeaders S.empty builtinData builtinClasses ds cs);
    lowered <- sourcePhase Inference root (Classes.lowerSeparateClasses externals instanceNames
      (SClassProgram (append builtinData ownData) (append builtinClasses ownClasses)
        (append (map snd builtinInstances) instances) body));
    Right ((,) ((,) ownData ownClasses) lowered)
  }
}
