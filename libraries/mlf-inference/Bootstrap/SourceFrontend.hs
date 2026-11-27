-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.SourceFrontend
  (standalone, lowerStandalone, finishWithSourceNames, phase, diagnostic, prettyPhase, prettyError, atPhase) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Prelude as Prelude;
  import qualified Bootstrap.Standalone as Standalone;
  import qualified Bootstrap.Classes as Classes;
  import Bootstrap.CompilerCore (phase, diagnostic, prettyPhase, prettyError, atPhase);

  -- Source normalization and class lowering are shared frontend operations.
  -- They do not own inference: every public source/AST compiler is a crate
  -- request, while group and builtin kernels use CompilerCore directly.
  standalone (SourceModule _ name _ imports _ _ _ _ _ _) =
    case name of {
      Nothing -> L.null imports;
      Just _ -> False
    };
  lowerSourceProgram imports lower program = do {
    canonical <- Classes.canonicalSourceProgram imports program;
    lower canonical
  };
  finishWithSourceNames :: forall a. Map String String ->
    ((,) SProgram (Map String String) -> Either CompileError a) ->
    (,) SProgram (Map String String) -> Either CompileError a;
  finishWithSourceNames names finish lowered =
    let {
      classes = M.map (Modules.displayNames names) (L.snd lowered);
      display = Modules.displayNames (M.union compareString classes names)
    } in L.mapLeft (\(CompileError p message) -> CompileError p (display message)) (finish lowered);
  lowerStandalone :: PreludeMode -> SProgram -> Either CompileError
    ((,) (Maybe (Map String String)) ((,) SProgram (Map String String)));
  lowerStandalone mode original = do {
    normalized <- atPhase ModuleResolution (Standalone.normalize mode original);
    let {
      lower imports source = lowerSourceProgram imports (Classes.lowerClassesWithImports imports) source
    };
    case normalized of {
      Nothing -> case Prelude.withPrelude mode original of {
        (,) imports source -> do {
          lowered <- atPhase Inference (lower imports source);
          Right ((,) Nothing lowered)
        }
      };
      Just ((,,) imports source names) -> do {
        lowered <- atPhase Inference (L.mapLeft (Modules.displayNames names) (lower imports source));
        Right ((,) (Just names) lowered)
      }
    }
  }
}
