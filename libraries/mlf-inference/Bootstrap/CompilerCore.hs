-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.CompilerCore where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Constraint as C;
  import qualified Bootstrap.Elaborate as E;
  import qualified Bootstrap.Graph.Solver as Solver;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  data Compilation = Compilation Checked.CheckedTerm Graph String;
  inferredType (Compilation checked _ _) = Checked.typeOf checked;
  compiledTerm (Compilation checked _ _) = Checked.term checked;
  checkedTerm (Compilation checked _ _) = checked;
  presolution (Compilation _ g _) = g;
  sourceType (Compilation _ _ s) = s;
  phase (CompileError p _) = p;
  diagnostic (CompileError _ s) = s;
  prettyPhase :: Phase -> String;
  prettyPhase p =
    case p of {
      Parsing -> "Parsing";
      ModuleResolution -> "ModuleResolution";
      Inference -> "Inference";
      Resolution -> "Resolution";
      Elaboration -> "Elaboration";
      Verification -> "Verification"
    };
  prettyError (CompileError p s) = (prettyPhase p ++ (": " ++ s));
  atPhase :: forall a. Phase -> Either String a -> Either CompileError a;
  atPhase p value =
    case value of {
      Left e -> Left (CompileError p e);
      Right a -> Right a
    };
  finishCompilation :: (,) SProgram (Map String String) -> Either CompileError Compilation;
  finishCompilation = finishCompilationWith C.generateProgram;
  finishCompilationWith generate = finishCompilationUsing (\program -> do {
    constraints <- generate program;
    solved <- C.solvePrepared constraints;
    Right ((,) constraints solved)
  });
  finishFileCompilation :: (,) SProgram (Map String String) -> Either CompileError Compilation;
  finishFileCompilation = finishCompilationUsing C.generateAndSolveFileProgram;
  finishCompilationUsing = finishSolvedCompilation E.prepareSolvedTypes;
  finishSolvedCompilation :: (Solver -> E.TypeContext) ->
    (SProgram -> Either String ((,) Constraints Solver)) ->
    (,) SProgram (Map String String) -> Either CompileError Compilation;
  finishSolvedCompilation prepareTypes infer ((,) program names) =
    case program of {
      SClassProgram _ _ _ _ ->
        Left (CompileError Inference "class translation did not produce a core program");
      SProgram declarations expression ->
        do {
          (,) constraints solved <- atPhase Inference (infer program);
          let {
            graph = Solver.solverGraph solved
          };
          let {
            types = prepareTypes solved
          };
          (,) checked _ <- finishCheckedRoot types
            (E.graphDatatypes (E.contextGraph types)) constraints solved declarations []
            Checked.check "elaboration changed the inferred type" "elaboration changed source erasure";
          Right (Compilation checked graph (Classes.prettyQualified names (Checked.typeOf checked)))
        }
    };
  -- Imported callers authenticate their ordered parameters before this stage.
  -- Keep the checked wrapper and the user result type separate: import arrows
  -- belong to the wrapper, while source diagnostics report the user's type.
  finishCheckedRoot :: E.TypeContext -> DataEnv -> Constraints -> Solver ->
    [] DataDecl -> [] ((,) XName XType) ->
    (XTerm -> Either String Checked.CheckedTerm) -> String -> String ->
    Either CompileError ((,) Checked.CheckedTerm XType);
  finishCheckedRoot types datatypes constraints solved declarations parameters check typeError erasureError = do {
    evidence <- atPhase Resolution (E.resolveWithinIn types datatypes M.empty (C.skeleton constraints));
    body <- atPhase Elaboration
      (E.elaborateWithinIn types datatypes evidence solved M.empty (C.skeleton constraints));
    let {
      userType = E.schemeTypeIn types (C.generalization (C.skeleton constraints));
      wrapped = L.foldr (\((,) name ty) rest -> XAbs name ty rest) body parameters;
      term = if L.null declarations then wrapped else XWithData declarations wrapped;
      expected = L.foldr (\((,) _ ty) rest -> XArrow ty rest) userType parameters;
      erased = L.foldr (\((,) name _) rest -> XEAbs name rest)
        (C.eraseSourceWith evidence (C.skeleton constraints)) parameters
    };
    checked <- atPhase Verification (check term);
    if L.not (T.alphaEq (Checked.typeOf checked) expected)
    then Left (CompileError Verification typeError)
    else if L.not (X.equalErased (X.erase term) erased)
         then Left (CompileError Verification erasureError)
         else Right ((,) checked userType)
  }
}
