-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.SourceCrate
  (Compilation, compile, compileScriptWith, needsBuiltin, close, finish, checkedTerm, sourceType, dictionaryIdentities) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.Compiler as Compiler;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.InferenceUnit as Inference;
  import qualified Bootstrap.ImportParameters as Parameters;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.Crate as Crate;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.CrateSession as Session;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.X.Checked as Checked;

  -- Discovery supplies one dependency-ordered closure, with the source entry
  -- last. An anonymous root can also be supplied a checked Prelude by the
  -- installation through compileScriptWith after checking source eligibility.
  needsBuiltin :: PreludeMode -> [] SourceModule -> Bool;
  needsBuiltin mode sources = case sources of {
    [source] -> not (Compiler.standalone source) && Crate.needsBuiltin mode sources;
    _ -> Crate.needsBuiltin mode sources
  };
  compile :: Session.QueryStorage -> PreludeMode -> [] SourceModule ->
    [] ((,) String Artifact.CrateInterface) -> IO (Either CompileError Session.SourceRoot);
  compile storage mode sources interfaces = case sources of {
    [] -> ioReturn (Left (CompileError ModuleResolution "no entry module"));
    _ -> let {
      root = last sources;
      owner = Modules.moduleIdentity root;
      identity = "emlf:source:" ++ owner
    } in if Compiler.standalone root
    then compileScriptWith storage root [] (\program -> do {
      (,) names lowered <- Compiler.lowerStandalone mode program;
      Right ((,) (fromMaybe M.empty names) lowered)
    })
    else case Compiler.atPhase ModuleResolution (traverseEither Separate.cleanParsedSource sources) of {
      Left error -> ioReturn (Left error);
      Right cleaned -> Session.compileSourceRoot storage mode identity owner cleaned interfaces
    }
  };

  -- Insert the entry below the user's declarations and above its expression.
  -- This exposes each top-level SCC to the query graph, including the main
  -- binding in a declaration-only script, without splitting local lets.
  compileScriptWith :: Session.QueryStorage -> SourceModule -> [] ((,) String Artifact.CrateInterface) ->
    (SProgram -> Either CompileError ((,) (Map String String) ((,) SProgram (Map String String)))) ->
    IO (Either CompileError Session.SourceRoot);
  compileScriptWith storage source interfaces lower = let {
    owner = Modules.moduleIdentity source;
    used = Set.fromList compareString (Modules.sourceUsed source);
    choose index = let {
      identity = "emlf:script:" ++ (owner ++ (":" ++ showInt index));
      entry = Artifact.definitionName identity (Modules.Entity owner "<crate-entry>" Modules.Value)
    } in if Set.member compareString entry used then choose (index + 1) else (,) identity entry
  } in case choose 0 of { (,) identity entry -> case do {
    program <- Compiler.atPhase Parsing (Parser.standaloneProgramWith
      (\expression -> SLet entry expression (SConstructor "()")) source);
    (,) names ((,) lowered dictionaries) <- lower program;
    case lowered of {
      SClassProgram _ _ _ _ -> Left (CompileError Inference "class translation did not produce a core program");
      SProgram declarations body -> do {
        let { imports = M.fromList compareString (concatMap (compose Artifact.crateBindings snd) interfaces) };
        local <- Compiler.atPhase Verification (if M.null imports then Right body else case Parameters.prefix body of {
          Just ((,,) Nothing parameters inner) -> do {
            ensure (eqList eqString (map (\((,,) name _ _) -> name) parameters) (M.keys imports))
              "script import parameter inventory mismatch";
            Right inner
          };
          _ -> Left "script import parameters are missing from lowered declarations"
        });
        members <- Compiler.atPhase Inference (Inference.extractLoweredDeclarations local);
        Right ((,,,) names declarations members dictionaries)
      }
    }
  } of {
    Left error -> ioReturn (Left error);
    Right ((,,,) names declarations members dictionaries) ->
      Session.compileExpressionRoot storage identity owner names interfaces declarations members dictionaries
  } };

  data Compilation = Compilation Checked.CheckedTerm String (Map String String);
  checkedTerm (Compilation checked _ _) = checked;
  sourceType (Compilation _ rendered _) = rendered;
  dictionaryIdentities (Compilation _ _ names) = names;
  finish :: Session.SourceRoot -> Checked.CheckedTerm -> Compilation;
  finish root checked = let {
    display = Modules.displayNames (Session.rootDisplayNames root);
    dictionaries = Session.rootDictionaryNames root
  } in Compilation checked (display (Classes.prettyQualified dictionaries (Checked.typeOf checked))) dictionaries;
  close :: [] Artifact.CrateObject -> Session.SourceRoot -> Either CompileError Compilation;
  close dependencies root = do {
    let {
      object = Session.rootObject root;
      iface = Artifact.objectInterface object;
      objects = if null (Artifact.crateDependencies iface) then [object] else (:) object dependencies
    };
    checked <- Compiler.atPhase Verification (Artifact.linkCheckedObjects objects (Artifact.crateId iface));
    Right (finish root checked)
  }
}
