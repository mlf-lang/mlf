-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.InstalledPreludeWholeRoot
  (InstalledPrelude, WholeRootOutcome, restoreVerified, snapshot, compileInstalledRoot,
   checkedTerm, reused, routeReason, rawRootCompilation, rootDictionaryMap) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Module as Modules;
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

  -- Conditional pure boundary. The opt-in supervisor verifies an externally
  -- pinned descriptor (compiler/source/ABI/schema plus both content SHA256s),
  -- reads each byte stream once and passes precisely those bytes here. This
  -- comparison is NOT a replacement for that cryptographic verification.
  data InstalledPrelude = InstalledPrelude String Artifact.CrateInterface
    Artifact.FragmentState Modules.Names Modules.Interface (Set String) (Set String);
  data WholeRootOutcome = OriginalFallback String Core.Compilation |
    InstalledRoot Checked.CheckedTerm Core.Compilation (Map String String) Standalone.RewrittenRoot;
  checkedTerm outcome = case outcome of {
    OriginalFallback _ compiled -> Core.checkedTerm compiled;
    InstalledRoot checked _ _ _ -> checked
  };
  reused outcome = case outcome of { OriginalFallback _ _ -> False; InstalledRoot _ _ _ _ -> True };
  routeReason outcome = case outcome of {
    OriginalFallback reason _ -> reason;
    InstalledRoot _ _ _ _ -> "authenticated full builtin; whole-root inference and checked graft"
  };
  -- Actual user-root inference with checked import parameters, not a fabricated
  -- grafted Compilation or proof of baseline principal-scheme equivalence.
  rawRootCompilation outcome = case outcome of {
    OriginalFallback _ compiled -> compiled;
    InstalledRoot _ compiled _ _ -> compiled
  };
  rootDictionaryMap outcome = case outcome of {
    OriginalFallback _ _ -> M.empty;
    InstalledRoot _ _ names _ -> names
  };
  sameEntity a b = Modules.compareEntity a b == 0;
  intrinsic entity = elem sameEntity entity Modules.sharedPrimitiveEntities;
  callStackEntity = Modules.Entity "MLF.Primitive" "callStack" Modules.Value;
  snapshot = do {
    object <- Artifact.builtinPrelude;
    Right ((,) (Artifact.encodeInterface (Artifact.objectInterface object)) (Artifact.encodeObject object))
  };
  restoreVerified :: String -> String -> String -> String -> Either String InstalledPrelude;
  restoreVerified expectedDescriptor actualDescriptor metadata bytes = do {
    ensure (not (eqString expectedDescriptor "") && eqString expectedDescriptor actualDescriptor)
      "installed Prelude trusted descriptor mismatch";
    iface <- Artifact.decodeInterface metadata;
    Artifact.validateInterface iface;
    ensure (eqString (Artifact.crateId iface) Artifact.builtinCrateIdentity)
      "installed Prelude is not the builtin crate";
    ensure (null (Artifact.crateDependencies iface) && eqString (Artifact.crateEntry iface) "")
      "installed Prelude must have no dependencies or executable entry";
    object <- Artifact.decodeObject iface bytes;
    let { byName = Artifact.interfaceMap ((:) iface []) };
    Artifact.validateDependencies byName iface;
    Artifact.validateExportBoundary byName iface;
    Artifact.validateLayouts ((:) iface []);
    let { layouts = M.fromList compareString (map (\d -> (,) (D.datatypeName d) (Artifact.datatypePart d))
          (Artifact.crateLoweredData iface)) };
    linked <- Artifact.linkCrate byName layouts (Artifact.FragmentState 0 M.empty [] [] S.empty) object;
    -- EXACT original standalone visible environment, not full crate exports.
    declared <- Modules.locals Modules.primitiveSource;
    let {
      env = Modules.union declared (Modules.interface Modules.sharedPrimitiveEntities);
      entities = S.toList (Modules.visible env);
      exports = concatMap snd (Artifact.crateExports iface);
      nameOf = Artifact.definitionName Artifact.builtinCrateIdentity;
      names = Modules.Names (M.fromList Modules.compareEntity (map (\e -> (,) e (nameOf e)) entities));
      sourceValues = S.fromList compareString
        (map nameOf (filter (\e -> Modules.isRole Modules.Value e && not (sameEntity e callStackEntity)) entities));
      sourceData = Artifact.crateData iface;
      loweredData = Artifact.crateLoweredData iface;
      classes = Artifact.crateClasses iface;
      protectedNames = S.fromList compareString (append (map fst (Artifact.crateBindings iface))
        (append (map fst (Artifact.crateInstances iface))
          (append (concatMap (\d -> (:) (D.datatypeName d) (map D.constructorName (D.datatypeConstructors d)))
                    (append sourceData loweredData))
            (append (map Modules.className classes) (concatMap (\c -> map fst (Modules.classMethods c)) classes)))))
    };
    -- Names follow the existing separate-lowering rule, never a displayed
    -- class spelling. Exact root-generated layout equality is checked again
    -- by mergeDeclaration after lowering, before the final independent check.
    traverseEither (\klass -> ensure
      (elem eqString ("Dict_" ++ Modules.className klass) (map D.datatypeName loweredData))
      ("installed Prelude missing authenticated dictionary layout: " ++ Modules.className klass)) classes;
    traverseEither (\entity -> do {
      ensure (intrinsic entity || elem sameEntity entity exports)
        ("installed Prelude lacks exact visible Entity: " ++ Modules.label entity);
      case Modules.role entity of {
        Modules.Value -> ensure (sameEntity entity callStackEntity ||
          elem eqString (nameOf entity) (map fst (Artifact.crateBindings iface)))
          ("installed Prelude missing value signature: " ++ Modules.label entity);
        Modules.Class -> ensure (elem eqString (nameOf entity) (map Modules.className classes))
          ("installed Prelude missing class identity: " ++ Modules.label entity);
        Modules.Method _ -> ensure (elem eqString (nameOf entity) (concatMap (\c -> map fst (Modules.classMethods c)) classes))
          ("installed Prelude missing method identity: " ++ Modules.label entity);
        Modules.Datatype -> ensure (elem eqString (nameOf entity) (map D.datatypeName sourceData))
          ("installed Prelude missing datatype identity: " ++ Modules.label entity);
        Modules.Constructor _ -> ensure (elem eqString (nameOf entity) (concatMap (\d -> map D.constructorName (D.datatypeConstructors d)) sourceData))
          ("installed Prelude missing constructor identity: " ++ Modules.label entity);
        _ -> ensure (intrinsic entity) "unsupported installed Prelude intrinsic Entity"
      }
    }) entities;
    Right (InstalledPrelude actualDescriptor iface linked names env sourceValues protectedNames)
  };
  sourcePhase phase root result = Core.atPhase phase
    (mapLeft (Modules.displayNames (Standalone.rewrittenDisplay root)) result);
  finishRoot root lowered = let {
    display = Modules.displayNames (Standalone.rewrittenDisplay root);
    diagnosticNames = M.union compareString (M.map display (snd lowered))
      (Standalone.rewrittenDisplay root)
  } in case Core.finishCompilation lowered of {
    Left (CompileError phase message) -> Left (CompileError phase (Modules.displayNames diagnosticNames message));
    Right compiled -> Right compiled
  };
  original reason mode program = mapEither (OriginalFallback reason) (Compiler.compileProgramWithPrelude mode program);
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
  compileInstalledRoot :: InstalledPrelude -> PreludeMode -> SProgram -> Either CompileError WholeRootOutcome;
  compileInstalledRoot (InstalledPrelude _ iface linked names env sourceValues protected) mode program =
    if collides protected program then original "canonical installed identifier collision" mode program
    else do {
      root <- Core.atPhase ModuleResolution (Standalone.rewriteRootWithNames mode names env program);
      if not (Standalone.rewrittenNeeded root) then original "no facade use; unchanged pure route" mode program
      else if ownSupportCollision protected root then original "own class stable support collision" mode program
      else do {
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
          dictionaries = M.fromList compareString
            (map (\c -> (,) ("Dict_" ++ Classes.className c) (Classes.className c)) builtinClasses);
          externals = M.mapWithKey (\name ty ->
            if S.member compareString name sourceValues then Separate.sourceScheme dictionaries ty
            else Separate.sourceSchemeIn M.empty False ty) signatures;
          used = S.union compareString protected (S.fromList compareString (Standalone.programNames program));
          instanceNames = append (map fst builtinInstances) (userInstanceNames used instances)
        };
        -- Imported checked declarations are ABI CONTEXT, never rewrite input.
        ownData <- sourcePhase Inference root (D.canonicalSourceDeclarations builtinData ds);
        ownClasses <- sourcePhase Inference root (Classes.canonicalSourceClasses S.empty
          (append builtinData ownData) builtinClasses cs);
        lowered <- sourcePhase Inference root (Classes.lowerSeparateClasses externals instanceNames
          (SClassProgram (append builtinData ownData) (append builtinClasses ownClasses)
            (append (map snd builtinInstances) instances) body));
        compiled <- finishRoot root lowered;
        let {
          fresh = snd (Separate.freshObject (Artifact.fragmentSerial linked) (Core.compiledTerm compiled));
          rootData = case fresh of { XWithData declarations _ -> declarations; _ -> [] }
        };
        actualRoot <- Core.atPhase Verification (Separate.removeEntryParameters signatures (Artifact.fragmentBindings linked) fresh);
        declarations <- Core.atPhase Verification
          (foldEither Separate.mergeDeclaration (Artifact.fragmentData linked) rootData);
        grafted <- Core.atPhase Verification
          (foldEither (\rootBody declarationSpine -> Separate.graft declarationSpine rootBody)
            actualRoot (Artifact.fragmentBodies linked));
        checked <- Core.atPhase Verification (Checked.check (XWithData declarations grafted));
        Core.atPhase Verification (ensure (T.alphaEq (Checked.typeOf checked) (Core.inferredType compiled))
          "installed Prelude graft changed actual root type");
        Right (InstalledRoot checked compiled (snd lowered) root)
      }
    }
}
