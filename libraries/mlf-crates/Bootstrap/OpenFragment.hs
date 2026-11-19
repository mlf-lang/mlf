-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.OpenFragment
  (Environment, environment, declarations, dataEnvironment, Fragment, check, fromChecked,
   parameters, body, bodyValue, storageValue, checkedStorageValue, bindings, usedParameters, context, fingerprint,
   normalize, withNameHints, encodeBody, encodeRaw, encodeCheckedRaw, decodeTrusted, decodeTrustedIds, audit, closedTerm, fresh, linkBody,
   Package, makePackage, makeCheckedPackage, readPackage, readPackageProfiled, packageFragments, packageBytes,
   packageHash, packageMetadata, packageFamily, declarationValue, compatibilityIdentity,
   MetadataReceipt, makeMetadataReceipt, metadataReceiptHash, withMetadataReceipt, cachedMetadata) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Host as Host;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as T;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.EvidenceBoundary as Boundary;
  import qualified Bootstrap.Bitstream as W;
  import qualified Bootstrap.ArtifactStructure as Structure;
  import qualified Bootstrap.ArtifactStorage as Storage;
  import qualified Bootstrap.QueryGraph as QueryGraph;

  -- Environments and receipts are immutable. The constructor is private;
  -- decoding below is the only trusted-disk admission, after a byte SHA match.
  data Environment = Environment ([] DataDecl) DataEnv;
  environment ds = mapEither (Environment ds) (D.validateDeclarations ds);
  -- DataDecl and an all-Star DataDeclK denote the same declaration. Bound
  -- parameter spellings and saturated application syntax are not identities.
  canonicalField scope depth field = case field of {
    Parameter name -> Parameter (M.findWithDefault compareString name name scope);
    Function a b -> Function (canonicalField scope depth a) (canonicalField scope depth b);
    Applied name arguments -> Applied name (map (canonicalField scope depth) arguments);
    Application a b -> let { function = canonicalField scope depth a; argument = canonicalField scope depth b }
      in case function of { Applied name args -> Applied name (snoc args argument); _ -> Application function argument };
    Quantified name kind body -> let { fresh = "type:" ++ showInt depth } in
      Quantified fresh kind (canonicalField (M.insert compareString name fresh scope) (depth + 1) body)
  };
  canonicalDeclaration declaration = let {
    binders = D.datatypeBinders declaration;
    normalized = map (\((,) index ((,) _ kind)) -> (,) ("type:" ++ showInt index) kind)
      (zip (range 0 (length binders - 1)) binders);
    scope = M.fromList compareString (zip (map fst binders) (map fst normalized))
  } in DataDeclK (D.datatypeName declaration) normalized (map (\(ConstructorDecl name fields) ->
    ConstructorDecl name (map (canonicalField scope (length binders)) fields)) (D.datatypeConstructors declaration));
  declarationValue declaration = Structure.toDataDecl (canonicalDeclaration declaration);
  declarations (Environment ds _) = ds;
  dataEnvironment (Environment _ ds) = ds;
  -- Derive the wire tree once from the exact immutable checked term. The
  -- bytes for each envelope still go through their own ordinary writer.
  -- The flag selects schema 10 only when a ground instantiation is present.
  data StoredTerm = StoredTerm Bool W.Value;
  storedWire (StoredTerm _ value) = value;
  hasGroundRows (StoredTerm ground _) = ground;
  -- A compact view belongs to the exact bytes that passed the package's
  -- expanded-work and first-use checks. Unpublished fragments retain their
  -- ordinary linking behavior, including demand for individual fields.
  data LinkView = LinkPattern Structure.TermPattern | LinkLambda LinkView |
    LinkLet (Maybe LinkView) (Maybe LinkView);
  data Fragment = Fragment Environment ([] ((,) XName XType)) XTerm
    ([] ((,) XName XType)) ([] XName) String W.Value (Maybe StoredTerm) (Maybe StoredTerm) (Maybe LinkView);
  fragmentWith env ps term bs used saved =
    let { raw = Structure.toXTerm term } in Fragment env ps term bs used saved raw (compactTerm term) (compactTermWith spinePattern term) Nothing;
  context (Fragment env _ _ _ _ _ _ _ _ _) = env;
  parameters (Fragment _ ps _ _ _ _ _ _ _ _) = ps;
  body (Fragment _ _ term _ _ _ _ _ _ _) = term;
  bodyValue (Fragment _ _ _ _ _ _ value _ _ _) = value;
  fragmentStorage (Fragment _ _ _ _ _ _ _ stored _ _) = stored;
  fragmentLinkView (Fragment _ _ _ _ _ _ _ _ _ view) = view;
  fragmentSpineStorage (Fragment _ _ _ _ _ _ _ _ stored _) = stored;
  checkedStorageValue fragment = mapOptional snd (selectedStorage True fragment);
  storageValue fragment = mapOptional storedWire (fragmentStorage fragment);
  -- Rows retain variables, ground variable instantiations, primitives, literal
  -- slots and applications of two earlier rows. Literal slots consume the
  -- signed integer stream in source order, including repeated subtrees.
  data PatternTable = PatternTable Int ([] W.Value)
    (IntMap Int) (Map ((,) Int String) Int) (IntMap Int) (Map ((,) Int ((,) String String)) Int);
  data LiteralStream = LiteralStream Int Int Int Int Int ([] W.Value);
  finishRun count first last step tail = if count == 0 then tail else
    if count == 1 then (:) (W.VInt first) tail else
    if count == 2 then (:) (W.VInt last) ((:) (W.VInt first) tail)
    else (:) (W.VNode 89 [W.VInt first,W.VInt step,W.VInt count]) tail;
  addLiteral value (LiteralStream size count first last step tail) = let {
    next = size + 1;
    diff = value - last;
    following = count + 1
  } in seq next (if count == 0 then LiteralStream next 1 value value 0 tail
    else if count == 1 || diff == step then seq diff (seq following (LiteralStream next following first value diff tail))
    else LiteralStream next 1 value value 0 (finishRun count first last step tail));
  data PatternVisit = NoPattern | Visited Int Int PatternTable LiteralStream;
  -- The format limits nesting to 128. Thread each completed child directly
  -- into its parent, preserving postorder numbering and the occurrence budget.
  expressionPattern value = let {
    visit depth fuel table@(PatternTable count entries pairs names primitives ground) stream term complete =
      if fuel < 0 || depth > 128 then NoPattern else let {
        remaining = fuel - 1;
        finish i nextTable nextStream = if remaining < 0 then NoPattern else complete i remaining nextTable nextStream;
        save node nextNames nextPrimitives nextGround = if count >= 512 then NoPattern else let { next = count + 1 } in
          seq next (finish count (PatternTable next ((:) node entries) pairs nextNames nextPrimitives nextGround) stream);
        -- Successful atom lookups already have a postorder row. A miss
        -- returns to the ordinary first-use writer before inspecting its sibling.
        known atom = case atom of {
          XVarTerm (XName i hint) -> M.lookup (comparePair compareInt compareString) ((,) i hint) names;
          XTypeApp (XVarTerm (XName i hint)) (XThen (XInner (XBottom (XCon ty []))) XElim) ->
            M.lookup (comparePair compareInt (comparePair compareString compareString)) ((,) i ((,) hint ty)) ground;
          XPrimitive p args -> case args of {
            [] -> IM.lookup (Structure.primitiveCode p) primitives; _ -> Nothing
          };
          _ -> Nothing
        };
        joined l h rest current@(PatternTable size nodes apps ns ps gs) literals = let {
              key = l * 512 + h
            } in case IM.lookup key apps of {
              Just i -> complete i rest current literals;
              Nothing -> if size >= 512 then NoPattern else let {
                next = size + 1; row = W.VNode 88 [W.VInt l,W.VInt h]
              } in seq next (complete size rest (PatternTable next ((:) row nodes) (IM.insert key size apps) ns ps gs) literals)
            };
        application left right = let {
          afterLeft l available leftTable leftStream =
            visit (depth + 1) available leftTable leftStream right (joined l);
          ordinary = visit (depth + 1) remaining table stream left afterLeft
        } in if depth >= 128 || remaining <= 0 then ordinary else case known left of {
          Nothing -> ordinary;
          Just l -> afterLeft l (remaining - 1) table stream
        }
      } in case term of {
        XApp left right -> application left right;
        XIntTerm integer -> let { next = addLiteral integer stream } in seq next (finish 0 table next);
        XVarTerm (XName i hint) -> let { key = (,) i hint } in
          case M.lookup (comparePair compareInt compareString) key names of {
            Just index -> finish index table stream;
            Nothing -> save (Structure.toXTerm term) (M.insert (comparePair compareInt compareString) key count names) primitives ground
          };
        XTypeApp (XVarTerm (XName i hint)) (XThen (XInner (XBottom (XCon ty []))) XElim) -> let {
          key = (,) i ((,) hint ty);
          order = comparePair compareInt (comparePair compareString compareString)
        } in case M.lookup order key ground of {
          Just index -> finish index table stream;
          Nothing -> save (W.VNode 85 [W.VInt i,W.VText hint,W.VText ty]) names primitives (M.insert order key count ground)
        };
        XPrimitive p args -> case args of {
          [] -> let { code = Structure.primitiveCode p } in case IM.lookup code primitives of {
            Just index -> finish index table stream;
            Nothing -> save (Structure.toXTerm term) names (IM.insert code count primitives) ground
          };
          _ -> NoPattern
        };
        _ -> NoPattern
      };
    table = PatternTable 1 [W.VNode 87 []] IM.empty M.empty IM.empty M.empty
  } in case visit 1 1048576 table (LiteralStream 0 0 0 0 0 []) value Visited of {
    NoPattern -> Nothing;
    Visited root fuel (PatternTable count entries _ _ _ ground) (LiteralStream size amount first last step tail) ->
      if size < 8 || 1048576 - fuel < count * 3 then Nothing else
        Just (StoredTerm (not (M.null ground)) (W.VNode 86
          [W.VNode 1 (reverse entries),W.VNode 1 (reverse (finishRun amount first last step tail)),W.VInt root]))
  };
  -- A run represents f1 (f2 (... tail)). Heads have the same immutable
  -- application skeleton. Each integer still consumes its own source slot.
  data SpineRows = SpineRows Int ([] W.Value) (Map ((,) ((,) Int Int) ((,) Int String)) Int) Bool;
  data SpineVisit = NoSpine | SpineVisited Int Int SpineRows LiteralStream;
  spinePattern term = let {
    order = comparePair (comparePair compareInt compareInt) (comparePair compareInt compareString);
    row kind a b text wire repeated fuel (SpineRows count rows index strong) stream done = let {
      key = (,) ((,) kind a) ((,) b text)
    } in case M.lookup order key index of {
      Just i -> done i fuel (SpineRows count rows index (strong || repeated)) stream;
      Nothing -> if count >= 512 then NoSpine else let {
        next = count + 1; updated = M.insert order key count index
      } in seq next (seq updated (done count fuel
        (SpineRows next ((:) wire rows) updated (strong || repeated)) stream))
    };
    -- The first head has already been visited in source order and has at
    -- most 64 syntax nodes. A failed comparison discards its literal state.
    match first later literals = case first of {
      XIntTerm _ -> case later of {
        XIntTerm value -> let { next = addLiteral value literals } in seq next (Just next); _ -> Nothing };
      XVarTerm (XName i hint) -> case later of {
        XVarTerm (XName j text) -> if i == j && eqString hint text then Just literals else Nothing;
        _ -> Nothing };
      XConstructor name [] -> case later of {
        XConstructor other [] -> if eqString name other then Just literals else Nothing; _ -> Nothing };
      XPrimitive p [] -> case later of {
        XPrimitive other [] -> if Structure.primitiveCode p == Structure.primitiveCode other then Just literals else Nothing;
        _ -> Nothing };
      XApp f x -> case later of {
        XApp g y -> case match f g literals of { Just state -> match x y state; Nothing -> Nothing };
        _ -> Nothing };
      _ -> Nothing
    };
    visit depth fuel table stream value done = if depth > 128 || fuel <= 0 then NoSpine else let {
      next = fuel - 1;
      atom kind id text = row kind id 0 text (Structure.toXTerm value) False next table stream done
    } in case value of {
      XIntTerm n -> let { updated = addLiteral n stream } in seq updated (done 0 next table updated);
      XVarTerm (XName i hint) -> atom 0 i hint;
      XConstructor name [] -> atom 1 0 name;
      XPrimitive p [] -> atom 2 (Structure.primitiveCode p) "";
      XApp f x -> visit (depth + 1) next table stream f (\left remaining after fields -> let {
        width = next - remaining;
        finish count tail available literals = visit (depth + 1) available after literals tail
          (\right rest rows slots -> let {
            pair = left * 512 + right;
            children = if count == 1 then [W.VInt left,W.VInt right] else [W.VInt left,W.VInt right,W.VInt count]
          } in row 3 pair count "" (W.VNode 88 children) (count >= 8) rest rows slots done);
        heads count tail available literals = if width > 64 then finish count tail available literals else case tail of {
          XApp nextHead more -> if count >= W.maxDepth W.defaultLimits || available <= width then NoSpine
            else case match f nextHead literals of {
              Nothing -> finish count tail available literals;
              Just updated -> let { total = count + 1; rest = available - width - 1 } in
                seq total (seq rest (heads total more rest updated))
            };
          _ -> finish count tail available literals
        }
      } in heads 1 x remaining fields);
      _ -> NoSpine
    };
    collect = case visit 1 1048576 (SpineRows 1 [W.VNode 87 []] M.empty False)
      (LiteralStream 0 0 0 0 0 []) term SpineVisited of {
      SpineVisited root _ (SpineRows _ rows _ True) (LiteralStream size n first last step tail) ->
        if size < 8 then Nothing else Just (StoredTerm False (W.VNode 86
          [W.VNode 1 (reverse rows),W.VNode 1 (reverse (finishRun n first last step tail)),W.VInt root]));
      _ -> Nothing
    }
  } in case term of {
    XApp _ (XApp _ (XApp _ (XApp _ _))) -> collect;
    _ -> Nothing
  };
  compactNode tag fields = let {
      replace rest = case rest of {
        [] -> Nothing;
        (:) ((,) raw changed) tail -> case changed of {
          Nothing -> mapOptional ((:) raw) (replace tail);
          Just updated -> Just ((:) (storedWire updated)
            (map (\((,) plain option) -> fromMaybe plain (mapOptional storedWire option)) tail))
        }
      };
      ground = any (\field -> case snd field of { Just value -> hasGroundRows value; Nothing -> False }) fields
    } in mapOptional (\children -> StoredTerm ground (W.VNode tag children)) (replace fields);
  compactTerm = compactTermWith expressionPattern;
  compactTermWith applications term = let {
    still value = (,) value Nothing;
    child value = (,) (Structure.toXTerm value) (compactTermWith applications value);
    node = compactNode;
    binding row@((,,) name ty body) = (,) (Structure.toTriple Structure.toXName Structure.toXType Structure.toXTerm row)
      (node 3 [still (Structure.toXName name),still (Structure.toXType ty),child body]);
    alternative row@(XAlternative pat body) = (,) (Structure.toXAlternative row)
      (node 92 [still (Structure.toXPattern pat),child body]);
    list values = (,) (W.VNode 1 (map fst values)) (node 1 values)
  } in case term of {
    XApp _ _ -> applications term;
    XAbs n ty b -> node 71 [still (Structure.toXName n),still (Structure.toXType ty),child b];
    XTypeAbs v ty b -> node 73 [still (Structure.toXTyVar v),still (Structure.toXType ty),child b];
    XTypeApp f p -> node 74 [child f,still (Structure.toXComputation p)];
    XLet n rhs b -> node 75 [still (Structure.toXName n),child rhs,child b];
    XLetRec defs b -> node 76 [list (map binding defs),child b];
    XCase scrut ty alts -> node 83 [child scrut,still (Structure.toXType ty),list (map alternative alts)];
    XWithData ds b -> node 84 [still (Structure.toList Structure.toDataDecl ds),child b];
    _ -> Nothing
  };
  bindings (Fragment _ _ _ bs _ _ _ _ _ _) = bs;
  usedParameters (Fragment _ _ _ _ used _ _ _ _ _) = used;
  fingerprint (Fragment _ _ _ _ _ stamp _ _ _ _) = stamp;
  -- The fingerprint frames each field with its Unicode scalar length. Hash
  -- successive pages of pretty-printer output while counting that length,
  -- then prepend the length with the same polynomial composition as pack.
  termEncoding term = let {
    -- Long repeated chunks, such as qualified names, have the same length
    -- and polynomial contribution at every occurrence. Bound the number
    -- and size of saved pieces within this term.
    flush page count a b next = case page of {
      [] -> next count a b;
      _ -> let { text = concatStringList (reverse page); size = stringLength text;
                 total = count + size } in case Separate.canonicalFingerprintText text 0 size a b of {
        (,) x y -> seq total (seq x (seq y (next total x y)))
      }
    };
    finish count a b = Separate.FingerprintEncoding count
      (Separate.fingerprintPower 65599 count 2147483647)
      (Separate.fingerprintPower 131 count 2147483629) a b;
    consume chunks page slots saved count a b = case chunks of {
      [] -> flush page count a b finish;
      (:) piece rest -> seq piece (let {
        size = stringLength piece;
        buffered = (:) piece page;
        ordinary = if slots == 1 then flush buffered count a b
          (consume rest [] 128 saved) else consume rest buffered (slots - 1) saved count a b;
        reuse pool encoded start x y = case Separate.encodingState ((,) x y) encoded of {
          (,) u v -> let { total = start + size } in
            seq total (seq u (seq v (consume rest [] 128 pool total u v)))
        }
      } in if size < 32 || size > 4096 then ordinary else case M.lookup compareString piece saved of {
        Just encoded -> flush page count a b (reuse saved encoded);
        Nothing -> if M.size saved >= 32 then ordinary else let {
          encoded = Separate.encodingText piece;
          next = M.insert compareString piece encoded saved
        } in flush page count a b (reuse next encoded)
      })
    }
  } in consume (Pretty.termChunks 0 term []) [] 128 M.empty 0 0 0;
  -- Between two literal slots each scalar is fixed by the application table.
  -- Summarize these strings once, including the parentheses on right children.
  data StampText = StampText Separate.FingerprintEncoding |
    StampSlots Separate.FingerprintEncoding StampHoles Separate.FingerprintEncoding;
  data StampHoles = StampHole | StampJoin StampHoles Separate.FingerprintEncoding StampHoles;
  stampJoin left right = case (,) left right of {
    (,) (StampText a) (StampText b) -> StampText (Separate.encodingAppend a b);
    (,) (StampText a) (StampSlots p xs q) -> StampSlots (Separate.encodingAppend a p) xs q;
    (,) (StampSlots p xs q) (StampText b) -> StampSlots p xs (Separate.encodingAppend q b);
    (,) (StampSlots p xs q) (StampSlots s ys t) -> StampSlots p (StampJoin xs (Separate.encodingAppend q s) ys) t
  };
  stampSyntax value = StampText (Separate.encodingText value);
  stampTable entries = let {
    build index table rest = case rest of {
      [] -> Just table;
      (:) entry more -> let {
        add plain arg = build (index + 1) (IM.insert index ((,) plain arg) table) more;
        leaf text = let { plan = stampSyntax text } in add plan plan
      } in case entry of {
        W.VNode 87 [] -> let { hole = StampSlots Separate.encodingEmpty StampHole Separate.encodingEmpty } in add hole hole;
        W.VNode 70 [W.VNode 31 [W.VInt i,W.VText hint]] -> leaf (Pretty.name (XName i hint));
        W.VNode 85 [W.VInt i,W.VText hint,W.VText ty] -> leaf (Pretty.prettyTerm (Structure.groundVariable i hint ty));
        W.VNode 81 [p,W.VNode 1 []] -> case Structure.fromPrimitive p of {
          Right primitive -> leaf (Pretty.prettyTerm (XPrimitive primitive [])); Left _ -> Nothing
        };
        W.VNode 88 [W.VInt l,W.VInt r] -> case (,) (IM.lookup l table) (IM.lookup r table) of {
          (,) (Just ((,) f _)) (Just ((,) _ a)) -> let {
            plain = stampJoin f (stampJoin (stampSyntax " ") a);
            arg = stampJoin (stampSyntax "(") (stampJoin plain (stampSyntax ")"))
          } in add plain arg;
          _ -> Nothing
        };
        _ -> Nothing
      }
    }
  } in build 0 IM.empty entries;
  stampLiterals runs = let {
    more raw = case raw of {
      [] -> [];
      (:) row rest -> case row of {
        W.VInt n -> (:) n (more rest);
        W.VNode 89 [W.VInt start,W.VInt step,W.VInt size] -> rangeRun start step size rest;
        _ -> []
      }
    };
    rangeRun start step size rest = if size <= 0 then more rest else (:) start (rangeRun (start + step) step (size - 1) rest)
  } in more runs;
  data StampState = StampState Int Int Int ([] Int);
  stampFixed piece (StampState count a b literals) = let { total = count + Separate.encodingLength piece } in
    case Separate.encodingState ((,) a b) piece of { (,) x y -> seq total (seq x (seq y (StampState total x y literals))) };
  -- A literal contributes its signed decimal spelling to both scalar hashes.
  -- Keep the magnitude nonpositive so the minimum Int has a representation.
  -- Two ASCII digits advance the same canonical residues as two scalar steps.
  stampDigits width factorA factorB digitsA digitsB (StampState count a b rest) = let {
    total = count + width;
    x = (a * factorA + digitsA) % 2147483647;
    y = (b * factorB + digitsB) % 2147483629
  } in seq total (seq x (seq y (StampState total x y rest)));
  stampPairCodes n = let {
    tens = quotInt n 10; first = 48 + tens; last = 48 + n - tens * 10
  } in (,) (first * 65599 + last) (first * 131 + last);
  decimalStampPairs :: V.IndexVec Int ((,) Int Int);
  decimalStampPairs = V.fromList (map stampPairCodes (range 0 99));
  stampInteger value initial = let {
    single code = stampDigits 1 65599 131 code code;
    pair n current = case V.at decimalStampPairs (V.fromInt n) of {
      (,) a b -> stampDigits 2 8261507 17161 a b current
    };
    digits n current = if n > (0 - 10) then single (48 - n) current else let {
      higher = quotInt n 100; low = higher * 100 - n
    } in pair low (if higher == 0 then current else digits higher current)
  } in if value < 0 then digits value (single 45 initial) else digits (0 - value) initial;
  stampHoles holes state = case holes of {
    StampHole -> case state of {
      StampState count a b ((:) value rest) -> let {
        next = stampInteger value (StampState count a b rest)
      } in seq next (Just next);
      _ -> Nothing
    };
    StampJoin left piece right -> case stampHoles left state of {
      Nothing -> Nothing; Just next -> stampHoles right (stampFixed piece next)
    }
  };
  patternEncoding entries runs root = case stampTable entries of {
    Nothing -> Nothing;
    Just table -> case IM.lookup root table of {
      Just ((,) (StampSlots prefix holes suffix) _) -> case stampHoles holes
        (stampFixed prefix (StampState 0 0 0 (stampLiterals runs))) of {
        Nothing -> Nothing;
        Just next -> case stampFixed suffix next of {
          StampState count a b [] -> Just (Separate.FingerprintEncoding count
            (Separate.fingerprintPower 65599 count 2147483647) (Separate.fingerprintPower 131 count 2147483629) a b);
          _ -> Nothing
        }
      };
      _ -> Nothing
    }
  };
  stampThen first next = case first of {
    Separate.FingerprintEncoding n pa pb a b -> seq n (seq a (seq b (Separate.encodingAppend first next)))
  };
  -- The compact writer may inspect literal differences to select runs. Before
  -- using that table for a fingerprint, force leaf spellings in the same order
  -- as the logical pretty printer. A non-application leaf outside this grammar
  -- returns directly to that printer, including its original demand order.
  orderedPatternLeaves depth remaining term = if depth > 128 || remaining <= 0 then 0 else
    let { next = remaining - 1 } in case term of {
      XApp f a -> let { fuel = orderedPatternLeaves (depth + 1) next f } in
        if fuel <= 0 then 0 else orderedPatternLeaves (depth + 1) fuel a;
      XIntTerm value -> seq value next;
      XVarTerm (XName i hint) -> seq hint (seq i next);
      XTypeApp (XVarTerm (XName i hint)) proof -> seq hint (seq i (case proof of {
        XThen (XInner (XBottom (XCon ty arguments))) end -> case arguments of {
          [] -> seq ty (case end of { XElim -> next; _ -> 0 }); _ -> 0
        };
        _ -> 0
      }));
      XPrimitive p args -> seq p (case args of { [] -> next; _ -> 0 });
      _ -> 0
    };
  -- Reuse the exact physical table at every root whose fingerprint uses the
  -- same typed application grammar. Either view can be requested first.
  termViews term = case term of {
    XLet name rhs body -> let {
      left = termViews rhs; right = termViews body;
      stored = compactNode 75 [(,) (Structure.toXName name) Nothing,
        (,) (Structure.toXTerm rhs) (fst left),(,) (Structure.toXTerm body) (fst right)];
      summary = stampThen (Separate.encodingText ("let " ++ Pretty.name name ++ " = "))
        (stampThen (snd left) (stampThen (Separate.encodingText " in ") (snd right)))
    } in (,) stored summary;
    XAbs name ty body -> let {
      nested = termViews body;
      stored = compactNode 71 [(,) (Structure.toXName name) Nothing,(,) (Structure.toXType ty) Nothing,
        (,) (Structure.toXTerm body) (fst nested)];
      summary = stampThen (Separate.encodingText ("\\(" ++ Pretty.name name ++ " : " ++ Pretty.prettyType ty ++ ") -> "))
        (snd nested)
    } in (,) stored summary;
    XApp _ _ -> let {
      stored = expressionPattern term;
      plain = termEncoding term;
      summary = if orderedPatternLeaves 1 1048577 term > 0 then case stored of {
        Just (StoredTerm _ (W.VNode 86 [W.VNode 1 rows,W.VNode 1 runs,W.VInt root])) ->
          fromMaybe plain (patternEncoding rows runs root);
        _ -> plain
      } else plain
    } in (,) stored summary;
    _ -> (,) (compactTerm term) (termEncoding term)
  };
  checkedFragment env ps term bs used = let {
    views = termViews term;
    saved = stampEncoding env ps (snd views) bs
  } in Fragment env ps term bs used saved (Structure.toXTerm term) (fst views) (compactTermWith spinePattern term) Nothing;
  stamp env ps term bs = stampEncoding env ps (termEncoding term) bs;
  stampEncoding env ps summary bs = Separate.encodingFingerprint (Separate.encodingPack
    [Separate.encodingText (Separate.pack (map (compose D.prettyDeclaration canonicalDeclaration) (declarations env))),
     Separate.encodingText (Separate.pack (map (\((,) n ty) -> Separate.pack [showInt (X.nameId n), X.nameHint n, Pretty.prettyType (Separate.normalType ty)]) ps)),
     summary,
     Separate.encodingText (Separate.pack (map (\((,) n ty) -> Separate.pack [X.nameHint n, Pretty.prettyType (Separate.normalType ty)]) bs))]);
  make env ps term bs = checkedFragment env ps term bs (Boundary.nubNames (Boundary.freeNames term));
  -- Hints are labels, never binder identities. This transformation starts from
  -- an opaque checked fragment and changes every occurrence consistently. It
  -- preserves the environment, all IDs, types, evidence and free-use inventory;
  -- callers cannot attach a different type or an unchecked term through it.
  withNameHints hints fragment = let {
    rename n = XName (X.nameId n) (M.findWithDefault compareInt (X.nameHint n) (X.nameId n) hints);
    ps = map (\((,) n ty) -> (,) (rename n) ty) (parameters fragment);
    term = Separate.mapTerm rename (\v -> v) (body fragment);
    bs = map (\((,) n ty) -> (,) (rename n) ty) (bindings fragment);
    env = context fragment
  } in checkedFragment env ps term bs (map rename (usedParameters fragment));
  check :: Environment -> [] ((,) XName XType) -> XTerm -> Either String Fragment;
  check env@(Environment _ ds) ps term = do {
    let { names = map fst ps };
    ensure (length names == length (nubBy X.equalName names)) "duplicate open-fragment parameter";
    let { scope = XEnv M.empty (M.fromList X.compareName ps) };
    mapM_ (Check.termType ds M.empty) (map snd ps);
    answer <- Check.inferDeclarationSpine ds scope term;
    owned <- snd answer;
    ensure (all (\p -> S.null (T.freeVars (snd p))) owned) "open fragment exports an open type";
    Right (make env ps term owned)
  };
  fromChecked checked = do {
    let { source = Checked.term checked;
      parts = case source of { XWithData ds term -> (,) ds term; term -> (,) [] term };
      split = Separate.splitParameters (snd parts) };
    env <- environment (fst parts);
    owned <- Checked.declarationBindings checked;
    Right (make env (fst split) (snd split) owned)
  };
  -- Compatibility/export adapter only. Query IO and the new crate format use
  -- body and explicit references directly, never this materialization.
  closedTerm fragment = XWithData (declarations (context fragment))
    (foldr (\((,) n ty) rest -> XAbs n ty rest) (body fragment) (parameters fragment));
  normalize fragment term = check (context fragment) (parameters fragment) term;
  audit fragment = do {
    checked <- check (context fragment) (parameters fragment) (body fragment);
    ensure (eqString (fingerprint checked) (fingerprint fragment)) "open fragment audit mismatch";
    Right checked
  };
  -- Injective alpha-renaming preserves this exact checked environment/body.
  -- Imported identities participate even if the body never uses them.
  -- Every non-hole row is reachable, and each variable row retains its
  -- original name. Literals and applications introduce no other identities.
  linkIdentities source view seen = case (,) source view of {
    (,) _ (Just (LinkPattern (Structure.TermPattern table _ _ _ _))) ->
      IM.foldl (\ids row -> case row of {
        Structure.PatternRow (Structure.PatternAtom term) _ _ _ -> Separate.termIdentities term ids;
        _ -> ids
      }) seen table;
    (,) (XLet name a b) (Just (LinkLet left right)) ->
      linkIdentities b right (linkIdentities a left (IS.insert (X.nameId name) seen));
    (,) (XAbs name ty b) (Just (LinkLambda inner)) ->
      linkIdentities b (Just inner) (Separate.typeIdentities ty (IS.insert (X.nameId name) seen));
    _ -> Separate.termIdentities source seen
  };
  withFreshNames serial fragment action = let {
    ids = IS.toList (foldl (\seen p -> IS.insert (X.nameId (fst p)) seen)
      (linkIdentities (body fragment) (fragmentLinkView fragment) IS.empty) (parameters fragment));
    replacements = IM.fromList (zip ids (range serial (advanceIdentity serial (length ids) - 1)));
    name = \(XName n hint) -> XName (IM.get n replacements) hint;
    variable = \(XTyVar n) -> XTyVar (IM.get n replacements)
  } in action (advanceIdentity serial (length ids)) name variable;
  freshExports name fragment = map (\((,) n ty) -> (,) (name n) (Separate.normalType ty)) (bindings fragment);
  fresh serial fragment = withFreshNames serial fragment (\next name variable -> let {
    ps = map (\((,) n ty) -> (,) (name n) ty) (parameters fragment);
    term = Separate.mapTerm name variable (body fragment);
    bs = freshExports name fragment;
    renamed = checkedFragment (context fragment) ps term bs (map name (usedParameters fragment))
  } in (,) next renamed);
  -- Parameters are keyed by their original fragment identities. All other
  -- term and type identities receive the same injective renaming as fresh.
  data LinkRow = LinkFixed XTerm | LinkHole | LinkFunction XTerm LinkRow | LinkChildren LinkRow LinkRow | LinkRepeated LinkRow LinkRow Int;
  mapLinkPattern name variable (Structure.TermPattern table root runs _ _) = let {
    add prior i (Structure.PatternRow row _ _ _) = let {
      value = case row of {
        Structure.PatternHole -> LinkHole;
        Structure.PatternAtom atom -> LinkFixed (Separate.mapTerm name variable atom);
        Structure.PatternRepeat lhs rhs count -> LinkRepeated (IM.get lhs prior) (IM.get rhs prior) count;
        Structure.PatternJoin lhs rhs -> let { a = IM.get lhs prior; b = IM.get rhs prior } in
          case a of {
            LinkFixed f -> case b of {
              LinkFixed x -> LinkFixed (XApp f x);
              _ -> LinkFunction f b
            };
            _ -> LinkChildren a b
          }
      }
    } in seq value (IM.insert i value prior);
    rows = IM.foldlWithKey add IM.empty table;
    -- Keep the preceding literal's run count. Inspect it only at the next
    -- hole or at end of input, just as the tail of a consumed run is demanded.
    fill row previous start step runs done = case row of {
      LinkFixed term -> done term previous start step runs;
      LinkHole -> let { take count value delta following = let { next = value + delta } in
          seq next (done (XIntTerm value) count next delta following)
      } in if previous == 1 then case runs of {
        (:) (Structure.PatternRun count first delta) following -> take count first delta following;
        [] -> Nothing
      } else take (previous - 1) start step runs;
      LinkFunction f a -> fill a previous start step runs (\right count next stride tail ->
        done (XApp f right) count next stride tail);
      LinkRepeated head tail amount -> let {
        collect n heads old value stride remaining = if n == 0 then
          fill tail old value stride remaining (\last count next delta rest ->
            done (foldlStrict (\body f -> XApp f body) last heads) count next delta rest)
          else fill head old value stride remaining (\f count next delta rest ->
            collect (n - 1) ((:) f heads) count next delta rest)
      } in collect amount [] previous start step runs;
      LinkChildren f a -> fill f previous start step runs (\left rest value delta following -> case a of {
        LinkFixed right -> done (XApp left right) rest value delta following;
        _ -> fill a rest value delta following (\right count next stride tail ->
          done (XApp left right) count next stride tail)
      })
    }
  } in fill (IM.get root rows) 1 0 0 runs (\term previous _ _ following ->
    if previous == 1 && null following then Just term else Nothing);
  mapLinkedTerm name variable source view = let {
    ordinary = Separate.mapTerm name variable source;
    child = mapLinkedTerm name variable
  } in case (,) source view of {
    (,) _ (Just (LinkPattern plan)) -> fromMaybe ordinary (mapLinkPattern name variable plan);
    (,) (XLet binder a b) (Just (LinkLet left right)) ->
      XLet (name binder) (child a left) (child b right);
    (,) (XAbs binder ty b) (Just (LinkLambda inner)) ->
      XAbs (name binder) (Separate.mapType variable ty) (child b (Just inner));
    _ -> ordinary
  };
  linkBody serial imports fragment = withFreshNames serial fragment (\next name variable -> let {
    resolve n = M.findWithDefault X.compareName (name n) n imports
  } in (,,) next (freshExports name fragment) (mapLinkedTerm resolve variable (body fragment) (fragmentLinkView fragment)));
  -- The environment and external types are supplied from verified shared
  -- dependency nodes. This record contains their local identities, not copies.
  encodeBody stage name fragment = bodyRecord 400 stage name fragment (bodyValue fragment);
  selectedStorage :: Bool -> Fragment -> Maybe ((,) Int W.Value);
  selectedStorage spines fragment = case fragmentStorage fragment of {
    Just stored -> Just ((,) (if hasGroundRows stored then 10 else 9) (storedWire stored));
    Nothing -> if not spines then Nothing else mapOptional (\stored -> (,) 11 (storedWire stored))
      (fragmentSpineStorage fragment)
  };
  encodeRaw = encodeRawWith False;
  encodeCheckedRaw = encodeRawWith True;
  encodeRawWith spines references stage name fragment = let {
    envelope record = W.VNode 425 [references,record];
    ordinary = encodeBody stage name fragment;
    choose = case selectedStorage spines fragment of {
      Nothing -> ordinary;
      Just ((,) version term) -> let { tag = if version == 11 then 442 else if version == 10 then 441 else 440;
        record = bodyRecord tag stage name fragment term } in
        case bindEither (W.planGraph W.defaultLimits [envelope record])
          (\graph -> Structure.admitPatternsWith (version >= 10) (version == 11) graph (W.maxExpandedWork W.defaultLimits)) of {
          Right _ -> record; Left _ -> ordinary
        }
    }
    -- The ordinary record writes its header and logical fingerprint before
    -- its term. Inspect literal runs only after those earlier fields succeed.
  } in envelope (seq stage (seq name (seq (fingerprint fragment) choose)));
  bodyRecord tag stage name fragment term = W.VNode tag
    [W.VText stage, W.VText name, W.VText (fingerprint fragment),
     Structure.toList (Structure.toPair Structure.toXName (\p -> W.VText p))
       (map (\((,) n _) -> (,) n (X.nameHint n)) (parameters fragment)),
     term,
     Structure.toList (Structure.toPair Structure.toXName Structure.toXType) (bindings fragment),
     Structure.toList Structure.toXName (usedParameters fragment)];
  -- A reader cannot attach a claimed type to an AST. It must acquire the
  -- immutable bytes whose SHA came from the trusted generation/object index.
  -- The compatibility caller supplies stable names only. Number its whole
  -- expected interface once. The query driver supplies its actual slots.
  decodeTrusted path expected references stage name env parameters members = let {
    start = length parameters;
    slots = map V.fromInt (range 0 (start + length members - 1));
    ps = zipWith (\i ((,) key ty) -> (,,) i key ty) slots parameters
  } in decodeTrustedIds path expected references stage name env ps (zip (drop start slots) members);
  decodeTrustedIds :: String -> String -> [] ((,) String String) -> String -> String -> Environment ->
    [] ((,,) (V.Index Declaration) String XType) -> [] ((,) (V.Index Declaration) String) ->
    IO (Either String Fragment);
  decodeTrustedIds path expected references stage name env expectedParameters expectedMembers = do {
    acquired <- Storage.readRaw path;
    case acquired of {
      Left message -> ioReturn (Left message);
      Right bytes -> do {
        actual <- byteArrayDigest bytes;
        if not (eqString actual expected) then ioReturn (Left "open fragment payload SHA mismatch") else do {
          decoded <- W.decodeGraph W.defaultLimits 6 bytes;
          ioReturn (do {
            graph <- decoded;
            root <- case W.graphRoots graph of { [r] -> Right r; _ -> Left "open fragment root count" };
            envelope <- W.lookupGraphNode graph root;
            record <- case envelope of {
              W.GNode 425 [rs,record] -> do {
                values <- Structure.decodeGraphValue
                  (Structure.ShapeList (Structure.ShapePair Structure.ShapeText Structure.ShapeText)) graph rs;
                saved <- Structure.expectList (Structure.expectPair Structure.expectText Structure.expectText) values;
                ensure (eqList (eqPair eqString eqString) saved references) "open fragment environment version mismatch";
                Right record
              };
              _ -> Left "open fragment environment record missing"
            };
            value <- W.lookupGraphNode graph record;
            case value of {
              W.GNode tag [s,n,h,ps,t,bs,uses] -> do {
                ensure (tag == 400 || tag == 440 || tag == 441 || tag == 442) "unknown open fragment storage; rebuild cache";
                savedStage <- textAt graph s;
                savedName <- textAt graph n;
                savedStamp <- textAt graph h;
                ensure (eqString savedStage stage && eqString savedName name) "open fragment stage/owner mismatch";
                rawParameters <- decodedList
                  (Structure.ShapePair Structure.ShapeXName Structure.ShapeText) graph ps;
                pairs <- traverseEither (Structure.expectPair Structure.expectXName Structure.expectText) rawParameters;
                ensure (length pairs == length expectedParameters) "open fragment dependency inventory mismatch";
                let { ids = append (map (\((,,) i _ _) -> V.toInt i) expectedParameters)
                        (map (compose V.toInt fst) expectedMembers) };
                ensure (IS.size (IS.fromList ids) == length ids) "duplicate open fragment declaration";
                typed <- traverseEither (\((,) ((,) binder key) ((,,) _ stable ty)) -> do {
                  ensure (eqString (X.nameHint binder) key) "open fragment parameter identity mismatch";
                  ensure (eqString key stable) "open fragment dependency inventory mismatch";
                  Right ((,) binder ty)
                }) (zip pairs expectedParameters);
                term <- if tag == 400 then Structure.fromGraphXTerm graph t else Structure.storedTermWith (tag >= 441) (tag == 442) graph t;
                ownedValues <- decodedList
                  (Structure.ShapePair Structure.ShapeXName Structure.ShapeXType) graph bs;
                owned <- traverseEither (Structure.expectPair Structure.expectXName Structure.expectXType) ownedValues;
                ensure (eqList eqString (sortBy compareString (map (compose X.nameHint fst) owned))
                  (sortBy compareString (map snd expectedMembers))) "open fragment member inventory mismatch";
                usedValues <- decodedList Structure.ShapeXName graph uses;
                used <- traverseEither Structure.expectXName usedValues;
                validateBinders typed owned used;
                let { result = fragmentWith env typed term owned used savedStamp };
                -- ICH verification is serialization/fingerprint verification,
                -- independent of the explicit semantic-audit operation.
                Right result
              };
              _ -> Left "unsupported open fragment record"
            }
          })
        }
      }
    }
  };
  -- XName IDs are fragment-local. A used reference must identify the same
  -- binder and carry its recorded hint; the hint alone never binds an XName.
  validateBinders parameters owned used = let {
    ps = map fst parameters;
    names = append ps (map fst owned);
    byId = IM.fromList (map (\n -> (,) (X.nameId n) (X.nameHint n)) ps);
    usedIds = IS.fromList (map X.nameId used);
    matches n = case IM.lookup (X.nameId n) byId of {
      Just key -> eqString key (X.nameHint n); Nothing -> False
    }
  } in do {
    ensure (length names == IS.size (IS.fromList (map X.nameId names))) "duplicate open fragment binder";
    ensure (length used == IS.size usedIds && all matches used) "open fragment free-reference inventory mismatch"
  };
  decodedList shape graph index = do {
    decoded <- Structure.decodeGraphValue (Structure.ShapeList shape) graph index;
    Structure.expectList (\value -> Right value) decoded
  };
  textAt graph index = do {
    value <- W.lookupGraphNode graph index;
    case value of { W.GText text -> Right text; _ -> Left "expected open fragment text" }
  };
  -- Only successful canonical schema-6 encoding can create this receipt.
  -- Retain its generic metadata fields and compact binding types separately;
  -- the expanded type encoding can be collected after hashing. Method bodies
  -- are excluded by the ordinary interface encoder, not retained as syntax.
  data MetadataReceipt = MetadataReceipt ([] W.Value) ([] ((,) String XType)) ([] W.Value) String;
  makeMetadataReceipt fields = case Structure.crateMetadataParts fields of {
    (,,,) value before bindings after -> do {
      hashed <- QueryGraph.encodeHashed value;
      ioReturn (mapEither (\((,) digest _) -> MetadataReceipt before bindings after digest) hashed)
    }
  };
  metadataReceiptHash (MetadataReceipt _ _ _ digest) = digest;
  data Package = Package String ([] ((,) String Fragment)) ByteArray String (Maybe MetadataReceipt);
  packageMetadata (Package metadata _ _ _ _) = metadata;
  packageFragments (Package _ fragments _ _ _) = fragments;
  packageBytes (Package _ _ bytes _ _) = bytes;
  packageHash (Package _ _ _ digest _) = digest;
  withMetadataReceipt receipt (Package metadata fragments bytes digest _) = do {
    manifest <- Separate.unpack metadata;
    ensure (case manifest of {
      (:) root _ -> eqString root (metadataReceiptHash receipt); [] -> False
    }) "open object metadata receipt mismatch";
    Right (Package metadata fragments bytes digest (Just receipt))
  };
  cachedMetadata fields (Package _ _ _ _ receipt) = case receipt of {
    Just (MetadataReceipt before bindings after digest) -> case Structure.crateMetadataParts fields of {
      (,,,) _ before2 bindings2 after2 ->
        if eqList sameSyntax before before2 &&
          eqList (eqPair eqString Structure.sameEncodedXType) bindings bindings2 &&
          eqList sameSyntax after after2 then Just digest else Nothing
    };
    Nothing -> Nothing
  };
  packageFormat :: String;
  packageFormat = "MLF-OPEN-CRATE-1/checker-1";
  -- packageFormat remains part of the existing semantic checker identity.
  -- Storage framing has an independent version.
  wireFormat8 :: String;
  wireFormat8 = "MLF-OPEN-CRATE-2/checker-1";
  wireFormat9 :: String;
  wireFormat9 = "MLF-OPEN-CRATE-3/checker-1";
  wireFormat10 :: String;
  wireFormat10 = "MLF-OPEN-CRATE-4/checker-1";
  wireFormat11 :: String;
  wireFormat11 = "MLF-OPEN-CRATE-5/checker-1";
  applicationFormat :: Int -> String;
  applicationFormat schema = if schema == 11 then wireFormat11 else if schema == 10 then wireFormat10 else if schema == 9 then wireFormat9 else wireFormat8;
  -- Candidate engineering resource class; qualification is required.
  packageWorkLimit :: Int;
  packageWorkLimit = Storage.maxBytes;
  -- The distinct binary schema is a committed dispatch, never a fallback to
  -- an older parser after corruption of an open object.
  packageSchema bytes = do {
    size <- lengthByteArray bytes;
    magic <- W.hasMagic bytes;
    if not magic || size < 20 then ioReturn 0 else do {
      a <- readByteArray bytes 16; b <- readByteArray bytes 17;
      c <- readByteArray bytes 18; d <- readByteArray bytes 19;
      ioReturn (if b == 0 && c == 0 && d == 0 then a else 0)
    }
  };
  packageFamily bytes = do {
    schema <- packageSchema bytes;
    ioReturn (schema == 7 || schema == 8 || schema == 9 || schema == 10 || schema == 11)
  };
  bindingReference ((,) n _) = Structure.toXName n;
  encodeFinal stored entry@((,) _ fragment) = encodeFinalWire
    (if stored then fromMaybe (bodyValue fragment) (storageValue fragment) else bodyValue fragment) entry;
  encodeFinalWire wire ((,) name fragment) = W.VNode 401
    [Structure.toText name, Structure.toText (fingerprint fragment),
     Structure.toList Structure.toText (map D.datatypeName (declarations (context fragment))),
     Structure.toList bindingReference (parameters fragment),
     wire,
     Structure.toList bindingReference (bindings fragment),
     Structure.toList Structure.toXName (usedParameters fragment)];
  hashSyntax value = do {
    encoded <- Storage.encode 6 [value];
    case encoded of { Left e -> ioReturn (Left e); Right bytes -> do {
      digest <- byteArrayDigest bytes; ioReturn (Right digest)
    } }
  };
  -- Formal artifacts are shared by emlf, package tools and library generators.
  -- Their executable hashes differ even in one build. The artifact ABI/checker
  -- version and actual builtin dictionary identify their shared interpretation;
  -- local query caches separately bind the complete producer executable SHA.
  -- Bump packageFormat whenever a checked-artifact invariant changes.
  compatibilityIdentity = hashSyntax (W.VNode 431
    [Structure.toText "MLF/shared-haskell-v1",Structure.toText packageFormat,
     Structure.toList Structure.toDataDecl D.builtinDeclarations]);
  referenceHashes encode values = do {
    hashes <- mapM (\((,) key value) -> do {
      digest <- hashSyntax (encode value);
      ioReturn (mapEither ((,) key) digest)
    }) values;
    ioReturn (sequenceEither hashes)
  };

  -- The returned remainder is derived from the SAME plan that is encoded.
  -- Single-reference limits remain defaultLimits; aggregate is remaining.
  hashSyntaxBudget remaining value =
    catchIOError (hashSyntaxBudgetChecked remaining value)
      (\error -> ioReturn (Left
        ("binary encode IO failure: " ++ textFromChars (ioeGetErrorString error))));
  hashSyntaxBudgetChecked remaining value =
    case W.planRootBounded W.defaultLimits remaining [value] of {
      Left message -> ioReturn (Left message);
      Right ((,) tables used) ->
        if used < 0 || used > remaining
        then ioReturn (Left "open crate reference-work accounting mismatch")
        else case W.layout W.defaultLimits tables of {
          Left message -> ioReturn (Left message);
          Right geometry -> do {
            encoded <- W.encodeTables 6 geometry tables;
            case encoded of {
              Left message -> ioReturn (Left message);
              Right bytes -> do {
                digest <- byteArrayDigest bytes;
                let { next = remaining - used };
                seq next (ioReturn (Right ((,) digest next)))
              }
            }
          }
        }
    };

  -- Retain one fully validated syntax value. Equal consecutive references
  -- have identical canonical bytes, but still consume their entire expanded
  -- work budget. Equality is structural, never a hash-only admission, and is
  -- bounded by the previously accepted value. No cache survives this call.
  data SyntaxHash = SyntaxHash W.Value String Int;
  sameSyntax left right = case (,) left right of {
    (,) (W.VInt a) (W.VInt b) -> a == b;
    (,) (W.VBits a) (W.VBits b) -> a == b;
    (,) (W.VText a) (W.VText b) -> eqString a b;
    (,) (W.VNode a xs) (W.VNode b ys) -> a == b && eqList sameSyntax xs ys;
    _ -> False
  };
  hashSyntaxMemo previous remaining value = case previous of {
    Just (SyntaxHash old digest used) ->
      if used <= remaining && remaining <= 2147483647 && sameSyntax old value
      then ioReturn (Right ((,,) digest (remaining - used) previous))
      else hashSyntaxFresh remaining value;
    Nothing -> hashSyntaxFresh remaining value
  };
  hashSyntaxFresh remaining value = do {
    hashed <- hashSyntaxBudget remaining value;
    ioReturn (mapEither (\((,) digest next) ->
      (,,) digest next (Just (SyntaxHash value digest (remaining - next)))) hashed)
  };
  referenceHashesBudget encode entries remaining reversed =
    referenceHashesMemo Nothing encode entries remaining reversed;
  referenceHashesMemo previous encode entries remaining reversed =
    case entries of {
      [] -> ioReturn (Right ((,) (reverse reversed) remaining));
      (:) ((,) key value) rest -> do {
        hashed <- hashSyntaxMemo previous remaining (encode value);
        case hashed of {
          Left message -> ioReturn (Left message);
          Right ((,,) digest next cached) ->
            seq next (referenceHashesMemo cached encode rest next
              ((:) ((,) key digest) reversed))
        }
      }
    };

  -- One map is also the duplicate-reference check. Its values are the same
  -- verified shared external values, not copies decoded from the package.
  validateReferencesBudget encode available references remaining checked =
    validateReferencesMemo Nothing encode available references remaining checked;
  validateReferencesMemo previous encode available references remaining checked =
    case references of {
      [] -> ioReturn (Right ((,) checked remaining));
      (:) ((,) name expected) rest ->
        if M.member compareString name checked
        then ioReturn (Left "duplicate open crate reference")
        else case M.lookup compareString name available of {
          Nothing -> ioReturn (Left ("missing open crate reference: " ++ name));
          Just value -> do {
            hashed <- hashSyntaxMemo previous remaining (encode value);
            case hashed of {
              Left message -> ioReturn (Left message);
              Right ((,,) actual next cached) ->
                if not (eqString actual expected)
                then ioReturn (Left ("open crate dependency changed: " ++ name))
                else let {
                  following = M.insert compareString name value checked
                } in seq next (seq following
                  (validateReferencesMemo cached encode available rest next following))
            }
          }
        }
    };

  -- Reading a recognized schema never retries a different parser.
  -- Both selected readers authenticate the complete original byte snapshot.
  readPackage = readPackageProfiled Nothing;
  readPackageProfiled profile bytes expected compiler metadata allBindings allDeclarations = Host.phaseIO profile "validate_ms" (do {
    schema <- packageSchema bytes;
    if schema == 8 || schema == 9 || schema == 10 || schema == 11
    then readPackage8Profiled schema profile bytes expected compiler metadata allBindings allDeclarations
    else if schema == 7
    then readPackage7Profiled profile bytes expected compiler metadata allBindings allDeclarations
    else ioReturn (Left "unsupported open crate schema; rebuild object")
  });

  data PackageHeader8 = PackageHeader8 W.Graph
    ([] ((,) String String)) ([] ((,) String String)) ([] Int) Int (Maybe (IntMap Structure.TermPattern));
  readPackage8Profiled schema profile bytes expected compiler metadata allBindings allDeclarations = do {
    auditSetting <- getEnv "MLF_QUERY_SEMANTIC_AUDIT";
    digest <- byteArrayDigest bytes;
    if not (eqString digest expected)
    then ioReturn (Left "open crate SHA mismatch")
    else do {
      decoded <- Host.phaseIO profile "wire_decode_ms" (W.decodeGraphRootBounded
        W.defaultLimits packageWorkLimit schema bytes);
      case do {
        graph <- decoded;
        roots <- case W.graphRoots graph of {
          [] -> Left "open crate root count";
          (:) header entries -> Right ((,) header entries)
        };
        case roots of {
          (,) header entries -> do {
            value <- W.lookupGraphNode graph header;
            case value of {
              W.GNode 432 [f,c,m,b,d,k] -> do {
                format <- textAt graph f;
                identity <- textAt graph c;
                association <- textAt graph m;
                ensure (eqString format (applicationFormat schema) &&
                  eqString identity compiler)
                  "open crate checker/compiler version mismatch; rebuild object";
                ensure (eqString association metadata)
                  "open crate interface mismatch";
                countNode <- W.lookupGraphNode graph k;
                savedCount <- case countNode of {
                  W.GInt count -> Right count;
                  _ -> Left "invalid open crate fragment count"
                };
                count <- W.boundedLength
                  (W.maxEdges W.defaultLimits - 1) entries;
                ensure (savedCount == count)
                  "open crate fragment count mismatch";
                bindings <- referenceList graph b;
                declarations <- referenceList graph d;
                physical <- W.graphExpandedWork graph;
                ensure (physical >= 0 && physical <= packageWorkLimit) "open crate package-work accounting mismatch";
                (,) plans available <- if schema >= 9 then do {
                  prepared <- Structure.admitPatternsWith (schema >= 10) (schema == 11) graph (packageWorkLimit - physical);
                  Right ((,) (Just (fst prepared)) (packageWorkLimit - physical - snd prepared))
                } else Right ((,) Nothing (packageWorkLimit - physical));
                seq available (Right (PackageHeader8 graph bindings declarations entries available plans))
              };
              _ -> Left "invalid open crate header"
            }
          }
        }
      } of {
        Left message -> ioReturn (Left message);
        Right (PackageHeader8 graph references dataReferences entries remaining plans) -> do {
          bs <- Host.phaseIO profile "reference_validate_ms" (validateReferencesBudget
            Structure.toXType allBindings references remaining M.empty);
          case bs of {
            Left message -> ioReturn (Left message);
            Right ((,) checkedBindings afterBindings) -> do {
              ds <- Host.phaseIO profile "reference_validate_ms" (validateReferencesBudget declarationValue
                allDeclarations dataReferences afterBindings M.empty);
              case ds of {
                Left message -> ioReturn (Left message);
                Right ((,) checkedDeclarations _) -> do {
                  -- Demand the admission result before the next phase starts.
                  let { rows = M.toList checkedBindings; types = V.fromList (map snd rows);
                    table = M.fromDistinctAscList (zip (map fst rows) (V.indices types)) };
                  headers <- Host.phaseValue profile "validate_ms" (Host.phaseEither length)
                    (prepareFinals8 graph ((,) table types) checkedDeclarations M.empty S.empty entries);
                  case headers of {
                    Left message -> ioReturn (Left message);
                    Right prepared -> do {
                  -- A fresh graph-local typed memo, with the unchanged 64Mi bound.
                  decoded <- Host.phaseValue profile "syntax_decode_ms" (Host.phaseEither length) (do {
                    let { bodies = map finalBodyIndex8 prepared };
                    values <- case plans of {
                      Nothing -> Structure.decodeGraphMany Structure.ShapeXTerm graph bodies;
                      Just table -> Structure.decodeStoredManyWith table graph bodies
                    };
                    traverseEither Structure.expectXTerm values
                  });
                  Host.phaseIO profile "fragment_validate_ms" (ioReturn (do {
                  bodies <- decoded;
                  fragments <- restoreFinals8 prepared bodies;
                  let { usedKeys = S.fromList compareString (concatMap (\((,) _ fragment) ->
                    map (compose X.nameHint fst) (append (parameters fragment) (bindings fragment))) fragments) };
                  ensure (S.size usedKeys == length rows) "open crate binding reference inventory mismatch";
                  if eqString auditSetting "1"
                    then mapM_ (compose audit snd) fragments
                    else Right ();
                  let { linked = case plans of {
                    Just table -> attachLinkViews graph table fragments;
                    Nothing -> fragments
                  } };
                  Right (Package metadata linked bytes digest Nothing)
                  }))
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  };

  data PackageFinalFields8 = PackageFinalFields8 String String Environment
    ([] ((,) XName XType)) Int ([] ((,) XName XType)) ([] XName);
  finalBodyIndex8 (PackageFinalFields8 _ _ _ _ index _ _) = index;

  prepareFinals8 graph types declarations contexts seen entries =
    case entries of {
      [] -> Right [];
      (:) index rest -> do {
        value <- W.lookupGraphNode graph index;
        case value of {
          W.GNode 401 [n,h,ds,ps,t,bs,uses] -> do {
            name <- textAt graph n;
            savedStamp <- textAt graph h;
            ensure (not (S.member compareString name seen))
              "duplicate open crate fragment";
            rawData <- decodedList Structure.ShapeText graph ds;
            names <- traverseEither Structure.expectText rawData;
            let { identity = Separate.pack names };
            env <- case M.lookup compareString identity contexts of {
              Just env -> Right env;
              Nothing -> do {
                values <- traverseEither
                  (\key -> case M.lookup compareString key declarations of {
                    Just declaration -> Right declaration;
                    Nothing -> Left "open crate datatype reference out of scope"
                  }) names;
                environment values
              }
            };
            params <- finalBindings graph types ps;
            owned <- finalBindings graph types bs;
            usedValues <- decodedList Structure.ShapeXName graph uses;
            used <- traverseEither Structure.expectXName usedValues;
            validateBinders params owned used;
            next <- prepareFinals8 graph types declarations
              (M.insert compareString identity env contexts)
              (S.insert compareString name seen) rest;
            Right ((:)
              (PackageFinalFields8 name savedStamp env params t owned used)
              next)
          };
          _ -> Left "invalid final open crate fragment"
        }
      }
    };

  restoreFinals8 :: [] PackageFinalFields8 -> [] XTerm ->
    Either String ([] ((,) String Fragment));
  restoreFinals8 prepared bodies = case prepared of {
    [] -> case bodies of {
      [] -> Right [];
      _ -> Left "open crate decoded body count mismatch"
    };
    (:) (PackageFinalFields8 name savedStamp env params _ owned used) rest ->
      case bodies of {
        [] -> Left "open crate decoded body count mismatch";
        (:) source more -> do {
          ensure (eqString savedStamp (stamp env params source owned))
            "open crate fragment fingerprint mismatch";
          next <- restoreFinals8 rest more;
          Right ((:) ((,) name
            (fragmentWith env params source owned used savedStamp)) next)
        }
      }
  };

  -- Keep the last lazy value, matching Map.fromList, for repeated references.
  referenceTable :: forall a. [] ((,) String a) -> Map String a;
  referenceTable entries = M.fromList compareString entries;
  -- Keep the admitted plans on their own fragment only. The rest of the
  -- decoded package graph can be released before linking.
  packageLinkView graph plans index = case IM.lookup index plans of {
    Just plan -> Just (LinkPattern plan);
    Nothing -> case W.lookupGraphNode graph index of {
      Right (W.GNode 71 [_,_,child]) -> mapOptional LinkLambda (packageLinkView graph plans child);
      Right (W.GNode 75 [_,lhs,body]) -> let {
        left = packageLinkView graph plans lhs; right = packageLinkView graph plans body
      } in seq left (seq right (case (,) left right of {
        (,) Nothing Nothing -> Nothing; _ -> Just (LinkLet left right)
      }));
      _ -> Nothing
    }
  };
  attachLinkViews graph plans fragments = let {
    attach rows entries = case (,) rows entries of {
      (,) ((:) ((,) label fragment) rest) ((:) index tail) -> let {
        view = case W.lookupGraphNode graph index of {
          Right (W.GNode 401 [_,_,_,_,t,_,_]) -> packageLinkView graph plans t;
          _ -> Nothing
        };
        withView = case fragment of {
          Fragment env ps source bs used stamp raw stored spines _ ->
            Fragment env ps source bs used stamp raw stored spines view
        }
      } in seq view ((:) ((,) label withView) (attach rest tail));
      _ -> rows
    }
  } in case W.graphRoots graph of {
    (:) _ entries -> attach fragments entries;
    [] -> fragments
  };
  -- Only the checked crate-session path speculates on new storage shapes.
  -- General callers retain the original field and fragment evaluation order.
  makePackage = makePackageWith False;
  makeCheckedPackage = makePackageWith True;
  makePackageWith spines compiler metadata fragments = do {
    let {
      ps = M.toList (referenceTable (concatMap
        (\((,) _ f) -> map
          (\((,) n ty) -> (,) (X.nameHint n) (Separate.normalType ty))
          (append (parameters f) (bindings f))) fragments));
      ds = M.toList (referenceTable (concatMap
        (\((,) _ f) -> map (\d -> (,) (D.datatypeName d) d)
          (declarations (context f))) fragments))
    };
    case W.boundedLength (W.maxEdges W.defaultLimits - 1) fragments of {
      Left message -> ioReturn (Left message);
      Right count -> do {
        bh <- referenceHashesBudget Structure.toXType ps packageWorkLimit [];
        case bh of {
          Left message -> ioReturn (Left message);
          Right ((,) b afterBindings) -> do {
            dh <- referenceHashesBudget declarationValue ds afterBindings [];
            case dh of {
              Left message -> ioReturn (Left message);
              Right ((,) d remaining) -> do {
                let {
                  header format = W.VNode 432
                    [Structure.toText format, Structure.toText compiler,
                     Structure.toText metadata,
                     Structure.toList
                       (Structure.toPair Structure.toText Structure.toText) b,
                     Structure.toList
                       (Structure.toPair Structure.toText Structure.toText) d,
                     W.VInt count];
                  plan entry = (,) entry (selectedStorage spines (snd entry));
                  plans = map plan fragments;
                  final ((,) entry selected) = case selected of {
                    Just ((,) _ wire) -> encodeFinalWire wire entry; Nothing -> encodeFinal False entry
                  };
                  write schema format stored = W.encodeRootsWithAtoms Structure.termAtomShapes W.defaultLimits
                    remaining schema ((:) (header format) (if stored then map final plans else map (encodeFinal False) fragments));
                  legacy = do {
                    encoded <- write 8 wireFormat8 False;
                    ioReturn (mapEither (\bytes -> (,) bytes fragments) encoded)
                  };
                  requiredSchema current entries = case entries of {
                    [] -> current;
                    (:) ((,) _ selected) rest -> case selected of {
                      Nothing -> requiredSchema current rest;
                      Just ((,) version _) -> if version == (if spines then 11 else 10) then version else requiredSchema (max current version) rest
                    }
                  };
                  schema = requiredSchema 8 plans
                };
                encoded <- if schema == 8 then legacy else do {
                  candidate <- write schema (applicationFormat schema) True;
                  case candidate of {
                    Left _ -> legacy;
                    Right bytes -> do {
                      decoded <- W.decodeGraphRootBounded W.defaultLimits remaining schema bytes;
                      case bindEither decoded (\graph -> do {
                        used <- W.graphExpandedWork graph;
                        (,) plans _ <- Structure.admitPatternsWith (schema >= 10) (schema == 11) graph (remaining - used);
                        Right (attachLinkViews graph plans fragments)
                      }) of { Left _ -> legacy; Right rows -> ioReturn (Right ((,) bytes rows)) }
                    }
                  }
                };
                case encoded of {
                  Left message -> ioReturn (Left message);
                  Right ((,) bytes rows) -> do {
                    digest <- byteArrayDigest bytes;
                    ioReturn (Right (Package metadata rows bytes digest Nothing))
                  }
                }
              }
            }
          }
        }
      }
    }
  };
  -- Only an acquired immutable object snapshot, its paired interface checksum,
  -- and checked dependency metadata can restore final receipts. No AST enters.
  readPackage7Profiled profile bytes expected compiler metadata allBindings allDeclarations = do {
    auditSetting <- getEnv "MLF_QUERY_SEMANTIC_AUDIT";
    digest <- byteArrayDigest bytes;
    if not (eqString digest expected) then ioReturn (Left "open crate SHA mismatch") else do {
      decoded <- Host.phaseIO profile "wire_decode_ms" (W.decodeGraph W.defaultLimits 7 bytes);
      case do {
        graph <- decoded;
        root <- case W.graphRoots graph of { [r] -> Right r; _ -> Left "open crate root count" };
        value <- W.lookupGraphNode graph root;
        case value of {
          W.GNode 430 [f,c,m,b,d,fs] -> do {
            format <- textAt graph f; identity <- textAt graph c; association <- textAt graph m;
            ensure (eqString format packageFormat && eqString identity compiler) "open crate checker/compiler version mismatch; rebuild object";
            ensure (eqString association metadata) "open crate interface mismatch";
            bindingRefs <- referenceList graph b;
            declarations <- referenceList graph d;
            entries <- nodeList graph fs;
            Right ((,,,) graph bindingRefs declarations entries)
          };
          _ -> Left "invalid open crate header"
        }
      } of {
        Left e -> ioReturn (Left e);
        Right ((,,,) graph bindingRefs declarations entries) -> do {
          bs <- validateReferences Structure.toXType allBindings bindingRefs;
          ds <- validateReferences declarationValue allDeclarations declarations;
          ioReturn (do {
            checkedBindings <- bs; checkedDeclarations <- ds;
            let { rows = M.toList checkedBindings; types = V.fromList (map snd rows);
              table = M.fromDistinctAscList (zip (map fst rows) (V.indices types)) };
            fragments <- decodeFinals graph ((,) table types) checkedDeclarations M.empty entries;
            let { usedKeys = S.fromList compareString (concatMap (\((,) _ fragment) ->
              map (compose X.nameHint fst) (append (parameters fragment) (bindings fragment))) fragments) };
            ensure (S.size usedKeys == length rows) "open crate binding reference inventory mismatch";
            ensure (length fragments == length (nubBy eqString (map fst fragments))) "duplicate open crate fragment";
            if eqString auditSetting "1" then mapM_ (compose audit snd) fragments else Right ();
            Right (Package metadata fragments bytes digest Nothing)
          })
        }
      }
    }
  };
  referenceList graph index = do {
    values <- Structure.decodeGraphValue (Structure.ShapeList
      (Structure.ShapePair Structure.ShapeText Structure.ShapeText)) graph index;
    rows <- Structure.expectList (Structure.expectPair Structure.expectText Structure.expectText) values;
    ensure (ascending (map fst rows)) "duplicate or unordered open crate reference";
    Right rows
  };
  ascending names = case names of {
    (:) a rest@((:) b _) -> compareString a b < 0 && ascending rest;
    _ -> True
  };
  nodeList graph index = do {
    value <- W.lookupGraphNode graph index;
    case value of { W.GNode 1 entries -> Right entries; _ -> Left "expected open crate list" }
  };
  validateReferences encode available references = do {
    checked <- mapM (\((,) name expected) -> case M.lookup compareString name available of {
      Nothing -> ioReturn (Left ("missing open crate reference: " ++ name));
      Just value -> do {
        actual <- hashSyntax (encode value);
        ioReturn (do { digest <- actual;
          ensure (eqString digest expected) ("open crate dependency changed: " ++ name);
          Right ((,) name value) })
      }
    }) references;
    ioReturn (do {
      values <- sequenceEither checked;
      ensure (length values == length (nubBy eqString (map fst values))) "duplicate open crate reference";
      Right (M.fromList compareString values)
    })
  };
  decodeFinals graph types declarations contexts entries = case entries of {
    [] -> Right [];
    (:) index rest -> do {
      value <- W.lookupGraphNode graph index;
      case value of {
        W.GNode 401 [n,h,ds,ps,t,bs,uses] -> do {
          name <- textAt graph n; savedStamp <- textAt graph h;
          rawData <- decodedList Structure.ShapeText graph ds;
          names <- traverseEither Structure.expectText rawData;
          let { identity = Separate.pack names };
          env <- case M.lookup compareString identity contexts of {
            Just env -> Right env;
            Nothing -> do {
              values <- traverseEither (\key -> case M.lookup compareString key declarations of {
                Just d -> Right d; Nothing -> Left "open crate datatype reference out of scope" }) names;
              environment values
            }
          };
          params <- finalBindings graph types ps;
          owned <- finalBindings graph types bs;
          source <- Structure.fromGraphXTerm graph t;
          usedValues <- decodedList Structure.ShapeXName graph uses;
          used <- traverseEither Structure.expectXName usedValues;
          validateBinders params owned used;
          -- Final objects retain the checked fingerprint of their own ordered
          -- parameter list. The public interface only describes all exports.
          ensure (eqString savedStamp (stamp env params source owned)) "open crate fragment fingerprint mismatch";
          let { fragment = fragmentWith env params source owned used savedStamp };
          next <- decodeFinals graph types declarations (M.insert compareString identity env contexts) rest;
          Right ((:) ((,) name fragment) next)
        };
        _ -> Left "invalid final open crate fragment"
      }
    }
  };
  finalBindings :: W.Graph -> (,) (Map String (V.Index Declaration))
    (V.IndexVec Declaration XType) -> Int -> Either String ([] ((,) XName XType));
  finalBindings graph ((,) slots types) index = do {
    raw <- decodedList Structure.ShapeXName graph index;
    names <- traverseEither Structure.expectXName raw;
    aligned <- traverseEither (\name -> case M.lookup compareString (X.nameHint name) slots of {
      Just i -> Right ((,) name i); Nothing -> Left "open crate binding reference out of scope"
    }) names;
    ensure (IS.size (IS.fromList (map (compose V.toInt snd) aligned)) == length aligned)
      "duplicate open crate binding reference";
    Right (map (\((,) name i) -> (,) name (V.at types i)) aligned)
  }
}
