-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Compiler (Compilation, inferredType, compiledTerm, checkedTerm, presolution, sourceType, phase, diagnostic, prettyPhase, prettyError, atPhase, compile, compileWithPrelude, compileModules, compileModulesWithPrelude, compileFile, compileFileWithPrelude, compileSourceWithImports, standalone, compileStandalone, compileLinked, compileExpr, compileExprWithPrelude, compileProgram, compileProgramWithPrelude, finishCompilation) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Parser as P;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Prelude as Prelude;
  import qualified Bootstrap.Standalone as Standalone;
  import qualified Bootstrap.Data as D;
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
  compileLinked mode modules =
    do {
      boundValueShared1 <- atPhase ModuleResolution (Modules.linkModules mode modules);
      case boundValueShared1 of {
        LinkedModule program names valueScopes instanceScopes ->
          do {
            let {
              display = Modules.displayNames names
            };
            canonical <- case D.canonicalSourceProgram program of {
              Left message -> Left (CompileError Inference (display message));
              Right value -> Right value
            };
            lowered <-
              case Classes.lowerClassesWithScopes valueScopes instanceScopes canonical of {
                Left err -> Left (CompileError Inference (display err));
                Right lowered -> Right lowered
              };
            case lowered of {
              (,) core classes ->
                let {
                  diagnosticNames = M.union compareString (M.map display classes) names
                } in
                case finishCompilation lowered of {
                  Left (CompileError p message) ->
                    Left (CompileError p (Modules.displayNames diagnosticNames message));
                  Right (Compilation checked graph source) ->
                    Right (Compilation checked graph (display source))
                }
            }
          }
      }
    };
  compileExpr :: SExpr -> Either CompileError Compilation;
  compileExpr expr = compileExprWithPrelude ImplicitPrelude expr;
  compileExprWithPrelude :: PreludeMode -> SExpr -> Either CompileError Compilation;
  compileExprWithPrelude mode expr = compileProgramWithPrelude mode (SProgram [] expr);
  compileProgram :: SProgram -> Either CompileError Compilation;
  compileProgram program = compileProgramWithPrelude ImplicitPrelude program;
  compileProgramWithPrelude :: PreludeMode -> SProgram -> Either CompileError Compilation;
  compileProgramWithPrelude mode original =
    do {
      normalized <- atPhase ModuleResolution (Standalone.normalize mode original);
      case normalized of {
        Nothing -> compileLegacyProgramWithPrelude mode original;
        Just ((,,) imports source names) -> do {
          let { display = Modules.displayNames names };
          canonical <- case D.canonicalSourceProgram source of {
            Left message -> Left (CompileError Inference (display message));
            Right value -> Right value
          };
          lowered <- case Classes.lowerClassesWithImports imports canonical of {
            Left message -> Left (CompileError Inference (display message));
            Right result -> Right result
          };
          case lowered of { (,) core classes ->
            let { diagnosticNames = M.union compareString (M.map display classes) names } in
            case finishCompilation lowered of {
              Left (CompileError p message) ->
                Left (CompileError p (Modules.displayNames diagnosticNames message));
              Right (Compilation checked graph text) ->
                Right (Compilation checked graph (display text))
            }
          }
        }
      }
    };
  -- Preserve the historical class-free/abstract-nominal route byte-for-byte
  -- when no genuine standard-facade capability is used by the public AST.
  compileLegacyProgramWithPrelude :: PreludeMode -> SProgram -> Either CompileError Compilation;
  compileLegacyProgramWithPrelude mode original =
    case Prelude.withPrelude mode original of {
      (,) imports source ->
        do {
          canonical <- atPhase Inference (D.canonicalSourceProgram source);
          lowered <- atPhase Inference (Classes.lowerClassesWithImports imports canonical);
          finishCompilation lowered
        }
    }
}
