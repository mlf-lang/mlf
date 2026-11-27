-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Compiler
  (Compilation, inferredType, compiledTerm, checkedTerm, sourceType,
   phase, diagnostic, prettyPhase, prettyError, atPhase, standalone,
   compile, compileWithPrelude, compileModules, compileModulesWithPrelude,
   compileFile, compileFileWithPrelude, compileSourceWithImports,
   compileStandalone, compileLinked, compileExpr, compileExprWithPrelude,
   compileProgram, compileProgramWithPrelude) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Parser as P;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.SourceCrate as Source;
  import Bootstrap.SourceCrate (Compilation, checkedTerm, sourceType);
  import qualified Bootstrap.CrateSession as Session;
  import Bootstrap.SourceFrontend (standalone, phase, diagnostic, prettyPhase, prettyError, atPhase);
  import qualified Bootstrap.X.Checked as Checked;

  -- Files, source text and caller-owned ASTs only differ in discovery. All
  -- requests use the crate declaration graph, checked objects and linker.
  -- In-memory callers use the same query session without filesystem storage.
  inferredType compiled = Checked.typeOf (checkedTerm compiled);
  compiledTerm compiled = Checked.term (checkedTerm compiled);
  compile :: String -> String -> IO (Either CompileError Compilation);
  compile file source = compileWithPrelude ImplicitPrelude file source;
  compileWithPrelude :: PreludeMode -> String -> String -> IO (Either CompileError Compilation);
  compileWithPrelude mode file source = compileModulesWithPrelude mode M.empty file source;
  compileModules :: Map String ((,) String String) ->
    String -> String -> IO (Either CompileError Compilation);
  compileModules sources file input = compileModulesWithPrelude ImplicitPrelude sources file input;
  compileModulesWithPrelude :: PreludeMode -> Map String ((,) String String) ->
    String -> String -> IO (Either CompileError Compilation);
  compileModulesWithPrelude mode sources file input = case atPhase Parsing (P.parseModule file input) of {
    Left err -> ioReturn (Left err);
    Right root -> if standalone root then compileLinked mode [root]
      else case atPhase ModuleResolution (Modules.loadModuleMap sources root) of {
        Left err -> ioReturn (Left err);
        Right modules -> compileLinked mode modules
      }
  };
  compileFile :: [] String -> String -> IO (Either CompileError Compilation);
  compileFile paths file = compileFileWithPrelude ImplicitPrelude paths file;
  compileFileWithPrelude :: PreludeMode -> [] String -> String -> IO (Either CompileError Compilation);
  compileFileWithPrelude mode paths file = do {
    present <- fileExists file;
    if present then do {
      input <- readFile file;
      compileSourceWithImports mode paths file input
    } else ioReturn (Left (CompileError ModuleResolution ("file does not exist: " ++ file)))
  };
  compileSourceWithImports :: PreludeMode -> [] String ->
    String -> String -> IO (Either CompileError Compilation);
  compileSourceWithImports mode paths file input = case atPhase Parsing (P.parseModule file input) of {
    Left err -> ioReturn (Left err);
    Right root -> if standalone root then compileLinked mode [root] else do {
      loaded <- Modules.loadModuleFiles paths root;
      case atPhase ModuleResolution loaded of {
        Left err -> ioReturn (Left err);
        Right sources -> compileLinked mode sources
      }
    }
  };
  compileStandalone :: PreludeMode -> SourceModule -> IO (Either CompileError Compilation);
  compileStandalone mode root = case atPhase Parsing (P.standaloneProgram root) of {
    Left err -> ioReturn (Left err);
    Right program -> compileProgramWithPrelude mode program
  };
  compileLinked :: PreludeMode -> [] SourceModule -> IO (Either CompileError Compilation);
  compileLinked = Source.compileClosed Session.MemoryQueries;
  compileExpr :: SExpr -> IO (Either CompileError Compilation);
  compileExpr = compileExprWithPrelude ImplicitPrelude;
  compileExprWithPrelude :: PreludeMode -> SExpr -> IO (Either CompileError Compilation);
  compileExprWithPrelude mode expr = compileProgramWithPrelude mode (SProgram [] expr);
  compileProgram :: SProgram -> IO (Either CompileError Compilation);
  compileProgram = compileProgramWithPrelude ImplicitPrelude;
  compileProgramWithPrelude :: PreludeMode -> SProgram -> IO (Either CompileError Compilation);
  compileProgramWithPrelude mode program = let {
    source declarations classes instances body = SourceModule "<expression>" Nothing Nothing []
      declarations classes instances [] (Just body) LegacyEmlfV1
  } in compileLinked mode [case program of {
    SProgram declarations body -> source declarations [] [] body;
    SClassProgram declarations classes instances body -> source declarations classes instances body
  }]
}
