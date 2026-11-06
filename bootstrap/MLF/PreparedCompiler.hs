-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.PreparedCompiler
  (Compilation, compileFileWithPrelude, compileSourceWithImports, compileProgramWithPrelude,
   checkedTerm, compiledTerm, sourceType, reused, dictionaryIdentities, verifyBuiltin, verifyBuiltinImages, installCompilerPrelude, cratePrelude,
   emitNativeFileChunks, emitNativeSourceChunks, nativeInstallInfo,
   NativeCompilation, compileNativeFile, compileNativeSource,
   nativeChunks, nativeManifest, nativeExportCount, nativeInlineCount, nativeFallback, nativeInputs,
   emitNativeLibraryChunks, nativeLibraryMetadata) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Compiler as Compiler;
  import qualified Bootstrap.CompilerCore as Core;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.Crate as Crate;
  import qualified Bootstrap.CrateQuery as Query;
  import qualified Bootstrap.ArtifactStorage as Storage;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.BuiltinPreludeContext as Context;
  import qualified Bootstrap.PreparedStandalone as PreparedStandalone;
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
      (,) "format" (Json.str "MLF-NATIVE-LIBRARY-1"),
      (,) "identity" (Json.str (Libraries.inputIdentity raw)),
      (,) "export_abi" (Json.str nativeExportABI),
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
  nativeInstallInfo :: IO (Either String String);
  nativeInstallInfo = if not NativeData.enabled then ioReturn (Left "native installation is disabled") else do {
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
             (,) "export_abi" NativeData.exportABI];
          -- The compiled manifest hash binds the layout produced and checked
          -- during independent installation regeneration. Reconstructing the
          -- full export schema here repeats that proof on every invocation;
          -- user wrappers still undergo their own checked layout validation.
          ensure (eqString (Json.getText "format" "" manifest) "MLF-NATIVE-LIBRARY-1")
            "installed native manifest format mismatch";
          let { objectRows = Json.array (map (\((,) path digest) -> Json.object
            [(,) "path" (Json.str path), (,) "sha256" (Json.str digest)]) NativeData.objectPaths) };
          ensure (eqString (Json.render (Json.get "objects" manifest)) (Json.render objectRows))
            "installed native object inventory mismatch";
          nativeLinkInputs manifest
        } };
        case inspected of {
          Left message -> ioReturn (Left message);
          Right linkInputs -> do {
            valid <- validateNativeFiles linkInputs;
            ioReturn (mapEither (\_ -> text) valid)
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
  compileNativeFile mode paths file = do {
    present <- fileExists file;
    if not present then ioReturn (Left (CompileError ModuleResolution ("file does not exist: " ++ file))) else do {
      input <- readFile file;
      compileNativeSource mode paths file input
    }
  };
  compileNativeSource :: PreludeMode -> [] String -> String -> String -> IO (Either CompileError NativeCompilation);
  compileNativeSource mode paths file input =
    if not NativeData.enabled then ioReturn (Left (CompileError Verification
      "standard native installation is unavailable; build the compiler with tools/shared/build.py")) else do {
    installed <- nativeInstallInfo;
    case installed of {
      Left message -> ioReturn (Left (CompileError Verification message));
      Right manifest -> case Core.atPhase Parsing (Parser.parseModule file input) of {
        Left error -> ioReturn (Left error);
        Right root -> do {
          let { defaults = case Json.parse manifest of {
            Left _ -> [];
            Right value -> Json.getStrings "source_roots" value
          } };
          loaded <- Modules.loadModuleFilesWithEvidenceUsingFallback LibraryData.parseLibrary paths defaults root input;
          let { candidate = do {
            graph <- Core.atPhase ModuleResolution loaded;
            raw <- Core.atPhase Verification fixedNativeLibrary;
            compiled <- Libraries.compileNativeRootUsing LibraryData.parseLibrary raw mode graph;
            layout <- Core.atPhase Verification (nativeLayoutFor raw (Libraries.nativeLayoutIds compiled));
            chunks <- Core.atPhase Verification (NativeLLVM.emitRootIds layout
              (Libraries.nativeSelectedIds compiled) (Libraries.nativeCheckedWrapper compiled));
            Right (NativeCompilation manifest chunks (length (M.keys (Libraries.nativeSignatures compiled)))
              (Libraries.nativeBuiltinCount compiled) ""
              (map (\entry -> (,) (Modules.sourcePath (Modules.loadedSource entry))
                (Modules.loadedText entry)) (Modules.loadedEntries graph)))
          } };
          case candidate of {
            Left error -> do {
              putErr ("native library fallback: " ++ Core.prettyError error ++ "\n");
              ioReturn (do {
                graph <- Core.atPhase ModuleResolution loaded;
                ordinary <- Libraries.compileLoaded LibraryData.libraries mode graph;
                chunks <- Core.atPhase Verification (LLVM.emitCheckedChunks False (Libraries.checkedTerm ordinary));
                Right (NativeCompilation manifest chunks 0 0 (Core.prettyError error)
                  (map (\entry -> (,) (Modules.sourcePath (Modules.loadedSource entry))
                    (Modules.loadedText entry)) (Modules.loadedEntries graph)))
              })
            };
            Right compiled -> ioReturn (Right compiled)
          }
        }
      }
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
      ioReturn (do {
        pair <- images;
        ensure (eqString (fst pair) Builtin.interfaceImage && eqString (snd pair) Builtin.objectImage)
          "prepared Prelude binary images differ from fresh complete preparation"
      })
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
    first <- decodeCompilerImage Builtin.interfaceImage; second <- decodeCompilerImage Builtin.objectImage;
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
  exactImage path expected = do {
    limit <- lengthByteArray expected;
    acquired <- readByteFileOrError path limit;
    case acquired of { (,) message bytes -> if eqString message ""
      then Storage.sameBytes bytes expected else ioReturn False }
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
  compileFileWithPrelude mode paths file = do {
    present <- fileExists file;
    if present then do {
      input <- readFile file;
      compileSourceWithImports mode paths file input
    } else ioReturn (Left (CompileError ModuleResolution ("file does not exist: " ++ file)))
  };
  compileSourceWithImports mode paths file input =
    case Core.atPhase Parsing (Parser.parseModule file input) of {
      Left error -> ioReturn (Left error);
      Right source -> if Compiler.standalone source then ioReturn (do {
        program <- Core.atPhase Parsing (Parser.standaloneProgram source);
        compileProgramWithPrelude mode program
      }) else do {
        loaded <- Modules.loadModuleFilesWithEvidenceUsing LibraryData.parseLibrary paths source input;
        ioReturn (do {
          modules <- Core.atPhase ModuleResolution loaded;
          result <- Libraries.compileLoaded LibraryData.libraries mode modules;
          Right (Compilation (Libraries.checkedTerm result) (Libraries.sourceType result)
            (Libraries.reused result) M.empty)
        })
      }
    };
  compileProgramWithPrelude mode program =
    case PreparedStandalone.admitRoot mode rawNames rawEnvironment rawProtected program of {
      Nothing -> original mode program;
      Just root -> do {
        context <- Core.atPhase Verification prepared;
        result <- PreparedStandalone.compileChecked context root program;
        case result of { (,,) checked source names -> Right (Compilation checked source True names) }
      }
    }
}
