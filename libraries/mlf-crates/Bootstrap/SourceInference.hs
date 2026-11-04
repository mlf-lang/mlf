-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.SourceInference where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import Bootstrap.Fresh;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.EvidenceBoundary as Boundary;
  import qualified Bootstrap.InferenceUnit as Inference;
  import qualified Bootstrap.OpenFragment as Open;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.Resolved as R;
  import qualified Bootstrap.IndexVec as V;
  import qualified Bootstrap.ST as ST;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.Data as Data;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Type as Type;
  import qualified Bootstrap.X.Checked as Checked;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.Bitstream as Wire;
  import qualified Bootstrap.ArtifactStructure as Structure;
  import qualified Bootstrap.SourceUnit as Unit;

  -- Source-finalization representation policy, never a lossless codec rule.
  -- Keep exact original fields and opaque checking receipts separate from the
  -- raw graph used for bounded identity/depth bookkeeping.
  data FinalSyntax = FinalTerm XTerm | FinalComputation XComputation |
    FinalBinding ((,,) XName XType XTerm) | FinalAlternative XAlternative |
    FinalBindings ([] ((,,) XName XType XTerm)) | FinalAlternatives ([] XAlternative);
  data FinalSyntaxResult = FinalSyntaxResult Int Int (Maybe Int) FinalSyntax;
  data FinalSyntaxKey = FinalSyntaxKey Int Int ([] ((,) Int Int));
  data FinalSyntaxState = FinalSyntaxState
    (Map FinalSyntaxKey FinalSyntaxResult)
    (Map ((,) Int Int) FinalSyntaxResult) Int Int Int;
  data FinalSyntaxEdge = FinalOriginalEdge Int | FinalResultEdge FinalSyntaxResult;
  data FinalSyntaxBlock = FinalSyntaxBlock Int FinalSyntaxResult;
  data FinalSyntaxTask = FinalVisit Int FinalSyntax |
    FinalRemember Int Int | FinalClose Int FinalSyntax ([] Int) Int |
    FinalBindingItems ([] Int) ([] ((,,) XName XType XTerm)) |
    FinalAlternativeItems ([] Int) ([] XAlternative) |
    FinalChain Int XComputation ([] ((,) Int XComputation))
      (Map ((,) Int Int) ((,) Int XComputation)) ([] FinalSyntaxBlock) |
    FinalChainAppend Int XComputation ([] ((,) Int XComputation))
      (Map ((,) Int Int) ((,) Int XComputation)) ([] FinalSyntaxBlock);
  finalSyntaxShape :: FinalSyntax -> Int;
  finalSyntaxShape value = case value of {
    FinalTerm _ -> 0; FinalComputation _ -> 1; FinalBinding _ -> 2;
    FinalAlternative _ -> 3; FinalBindings _ -> 4; FinalAlternatives _ -> 5
  };
  finalSyntaxId (FinalSyntaxResult identity _ _ _) = identity;
  finalSyntaxDepth (FinalSyntaxResult _ depth _ _) = depth;
  finalSyntaxOrigin (FinalSyntaxResult _ _ origin _) = origin;
  finalSyntaxValue (FinalSyntaxResult _ _ _ value) = value;
  finalSyntaxUnchanged identity result = case finalSyntaxOrigin result of {
    Just original -> original == identity; Nothing -> False
  };
  finalSyntaxReuseOriginal identity original result@(FinalSyntaxResult key depth origin _) =
    if finalSyntaxUnchanged identity result
    then FinalSyntaxResult key depth origin original else result;
  finalSyntaxTerm :: FinalSyntaxResult -> Either String XTerm;
  finalSyntaxTerm result = case finalSyntaxValue result of {
    FinalTerm term -> Right term; _ -> Left "source finalization term result mismatch"
  };
  finalSyntaxComputation :: FinalSyntaxResult -> Either String XComputation;
  finalSyntaxComputation result = case finalSyntaxValue result of {
    FinalComputation computation -> Right computation;
    _ -> Left "source finalization computation result mismatch"
  };
  compareFinalSyntaxKey (FinalSyntaxKey shape tag children) (FinalSyntaxKey otherShape otherTag otherChildren) =
    let { a = compareInt shape otherShape; b = compareInt tag otherTag } in
    if a /= 0 then a else if b /= 0 then b
    else compareList (comparePair compareInt compareInt) children otherChildren;
  finalSyntaxEdgeKey :: FinalSyntaxEdge -> (,) Int Int;
  finalSyntaxEdgeKey edge = case edge of {
    FinalOriginalEdge identity -> (,) 0 identity;
    FinalResultEdge result -> (,) 1 (finalSyntaxId result)
  };
  finalSyntaxEdgeDepth graph edge = case edge of {
    FinalOriginalEdge identity -> Wire.graphNodeDepth graph identity;
    FinalResultEdge result -> Right (finalSyntaxDepth result)
  };
  finalSyntaxIntern shape tag edges depth origin value
    (FinalSyntaxState entries memo count edgeCount visits) = do {
    ensure (depth >= 1 && depth <= Wire.maxDepth Wire.defaultLimits)
      "source finalization depth limit exceeded";
    let { key = FinalSyntaxKey shape tag edges };
    case M.lookup compareFinalSyntaxKey key entries of {
      Just (FinalSyntaxResult identity recordedDepth _ recorded) -> do {
        ensure (depth == recordedDepth && finalSyntaxShape recorded == shape)
          "source finalization intern invariant failure";
        Right ((,) (FinalSyntaxResult identity depth origin
          (case origin of { Just _ -> value; Nothing -> recorded }))
          (FinalSyntaxState entries memo count edgeCount visits))
      };
      Nothing -> do {
        ensure (count < Wire.maxNodes Wire.defaultLimits)
          "source finalization node limit exceeded";
        let { arity = length edges };
        ensure (arity <= Wire.maxEdges Wire.defaultLimits - edgeCount)
          "source finalization edge limit exceeded";
        let { result = FinalSyntaxResult count depth origin value;
          following = M.insert compareFinalSyntaxKey key result entries;
          nextCount = count + 1; nextEdges = edgeCount + arity };
        seq following (seq nextCount (seq nextEdges (Right ((,) result
          (FinalSyntaxState following memo nextCount nextEdges visits)))))
      }
    }
  };
  finalSyntaxCharge (FinalSyntaxState entries memo count edges visits) = do {
    -- A chain atom is visited once by its collector and once by its normal
    -- visitor. This is an execution-step bound, not a changed wire work limit.
    ensure (visits < 2 * Wire.maxExpandedWork Wire.defaultLimits)
      "source finalization traversal limit exceeded";
    let { next = visits + 1 };
    seq next (Right (FinalSyntaxState entries memo count edges next))
  };
  finalSyntaxNode graph identity expected = do {
    node <- Wire.lookupGraphNode graph identity;
    case node of {
      Wire.GNode tag children -> do {
        ensure (tag == expected) "source finalization paired constructor mismatch";
        Right children
      };
      _ -> Left "source finalization expected a constructor node"
    }
  };
  finalSyntaxEdges :: Wire.Graph -> [] FinalSyntaxEdge -> [] ((,) Int Int) -> Int -> Int -> Either String ((,) ([] ((,) Int Int)) Int);
  finalSyntaxEdges graph edges keys deepest count = case edges of {
    [] -> Right ((,) (reverse keys) deepest);
    (:) edge rest -> do {
      ensure (count < Wire.maxEdges Wire.defaultLimits)
        "source finalization edge-list limit exceeded";
      depth <- finalSyntaxEdgeDepth graph edge;
      let { following = max deepest depth; nextCount = count + 1 };
      seq following (seq nextCount (finalSyntaxEdges graph rest
        ((:) (finalSyntaxEdgeKey edge) keys) following nextCount))
    }
  };
  finalSyntaxFinish graph identity original tag edges candidate unchanged state = do {
    measured <- finalSyntaxEdges graph edges [] 0 0;
    let { largest = snd measured };
    ensure (largest < Wire.maxDepth Wire.defaultLimits)
      "source finalization depth limit exceeded";
    let { depth = largest + 1 };
    before <- Wire.graphNodeDepth graph identity;
    ensure (depth <= before) "source finalization increased structural depth";
    finalSyntaxIntern (finalSyntaxShape original) tag (fst measured)
      depth (if unchanged then Just identity else Nothing)
      (if unchanged then original else candidate) state
  };
  finalSyntaxJoin originals left right state = do {
    a <- finalSyntaxComputation left; b <- finalSyntaxComputation right;
    let { deepest = max (finalSyntaxDepth left) (finalSyntaxDepth right) };
    ensure (deepest < Wire.maxDepth Wire.defaultLimits)
      "source finalization depth limit exceeded";
    let { found = case (,) (finalSyntaxOrigin left) (finalSyntaxOrigin right) of {
      (,) (Just l) (Just r) -> M.lookup (comparePair compareInt compareInt) ((,) l r) originals;
      _ -> Nothing
    }; value = case found of { Just ((,) _ original) -> original; Nothing -> XThen a b };
      origin = case found of { Just ((,) identity _) -> Just identity; Nothing -> Nothing } };
    finalSyntaxIntern 1 58 [(,) 1 (finalSyntaxId left), (,) 1 (finalSyntaxId right)]
      (deepest + 1) origin (FinalComputation value) state
  };
  finalSyntaxCarry originals height value forest state = case forest of {
    [] -> Right ((,) [FinalSyntaxBlock height value] state);
    (:) (FinalSyntaxBlock previous first) rest ->
      if height < previous then Right ((,) ((:) (FinalSyntaxBlock height value) forest) state)
      else if height /= previous then Left "source finalization forest order mismatch"
      else do {
        ensure (height < Wire.maxDepth Wire.defaultLimits)
          "source finalization coverage limit exceeded";
        joined <- finalSyntaxJoin originals first value state;
        finalSyntaxCarry originals (height + 1) (fst joined) rest (snd joined)
      }
  };
  finalSyntaxPad originals height accumulated forest state = case forest of {
    (:) (FinalSyntaxBlock previous first) rest ->
      if previous < height then case accumulated of {
        Nothing -> finalSyntaxPad originals height (Just first) rest state;
        Just right -> do {
          joined <- finalSyntaxJoin originals first right state;
          finalSyntaxPad originals height (Just (fst joined)) rest (snd joined)
        }
      } else finalSyntaxPadded originals height accumulated forest state;
    [] -> finalSyntaxPadded originals height accumulated [] state
  };
  finalSyntaxPadded originals height accumulated forest state = case accumulated of {
    Nothing -> Right ((,) forest state);
    Just value -> do {
      ensure (finalSyntaxDepth value <= height) "source finalization padding depth mismatch";
      finalSyntaxCarry originals height value forest state
    }
  };
  finalSyntaxAppend originals atom forest state = do {
    let { height = finalSyntaxDepth atom };
    padded <- finalSyntaxPad originals height Nothing forest state;
    finalSyntaxCarry originals height atom (fst padded) (snd padded)
  };
  finalSyntaxForest originals accumulated forest state = case forest of {
    [] -> case accumulated of {
      Nothing -> Left "source finalization empty computation sequence";
      Just value -> Right ((,) value state)
    };
    (:) (FinalSyntaxBlock _ first) rest -> case accumulated of {
      Nothing -> finalSyntaxForest originals (Just first) rest state;
      Just right -> do {
        joined <- finalSyntaxJoin originals first right state;
        finalSyntaxForest originals (Just (fst joined)) rest (snd joined)
      }
    }
  };
  finalSyntaxTake :: forall a. Int -> [] a -> [] a -> Either String ((,) ([] a) ([] a));
  finalSyntaxTake count values acc = if count == 0 then Right ((,) acc values)
    else case values of {
      [] -> Left "source finalization result stack underflow";
      (:) value rest -> finalSyntaxTake (count - 1) rest ((:) value acc)
    };
  finalSyntaxRun graph tasks values state = case tasks of {
    [] -> case values of {
      [result] -> Right result; _ -> Left "source finalization result stack mismatch"
    };
    (:) task rest -> case task of {
      FinalVisit identity original -> do {
        charged <- finalSyntaxCharge state;
        case charged of { FinalSyntaxState _ memo _ _ _ ->
          case M.lookup (comparePair compareInt compareInt)
            ((,) (finalSyntaxShape original) identity) memo of {
            Just result -> finalSyntaxRun graph rest
              ((:) (finalSyntaxReuseOriginal identity original result) values) charged;
            Nothing -> finalSyntaxVisit graph identity original
              ((:) (FinalRemember (finalSyntaxShape original) identity) rest) values charged
          }
        }
      };
      FinalRemember shape identity -> case values of {
        [] -> Left "source finalization memo stack underflow";
        (:) result _ -> case state of { FinalSyntaxState entries memo count edges visits ->
          let { following = M.insert (comparePair compareInt compareInt)
            ((,) shape identity) result memo } in seq following
          (finalSyntaxRun graph rest values (FinalSyntaxState entries following count edges visits))
        }
      };
      FinalClose identity original references count -> do {
        split <- finalSyntaxTake count values [];
        built <- finalSyntaxBuild graph identity original references (fst split) state;
        finalSyntaxRun graph rest ((:) (fst built) (snd split)) (snd built)
      };
      FinalBindingItems references bindings -> case (,) references bindings of {
        (,) [] [] -> finalSyntaxRun graph rest values state;
        (,) ((:) identity ids) ((:) binding more) -> finalSyntaxRun graph
          ((:) (FinalVisit identity (FinalBinding binding)) ((:) (FinalBindingItems ids more) rest)) values state;
        _ -> Left "source finalization paired binding list mismatch"
      };
      FinalAlternativeItems references alternatives -> case (,) references alternatives of {
        (,) [] [] -> finalSyntaxRun graph rest values state;
        (,) ((:) identity ids) ((:) alternative more) -> finalSyntaxRun graph
          ((:) (FinalVisit identity (FinalAlternative alternative))
            ((:) (FinalAlternativeItems ids more) rest)) values state;
        _ -> Left "source finalization paired alternative list mismatch"
      };
      FinalChain identity original pending originals forest -> case pending of {
        [] -> do {
          finished <- finalSyntaxForest originals Nothing forest state;
          before <- Wire.graphNodeDepth graph identity;
          ensure (finalSyntaxDepth (fst finished) <= before)
            "source finalization increased computation depth";
          finalSyntaxRun graph rest ((:) (fst finished) values) (snd finished)
        };
        (:) ((,) current computation) more -> do {
          charged <- finalSyntaxCharge state;
          case computation of {
            XThen a b -> do {
              references <- finalSyntaxNode graph current 58;
              case references of {
                [left, right] -> let {
                  following = M.insert (comparePair compareInt compareInt) ((,) left right)
                    ((,) current computation) originals
                } in seq following (finalSyntaxRun graph
                  ((:) (FinalChain identity original ((:) ((,) left a) ((:) ((,) right b) more))
                    following forest) rest) values charged);
                _ -> Left "source finalization XThen arity mismatch"
              }
            };
            _ -> finalSyntaxRun graph
              ((:) (FinalVisit current (FinalComputation computation))
                ((:) (FinalChainAppend identity original more originals forest) rest)) values charged
          }
        }
      };
      FinalChainAppend identity original pending originals forest -> case values of {
        [] -> Left "source finalization atom stack underflow";
        (:) atom previous -> do {
          appended <- finalSyntaxAppend originals atom forest state;
          finalSyntaxRun graph ((:) (FinalChain identity original pending originals (fst appended)) rest)
            previous (snd appended)
        }
      }
    }
  };
  finalSyntaxVisit graph identity original rest values state =
    let { schedule = \tag children -> do {
      references <- finalSyntaxNode graph identity tag;
      finalSyntaxRun graph (append children
        ((:) (FinalClose identity original references (length children)) rest)) values state
    } } in case original of {
      FinalTerm term -> case term of {
        XVarTerm _ -> schedule 70 [];
        XAbs _ _ body -> finalSyntaxTermChild graph identity original 71 2 body rest values state;
        XApp a b -> finalSyntaxTermPair graph identity original 72 0 a 1 b rest values state;
        XTypeAbs _ _ body -> finalSyntaxTermChild graph identity original 73 2 body rest values state;
        XTypeApp body computation -> do {
          references <- finalSyntaxNode graph identity 74;
          case references of {
            [a,b] -> finalSyntaxRun graph (append
              [FinalVisit a (FinalTerm body), FinalVisit b (FinalComputation computation),
                FinalClose identity original references 2] rest) values state;
            _ -> Left "source finalization XTypeApp arity mismatch"
          }
        };
        XLet _ a b -> finalSyntaxTermPair graph identity original 75 1 a 2 b rest values state;
        XLetRec bindings body -> do {
          references <- finalSyntaxNode graph identity 76;
          case references of {
            [a,b] -> finalSyntaxRun graph (append
              [FinalVisit a (FinalBindings bindings), FinalVisit b (FinalTerm body),
                FinalClose identity original references 2] rest) values state;
            _ -> Left "source finalization XLetRec arity mismatch"
          }
        };
        XIntTerm _ -> schedule 77 []; XDoubleTerm _ -> schedule 78 [];
        XBoolTerm _ -> schedule 79 []; XStringTerm _ -> schedule 80 [];
        XPrimitive _ _ -> schedule 81 []; XConstructor _ _ -> schedule 82 [];
        XCase body _ alternatives -> do {
          references <- finalSyntaxNode graph identity 83;
          case references of {
            [a,_,b] -> finalSyntaxRun graph (append
              [FinalVisit a (FinalTerm body), FinalVisit b (FinalAlternatives alternatives),
                FinalClose identity original references 2] rest) values state;
            _ -> Left "source finalization XCase arity mismatch"
          }
        };
        XWithData _ body -> finalSyntaxTermChild graph identity original 84 1 body rest values state
      };
      FinalComputation computation -> case computation of {
        XRefl -> schedule 50 []; XBottom _ -> schedule 51 []; XHyp _ -> schedule 52 [];
        XInner child -> finalSyntaxComputationChild graph identity original 53 0 child rest values state;
        XOuter _ child -> finalSyntaxComputationChild graph identity original 54 1 child rest values state;
        XElim -> schedule 55 []; XIntro _ -> schedule 56 []; XIntroKind _ _ -> schedule 57 [];
        XThen _ _ -> finalSyntaxRun graph
          ((:) (FinalChain identity computation [(,) identity computation] M.empty []) rest) values state
      };
      FinalBinding ((,,) _ _ body) -> finalSyntaxTermChild graph identity original 3 2 body rest values state;
      FinalAlternative (XAlternative _ body) -> finalSyntaxTermChild graph identity original 92 1 body rest values state;
      FinalBindings bindings -> do {
        references <- finalSyntaxNode graph identity 1;
        finalSyntaxRun graph ((:) (FinalBindingItems references bindings)
          ((:) (FinalClose identity original references (length references)) rest)) values state
      };
      FinalAlternatives alternatives -> do {
        references <- finalSyntaxNode graph identity 1;
        finalSyntaxRun graph ((:) (FinalAlternativeItems references alternatives)
          ((:) (FinalClose identity original references (length references)) rest)) values state
      }
    };
  finalSyntaxReference :: forall a. [] a -> Int -> Either String a;
  finalSyntaxReference references position = case references of {
    [] -> Left "source finalization missing paired child";
    (:) first more -> if position == 0 then Right first else finalSyntaxReference more (position - 1)
  };
  finalSyntaxTermChild graph identity original tag position body rest values state = do {
    references <- finalSyntaxNode graph identity tag;
    child <- finalSyntaxReference references position;
    finalSyntaxRun graph ((:) (FinalVisit child (FinalTerm body))
      ((:) (FinalClose identity original references 1) rest)) values state
  };
  finalSyntaxComputationChild graph identity original tag position body rest values state = do {
    references <- finalSyntaxNode graph identity tag;
    child <- finalSyntaxReference references position;
    finalSyntaxRun graph ((:) (FinalVisit child (FinalComputation body))
      ((:) (FinalClose identity original references 1) rest)) values state
  };
  finalSyntaxTermPair graph identity original tag firstPosition a secondPosition b rest values state = do {
    references <- finalSyntaxNode graph identity tag;
    first <- finalSyntaxReference references firstPosition;
    second <- finalSyntaxReference references secondPosition;
    finalSyntaxRun graph (append [FinalVisit first (FinalTerm a), FinalVisit second (FinalTerm b),
      FinalClose identity original references 2] rest) values state
  };
  finalSyntaxBinding :: FinalSyntaxResult -> Either String ((,,) XName XType XTerm);
  finalSyntaxBinding result = case finalSyntaxValue result of {
    FinalBinding binding -> Right binding; _ -> Left "source finalization binding result mismatch"
  };
  finalSyntaxAlternative :: FinalSyntaxResult -> Either String XAlternative;
  finalSyntaxAlternative result = case finalSyntaxValue result of {
    FinalAlternative alternative -> Right alternative;
    _ -> Left "source finalization alternative result mismatch"
  };
  finalSyntaxBindings :: FinalSyntaxResult -> Either String ([] ((,,) XName XType XTerm));
  finalSyntaxBindings result = case finalSyntaxValue result of {
    FinalBindings bindings -> Right bindings; _ -> Left "source finalization bindings result mismatch"
  };
  finalSyntaxAlternatives :: FinalSyntaxResult -> Either String ([] XAlternative);
  finalSyntaxAlternatives result = case finalSyntaxValue result of {
    FinalAlternatives alternatives -> Right alternatives;
    _ -> Left "source finalization alternatives result mismatch"
  };
  finalSyntaxCollectBindings :: [] FinalSyntaxResult -> [] ((,,) XName XType XTerm) -> Either String ([] ((,,) XName XType XTerm));
  finalSyntaxCollectBindings children acc = case children of {
    [] -> Right (reverse acc);
    (:) child rest -> do {
      binding <- finalSyntaxBinding child;
      finalSyntaxCollectBindings rest ((:) binding acc)
    }
  };
  finalSyntaxCollectAlternatives :: [] FinalSyntaxResult -> [] XAlternative -> Either String ([] XAlternative);
  finalSyntaxCollectAlternatives children acc = case children of {
    [] -> Right (reverse acc);
    (:) child rest -> do {
      alternative <- finalSyntaxAlternative child;
      finalSyntaxCollectAlternatives rest ((:) alternative acc)
    }
  };
  finalSyntaxUnchangedList :: [] Int -> [] FinalSyntaxResult -> Bool -> Either String Bool;
  finalSyntaxUnchangedList references children unchanged = case (,) references children of {
    (,) [] [] -> Right unchanged;
    (,) ((:) identity ids) ((:) child rest) ->
      let { next = unchanged && finalSyntaxUnchanged identity child } in
      seq next (finalSyntaxUnchangedList ids rest next);
    _ -> Left "source finalization child-list arity mismatch"
  };
  finalSyntaxBuild graph identity original references children state =
    let { finish = \tag edges candidate unchanged ->
      finalSyntaxFinish graph identity original tag edges candidate unchanged state;
      unchanged = \reference result -> finalSyntaxUnchanged reference result;
      untouched = \tag -> finish tag (map FinalOriginalEdge references) original True
    } in case original of {
      FinalTerm term -> case (,,) term references children of {
        (,,) (XVarTerm _) [_] [] -> untouched 70;
        (,,) (XAbs name ty _) [n,t,b] [body] -> do {
          value <- finalSyntaxTerm body;
          finish 71 [FinalOriginalEdge n,FinalOriginalEdge t,FinalResultEdge body]
            (FinalTerm (XAbs name ty value)) (unchanged b body)
        };
        (,,) (XApp _ _) [a,b] [first,second] -> do {
          x <- finalSyntaxTerm first; y <- finalSyntaxTerm second;
          finish 72 [FinalResultEdge first,FinalResultEdge second]
            (FinalTerm (XApp x y)) (unchanged a first && unchanged b second)
        };
        (,,) (XTypeAbs variable ty _) [n,t,b] [body] -> do {
          value <- finalSyntaxTerm body;
          finish 73 [FinalOriginalEdge n,FinalOriginalEdge t,FinalResultEdge body]
            (FinalTerm (XTypeAbs variable ty value)) (unchanged b body)
        };
        (,,) (XTypeApp _ _) [a,b] [body,computation] -> do {
          x <- finalSyntaxTerm body; y <- finalSyntaxComputation computation;
          finish 74 [FinalResultEdge body,FinalResultEdge computation]
            (FinalTerm (XTypeApp x y)) (unchanged a body && unchanged b computation)
        };
        (,,) (XLet name _ _) [n,a,b] [first,second] -> do {
          x <- finalSyntaxTerm first; y <- finalSyntaxTerm second;
          finish 75 [FinalOriginalEdge n,FinalResultEdge first,FinalResultEdge second]
            (FinalTerm (XLet name x y)) (unchanged a first && unchanged b second)
        };
        (,,) (XLetRec _ _) [a,b] [bindings,body] -> do {
          x <- finalSyntaxBindings bindings; y <- finalSyntaxTerm body;
          finish 76 [FinalResultEdge bindings,FinalResultEdge body]
            (FinalTerm (XLetRec x y)) (unchanged a bindings && unchanged b body)
        };
        (,,) (XIntTerm _) [_] [] -> untouched 77;
        (,,) (XDoubleTerm _) [_] [] -> untouched 78;
        (,,) (XBoolTerm _) [_] [] -> untouched 79;
        (,,) (XStringTerm _) [_] [] -> untouched 80;
        (,,) (XPrimitive _ _) [_,_] [] -> untouched 81;
        (,,) (XConstructor _ _) [_,_] [] -> untouched 82;
        (,,) (XCase _ ty _) [a,t,b] [body,alternatives] -> do {
          x <- finalSyntaxTerm body; y <- finalSyntaxAlternatives alternatives;
          finish 83 [FinalResultEdge body,FinalOriginalEdge t,FinalResultEdge alternatives]
            (FinalTerm (XCase x ty y)) (unchanged a body && unchanged b alternatives)
        };
        (,,) (XWithData declarations _) [d,b] [body] -> do {
          value <- finalSyntaxTerm body;
          finish 84 [FinalOriginalEdge d,FinalResultEdge body]
            (FinalTerm (XWithData declarations value)) (unchanged b body)
        };
        _ -> Left "source finalization term constructor or arity mismatch"
      };
      FinalComputation computation -> case (,,) computation references children of {
        (,,) XRefl [] [] -> untouched 50;
        (,,) (XBottom _) [_] [] -> untouched 51;
        (,,) (XHyp _) [_] [] -> untouched 52;
        (,,) (XInner _) [a] [child] -> do {
          value <- finalSyntaxComputation child;
          finish 53 [FinalResultEdge child] (FinalComputation (XInner value)) (unchanged a child)
        };
        (,,) (XOuter variable _) [v,a] [child] -> do {
          value <- finalSyntaxComputation child;
          finish 54 [FinalOriginalEdge v,FinalResultEdge child]
            (FinalComputation (XOuter variable value)) (unchanged a child)
        };
        (,,) XElim [] [] -> untouched 55;
        (,,) (XIntro _) [_] [] -> untouched 56;
        (,,) (XIntroKind _ _) [_,_] [] -> untouched 57;
        (,,) (XThen _ _) _ _ -> Left "source finalization chain bypassed forest";
        _ -> Left "source finalization computation constructor or arity mismatch"
      };
      FinalBinding ((,,) name ty _) -> case (,) references children of {
        (,) [n,t,b] [body] -> do {
          value <- finalSyntaxTerm body;
          finish 3 [FinalOriginalEdge n,FinalOriginalEdge t,FinalResultEdge body]
            (FinalBinding ((,,) name ty value)) (unchanged b body)
        };
        _ -> Left "source finalization binding arity mismatch"
      };
      FinalAlternative (XAlternative pattern _) -> case (,) references children of {
        (,) [p,b] [body] -> do {
          value <- finalSyntaxTerm body;
          finish 92 [FinalOriginalEdge p,FinalResultEdge body]
            (FinalAlternative (XAlternative pattern value)) (unchanged b body)
        };
        _ -> Left "source finalization alternative arity mismatch"
      };
      FinalBindings _ -> do {
        same <- finalSyntaxUnchangedList references children True;
        bindings <- finalSyntaxCollectBindings children [];
        finish 1 (map FinalResultEdge children) (FinalBindings bindings) same
      };
      FinalAlternatives _ -> do {
        same <- finalSyntaxUnchangedList references children True;
        alternatives <- finalSyntaxCollectAlternatives children [];
        finish 1 (map FinalResultEdge children) (FinalAlternatives alternatives) same
      }
    };
  -- The original finite-plan gate is new source-finalizer resource policy.
  -- It is not a claim that an arbitrarily large raw source object that would
  -- later compact has inherited the old binary decoder's supported domain.
  admitFinalSourceObject object = mapEither fst (prepareFinalSourceObject object);
  canonicalFinalSourceObject object = do { prepared <- prepareFinalSourceObject object; snd prepared };
  -- Keep the delayed canonical result attached to the exact admitted object.
  -- The graph is demanded only on the paths that normalize this object.
  -- Only XThen chains with three or more atoms can change shape. On a
  -- small unshared tree we can prove both identity and all wire bounds in
  -- one bounded scan. Shared/deep inputs still use the exact DAG planner.
  smallFinalValue :: Wire.Value -> Maybe Bool;
  smallFinalValue raw = let {
    limits = Wire.defaultLimits;
    count = min (Wire.maxSymbols limits) (min (Wire.maxSymbolBytes limits)
      (min (Wire.maxTotalSymbolBytes limits) (min (Wire.maxNodes limits / 4)
        (min (Wire.maxEdges limits / 4) (Wire.maxExpandedWork limits / 4)))));
    -- At most 32 bytes per expanded node/edge/text byte, even with maximal
    -- varints. Header, root reference and final padding fit in 96 bytes.
    allowance = min 1048576 (min count ((Wire.maxBytes limits - 96) / 32))
  } in smallFinalTasks [(,,) 1 False [raw]] allowance (min 256 (Wire.maxDepth limits)) False;
  smallFinalTasks pending remaining maxDepth nested = case pending of {
    [] -> Just nested;
    (:) ((,,) depth parentThen values) rest -> case values of {
      [] -> smallFinalTasks rest remaining maxDepth nested;
      (:) value more -> if remaining <= 0 || depth > maxDepth then Nothing else let {
        tail = (:) ((,,) depth parentThen more) rest; next = remaining - 1
      } in case value of {
        Wire.VText text -> let { count = stringLength text } in
          if count > next / 4 then Nothing else smallFinalTasks tail (next - 4 * count) maxDepth nested;
        Wire.VNode tag children -> if tag < 0 || tag > 2147483647 then Nothing else let { changed = nested || (parentThen && tag == 58) } in
          seq changed (smallFinalTasks ((:) ((,,) (depth + 1) (tag == 58) children) tail)
            next maxDepth changed);
        _ -> smallFinalTasks tail next maxDepth nested
      }
    }
  };
  -- On the certified small domain the only rewriting operation is still the
  -- same depth-aware XThen forest. Atom heights and child identities are local
  -- to each computation; header, datatype and unrelated term nodes cannot
  -- affect any join. Reuse the original tree wherever the forest was unchanged.
  data FinalSourcePlan = AlreadyNormal | LocalProofs | FullPlan Wire.GraphPlan;
  nestedComposition computation = case computation of {
    XThen a b -> isComposition a || isComposition b || nestedComposition a || nestedComposition b;
    XInner a -> nestedComposition a; XOuter _ a -> nestedComposition a;
    _ -> False
  };
  isComposition computation = case computation of { XThen _ _ -> True; _ -> False };
  rewriteProof computation =
    if not (nestedComposition computation) then Right Nothing else do {
      graph <- Wire.planGraph Wire.defaultLimits [Structure.toXComputation computation];
      root <- case Wire.graphRoots graph of {
        [identity] -> Right identity; _ -> Left "source finalization computation root mismatch"
      };
      result <- finalSyntaxRun graph [FinalVisit root (FinalComputation computation)] []
        (FinalSyntaxState M.empty M.empty 0 0 0);
      if finalSyntaxUnchanged root result then Right Nothing else mapEither Just (finalSyntaxComputation result)
    };
  combineEdits build a b left right = case (,) left right of {
    (,) Nothing Nothing -> Nothing; _ -> Just (build (fromMaybe a left) (fromMaybe b right))
  };
  editItems edit values = editItemsFrom edit values [] False;
  editItemsFrom edit values acc changed = case values of {
    [] -> Right (if changed then Just (reverse acc) else Nothing);
    (:) x xs -> do {
      replacement <- edit x;
      case replacement of {
        Nothing -> editItemsFrom edit xs ((:) x acc) changed;
        Just new -> editItemsFrom edit xs ((:) new acc) True
      }
    }
  };
  editBinding ((,,) n ty body) = mapEither (mapOptional (\t -> (,,) n ty t)) (editProofs body);
  editAlternative (XAlternative pattern body) = mapEither (mapOptional (XAlternative pattern)) (editProofs body);
  editProofs term = let {
    pair = \build a b -> do {
      x <- editProofs a; y <- editProofs b; Right (combineEdits build a b x y)
    }; one = \build a -> mapEither (mapOptional build) (editProofs a)
  } in case term of {
    XAbs n ty b -> one (XAbs n ty) b; XApp a b -> pair XApp a b;
    XTypeAbs n ty b -> one (XTypeAbs n ty) b;
    XTypeApp a phi -> do {
      x <- editProofs a; y <- rewriteProof phi; Right (combineEdits XTypeApp a phi x y)
    };
    XLet n a b -> pair (XLet n) a b;
    XLetRec bs b -> do {
      x <- editItems editBinding bs; y <- editProofs b; Right (combineEdits XLetRec bs b x y)
    };
    XCase a ty bs -> do {
      x <- editProofs a; y <- editItems editAlternative bs;
      Right (combineEdits (\t alts -> XCase t ty alts) a bs x y)
    };
    XWithData ds b -> one (XWithData ds) b;
    XVarTerm _ -> Right Nothing; XIntTerm _ -> Right Nothing; XDoubleTerm _ -> Right Nothing;
    XBoolTerm _ -> Right Nothing; XStringTerm _ -> Right Nothing; XPrimitive _ _ -> Right Nothing;
    XConstructor _ _ -> Right Nothing
  };
  prepareFinalSourceObject object = prepareSourceUnit (Unit.pending object);
  prepareSourceUnit input = do {
    let { object = Unit.object input; raw = Structure.toRawUnitObject object };
    plan <- case smallFinalValue raw of {
      Just False -> Right AlreadyNormal; Just True -> Right LocalProofs;
      Nothing -> mapEither FullPlan (Wire.prepareGraphPlan Wire.defaultLimits [raw])
    };
    let { iface = Separate.objectInterface object; term = Separate.objectTerm object };
    admitted <- Unit.admit input;
    let { finish = \replacement -> case replacement of {
      Nothing -> Right admitted;
      Just result -> do {
        -- The replacement is independently bounded before checking or rendering.
        let { value = Structure.toRawUnitObject (Separate.UnitObject iface result) };
        _ <- case smallFinalValue value of {
          Just _ -> Right ();
          Nothing -> do {
            tables <- Wire.plan Wire.defaultLimits [value];
            _ <- Wire.layout Wire.defaultLimits tables;
            Right ()
          }
        };
        proof <- Checked.check result;
        ensure (eqString (Separate.fingerprint (Pretty.prettyTerm result))
          (Separate.unitObjectFingerprint iface)) "source finalization changed object checksum";
        Right (Separate.CheckedUnitObject iface proof)
      }
    } };
    Right ((,) admitted (case plan of {
      AlreadyNormal -> Right admitted;
      LocalProofs -> bindEither (editProofs term) finish;
      FullPlan tables -> do {
      graph <- Wire.realizeGraphPlan tables;
      root <- case Wire.graphRoots graph of {
        [identity] -> Right identity;
        _ -> Left "source finalization graph root mismatch"
      };
      fields <- finalSyntaxNode graph root 241;
      termIdentity <- case fields of {
        [_,identity] -> Right identity;
        _ -> Left "source finalization object arity mismatch"
      };
      -- Only recursive term/proof children are paired. The original declaration
      -- list and every untouched type/name/pattern/literal object stay in place.
      normalized <- finalSyntaxRun graph [FinalVisit termIdentity (FinalTerm term)] []
        (FinalSyntaxState M.empty M.empty 0 0 0);
      result <- finalSyntaxTerm normalized;
      finish (if finalSyntaxUnchanged termIdentity normalized then Nothing else Just result)
    } }))
  };


  -- Internal explicit source calling convention, paired with a checked target
  -- scheme. No dictionary-arrow inspection constructs this overload list.
  data SourceContract = SourceContract XType ([] String) Bool;
  contractType (SourceContract ty _ _) = ty;
  contractClasses (SourceContract _ classes _) = classes;
  contractProtected (SourceContract _ _ protected) = protected;
  contractTypes contracts = M.map contractType contracts;
  contractOverloads contracts = M.mapWithKey
    (\name contract -> (,) name (contractClasses contract)) contracts;

  -- Keep this helper below CrateQuery to avoid a query/orchestrator cycle.
  selectedBindings members available =
    let { used = Set.fromList compareString
      (concatMap (\member -> Dependency.valueNames (Dependency.observeDeclaration member)) members) }
    in M.toList (M.filterWithKey (\name _ -> Set.member compareString name used) available);

  -- Provisional is never an available contract/cache hit. Source-issued labels
  -- and exact candidate scope travel with its independently checked object.
  data ProvisionalRoot = ProvisionalRoot String Separate.UnitObject
    ([] ((,,) String String String)) ([] ((,) EvidenceRole String)) Bool
    (Map String String) ([] ((,,) EvidenceRole String XType)) ([] String);
  provisionalObject (ProvisionalRoot _ object _ _ _ _ _ _) = object;
  provisionalLabels (ProvisionalRoot _ _ labels _ _ _ _ _) = labels;
  provisionalCandidates (ProvisionalRoot _ _ _ candidates _ _ _ _) = candidates;
  provisionalProtected (ProvisionalRoot _ _ _ _ protected _ _ _) = protected;

  protectedCandidateNames contracts names = filter
    (\name -> case M.lookup compareString name contracts of {
      Nothing -> True;
      Just contract -> contractProtected contract
    }) names;
  checkedDependencyProtected :: [] ((,) String Bool) -> Separate.UnitObject -> Either String Bool;
  checkedDependencyProtected flags object = do {
    let { term = case Separate.objectTerm object of { XWithData _ body -> body; body -> body } };
    let { split = Separate.splitParameters term };
    let { parameters = fst split };
    let { used = Boundary.nubNames (Boundary.freeNames (snd split)) };
    protected <- traverseEither (\name -> do {
      parameter <- case find (\((,) binder _) -> X.equalName binder name) parameters of {
        Nothing -> Left "checked raw implementation has an unowned free parameter";
        Just value -> Right (fst value)
      };
      case find (\((,) hint _) -> eqString hint (X.nameHint parameter)) flags of {
        Nothing -> Left "used checked predecessor lacks protection authority";
        Just entry -> Right (snd entry)
      }
    }) used;
    Right (any (\flag -> flag) protected)
  };
  parameterProtection contracts bindings = map
    (\((,) name _) -> (,) name (case M.lookup compareString name contracts of {
      Nothing -> True;
      Just contract -> contractProtected contract
    })) bindings;

  -- The validated lowerer derives source/selector/transitive protection;
  -- callers cannot obtain eligibility merely by passing a false flag.
  prepareUnsignedRoot :: Classes.ClassInventory -> Map String SourceContract ->
    String -> SExpr -> Fresh ProvisionalRoot;
  prepareUnsignedRoot inventory contracts name original =
    do {
      freshLift (ensure (not (M.member compareString name contracts))
        "source root also occurs in predecessor contracts");
      lowered <- Classes.lowerUnsignedSourceRootProtected inventory
        (contractOverloads contracts) (M.map contractProtected contracts) name original;
      case lowered of {
        Classes.SourceRootLowering rhs labels candidates protected ->
          do {
            let { members = (:) ((,,) name Nothing rhs) [] };
            let { selected = selectedBindings members (contractTypes contracts) };
            let { datatypes = case inventory of {
              Classes.ClassInventory ds _ _ _ _ _ _ _ _ -> ds
            } };
            object <- freshLift
              (Inference.compileLoweredGroup name
                ((:) (Separate.UnitInterface "SourceInputs" [] [] [] [] [] selected "parameters") []) datatypes members);
            typedCandidates <- freshLift (traverseEither
              (\((,) role candidate) -> case M.lookup compareString candidate contracts of {
                Nothing -> Left ("definition evidence support has not been checked: " ++ candidate);
                Just contract -> Right ((,,) role candidate (contractType contract))
              }) candidates);
            usedProtected <- freshLift
              (checkedDependencyProtected (parameterProtection contracts selected) object);
            freshPure (ProvisionalRoot name object labels candidates
              (protected || usedProtected)
              (Classes.inventoryOrdinaryRegistry inventory) typedCandidates
              (protectedCandidateNames contracts (map snd candidates)))
          }
      }
    };

  data RootParts = RootParts ([] DataDecl) ([] ((,) XName XType)) XName XType XTerm;
  rootParts :: ProvisionalRoot -> Either String RootParts;
  rootParts (ProvisionalRoot name object _ _ _ _ _ _) =
    do {
      let { datatypes = Separate.unitData (Separate.objectInterface object) };
      let { term = case Separate.objectTerm object of {
        XWithData _ body -> body; body -> body
      } };
      let { split = Separate.splitParameters term };
      found <- case snd split of {
        XLet binder rhs (XConstructor "()" []) -> Right ((,) binder rhs);
        _ -> Left "source root did not retain a single nonrecursive checked binding"
      };
      case Separate.unitBindings (Separate.objectInterface object) of {
        (:) ((,) exported ty) [] -> do {
          ensure (eqString exported name && eqString (X.nameHint (fst found)) name)
            "source root checked ownership mismatch";
          Right (RootParts datatypes (fst split) (fst found) ty (snd found))
        };
        _ -> Left "source root changed binding count"
      }
    };

  -- Direct representation map only. Unsupported target wrappers are an
  -- unchanged-boundary fallback, never grounds for invented binder identities.
  targetSlots :: [] ((,,) String String String) -> XTerm ->
    Either String (Maybe ([] ((,,) XName String String)));
  targetSlots labels rhs = case labels of {
    [] -> Right (Just []);
    (:) ((,,) sourceName className dictionaryName) rest -> case rhs of {
      XAbs binder _ body -> do {
        ensure (eqString (X.nameHint binder) sourceName)
          "source-issued slot does not match checked target binder";
        following <- targetSlots rest body;
        Right (case following of {
          Nothing -> Nothing;
          Just values -> Just ((:) ((,,) binder className dictionaryName) values)
        })
      };
      _ -> Right Nothing
    }
  };

  data FinalRoot = FinalRoot Separate.UnitObject SourceContract;
  finalObject (FinalRoot object _) = object;
  finalContract (FinalRoot _ contract) = contract;
  unchangedRoot :: ProvisionalRoot -> Either String FinalRoot;
  unchangedRoot root@(ProvisionalRoot _ object labels _ protected _ _ _) =
    do {
      _ <- admitFinalSourceObject object;
      parts <- rootParts root;
      case parts of {
        RootParts _ _ _ ty _ -> do {
          finalized <- canonicalFinalSourceObject object;
          Right (FinalRoot finalized
            (SourceContract ty (map (\((,,) _ className _) -> className) labels) protected))
        }
      }
    };

  -- A typed boundary adapter supplies a raw term and exact parameter list; no
  -- dictionary body is duplicated here. This verifies the public target binding
  -- independently of the adapter before returning the compact source contract.
  -- Only ALL-ground zero-residual plans may call this first-slice constructor.
  checkedCompactRoot :: ProvisionalRoot -> XType -> XTerm ->
    [] ((,) XName XType) -> Either String FinalRoot;
  checkedCompactRoot root@(ProvisionalRoot name _ _ _ protected _ _ _) ty adapter parameters =
    do {
      ensure (not protected) "cannot compact a protected source boundary";
      _ <- admitFinalSourceObject (provisionalObject root);
      parts <- rootParts root;
      case parts of {
        RootParts datatypes _ binder _ _ -> do {
          let { implementation = XLet binder adapter (XConstructor "()" []) };
          let { payload = XWithData datatypes
            (foldr (\((,) n t) body -> XAbs n t body) implementation parameters) };
          checked <- Checked.check payload;
          dataEnv <- Data.validateDeclarations datatypes;
          bindings <- Separate.collectBindings dataEnv
            (XEnv M.empty (M.fromList X.compareName parameters)) implementation;
          ensure (case bindings of {
            (:) ((,) actualName actualType) [] ->
              X.equalName actualName binder && Type.alphaEq actualType ty;
            _ -> False
          }) "compact root binding and checked adapter type disagree";
          let { iface = Separate.UnitInterface
            (Separate.unitName (Separate.objectInterface (provisionalObject root))) [] [] datatypes [] []
            ((:) ((,) name ty) []) (Separate.fingerprint (Pretty.prettyTerm payload)) };
          finalized <- canonicalFinalSourceObject (Separate.CheckedUnitObject iface checked);
          Right (FinalRoot finalized (SourceContract ty [] False))
        }
      }
    };

  candidateParameters :: [] ((,) XName XType) ->
    XTerm -> [] ((,,) EvidenceRole String XType) -> Either String ([] Boundary.Candidate);
  candidateParameters parameters term candidates =
    let {
      first = 1 + foldl max 0 (IS.toList (Separate.termIdentities term IS.empty))
    } in
    traverseEither
      (\((,) ordinal ((,,) role name ty)) -> do {
        let { binder = case find (\((,) n _) -> eqString (X.nameHint n) name) parameters of {
          Just ((,) n _) -> n;
          Nothing -> XName (first + ordinal) name
        } };
        Right (Boundary.Candidate role binder ty)
      })
      (zip (range 0 (length candidates - 1)) candidates);

  finishUnsignedRoot :: ProvisionalRoot -> Either String FinalRoot;
  finishUnsignedRoot root@(ProvisionalRoot rootName object labels roles protected registry typedCandidates protectedCandidates) = do {
    _ <- admitFinalSourceObject object;
    if protected then unchangedRoot root else do {
      parts <- rootParts root;
      case parts of {
        RootParts datatypes parameters binder ty rhs -> do {
          slots <- targetSlots labels rhs;
          case slots of {
            Nothing -> unchangedRoot root;
            Just mapped -> do {
              authorized <- candidateParameters parameters (Separate.objectTerm object) typedCandidates;
              let { boundary = Boundary.Boundary 0 Boundary.UnsignedRoot False 0
                (map (\((,,) n _ _) -> n) mapped) };
              let { obligations = map
                (\((,) ordinal ((,,) n className dictionaryName)) ->
                  Boundary.Slot 0 ordinal n (Boundary.GeneratedOrdinary className dictionaryName) 0)
                (zip (range 0 (length mapped - 1)) mapped) };
              plan <- Boundary.adaptOpen registry
                datatypes boundary obligations parameters
                ((:) (Boundary.EvidenceScope 0 authorized) []) ty rhs;
              if any (\support -> elem eqString (X.nameHint support) protectedCandidates)
                   (Boundary.openProofSupports plan)
              then unchangedRoot (ProvisionalRoot rootName object labels roles True registry
                typedCandidates protectedCandidates)
              else if Boundary.openChanged plan
              then do {
                ensure (null (Boundary.openResidualOrdinals plan))
                  "partial evidence contraction is outside source boundary policy";
                checkedCompactRoot root (Boundary.openNewType plan)
                  (Boundary.openRawAdapter plan) (Boundary.openRequiredParameters plan)
              }
              else unchangedRoot root
            }
          }
        }
      }
    }
  };
  compileUnsignedRoot :: Classes.ClassInventory -> Map String SourceContract ->
    String -> SExpr -> Fresh FinalRoot;
  compileUnsignedRoot inventory contracts name rhs = do {
    provisional <- prepareUnsignedRoot inventory contracts name rhs;
    freshLift (finishUnsignedRoot provisional)
  };

  -- Source planning retains original annotations/ownership until after routing.
  -- The legacy recipe is lazy and is used only by the explicit whole-path
  -- fallback or compatibility diagnostics, never to prepare source queries.
  data PlanInput = NamedInput ([] ((,,) String (Maybe SAnnotation) SExpr)) | ResolvedInput Dependency.BoundValues;
  data PlannedBinding = PlannedSource Int (Maybe SAnnotation) (R.Expr Declaration) |
    PlannedSupport Int (Maybe SAnnotation) SExpr;
  data PlanGraph = NamedPlan ([] ((,,) String (Maybe SAnnotation) SExpr))
    ([] ((,,) String (Maybe SAnnotation) SExpr)) ([] ([] String)) |
    IndexedPlan Dependency.Symbols (V.IndexVec Declaration PlannedBinding)
      ([] (V.Index Declaration)) ([] (V.Index Declaration)) ([] ([] ((,) (V.Index Declaration) Bool)));
  data SourcePlan = SourcePlan Classes.ClassInventory PlanGraph
    Int (Set String) (Map String SType) (Either String Inference.LoweredDeclarations)
    ([] ((,) String SInstanceDecl)) (Map String Bool);
  planInventory (SourcePlan inventory _ _ _ _ _ _ _) = inventory;
  planGraph (SourcePlan _ graph _ _ _ _ _ _) = graph;
  -- The inventory and persisted query envelopes consume named syntax. Select
  -- by ID first, projecting only the rows demanded by that consumer.
  namedBinding symbols rows i = let { name = Dependency.symbolName symbols } in case V.at rows i of {
    PlannedSource ordinal annotation rhs -> (,) ordinal ((,,) (name i) annotation (R.namedExpr name rhs));
    PlannedSupport ordinal annotation rhs -> (,) ordinal ((,,) (name i) annotation rhs)
  };
  planSources plan = case planGraph plan of {
    NamedPlan sources _ _ -> sources;
    IndexedPlan symbols rows ids _ _ -> map (compose snd (namedBinding symbols rows)) ids
  };
  planSupports plan = case planGraph plan of {
    NamedPlan _ supports _ -> supports;
    IndexedPlan symbols rows _ ids _ -> map (compose snd (namedBinding symbols rows)) ids
  };
  planGroups plan = case planGraph plan of {
    NamedPlan _ _ groups -> groups;
    IndexedPlan symbols _ _ _ groups -> map (map (compose (Dependency.symbolName symbols) fst)) groups
  };
  planData plan = case planInventory plan of {
    Classes.ClassInventory ds _ _ _ _ _ _ _ _ -> ds
  };
  planNames plan = case planInventory plan of {
    Classes.ClassInventory _ _ _ _ _ _ _ names _ -> names
  };
  planLegacy (SourcePlan _ _ _ _ _ legacy _ _) = legacy;
  sourceName ((,,) name _ _) = name;
  sourceRhs ((,,) _ _ rhs) = rhs;
  isCopied :: SExpr -> Bool;
  isCopied (SSourceDefinition _) = True;
  isCopied (SCallSite _ _ body) = isCopied body;
  isCopied (SAnn body _) = isCopied body;
  isCopied (SSignature body _) = isCopied body;
  isCopied (SChecked _ body) = isCopied body;
  isCopied _ = False;
  prepareSourcePlan :: Map String SType -> [] DataDecl -> [] SClassDecl ->
    [] ((,) String SInstanceDecl) -> Map String IntSet -> [] IntSet ->
    [] ((,,) String (Maybe SAnnotation) SExpr) -> Either String (Maybe SourcePlan);
  prepareSourcePlan externals datatypes classes instances valueScopes instanceScopes members = do {
    closed <- traverseEither (\((,) name inst) -> mapEither ((,) name) (Separate.closeInstance members inst)) instances;
    mapEither fst (sourcePlanWith (NamedInput members) externals datatypes classes instances closed (Dependency.NamedScopes valueScopes) instanceScopes)
  };
  prepareResolvedSourcePlan bindings = sourcePlanWith (ResolvedInput bindings);
  sourcePlanWith input externals datatypes classes instances closedInstances valueScopes instanceScopes = do {
    body <- case input of {
      NamedInput members -> Surface.bindValues members (SConstructor "()");
      ResolvedInput bindings -> Surface.bindResolved bindings (SConstructor "()")
    };
    prepared <- Classes.withClassScopes externals (map fst closedInstances)
      valueScopes instanceScopes
      (SClassProgram datatypes classes (map snd closedInstances) body)
      (\inventory -> Fresh (\count used -> Right ((,,) ((,,) inventory count used) count used)));
    case prepared of { (,,) inventory count used -> do {
      let { legacy = Inference.lowerBoundInScopes externals datatypes classes closedInstances valueScopes instanceScopes body };
      graph <- case inventory of { Classes.ClassInventory _ _ _ scopes _ methods definitions _ _ ->
        let { supports = map (\((,,) name annotation rhs) -> (,,) name (Just annotation) rhs) (Classes.supportDefinitions definitions);
              targets = Dependency.mapScopes (map snd) scopes
        } in case input of {
          NamedInput members -> namedPlan members supports methods (Dependency.namedScopes targets);
          ResolvedInput bindings -> case Classes.inventoryDeclarations inventory of {
            Nothing -> Left "resolved source inventory lacks generated declaration slots";
            Just generation -> indexedPlanWith bindings generation supports
              (\i -> map snd (Classes.inventoryCandidateIds inventory i))
          }
        }
      };
      Right ((,) (mapOptional (\g -> SourcePlan inventory g count used externals legacy instances M.empty) graph) legacy)
    } }
  };
  namedPlan members supports methods scopes = do {
    let { allMembers = append supports members;
          sourceNames = Set.fromList compareString (map sourceName members);
          supportNames = Set.fromList compareString (map sourceName supports);
          sourceEdges member =
            let { name = sourceName member; refs = Dependency.valueNames (Dependency.observeDeclaration member);
                  target ref = case M.lookup compareString ref methods of { Nothing -> ref; Just ((,) n _) -> n }
            } in (,) name (append (map target refs) (M.findWithDefault compareString [] name scopes));
          groups = Dependency.components (append (Dependency.declarationEdges supports) (map sourceEdges members));
          mixed names = any (\n -> Set.member compareString n sourceNames) names &&
                        any (\n -> Set.member compareString n supportNames) names
    };
    ensure (length allMembers == Set.size (Set.fromList compareString (map sourceName allMembers)))
      "duplicate source/support binding";
    Right (if any mixed groups || any (compose isCopied sourceRhs) members then Nothing else
      Just (NamedPlan members supports groups))
  };
  indexedPlan bindings supports methods scopes = indexedPlanInScopes bindings supports methods (Dependency.NamedScopes scopes);
  indexedPlanInScopes bindings@(Dependency.BoundValues base members) supports methods scopes =
    let { generation = Dependency.generatedTable base (map Dependency.boundId members)
            (map sourceName supports) [] methods;
          targets i = mapMaybe (Dependency.generatedNameId generation) (fromMaybe []
            (case scopes of {
              Dependency.NamedScopes values -> M.lookup compareString (Dependency.symbolName base i) values;
              Dependency.IndexedScopes _ _ _ _ -> Dependency.scopeAt scopes i
            }))
    } in indexedPlanWith bindings generation supports targets;
  indexedPlanWith bindings@(Dependency.BoundValues base members) generation supports targets = do {
    (,) symbols groups <- Dependency.resolvedGroupsWith bindings generation (Dependency.declarationEdges supports) targets;
    let { baseCount = V.count (Dependency.symbolNodes base); count = V.count (Dependency.symbolNodes symbols);
          sources = map Dependency.boundId members; generated = Dependency.generatedSlots generation;
          source i = V.toInt i < baseCount;
          -- Groups are in lexical SCC order. Each input's ordinal recovers
          -- its original declaration order when preparing a multi-member SCC.
          mixed group = any (compose source fst) group && any (compose (compose not source) fst) group;
          sourceRow ordinal (Dependency.Bound i annotation rhs) = (,) i (PlannedSource ordinal annotation rhs);
          supportRow i ((,,) _ annotation rhs) = (,) i (PlannedSupport (V.toInt i - baseCount) annotation rhs);
          entries = append (mapIndexed sourceRow members) (zipWith supportRow generated supports);
          rows = runST (stBind (V.filled count (panic "inactive source plan slot")) (\table ->
            stBind (ST.map_ (\((,) i row) -> V.set table i row) entries) (\_ -> V.freeze table)));
          copied (Dependency.Bound _ _ rhs) = copiedSource rhs
    };
    Right (if any mixed groups || any copied members then Nothing else Just (IndexedPlan symbols rows sources generated groups))
  };
  copiedSource term = case term of {
    R.SourceDefinition _ -> True; R.CallSite _ _ b -> copiedSource b;
    R.Ann b _ -> copiedSource b; R.Signature b _ -> copiedSource b; _ -> False
  };
  initializeProtection :: SourcePlan -> Map String Bool -> Either String SourcePlan;
  initializeProtection plan@(SourcePlan inventory graph count used externals legacy instances _) imported = do {
    let { sourceRefs = case graph of {
      NamedPlan _ _ _ -> Nothing;
      IndexedPlan _ rows _ _ _ -> Just (\i -> case V.at rows i of {
        PlannedSource _ _ rhs -> R.references rhs; PlannedSupport _ _ _ -> []
      })
    } };
    flags <- Classes.inventoryProtectionWith sourceRefs inventory imported instances (planSources plan);
    Right (SourcePlan inventory graph count used externals legacy instances flags)
  };
  initialContracts :: SourcePlan -> Map String XType -> Map String Bool ->
    Either String (Map String SourceContract);
  initialContracts (SourcePlan _ _ _ _ externals _ _ _) types protected =
    mapEither (M.fromList compareString) (traverseEither
      (\((,) name ty) -> do {
        source <- case M.lookup compareString name externals of {
          Nothing -> Left ("source dependency lacks an import contract: " ++ name);
          Just value -> Right value
        };
        let { classes = case Classes.scheme source of {
          (,,) _ predicates _ -> map (\(SPredicate cls _) -> cls) predicates
        } };
        Right ((,) name (SourceContract ty classes
          (M.findWithDefault compareString True name protected || Classes.managedType source)))
      }) (M.toList types));

  -- A sealed prepared query contains raw input and all finalization authority.
  -- No checked object is admitted until the existing raw cache/inference checks.
  data PreparedGroup = PreparedGroup
    ([] ((,,) String (Maybe SAnnotation) SExpr))
    ([] ((,,) String (Maybe SAnnotation) SExpr))
    ([] ((,) String XType)) (Map String String)
    ([] ((,,) String ([] String) Bool)) (Maybe RootAuthority) ([] ((,) String Bool));
  data RootAuthority = RootAuthority String ([] ((,,) String String String)) Bool
    ([] ((,,) EvidenceRole String XType)) ([] String);
  groupOriginal (PreparedGroup original _ _ _ _ _ _) = original;
  groupMembers (PreparedGroup _ members _ _ _ _ _) = members;
  groupBindings (PreparedGroup _ _ bindings _ _ _ _) = bindings;
  groupRegistry (PreparedGroup _ _ _ registry _ _ _) = registry;
  groupContracts (PreparedGroup _ _ _ _ contracts _ _) = contracts;
  groupAuthority (PreparedGroup _ _ _ _ _ authority _) = authority;
  groupParameterProtection (PreparedGroup _ _ _ _ _ _ flags) = flags;
  groupCandidateBindings group = case groupAuthority group of {
    Nothing -> [];
    Just (RootAuthority _ _ _ candidates _) ->
      map (\((,,) _ name ty) -> (,) name ty) candidates
  };
  -- The sparse selector is reserved for finite parsed-file groups. The public
  -- selector retains its full-map traversal and partial-value demand behavior.
  selectedContractBindings members contracts =
    let { used = Set.fromList compareString
      (concatMap (\member -> Dependency.valueNames (Dependency.observeDeclaration member)) members) }
    in concatMap (\name -> case M.lookup compareString name contracts of {
      Nothing -> [];
      Just contract -> [(,) name (contractType contract)]
    }) (Set.toList used);
  structuralContractBindings members contracts = selectedBindings members (contractTypes contracts);
  makePrepared = makePreparedUsing structuralContractBindings;
  makePreparedUsing selectBindings original lowered registry specs authority contracts =
    let { bindings = selectBindings lowered contracts } in
    PreparedGroup original lowered bindings registry specs authority
      (parameterProtection contracts bindings);
  eligibleSource :: [] ((,,) String (Maybe SAnnotation) SExpr) -> Bool;
  eligibleSource members = eligibleSourceWith (case members of {
    [(,,) name _ rhs] -> elem eqString name (Surface.freeNames rhs);
    _ -> False
  }) members;
  eligibleSourceWith selfReference members = case members of {
    (:) ((,,) name Nothing rhs) [] ->
      not (isCopied rhs) && not selfReference &&
      null (Classes.sourceDeclaredClasses Nothing rhs);
    _ -> False
  };
  prepareGroup :: SourcePlan -> Map String SourceContract -> [] String -> Either String PreparedGroup;
  prepareGroup = prepareGroupUsing structuralContractBindings;
  -- Only the file-owned query drivers select this route, with finite parsed
  -- declarations and their current checked predecessor contracts.
  prepareGroupSparse :: SourcePlan -> Map String SourceContract -> [] String -> Either String PreparedGroup;
  prepareGroupSparse = prepareGroupUsing selectedContractBindings;
  -- The file query driver keeps the group's IDs through selection. The
  -- printable names belong to the query key and the named inference boundary.
  planSteps plan = case planGraph plan of {
    NamedPlan _ _ groups -> map (\names -> (,) names (\contracts -> prepareGroupSparse plan contracts names)) groups;
    IndexedPlan symbols rows _ _ groups -> let {
      step group = let {
        ids = map fst group;
        names = map (Dependency.symbolName symbols) ids;
        entries = sortBy (\a b -> compareInt (fst a) (fst b)) (map (namedBinding symbols rows) ids);
        members = map snd entries;
        support = case ids of { (:) i _ -> case V.at rows i of { PlannedSupport _ _ _ -> True; _ -> False }; [] -> False };
        prepare contracts = prepareGroupWithReservation selectedContractBindings Nothing (case ids of { [i] -> Just i; _ -> Nothing })
          (eligibleSourceWith (any snd group)) plan contracts names
          (if support then [] else members) (if support then members else [])
          (contractOverloads contracts) (M.map contractProtected contracts)
      } in (,) names prepare
    } in map step groups
  };
  -- This context belongs to one finite parsed file and its checked predecessor
  -- map. Ordinals retain declaration order independently of SCC name order.
  -- Index values and projected contract fields remain lazy. Finalized deltas
  -- replace all views with the same left bias as the owned contract map.
  -- The reserved set is only plan.used plus current contract keys. Per-group
  -- generated names and method targets never enter this persistent seed.
  data OwnedSourceContext = OwnedSourceContext
    (Map String ((,) Int ((,,) String (Maybe SAnnotation) SExpr)))
    (Map String ((,) Int ((,,) String (Maybe SAnnotation) SExpr)))
    (Map String ((,) String ([] String))) (Map String Bool) (Set String);
  ownedSourceUsed (OwnedSourceContext _ _ _ _ used) = used;
  reserveContractKeys contracts used = M.foldlWithKeyStrict
    (\reserved name _ -> Set.insert compareString name reserved) used contracts;
  indexSourceDeclarations members = M.fromList compareString (numberSourceDeclarations 0 members);
  numberSourceDeclarations ordinal members = case members of {
    [] -> [];
    (:) member rest -> (:) ((,) (sourceName member) ((,) ordinal member))
      (numberSourceDeclarations (ordinal + 1) rest)
  };
  prepareOwnedSourceContext :: SourcePlan -> Map String SourceContract -> OwnedSourceContext;
  prepareOwnedSourceContext plan@(SourcePlan _ _ _ used _ _ _ _) contracts = OwnedSourceContext
    (indexSourceDeclarations (planSources plan)) (indexSourceDeclarations (planSupports plan))
    (contractOverloads contracts) (M.map contractProtected contracts)
    (reserveContractKeys contracts used);
  extendOwnedSourceContext :: Map String SourceContract -> OwnedSourceContext -> OwnedSourceContext;
  extendOwnedSourceContext contracts (OwnedSourceContext sources supports overloads protected used) =
    OwnedSourceContext sources supports
      (M.union compareString (contractOverloads contracts) overloads)
      (M.union compareString (M.map contractProtected contracts) protected)
      (reserveContractKeys contracts used);
  indexedSourceDeclarations index names =
    let { selected = concatMap (\name -> case M.lookup compareString name index of {
      Nothing -> [];
      Just entry -> [entry]
    }) (Set.toList (Set.fromList compareString names)) }
    in map snd (sortBy (\left right -> compareInt (fst left) (fst right)) selected);
  prepareGroupOwned :: OwnedSourceContext -> SourcePlan -> Map String SourceContract ->
    [] String -> Either String PreparedGroup;
  prepareGroupOwned (OwnedSourceContext sources supports overloads protected used) plan contracts names =
    prepareGroupWithReservation selectedContractBindings (Just used) Nothing eligibleSource plan contracts names
      (indexedSourceDeclarations sources names) (indexedSourceDeclarations supports names)
      overloads protected;
  prepareGroupUsing selectBindings plan contracts names =
    prepareGroupWithViews selectBindings plan contracts names
      (filter (\member -> elem eqString (sourceName member) names) (planSources plan))
      (filter (\member -> elem eqString (sourceName member) names) (planSupports plan))
      (contractOverloads contracts) (M.map contractProtected contracts);
  prepareGroupWithViews selectBindings = prepareGroupWithReservation selectBindings Nothing Nothing eligibleSource;
  prepareGroupWithReservation selectBindings reserved owner eligible (SourcePlan inventory _ count used _ _ _ supportProtection)
    contracts names original support overloads protected = do {
    ensure (length original + length support == length names) "source SCC ownership mismatch";
    traverseEither (\name -> ensure (not (M.member compareString name contracts))
      "source SCC imports its own checked predecessor") names;
    let { registry = Classes.inventoryOrdinaryRegistry inventory };
    if not (null support) then do {
      ensure (null original) "mixed support/source SCC requires whole-path fallback";
      specs <- traverseEither (\name -> case M.lookup compareString name supportProtection of {
        Nothing -> Left ("generated support lacks source protection provenance: " ++ name);
        Just protected -> Right ((,,) name []
          (protected || any (\peer -> M.findWithDefault compareString True peer supportProtection) names))
      }) names;
      Right (makePreparedUsing selectBindings support support registry specs Nothing contracts)
    } else do {
      outcome <- runFreshState
        (if eligible original then case original of {
          (:) ((,,) name Nothing rhs) [] -> do {
            lowered <- (case reserved of {
              Nothing -> Classes.lowerUnsignedRootAt
                (\_ _ env suffix -> Classes.sourceEnvironmentNames env suffix) owner;
              Just _ -> Classes.lowerUnsignedRootAt Classes.sourceOwnedEnvironmentNames owner
            }) inventory overloads protected name rhs;
            case lowered of { Classes.SourceRootLowering body labels candidates protected -> do {
              typed <- freshLift (traverseEither
                (\((,) role candidate) -> case M.lookup compareString candidate contracts of {
                  Nothing -> Left ("definition evidence support has not been checked: " ++ candidate);
                  Just contract -> Right ((,,) role candidate (contractType contract))
                }) candidates);
              let { loweredMembers = (:) ((,,) name Nothing body) [] };
              let { protectedNow = protected };
              freshPure (makePreparedUsing selectBindings original loweredMembers registry
                ((:) ((,,) name (map (\((,,) _ cls _) -> cls) labels) protectedNow) [])
                (Just (RootAuthority name labels protectedNow typed
                  (protectedCandidateNames contracts (map snd candidates)))) contracts)
            } }
          };
          _ -> freshFail "invalid eligible source group"
        } else do {
          lowered <- (case reserved of {
            Nothing -> Classes.lowerSourceGroupUnchanged;
            Just _ -> Classes.lowerSourceGroupUnchangedOwned
          }) inventory overloads protected original;
          case lowered of { (,) body specs -> do {
            values <- freshLift (Inference.extractLoweredDeclarations body);
            freshPure (makePreparedUsing selectBindings original values registry specs Nothing contracts)
          } }
        }) count (case reserved of { Nothing -> used; Just cached -> cached });
      case outcome of { (,,) prepared _ _ -> Right prepared }
    }
  };
  validateRawSlots :: [] ((,,) String String String) -> XErased -> Either String ();
  validateRawSlots labels rhs = case labels of {
    [] -> Right ();
    (:) ((,,) name _ _) rest -> case rhs of {
      XEAbs binder body -> do {
        ensure (eqString name (X.nameHint binder)) "raw source evidence prefix identity mismatch";
        validateRawSlots rest body
      };
      _ -> Left "raw source evidence prefix is missing"
    }
  };
  validatePreparedRaw :: PreparedGroup -> Separate.UnitObject -> Either String Separate.UnitObject;
  validatePreparedRaw prepared object = case groupAuthority prepared of {
    Nothing -> Right object;
    Just (RootAuthority name labels protected candidates protectedCandidates) -> do {
      parts <- rootParts (ProvisionalRoot name object labels
        (map (\((,,) role candidate _) -> (,) role candidate) candidates)
        protected (groupRegistry prepared) candidates protectedCandidates);
      case parts of { RootParts _ _ _ _ rhs -> do {
        validateRawSlots labels (X.erase rhs);
        Right object
      } }
    }
  };
  data FinalGroup = FinalGroup Separate.UnitObject (Map String SourceContract);
  finalGroupObject (FinalGroup object _) = object;
  finalGroupContracts (FinalGroup _ contracts) = contracts;
  finishGroup :: PreparedGroup -> Separate.UnitObject -> Either String FinalGroup;
  finishGroup prepared object = finishSourceUnit prepared (Unit.pending object);
  finishSourceUnit prepared input = do {
    let { object = Unit.object input };
    admitted <- prepareSourceUnit input;
    validatePreparedRaw prepared object;
    usedProtected <- checkedDependencyProtected (groupParameterProtection prepared) object;
    let { expected = sortBy compareString (map sourceName (groupMembers prepared)) };
    ensure (eqList eqString expected (map fst (Separate.unitBindings (Separate.objectInterface object))))
      "raw group changed source ownership";
    case groupAuthority prepared of {
      Just (RootAuthority name labels protected candidates protectedCandidates) -> do {
        root <- finishUnsignedRoot (ProvisionalRoot name object labels
          (map (\((,,) role candidate _) -> (,) role candidate) candidates) (protected || usedProtected)
          (groupRegistry prepared) candidates protectedCandidates);
        Right (FinalGroup (finalObject root)
          (M.fromList compareString ((:) ((,) name (finalContract root)) [])))
      };
      Nothing -> do {
        contracts <- traverseEither
          (\((,) name ty) -> case find (\((,,) n _ _) -> eqString n name) (groupContracts prepared) of {
            Nothing -> Left "final source group lacks calling-convention metadata";
            Just ((,,) _ classes protected) -> Right ((,) name (SourceContract ty classes (protected || usedProtected)))
          }) (Separate.unitBindings (Separate.objectInterface object));
        finalized <- snd admitted;
        Right (FinalGroup finalized (M.fromList compareString contracts))
      }
    }
  };

  -- Only the checked adapter path can supply a replacement fragment.
  data FinalBody = KeepRawBody | AdaptedBody Open.Fragment;
  data OpenFinalGroup = OpenFinalGroup FinalBody (Map String SourceContract);
  openFinalObject raw KeepRawBody = raw;
  openFinalObject _ (AdaptedBody checked) = checked;
  openRootParts object = case (,) (Open.body object) (Open.bindings object) of {
    (,) (XLet binder rhs (XConstructor "()" [])) [(,) owned ty] -> do {
      ensure (X.equalName binder owned) "open root member identity mismatch";
      Right ((,,) binder ty rhs)
    };
    _ -> Left "source root did not retain a single nonrecursive checked binding"
  };
  validatePreparedOpen prepared object = do {
    ensure (eqList eqString (sortBy compareString (map sourceName (groupMembers prepared)))
      (sortBy compareString (map (compose X.nameHint fst) (Open.bindings object))))
      "raw group changed source ownership";
    case groupAuthority prepared of {
      Nothing -> Right ();
      Just (RootAuthority name labels _ _ _) -> do {
        parts <- openRootParts object;
        case parts of { (,,) binder _ rhs -> do {
          ensure (eqString name (X.nameHint binder)) "raw source identity mismatch";
          validateRawSlots labels (X.erase rhs)
        } }
      }
    }
  };
  canonicalOpen object = do {
    plan <- Wire.prepareGraphPlan Wire.defaultLimits [Structure.toXTerm (Open.body object)];
    graph <- Wire.realizeGraphPlan plan;
    identity <- case Wire.graphRoots graph of { [root] -> Right root; _ -> Left "open raw root count" };
    normalized <- finalSyntaxRun graph [FinalVisit identity (FinalTerm (Open.body object))] []
      (FinalSyntaxState M.empty M.empty 0 0 0);
    result <- finalSyntaxTerm normalized;
    if finalSyntaxUnchanged identity normalized then Right object else Open.normalize object result
  };
  prepareOpenFinish prepared object = do {
    usedFlags <- traverseEither (\name -> case find
      (\((,) n _) -> eqString n (X.nameHint name)) (groupParameterProtection prepared) of {
        Just ((,) _ protected) -> Right protected;
        Nothing -> Left "used checked predecessor lacks protection authority"
      }) (Open.usedParameters object);
    let { usedProtected = any (\flag -> flag) usedFlags };
    case groupAuthority prepared of {
      Nothing -> do {
        contracts <- traverseEither (\((,) binder ty) ->
          case find (\((,,) n _ _) -> eqString n (X.nameHint binder)) (groupContracts prepared) of {
            Nothing -> Left "final source group lacks calling-convention metadata";
            Just ((,,) name classes protected) -> Right ((,) name (SourceContract ty classes (protected || usedProtected)))
          }) (Open.bindings object);
        Right (ReadyOpenFinish (OpenFinalGroup KeepRawBody (M.fromList compareString contracts)))
      };
      Just (RootAuthority name labels protected candidates protectedCandidates) -> do {
        parts <- openRootParts object;
        case parts of { (,,) binder ty rhs -> let {
          unchanged = \flag -> Right (ReadyOpenFinish (OpenFinalGroup KeepRawBody
            (M.fromList compareString [(,) name (SourceContract ty (map (\((,,) _ cls _) -> cls) labels) flag)])));
          isProtected = protected || usedProtected
        } in if isProtected || null labels then unchanged isProtected else do {
          slots <- targetSlots labels rhs;
          case slots of {
            Nothing -> unchanged isProtected;
            Just mapped -> do {
              authorized <- candidateParameters (Open.parameters object) (Open.body object) candidates;
              let { boundary = Boundary.Boundary 0 Boundary.UnsignedRoot False 0
                (map (\((,,) n _ _) -> n) mapped);
                obligations = map
                  (\((,) ordinal ((,,) n cls dictionary)) ->
                    Boundary.Slot 0 ordinal n (Boundary.GeneratedOrdinary cls dictionary) 0)
                  (zip (range 0 (length mapped - 1)) mapped) };
              plan <- Boundary.checkedPlan (groupRegistry prepared) boundary obligations (Open.parameters object)
                [Boundary.EvidenceScope 0 authorized] ty rhs;
              Right (PendingOpenFinish object name binder ty labels isProtected protectedCandidates plan)
            }
          }
        } }
      }
    }
  };

  data OpenFinish = ReadyOpenFinish OpenFinalGroup | PendingOpenFinish Open.Fragment String XName XType
    ([] ((,,) String String String)) Bool ([] String) Boundary.CheckedPlan;
  openFinishRequests finish = case finish of {
    ReadyOpenFinish _ -> [];
    PendingOpenFinish _ _ _ _ _ _ _ plan -> Boundary.checkedRequests plan
  };
  completeOpenFinish finish answers = case finish of {
    ReadyOpenFinish group -> Right group;
    PendingOpenFinish object name binder ty labels protected protectedCandidates plan -> do {
      recipe <- Boundary.finishCheckedPlan plan answers;
      let { unchanged = \flag -> Right (OpenFinalGroup KeepRawBody (M.fromList compareString
        [(,) name (SourceContract ty (map (\((,,) _ cls _) -> cls) labels) flag)])) };
      case recipe of {
        Boundary.KeepRecipe -> unchanged protected;
        Boundary.ChangeRecipe result body required supports ->
          if any (\n -> elem eqString (X.nameHint n) protectedCandidates) supports then unchanged True else do {
            final <- Open.check (Open.context object) required (XLet binder body (XConstructor "()" []));
            ensure (case Open.bindings final of {
              [(,) actual actualType] -> X.equalName actual binder && Type.alphaEq actualType result;
              _ -> False }) "checked evidence adapter type mismatch";
            canonical <- canonicalOpen final;
            Right (OpenFinalGroup (AdaptedBody canonical) (M.fromList compareString [(,) name (SourceContract result [] False)]))
          }
      }
    }
  }

}
