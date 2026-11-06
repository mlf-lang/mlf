-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.PreparedImportParameters (select, remove) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Separate as Separate;

  -- This operates only after the unchanged complete class lowering has
  -- validated every class, instance and translated external scheme. It does
  -- not select declarations or evidence candidates. Dependency observation
  -- includes SWanted candidate names and every local RHS, including unused
  -- bindings; Surface.freeNames does not include wanted candidates.
  select :: Map String XType -> (,) SProgram (Map String String) ->
    Either String ((,) ((,) SProgram (Map String String)) (Map String XType));
  select signatures ((,) program dictionaries) = case program of {
    SClassProgram _ _ _ _ -> Left "prepared import selection requires lowered classes";
    SProgram ds expression ->
      if M.null signatures then Right ((,) ((,) program dictionaries) signatures)
      else case expression of {
        SLetRec parameters inner -> do {
          ensure (eqList eqString (map (\((,,) name _ _) -> name) parameters) (M.keys signatures))
            "prepared import parameter inventory mismatch";
          let {
            required = S.fromList compareString (Dependency.valueNames (Dependency.observeExpression inner));
            keep = \name -> S.member compareString name required;
            selected = filter (\((,,) name _ _) -> keep name) parameters;
            selectedSignatures = M.fromList compareString (filter (\((,) name _) -> keep name) (M.toList signatures));
            output = if null selected then inner else SLetRec selected inner
          };
          Right ((,) ((,) (SProgram ds output) dictionaries) selectedSignatures)
        };
        _ -> Left "prepared import parameters are missing from lowered root"
      }
  };

  -- With zero selected imports there is no synthetic recursive group to
  -- remove. Preserve every user term/type binder; only the outer data context
  -- is owned by the enclosing checked graft, as on the existing nonempty path.
  remove :: Map String XType -> Map String ((,) XName XType) -> XTerm -> Either String XTerm;
  remove signatures available expression =
    if M.null signatures then Right (case expression of { XWithData _ body -> body; _ -> expression })
    else Separate.removeEntryParameters signatures available expression
}
