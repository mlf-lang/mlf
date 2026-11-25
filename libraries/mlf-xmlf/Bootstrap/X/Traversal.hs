-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.X.Traversal (names, freeNames, freeNamesOnto, rewriteGuardedChildren) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.X.Syntax as X;
  names :: XTerm -> [] XName;
  names term = occurrences True (\_ -> True) term [];
  freeNames term = freeNamesOnto (\_ -> True) term [];
  freeNamesOnto = occurrences False;
  -- Preserve occurrence order and multiplicity, including the head of a packed spine.
  occurrences includeBinders allowed term rest = let {
    visit = occurrences includeBinders allowed;
    emit n pending = if allowed n then (:) n pending else pending;
    binders ns pending = if includeBinders then append ns pending else pending;
    under ns = if includeBinders then visit else
      occurrences False (\n -> not (any (X.equalName n) ns) && allowed n)
  } in case term of {
    XVarTerm n -> emit n rest;
    XAbs n _ body -> binders [n] (under [n] body rest);
    XApp f a -> visit f (visit a rest);
    XTypeAbs _ _ body -> visit body rest;
    XTypeApp body _ -> visit body rest;
    XProjection rows selected -> if includeBinders then append (map (\((,,) n _ _) -> n) rows) ((:) selected rest) else rest;
    XInstantiationSpine n rows -> emit n (foldr (\((,,) _ _ operand) pending -> visit operand pending) rest rows);
    XLet n rhs body -> binders [n] (visit rhs (under [n] body rest));
    XLetRec defs body -> let { inner = under (map (\((,,) n _ _) -> n) defs) } in
      foldr (\((,,) n _ rhs) pending -> binders [n] (inner rhs pending)) (inner body rest) defs;
    XCase subject _ branches -> visit subject (foldr (\(XAlternative pat body) pending ->
      let { ns = X.patternNames pat } in binders ns (under ns body pending)) rest branches);
    XWithData _ body -> visit body rest;
    XIntTerm _ -> rest; XDoubleTerm _ -> rest; XBoolTerm _ -> rest; XStringTerm _ -> rest;
    XPrimitive _ _ -> rest; XConstructor _ _ -> rest
  };
  -- A substitution may decline a binder or a declaration boundary.
  rewriteGuardedChildren safe visit value = case value of {
    XVarTerm _ -> Just value;
    XApp a b -> do { f <- visit a; arg <- visit b; Just (XApp f arg) };
    XInstantiationSpine name rows -> visit (X.expandInstantiationSpine name rows);
      XAbs name ty body -> if safe name then mapOptional (XAbs name ty) (visit body) else Nothing;
      XTypeAbs var bound body -> mapOptional (XTypeAbs var bound) (visit body);
      XTypeApp body proof -> mapOptional (\term -> XTypeApp term proof) (visit body);
      XLet name rhs body -> if not (safe name) then Nothing else do {
        binding <- visit rhs;
        result <- visit body;
        Just (XLet name binding result)
      };
      XLetRec definitions body ->
        if not (all (\((,,) name _ _) -> safe name) definitions) then Nothing else do {
          bindings <- mapM (\((,,) name ty rhs) -> mapOptional (\result -> (,,) name ty result) (visit rhs)) definitions;
          result <- visit body;
          Just (XLetRec bindings result)
        };
      XCase scrutinee ty alternatives -> do {
        selected <- visit scrutinee;
        branches <- mapM (\(XAlternative pattern body) -> if all safe (X.patternNames pattern)
          then mapOptional (XAlternative pattern) (visit body) else Nothing) alternatives;
        Just (XCase selected ty branches)
      };
      XWithData _ _ -> Nothing;
      XProjection _ _ -> Just value;
      XIntTerm _ -> Just value;
      XDoubleTerm _ -> Just value;
      XBoolTerm _ -> Just value;
      XStringTerm _ -> Just value;
      XPrimitive _ _ -> Just value;
      XConstructor _ _ -> Just value
  }
}
