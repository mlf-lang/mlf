-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.SourceCrate
  (Compilation, compile, compileClosed, compileScriptWith, needsBuiltin, close, finish, checkedTerm, sourceType, dictionaryIdentities, nameMap) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Parser as Parser;
  import qualified Bootstrap.SourceFrontend as Compiler;
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
    } in if null interfaces && Compiler.standalone root
    then compileScriptWith storage root [] (\program -> do {
      (,) names lowered <- Compiler.lowerStandalone mode program;
      Right ((,,) (fromMaybe M.empty names) Nothing lowered)
    })
    else case Compiler.atPhase ModuleResolution (traverseEither Separate.cleanParsedSource sources) of {
      Left error -> ioReturn (Left error);
      Right cleaned -> Session.compileSourceRoot storage mode identity owner cleaned interfaces
    }
  };

  compileClosed :: Session.QueryStorage -> PreludeMode -> [] SourceModule ->
    IO (Either CompileError Compilation);
  compileClosed storage mode sources = let {
    -- A caller may pass an MLF.Primitive source to stand in for the builtin
    -- module (the indexvec probes do this to control instance visibility).
    -- The checked Prelude already owns that module and crate validation
    -- refuses a second owner, so the builtin interface supplies it and the
    -- caller's placeholder is not compiled as an owned module.
    owned = filter (\source ->
      not (Modules.isBuiltinModule (Modules.moduleIdentity source))) sources;
    dependencies = if needsBuiltin mode owned then do {
      object <- Compiler.atPhase Verification Artifact.builtinPrelude;
      Right [object]
    } else Right []
  } in case dependencies of {
    Left err -> ioReturn (Left err);
    Right objects -> do {
      let { interfaces = map (\object ->
        (,) "/builtin/prelude.mlfci" (Artifact.objectInterface object)) objects };
      result <- compile storage mode owned interfaces;
      ioReturn (bindEither result (close objects))
    }
  };

  -- Keep the final expression in its use-site class scope while lowering.
  -- An empty recursive group introduces no binding or generalization and
  -- preserves that boundary through lowering. Only then make the checked
  -- entry a declaration; its RHS still contains all of the user's local lets.
  compileScriptWith :: Session.QueryStorage -> SourceModule -> [] ((,) String Artifact.CrateInterface) ->
    (SProgram -> Either CompileError ((,,) (Map String String) (Maybe ((,) ([] DataDecl) ([] SClassDecl))) ((,) SProgram (Map String String)))) ->
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
      (SLetRec []) source);
    (,,) names headers ((,) lowered dictionaries) <- lower program;
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
        body <- Compiler.atPhase Verification (insertScriptEntry entry local);
        members <- Compiler.atPhase Inference (Inference.extractLoweredDeclarations body);
        Right ((,,) names (fromMaybe ((,) declarations []) headers) (Inference.LoweredDeclarations (Just entry) declarations members dictionaries))
      }
    }
  } of {
    Left error -> ioReturn (Left error);
    Right ((,,) names headers lowered) ->
      Session.compileExpressionRoot storage identity owner entry names interfaces headers lowered
  } };

  insertScriptEntry :: String -> SExpr -> Either String SExpr;
  insertScriptEntry entry expression = case expression of {
    SDeclScope ids body -> mapEither (SDeclScope ids) (insertScriptEntry entry body);
    SLet name value body -> mapEither (SLet name value) (insertScriptEntry entry body);
    SLetRec [] body -> Right (SLet entry body (SConstructor "()"));
    SLetRec members body -> mapEither (SLetRec members) (insertScriptEntry entry body);
    _ -> Left "class lowering lost the script expression boundary"
  };

  data Compilation = Compilation Checked.CheckedTerm String (Map String String) Modules.Names;
  checkedTerm (Compilation checked _ _ _) = checked;
  sourceType (Compilation _ rendered _ _) = rendered;
  dictionaryIdentities (Compilation _ _ names _) = names;
  nameMap (Compilation _ _ _ (Modules.Names names)) = names;
  finish :: Session.SourceRoot -> Checked.CheckedTerm -> Compilation;
  finish root checked = let {
    display = Modules.displayNames (Session.rootDisplayNames root);
    dictionaries = Session.rootDictionaryNames root
  } in Compilation checked (display (Classes.prettyQualified dictionaries (Checked.typeOf checked))) dictionaries
    (Session.rootNames root);
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
