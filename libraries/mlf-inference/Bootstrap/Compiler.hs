-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Compiler (Compilation, inferredType, compiledTerm, checkedTerm, presolution, sourceType, phase, diagnostic, prettyPhase, prettyError, atPhase, compile, compileWithPrelude, compileModules, compileModulesWithPrelude, compileFile, compileFileWithPrelude, compileSourceWithImports, standalone, compileStandalone, compileLinked, compileResolvedRoot, compileExpr, compileExprWithPrelude, compileProgram, compileProgramWithPrelude, lowerStandalone, finishWithSourceNames, finishCompilation) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Parser as P;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Prelude as Prelude;
  import qualified Bootstrap.Standalone as Standalone;
  import qualified Bootstrap.Classes as Classes;
  import Bootstrap.CompilerCore;
  compile :: String -> String -> Either CompileError Compilation;
  compile file source = compileWithPrelude ImplicitPrelude file source;
  compileWithPrelude :: PreludeMode -> String -> String -> Either CompileError Compilation;
  compileWithPrelude mode file source = compileModulesWithPrelude mode M.empty file source;
  compileModules :: Map String ((,) String String) ->
                    String -> String -> Either CompileError Compilation;
  compileModules sources file input = compileModulesWithPrelude ImplicitPrelude sources file input;
  compileModulesWithPrelude :: PreludeMode ->
                               Map String ((,) String String) ->
                               String -> String -> Either CompileError Compilation;
  compileModulesWithPrelude mode sources file input =
    do {
      root <- atPhase Parsing (P.parseModule file input);
      if standalone root
      then compileStandalone mode root
      else do {
             modules <- atPhase ModuleResolution (Modules.loadModuleMap sources root);
             compileLinked mode modules
           }
    };
  compileFile :: [] String -> String -> IO (Either CompileError Compilation);
  compileFile paths file = compileFileWithPrelude ImplicitPrelude paths file;
  compileFileWithPrelude :: PreludeMode ->
                            [] String -> String -> IO (Either CompileError Compilation);
  compileFileWithPrelude mode paths file =
    do {
      present <- fileExists file;
      if present
      then do {
             input <- readFile file;
             compileSourceWithImports mode paths file input
           }
      else ioReturn (Left (CompileError ModuleResolution ("file does not exist: " ++ file)))
    };
  compileSourceWithImports :: PreludeMode ->
                              [] String ->
                              String -> String -> IO (Either CompileError Compilation);
  compileSourceWithImports mode paths file input =
    case atPhase Parsing (P.parseModule file input) of {
      Left err -> ioReturn (Left err);
      Right root ->
        if standalone root
        then ioReturn (compileStandalone mode root)
        else do {
               modules <- Modules.loadModuleFiles paths root;
               ioReturn
                 (case atPhase ModuleResolution modules of {
                    Left err -> Left err;
                    Right loaded -> compileLinked mode loaded
                  })
             }
    };
  standalone (SourceModule _ name _ imports _ _ _ _ _ _) =
    case name of {
      Nothing -> L.null imports;
      Just _ -> False
    };
  compileStandalone :: PreludeMode -> SourceModule -> Either CompileError Compilation;
  compileStandalone mode root =
    do {
      program <- atPhase Parsing (P.standaloneProgram root);
      compileProgramWithPrelude mode program
    };
  compileLinked :: PreludeMode -> [] SourceModule -> Either CompileError Compilation;
  compileLinked mode modules = do {
    root <- atPhase ModuleResolution (Modules.resolveSourceRoot mode modules);
    compileResolvedRoot root
  };
  compileResolvedRoot :: Modules.ResolvedCrate -> Either CompileError Compilation;
  compileResolvedRoot root = do {
    (,) (LinkedModule program names _ instanceScopes) valueScopes <-
      atPhase ModuleResolution (Modules.linkResolvedForCompilation root);
    compileNamedProgram S.empty names (Classes.lowerClassesInScopes valueScopes instanceScopes) program
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
  -- A linked module supplies its defining scopes. A standalone root supplies
  -- its normalized imports. Both own one program through inference and checking.
  compileNamedProgram imports names lower program = do {
    let { display = Modules.displayNames names };
    lowered <- atPhase Inference (L.mapLeft display (lowerSourceProgram imports lower program));
    finishNamedProgram names lowered
  };
  finishNamedProgram names lowered = do {
    Compilation checked graph source <- finishWithSourceNames names finishCompilation lowered;
    Right (Compilation checked graph (Modules.displayNames names source))
  };
  compileExpr :: SExpr -> Either CompileError Compilation;
  compileExpr expr = compileExprWithPrelude ImplicitPrelude expr;
  compileExprWithPrelude :: PreludeMode -> SExpr -> Either CompileError Compilation;
  compileExprWithPrelude mode expr = compileProgramWithPrelude mode (SProgram [] expr);
  compileProgram :: SProgram -> Either CompileError Compilation;
  compileProgram program = compileProgramWithPrelude ImplicitPrelude program;
  compileProgramWithPrelude :: PreludeMode -> SProgram -> Either CompileError Compilation;
  compileProgramWithPrelude mode original = do {
    (,) names lowered <- lowerStandalone mode original;
    case names of {
      Nothing -> finishCompilation lowered;
      Just table -> finishNamedProgram table lowered
    }
  };
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
