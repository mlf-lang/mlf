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
  finishCompilation ((,) program names) =
    case program of {
      SClassProgram _ _ _ _ ->
        Left (CompileError Inference "class translation did not produce a core program");
      SProgram declarations expression ->
        do {
          constraints <- atPhase Inference (C.generateProgram program);
          solved <- atPhase Inference (C.solvePrepared constraints);
          let {
            graph = Solver.solverGraph solved
          };
          let {
            types = E.prepareTypes graph
          };
          evidence <- atPhase Resolution (E.resolveEvidenceIn types (C.skeleton constraints));
          body <-
            atPhase Elaboration
              (E.elaboratePreparedIn types solved evidence (C.skeleton constraints));
          let {
            term = if L.null declarations then body else XWithData declarations body
          };
          checked <- atPhase Verification (Checked.check term);
          let {
            ty = Checked.typeOf checked
          };
          let {
            expected = E.schemeTypeIn types (C.generalization (C.skeleton constraints))
          };
          if L.not (T.alphaEq ty expected)
          then Left (CompileError Verification "elaboration changed the inferred type")
          else if L.not
                    (X.equalErased (X.erase term)
                       (C.eraseSourceWith evidence (C.skeleton constraints)))
               then Left (CompileError Verification "elaboration changed source erasure")
               else Right (Compilation checked graph (Classes.prettyQualified names ty))
        }
    }
}
