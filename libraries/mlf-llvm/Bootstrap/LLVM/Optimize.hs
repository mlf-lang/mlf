-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.Optimize where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.Primitive as P;
  -- Fresh copies preserve global binder identity uniqueness when rewriting.
  data Fresh a = Fresh (Int -> (,) a Int);
  runFresh :: forall a. Fresh a -> Int -> (,) a Int;
  runFresh (Fresh f) seed = f seed;
  freshPure :: forall a. a -> Fresh a;
  freshPure value = Fresh (\seed -> (,) value seed);
  freshBind :: forall a b. Fresh a -> (a -> Fresh b) -> Fresh b;
  freshBind action next =
    Fresh
      (\seed ->
         case runFresh action seed of {
           (,) value after -> runFresh (next value) after
         });
  instance Functor Fresh where {
    fmap function action = freshBind action (\value -> freshPure (function value))
  };
  instance Applicative Fresh where {
    pure = freshPure;
    (<*>) action argument =
      freshBind action (\function -> freshBind argument (\value -> freshPure (function value)))
  };
  instance Monad Fresh where {
    (>>=) = freshBind
  };
  freshName :: Fresh XName;
  freshName = Fresh (\seed -> (,) (XName seed "native") (seed + 1));
  nameId :: XName -> Int;
  nameId (XName n hint) = n;
  compareName :: XName -> XName -> Int;
  compareName a b =
    if (nameId a < nameId b) then (0 - 1) else if (nameId a == nameId b) then 0 else 1;
  eqName :: XName -> XName -> Bool;
  eqName a b = (nameId a == nameId b);
  free :: XErased -> Set XName;
  free expression =
    case expression of {
      XEVar n -> S.singleton n;
      XEAbs n b -> S.delete compareName n (free b);
      XEApp f a -> S.union compareName (free f) (free a);
      XELet n a b -> S.union compareName (free a) (S.delete compareName n (free b));
      XELetRec ds b ->
        S.difference compareName
          (S.unions compareName
             ((:) (free b)
                (L.map
                   (\entry ->
                      case entry of {
                        (,) n a -> free a
                      })
                   ds)))
          (S.fromList compareName
             (L.map
                (\entry ->
                   case entry of {
                     (,) n a -> n
                   })
                ds));
      XECase a branches ->
        S.union compareName (free a) (S.unions compareName (L.map freeAlternative branches));
      _ -> S.empty
    };
  freeAlternative :: XErasedAlternative -> Set XName;
  freeAlternative (XErasedAlternative p b) =
    S.difference compareName (free b) (S.fromList compareName (X.patternNames p));
  applications :: XErased -> (,) XErased ([] XErased);
  applications expression = collectApplications [] expression;
  collectApplications :: [] XErased -> XErased -> (,) XErased ([] XErased);
  collectApplications args expression =
    case expression of {
      XEApp f a -> collectApplications ((:) a args) f;
      _ -> (,) expression args
    };
  lambdas :: XErased -> (,) ([] XName) XErased;
  lambdas expression =
    case expression of {
      XEAbs n b ->
        case lambdas b of {
          (,) ns body -> (,) ((:) n ns) body
        };
      _ -> (,) [] expression
    };
  -- Match the seed's bounded size query: a function larger than the inlining
  -- threshold need not have its remaining tree traversed.
  remainingSize :: Int -> XErased -> Int;
  remainingSize budget expression =
    if (budget <= 0)
    then (0 - 1)
    else let {
           rest = (budget - 1)
         } in
         case expression of {
           XEAbs n b -> remainingSize rest b;
           XEApp f a -> remainingSize (remainingSize rest f) a;
           XELet n a b -> remainingSize (remainingSize rest a) b;
           XELetRec ds b ->
             remainingSizes (remainingSize rest b)
               (L.map
                  (\entry ->
                     case entry of {
                       (,) n a -> a
                     })
                  ds);
           XECase a branches ->
             remainingSizes (remainingSize rest a)
               (L.map
                  (\branch ->
                     case branch of {
                       XErasedAlternative p b -> b
                     })
                  branches);
           _ -> rest
         };
  remainingSizes :: Int -> [] XErased -> Int;
  remainingSizes budget expressions =
    if (budget < 0)
    then (0 - 1)
    else case expressions of {
           [] -> budget;
           (:) expression rest -> remainingSizes (remainingSize budget expression) rest
         };
  -- Only zero, one, and multiple free uses matter to these rewrites. The limit
  -- is shared across siblings, and binder checks keep this query scope-correct.
  occurrences :: Int -> XName -> XErased -> Int;
  occurrences limit name expression =
    if (limit <= 0)
    then 0
    else case expression of {
           XEVar n -> if eqName name n then 1 else 0;
           XEAbs n b -> if eqName name n then 0 else occurrences limit name b;
           XEApp f a -> occurrenceTerms limit name ((:) f ((:) a []));
           XELet n a b ->
             occurrenceTerms limit name ((:) a (if eqName name n then [] else (:) b []));
           XELetRec ds b ->
             if L.any
                  (\entry ->
                     case entry of {
                       (,) n a -> eqName name n
                     })
                  ds
             then 0
             else occurrenceTerms limit name
                    ((:) b
                       (L.map
                          (\entry ->
                             case entry of {
                               (,) n a -> a
                             })
                          ds));
           XECase a branches ->
             occurrenceTerms limit name
               ((:) a
                  (L.map
                     (\branch ->
                        case branch of {
                          XErasedAlternative p b -> b
                        })
                     (L.filter
                        (\branch ->
                           case branch of {
                             XErasedAlternative p b ->
                               L.not (L.any (eqName name) (X.patternNames p))
                           })
                        branches)));
           _ -> 0
         };
  occurrenceTerms :: Int -> XName -> [] XErased -> Int;
  occurrenceTerms limit name expressions =
    if (limit <= 0)
    then 0
    else case expressions of {
           [] -> 0;
           (:) expression rest ->
             let {
               used = occurrences limit name expression
             } in
             (used + occurrenceTerms (limit - used) name rest)
         };
  traverseFresh :: forall a b. (a -> Fresh b) -> [] a -> Fresh ([] b);
  traverseFresh f values =
    case values of {
      [] -> freshPure [];
      (:) a rest ->
        do {
          value <- f a;
          tail <- traverseFresh f rest;
          freshPure ((:) value tail)
        }
    };
  copy :: Map XName XErased -> XErased -> Fresh XErased;
  copy env expression =
    case expression of {
      XEVar n -> freshPure (M.findWithDefault compareName expression n env);
      XEAbs n b ->
        do {
          renamed <- freshName;
          body <- copy (M.insert compareName n (XEVar renamed) env) b;
          freshPure (XEAbs renamed body)
        };
      XEApp f a ->
        do {
          function <- copy env f;
          argument <- copy env a;
          freshPure (XEApp function argument)
        };
      XELet n a b ->
        do {
          renamed <- freshName;
          value <- copy env a;
          body <- copy (M.insert compareName n (XEVar renamed) env) b;
          freshPure (XELet renamed value body)
        };
      XELetRec ds b ->
        do {
          names <- traverseFresh (\ignored -> freshName) ds;
          let {
            local =
              M.union compareName
                (M.fromList compareName
                   (L.zipWith
                      (\entry n ->
                         case entry of {
                           (,) old a -> (,) old (XEVar n)
                         })
                      ds
                      names))
                env
          };
          bindings <- traverseFresh (copyRecursive local) (L.zip names ds);
          body <- copy local b;
          freshPure (XELetRec bindings body)
        };
      XECase a branches ->
        do {
          subject <- copy env a;
          alternatives <- traverseFresh (copyAlternative env) branches;
          freshPure (XECase subject alternatives)
        };
      _ -> freshPure expression
    };
  copyRecursive :: Map XName XErased ->
                   (,) XName ((,) XName XErased) -> Fresh ((,) XName XErased);
  copyRecursive env ((,) name ((,) old value)) =
    do {
      copied <- copy env value;
      freshPure ((,) name copied)
    };
  copyAlternative :: Map XName XErased -> XErasedAlternative -> Fresh XErasedAlternative;
  copyAlternative env (XErasedAlternative pattern body) =
    do {
      names <- traverseFresh (\ignored -> freshName) (X.patternNames pattern);
      let {
        renaming = M.fromList compareName (L.zip (X.patternNames pattern) names)
      };
      let {
        patternNext =
          case pattern of {
            XDefaultPattern name -> XDefaultPattern (renameMaybe renaming name);
            XConstructorPattern c fields ->
              XConstructorPattern c (L.map (renameMaybe renaming) fields)
          }
      };
      result <- copy (M.union compareName (M.map XEVar renaming) env) body;
      freshPure (XErasedAlternative patternNext result)
    };
  renameMaybe :: Map XName XName -> Maybe XName -> Maybe XName;
  renameMaybe renaming optional =
    case optional of {
      Nothing -> Nothing;
      Just name -> Just (M.findWithDefault compareName name name renaming)
    };
  children :: (XErased -> Fresh XErased) -> XErased -> Fresh XErased;
  children f expression =
    case expression of {
      XEAbs n b ->
        do {
          body <- f b;
          freshPure (XEAbs n body)
        };
      XEApp a b ->
        do {
          function <- f a;
          argument <- f b;
          freshPure (XEApp function argument)
        };
      XELet n a b ->
        do {
          value <- f a;
          body <- f b;
          freshPure (XELet n value body)
        };
      XELetRec ds b ->
        do {
          definitions <-
            traverseFresh
              (\entry ->
                 case entry of {
                   (,) n a ->
                     do {
                       value <- f a;
                       freshPure ((,) n value)
                     }
                 })
              ds;
          body <- f b;
          freshPure (XELetRec definitions body)
        };
      XECase a branches ->
        do {
          subject <- f a;
          alternatives <-
            traverseFresh
              (\branch ->
                 case branch of {
                   XErasedAlternative p b ->
                     do {
                       body <- f b;
                       freshPure (XErasedAlternative p body)
                     }
                 })
              branches;
          freshPure (XECase subject alternatives)
        };
      _ -> freshPure expression
    };
  identities :: XErased -> Fresh XErased;
  identities expression =
    do {
      normalized <- children identities expression;
      case normalized of {
        XEApp (XEAbs n (XEVar other)) argument ->
          if eqName n other then freshPure argument else freshPure normalized;
        XELet n (XEVar a) b -> copy (M.singleton n (XEVar a)) b;
        _ -> freshPure normalized
      }
    };
  fixedPoints :: XErased -> Fresh XErased;
  fixedPoints expression =
    case expression of {
      XEAbs f (XELet g (XEAbs r (XECase (XEVar r1) ((:) (XErasedAlternative (XConstructorPattern c ((:) (Just next) [])) (XEApp (XEVar f1) (XEApp (XEVar next1) (XEVar r2)))) []))) (XEApp (XEVar g1) (XEApp (XEConstructor c1) (XEVar g2)))) ->
        if (eqName f f1 &&
            (eqName r r1 &&
             (eqName r r2 &&
              (eqName next next1 && (eqName g g1 && (eqName g g2 && eqString c c1))))))
        then do {
               loop <- freshName;
               freshPure
                 (XEAbs f
                    (XELetRec ((:) ((,) loop (XEApp (XEVar f) (XEVar loop))) []) (XEVar loop)))
             }
        else children fixedPoints expression;
      _ -> children fixedPoints expression
    };
  atom :: XErased -> Bool;
  atom expression =
    case expression of {
      XEVar n -> True;
      XEPrimitive p -> True;
      XEConstructor c -> True;
      XEInt n -> True;
      XEDouble n -> True;
      XEBool b -> True;
      _ -> False
    };
  smallValue :: XErased -> Bool;
  smallValue expression =
    if atom expression
    then True
    else case expression of {
           XEAbs n b -> (remainingSize 24 expression >= 0);
           _ ->
             case applications expression of {
               (,) (XEConstructor c) args -> L.all atom args;
               _ -> False
             }
         };
  -- Arity evidence comes from independently checked constructor patterns. No
  -- constructor spelling or runtime tag is special; absent/conflicting evidence
  -- disables propagation, and partial applications are never treated as data.
  subterms :: XErased -> [] XErased;
  subterms expression =
    case expression of {
      XEAbs n b -> (:) b [];
      XEApp f a -> (:) f ((:) a []);
      XELet n a b -> (:) a ((:) b []);
      XELetRec ds b ->
        L.snoc
          (L.map
             (\entry ->
                case entry of {
                  (,) n a -> a
                })
             ds)
          b;
      XECase a branches ->
        (:) a
          (L.map
             (\branch ->
                case branch of {
                  XErasedAlternative p b -> b
                })
             branches);
      _ -> []
    };
  agreeArity :: Maybe Int -> Maybe Int -> Maybe Int;
  agreeArity a b =
    case a of {
      Just n ->
        case b of {
          Just m -> if (n == m) then Just n else Nothing;
          Nothing -> Nothing
        };
      Nothing -> Nothing
    };
  alternativeArity :: Map String (Maybe Int) -> XErasedAlternative -> Map String (Maybe Int);
  alternativeArity known (XErasedAlternative pattern body) =
    case pattern of {
      XConstructorPattern c names ->
        M.insertWith compareString agreeArity c (Just (L.length names)) known;
      _ -> known
    };
  collectArities :: Map String (Maybe Int) -> XErased -> Map String (Maybe Int);
  collectArities known expression =
    let {
      after =
        case expression of {
          XECase a branches -> L.foldlStrict alternativeArity known branches;
          _ -> known
        }
    } in
    L.foldlStrict collectArities after (subterms expression);
  constructorArities :: XErased -> Map String (Maybe Int);
  constructorArities expression = collectArities M.empty expression;
  constructorValue :: Map String (Maybe Int) -> XErased -> Maybe ((,) String ([] XErased));
  constructorValue arities expression =
    case applications expression of {
      (,) (XEConstructor c) args ->
        case M.lookup compareString c arities of {
          Just (Just arity) -> if (arity == L.length args) then Just ((,) c args) else Nothing;
          _ -> Nothing
        };
      _ -> Nothing
    };
  -- Each non-atomic field gets one lazy binding before any projection is
  -- copied. Recursive fields remain in the original group to preserve knots.
  liftField :: XErased -> Fresh ((,) ([] ((,) XName XErased)) XErased);
  liftField field =
    if atom field
    then freshPure ((,) [] field)
    else do {
           name <- freshName;
           freshPure ((,) ((:) ((,) name field) []) (XEVar name))
         };
  liftConstructorValue :: Map String (Maybe Int) ->
                          XErased -> Fresh ((,) ([] ((,) XName XErased)) XErased);
  liftConstructorValue arities value =
    case constructorValue arities value of {
      Just ((,) c args) ->
        do {
          fields <- traverseFresh liftField args;
          freshPure
            ((,) (L.concatMap L.fst fields) (L.foldl XEApp (XEConstructor c) (L.map L.snd fields)))
        };
      Nothing -> freshPure ((,) [] value)
    };
  liftConstructorBinding :: Map String (Maybe Int) ->
                            (,) XName XErased ->
                            Fresh ((,) ((,) XName XErased) ([] ((,) XName XErased)));
  liftConstructorBinding arities ((,) name rhs) =
    do {
      lifted <- liftConstructorValue arities rhs;
      case lifted of {
        (,) fields value -> freshPure ((,) ((,) name value) fields)
      }
    };
  liftConstructorFields :: Map String (Maybe Int) -> XErased -> Fresh XErased;
  liftConstructorFields arities expression =
    do {
      normalized <- children (liftConstructorFields arities) expression;
      case normalized of {
        XELet name rhs body ->
          do {
            lifted <- liftConstructorValue arities rhs;
            case lifted of {
              (,) fields value ->
                freshPure
                  (L.foldr
                     (\entry rest ->
                        case entry of {
                          (,) n a -> XELet n a rest
                        })
                     (XELet name value body)
                     fields)
            }
          };
        XELetRec ds body ->
          do {
            lifted <- traverseFresh (liftConstructorBinding arities) ds;
            freshPure (XELetRec (L.append (L.map L.fst lifted) (L.concatMap L.snd lifted)) body)
          };
        _ -> freshPure normalized
      }
    };
  constructorFact :: Map String (Maybe Int) ->
                     Map XName ((,) String ([] XErased)) ->
                     (,) XName XErased -> Map XName ((,) String ([] XErased));
  constructorFact arities known ((,) name rhs) =
    case constructorValue arities rhs of {
      Just ((,) c fields) ->
        if L.all smallValue fields then M.insert compareName name ((,) c fields) known else known;
      Nothing -> known
    };
  collectConstructorFacts :: Map String (Maybe Int) ->
                             Map XName ((,) String ([] XErased)) ->
                             XErased -> Map XName ((,) String ([] XErased));
  collectConstructorFacts arities known expression =
    let {
      after =
        case expression of {
          XELet name rhs body -> constructorFact arities known ((,) name rhs);
          XELetRec ds body -> L.foldlStrict (constructorFact arities) known ds;
          _ -> known
        }
    } in
    L.foldlStrict (collectConstructorFacts arities) after (subterms expression);
  constructorFacts :: Map String (Maybe Int) -> XErased -> Map XName ((,) String ([] XErased));
  constructorFacts arities expression = collectConstructorFacts arities M.empty expression;
  projectConstructors :: Map XName ((,) String ([] XErased)) -> XErased -> Fresh XErased;
  -- Small lifted values may have inlined back into fields. Freshen any
  -- copied binders so repeated projections keep global identities unique.
  projectConstructors facts expression =
    do {
      normalized <- children (projectConstructors facts) expression;
      case normalized of {
        XECase (XEVar name) branches ->
          case M.lookup compareName name facts of {
            Just ((,) c args) ->
              case selectConstructor c args branches of {
                Just selected -> copy M.empty selected;
                Nothing -> freshPure normalized
              };
            Nothing -> freshPure normalized
          };
        _ -> freshPure normalized
      }
    };
  selectConstructor :: String -> [] XErased -> [] XErasedAlternative -> Maybe XErased;
  selectConstructor constructor args branches =
    case branches of {
      [] -> Nothing;
      (:) (XErasedAlternative pattern body) rest ->
        case pattern of {
          XConstructorPattern c names ->
            if (eqString constructor c && (L.length names == L.length args))
            then Just
                   (L.foldr
                      (\entry restBody ->
                         case entry of {
                           (,) optional value -> maybeLet optional value restBody
                         })
                      body
                      (L.zip names args))
            else selectConstructor constructor args rest;
          XDefaultPattern optional ->
            Just (maybeLet optional (L.foldl XEApp (XEConstructor constructor) args) body)
        }
    };
  maybeLet :: Maybe XName -> XErased -> XErased -> XErased;
  maybeLet optional value body =
    case optional of {
      Nothing -> body;
      Just name -> XELet name value body
    };
  -- Cache capped free-use counts beside each rewrite subtree. Substitution can
  -- retain an unaffected subtree without walking it, preserving rewrite order
  -- and the exact fresh-name allocation order of the original pass.
  data UseTree = UseTree XErased (Map XName Int) UseChildren;
  data UseChildren =
    UseLeaf |
    UseAbs XName UseTree |
    UseApp UseTree UseTree |
    UseLet XName UseTree UseTree |
    UseRec ([] ((,) XName UseTree)) UseTree |
    UseCase UseTree ([] ((,) XPattern UseTree));
  useTerm :: UseTree -> XErased;
  useTerm (UseTree term _ _) = term;
  useCounts :: UseTree -> Map XName Int;
  useCounts (UseTree _ counts _) = counts;
  useChildren :: UseTree -> UseChildren;
  useChildren (UseTree _ _ children) = children;
  addUses :: Int -> Int -> Int;
  addUses a b = L.min 2 (a + b);
  mergeUses :: Map XName Int -> Map XName Int -> Map XName Int;
  mergeUses a b =
    if (M.size a <= M.size b)
    then M.unionWith compareName addUses a b
    else M.unionWith compareName addUses b a;
  deleteUses :: [] XName -> Map XName Int -> Map XName Int;
  deleteUses names counts =
    L.foldl (\current name -> M.delete compareName name current) counts names;
  useAbs :: XName -> UseTree -> UseTree;
  useAbs name body =
    UseTree (XEAbs name (useTerm body)) (M.delete compareName name (useCounts body))
      (UseAbs name body);
  useApp :: UseTree -> UseTree -> UseTree;
  useApp function argument =
    UseTree (XEApp (useTerm function) (useTerm argument))
      (mergeUses (useCounts function) (useCounts argument))
      (UseApp function argument);
  useLet :: XName -> UseTree -> UseTree -> UseTree;
  useLet name value body =
    UseTree (XELet name (useTerm value) (useTerm body))
      (mergeUses (useCounts value) (M.delete compareName name (useCounts body)))
      (UseLet name value body);
  useRec :: [] ((,) XName UseTree) -> UseTree -> UseTree;
  useRec bindings body =
    let {
      counts =
        L.foldl (\current binding -> mergeUses current (useCounts (L.snd binding))) (useCounts body)
          bindings
    } in
    UseTree
      (XELetRec (L.map (\((,) name value) -> (,) name (useTerm value)) bindings) (useTerm body))
      (deleteUses (L.map L.fst bindings) counts)
      (UseRec bindings body);
  useCase :: UseTree -> [] ((,) XPattern UseTree) -> UseTree;
  useCase subject alternatives =
    let {
      counts =
        L.foldl
          (\current ((,) pattern body) ->
             mergeUses current (deleteUses (X.patternNames pattern) (useCounts body)))
          (useCounts subject)
          alternatives
    } in
    UseTree
      (XECase (useTerm subject)
         (L.map (\((,) pattern body) -> XErasedAlternative pattern (useTerm body)) alternatives))
      counts
      (UseCase subject alternatives);
  indexUses :: XErased -> UseTree;
  indexUses term =
    case term of {
      XEAbs name body -> useAbs name (indexUses body);
      XEApp function argument -> useApp (indexUses function) (indexUses argument);
      XELet name value body -> useLet name (indexUses value) (indexUses body);
      XELetRec bindings body ->
        useRec (L.map (\((,) name value) -> (,) name (indexUses value)) bindings)
          (indexUses body);
      XECase subject alternatives ->
        useCase (indexUses subject)
          (L.map (\(XErasedAlternative pattern body) -> (,) pattern (indexUses body))
             alternatives);
      XEVar name -> UseTree term (M.singleton name 1) UseLeaf;
      _ -> UseTree term M.empty UseLeaf
    };
  mapUseChildren :: (UseTree -> Fresh UseTree) -> UseTree -> Fresh UseTree;
  mapUseChildren f tree =
    case useChildren tree of {
      UseLeaf -> freshPure tree;
      UseAbs name body ->
        do {
          result <- f body;
          freshPure (useAbs name result)
        };
      UseApp function argument ->
        do {
          a <- f function;
          b <- f argument;
          freshPure (useApp a b)
        };
      UseLet name value body ->
        do {
          a <- f value;
          b <- f body;
          freshPure (useLet name a b)
        };
      UseRec bindings body ->
        do {
          values <-
            traverseFresh
              (\((,) name value) ->
                 do {
                   result <- f value;
                   freshPure ((,) name result)
                 })
              bindings;
          result <- f body;
          freshPure (useRec values result)
        };
      UseCase subject alternatives ->
        do {
          value <- f subject;
          branches <-
            traverseFresh
              (\((,) pattern body) ->
                 do {
                   result <- f body;
                   freshPure ((,) pattern result)
                 })
              alternatives;
          freshPure (useCase value branches)
        }
    };
  substituteUsed :: XName -> XErased -> UseTree -> Fresh UseTree;
  substituteUsed name value tree =
    if L.not (M.member compareName name (useCounts tree))
    then freshPure tree
    else case useTerm tree of {
           XEVar actual ->
             if eqName name actual
             then do {
                    copied <- copy M.empty value;
                    freshPure (indexUses copied)
                  }
             else freshPure tree;
           _ -> mapUseChildren (substituteUsed name value) tree
         };
  useApplications :: [] UseTree -> UseTree -> (,) UseTree ([] UseTree);
  useApplications arguments tree =
    case useChildren tree of {
      UseApp function argument -> useApplications ((:) argument arguments) function;
      _ -> (,) tree arguments
    };
  useMaybeLet :: Maybe XName -> UseTree -> UseTree -> UseTree;
  useMaybeLet optional value body =
    case optional of {
      Nothing -> body;
      Just name -> useLet name value body
    };
  selectUseConstructor :: String -> [] UseTree -> [] ((,) XPattern UseTree) -> Maybe UseTree;
  selectUseConstructor constructor arguments branches =
    case branches of {
      [] -> Nothing;
      (:) ((,) pattern body) rest ->
        case pattern of {
          XConstructorPattern name fields ->
            if (eqString constructor name && (L.length fields == L.length arguments))
            then Just
                   (L.foldr (\((,) optional value) result -> useMaybeLet optional value result)
                      body
                      (L.zip fields arguments))
            else selectUseConstructor constructor arguments rest;
          XDefaultPattern optional ->
            Just
              (useMaybeLet optional
                 (L.foldl useApp (indexUses (XEConstructor constructor)) arguments)
                 body)
        }
    };
  substituteUsedBindings :: UseTree -> [] ((,) XName UseTree) -> Fresh UseTree;
  substituteUsedBindings body bindings =
    case bindings of {
      [] -> freshPure body;
      (:) ((,) name value) rest ->
        do {
          result <- substituteUsed name (useTerm value) body;
          substituteUsedBindings result rest
        }
    };
  -- Expose a single lazy action use to the IO kernel recognizer.  Ordinary
  -- lambda/recursive/call contexts remain sharing boundaries.  The one lambda
  -- we enter is the continuation of the exact, saturated IO bind primitive;
  -- it runs once per execution of that action, not once globally.  Substitution
  -- moves pure action construction into its unique action use; it never
  -- directly executes IO. Scalar operands retain their original lazy sharing.
  -- Require the actual occurrence path to pass through bind, not merely an
  -- unrelated bind elsewhere in the body.  Zero-use subtrees remain opaque.
  singleUseIOPath :: XName -> Bool -> UseTree -> Bool;
  singleUseIOPath name insideIO tree =
    if M.findWithDefault compareName 0 name (useCounts tree) == 0
    then True
    else case useChildren tree of {
      UseLeaf ->
        case useTerm tree of {
          XEVar actual -> insideIO && eqName name actual;
          _ -> False
        };
      UseAbs _ _ -> False;
      UseRec _ _ -> False;
      UseLet _ value body ->
        singleUseIOPath name False value && singleUseIOPath name insideIO body;
      UseCase subject branches ->
        singleUseIOPath name False subject &&
        L.all (\entry -> singleUseIOPath name insideIO (L.snd entry)) branches;
      UseApp _ _ ->
        case useApplications [] tree of {
          (,) function arguments ->
            case useTerm function of {
              XEPrimitive PIOBind ->
                case arguments of {
                  (:) action ((:) continuation []) ->
                    case useChildren continuation of {
                      UseAbs _ body ->
                        singleUseIOPath name True action && singleUseIOPath name True body;
                      _ -> False
                    };
                  _ -> False
                };
              XEPrimitive PIfThenElse ->
                case arguments of {
                  (:) condition ((:) yes ((:) no [])) ->
                    singleUseIOPath name False condition &&
                    singleUseIOPath name insideIO yes && singleUseIOPath name insideIO no;
                  _ -> False
                };
              XEPrimitive primitive ->
                L.length arguments == P.primitiveArity primitive &&
                L.all (singleUseIOPath name False) arguments;
              _ -> False
            }
        }
    };
  -- Recover sharing when a nonrecursive local function is called only with
  -- the same complete vector of existing outer variables. Qualified local
  -- values can acquire ground dictionary parameters before inference; leaving
  -- those lambdas at every use rebuilds the value. This is static all-use
  -- specialization, not memoization or a dictionary/type-name heuristic.
  -- A single call must also normalize here: its immediate beta contraction can
  -- expose common arguments to an enclosing shared binding before inlining.
  data CommonCalls = NoCommonCalls | CommonCalls ([] XName) | DifferentCalls;
  sameCallNames :: [] XName -> [] XName -> Bool;
  sameCallNames left right = case left of {
    [] -> L.null right;
    (:) a rest -> case right of {
      [] -> False;
      (:) b more -> eqName a b && sameCallNames rest more
    }
  };
  mergeCommonCalls :: CommonCalls -> CommonCalls -> CommonCalls;
  mergeCommonCalls left right = case left of {
    DifferentCalls -> DifferentCalls;
    NoCommonCalls -> right;
    CommonCalls names -> case right of {
      DifferentCalls -> DifferentCalls;
      NoCommonCalls -> left;
      CommonCalls others -> if sameCallNames names others then left else DifferentCalls
    }
  };
  outerCallNames :: XName -> Map XName Int -> [] UseTree -> Maybe ([] XName);
  outerCallNames target outer arguments = case arguments of {
    [] -> Just [];
    (:) argument rest -> case useTerm argument of {
      XEVar name ->
        if L.not (eqName target name) && M.member compareName name outer
        then case outerCallNames target outer rest of {
          Nothing -> Nothing;
          Just names -> Just ((:) name names)
        }
        else Nothing;
      _ -> Nothing
    }
  };
  commonCalls :: XName -> Int -> Map XName Int -> UseTree -> CommonCalls;
  commonCalls target arity outer tree =
    if M.findWithDefault compareName 0 target (useCounts tree) == 0
    then NoCommonCalls
    else case useApplications [] tree of {
      (,) function arguments -> case useTerm function of {
        XEVar name ->
          if eqName target name
          then if L.length arguments == arity
               then case outerCallNames target outer arguments of {
                 Just names -> CommonCalls names;
                 Nothing -> DifferentCalls
               }
               else DifferentCalls
          else commonChildCalls target arity outer tree;
        _ -> commonChildCalls target arity outer tree
      }
    };
  commonChildCalls :: XName -> Int -> Map XName Int -> UseTree -> CommonCalls;
  commonChildCalls target arity outer tree =
    let { collect = commonCalls target arity outer;
          combine values = L.foldl mergeCommonCalls NoCommonCalls (L.map collect values)
    } in case useChildren tree of {
      UseLeaf -> DifferentCalls;
      UseAbs _ body -> collect body;
      UseApp function argument -> combine ((:) function ((:) argument []));
      UseLet _ value body -> combine ((:) value ((:) body []));
      UseRec definitions body -> combine ((:) body (L.map L.snd definitions));
      UseCase subject alternatives -> combine ((:) subject (L.map L.snd alternatives))
    };
  contractCommonCalls :: XName -> UseTree -> Fresh UseTree;
  contractCommonCalls target tree =
    if M.findWithDefault compareName 0 target (useCounts tree) == 0
    then freshPure tree
    else case useApplications [] tree of {
      (,) function _ -> case useTerm function of {
        XEVar name -> if eqName target name then freshPure function
                      else mapUseChildren (contractCommonCalls target) tree;
        _ -> mapUseChildren (contractCommonCalls target) tree
      }
    };
  -- Arguments are existing variables, so beta substitution is non-demanding.
  -- Expose them immediately: an enclosing binding must see the actual common
  -- evidence before its ordinary lambda inliner can duplicate computations.
  specializeCommonParameters :: UseTree -> [] XName -> Fresh UseTree;
  specializeCommonParameters value arguments = case arguments of {
    [] -> freshPure value;
    (:) argument rest -> case useChildren value of {
      UseAbs parameter body -> do {
        replaced <- substituteUsed parameter (XEVar argument) body;
        specializeCommonParameters replaced rest
      };
      _ -> freshPure value
    }
  };
  specializeSharedValue :: XName -> UseTree -> UseTree -> Fresh (Maybe UseTree);
  specializeSharedValue name value body = case lambdas (useTerm value) of {
    (,) [] _ -> freshPure Nothing;
    (,) parameters _ ->
      if M.findWithDefault compareName 0 name (useCounts body) < 1
      then freshPure Nothing
      else case commonCalls name (L.length parameters) (useCounts body) body of {
        CommonCalls arguments -> do {
          result <- contractCommonCalls name body;
          specialized <- specializeCommonParameters value arguments;
          freshPure (Just (useLet name specialized result))
        };
        _ -> freshPure Nothing
      }
  };
  rewriteOrdinaryLet :: UseTree -> XName -> UseTree -> UseTree -> Fresh UseTree;
  rewriteOrdinaryLet tree name value body =
        let {
          uses = M.findWithDefault compareName 0 name (useCounts body)
        } in
        if (uses == 0)
        then freshPure body
        else if smallValue (useTerm value)
             then substituteUsed name (useTerm value) body
             else if uses == 1 && singleUseIOPath name False body
                  then substituteUsed name (useTerm value) body
                  else case useChildren value of {
                    UseAbs _ _ ->
                      if (uses == 1)
                      then substituteUsed name (useTerm value) body
                      else freshPure tree;
                    UseLet inner a b -> freshPure (useLet inner a (useLet name b body));
                    UseRec ((:) ((,) r rhs) []) result ->
                      case useTerm result of {
                        XEVar other ->
                          if eqName r other
                          then do {
                                 replaced <- copy (M.singleton r (XEVar name)) (useTerm rhs);
                                 freshPure (useRec ((:) ((,) name (indexUses replaced)) []) body)
                               }
                          else freshPure tree;
                        _ -> freshPure tree
                      };
                    _ -> freshPure tree
                  };
  rewriteUsed :: UseTree -> Fresh UseTree;
  rewriteUsed tree =
    case useChildren tree of {
      UseApp function argument ->
        case useChildren function of {
          UseAbs name body -> freshPure (useLet name argument body);
          UseLet name value body -> freshPure (useLet name value (useApp body argument));
          UseRec bindings body -> freshPure (useRec bindings (useApp body argument));
          _ -> freshPure tree
        };
      UseLet name value body -> do {
        shared <- specializeSharedValue name value body;
        case shared of {
          Just result -> freshPure result;
          Nothing -> rewriteOrdinaryLet tree name value body
        }
      };
      UseRec bindings body ->
        let {
          group = S.fromList compareName (L.map L.fst bindings)
        } in
        let {
          expandable =
            L.filter
              (\((,) _ value) ->
                 (smallValue (useTerm value) &&
                  S.null (S.intersection compareName (free (useTerm value)) group)))
              bindings
        } in
        let {
          names = S.fromList compareName (L.map L.fst expandable)
        } in
        let {
          keep = L.filter (\((,) name _) -> L.not (S.member compareName name names)) bindings
        } in
        substituteUsedBindings (if L.null keep then body else useRec keep body) expandable;
      UseCase subject ((:) ((,) (XDefaultPattern optional) body) []) ->
        freshPure (useMaybeLet optional subject body);
      UseCase subject branches ->
        case useApplications [] subject of {
          (,) head arguments ->
            case useTerm head of {
              XEConstructor constructor ->
                case selectUseConstructor constructor arguments branches of {
                  Just selected -> freshPure selected;
                  Nothing -> freshPure tree
                };
              _ -> freshPure tree
            }
        };
      _ -> freshPure tree
    };
  passUsed :: UseTree -> Fresh UseTree;
  passUsed tree =
    do {
      normalized <- mapUseChildren passUsed tree;
      rewriteUsed normalized
    };
  -- Build use indices for normalized results directly. An initial indexed copy
  -- of the input is unnecessary: its counts are never consulted by this walk.
  passRaw :: XErased -> Fresh UseTree;
  passRaw expression =
    do {
      normalized <-
        case expression of {
          XEAbs name body ->
            do {
              result <- passRaw body;
              freshPure (useAbs name result)
            };
          XEApp function argument ->
            do {
              a <- passRaw function;
              b <- passRaw argument;
              freshPure (useApp a b)
            };
          XELet name value body ->
            do {
              a <- passRaw value;
              b <- passRaw body;
              freshPure (useLet name a b)
            };
          XELetRec bindings body ->
            do {
              values <-
                traverseFresh
                  (\((,) name value) ->
                     do {
                       result <- passRaw value;
                       freshPure ((,) name result)
                     })
                  bindings;
              result <- passRaw body;
              freshPure (useRec values result)
            };
          XECase subject alternatives ->
            do {
              value <- passRaw subject;
              branches <-
                traverseFresh
                  (\(XErasedAlternative pattern body) ->
                     do {
                       result <- passRaw body;
                       freshPure ((,) pattern result)
                     })
                  alternatives;
              freshPure (useCase value branches)
            };
          _ -> freshPure (indexUses expression)
        };
      rewriteUsed normalized
    };
  pass :: XErased -> Fresh XErased;
  pass expression =
    do {
      result <- passRaw expression;
      freshPure (useTerm result)
    };
  maxIdentity :: XErased -> Int;
  maxIdentity expression =
    case expression of {
      XEVar n -> nameId n;
      XEAbs n b -> L.max (nameId n) (maxIdentity b);
      XEApp f a -> L.max (maxIdentity f) (maxIdentity a);
      XELet n a b -> L.max (nameId n) (L.max (maxIdentity a) (maxIdentity b));
      XELetRec ds b ->
        L.foldl
          (\maximum entry ->
             case entry of {
               (,) n a -> L.max maximum (L.max (nameId n) (maxIdentity a))
             })
          (maxIdentity b)
          ds;
      XECase a branches ->
        L.foldl
          (\maximum branch ->
             case branch of {
               XErasedAlternative p b ->
                 L.foldl (\best n -> L.max best (nameId n)) (L.max maximum (maxIdentity b))
                   (X.patternNames p)
             })
          (maxIdentity a)
          branches;
      _ -> 0
    };
  iterations :: Map String (Maybe Int) -> Int -> XErased -> Fresh XErased;
  iterations arities count expression =
    if (count == 0)
    then freshPure expression
    else do {
           let {
             facts = constructorFacts arities expression
           };
           projected <-
             if M.null facts then freshPure expression else projectConstructors facts expression;
           next <- pass projected;
           if X.equalErased expression next
           then freshPure expression
           else iterations arities (count - 1) next
         };
  -- Bound cloning by both template size and the shared fresh-name budget.
  -- Only syntactic function values are copied; captured computations remain
  -- shared variables. The traversal never revisits its newly created clones.
  freshSeed :: Fresh Int;
  freshSeed = Fresh (\seed -> (,) seed seed);
  specializationDefinitions :: XErased -> Map XName XErased;
  specializationDefinitions expression =
    let {
      local =
        case expression of {
          XELet n a b -> M.singleton n a;
          XELetRec ds b -> M.fromList compareName ds;
          _ -> M.empty
        }
    } in
    M.unions compareName ((:) local (L.map specializationDefinitions (subterms expression)));
  staticCallback :: Map XName XErased -> XErased -> Bool;
  staticCallback definitions expression =
    case expression of {
      XEAbs n b -> (remainingSize 64 expression >= 0);
      _ ->
        case applications expression of {
          (,) (XEVar n) args ->
            case M.lookup compareName n definitions of {
              Nothing -> False;
              Just rhs ->
                case lambdas rhs of {
                  (,) parameters body -> ((L.length args < L.length parameters) && L.all atom args)
                }
            };
          (,) (XEPrimitive p) args -> L.null args;
          (,) (XEConstructor c) args -> L.all atom args;
          _ -> False
        }
    };
  appliedParameter :: XName -> XErased -> Bool;
  appliedParameter parameter expression =
    case applications expression of {
      (,) (XEVar name) ((:) first rest) ->
        if eqName name parameter
        then True
        else L.any (appliedParameter parameter) (subterms expression);
      _ -> L.any (appliedParameter parameter) (subterms expression)
    };
  specializeHigherOrder :: XErased -> Fresh XErased;
  specializeHigherOrder expression =
    do {
      seed <- freshSeed;
      specializeVisit (seed + 16384) (specializationDefinitions expression) expression
    };
  specializeVisit :: Int -> Map XName XErased -> XErased -> Fresh XErased;
  specializeVisit limit definitions expression =
    do {
      normalized <- children (specializeVisit limit definitions) expression;
      used <- freshSeed;
      case applications normalized of {
        (,) (XEVar name) ((:) callback args) ->
          if (used >= limit)
          then freshPure normalized
          else case M.lookup compareName name definitions of {
                 Nothing -> freshPure normalized;
                 Just rhs ->
                   case lambdas rhs of {
                     (,) ((:) first ((:) next rest)) body ->
                       if ((L.length args == (1 + L.length rest)) &&
                           ((remainingSize 128 rhs >= 0) &&
                            (staticCallback definitions callback &&
                             (S.member compareName name (free body) &&
                              appliedParameter first body))))
                       then specializeCall name rhs callback args
                       else freshPure normalized;
                     _ -> freshPure normalized
                   }
               };
        _ -> freshPure normalized
      }
    };
  specializeCall :: XName -> XErased -> XErased -> [] XErased -> Fresh XErased;
  -- Rename the original parameter scopes before inserting the callback,
  -- whose free names belong to this call site's enclosing scope.
  specializeCall name rhs callback arguments =
    do {
      specialized <- freshName;
      copied <- copy M.empty rhs;
      case lambdas copied of {
        (,) ((:) key parameters) body ->
          do {
            replaced <- specializeBody name specialized key (L.length parameters) callback body;
            freshPure
              (XELetRec ((:) ((,) specialized (L.foldr XEAbs replaced parameters)) [])
                 (L.foldl XEApp (XEVar specialized) arguments))
          };
        _ -> freshPure (L.foldl XEApp (XEVar name) ((:) callback arguments))
      }
    };
  specializeBody :: XName -> XName -> XName -> Int -> XErased -> XErased -> Fresh XErased;
  specializeBody original specialized key arity callback expression =
    case applications expression of {
      (,) (XEVar self) ((:) (XEVar argument) remaining) ->
        if (eqName self original && (eqName argument key && (L.length remaining == arity)))
        then do {
               arguments <-
                 traverseFresh (specializeBody original specialized key arity callback) remaining;
               freshPure (L.foldl XEApp (XEVar specialized) arguments)
             }
        else specializeOther original specialized key arity callback expression;
      _ -> specializeOther original specialized key arity callback expression
    };
  specializeOther :: XName -> XName -> XName -> Int -> XErased -> XErased -> Fresh XErased;
  specializeOther original specialized key arity callback expression =
    case expression of {
      XEVar name -> if eqName name key then copy M.empty callback else freshPure expression;
      _ -> children (specializeBody original specialized key arity callback) expression
    };
  optimizeWork :: XErased -> Fresh XErased;
  optimizeWork expression =
    do {
      unique <- copy M.empty expression;
      clean <- identities unique;
      recursive <- fixedPoints clean;
      let {
        arities = constructorArities recursive
      };
      lifted <- liftConstructorFields arities recursive;
      simple <- iterations arities 16 lifted;
      specialized <- specializeHigherOrder simple;
      iterations arities 16 specialized
    };
  optimize :: XErased -> XErased;
  optimize expression =
    case runFresh (optimizeWork expression) (1 + maxIdentity expression) of {
      (,) normalized seed ->
        case runFresh (copy M.empty normalized) 0 of {
          (,) result next -> result
        }
    }
}
