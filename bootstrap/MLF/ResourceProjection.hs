-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
-- Bounded post-check lazy environment weakening. Never a source-check shortcut.
module MLF.ResourceProjection where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.X.Checked as K;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified MLF.ResourceModules as Evidence;
  import qualified Package.Json as J;

  data Entry = LetEntry XName XTerm | RecEntry ([] ((,,) XName XType XTerm));
  data ErasedEntry = ErasedLet XName XErased | ErasedRec ([] ((,) XName XErased));
  data Projection = Projection K.CheckedTerm K.CheckedTerm ([] J.Json);
  original (Projection value _ _) = value;
  projected (Projection _ value _) = value;
  steps (Projection _ _ values) = values;
  ids names = IS.fromList (L.map X.nameId names);
  unionMany values = L.foldl IS.union IS.empty values;
  sorted values = J.Array (L.map J.num (IS.toList values));
  namesJson values = J.Array (L.map (L.compose J.num X.nameId) values);

  freeTyped :: XTerm -> IntSet;
  freeTyped term = case term of {
    XVarTerm n -> IS.singleton (X.nameId n);
    XAbs n _ body -> IS.delete (X.nameId n) (freeTyped body);
    XApp a b -> IS.union (freeTyped a) (freeTyped b);
    XTypeAbs _ _ body -> freeTyped body;
    XTypeApp body _ -> freeTyped body;
    XLet n rhs body -> IS.union (freeTyped rhs) (IS.delete (X.nameId n) (freeTyped body));
    XLetRec bindings body ->
      IS.difference (unionMany ((:) (freeTyped body)
        (L.map (\((,,) _ _ value) -> freeTyped value) bindings)))
        (ids (L.map (\((,,) n _ _) -> n) bindings));
    XCase subject _ alternatives -> IS.union (freeTyped subject)
      (unionMany (L.map (\(XAlternative pattern body) ->
        IS.difference (freeTyped body) (ids (X.patternNames pattern))) alternatives));
    XWithData _ body -> freeTyped body;
    XIntTerm _ -> IS.empty; XDoubleTerm _ -> IS.empty;
    XBoolTerm _ -> IS.empty; XStringTerm _ -> IS.empty;
    XPrimitive _ _ -> IS.empty; XConstructor _ _ -> IS.empty
  };
  freeErased :: XErased -> IntSet;
  freeErased term = case term of {
    XEVar n -> IS.singleton (X.nameId n);
    XEAbs n body -> IS.difference (freeErased body) (IS.singleton (X.nameId n));
    XEApp function argument -> IS.union (freeErased function) (freeErased argument);
    XELet n value continuation -> IS.union (freeErased value)
      (IS.difference (freeErased continuation) (IS.singleton (X.nameId n)));
    XELetRec definitions continuation -> let {
      bound = ids (L.map (\((,) n _) -> n) definitions);
      values = unionMany (L.map (\((,) _ value) -> freeErased value) definitions)
    } in IS.difference (IS.union values (freeErased continuation)) bound;
    XECase subject branches -> L.foldl IS.union (freeErased subject)
      (L.map (\(XErasedAlternative pattern body) ->
        IS.difference (freeErased body) (ids (X.patternNames pattern))) branches);
    XEInt _ -> IS.empty; XEDouble _ -> IS.empty; XEBool _ -> IS.empty;
    XEString _ -> IS.empty; XEPrimitive _ -> IS.empty;
    XEConstructor _ -> IS.empty; XEEvidenceHole _ -> IS.empty
  };
  noErasedHole term = case term of {
    XEEvidenceHole _ -> False;
    XEAbs _ body -> noErasedHole body;
    XEApp a b -> noErasedHole a && noErasedHole b;
    XELet _ a b -> noErasedHole a && noErasedHole b;
    XELetRec bindings body -> L.all (\((,) _ value) -> noErasedHole value) bindings && noErasedHole body;
    XECase subject alternatives -> noErasedHole subject &&
      L.all (\(XErasedAlternative _ body) -> noErasedHole body) alternatives;
    _ -> True
  };

  -- Count tagged syntax nodes and structural JSON depth with an explicit worklist.
  -- This is evidence admission only; all ordinary source checking precedes it.
  boundEvidence value = boundWork 0 [((,) 1 value)];
  boundWork count pending = case pending of {
    [] -> Right ();
    (:) ((,) depth value) rest -> do {
      L.ensure (depth <= 1024) "module evidence depth exceeds 1024";
      case value of {
        J.Object fields -> let {
          tagged = L.any (\((,) key _) -> eqString key "tag") fields;
          next = if tagged then count + 1 else count
        } in do {
          L.ensure (next <= 100000) "module evidence exceeds 100000 tagged syntax nodes";
          boundWork next (L.append (L.map (\((,) _ child) -> (,) (depth + 1) child) fields) rest)
        };
        J.Array values -> boundWork count (L.append (L.map (\child -> (,) (depth + 1) child) values) rest);
        _ -> boundWork count rest
      }
    }
  };
  -- Reject identity aliasing before set-based demand. Same textual spelling with
  -- distinct IDs is allowed; actual source allocator IDs must be globally fresh.
  remember binding n state = case state of { (,) bound hints -> do {
    let { identity = X.nameId n; hint = X.nameHint n };
    L.ensure (identity >= 0) "negative module term identity";
    case IM.lookup identity hints of {
      Nothing -> Right ();
      Just prior -> L.ensure (eqString prior hint) "module term identity changes hint"
    };
    L.ensure (L.not binding || L.not (IS.member identity bound)) "module term binding identity reused";
    Right ((,) (if binding then IS.insert identity bound else bound) (IM.insert identity hint hints))
  } };
  identities pending state = case pending of {
    [] -> Right ();
    (:) term rest -> case term of {
      XVarTerm n -> do { next <- remember False n state; identities rest next };
      XAbs n _ body -> do { next <- remember True n state; identities ((:) body rest) next };
      XLet n rhs body -> do { next <- remember True n state; identities ((:) rhs ((:) body rest)) next };
      XLetRec bindings body -> do {
        next <- L.foldEither (\current ((,,) n _ _) -> remember True n current) state bindings;
        identities (L.append (L.map (\((,,) _ _ rhs) -> rhs) bindings) ((:) body rest)) next
      };
      XApp a b -> identities ((:) a ((:) b rest)) state;
      XTypeAbs _ _ body -> identities ((:) body rest) state;
      XTypeApp body _ -> identities ((:) body rest) state;
      XWithData _ body -> identities ((:) body rest) state;
      XCase subject _ alternatives -> do {
        next <- L.foldEither (\current (XAlternative pattern _) ->
          L.foldEither (\scope n -> remember True n scope) current (X.patternNames pattern)) state alternatives;
        identities ((:) subject (L.append (L.map (\(XAlternative _ body) -> body) alternatives) rest)) next
      };
      _ -> identities rest state
    }
  };
  splitTyped term = case term of {
    XLet n rhs body -> let { projectionTypedLetParts = splitTyped body; rest = L.fst projectionTypedLetParts; end = L.snd projectionTypedLetParts } in (,) ((:) (LetEntry n rhs) rest) end;
    XLetRec bindings body -> let { projectionTypedRecParts = splitTyped body; rest = L.fst projectionTypedRecParts; end = L.snd projectionTypedRecParts } in (,) ((:) (RecEntry bindings) rest) end;
    _ -> (,) [] term
  };
  splitErased term = case term of {
    XELet n rhs body -> let { projectionErasedLetParts = splitErased body; rest = L.fst projectionErasedLetParts; end = L.snd projectionErasedLetParts } in (,) ((:) (ErasedLet n rhs) rest) end;
    XELetRec bindings body -> let { projectionErasedRecParts = splitErased body; rest = L.fst projectionErasedRecParts; end = L.snd projectionErasedRecParts } in (,) ((:) (ErasedRec bindings) rest) end;
    _ -> (,) [] term
  };
  entryNames entry = case entry of {
    LetEntry n _ -> [n]; RecEntry bindings -> L.map (\((,,) n _ _) -> n) bindings
  };
  erasedNames entry = case entry of {
    ErasedLet n _ -> [n]; ErasedRec bindings -> L.map (\((,) n _) -> n) bindings
  };
  decision index label names dependencies before after used keep = J.Object [
    ("index", J.num index), ("kind", J.String label),
    ("binding_ids", namesJson names), ("rhs_free_ids", sorted dependencies),
    ("demanded_ids", sorted used), ("keep", J.Boolean keep),
    ("need_before", sorted before), ("need_after", sorted after)];

  typedBack index entries body = case entries of {
    [] -> (,,) body (freeTyped body) [];
    (:) entry rest -> case typedBack (index + 1) rest body of {
      (,,) continuation needed rows -> let {
        names = entryNames entry; bound = ids names;
        used = IS.intersection needed bound; keep = L.not (IS.null used);
        dependencies = case entry of {
          LetEntry _ rhs -> freeTyped rhs;
          RecEntry bindings -> IS.difference
            (unionMany (L.map (\((,,) _ _ rhs) -> freeTyped rhs) bindings)) bound
        };
        next = if keep then IS.union (IS.difference needed bound) dependencies else needed;
        result = if keep then case entry of {
          LetEntry n rhs -> XLet n rhs continuation;
          RecEntry bindings -> XLetRec bindings continuation
        } else continuation;
        label = case entry of { LetEntry _ _ -> "let"; RecEntry _ -> "letrec" }
      } in (,,) result next ((:) (decision index label names dependencies needed next used keep) rows)
    }
  };
  -- Separate erased traversal and reconstruction. It does not call typedBack.
  erasedBack index entries body = case entries of {
    [] -> (,,) body (freeErased body) [];
    (:) entry rest -> case erasedBack (index + 1) rest body of {
      (,,) continuation demand decisions -> let {
        names = erasedNames entry; local = ids names;
        selected = IS.intersection local demand; retained = L.not (IS.null selected);
        free = case entry of {
          ErasedLet _ expression -> freeErased expression;
          ErasedRec definitions -> IS.difference
            (L.foldl IS.union IS.empty (L.map (\((,) _ expression) -> freeErased expression) definitions)) local
        };
        remaining = if retained then IS.union free (IS.difference demand local) else demand;
        output = if retained then case entry of {
          ErasedLet n expression -> XELet n expression continuation;
          ErasedRec definitions -> XELetRec definitions continuation
        } else continuation;
        label = case entry of { ErasedLet _ _ -> "let"; ErasedRec _ -> "letrec" }
      } in (,,) output remaining
        ((:) (decision index label names free demand remaining selected retained) decisions)
    }
  };

  projectChecked :: K.CheckedTerm -> Either String Projection;
  projectChecked supplied = do {
    boundEvidence (Evidence.rawTerm (K.term supplied));
    identities [K.term supplied] ((,) IS.empty IM.empty);
    before <- K.check (K.term supplied);
    L.ensure (T.alphaEq (K.typeOf supplied) (K.typeOf before)) "supplied module checked type differs";
    let { projectionDeclarationParts = case K.term before of {
      XWithData ds value -> (,) (Just ds) value;
      value -> (,) Nothing value
    }; declarations = L.fst projectionDeclarationParts; body = L.snd projectionDeclarationParts;
       projectionSpineParts = splitTyped body; spine = L.fst projectionSpineParts; end = L.snd projectionSpineParts };
    L.ensure (L.length spine <= 4096) "module declaration spine exceeds 4096";
    case end of { XWithData _ _ -> Left "nested declaration scope on module spine"; _ -> Right () };
    let { erasedOriginal = X.erase (K.term before); projectionErasedSpineParts = splitErased erasedOriginal;
          erasedSpine = L.fst projectionErasedSpineParts; erasedEnd = L.snd projectionErasedSpineParts };
    L.ensure (noErasedHole erasedOriginal) "unresolved source evidence hole in checked module";
    L.ensure (X.equalList (X.equalList X.equalName)
      (L.map entryNames spine) (L.map erasedNames erasedSpine))
      "type erasure exposes a different declaration spine; wrapper commuting forbidden";
    case typedBack 0 spine end of { (,,) transformed remaining witness -> do {
      L.ensure (IS.null remaining) "module projection leaves external term identities";
      let { term = case declarations of { Nothing -> transformed; Just ds -> XWithData ds transformed } };
      case erasedBack 0 erasedSpine erasedEnd of { (,,) erasedProjected erasedRemaining erasedWitness -> do {
        L.ensure (IS.null erasedRemaining) "erased module projection leaves external identities";
        L.ensure (eqString (J.render (J.Array witness)) (J.render (J.Array erasedWitness)))
          "typed and erased module dependency witnesses differ";
        L.ensure (X.equalErased (X.erase term) erasedProjected)
          "projected typed erasure differs from independent erased projection";
        after <- K.check term;
        L.ensure (T.alphaEq (K.typeOf before) (K.typeOf after)) "module projection changed root type";
        Right (Projection before after witness)
      } }
    } }
  };
  evidence value = J.Object [
    ("policy", J.String "outer-lazy-spine/1"),
    ("original_checked_type", Evidence.rawType (K.typeOf (original value))),
    ("projected_checked_type", Evidence.rawType (K.typeOf (projected value))),
    ("projected_annotated", Evidence.rawTerm (K.term (projected value))),
    ("projected_erased", Evidence.rawErased (X.erase (K.term (projected value)))),
    ("steps", J.Array (steps value)), ("original_rechecked", J.Boolean True),
    ("projected_rechecked", J.Boolean True), ("root_type_alpha_equal", J.Boolean True),
    ("declarations_equal", J.Boolean True), ("erased_projection_equal", J.Boolean True)];
}
