-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.GroundProofEdit where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  nestedComposition computation = case computation of {
    XThen a b -> isComposition a || isComposition b || nestedComposition a || nestedComposition b;
    XInner a -> nestedComposition a; XOuter _ a -> nestedComposition a;
    _ -> False
  };
  isComposition computation = case computation of { XThen _ _ -> True; _ -> False };
  combineEdits build a b left right = case (,) left right of {
    (,) Nothing Nothing -> Nothing; _ -> Just (build (fromMaybe a left) (fromMaybe b right))
  };
  -- Checked open fragments can normalize complete ground arguments after the
  -- geometry scan certifies the expanded tree. The bounded proof editor also
  -- handles mixed arguments before the complete graph finalizer is needed.
  -- In the finalizer's height-ordered forest, Inner (Bottom (Con n []))
  -- has height four and Elim has height one. Before the next Inner, padding
  -- joins the preceding Inner and Elim. Each complete argument is therefore
  -- one block of equal height. The order and spelling of its leaves survive
  -- the same binary carries as the general forest.
  groundArgumentBlock :: XComputation -> Bool;
  groundArgumentBlock proof = case proof of {
    XThen (XInner (XBottom (XCon _ []))) XElim -> True;
    _ -> False
  };
  -- The outer option records whether the bounded editor handled this proof.
  groundProofEdit :: XComputation -> Maybe (Maybe XComputation);
  groundProofEdit source = let {
    carry height value stack = case stack of {
      (:) ((,) previous first) rest -> if previous == height
        then carry (height + 1) (XThen first value) rest else (:) ((,) height value) stack;
      [] -> [(,) height value]
    };
    -- collection has already established exactly the same leaves in order.
    sameShape a b = case (,) (groundArgumentBlock a) (groundArgumentBlock b) of {
      (,) True yes -> yes;
      (,) False True -> False;
      _ -> case (,) a b of {
        (,) (XThen al ar) (XThen bl br) -> sameShape al bl && sameShape ar br;
        _ -> False
      }
    };
    collect remaining pending stack = case pending of {
      [] -> case stack of {
        [] -> Nothing;
        (:) ((,) _ lastBlock) rest -> let {
          result = foldlStrict (\right block -> XThen (snd block) right) lastBlock rest
        } in Just (if sameShape source result then Nothing else Just result)
      };
      (:) first rest -> if remaining <= 0 then Nothing else
        if groundArgumentBlock first then let { next = carry 0 first stack } in seq next
          (collect (remaining - 1) rest next)
        else case first of {
          XThen a b -> collect (remaining - 1) ((:) a ((:) b rest)) stack;
          _ -> Nothing
        }
    }
  } in if nestedComposition source then collect 127 [source] [] else Just Nothing;
  -- Only a geometry-certified raw tree reaches this editor. Its right
  -- application spines use an explicit pending list. Left nesting and
  -- wrappers have a shallow bound; other shapes keep the graph finalizer.
  editGroundTerm :: Int -> XTerm -> Maybe (Maybe XTerm);
  editGroundTerm depth term = if depth > 128 then Nothing else let {
    child = editGroundTerm (depth + 1);
    one build body = mapOptional (mapOptional build) (child body);
    pair build a b = case child a of {
      Nothing -> Nothing;
      Just left -> mapOptional (combineEdits build a b left) (child b)
    };
    spine f a functions changed = case child f of {
      Nothing -> Nothing;
      Just replacement -> let {
        following = (:) (fromMaybe f replacement) functions;
        different = changed || isJust replacement
      } in seq different (case a of {
        XApp g b -> spine g b following different;
        _ -> case child a of {
          Nothing -> Nothing;
          Just tailEdit -> Just (if different || isJust tailEdit
            then Just (foldlStrict (\value operator -> XApp operator value) (fromMaybe a tailEdit) following)
            else Nothing)
        }
      })
    }
  } in case term of {
    XApp f a -> spine f a [] False;
    XTypeApp f proof -> case child f of {
      Nothing -> Nothing;
      Just left -> mapOptional (combineEdits XTypeApp f proof left) (groundProofEdit proof)
    };
    XLet name a b -> pair (XLet name) a b;
    XAbs name ty body -> one (XAbs name ty) body;
    XTypeAbs name ty body -> one (XTypeAbs name ty) body;
    XWithData declarations body -> one (XWithData declarations) body;
    XProjection _ _ -> Just Nothing;
    XInstantiationSpine _ _ -> Just Nothing;
    XVarTerm _ -> Just Nothing; XIntTerm _ -> Just Nothing; XDoubleTerm _ -> Just Nothing;
    XBoolTerm _ -> Just Nothing; XStringTerm _ -> Just Nothing; XPrimitive _ _ -> Just Nothing;
    XConstructor _ _ -> Just Nothing; XLetRec _ _ -> Nothing; XCase _ _ _ -> Nothing
  };
}
