-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.ImportParameters (Signatures, admit, namedImports, entries, namedEntries, project, select, remove) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Separate as Separate;

  -- Each external signature has a consumer-local declaration slot. Keep the
  -- incoming stable-key order for the wrapper, independently of slot order.
  data Signatures = Signatures Dependency.Symbols ([] ((,) (V.Index Declaration) XType));
  entries (Signatures _ rows) = rows;
  namedEntries (Signatures symbols rows) = map (\((,) i ty) -> (,) (Dependency.symbolName symbols i) ty) rows;
  project imports = M.fromDistinctAscList (namedEntries imports);
  -- Resolved imports use their original entity slot. Checked support such as
  -- a dictionary absent from the source namespace extends the same domain.
  admit base known signatures = let {
    rows = M.toList signatures;
    extra = filter (\key -> not (M.member compareString key known)) (map fst rows);
    extended = Dependency.appendSymbols base extra; symbols = fst extended; ids = snd extended;
    slots = M.union compareString known (M.fromDistinctAscList (zip extra ids));
    bindings = map (\((,) key ty) -> (,) (M.get compareString key slots) ty) rows
  } in Signatures symbols bindings;
  namedImports = admit (Dependency.symbols []) M.empty;

  -- Complete class lowering has already validated the input. Bind its free
  -- references once at the named AST boundary. Observation includes SWanted
  -- candidates and unused local RHSs, and respects lexical shadowing.
  select :: Signatures -> (,) SProgram (Map String String) ->
    Either String ((,) ((,) SProgram (Map String String)) Signatures);
  select imports@(Signatures symbols rows) ((,) program dictionaries) = case program of {
    SClassProgram _ _ _ _ -> Left "prepared import selection requires lowered classes";
    SProgram ds expression ->
      if null rows then Right ((,) ((,) program dictionaries) imports)
      else case expression of {
        SLetRec parameters inner -> do {
          let { keys = map (compose (Dependency.symbolName symbols) fst) rows };
          ensure (eqList eqString (map (\((,,) name _ _) -> name) parameters) keys)
            "prepared import parameter inventory mismatch";
          let {
            slots = M.fromDistinctAscList (zip keys (map fst rows));
            needed = IS.fromList (map V.toInt (mapMaybe (\key -> M.lookup compareString key slots)
              (Dependency.valueNames (Dependency.observeExpression inner))));
            selected = filter (\((,) row _) -> IS.member (V.toInt (fst row)) needed) (zip rows parameters);
            output = if null selected then inner else SLetRec (map snd selected) inner
          };
          Right ((,) ((,) (SProgram ds output) dictionaries) (Signatures symbols (map fst selected)))
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
