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
  freshName = Fresh (\seed -> (,) (XName seed "native") (L.advanceIdentity seed 1));
  nameId :: XName -> Int;
  nameId (XName n hint) = n;
  compareName :: XName -> XName -> Int;
  compareName a b =
    if (nameId a < nameId b) then (0 - 1) else if (nameId a == nameId b) then 0 else 1;
  eqName :: XName -> XName -> Bool;
  eqName a b = (nameId a == nameId b);
  free :: XErased -> Set XName;
  free expression = freeWith free expression;
  freeWith :: (XErased -> Set XName) -> XErased -> Set XName;
  freeWith descend expression = case expression of {
    XEVar n -> S.singleton n;
    XEAbs n b -> S.delete compareName n (descend b);
    XEApp f a -> S.union compareName (descend f) (descend a);
    XELet n a b -> S.union compareName (descend a) (S.delete compareName n (descend b));
    XELetRec ds b -> S.difference compareName
      (S.unions compareName ((:) (descend b) (L.map (L.compose descend L.snd) ds)))
      (S.fromList compareName (L.map L.fst ds));
    XECase a branches -> S.union compareName (descend a)
      (S.unions compareName (L.map (freeAlternativeWith descend) branches));
    _ -> S.empty
  };
  freeAlternative :: XErasedAlternative -> Set XName;
  freeAlternative = freeAlternativeWith free;
  freeAlternativeWith descend (XErasedAlternative pattern body) =
    S.difference compareName (descend body) (S.fromList compareName (X.patternNames pattern));
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
      reduceIdentity normalized
    };
  reduceIdentity normalized = case normalized of {
    XEApp (XEAbs n (XEVar other)) argument ->
      if eqName n other then freshPure argument else freshPure normalized;
    XELet n (XEVar a) b -> copy (M.singleton n (XEVar a)) b;
    _ -> freshPure normalized
  };
  -- Recognize helpers on the freshened declaration spine. These identities
  -- remain distinct underneath nested lambdas, patterns and recursive groups.
  data FoldBranch = ReturnField Int | CombineFields Primitive Int Int;
  data UnaryConstructorUse = BuildsField String | SelectsField String |
    FoldsConstructors (Map String ((,) Int FoldBranch)) | ComposesFunctions | TranslatesBy Int;
  unaryConstructorUse term = case term of {
    XEAbs name (XEApp (XEConstructor constructor) (XEVar field)) ->
      if eqName name field then Just (BuildsField constructor) else Nothing;
    XEAbs name (XECase (XEVar subject)
        [XErasedAlternative (XConstructorPattern constructor [Just field]) (XEVar result)]) ->
      if eqName name subject && eqName field result then Just (SelectsField constructor) else Nothing;
    _ -> Nothing
  };
  -- The checked argument can pass through erased identities and local
  -- aliases on its way to a case. A recursive name must remain in scope
  -- for every recursive call in the branch table.
  constructorFold self value = case skipIdentity value of {
    XEAbs parameter rhs -> let {
      inspect names expression = case skipIdentity expression of {
        XELet alias from rest -> if L.not (eqName alias self) && argumentAlias names from
          then inspect (S.insert compareName alias names) rest else Nothing;
        XECase subject branches -> if argumentAlias names subject && L.not (L.null branches)
          then L.foldM (foldAlternative self) M.empty branches else Nothing;
        _ -> Nothing
      }
    } in if eqName self parameter then Nothing else inspect (S.singleton parameter) rhs;
    _ -> Nothing
  };
  foldAlternative self known (XErasedAlternative pattern body) = case pattern of {
    XConstructorPattern tag fields -> let {
      named = X.patternNames pattern;
      field name = fmap L.fst (L.find (\((,) _ item) -> case item of {
        Just binder -> eqName binder name; Nothing -> False
      }) (L.mapIndexed (\i item -> (,) i item) fields));
      child expr = case expr of {
        XEApp (XEVar f) (XEVar arg) -> if eqName self f then field arg else Nothing;
        _ -> Nothing
      }
    } in if M.member compareString tag known || L.any (eqName self) named ||
      S.size (S.fromList compareName named) /= L.length named then Nothing else do {
      rule <- case body of {
        XEVar name -> fmap ReturnField (field name);
        XEApp (XEApp (XEPrimitive primitive) left) right -> do {
          a <- child left; b <- child right;
          if a == b then Nothing else Just (CombineFields primitive a b)
        };
        _ -> Nothing
      };
      Just (M.insert compareString tag ((,) (L.length fields) rule) known)
    };
    _ -> Nothing
  };
  data ConstructorValue = ConstructorTerm XErased | ConstructorSum XName Int Int;
  constructorTerm value = case value of {
    ConstructorTerm term -> term;
    ConstructorSum name scale offset -> affineIntTerm name scale offset
  };
  constructorSummand value = case value of {
    ConstructorTerm term -> intSummand term;
    -- Inspecting a previously rendered summand forces its translation first,
    -- then its choice of a variable or a multiplication.
    ConstructorSum name scale offset -> seq offset (seq scale (Just ((,,) name scale offset)))
  };
  -- Each selected child is folded once. Keep an affine result in its checked
  -- Int representation until a different operation or the consumer needs a term.
  oneConstructorField :: forall a. a -> Int -> Maybe a;
  oneConstructorField value i = if i == 0 then Just value else Nothing;
  twoConstructorFields :: forall a. a -> a -> Int -> Maybe a;
  twoConstructorFields left right i = if i == 0 then Just left
    else if i == 1 then Just right else Nothing;
  erasedConstructorFields apply current = case current of {
      XEConstructor tag -> apply tag 0 (\i -> L.at i []);
      XEApp fn right -> case fn of {
        XEConstructor tag -> apply tag 1 (oneConstructorField right);
        XEApp head left -> case head of {
          XEConstructor tag -> apply tag 2 (twoConstructorFields left right);
          XEApp _ _ -> case collectApplications [left,right] head of {
            (,) (XEConstructor tag) fields -> apply tag (L.length fields) (\i -> L.at i fields);
            _ -> Nothing
          };
          _ -> Nothing
        };
        _ -> Nothing
      };
      _ -> Nothing
    };
  -- Type abstractions, instantiations and datatype scopes have no erased
  -- application node. Walk through them without evaluating their metadata.
  skipTypeWrappers term = case term of {
    XTypeAbs _ _ body -> skipTypeWrappers body;
    XTypeApp body _ -> skipTypeWrappers body;
    XWithData _ body -> skipTypeWrappers body;
    _ -> term
  };
  typedConstructorFields apply input = let {
    -- Only wider applications need a list for indexed access to their fields.
    collect args current = case skipTypeWrappers current of {
      XApp fn arg -> collect ((:) arg args) fn;
      XConstructor tag _ -> apply tag (L.length args) (\i -> L.at i args);
      _ -> Nothing
    }
  } in case skipTypeWrappers input of {
    XConstructor tag _ -> apply tag 0 (\i -> L.at i []);
    XApp fn right -> case skipTypeWrappers fn of {
      XConstructor tag _ -> apply tag 1 (oneConstructorField right);
      XApp head left -> case skipTypeWrappers head of {
        XConstructor tag _ -> apply tag 2 (twoConstructorFields left right);
        XApp rest prior -> collect [prior,left,right] rest;
        _ -> Nothing
      };
      _ -> Nothing
    };
    _ -> Nothing
  };
  foldKnownConstructor = foldConstructorUsing L.id erasedConstructorFields;
  foldTypedConstructor = foldConstructorUsing X.erase typedConstructorFields;
  foldConstructorUsing erase fields rules tree = let {
    visit current = fields apply current;
    apply tag count field = case M.lookup compareString tag rules of {
      Just ((,) arity rule) -> if arity /= count then Nothing else case rule of {
        ReturnField index -> fmap (\x -> ConstructorTerm (erase x)) (field index);
        CombineFields primitive first second -> do {
          left <- field first >>= visit;
          right <- field second >>= visit;
          let { applied = ConstructorTerm (XEApp (XEApp (XEPrimitive primitive)
                  (constructorTerm left)) (constructorTerm right)) };
          Just (case primitive of {
            PAddInt -> L.fromMaybe applied (addIntSummands ConstructorSum
              (constructorSummand left) (constructorSummand right));
            _ -> applied
          })
        }
      };
      Nothing -> Nothing
    }
  } in fmap constructorTerm (visit tree);
  -- The identity pass has already resolved erased coercions and local aliases
  -- in the RHS. Record composition only for the exact three-binder body.
  checkedFunctionUse known rhs = case rhs of {
    XEVar name -> M.lookup compareName name known;
    XEAbs outer (XEAbs inner (XEAbs input (XEApp (XEVar f) (XEApp (XEVar g) (XEVar x))))) ->
      if eqName outer f && eqName inner g && eqName input x &&
         L.not (eqName outer inner || eqName outer input || eqName inner input)
      then Just ComposesFunctions else Nothing;
    XEAbs name (XEVar result) -> if eqName name result then Just (TranslatesBy 0) else Nothing;
    XEAbs _ _ -> case iterationStep rhs of {
      Just (IntegerTranslation amount) -> Just (TranslatesBy amount);
      _ -> unaryConstructorUse rhs
    };
    _ -> Nothing
  };
  -- Only a saturated composition becomes f (g x). Each callback and the
  -- argument stay in the same demand position, even for a partial callback.
  -- Consecutive integer translations add in the language's wrapping Int ring.
  applyComposed known function argument = case function of {
    XEApp (XEApp (XEVar name) outer) inner -> case M.lookup compareName name known of {
      Just ComposesFunctions -> applyComposed known outer (applyComposed known inner argument);
      _ -> XEApp function argument
    };
    XEVar name -> case M.lookup compareName name known of {
      Just (TranslatesBy amount) -> case argument of {
        XEApp (XEApp (XEPrimitive PAddInt) base) (XEInt offset) -> translated (amount + offset) base;
        _ -> translated amount argument
      };
      _ -> XEApp function argument
    };
    _ -> XEApp function argument
  };
  checkedIdentities known expression = case expression of {
    XELet name value body -> do {
      rhs <- constructorIdentities known value;
      let { following = case checkedFunctionUse known rhs of {
        Just role -> M.insert compareName name role known; Nothing -> known
      } };
      result <- checkedIdentities following body;
      reduceIdentity (XELet name rhs result)
    };
    XELetRec [(,) name value] body -> do {
      rhs <- constructorIdentities known value;
      result <- case constructorFold name rhs of {
        Just rules -> checkedIdentities (M.insert compareName name (FoldsConstructors rules) known) body;
        Nothing -> constructorIdentities known body
      };
      freshPure (XELetRec [(,) name rhs] result)
    };
    _ -> constructorIdentities known expression
  };
  constructorIdentities known expression = if M.null known
    then identities expression else constructorApplications known expression;
  -- Inspect only partial applications built from checked composition roles
  -- and variables. Their ordinary child pass preserves the input syntax and
  -- seed. Callback roles are needed only when the erased result is demanded.
  translationChain :: Map XName UnaryConstructorUse -> XErased -> Maybe (Maybe Int);
  translationChain known function = let {
    amount name = case M.lookup compareName name known of {
      Just (TranslatesBy n) -> Just n; _ -> Nothing
    };
    combine outer rest = case amount outer of {
      Just first -> case rest of {
        Just later -> Just (seq later (first + later)); Nothing -> Nothing
      };
      Nothing -> Nothing
    };
    walk operator = case operator of {
      XEApp (XEApp (XEVar name) (XEVar outer)) inner -> case M.lookup compareName name known of {
        Just ComposesFunctions -> case walk inner of {
          Just rest -> Just (combine outer rest); Nothing -> Nothing
        };
        _ -> Nothing
      };
      XEVar name -> Just (amount name);
      _ -> Nothing
    }
  } in walk function;
  constructorApplications known expression = Fresh (\seed -> let {
    ordinary = runFresh (ordinaryConstructorApplications known expression) seed
  } in case expression of {
    XEApp function@(XEApp (XEApp (XEVar _) _) _) argument -> case translationChain known function of {
      Just summary -> let {
        result = case summary of {
          Just amount -> translated amount argument;
          Nothing -> applyComposed known function argument
        }
      } in case argument of {
        XEVar _ -> (,) result seed; XEInt _ -> (,) result seed; _ -> ordinary
      };
      Nothing -> ordinary
    };
    _ -> ordinary
  });
  ordinaryConstructorApplications known expression = do {
    term <- children (constructorApplications known) expression;
    case term of {
      XEApp (XEVar function) argument -> case M.lookup compareName function known of {
        Just (FoldsConstructors rules) -> freshPure (L.fromMaybe term (foldKnownConstructor rules argument));
        Just (SelectsField wanted) -> case argument of {
          XEApp (XEVar build) field -> case M.lookup compareName build known of {
            Just (BuildsField actual) -> freshPure (if eqString wanted actual then field else term);
            _ -> freshPure term
          };
          _ -> freshPure term
        };
        _ -> freshPure term
      };
      XEApp (XEApp (XEPrimitive PAddInt) left) right ->
        freshPure (L.fromMaybe term (combineIntSummands left right));
      XEApp function argument -> case function of {
        XEApp (XEApp (XEVar _) _) _ -> freshPure (applyComposed known function argument);
        _ -> reduceIdentity term
      };
      _ -> reduceIdentity term
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
    let { counts = bindingUses bindings body } in
    UseTree
      (XELetRec (L.map (\((,) name value) -> (,) name (useTerm value)) bindings) (useTerm body))
      (deleteUses (L.map L.fst bindings) counts)
      (UseRec bindings body);
  bindingUses bindings body = L.foldl
    (\current binding -> mergeUses current (useCounts (L.snd binding))) (useCounts body) bindings;
  -- Inlining a shared lambda with two free occurrences can multiply both
  -- incoming and outgoing dependencies at every layer. A linear wrapper
  -- forwards at most one free occurrence per use, so it can still inline.
  branchesToFreeValues value = case useChildren value of {
    UseAbs _ _ -> case M.toList (useCounts value) of {
      [] -> False;
      [(,) _ count] -> count > 1;
      _ -> True
    };
    _ -> False
  };
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
  -- Sink one nonescaping lazy binding into its unique selected branch.
  -- Conditions/scrutinees and reusable boundaries remain opaque. This does
  -- not make the RHS globally strict: an unselected branch never evaluates it.
  singleUseBranchPath :: XName -> Bool -> UseTree -> Bool;
  singleUseBranchPath name selected tree =
    if M.findWithDefault compareName 0 name (useCounts tree) == 0
    then True
    else case useChildren tree of {
      UseLeaf -> case useTerm tree of {
        XEVar actual -> selected && eqName name actual;
        _ -> False
      };
      UseAbs _ _ -> False;
      UseRec _ _ -> False;
      UseLet _ value body ->
        (M.findWithDefault compareName 0 name (useCounts value) == 0) &&
        singleUseBranchPath name selected body;
      UseCase subject branches ->
        (M.findWithDefault compareName 0 name (useCounts subject) == 0) &&
        L.all (\entry -> singleUseBranchPath name True (L.snd entry)) branches;
      UseApp _ _ -> case useApplications [] tree of {
        (,) function arguments -> case useTerm function of {
          XEPrimitive PIfThenElse -> case arguments of {
            (:) condition ((:) yes ((:) no [])) ->
              (M.findWithDefault compareName 0 name (useCounts condition) == 0) &&
              (singleUseBranchPath name True yes && singleUseBranchPath name True no);
            _ -> False
          };
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
             else if uses == 1 &&
                     (singleUseIOPath name False body || singleUseBranchPath name False body)
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
  -- Collect two integer summands which depend on the very same binder.
  -- Signed machine Int addition and multiplication wrap. Retain the operand
  -- even for a zero coefficient so that forcing a failing binder still fails.
  intSummand :: XErased -> Maybe ((,,) XName Int Int);
  intSummand term = let {
    withOffset value offset = case value of {
      XEVar name -> Just ((,,) name 1 offset);
      XEApp (XEApp (XEPrimitive PMulInt) (XEVar name)) (XEInt factor) -> Just ((,,) name factor offset);
      _ -> Nothing
    }
  } in case term of {
    XEApp (XEApp (XEPrimitive PAddInt) value) (XEInt offset) -> withOffset value offset;
    XEApp (XEApp (XEPrimitive PAddInt) (XEInt offset)) value -> withOffset value offset;
    _ -> withOffset term 0
  };
  affineIntTerm name scale offset = translated offset (if scale == 1 then XEVar name
    else XEApp (XEApp (XEPrimitive PMulInt) (XEVar name)) (XEInt scale));
  addIntSummands create left right = case left of {
    Just ((,,) name factor offset) -> case right of {
      Just ((,,) other otherFactor otherOffset) -> if eqName name other
        then Just (create name (factor + otherFactor) (offset + otherOffset)) else Nothing;
      Nothing -> Nothing
    };
    Nothing -> Nothing
  };
  combineIntSummands :: XErased -> XErased -> Maybe XErased;
  combineIntSummands left right = addIntSummands affineIntTerm (intSummand left) (intSummand right);
  rewriteUsed :: UseTree -> Fresh UseTree;
  rewriteUsed = rewriteUsedFor False;
  rewriteUsedFor checked tree =
    case useChildren tree of {
      UseApp function argument ->
        case useChildren function of {
          UseAbs name body -> freshPure (useLet name argument body);
          UseLet name value body -> freshPure (useLet name value (useApp body argument));
          UseRec bindings body -> freshPure (useRec bindings (useApp body argument));
          UseApp operator left -> case useTerm operator of {
            XEPrimitive PAddInt -> case combineIntSummands (useTerm left) (useTerm argument) of {
              Just reduced -> freshPure (indexUses reduced);
              Nothing -> freshPure tree
            };
            _ -> freshPure tree
          };
          _ -> freshPure tree
        };
      UseLet name value body -> case useTerm body of {
        XEVar result -> freshPure (if eqName name result then value else body);
        _ -> do {
          shared <- specializeSharedValue name value body;
          case shared of {
            Just result -> freshPure result;
            Nothing -> rewriteOrdinaryLet tree name value body
          }
        }
      };
      UseRec bindings body ->
        let {
          group = S.fromList compareName (L.map L.fst bindings);
          counts = bindingUses bindings body
        } in
        let {
          expandable =
            L.filter
              (\((,) name value) ->
                 (smallValue (useTerm value) &&
                  (L.not checked || L.not (branchesToFreeValues value) ||
                   M.findWithDefault compareName 0 name counts < 2) &&
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
  -- This route is reserved for finite checked input, after the optimizer's
  -- initial copy establishes globally unique binders. Legacy raw/partial tree
  -- entry points above retain their original traversal and demand behavior.
  -- A variable passed as an argument is used as a value. A callee whose
  -- first argument is not an outer variable also fails commonCalls at every
  -- positive arity. Scope-aware traversal excludes locally bound witnesses.
  negativeCalls :: UseTree -> Set XName;
  negativeCalls tree = negativeCallsIn (useCounts tree) tree;
  negativeCallsIn outer tree =
    case useChildren tree of {
      UseLeaf -> S.empty;
      UseAbs name body -> S.delete compareName name (negativeCallsIn outer body);
      UseApp function argument ->
        let { nested = S.union compareName (negativeCallsIn outer function) (negativeCallsIn outer argument) } in
        case useTerm argument of {
          XEVar argumentName -> let { passed = S.insert compareName argumentName nested } in
            case useTerm function of {
              XEVar name -> if M.member compareName argumentName outer then passed
                else S.insert compareName name passed;
              _ -> passed
            };
          _ -> case useTerm function of {
            XEVar name -> S.insert compareName name nested;
            _ -> nested
          }
        };
      UseLet name value body ->
        S.union compareName (negativeCallsIn outer value)
          (S.delete compareName name (negativeCallsIn outer body));
      UseRec bindings body ->
        S.difference compareName
          (S.unions compareName ((:) (negativeCallsIn outer body) (L.map (\entry -> negativeCallsIn outer (L.snd entry)) bindings)))
          (S.fromList compareName (L.map L.fst bindings));
      UseCase subject alternatives ->
        S.union compareName (negativeCallsIn outer subject)
          (S.unions compareName
             (L.map
                (\((,) pattern body) ->
                   S.difference compareName (negativeCallsIn outer body)
                     (S.fromList compareName (X.patternNames pattern)))
                alternatives))
    };
  -- Keep exact counts through three occurrences, with four meaning "many".
  -- This extra root summary leaves the public UseTree's 0/1/many contract
  -- unchanged. It is built once at a boundary, then updated by substitution.
  mergePendingUses a b = M.unionWith compareName (\x y -> L.min 4 (x + y)) a b;
  limitedUses tree = case useChildren tree of {
    UseLeaf -> useCounts tree;
    UseAbs name body -> M.delete compareName name (limitedUses body);
    UseApp function argument -> mergePendingUses (limitedUses function) (limitedUses argument);
    UseLet name value body -> mergePendingUses (limitedUses value)
      (M.delete compareName name (limitedUses body));
    UseRec bindings body -> deleteUses (L.map L.fst bindings)
      (L.foldl (\counts entry -> mergePendingUses counts (limitedUses (L.snd entry))) (limitedUses body) bindings);
    UseCase subject alternatives -> L.foldl
      (\counts entry -> mergePendingUses counts
        (deleteUses (X.patternNames (L.fst entry)) (limitedUses (L.snd entry))))
      (limitedUses subject) alternatives
  };
  -- The base skeleton is immutable. Entries are already fresh-copied at the
  -- original inner-to-outer let decision, never when materializing. Counts and
  -- witnesses describe the effective expanded body, not just the skeleton.
  -- A queue supplies a distinct copy for every occurrence, in original DFS
  -- order. No binder identity is shared between several substitutions.
  data PendingBody = PendingBody UseTree (Map XName ([] UseTree)) (Map XName Int) (Set XName);
  pendingCounts :: PendingBody -> Map XName Int;
  pendingCounts (PendingBody _ _ counts _) = M.map (L.min 2) counts;
  pendingLimitedCounts (PendingBody _ _ counts _) = counts;
  pendingCalls :: PendingBody -> Set XName;
  pendingCalls (PendingBody _ _ _ calls) = calls;
  beginPending :: UseTree -> PendingBody;
  beginPending body = PendingBody body M.empty (limitedUses body) (negativeCalls body);
  -- Expand each delayed occurrence once, including outer replacements inside
  -- earlier copied RHSs. Scope uniqueness makes masking unnecessary: a copied
  -- RHS cannot mention an eliminated inner let's binder. The dependency graph
  -- therefore points strictly outward and is acyclic. No rewrite or Fresh
  -- action runs during this walk; freshly exposed redexes wait for the next pass.
  materializeBody :: Map XName ([] UseTree) -> UseTree -> (,) UseTree (Map XName ([] UseTree));
  materializeBody replacements tree =
    case useChildren tree of {
      UseLeaf -> case useTerm tree of {
        XEVar name -> case M.lookup compareName name replacements of {
          Just ((:) value rest) -> materializeBody (M.insert compareName name rest replacements) value;
          _ -> (,) tree replacements
        };
        _ -> (,) tree replacements
      };
      UseAbs name body -> let { next = materializeBody replacements body }
        in (,) (useAbs name (L.fst next)) (L.snd next);
      UseApp function argument -> let {
        first = materializeBody replacements function;
        next = materializeBody (L.snd first) argument
      } in (,) (useApp (L.fst first) (L.fst next)) (L.snd next);
      UseLet name value body -> let {
        first = materializeBody replacements value;
        next = materializeBody (L.snd first) body
      } in (,) (useLet name (L.fst first) (L.fst next)) (L.snd next);
      UseRec bindings body -> let {
        first = materializePairs replacements bindings;
        next = materializeBody (L.snd first) body
      } in (,) (useRec (L.fst first) (L.fst next)) (L.snd next);
      UseCase subject alternatives -> let {
        first = materializeBody replacements subject;
        next = materializePairs (L.snd first) alternatives
      } in (,) (useCase (L.fst first) (L.fst next)) (L.snd next)
    };
  materializePairs replacements entries = case entries of {
    [] -> (,) [] replacements;
    (:) ((,) key value) rest -> let {
      first = materializeBody replacements value;
      next = materializePairs (L.snd first) rest
    } in (,) ((:) ((,) key (L.fst first)) (L.fst next)) (L.snd next)
  };
  materializePending :: PendingBody -> UseTree;
  materializePending (PendingBody body replacements _ _) =
    if M.null replacements then body else L.fst (materializeBody replacements body);
  queueSubstitution :: XName -> [] UseTree -> Int -> PendingBody -> PendingBody;
  queueSubstitution name copies uses (PendingBody body replacements counts calls) =
    let { replacement = L.head copies } in
      PendingBody body (M.insert compareName name copies replacements)
        (mergePendingUses (M.delete compareName name counts)
          (M.map (\count -> L.min 4 (count * uses)) (limitedUses replacement)))
        (S.union compareName (S.delete compareName name calls) (negativeCalls replacement));
  delayOwnedLet :: XName -> UseTree -> PendingBody -> Fresh PendingBody;
  delayOwnedLet name value pending =
    let {
      uses = M.findWithDefault compareName 0 name (pendingLimitedCounts pending);
      eligible = case useTerm value of {
        XEAbs _ _ ->
          smallValue (useTerm value) &&
          (uses > 0 && uses < 4 &&
           S.member compareName name (pendingCalls pending));
        _ -> False
      }
    } in
    if eligible
    then do {
      copies <- traverseFresh (\_ -> copy M.empty (useTerm value)) (L.range 1 uses);
      freshPure (queueSubstitution name (L.map indexUses copies) uses pending)
    }
    else do {
      let { body = materializePending pending };
      result <- rewriteUsed (useLet name value body);
      freshPure (beginPending result)
    };
  -- Preserve a shared binding without forcing the substitutions queued for
  -- the rest of the declaration spine. Its RHS is outside the binder scope.
  delayCheckedLet name value pending = case pending of {
    PendingBody body replacements counts calls ->
      let { uses = M.findWithDefault compareName 0 name counts;
        -- A constructor applied only to atoms has no binders to freshen.
        -- The ordinary rule substitutes it immediately. Queue its sole use
        -- without rebuilding all later declarations and their use counts.
        constructorValue = case useTerm value of {
          XEApp _ _ -> smallValue (useTerm value); _ -> False
        } } in
      -- The RHS has already been normalized. An unused binding costs no
      -- fresh names and leaves the effective body and its queued copies intact.
      if uses == 0 then freshPure pending
      else if uses == 1 && constructorValue then freshPure (queueSubstitution name [value] 1 pending)
      else if uses < 2 || L.not (branchesToFreeValues value) then delayOwnedLet name value pending
      else let {
        retained = PendingBody (useLet name value body) replacements
          (mergePendingUses (M.delete compareName name counts) (limitedUses value))
          (S.union compareName (S.delete compareName name calls) (negativeCalls value))
      } in if S.member compareName name calls then freshPure retained else do {
        -- All calls with the same outer arguments can still share a single
        -- specialized result. Inspect the effective body before deciding.
        shared <- specializeSharedValue name value (materializePending pending);
        freshPure (case shared of { Just result -> beginPending result; Nothing -> retained })
      }
  };
  -- Delay only while unwinding a contiguous nonrecursive let-body chain.
  -- Every other constructor and every unsupported let observes a fully
  -- materialized body. RHS normalization still precedes body normalization.
  passPendingRaw :: XErased -> Fresh PendingBody;
  passPendingRaw = passPendingFor False;
  passPendingFor checked expression = case expression of {
    XELet name value body -> do {
      normalized <- passOwnedFor checked value;
      pending <- passPendingFor checked body;
      if checked then delayCheckedLet name normalized pending else delayOwnedLet name normalized pending
    };
    _ -> do {
      result <- passOwnedFor checked expression;
      freshPure (beginPending result)
    }
  };
  passOwnedRaw :: XErased -> Fresh UseTree;
  passOwnedRaw = passOwnedFor False;
  passOwnedFor checked expression = case expression of {
    XELet _ _ _ -> do {
      pending <- passPendingFor checked expression;
      freshPure (materializePending pending)
    };
    _ -> do {
      normalized <- case expression of {
        XEAbs name body -> do {
          result <- passOwnedFor checked body;
          freshPure (useAbs name result)
        };
        XEApp function argument -> do {
          a <- passOwnedFor checked function;
          b <- passOwnedFor checked argument;
          freshPure (useApp a b)
        };
        XELetRec bindings body -> do {
          values <- traverseFresh
            (\((,) name value) -> do {
              result <- passOwnedFor checked value;
              freshPure ((,) name result)
            }) bindings;
          result <- passOwnedFor checked body;
          freshPure (useRec values result)
        };
        XECase subject alternatives -> do {
          value <- passOwnedFor checked subject;
          branches <- traverseFresh
            (\(XErasedAlternative pattern body) -> do {
              result <- passOwnedFor checked body;
              freshPure ((,) pattern result)
            }) alternatives;
          freshPure (useCase value branches)
        };
        _ -> freshPure (indexUses expression)
      };
      rewriteUsedFor checked normalized
    }
  };
  passOwned :: XErased -> Fresh XErased;
  passOwned = passOwnedUsing False;
  passOwnedUsing checked expression = do {
    result <- passOwnedFor checked expression;
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
      specializeVisit (L.advanceIdentity seed 16384) (specializationDefinitions expression) expression
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
  iterationsOwned :: Map String (Maybe Int) -> Int -> XErased -> Fresh XErased;
  iterationsOwned = iterationsOwnedFor False;
  iterationsOwnedFor checked arities count expression =
    if (count == 0)
    then freshPure expression
    else do {
           let {
             facts = constructorFacts arities expression
           };
           projected <-
             if M.null facts then freshPure expression else projectConstructors facts expression;
           next <- passOwnedUsing checked projected;
           if X.equalErased expression next
           then freshPure expression
           else iterationsOwnedFor checked arities (count - 1) next
         };
  -- Find references still needed by the entry before copying its declaration
  -- spine. A nonrecursive RHS is in the outer scope. A recursive group binds
  -- its names in every RHS and in the continuation.
  liveDeclarationSpine :: XErased -> (,) XErased (Set XName);
  liveDeclarationSpine expression = case expression of {
    XELet name rhs rest -> case liveDeclarationSpine rest of {
      (,) body live -> if S.member compareName name live
        then (,) (XELet name rhs body) (S.union compareName (free rhs) (S.delete compareName name live))
        else (,) body live
    };
    XELetRec bindings rest -> case liveDeclarationSpine rest of {
      (,) body live -> let {
        used = L.foldl (\names entry -> S.union compareName names (free (L.snd entry))) live bindings;
        bound = S.fromList compareName (L.map L.fst bindings)
      } in (,) (XELetRec bindings body) (S.difference compareName used bound)
    };
    _ -> (,) expression (free expression)
  };
  optimizeOwnedWork :: XErased -> Fresh XErased;
  optimizeOwnedWork = optimizeOwnedUsing identities;
  optimizeOwnedUsing = optimizeLetSharing False;
  optimizeLetSharing checked cleanInput expression =
    do {
      unique <- copy M.empty (L.fst (liveDeclarationSpine expression));
      clean <- cleanInput unique;
      recursive <- fixedPoints clean;
      let {
        arities = constructorArities recursive
      };
      lifted <- liftConstructorFields arities recursive;
      simple <- iterationsOwnedFor checked arities 16 lifted;
      specialized <- specializeHigherOrder simple;
      iterationsOwnedFor checked arities 16 specialized
    };
  -- Recognize finite nonrecursive iterators by binding identity. A summary is
  -- the number of applications of the first parameter to the second; it does
  -- not depend on source names, types' printed spelling or a benchmark size.
  -- Counts are bounded before addition. Recursive groups and unknown callbacks
  -- keep the ordinary optimizer path.
  addIterationCounts a b =
    if a <= 2147483647 - b then Just (a + b) else Nothing;
  iterationBody summaries step argument expression = case expression of {
    XEVar name -> if eqName name argument then Just 0 else Nothing;
    XEApp (XEVar name) value -> if eqName name step then case iterationBody summaries step argument value of {
      Just count -> addIterationCounts 1 count; Nothing -> Nothing
    } else Nothing;
    XEApp (XEApp (XEVar name) (XEVar callback)) value ->
      if eqName callback step then case M.lookup compareName name summaries of {
        Just count -> case iterationBody summaries step argument value of {
          Just rest -> addIterationCounts count rest; Nothing -> Nothing
        };
        Nothing -> Nothing
      } else Nothing;
    _ -> Nothing
  };
  iterationSummary summaries expression = case expression of {
    XEAbs step (XEAbs argument body) ->
      if eqName step argument then Nothing else
        iterationBody (M.delete compareName step (M.delete compareName argument summaries)) step argument body;
    XEVar name -> M.lookup compareName name summaries;
    _ -> Nothing
  };
  data IterationStep = IntegerTranslation Int | BooleanNegation;
  iterationStep expression = case expression of {
    XEAbs parameter body -> case applications body of {
      (,) (XEPrimitive PAddInt) [XEVar name,XEInt amount] ->
        if eqName name parameter then Just (IntegerTranslation amount) else Nothing;
      (,) (XEPrimitive PAddInt) [XEInt amount,XEVar name] ->
        if eqName name parameter then Just (IntegerTranslation amount) else Nothing;
      (,) (XEPrimitive PSubInt) [XEVar name,XEInt amount] ->
        if eqName name parameter then Just (IntegerTranslation (0 - amount)) else Nothing;
      (,) (XEPrimitive PIfThenElse) [XEVar name,XEBool False,XEBool True] ->
        if eqName name parameter then Just BooleanNegation else Nothing;
      _ -> Nothing
    };
    _ -> Nothing
  };
  reduceIteration summaries expression = case applications expression of {
    (,) (XEVar name) [callback,argument] -> case M.lookup compareName name summaries of {
      Nothing -> expression;
      Just count -> if count == 0 then argument else case iterationStep callback of {
        Just (IntegerTranslation amount) ->
          -- Language Int operations wrap at 64 bits; translation composition
          -- therefore uses the same multiplication/addition ring. No Double
          -- reassociation, quotient, effect or general callback is admitted.
          XEApp (XEApp (XEPrimitive PAddInt) argument) (XEInt (count * amount));
        Just BooleanNegation -> if count % 2 == 0 then argument
          else XEApp (XEApp (XEApp (XEPrimitive PIfThenElse) argument) (XEBool False)) (XEBool True);
        Nothing -> expression
      }
    };
    _ -> expression
  };
  simplifyIterations summaries expression = case expression of {
    XEAbs name body -> XEAbs name (simplifyIterations (M.delete compareName name summaries) body);
    XEApp function argument -> reduceIteration summaries
      (XEApp (simplifyIterations summaries function) (simplifyIterations summaries argument));
    XELet name value body -> let {
      normalized = simplifyIterations summaries value;
      following = case iterationSummary summaries normalized of {
        Just count -> M.insert compareName name count summaries;
        Nothing -> M.delete compareName name summaries
      }
    } in XELet name normalized (simplifyIterations following body);
    XELetRec bindings body -> let {
      scope = L.foldl (\current entry -> M.delete compareName (L.fst entry) current) summaries bindings
    } in XELetRec (L.map (\((,) name value) -> (,) name (simplifyIterations scope value)) bindings)
      (simplifyIterations scope body);
    XECase subject alternatives -> XECase (simplifyIterations summaries subject)
      (L.map (\(XErasedAlternative pattern body) -> XErasedAlternative pattern
        (simplifyIterations (L.foldl (\current name -> M.delete compareName name current)
          summaries (X.patternNames pattern)) body)) alternatives);
    _ -> expression
  };
  -- Normalize one complete first-order integer expression before the checked
  -- optimizer copies its declaration spine. A summary retains its one demanded
  -- binder even when its coefficient wraps to zero. A unary field can pass
  -- through only a matching constructor and selector proven in this scope.
  affineField facts expression = let {
    child = affineField facts;
    offset n arg = fmap (\((,,) name factor c) -> (,,) name factor (c + n)) (child arg);
    times n arg = fmap (\((,,) name factor c) -> (,,) name (factor * n) (c * n)) (child arg)
  } in case expression of {
    XEVar name -> Just ((,,) name 1 0);
    XEApp (XEVar select) (XEApp (XEVar build) arg) -> case M.lookup compareName select facts of {
      Just (SelectsField wanted) -> case M.lookup compareName build facts of {
        Just (BuildsField actual) -> if eqString wanted actual then child arg else Nothing;
        _ -> Nothing
      };
      _ -> Nothing
    };
    XEApp (XEApp (XEPrimitive PAddInt) left) right -> case (,) left right of {
      (,) (XEInt n) arg -> offset n arg;
      (,) arg (XEInt n) -> offset n arg;
      _ -> case child left of {
        Just ((,,) name a c) -> case child right of {
          Just ((,,) other b d) -> if eqName name other then Just ((,,) name (a + b) (c + d)) else Nothing;
          Nothing -> Nothing
        };
        Nothing -> Nothing
      }
    };
    XEApp (XEApp (XEPrimitive PMulInt) left) right -> case (,) left right of {
      (,) (XEInt n) arg -> times n arg;
      (,) arg (XEInt n) -> times n arg;
      _ -> Nothing
    };
    _ -> Nothing
  };
  -- Shared checked declarations can contain erased identity coercions and
  -- local aliases. Resolve only aliases of the sole argument. Each alias RHS
  -- sees its outer scope, and a matching field return sees the pattern scope.
  skipIdentity expression = case expression of {
    XEApp (XEAbs x (XEVar y)) a -> if eqName x y then skipIdentity a else expression;
    _ -> expression
  };
  argumentAlias names term = case skipIdentity term of {
    XEVar n -> S.member compareName n names; _ -> False
  };
  scopedUnaryUse expression = case skipIdentity expression of {
    XEAbs parameter value -> let {
      body names term = case skipIdentity term of {
        XELet n rhs rest -> if argumentAlias names rhs then body (S.insert compareName n names) rest else Nothing;
        XEApp (XEConstructor constructor) arg ->
          if argumentAlias names arg then Just (BuildsField constructor) else Nothing;
        XECase subject [XErasedAlternative (XConstructorPattern constructor [Just field]) result] ->
          if argumentAlias names subject then case skipIdentity result of {
            XEVar n -> if eqName n field then Just (SelectsField constructor) else Nothing;
            _ -> Nothing
          } else Nothing;
        _ -> Nothing
      }
    } in body (S.singleton parameter) value;
    _ -> Nothing
  };
  data ScopedInput a = OtherInput | LambdaInput XName a |
    LetInput XName a a | RecursiveInput XName a a | ApplicationInput a a;
  erasedScope term = case term of {
    XEAbs name body -> LambdaInput name body;
    XELet name value body -> LetInput name value body;
    XELetRec [(,) name rhs] body -> RecursiveInput name rhs body;
    XEApp fn arg -> ApplicationInput fn arg;
    _ -> OtherInput
  };
  typedScope term = case skipTypeWrappers term of {
    XAbs name _ body -> LambdaInput name body;
    XLet name value body -> LetInput name value body;
    XLetRec [(,,) name _ rhs] body -> RecursiveInput name rhs body;
    XApp fn arg -> ApplicationInput fn arg;
    _ -> OtherInput
  };
  foldScopedFields = foldScopedUsing erasedScope L.id foldKnownConstructor;
  eraseScopedFields = foldScopedUsing typedScope X.erase foldTypedConstructor;
  -- Follow declaration scopes on the input representation. A successful
  -- constructor fold only erases fields that survive in the resulting term.
  foldScopedUsing inspect erase foldArgument = let {
    visit facts expression = let { original = erase expression } in case inspect expression of {
      LetInput name value body -> let {
        following = case scopedUnaryUse (erase value) of {
          Just role -> M.insert compareName name role facts;
          Nothing -> M.delete compareName name facts
        }
      } in XELet name (visit facts value) (visit following body);
      RecursiveInput name value body -> let { rhs = erase value } in case constructorFold name rhs of {
        Just rules -> XELetRec [(,) name rhs]
          (visit (M.insert compareName name (FoldsConstructors rules) facts) body);
        Nothing -> original
      };
      LambdaInput name body -> XEAbs name (visit (M.delete compareName name facts) body);
      ApplicationInput fn arg -> let {
        affine = case affineField facts original of {
          Just ((,,) name factor offset) -> affineIntTerm name factor offset;
          Nothing -> original
        }
      } in if M.null facts then original else case erase fn of {
        XEVar name -> case M.lookup compareName name facts of {
          Just (FoldsConstructors rules) -> L.fromMaybe original (foldArgument rules arg);
          _ -> affine
        };
        _ -> affine
      };
      OtherInput -> original
    }
  } in visit;
  -- This extra algebraic pass is for finite checked programs. Its rewrites
  -- introduce no binders and preserve evaluation of the single input value.
  optimizeChecked expression = optimizeAfterFields (foldScopedFields M.empty expression);
  optimizeCheckedTerm term = optimizeAfterFields (eraseScopedFields M.empty term);
  optimizeAfterFields expression = optimizeOwnedWith (optimizeLetSharing True (checkedIdentities M.empty))
    (simplifyIterations M.empty (simplifyTranslations M.empty expression));
  -- A translation evaluates its one Int input once and adds a constant in
  -- the language's wrapping Int64 ring. Retain every unknown/effectful body.
  -- Summaries follow resolved binder identities and never cross shadowing.
  translationBody summaries parameter expression = case expression of {
    XEVar name -> if eqName name parameter then Just 0 else Nothing;
    XEApp (XEVar name) value -> case M.lookup compareName name summaries of {
      Just amount -> fmap (\rest -> amount + rest) (translationBody summaries parameter value);
      Nothing -> Nothing
    };
    XEApp (XEApp (XEPrimitive PAddInt) value) (XEInt amount) ->
      fmap (\rest -> rest + amount) (translationBody summaries parameter value);
    XEApp (XEApp (XEPrimitive PAddInt) (XEInt amount)) value ->
      fmap (\rest -> amount + rest) (translationBody summaries parameter value);
    XEApp (XEApp (XEPrimitive PSubInt) value) (XEInt amount) ->
      fmap (\rest -> rest - amount) (translationBody summaries parameter value);
    _ -> Nothing
  };
  translationSummary summaries expression = case expression of {
    XEAbs parameter body -> translationBody (M.delete compareName parameter summaries) parameter body;
    XEVar name -> M.lookup compareName name summaries;
    _ -> Nothing
  };
  translated amount argument = if amount == 0 then argument
    else XEApp (XEApp (XEPrimitive PAddInt) argument) (XEInt amount);
  simplifyTranslations summaries expression = case expression of {
    XEAbs name body -> let { scope = M.delete compareName name summaries } in
      XEAbs name (case translationBody scope name body of {
        Just amount -> translated amount (XEVar name);
        Nothing -> simplifyTranslations scope body
      });
    XEApp function argument -> let {
      value = simplifyTranslations summaries argument;
      normalized = simplifyTranslations summaries function
    } in case normalized of {
      XEVar name -> case M.lookup compareName name summaries of {
        Just amount -> translated amount value; Nothing -> XEApp normalized value
      };
      _ -> XEApp normalized value
    };
    XELet name value body -> let {
      normalized = simplifyTranslations summaries value;
      following = case translationSummary summaries normalized of {
        Just amount -> M.insert compareName name amount summaries;
        Nothing -> M.delete compareName name summaries
      }
    } in XELet name normalized (simplifyTranslations following body);
    XELetRec bindings body -> let {
      scope = L.foldl (\current entry -> M.delete compareName (L.fst entry) current) summaries bindings
    } in XELetRec (L.map (\((,) name value) -> (,) name (simplifyTranslations scope value)) bindings)
      (simplifyTranslations scope body);
    XECase subject alternatives -> XECase (simplifyTranslations summaries subject)
      (L.map (\(XErasedAlternative pattern body) -> XErasedAlternative pattern
        (simplifyTranslations (L.foldl (\current name -> M.delete compareName name current)
          summaries (X.patternNames pattern)) body)) alternatives);
    _ -> expression
  };
  optimizeOwned :: XErased -> XErased;
  optimizeOwned = optimizeOwnedWith optimizeOwnedWork;
  optimizeOwnedWith work expression =
    case runFresh (work expression) (L.advanceIdentity 1 (maxIdentity expression)) of {
      (,) normalized seed ->
        case runFresh (copy M.empty normalized) 0 of {
          (,) result next -> result
        }
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
    case runFresh (optimizeWork expression) (L.advanceIdentity 1 (maxIdentity expression)) of {
      (,) normalized seed ->
        case runFresh (copy M.empty normalized) 0 of {
          (,) result next -> result
        }
    }

}
