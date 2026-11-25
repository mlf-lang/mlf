-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.Optimize where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.IntSet as IS;
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
  free expression = case expression of {
    XEApp _ _ -> S.fromDistinctAscList (IM.elems (applicationFree IS.empty IM.empty expression));
    _ -> freeWith free expression
  };
  -- Accumulate one representative per free identity across an application.
  -- Visit the left operand first, matching the left-biased union of free sets.
  applicationFree :: IntSet -> IntMap XName -> XErased -> IntMap XName;
  applicationFree bound found expression = case expression of {
    XEVar n -> let { key = nameId n } in
      if IS.member key bound || IM.member key found then found else IM.insert key n found;
    XEApp f a -> applicationFree bound (applicationFree bound found f) a;
    XEAbs n body -> applicationFree (IS.insert (nameId n) bound) found body;
    XELet n rhs body -> applicationFree (IS.insert (nameId n) bound)
      (applicationFree bound found rhs) body;
    XELetRec ds body -> let {
      inside = L.foldlStrict (\scope binding -> IS.insert (nameId (L.fst binding)) scope) bound ds
    } in L.foldlStrict (\names binding -> applicationFree inside names (L.snd binding))
      (applicationFree inside found body) ds;
    XECase subject branches -> L.foldlStrict (\names (XErasedAlternative pattern body) ->
      let { inside = L.foldlStrict (\scope n -> IS.insert (nameId n) scope) bound (X.patternNames pattern) }
      in applicationFree inside names body) (applicationFree bound found subject) branches;
    _ -> found
  };
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
    FoldsConstructors (Map String ((,) Int FoldBranch)) | ComposesFunctions | TranslatesBy Int |
    ProjectsArgument Int Int;
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
  liftConstructorValue = liftConstructorValueFor False;
  liftConstructorValueFor :: Bool -> Map String (Maybe Int) ->
                                XErased -> Fresh ((,) ([] ((,) XName XErased)) XErased);
  liftConstructorValueFor checked arities value =
    case constructorValue arities value of {
      Just ((,) c args) ->
        if checked && closedNestedFields arities args then freshPure ((,) [] value) else do {
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
  liftConstructorFields = liftConstructorFieldsFor False;
  -- A closed, nested constructor tree already has one lazy binding. Lifting
  -- its children makes the parent a constructor with atomic fields, which
  -- the ordinary inliner can then duplicate at each use.
  closedNestedFields :: Map String (Maybe Int) -> [] XErased -> Bool;
  closedNestedFields arities fields = let {
    closed term = case term of {
      XEInt _ -> True; XEDouble _ -> True; XEBool _ -> True; XEString _ -> True;
      _ -> case constructorValue arities term of {
        Just ((,) _ children) -> L.all closed children;
        Nothing -> False
      }
    };
    applied field = case field of { XEApp _ _ -> True; _ -> False }
  } in L.any applied fields && L.all closed fields;
  liftConstructorFieldsFor :: Bool -> Map String (Maybe Int) -> XErased -> Fresh XErased;
  liftConstructorFieldsFor checked arities expression =
    do {
      normalized <- children (liftConstructorFieldsFor checked arities) expression;
      case normalized of {
        XELet name rhs body ->
          do {
            lifted <- liftConstructorValueFor checked arities rhs;
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
  data UseTree = UseTree XErased (Map XName Int) UseChildren
    | IndexedUses XErased (IntMap UseCount) UseChildren;
  data UseCount = UseCount XName Int;
  data UseChildren =
    UseLeaf |
    UseAbs XName UseTree |
    UseApp UseTree UseTree |
    UseLet XName UseTree UseTree |
    UseRec ([] ((,) XName UseTree)) UseTree |
    UseCase UseTree ([] ((,) XPattern UseTree));
  useTerm :: UseTree -> XErased;
  useTerm (UseTree term _ _) = term;
  useTerm (IndexedUses term _ _) = term;
  useCounts :: UseTree -> Map XName Int;
  useCounts (UseTree _ counts _) = counts;
  useCounts (IndexedUses _ counts _) = M.fromDistinctAscList
    (L.map (\((,) _ (UseCount name count)) -> (,) name count) (IM.toList counts));
  countIndex :: UseTree -> IntMap UseCount;
  countIndex (IndexedUses _ counts _) = counts;
  countIndex (UseTree _ counts _) = IM.fromList
    (L.map (\((,) name count) -> (,) (nameId name) (UseCount name count)) (M.toList counts));
  useCount :: XName -> UseTree -> Int;
  useCount name tree = case tree of {
    UseTree _ counts _ -> M.findWithDefault compareName 0 name counts;
    IndexedUses _ counts _ -> case IM.lookup (nameId name) counts of {
      Nothing -> 0;
      Just (UseCount _ count) -> count
    }
  };
  usesName :: XName -> UseTree -> Bool;
  usesName name tree = case tree of {
    UseTree _ counts _ -> M.member compareName name counts;
    IndexedUses _ counts _ -> IM.member (nameId name) counts
  };
  useChildren :: UseTree -> UseChildren;
  useChildren (UseTree _ _ children) = children;
  useChildren (IndexedUses _ _ children) = children;
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
  -- Identity comparison on these maps needs only the numeric binder key.
  -- Retain the representative name for callers that inspect useCounts.
  mergeCountIndex :: IntMap UseCount -> IntMap UseCount -> IntMap UseCount;
  mergeCountIndex left right = let {
    merge (UseCount name a) (UseCount _ b) = UseCount name (addUses a b)
  } in if IM.size left <= IM.size right then IM.unionWith merge left right
    else IM.unionWith merge right left;
  dropCountIndex :: [] XName -> IntMap UseCount -> IntMap UseCount;
  dropCountIndex names counts = L.foldl (\current name -> IM.delete (nameId name) current) counts names;
  useAbs :: XName -> UseTree -> UseTree;
  useAbs name body =
    IndexedUses (XEAbs name (useTerm body)) (IM.delete (nameId name) (countIndex body))
      (UseAbs name body);
  useApp :: UseTree -> UseTree -> UseTree;
  useApp function argument =
    IndexedUses (XEApp (useTerm function) (useTerm argument))
      (mergeCountIndex (countIndex function) (countIndex argument))
      (UseApp function argument);
  useLet :: XName -> UseTree -> UseTree -> UseTree;
  useLet name value body =
    IndexedUses (XELet name (useTerm value) (useTerm body))
      (mergeCountIndex (countIndex value) (IM.delete (nameId name) (countIndex body)))
      (UseLet name value body);
  useRec :: [] ((,) XName UseTree) -> UseTree -> UseTree;
  useRec bindings body =
    let { counts = bindingCountIndex bindings body } in
    IndexedUses
      (XELetRec (L.map (\((,) name value) -> (,) name (useTerm value)) bindings) (useTerm body))
      (dropCountIndex (L.map L.fst bindings) counts)
      (UseRec bindings body);
  bindingUses bindings body = L.foldl
    (\current binding -> mergeUses current (useCounts (L.snd binding))) (useCounts body) bindings;
  bindingCountIndex bindings body = L.foldl
    (\current binding -> mergeCountIndex current (countIndex (L.snd binding))) (countIndex body) bindings;
  -- Inlining a shared lambda with two free occurrences can multiply both
  -- incoming and outgoing dependencies at every layer. A linear wrapper
  -- forwards at most one free occurrence per use, so it can still inline.
  branchesToFreeValues value = case useChildren value of {
    UseAbs _ _ -> case IM.toList (countIndex value) of {
      [] -> False;
      [(,) _ (UseCount _ count)] -> count > 1;
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
             mergeCountIndex current (dropCountIndex (X.patternNames pattern) (countIndex body)))
          (countIndex subject)
          alternatives
    } in
    IndexedUses
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
      XEVar name -> IndexedUses term (IM.singleton (nameId name) (UseCount name 1)) UseLeaf;
      _ -> IndexedUses term IM.empty UseLeaf
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
    if L.not (usesName name tree)
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
  selectKnownConstructor :: UseTree -> [] ((,) XPattern UseTree) -> Maybe UseTree;
  selectKnownConstructor subject branches = case useApplications [] subject of {
    (,) head arguments -> case useTerm head of {
      XEConstructor constructor -> selectUseConstructor constructor arguments branches;
      _ -> Nothing
    }
  };
  -- The condition is still demanded before either selected branch. At least
  -- one result is a closed literal, so no local binder is duplicated.
  selectConditionalConstructors :: UseTree -> [] ((,) XPattern UseTree) -> Maybe UseTree;
  selectConditionalConstructors subject branches@((:) ((,) (XConstructorPattern _ _) _) _) = let {
    closedLiteral value = case useTerm value of {
      XEInt _ -> True; XEBool _ -> True; XEString _ -> True; XEDouble _ -> True; _ -> False
    }
  } in case useChildren subject of {
    UseApp (UseTree _ _ (UseApp (UseTree _ _ (UseApp operator condition)) yes)) no ->
      case useTerm operator of {
        XEPrimitive PIfThenElse -> do {
          left <- selectKnownConstructor yes branches;
          right <- selectKnownConstructor no branches;
          if closedLiteral left || closedLiteral right
          then Just (useApp (useApp (useApp operator condition) left) right)
          else Nothing
        };
        _ -> Nothing
      };
    _ -> Nothing
  };
  selectConditionalConstructors _ _ = Nothing;
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
    if useCount name tree == 0
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
    if useCount name tree == 0
    then True
    else case useChildren tree of {
      UseLeaf -> case useTerm tree of {
        XEVar actual -> selected && eqName name actual;
        _ -> False
      };
      UseAbs _ _ -> False;
      UseRec _ _ -> False;
      UseLet _ value body ->
        (useCount name value == 0) &&
        singleUseBranchPath name selected body;
      UseCase subject branches ->
        (useCount name subject == 0) &&
        L.all (\entry -> singleUseBranchPath name True (L.snd entry)) branches;
      UseApp _ _ -> case useApplications [] tree of {
        (,) function arguments -> case useTerm function of {
          XEPrimitive PIfThenElse -> case arguments of {
            (:) condition ((:) yes ((:) no [])) ->
              (useCount name condition == 0) &&
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
  outerCallNames target outer = outerCallNamesUsing target (\name -> M.member compareName name outer);
  outerCallNamesUsing target outer arguments = case arguments of {
    [] -> Just [];
    (:) argument rest -> case useTerm argument of {
      XEVar name ->
        if L.not (eqName target name) && outer name
        then case outerCallNamesUsing target outer rest of {
          Nothing -> Nothing;
          Just names -> Just ((:) name names)
        }
        else Nothing;
      _ -> Nothing
    }
  };
  commonCalls :: XName -> Int -> Map XName Int -> UseTree -> CommonCalls;
  commonCalls target arity outer = commonCallsUsing target arity (\name -> M.member compareName name outer);
  commonCallsUsing target arity outer tree =
    if useCount target tree == 0
    then NoCommonCalls
    else case useApplications [] tree of {
      (,) function arguments -> case useTerm function of {
        XEVar name ->
          if eqName target name
          then if L.length arguments == arity
               then case outerCallNamesUsing target outer arguments of {
                 Just names -> CommonCalls names;
                 Nothing -> DifferentCalls
               }
               else DifferentCalls
          else commonChildCallsUsing target arity outer tree;
        _ -> commonChildCallsUsing target arity outer tree
      }
    };
  commonChildCalls :: XName -> Int -> Map XName Int -> UseTree -> CommonCalls;
  commonChildCalls target arity outer = commonChildCallsUsing target arity (\name -> M.member compareName name outer);
  commonChildCallsUsing target arity outer tree =
    let { collect = commonCallsUsing target arity outer;
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
    if useCount target tree == 0
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
      if useCount name body < 1
      then freshPure Nothing
      else case commonCallsUsing name (L.length parameters) (\wanted -> usesName wanted body) body of {
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
          uses = useCount name body
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
        case selectKnownConstructor subject branches of {
          Just selected -> freshPure selected;
          Nothing -> if checked then case selectConditionalConstructors subject branches of {
            Just selected -> freshPure selected;
            Nothing -> freshPure tree
          } else freshPure tree
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
  -- A queried negative call is always a free use. Use the existing subtree
  -- counts to visit only paths where that particular name can survive.
  negativeMember :: Map XName Int -> XName -> UseTree -> Bool;
  negativeMember outer = negativeMemberUsing (\name -> M.member compareName name outer);
  negativeMemberUsing outer target tree =
    usesName target tree && (case useChildren tree of {
      UseLeaf -> False;
      UseAbs _ body -> negativeMemberUsing outer target body;
      UseApp function argument -> let {
        headWitness = case useTerm argument of {
          XEVar name -> eqName name target || (case useTerm function of {
            XEVar called -> eqName called target && L.not (outer name);
            _ -> False
          });
          _ -> case useTerm function of { XEVar called -> eqName called target; _ -> False }
        }
      } in headWitness || negativeMemberUsing outer target function || negativeMemberUsing outer target argument;
      UseLet name value body -> negativeMemberUsing outer target value ||
        (L.not (eqName name target) && negativeMemberUsing outer target body);
      UseRec bindings body -> negativeMemberUsing outer target body ||
        L.any (\entry -> negativeMemberUsing outer target (L.snd entry)) bindings;
      UseCase subject alternatives -> negativeMemberUsing outer target subject ||
        L.any (\entry -> L.not (L.any (eqName target) (X.patternNames (L.fst entry))) &&
          negativeMemberUsing outer target (L.snd entry)) alternatives
    });
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
  materializeBody = materializeBodyWith False;
  -- Each pending binder is globally fresh on the checked route. Its free
  -- occurrences are indexed on the normalized use tree. A disjoint subtree
  -- consumes no replacement and can be returned with all cached uses intact.
  shareMaterialized replacements tree = let { counts = countIndex tree;
    overlapsReplacements = M.foldrWithKey (\name _ found -> IM.member (nameId name) counts || found) False replacements;
    overlapsCounts = IM.foldrWithKey (\_ (UseCount name _) found -> M.member compareName name replacements || found) False counts
  } in M.null replacements || IM.null counts || L.not
    (if M.size replacements <= IM.size counts then overlapsReplacements else overlapsCounts);
  materializeBodyWith checked replacements tree =
    if checked && shareMaterialized replacements tree then (,) tree replacements else
    case useChildren tree of {
      UseLeaf -> case useTerm tree of {
        XEVar name -> case M.lookup compareName name replacements of {
          Just ((:) value rest) -> materializeBodyWith checked
            (if checked && L.null rest then M.delete compareName name replacements
             else M.insert compareName name rest replacements) value;
          _ -> (,) tree replacements
        };
        _ -> (,) tree replacements
      };
      UseAbs name body -> let { next = materializeBodyWith checked replacements body }
        in (,) (useAbs name (L.fst next)) (L.snd next);
      UseApp function argument -> let {
        first = materializeBodyWith checked replacements function;
        next = materializeBodyWith checked (L.snd first) argument
      } in (,) (useApp (L.fst first) (L.fst next)) (L.snd next);
      UseLet name value body -> let {
        first = materializeBodyWith checked replacements value;
        next = materializeBodyWith checked (L.snd first) body
      } in (,) (useLet name (L.fst first) (L.fst next)) (L.snd next);
      UseRec bindings body -> let {
        first = materializePairsWith checked replacements bindings;
        next = materializeBodyWith checked (L.snd first) body
      } in (,) (useRec (L.fst first) (L.fst next)) (L.snd next);
      UseCase subject alternatives -> let {
        first = materializeBodyWith checked replacements subject;
        next = materializePairsWith checked (L.snd first) alternatives
      } in (,) (useCase (L.fst first) (L.fst next)) (L.snd next)
    };
  materializePairs = materializePairsWith False;
  materializePairsWith :: forall a. Bool -> Map XName ([] UseTree) -> [] ((,) a UseTree) ->
    (,) ([] ((,) a UseTree)) (Map XName ([] UseTree));
  materializePairsWith checked replacements entries = case entries of {
    [] -> (,) [] replacements;
    (:) ((,) key value) rest -> let {
      first = materializeBodyWith checked replacements value;
      next = materializePairsWith checked (L.snd first) rest
    } in (,) ((:) ((,) key (L.fst first)) (L.fst next)) (L.snd next)
  };
  materializePending :: PendingBody -> UseTree;
  materializePending = materializePendingWith False;
  materializePendingWith checked (PendingBody body replacements _ _) =
    if M.null replacements then body else L.fst (materializeBodyWith checked replacements body);
  queueSubstitution :: XName -> [] UseTree -> Int -> PendingBody -> PendingBody;
  queueSubstitution name copies uses (PendingBody body replacements counts calls) =
    let { replacement = L.head copies } in
      PendingBody body (M.insert compareName name copies replacements)
        (mergePendingUses (M.delete compareName name counts)
          (M.map (\count -> L.min 4 (count * uses)) (limitedUses replacement)))
        (S.union compareName (S.delete compareName name calls) (negativeCalls replacement));
  delayOwnedLet :: XName -> UseTree -> PendingBody -> Fresh PendingBody;
  delayOwnedLet name value pending = delayLetWith False name value pending
    (M.findWithDefault compareName 0 name (pendingLimitedCounts pending)) (\wanted -> S.member compareName wanted (pendingCalls pending))
    (\copies uses -> queueSubstitution name copies uses pending) beginPending;
  delayLetWith :: forall a. Bool -> XName -> UseTree -> PendingBody -> Int -> (XName -> Bool) ->
    ([] UseTree -> Int -> a) -> (UseTree -> a) -> Fresh a;
  delayLetWith checked name value pending uses witnessed queue begin =
    let {
      eligible = case useTerm value of {
        XEAbs _ _ ->
          -- The ordinary inliner copies a single-use lambda even when its
          -- body is large. A witnessed non-specializable call lets the
          -- checked pass defer that same copy with its other replacements.
          (smallValue (useTerm value) || (checked && uses == 1)) &&
          (uses > 0 && uses < 4 &&
           witnessed name);
        _ -> False
      }
    } in
    if eligible
    then do {
      copies <- traverseFresh (\_ -> copy M.empty (useTerm value)) (L.range 1 uses);
      freshPure (queue (L.map indexUses copies) uses)
    }
    else do {
      let { body = materializePendingWith checked pending };
      result <- rewriteUsed (useLet name value body);
      freshPure (begin result)
    };
  -- The checked pass owns every binder after its initial fresh copy. An
  -- already-saturated action used only as another bind's continuation body
  -- can move there with its original binders and exact execution order.
  sequenceSingleAction :: XName -> UseTree -> UseTree -> Maybe UseTree;
  sequenceSingleAction name value body = case useTerm value of {
    XEApp (XEApp (XEPrimitive PIOBind) _) _ -> case useChildren body of {
      UseApp function continuation -> case (,) (useTerm function) (useChildren continuation) of {
        (,) (XEApp (XEPrimitive PIOBind) _) (UseAbs arg result) -> case useTerm result of {
          XEVar wanted -> if eqName name wanted && L.not (eqName name arg) &&
            L.not (usesName arg value)
            then Just (useApp function (useAbs arg value)) else Nothing;
          _ -> Nothing
        };
        _ -> Nothing
      };
      _ -> Nothing
    };
    _ -> Nothing
  };
  -- The caller has established exactly one use in the fully indexed body.
  -- An immediate case demands its scrutinee there. Reduce the sole use
  -- only when the constructor and selected branch are already known.
  moveSingleUse :: XName -> UseTree -> UseTree -> Maybe UseTree;
  moveSingleUse name value body = case useChildren body of {
    UseCase subject branches -> case useTerm subject of {
      XEVar wanted -> if eqName name wanted then case selectKnownConstructor value branches of {
        Just selected -> Just selected;
        Nothing -> selectConditionalConstructors value branches
      } else Nothing;
      _ -> Nothing
    };
    _ -> sequenceSingleAction name value body
  };
  -- Preserve a shared binding without forcing the substitutions queued for
  -- the rest of the declaration spine. Its RHS is outside the binder scope.
  data CheckedPending = CheckedPending PendingBody (XName -> Bool) (XName -> Int)
    | ClosedCheckedPending PendingBody IntSet (XName -> Bool) (XName -> Int);
  checkedBody (CheckedPending body _ _) = body;
  checkedBody (ClosedCheckedPending body _ _ _) = body;
  checkedUseCount tree name = boundedUseCount 4 name tree;
  -- Existing counts distinguish zero, one and two-or-more free occurrences
  -- at every subtree. Only an unmet budget above two needs any traversal.
  boundedUseCount limit target tree = let {
    known = useCount target tree;
    appendCount count child = if count == limit then limit else
      count + boundedUseCount (limit - count) target child
  } in if known < 2 || limit <= 2 then L.min limit known else
    case useChildren tree of {
      UseLeaf -> known;
      UseAbs _ body -> boundedUseCount limit target body;
      UseApp function argument -> appendCount (boundedUseCount limit target function) argument;
      UseLet bound value body -> let { first = boundedUseCount limit target value } in
        if eqName target bound then first else appendCount first body;
      UseRec bindings body -> L.foldl
        (\count entry -> appendCount count (L.snd entry)) (boundedUseCount limit target body) bindings;
      UseCase subject alternatives -> L.foldl
        (\count entry -> if L.any (eqName target) (X.patternNames (L.fst entry))
          then count else appendCount count (L.snd entry)) (boundedUseCount limit target subject) alternatives
    };
  afterUseBinding name value uses prior target = L.min 4
    ((if eqName name target then 0 else prior target) + uses * checkedUseCount value target);
  beginChecked body = CheckedPending (beginPending body) (\wanted -> negativeMemberUsing (\name -> usesName name body) wanted body)
    (checkedUseCount body);
  afterCallBinding name value previous wanted =
    (L.not (eqName wanted name) && previous wanted) || negativeMemberUsing (\name -> usesName name value) wanted value;
  -- Keep the original exported full witness set. The checked pass asks about
  -- one binder at a time and can issue that exact query without building it.
  delayCheckedLet name value pending = do {
    result <- delayCheckedPending name value
      (CheckedPending pending (\wanted -> S.member compareName wanted (pendingCalls pending))
        (\wanted -> M.findWithDefault compareName 0 wanted (pendingLimitedCounts pending)));
    freshPure (checkedBody result)
  };
  delayCheckedPending name value state = case state of {
    CheckedPending pending witnessed countOf ->
      delayCheckedWith name value state pending IS.empty witnessed countOf;
    ClosedCheckedPending pending removed witnessed countOf ->
      delayCheckedWith name value state pending removed witnessed countOf
  };
  delayCheckedWith name value state pending removed previousWitness previousCount = case pending of {
    PendingBody body replacements counts calls ->
      -- With no queued substitutions, the indexed body's existing 0/1/many
      -- count suffices for all of the comparisons below.
      let { witnessed target = IS.notMember (nameId target) removed && previousWitness target;
        countOf target = if IS.member (nameId target) removed then 0 else previousCount target;
        uses = if M.null replacements then useCount name body else countOf name;
        -- A constructor applied only to atoms has no binders to freshen.
        -- The ordinary rule substitutes it immediately. Queue its sole use
        -- without rebuilding all later declarations and their use counts.
        -- A closed replacement removes its own binder and contributes no free
        -- names. Share the previous lookup functions across consecutive closed
        -- replacements, recording the removed names in a single bitmap index.
        queue copies count = let { replacement = L.head copies;
          next = queueSubstitution name copies count pending
        } in if IM.null (countIndex replacement)
          then ClosedCheckedPending next (IS.insert (nameId name) removed) previousWitness previousCount
          else CheckedPending next (afterCallBinding name replacement witnessed)
            (afterUseBinding name replacement count countOf);
        ordinary = delayLetWith True name value pending (countOf name) witnessed queue beginChecked;
        constructorValue = case useTerm value of {
          XEApp _ _ -> smallValue (useTerm value); _ -> False
        } } in
      -- The RHS has already been normalized. An unused binding costs no
      -- fresh names and leaves the effective body and its queued copies intact.
      if uses == 0 then freshPure state
      else if uses == 1 && constructorValue then freshPure (queue [value] 1)
      else if uses == 1 && M.null replacements then case moveSingleUse name value body of {
        Just result -> freshPure (beginChecked result);
        Nothing -> ordinary
      }
      else if uses < 2 || L.not (branchesToFreeValues value) then ordinary
      else let {
        retained = CheckedPending (PendingBody (useLet name value body) replacements
          (mergePendingUses (M.delete compareName name counts) (limitedUses value))
          (S.union compareName (S.delete compareName name calls) (negativeCalls value)))
          (afterCallBinding name value witnessed) (afterUseBinding name value 1 countOf)
      } in if witnessed name then freshPure retained else do {
        -- All calls with the same outer arguments can still share a single
        -- specialized result. Inspect the effective body before deciding.
        shared <- specializeSharedValue name value (materializePendingWith True pending);
        freshPure (case shared of { Just result -> beginChecked result; Nothing -> retained })
      }
  };
  -- Delay only while unwinding a contiguous nonrecursive let-body chain.
  -- Every other constructor and every unsupported let observes a fully
  -- materialized body. RHS normalization still precedes body normalization.
  passPendingRaw :: XErased -> Fresh PendingBody;
  passPendingRaw = passPendingFor False;
  passPendingFor checked expression = if checked then do {
    result <- passPendingWith True beginChecked delayCheckedPending expression;
    freshPure (checkedBody result)
  } else passPendingWith False beginPending delayOwnedLet expression;
  -- An adjacent, nonrecursive local function can be inlined twice when both
  -- arms call it. Keep one call and force the condition before its entry.
  -- The ordinary application still controls demand for the selected argument.
  shareLocalConditional :: XName -> XErased -> Fresh XErased;
  shareLocalConditional name expression = let {
    share chosen rebuild = case chosen of {
      XEApp (XEApp (XEApp (XEPrimitive PIfThenElse) condition) (XEApp (XEVar first) yes)) (XEApp (XEVar second) no) ->
        if eqName name first && eqName name second then do {
          decision <- freshName;
          let { flag = XEVar decision;
            selected = XEApp (XEApp (XEApp (XEPrimitive PIfThenElse) flag) yes) no;
            invoke = XEApp (XEVar name) selected };
          freshPure (rebuild (XELet decision condition (XEApp (XEApp (XEPrimitive PSeq) flag) invoke)))
        } else freshPure expression;
      _ -> freshPure expression
    }
  } in case expression of {
    XELet binder value body -> share value (\newValue -> XELet binder newValue body);
    _ -> share expression L.id
  };
  passPendingWith :: forall a. Bool -> (UseTree -> a) -> (XName -> UseTree -> a -> Fresh a) ->
    XErased -> Fresh a;
  passPendingWith checked begin delay expression = case expression of {
    XELet name value body -> do {
      normalized <- passOwnedFor checked value;
      following <- if checked then case useChildren normalized of {
        UseAbs _ _ -> shareLocalConditional name body;
        _ -> freshPure body
      } else freshPure body;
      pending <- passPendingWith checked begin delay following;
      delay name normalized pending
    };
    _ -> do {
      result <- passOwnedFor checked expression;
      freshPure (begin result)
    }
  };
  passOwnedRaw :: XErased -> Fresh UseTree;
  passOwnedRaw = passOwnedFor False;
  passOwnedFor checked expression = case expression of {
    XELet _ _ _ -> do {
      pending <- passPendingFor checked expression;
      freshPure (materializePendingWith checked pending)
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
  -- One checked pass owns unique names. Cache only independent RHS work
  -- that leaves the Fresh counter unchanged. The declaration body's rewrite
  -- still sees the entire current context and follows the original order.
  data StableRhs = StableRhs XErased UseTree;
  sameOwnedName :: XName -> XName -> Bool;
  sameOwnedName (XName a hint) (XName b other) = a == b && eqString hint other;
  sameOwnedOptional left right = case (,) left right of {
    (,) Nothing Nothing -> True;
    (,) (Just a) (Just b) -> sameOwnedName a b;
    _ -> False
  };
  sameOwnedPattern left right = case (,) left right of {
    (,) (XDefaultPattern a) (XDefaultPattern b) -> sameOwnedOptional a b;
    (,) (XConstructorPattern a ns) (XConstructorPattern b ms) ->
      eqString a b && L.eqList sameOwnedOptional ns ms;
    _ -> False
  };
  sameStableInput :: XErased -> XErased -> Bool;
  sameStableInput left right = case (,) left right of {
    (,) (XEVar a) (XEVar b) -> sameOwnedName a b;
    (,) (XEAbs a x) (XEAbs b y) -> sameOwnedName a b && sameStableInput x y;
    (,) (XEApp f a) (XEApp g b) -> sameStableInput f g && sameStableInput a b;
    (,) (XELet n v body) (XELet m w rest) ->
      sameOwnedName n m && sameStableInput v w && sameStableInput body rest;
    (,) (XELetRec as body) (XELetRec bs rest) ->
      L.eqList (\((,) a x) ((,) b y) -> sameOwnedName a b && sameStableInput x y) as bs &&
      sameStableInput body rest;
    (,) (XECase x as) (XECase y bs) -> sameStableInput x y && L.eqList
      (\(XErasedAlternative p a) (XErasedAlternative q b) ->
        sameOwnedPattern p q && sameStableInput a b) as bs;
    (,) (XEDouble a) (XEDouble b) -> doubleToBits a == doubleToBits b;
    _ -> X.equalErased left right
  };
  normalizeStableRhs :: IntMap StableRhs -> IntMap StableRhs -> XName -> XErased ->
    Fresh ((,) UseTree (IntMap StableRhs));
  normalizeStableRhs previous current name value = let {
    identity = nameId name;
    save normalized entry = let { indexed = IM.insert identity entry current } in
      seq indexed (freshPure ((,) normalized indexed));
    normalize = do {
      before <- freshSeed;
      normalized <- passOwnedFor True value;
      after <- freshSeed;
      if before == after && remainingSize 31 value < 0
      then save normalized (StableRhs value normalized)
      else freshPure ((,) normalized current)
    }
  } in case IM.lookup identity previous of {
    Just entry@(StableRhs input normalized) -> if sameStableInput input value
      then save normalized entry else normalize;
    Nothing -> normalize
  };
  stableBindingGroup :: IntMap StableRhs -> IntMap StableRhs -> [] ((,) XName XErased) ->
    Fresh ((,) ([] ((,) XName UseTree)) (IntMap StableRhs));
  stableBindingGroup previous current bindings = case bindings of {
    [] -> freshPure ((,) [] current);
    (:) ((,) name value) rest -> do {
      (,) normalized found <- normalizeStableRhs previous current name value;
      (,) following cached <- stableBindingGroup previous found rest;
      freshPure ((,) ((:) ((,) name normalized) following) cached)
    }
  };
  cachedDeclarationPass :: IntMap StableRhs -> IntMap StableRhs -> XErased ->
    Fresh ((,) UseTree (IntMap StableRhs));
  cachedDeclarationPass previous current expression = case expression of {
    XELet _ _ _ -> do {
      (,) pending cached <- cachedDeclarationSpine previous current expression;
      freshPure ((,) (materializePendingWith True (checkedBody pending)) cached)
    };
    XELetRec bindings body -> do {
      (,) normalized found <- stableBindingGroup previous current bindings;
      (,) following cached <- cachedDeclarationPass previous found body;
      result <- rewriteUsedFor True (useRec normalized following);
      freshPure ((,) result cached)
    };
    _ -> do {
      result <- passOwnedFor True expression;
      freshPure ((,) result current)
    }
  };
  cachedDeclarationSpine :: IntMap StableRhs -> IntMap StableRhs -> XErased ->
    Fresh ((,) CheckedPending (IntMap StableRhs));
  cachedDeclarationSpine previous current expression = case expression of {
    XELet name value body -> do {
      (,) normalized found <- normalizeStableRhs previous current name value;
      following <- case useChildren normalized of {
        UseAbs _ _ -> shareLocalConditional name body;
        _ -> freshPure body
      };
      (,) pending cached <- cachedDeclarationSpine previous found following;
      result <- delayCheckedPending name normalized pending;
      freshPure ((,) result cached)
    };
    _ -> do {
      (,) result cached <- cachedDeclarationPass previous current expression;
      freshPure ((,) (beginChecked result) cached)
    }
  };
  -- No projection can start in a subtree without a case whose original
  -- scrutinee names a known constructor. A later case can become eligible
  -- after a child rewrite, so any positive probe uses the full traversal.
  hasConstructorProjection :: Map XName ((,) String ([] XErased)) -> XErased -> Bool;
  hasConstructorProjection facts expression = let { visit = hasConstructorProjection facts } in
    case expression of {
      XEAbs _ body -> visit body;
      XEApp function argument -> visit function || visit argument;
      XELet _ value body -> visit value || visit body;
      XELetRec bindings body -> L.any (\((,) _ value) -> visit value) bindings || visit body;
      XECase subject alternatives -> (case subject of {
          XEVar name -> M.member compareName name facts;
          _ -> visit subject
        }) || L.any (\(XErasedAlternative _ body) -> visit body) alternatives;
      _ -> False
    };
  projectDeclarationSpine :: Map XName ((,) String ([] XErased)) -> XErased -> Fresh XErased;
  projectDeclarationSpine facts expression = let {
    project value = if hasConstructorProjection facts value then projectConstructors facts value else freshPure value
  } in case expression of {
    XELet name value body -> do {
      rhs <- project value;
      rest <- projectDeclarationSpine facts body;
      freshPure (XELet name rhs rest)
    };
    XELetRec bindings body -> do {
      rhs <- traverseFresh (\((,) name value) -> do {
        projected <- project value;
        freshPure ((,) name projected)
      }) bindings;
      rest <- projectDeclarationSpine facts body;
      freshPure (XELetRec rhs rest)
    };
    _ -> project expression
  };
  stableDeclarationIterations :: Map String (Maybe Int) -> Int -> IntMap StableRhs -> XErased -> Fresh XErased;
  stableDeclarationIterations arities count previous expression = if count == 0
    then freshPure expression else do {
      let { facts = constructorFacts arities expression };
      projected <- if M.null facts then freshPure expression else projectDeclarationSpine facts expression;
      (,) normalized cached <- cachedDeclarationPass previous IM.empty projected;
      let { next = useTerm normalized };
      if X.equalErased expression next then freshPure expression
      else stableDeclarationIterations arities (count - 1) cached next
    };
  -- Find references still needed by the entry before copying its declaration
  -- spine. A nonrecursive RHS is in the outer scope. A recursive group binds
  -- its names in every RHS and in the continuation. Any reference from the
  -- continuation keeps the whole recursive group.
  liveDeclarationSpine :: XErased -> (,) XErased (Set XName);
  liveDeclarationSpine expression = case expression of {
    XELet name rhs rest -> case liveDeclarationSpine rest of {
      (,) body live -> if S.member compareName name live
        then (,) (XELet name rhs body) (S.union compareName (free rhs) (S.delete compareName name live))
        else (,) body live
    };
    XELetRec bindings rest -> case liveDeclarationSpine rest of {
      (,) body live ->
        if L.any (\entry -> S.member compareName (L.fst entry) live) bindings
        then let {
          used = L.foldl (\names entry -> S.union compareName names (free (L.snd entry))) live bindings;
          bound = S.fromList compareName (L.map L.fst bindings)
        } in (,) (XELetRec bindings body) (S.difference compareName used bound)
        else (,) body live
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
      lifted <- liftConstructorFieldsFor checked arities recursive;
      let { iterate = if checked then stableDeclarationIterations arities 16 IM.empty
        else iterationsOwnedFor False arities 16 };
      simple <- iterate lifted;
      specialized <- specializeHigherOrder simple;
      iterate specialized
    };
  -- The checked optimizer has assigned distinct identities to all binders.
  -- In a wide mutually recursive group, keep one formal for positions that
  -- receive the same variable at every entry and stay equal on every peer call.
  compactRecursiveArguments :: XErased -> XErased;
  compactRecursiveArguments expression = case expression of {
    XELet n rhs rest -> XELet n rhs (compactRecursiveArguments rest);
    XELetRec bindings rest -> let {
      following = compactRecursiveArguments rest;
      original = XELetRec bindings following;
      members = L.map (\((,) n rhs) -> (,) n (lambdas rhs)) bindings
    } in case members of {
      (:) ((,) _ ((,) first _)) ((:) _ _) -> let {
        width = L.foldlStrict (\w entry -> L.min w (L.length (L.fst (L.snd entry))))
          (L.length first) members
      } in if width < 16 then original else compactGroupArguments members width following original;
      _ -> original
    };
    _ -> expression
  };
  -- Include partial applications and bare escapes. The shortest use bounds
  -- the prefix whose evaluation and calling convention can change together.
  recursiveArgumentUses targets params term tail = case applications term of {
    (,) (XEVar n) args -> let { following = L.foldr (recursiveArgumentUses targets params) tail args } in
      if S.member compareName n targets then (:) ((,) params args) following else following;
    (,) head [] -> L.foldr (recursiveArgumentUses targets params) tail (subterms head);
    (,) head args -> recursiveArgumentUses targets params head (L.foldr (recursiveArgumentUses targets params) tail args)
  };
  -- Intersect the current partition with the equality observed at one site.
  -- Only variable identity and the caller's proven formal classes can equate
  -- positions. Two arbitrary expressions always get distinct keys.
  refineArgumentClasses positions classes current ((,) params args) = let {
    formals = M.fromList compareName (L.zip params classes);
    token pos arg = case arg of {
      XEVar n -> case M.lookup compareName n formals of {
        Just representative -> (,) 0 representative;
        Nothing -> (,) 1 (nameId n)
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
  compactGroupArguments members arity rest original = let {
    targets = S.fromList compareName (L.map L.fst members);
    external = recursiveArgumentUses targets [] rest [];
    calls = L.foldr (\((,) _ ((,) params body)) tail -> recursiveArgumentUses targets params body tail) external members;
    width = L.foldlStrict (\n call -> L.min n (L.length (L.snd call))) arity calls;
    positions = L.range 0 (width - 1);
    stable classes = let { next = L.foldlStrict (refineArgumentClasses positions classes) classes calls } in
      if L.eqList eqInt next classes then classes else stable next;
    classes = stable (L.replicate width 0);
    keep = L.zipWith eqInt positions classes;
    select xs = L.append (L.map L.snd (L.filter L.fst (L.zip keep xs))) (L.drop width xs);
    rewrite aliases t = case applications t of {
      (,) (XEVar n) args -> do {
        actuals <- traverseFresh (rewrite aliases) (if S.member compareName n targets then select args else args);
        freshPure (L.foldl XEApp (XEVar (M.findWithDefault compareName n n aliases)) actuals)
      };
      (,) head [] -> children (rewrite aliases) head;
      (,) head args -> do {
        f <- rewrite aliases head;
        actuals <- traverseFresh (rewrite aliases) args;
        freshPure (L.foldl XEApp f actuals)
      }
    };
    member ((,) n ((,) args body)) = let {
      formals = M.fromList L.compareInt (L.zip positions args);
      aliases = M.fromList compareName (L.zip args (L.map (\rep -> M.get L.compareInt rep formals) classes));
      result = L.fst (runFresh (rewrite aliases body) 0)
    } in (,) n (L.foldr XEAbs result (select args))
  } in if L.null external || width < 2 || L.all (\v -> v) keep then original else
    XELetRec (L.map member members) (L.fst (runFresh (rewrite M.empty rest) 0));
  -- Specialize a private recursive worker entered by one saturated call.
  -- A static function argument stays fixed when every recursive call passes
  -- the formal itself or the same primitive. Any partial application, escape,
  -- or different argument keeps the original calling convention.
  compactStaticRecursion :: XErased -> XErased;
  compactStaticRecursion expression =
    L.fst (runFresh (specializeStaticRecursion expression) (L.advanceIdentity (maxIdentity expression) 1));
  specializeStaticRecursion :: XErased -> Fresh XErased;
  specializeStaticRecursion expression = do {
    normalized <- children specializeStaticRecursion expression;
    case normalized of {
      -- Encoding the canonical character list of a literal gives that string.
      XEApp (XEPrimitive PTextFromChars) (XEApp (XEPrimitive PTextToChars) literal@(XEString _)) ->
        freshPure literal;
      XELetRec [((,) worker rhs)] entry -> case (,) (lambdas rhs) (applications entry) of {
        (,) ((,) parameters body) ((,) (XEVar called) arguments) ->
          let {
            slots = L.zipWith (\parameter argument -> (,) parameter (staticPrimitive argument))
              parameters arguments;
            fixed = L.mapMaybe (\((,) name expected) -> case expected of {
              Just primitive -> Just ((,) name (XEPrimitive primitive)); Nothing -> Nothing
            }) slots;
            retained = L.mapMaybe (\((,) name expected) -> case expected of {
              Nothing -> Just name; Just _ -> Nothing
            }) slots
          } in if eqName worker called && L.length parameters == L.length arguments &&
                    L.not (L.null fixed) && L.not (L.null retained) &&
                    L.all (\argument -> occurrences 1 worker argument == 0) arguments &&
                    uniformStaticRecursion worker slots body
          then do {
            let { plan = L.map L.snd slots };
            contracted <- contractStaticRecursion worker plan body;
            specialized <- copy (M.fromList compareName fixed) contracted;
            freshPure (XELetRec [((,) worker (L.foldr XEAbs specialized retained))]
              (L.foldl XEApp (XEVar worker) (dynamicArguments plan arguments)))
          } else freshPure normalized;
        _ -> freshPure normalized
      };
      XELetRec bindings _ -> if textWorkerGroup bindings then foldStaticConversions normalized else freshPure normalized;
      _ -> freshPure normalized
    }
  };
  -- A direct primitive argument from a sibling starts a bounded local analysis.
  -- Check every use of each private function, including references in argument
  -- position. A partial call or escape makes all its formals unknown.
  textWorkerGroup bindings = case bindings of {
    (:) _ ((:) _ _) -> L.null (L.drop 4 bindings) && L.any (\((,) self fn) ->
      case applications (L.snd (lambdas fn)) of {
        (,) (XEVar target) args -> L.not (eqName target self) &&
          L.any (\entry -> eqName target (L.fst entry)) bindings &&
          L.any textConverter args;
        _ -> False
      }) bindings;
    _ -> False
  };
  textConverter term = case term of { XEPrimitive PTextFromChars -> True; _ -> False };
  privateFunctions term rest = let {
    put ((,) name fn) tail = case lambdas fn of {
      (,) [] _ -> tail; (,) parameters _ -> (:) ((,) name parameters) tail
    };
    below = L.foldr privateFunctions rest (subterms term)
  } in case term of {
    XELet name rhs _ -> put ((,) name rhs) below;
    XELetRec defs _ -> L.foldr put below defs;
    _ -> below
  };
  regionBinders term rest = let { below = L.foldr regionBinders rest (subterms term) } in case term of {
    XEAbs n _ -> (:) n below;
    XELet n _ _ -> (:) n below;
    XELetRec defs _ -> L.foldr (\entry tail -> (:) (L.fst entry) tail) below defs;
    XECase _ branches -> L.foldr (\(XErasedAlternative pattern _) tail ->
      L.append (X.patternNames pattern) tail) below branches;
    _ -> below
  };
  privateCalls functions known term = case applications term of {
    (,) head args -> let {
      here = case head of {
        XEVar target -> if M.member compareName target functions
          then M.insertWith compareName L.append target [args] known else known;
        _ -> L.foldlStrict (privateCalls functions) known (subterms head)
      }
    } in L.foldlStrict (privateCalls functions) here args
  };
  -- Nothing rules out a slot. Otherwise it records the supplying formals and
  -- whether any call supplies the converter directly.
  conversionInputs functions calls = L.concatMap (\((,) target parameters) ->
    let { uses = M.findWithDefault compareName [] target calls;
          arity = L.length parameters;
          add observed value = case observed of {
            Nothing -> Nothing;
            Just ((,) concrete names) -> case value of {
              XEPrimitive PTextFromChars -> Just ((,) True names);
              XEVar name -> Just ((,) concrete ((:) name names));
              _ -> Nothing
            }
          };
          inputs = L.foldlStrict (L.zipWith add) (L.map (\_ -> Just ((,) False [])) parameters) uses
    } in if L.null uses || L.any (\args -> L.length args /= arity) uses then []
      else L.mapMaybe (\((,) name value) -> case value of {
        Nothing -> Nothing; Just supplied -> Just ((,) name supplied)
      }) (L.zip parameters inputs)) (M.toList functions);
  -- Each newly certified formal has a concrete supplier. A self-forwarding
  -- call preserves it. Unseeded or mutually dependent unknowns remain opaque.
  certifiedConversions limit inputs known =
    if limit == 0 then known else let {
      next = L.foldlStrict (\found ((,) slot ((,) concrete names)) ->
        if (concrete || L.any (\name -> S.member compareName name known) names) &&
           L.all (\name -> eqName name slot || S.member compareName name known) names
        then S.insert compareName slot found else found) known inputs
    } in if S.size next == S.size known then known else certifiedConversions (limit - 1) inputs next;
  -- Only a known positive-arity primitive can erase this seq. Preserve every
  -- other binding and demand, including a converter supplied as a computation.
  foldConversionText known expression = do {
    value <- children (foldConversionText known) expression;
    let { isConverter item = case item of {
          XEVar name -> S.member compareName name known; _ -> textConverter item
        } };
    freshPure (case value of {
      XELet bound rhs (XEApp (XEApp (XEPrimitive PSeq) (XEVar forced)) (XEVar returned)) ->
        if eqName bound forced && eqName bound returned && isConverter rhs
        then XEPrimitive PTextFromChars else value;
      XEApp fn (XEApp (XEPrimitive PTextToChars) literal@(XEString _)) ->
        if isConverter fn then literal else value;
      XEApp (XEPrimitive PStringLength) (XEString text) -> XEInt (stringLength text);
      XEApp (XEApp (XEPrimitive PAddInt) (XEInt left)) (XEInt right) -> XEInt (left + right);
      _ -> value
    })
  };
  foldStaticConversions expression =
    if remainingSize 16384 expression < 0 then freshPure expression else let {
      definitions = privateFunctions expression [];
      binders = regionBinders expression [];
      bound = S.fromList compareName binders;
      -- The checked optimizer normally gives binders unique identities. Keep
      -- ambiguous hand-built terms on the ordinary path as well.
      scoped = S.size bound == L.length binders &&
        S.null (S.intersection compareName bound (free expression))
    } in if L.not (L.null (L.drop 16 definitions)) || L.not scoped then freshPure expression else let {
      functions = M.fromList compareName definitions;
      inputs = conversionInputs functions (privateCalls functions M.empty expression);
      certified = certifiedConversions 12 inputs S.empty
    } in if S.null certified then freshPure expression else do {
      folded <- foldConversionText certified expression;
      contractConversionFormals functions certified folded
    };
  -- Certified private functions can omit a converter from both binders and
  -- saturated calls. Keep all-static functions as functions to preserve WHNF.
  contractConversionFormals :: Map XName ([] XName) -> Set XName -> XErased -> Fresh XErased;
  contractConversionFormals functions certified expression = let {
    known name = S.member compareName name certified;
    select parameters = if L.all known parameters then [] else L.filter known parameters;
    removed = S.fromList compareName (L.concatMap select (M.elems functions));
    drops name = S.member compareName name removed;
    plan parameters = if L.any drops parameters
      then Just (L.map (\name -> if drops name then Just PTextFromChars else Nothing) parameters)
      else Nothing;
    plans = M.mapMaybe plan functions;
    visit term = case term of {
      XEVar name -> freshPure (if drops name then XEPrimitive PTextFromChars else term);
      XEAbs name body -> if drops name then visit body else children visit term;
      XEApp _ _ -> case applications term of {
        (,) head arguments -> let {
          retained = case head of {
            XEVar target -> case M.lookup compareName target plans of {
              Just slots -> dynamicArguments slots arguments; Nothing -> arguments
            };
            _ -> arguments
          }
        } in do {
          callee <- visit head;
          operands <- traverseFresh visit retained;
          freshPure (L.foldl XEApp callee operands)
        }
      };
      _ -> children visit term
    }
  } in if S.null removed then freshPure expression else visit expression;
  staticPrimitive :: XErased -> Maybe Primitive;
  staticPrimitive expression = case expression of {
    XEPrimitive primitive -> if P.primitiveArity primitive > 0 then Just primitive else Nothing;
    _ -> Nothing
  };
  dynamicArguments :: [] (Maybe Primitive) -> [] XErased -> [] XErased;
  dynamicArguments slots arguments = L.mapMaybe (\((,) expected argument) -> case expected of {
    Nothing -> Just argument; Just _ -> Nothing
  }) (L.zip slots arguments);
  uniformStaticRecursion :: XName -> [] ((,) XName (Maybe Primitive)) -> XErased -> Bool;
  uniformStaticRecursion worker slots = let {
    forwarding ((,) ((,) formal expected) argument) = case expected of {
      Nothing -> True;
      Just primitive -> case argument of {
        XEVar name -> eqName formal name;
        XEPrimitive p -> P.primitiveCode p == P.primitiveCode primitive;
        _ -> False
      }
    };
    visit term = case applications term of {
      (,) (XEVar name) args ->
        if eqName name worker
        then L.length slots == L.length args && L.all forwarding (L.zip slots args) && L.all visit args
        else L.all visit args;
      (,) head args -> L.all visit (subterms head) && L.all visit args
    }
  } in visit;
  contractStaticRecursion :: XName -> [] (Maybe Primitive) -> XErased -> Fresh XErased;
  contractStaticRecursion worker slots expression = case applications expression of {
    (,) (XEVar target) args -> if eqName target worker then do {
      kept <- traverseFresh (contractStaticRecursion worker slots) (dynamicArguments slots args);
      freshPure (L.foldl XEApp (XEVar worker) kept)
    } else children (contractStaticRecursion worker slots) expression;
    _ -> children (contractStaticRecursion worker slots) expression
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
  -- A saturated call to a lambda that returns its parameter does not
  -- evaluate the remaining arguments. Keep excess applications in order.
  scopedProjection expression = case lambdas expression of {
    (,) ((:) first rest) (XEVar selected) -> let {
      parameters = (:) first rest;
      arity = L.length parameters;
      position i remaining = case remaining of {
        [] -> Nothing;
        (:) name tail -> if eqName name selected then Just (ProjectsArgument arity i)
          else position (i - 1) tail
      }
    } in position (arity - 1) (L.reverse parameters);
    _ -> Nothing
  };
  projectApplication facts original = case applications original of {
    (,) (XEVar name) arguments -> case M.lookup compareName name facts of {
      Just (ProjectsArgument arity index) -> case L.splitAt arity arguments of {
        (,) prefix rest -> if L.length prefix == arity then case L.drop index prefix of {
          (:) argument _ -> Just (L.foldl XEApp argument rest);
          _ -> Nothing
        } else Nothing
      };
      _ -> Nothing
    };
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
    XInstantiationSpine head rows -> typedScope (X.expandInstantiationSpine head rows);
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
        normalized = visit facts value;
        role = case scopedProjection normalized of {
          Just projection -> Just projection;
          Nothing -> scopedUnaryUse (erase value)
        };
        following = case role of {
          Just found -> M.insert compareName name found facts;
          Nothing -> M.delete compareName name facts
        }
      } in XELet name normalized (visit following body);
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
        };
        ordinary = case erase fn of {
          XEVar name -> case M.lookup compareName name facts of {
            Just (FoldsConstructors rules) -> L.fromMaybe original (foldArgument rules arg);
            _ -> affine
          };
          _ -> affine
        }
      } in if M.null facts then original else L.fromMaybe ordinary (projectApplication facts original);
      OtherInput -> original
    }
  } in visit;
  -- This extra algebraic pass is for finite checked programs. Its rewrites
  -- introduce no binders and preserve evaluation of the single input value.
  optimizeChecked expression = optimizeAfterFields (foldScopedFields M.empty expression);
  optimizeCheckedTerm term = compactRecursiveArguments (optimizeAfterFields (eraseScopedFields M.empty term));
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
