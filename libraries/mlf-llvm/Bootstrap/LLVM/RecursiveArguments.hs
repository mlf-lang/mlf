-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.RecursiveArguments (compactRecursiveArguments) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
  import qualified Bootstrap.X.Syntax as X;
  -- The checked optimizer has assigned distinct identities to all binders.
  -- In a wide mutually recursive group, keep one formal for positions that
  -- receive the same variable at every entry and stay equal on every peer call.
  compactRecursiveArguments :: XErased -> XErased;
  compactRecursiveArguments expression = case planRecursiveArguments IS.empty expression of {
    (,,) prepared _ masks -> if IM.null masks then expression else
      rewriteRecursiveArguments masks M.empty prepared
  };
  -- Index the continuation once, returning only sites for in-scope wide
  -- groups. A bare variable and a partial application are sites too.
  indexArgumentCalls :: IntSet -> XErased -> IntMap ([] ([] XErased)) -> IntMap ([] ([] XErased));
  indexArgumentCalls targets term sites = if IS.null targets then sites else case X.applications term of {
    (,) head args -> let {
      visit = indexArgumentCalls targets;
      inside = L.foldr visit sites args
    } in case head of {
      XEVar n -> if IS.member (X.nameId n) targets
        then IM.insertWith L.append (X.nameId n) [args] inside else inside;
      _ -> L.foldr visit inside (X.subterms head)
    }
  };
  planRecursiveArguments :: IntSet -> XErased -> (,,) XErased (IntMap ([] ([] XErased))) (IntMap ([] Bool));
  planRecursiveArguments outer expression = case expression of {
    XELet n rhs rest -> case planRecursiveArguments outer rest of {
      (,,) body sites masks -> (,,) (XELet n rhs body) (indexArgumentCalls outer rhs sites) masks
    };
    XELetRec bindings rest -> let {
      members = L.map (\((,) n rhs) -> (,) n (X.lambdas rhs)) bindings;
      width = case members of {
        (:) ((,) _ ((,) first _)) ((:) _ _) ->
          L.foldlStrict (\w entry -> L.min w (L.length (L.fst (L.snd entry)))) (L.length first) members;
        _ -> 0
      };
      ids = L.map (L.compose X.nameId L.fst) bindings;
      scope = if width < 16 then outer else L.foldlStrict (L.flip IS.insert) outer ids
    } in case planRecursiveArguments scope rest of {
      (,,) body sites masks -> let {
        external = L.concatMap (\key -> IM.findWithDefault [] key sites) ids;
        finish group next = let {
          remaining = L.foldlStrict (L.flip IM.delete) sites ids;
          calls = L.foldr (\binding -> indexArgumentCalls outer (L.snd binding)) remaining group
        } in (,,) (XELetRec group body) calls next
      } in if width < 16 || L.null external then finish bindings masks else
        case compactGroupArguments members width external of {
          Nothing -> finish bindings masks;
          Just ((,) group keep) -> finish group (L.foldlStrict (\m k -> IM.insert k keep m) masks ids)
        }
    };
    _ -> (,,) expression (indexArgumentCalls outer expression IM.empty) IM.empty
  };
  -- Intersect the current partition with the equality observed at one site.
  -- Only variable identity and the caller's proven formal classes can equate
  -- positions. Two arbitrary expressions always get distinct keys.
  refineArgumentClasses positions classes current ((,) params args) = let {
    formals = M.fromList X.compareName (L.zip params classes);
    token pos arg = case arg of {
      XEVar n -> case M.lookup X.compareName n formals of {
        Just representative -> (,) 0 representative;
        Nothing -> (,) 1 (X.nameId n)
      };
      _ -> (,) 2 pos
    };
    order = L.comparePair L.compareInt (L.comparePair L.compareInt L.compareInt);
    step ((,) seen reversed) ((,) pos ((,) old arg)) = let { key = (,) old (token pos arg) } in
      case M.lookup order key seen of {
        Just representative -> (,) seen ((:) representative reversed);
        Nothing -> (,) (M.insert order key pos seen) ((:) pos reversed)
      }
  } in L.reverse (L.snd (L.foldlStrict step ((,) M.empty []) (L.zip positions (L.zip current args))));
  compactGroupArguments members arity external = let {
    ids = L.map (L.compose X.nameId L.fst) members;
    targets = IS.fromList ids;
    peerSites ((,) _ ((,) params body)) = let {
      found = indexArgumentCalls targets body IM.empty
    } in L.map ((,) params) (L.concat (IM.elems found));
    calls = L.append (L.concatMap peerSites members) (L.map ((,) []) external);
    width = L.foldlStrict (\n call -> L.min n (L.length (L.snd call))) arity calls;
    positions = L.range 0 (width - 1);
    stable classes = let { next = L.foldlStrict (refineArgumentClasses positions classes) classes calls } in
      if L.eqList eqInt next classes then classes else stable next;
    classes = stable (L.replicate width 0);
    keep = L.zipWith eqInt positions classes;
    member ((,) n ((,) args body)) = let {
      formals = M.fromList L.compareInt (L.zip positions args);
      aliases = M.fromList X.compareName (L.zip args (L.map (\rep -> M.get L.compareInt rep formals) classes));
      result = rewriteRecursiveArguments IM.empty aliases body
    } in (,) n (L.foldr XEAbs result (selectRecursiveArguments keep args))
  } in if width < 2 || L.all (\v -> v) keep then Nothing else Just ((,) (L.map member members) keep);
  selectRecursiveArguments keep args =
    L.append (L.map L.snd (L.filter L.fst (L.zip keep args))) (L.drop (L.length keep) args);
  -- A removed actual is a duplicate variable, so a retained copy still
  -- records any bare escape. Member aliases were already applied before
  -- indexing their calls into enclosing groups. Apply all call masks once.
  rewriteRecursiveArguments masks aliases term = let {
    visit = rewriteRecursiveArguments masks aliases
  } in case X.applications term of {
    (,) (XEVar n) args -> let {
      kept = case IM.lookup (X.nameId n) masks of {
        Nothing -> args; Just keep -> selectRecursiveArguments keep args
      }
    } in L.foldl XEApp (XEVar (M.findWithDefault X.compareName n n aliases)) (L.map visit kept);
    (,) head [] -> X.mapErasedChildren visit head;
    (,) head args -> L.foldl XEApp (visit head) (L.map visit args)
  };
}
