-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.PreparedCompiler
  (Compilation, compileFileWithPrelude, compileSourceWithImports, compileProgramWithPrelude,
   checkedTerm, compiledTerm, sourceType, reused, dictionaryIdentities, verifyBuiltin,
   emitNativeFileChunks, emitNativeSourceChunks, nativeInstallInfo,
   NativeCompilation, compileNativeFile, compileNativeSource,
   nativeChunks, nativeManifest, nativeExportCount, nativeInlineCount, nativeFallback, nativeInputs,
   emitNativeLibraryChunks, nativeLibraryMetadata) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
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
    [raw] -> Right raw;
    _ -> Left "native installation requires exactly one fixed prepared library"
  };
  nativeLayout :: Libraries.RawLibrary -> Either String NativeLLVM.ExportLayout;
  nativeLayout raw = do {
    declarations <- Libraries.nativeLibraryDeclarations raw;
    NativeLLVM.prepareLayoutWithTypeNames (Libraries.inputIdentity raw)
      (map (\((,) key ty) -> (,,) key (Constraint.targetNameHint key) ty)
        (Libraries.nativeExportSignatures raw)) declarations NativeData.reservedTypeNames
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
            layout <- Core.atPhase Verification (nativeLayout raw);
            chunks <- Core.atPhase Verification (NativeLLVM.emitRoot layout
              (M.keys (Libraries.nativeSignatures compiled)) (Libraries.nativeCheckedWrapper compiled));
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
  rawNames = case Builtin.builtin of { Context.RawPrelude _ _ _ _ _ _ value _ _ _ _ _ -> value };
  rawEnvironment = case Builtin.builtin of { Context.RawPrelude _ _ _ _ _ _ _ value _ _ _ _ -> value };
  rawProtected = case Builtin.builtin of { Context.RawPrelude _ _ _ _ _ _ _ _ _ value _ _ -> value };
  verifyBuiltin identity = do {
    ensure (eqString identity (Context.inputIdentity Builtin.builtin)) "prepared Prelude build source identity is stale";
    prepared;
    fresh <- Context.prepareFresh identity;
    ensure (eqString (Literal.rawPrelude fresh) (Literal.rawPrelude Builtin.builtin))
      "prepared Prelude differs from fresh complete preparation"
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
  finishImported root signatures lowered = let {
    display = Modules.displayNames (Standalone.rewrittenDisplay root);
    diagnosticNames = M.union compareString (M.map display (snd lowered))
      (Standalone.rewrittenDisplay root)
  } in case Imported.finishCompilation signatures lowered of {
    Left (CompileError phase message) -> Left (CompileError phase (Modules.displayNames diagnosticNames message));
    Right compiled -> Right compiled
  };
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
        ownData <- sourcePhase Inference root (D.canonicalSourceDeclarations builtinData ds);
        ownClasses <- sourcePhase Inference root (Classes.canonicalSourceClasses S.empty
          (append builtinData ownData) builtinClasses cs);
        fullLowered <- sourcePhase Inference root (Classes.lowerSeparateClasses externals instanceNames
          (SClassProgram (append builtinData ownData) (append builtinClasses ownClasses)
            (append (map snd builtinInstances) instances) body));
        selected <- Core.atPhase Verification
          (Parameters.select signatures fullLowered);
        let { lowered = fst selected; selectedSignatures = snd selected };
        compiled <- finishImported root selectedSignatures lowered;
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
