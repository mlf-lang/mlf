-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Test.CaseSelection (CaseSelection, matching, project, rebind, total, cases) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.Map as M;
  import qualified Test.Case as C;
  import qualified Test.Registry as R;
  data CaseSelection = CaseSelection Int ([] C.Case);
  total (CaseSelection count _) = count;
  cases (CaseSelection _ selected) = selected;
  matching predicate entries = do {
    R.validate (S.map C.descriptor entries);
    let { selected = S.filter predicate entries };
    if S.null selected then Left "no tests matched selection" else Right (CaseSelection (S.length entries) selected)
  };
  -- Adapter actions can be installed after planning. Verify their descriptors
  -- against the same inventory while preserving the adapter's execution order.
  project entries selected = validateProjection False entries selected;
  rebind entries selected = validateProjection True entries selected;
  validateProjection install entries selected = do {
    R.validate (S.map C.descriptor entries);
    R.validIds (S.map C.id selected);
    R.ensure (S.not (S.null selected)) "empty required test selection";
    let {
      index = M.fromList compareString (S.map (\entry -> (,) (C.id entry) entry) entries);
      check entry = case M.lookup compareString (C.id entry) index of {
        Nothing -> Left "unknown test ID";
        Just original -> do {
          R.ensure (eqString (C.name original) (C.name entry) && S.eqList eqString (C.tags original) (C.tags entry))
            "selected test descriptor changed";
          Right (if install then original else entry)
        }
      }
    };
    bound <- S.mapM check selected;
    Right (CaseSelection (S.length entries) bound)
  }
}
