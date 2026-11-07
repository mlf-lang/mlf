-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.PreparedStandalone
  (admitRoot, compileChecked, compileCheckedWithConstraints) where {
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
  import qualified Bootstrap.CompilerCore as Core;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.ImportParameters as Parameters;
  import qualified Bootstrap.ImportedRoot as Imported;
  import qualified Bootstrap.BuiltinPreludeContext as Context;

  -- Admission uses the same provider name and visibility tables before either
  -- compiler or graph comparison asks for the checked root.
  admitRoot :: PreludeMode -> Modules.Names -> Modules.Interface -> Set String ->
    SProgram -> Maybe Standalone.RewrittenRoot;
  admitRoot mode names environment protected program = case mode of {
    NoImplicitPrelude -> Nothing;
    ImplicitPrelude ->
      if collides protected program then Nothing else
      case Standalone.rewriteRootWithNames mode names environment program of {
        Left _ -> Nothing;
        Right root ->
          if not (Standalone.rewrittenNeeded root) || ownSupportCollision protected root
          then Nothing else Just root
      }
  };

  sourcePhase phase root result = Core.atPhase phase
    (mapLeft (Modules.displayNames (Standalone.rewrittenDisplay root)) result);
  finishImported finish root signatures lowered = let {
    display = Modules.displayNames (Standalone.rewrittenDisplay root);
    diagnosticNames = M.union compareString (M.map display (snd lowered))
      (Standalone.rewrittenDisplay root)
  } in case finish signatures lowered of {
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
  compileChecked :: Context.PreparedPrelude -> Standalone.RewrittenRoot -> SProgram ->
    Either CompileError ((,,) Checked.CheckedTerm String (Map String String));
  compileChecked = compileCheckedUsing
    (\context signatures lowered -> mapEither (\compiled -> (,) compiled ())
      (Imported.finishSelectedWithEvidence context signatures lowered))
    (\checked source names _ -> (,,) checked source names);
  compileCheckedWithConstraints :: Context.PreparedPrelude -> Standalone.RewrittenRoot -> SProgram ->
    Either CompileError ((,,,) Checked.CheckedTerm String (Map String String) Constraints);
  compileCheckedWithConstraints = compileCheckedUsing Imported.finishSelectedWithEvidenceAndConstraints (,,,);
  compileCheckedUsing :: forall observation result.
    (Context.PreparedPrelude -> Parameters.Signatures -> (,) SProgram (Map String String) ->
      Either CompileError ((,) Imported.Compilation observation)) ->
    (Checked.CheckedTerm -> String -> Map String String -> observation -> result) ->
    Context.PreparedPrelude -> Standalone.RewrittenRoot -> SProgram -> Either CompileError result;
  compileCheckedUsing finish report context root program = do {
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
          (Parameters.selectNamed (Parameters.namedImports signatures) fullLowered);
        let { lowered = fst selected; selectedSignatures = Parameters.project (snd selected) };
        finished <- finishImported (finish context) root (snd selected) lowered;
        let {
          compiled = fst finished;
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
        Right (report checked (Modules.displayNames (Standalone.rewrittenDisplay root)
          (Imported.sourceType compiled))
          (M.map (Modules.displayNames (Standalone.rewrittenDisplay root)) (snd lowered)) (snd finished))
  }
}
