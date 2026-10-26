-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.PreparedCompiler
  (Compilation, compileFileWithPrelude, compileSourceWithImports, compileProgramWithPrelude,
   checkedTerm, compiledTerm, sourceType, reused, dictionaryIdentities, verifyBuiltin) where {
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
        loaded <- Modules.loadModuleFiles paths source;
        ioReturn (do {
          modules <- Core.atPhase ModuleResolution loaded;
          mapEither ordinary (Compiler.compileLinked mode modules)
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
