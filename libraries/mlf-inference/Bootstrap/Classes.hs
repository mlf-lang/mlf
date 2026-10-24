-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Classes where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import Bootstrap.Fresh;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.IntSet as I;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Kinding as K;
  import qualified Bootstrap.Desugar as Desugar;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.X.Pretty as Pretty;
  data Info = Info SClassDecl String String (List (Pair String String)) (List String);
  data InstanceHead = HVar String | HCon String (List InstanceHead);
  className :: SClassDecl -> String;
  className (SClassDecl n _ _ _) = n;
  classParameters :: SClassDecl -> List (Pair String Kind);
  classParameters (SClassDecl _ ps _ _) = ps;
  superclasses :: SClassDecl -> List SPredicate;
  superclasses (SClassDecl _ _ ps _) = ps;
  classMethods :: SClassDecl -> List (Pair String SType);
  classMethods (SClassDecl _ _ _ ms) = ms;
  instanceVariables :: SInstanceDecl -> List (Pair String Kind);
  instanceVariables (SInstanceDecl vs _ _ _ _) = vs;
  instanceContext :: SInstanceDecl -> List SPredicate;
  instanceContext (SInstanceDecl _ ps _ _ _) = ps;
  instanceClass :: SInstanceDecl -> String;
  instanceClass (SInstanceDecl _ _ c _ _) = c;
  instanceHead :: SInstanceDecl -> List SType;
  instanceHead (SInstanceDecl _ _ _ ts _) = ts;
  instanceMethods :: SInstanceDecl -> List (Pair String SExpr);
  instanceMethods (SInstanceDecl _ _ _ _ ms) = ms;
  lookupInfo :: Map String Info -> String -> Either String Info;
  lookupInfo infos name =
    case M.lookup compareString name infos of {
      Nothing -> Left ("unknown class: " ++ name);
      Just info -> Right info
    };
  dictionary :: Map String Info -> SPredicate -> Either String SType;
  dictionary infos (SPredicate name arguments) =
    do {
      boundValueShared1 <- lookupInfo infos name;
      case boundValueShared1 of {
        Info _ ty _ _ _ ->
          do {
            Right (SCon ty arguments)
          }
      }
    };
  bottom :: Kind -> SType;
  bottom k =
    case k of {
      Star -> SBottom;
      _ -> SBottomKind k
    };
  quantify :: List (Pair String Kind) -> SType -> SType;
  quantify variables ty = foldr (\(Pair n k) b -> SForall Flexible n (bottom k) b) ty variables;
  freeType :: SType -> List String;
  freeType ty = sortBy compareString (nubBy eqString (freeTypeRaw ty));
  freeTypeRaw :: SType -> List String;
  freeTypeRaw ty =
    case ty of {
      STVar a -> Cons a Nil;
      SArrow a b -> append (freeTypeRaw a) (freeTypeRaw b);
      STypeApp a b -> append (freeTypeRaw a) (freeTypeRaw b);
      SCon _ ts -> concatMap freeTypeRaw ts;
      SForall _ a bound body ->
        append (freeTypeRaw bound) (filter (\n -> not (eqString a n)) (freeTypeRaw body));
      SQualified predicates body ->
        append (freeTypeRaw body)
          (concatMap (\(SPredicate _ args) -> concatMap freeTypeRaw args) predicates);
      _ -> Nil
    };
  unique :: String -> List String -> Either String Unit;
  unique label names =
    ensure (length names == length (nubBy eqString names)) ("duplicate " ++ label);
  scheme :: SType -> Triple (List (Triple Flag String SType)) (List SPredicate) SType;
  scheme ty =
    case ty of {
      SForall flag name bound body ->
        case scheme body of {
          Triple variables predicates result ->
            Triple (Cons (Triple flag name bound) variables) predicates result
        };
      SQualified predicates body -> Triple Nil predicates body;
      _ -> Triple Nil Nil ty
    };
  qualified :: SType -> Bool;
  qualified ty =
    case ty of {
      SQualified _ _ -> True;
      SForall _ _ a b -> (qualified a || qualified b);
      SArrow a b -> (qualified a || qualified b);
      STypeApp a b -> (qualified a || qualified b);
      SCon _ ts -> any qualified ts;
      _ -> False
    };
  translateScheme :: DataEnv -> Map String Info -> SType -> Either String SType;
  translateScheme ds infos ty =
    case scheme ty of {
      Triple variables predicates body ->
        do {
          ensure (not (qualified body || any (\(Triple _ _ bound) -> qualified bound) variables))
            "class constraints must occur at the outside of a type scheme";
          scope <-
            foldEither
              (\env (Triple _ a bound) ->
                 do {
                   kind <- K.kindOf ds env bound;
                   Right (M.insert compareString a kind env)
                 })
              M.empty
              variables;
          traverseEither (checkPredicate ds infos scope) predicates;
          args <- traverseEither (dictionary infos) predicates;
          let {
            result =
              foldr (\(Triple flag a bound) rest -> SForall flag a bound rest)
                (foldr SArrow body args)
                variables
          };
          K.annotationType ds M.empty result;
          Right result
        }
    };
  checkPredicate :: DataEnv ->
                    Map String Info -> Map String Kind -> SPredicate -> Either String Unit;
  checkPredicate ds infos scope (SPredicate name arguments) =
    do {
      boundValueShared2 <- lookupInfo infos name;
      case boundValueShared2 of {
        Info declaration _ _ _ _ ->
          do {
            let {
              parameters = classParameters declaration
            };
            ensure (length arguments == length parameters)
              ("class argument arity mismatch: " ++
               (name ++
                (" expects " ++
                 (showInt (length parameters) ++ (", got " ++ showInt (length arguments))))));
            actual <- traverseEither (K.kindOf ds scope) arguments;
            ensure (eqList eqKind actual (map snd parameters))
              ("class parameter kind mismatch: " ++ name)
          }
      }
    };
  field :: SType -> Either String Field;
  field ty =
    case ty of {
      STVar a -> Right (Parameter a);
      SArrow a b ->
        do {
          x <- field a;
          y <- field b;
          Right (Function x y)
        };
      STypeApp f a ->
        do {
          x <- field f;
          y <- field a;
          Right (Application x y)
        };
      SCon c args -> mapEither (Applied c) (traverseEither field args);
      SForall Flexible a SBottom body -> mapEither (Quantified a Star) (field body);
      SForall Flexible a (SBottomKind k) body -> mapEither (Quantified a k) (field body);
      _ ->
        Left
          "class methods require ordinary forall signatures without bounded or nested class constraints"
    };
  lowerClasses :: SProgram -> Either String (Pair SProgram (Map String String));
  lowerClasses original = lowerClassesWithImports S.empty original;
  lowerClassesWithImports :: Set String ->
                             SProgram -> Either String (Pair SProgram (Map String String));
  lowerClassesWithImports imported original =
    do {
      program <- Surface.lowerSurface original;
      lowerCoreClasses imported M.empty Nothing program
    };
  lowerClassesWithScopes :: Map String IntSet ->
                            List IntSet ->
                            SProgram -> Either String (Pair SProgram (Map String String));
  lowerClassesWithScopes values instances original =
    do {
      program <- Surface.lowerSurface original;
      lowerCoreClasses S.empty values (Just instances) program
    };
  lowerCoreClasses :: Set String ->
                      Map String IntSet ->
                      Maybe (List IntSet) ->
                      SProgram -> Either String (Pair SProgram (Map String String));
  lowerCoreClasses imported valueIndices instanceIndices program =
    lowerCoreClassesWith Nothing imported valueIndices instanceIndices program;
  lowerSeparateClasses externals instanceNames original =
    do {
      program <-
        Surface.lowerSurface
          (case original of {
             SProgram ds b -> SClassProgram ds Nil Nil b;
             _ -> original
           });
      case program of {
        SClassProgram ds Nil Nil body ->
          let {
            parameters =
              map
                (\(Pair n ty) ->
                   Triple n (SAnnotation Nil ty)
                     (SChecked ty
                        (SApp (SPrimitive PPanic) (SStringLit "unlinked module parameter"))))
                (M.toList externals)
          } in
          Right
            (Pair (SProgram ds (if null parameters then body else SLetRec parameters body))
               M.empty);
        _ ->
          lowerCoreClassesWith (Just (Pair externals instanceNames)) S.empty M.empty Nothing program
      }
    };
  -- Crate lowering has a complete declaration/instance inventory, but candidate
  -- visibility remains that of each declaration's defining module. Stable
  -- dictionary names make the lowered declarations reusable inference queries.
  lowerSeparateClassesWithScopes :: Map String SType ->
                                    List String ->
                                    Map String IntSet ->
                                    List IntSet ->
                                    SProgram -> Either String (Pair SProgram (Map String String));
  lowerSeparateClassesWithScopes externals instanceNames valueScopes instanceScopes original =
    do {
      program <-
        Surface.lowerSurface
          (case original of {
             SProgram ds b -> SClassProgram ds Nil Nil b;
             _ -> original
           });
      case program of {
        SClassProgram ds Nil Nil body ->
          let {
            parameters =
              map
                (\(Pair n ty) ->
                   Triple n (SAnnotation Nil ty)
                     (SChecked ty
                        (SApp (SPrimitive PPanic) (SStringLit "unlinked crate parameter"))))
                (M.toList externals)
          } in
          Right
            (Pair (SProgram ds (if null parameters then body else SLetRec parameters body))
               M.empty);
        _ ->
          lowerCoreClassesWith (Just (Pair externals instanceNames)) S.empty valueScopes
            (Just instanceScopes)
            program
      }
    };
  lowerCoreClassesWith :: Maybe (Pair (Map String SType) (List String)) ->
                          Set String ->
                          Map String IntSet ->
                          Maybe (List IntSet) ->
                          SProgram -> Either String (Pair SProgram (Map String String));
  lowerCoreClassesWith config imported valueIndices instanceIndices program =
    case program of {
      SProgram ds body ->
        case config of {
          Nothing -> Right (Pair program M.empty);
          Just _ ->
            lowerCoreClassesWith config imported valueIndices instanceIndices
              (SClassProgram ds Nil Nil body)
        };
      SClassProgram datatypes declarations instances body ->
        do {
          case instanceIndices of {
            Nothing -> Right Unit;
            Just scopes ->
              ensure (length scopes == length instances) "module instance scope count mismatch"
          };
          base <- D.validateDeclarations datatypes;
          unique "class" (map className declarations);
          unique "class method"
            (concatMap
               (\d ->
                  if S.member compareString (className d) imported
                  then Nil
                  else map fst (classMethods d))
               declarations);
          unique "class method"
            (concatMap
               (\d ->
                  if S.member compareString (className d) imported
                  then map fst (classMethods d)
                  else Nil)
               declarations);
          traverseEither
            (\d ->
               do {
                 unique "class method" (map fst (classMethods d));
                 unique "class parameter" (map fst (classParameters d));
                 ensure (not (null (classParameters d))) "class must have at least one parameter"
               })
            declarations;
          let {
            classes = map implicitParameters declarations
          };
          let {
            used =
              append (Desugar.allNames body)
                (append
                   (concatMap
                      (\i -> concatMap (\(Pair _ e) -> Desugar.allNames e) (instanceMethods i))
                      instances)
                   (append
                      (concatMap
                         (\d ->
                            Cons (D.datatypeName d)
                              (map D.constructorName (D.datatypeConstructors d)))
                         datatypes)
                      (concatMap
                         (\d ->
                            Cons (className d)
                              (append (map fst (classParameters d))
                                 (concatMap (\(Pair n ty) -> Cons n (typeNames ty))
                                    (classMethods d))))
                         declarations)))
          };
          runFresh used
            (lowerClassesBody config imported valueIndices instanceIndices datatypes instances body
               base
               classes)
        }
    };
  implicitParameters :: SClassDecl -> SClassDecl;
  implicitParameters (SClassDecl name parameters supers methods) =
    SClassDecl name parameters supers
      (map
         (\(Pair n ty) ->
            Pair n
              (quantify
                 (map (\a -> Pair a Star) (Surface.without (freeType ty) (map fst parameters)))
                 ty))
         methods);
  typeNames :: SType -> List String;
  typeNames ty =
    case ty of {
      STVar n -> Cons n Nil;
      SCon n ts -> Cons n (concatMap typeNames ts);
      SForall _ n a b -> Cons n (append (typeNames a) (typeNames b));
      SArrow a b -> append (typeNames a) (typeNames b);
      STypeApp a b -> append (typeNames a) (typeNames b);
      SQualified ps t ->
        append (concatMap (\(SPredicate n ts) -> Cons n (concatMap typeNames ts)) ps) (typeNames t);
      _ -> Nil
    };
  separateName config stable prefix =
    case config of {
      Nothing -> freshName prefix;
      Just _ -> freshPure stable
    };
  lowerClassesBody :: Maybe (Pair (Map String SType) (List String)) ->
                      Set String ->
                      Map String IntSet ->
                      Maybe (List IntSet) ->
                      List DataDecl ->
                      List SInstanceDecl ->
                      SExpr ->
                      DataEnv -> List SClassDecl -> Fresh (Pair SProgram (Map String String));
  lowerClassesBody config imported valueIndices instanceIndices datatypes instances body base classes =
    do {
      entries <-
        mapM
          (\declaration ->
             do {
               dict <-
                 separateName config ("Dict_" ++ className declaration)
                   ("Dict" ++ className declaration);
               ctor <-
                 separateName config ("Make_" ++ className declaration)
                   ("Make" ++ className declaration);
               methods <-
                 mapM
                   (\(Pair n _) ->
                      do {
                        selector <-
                          separateName config ("select_" ++ n) ("select" ++ className declaration);
                        freshPure (Pair n selector)
                      })
                   (classMethods declaration);
               supers <-
                 mapM
                   (\i ->
                      separateName config
                        ("super_" ++ (className declaration ++ ("_" ++ showInt i)))
                        "superclass")
                   (range 0 (length (superclasses declaration) - 1));
               freshPure (Pair (className declaration) (Info declaration dict ctor methods supers))
             })
          classes;
      let {
        infos = M.fromList compareString entries
      };
      freshLift (validateClasses base infos);
      dictionaries <-
        freshLift (traverseEither (\entry -> dictionaryDecl infos (snd entry)) entries);
      ds <- freshLift (D.validateDeclarations (append datatypes dictionaries));
      checkedInstances <- freshLift (traverseEither (validateInstance ds infos) instances);
      freshLift (checkOverlap checkedInstances);
      names <-
        case config of {
          Nothing -> mapM (\inst -> freshName "instanceDictionary") checkedInstances;
          Just (Pair _ ns) ->
            do {
              freshLift
                (ensure (length ns == length checkedInstances)
                   "separate instance identity count mismatch");
              freshPure ns
            }
        };
      let {
        supers =
          concatMap (\(Pair _ (Info _ _ _ _ ns)) -> map (\n -> Pair SuperclassEvidence n) ns)
            entries
      };
      let {
        globalCandidates = append (map (\n -> Pair InstanceEvidence n) names) supers
      };
      let {
        select = selectCandidates names supers
      };
      let {
        valueScopes = M.map select valueIndices
      };
      let {
        instanceScopes =
          case instanceIndices of {
            Nothing -> replicate (length instances) globalCandidates;
            Just scopes -> map select scopes
          }
      };
      let {
        externalSchemes =
          case config of {
            Nothing -> M.empty;
            Just (Pair es _) -> es
          }
      };
      let {
        externalOverloads =
          M.mapWithKey
            (\n ty ->
               case scheme ty of {
                 Triple _ ps _ -> Pair n (map (\(SPredicate c _) -> c) ps)
               })
            externalSchemes
      };
      let {
        methodEnv =
          M.union compareString externalOverloads
            (M.union compareString (methodBindings imported False entries)
               (methodBindings imported True entries))
      };
      selectorGroups <- mapM (\entry -> selectorDefinitions infos (snd entry)) entries;
      definitions <-
        mapM
          (\(Pair (Pair name inst) available) ->
             instanceDefinition valueScopes ds infos methodEnv name inst available)
          (zip (zip names checkedInstances) instanceScopes);
      boundValueShared3 <- lowerExpr valueScopes ds infos methodEnv globalCandidates body;
      case boundValueShared3 of {
        Pair expression wants ->
          do {
            let {
              result = closeWants infos globalCandidates wants expression
            };
            let {
              bindings =
                map
                  (\(Triple n annotation rhs) ->
                     case annotation of {
                       SAnnotation _ ty -> Triple n annotation (SChecked ty rhs)
                     })
                  (append (concat selectorGroups) definitions)
            };
            let {
              localBindings =
                filter (\(Triple n _ _) -> not (M.member compareString n externalSchemes)) bindings
            };
            let {
              inner = if null localBindings then result else SLetRec localBindings result
            };
            externalBindings <-
              mapM
                (\(Pair n ty) ->
                   do {
                     translated <- freshLift (translateScheme ds infos ty);
                     freshPure
                       (Triple n (SAnnotation Nil translated)
                          (SChecked translated
                             (SApp (SPrimitive PPanic) (SStringLit "unlinked module parameter"))))
                   })
                (M.toList externalSchemes);
            let {
              output = if null externalBindings then inner else SLetRec externalBindings inner
            };
            freshPure
              (Pair (SProgram (append datatypes dictionaries) output)
                 (M.fromList compareString
                    (map (\(Pair name (Info _ dict _ _ _)) -> Pair dict name) entries)))
          }
      }
    };
  selectCandidates :: List String ->
                      List (Pair EvidenceRole String) -> IntSet -> List (Pair EvidenceRole String);
  selectCandidates names supers indices =
    append
      (concatMap
         (\(Pair i n) -> if I.member i indices then Cons (Pair InstanceEvidence n) Nil else Nil)
         (zip (range 0 (length names - 1)) names))
      supers;
  methodBindings :: Set String ->
                    Bool -> List (Pair String Info) -> Map String (Pair String (List String));
  methodBindings imported isImported entries =
    M.fromList compareString
      (concatMap
         (\(Pair name (Info _ _ _ methods _)) ->
            if if isImported
               then S.member compareString name imported
               else not (S.member compareString name imported)
            then map (\(Pair method selector) -> Pair method (Pair selector (Cons name Nil)))
                   methods
            else Nil)
         entries);
  instanceDefinition :: Map String (List (Pair EvidenceRole String)) ->
                        DataEnv ->
                        Map String Info ->
                        Map String (Pair String (List String)) ->
                        String ->
                        SInstanceDecl ->
                        List (Pair EvidenceRole String) -> Fresh (Triple String SAnnotation SExpr);
  instanceDefinition valueScopes ds infos methodEnv name inst available =
    do {
      boundValueShared6 <- freshLift (lookupInfo infos (instanceClass inst));
      case boundValueShared6 of {
        Info declaration _ ctor _ _ ->
          do {
            givenNames <- mapM (\p -> freshName "givenDictionary") (instanceContext inst);
            let {
              candidates = append (map (\n -> Pair GivenEvidence n) givenNames) available
            };
            methodBodies <-
              mapM
                (\(Pair method methodType) ->
                   do {
                     original <-
                       freshLift
                         (case lookup eqString method (instanceMethods inst) of {
                            Nothing -> Left ("missing instance method: " ++ method);
                            Just e -> Right e
                          });
                     boundValueShared4 <-
                       lowerExpr valueScopes ds infos methodEnv candidates original;
                     case boundValueShared4 of {
                       Pair translated wants ->
                         do {
                           expected <-
                             instantiateMethod
                               (M.fromList compareString
                                  (zip (map fst (classParameters declaration)) (instanceHead inst)))
                               methodType;
                           freshPure
                             (SChecked expected (closeWants infos candidates wants translated))
                         }
                     }
                   })
                (classMethods declaration);
            superBodies <-
              mapM
                (\(SPredicate c _) ->
                   do {
                     boundValueShared5 <- freshLift (lookupInfo infos c);
                     case boundValueShared5 of {
                       Info _ dict _ _ _ ->
                         do {
                           freshPure (SWanted dict candidates)
                         }
                     }
                   })
                (superclasses declaration);
            contextTypes <- freshLift (traverseEither (dictionary infos) (instanceContext inst));
            resultType <-
              freshLift (dictionary infos (SPredicate (instanceClass inst) (instanceHead inst)));
            let {
              ty = quantify (instanceVariables inst) (foldr SArrow resultType contextTypes)
            };
            let {
              rhs =
                foldr (\n b -> SLam n Nothing b)
                  (foldl SApp (SConstructor ctor) (append superBodies methodBodies))
                  givenNames
            };
            freshPure (Triple name (SAnnotation Nil ty) rhs)
          }
      }
    };
  validateClasses :: DataEnv -> Map String Info -> Either String Unit;
  validateClasses ds infos =
    do {
      traverseEither
        (\(Info declaration _ _ _ _) ->
           do {
             let {
               scope = M.fromList compareString (classParameters declaration)
             };
             traverseEither (checkPredicate ds infos scope) (superclasses declaration);
             traverseEither
               (\(Pair name ty) ->
                  do {
                    let {
                      missing = Surface.without (M.keys scope) (freeType ty)
                    };
                    ensure (null missing)
                      ("ambiguous class method: " ++
                       (name ++
                        (" does not mention class parameters " ++ intercalate ", " missing)));
                    K.annotationType ds scope ty;
                    field ty;
                    Right Unit
                  })
               (classMethods declaration);
             Right Unit
           })
        (M.elems infos);
      traverseEither (visitSuperclass infos Nil) (M.keys infos);
      Right Unit
    };
  visitSuperclass :: Map String Info -> List String -> String -> Either String Unit;
  visitSuperclass infos seen name =
    if elem eqString name seen
    then Left ("cyclic superclass hierarchy: " ++ name)
    else do {
           boundValueShared7 <- lookupInfo infos name;
           case boundValueShared7 of {
             Info declaration _ _ _ _ ->
               do {
                 traverseEither (\(SPredicate c _) -> visitSuperclass infos (Cons name seen) c)
                   (superclasses declaration);
                 Right Unit
               }
           }
         };
  dictionaryDecl :: Map String Info -> Info -> Either String DataDecl;
  dictionaryDecl infos (Info declaration name ctor _ _) =
    do {
      supers <- traverseEither (dictionary infos) (superclasses declaration);
      fields <- traverseEither field (append supers (map snd (classMethods declaration)));
      Right (DataDeclK name (classParameters declaration) (Cons (ConstructorDecl ctor fields) Nil))
    };
  selectorDefinitions :: Map String Info -> Info -> Fresh (List (Triple String SAnnotation SExpr));
  selectorDefinitions infos (Info declaration dict ctor methods supers) =
    do {
      superTypes <- freshLift (traverseEither (dictionary infos) (superclasses declaration));
      let {
        signatures =
          append (zip supers superTypes)
            (zip (map snd methods) (map snd (classMethods declaration)))
      };
      let {
        parameters = classParameters declaration
      };
      mapM
        (\(Pair selected (Pair name ty)) ->
           do {
             d <- freshName "dictionary";
             value <- freshName "methodValue";
             let {
               fields =
                 map (\i -> if (i == selected) then Just value else Nothing)
                   (range 0 (length signatures - 1))
             };
             let {
               rhs =
                 SLam d Nothing
                   (SCase (SVar d)
                      (Cons (SAlternative (SConstructorPattern ctor fields) (SVar value)) Nil))
             };
             let {
               signature =
                 quantify parameters
                   (SArrow (SCon dict (map (\(Pair n _) -> STVar n) parameters)) ty)
             };
             freshPure (Triple name (SAnnotation Nil signature) rhs)
           })
        (zip (range 0 (length signatures - 1)) signatures)
    };
  methodNames :: List String -> String;
  methodNames names =
    ("[" ++ (intercalate "," (map Pretty.prettyString (sortBy compareString names)) ++ "]"));
  validateInstance :: DataEnv -> Map String Info -> SInstanceDecl -> Either String SInstanceDecl;
  validateInstance ds infos inst =
    do {
      boundValueShared8 <- lookupInfo infos (instanceClass inst);
      case boundValueShared8 of {
        Info declaration _ _ _ _ ->
          do {
            unique "instance method" (map fst (instanceMethods inst));
            let {
              required = map fst (classMethods declaration)
            };
            let {
              supplied = map fst (instanceMethods inst)
            };
            ensure
              (null (Surface.without required supplied) && null (Surface.without supplied required))
              ("instance methods do not match class " ++
               (instanceClass inst ++
                ("; missing " ++
                 (methodNames (Surface.without required supplied) ++
                  ("; unexpected " ++ methodNames (Surface.without supplied required))))));
            unique "instance type variable" (map fst (instanceVariables inst));
            let {
              arguments = instanceHead inst
            };
            let {
              free = sortBy compareString (nubBy eqString (concatMap freeType arguments))
            };
            let {
              explicit = instanceVariables inst
            };
            let {
              vars =
                append explicit (map (\a -> Pair a Star) (Surface.without free (map fst explicit)))
            };
            let {
              scope = M.fromList compareString vars
            };
            ensure (null (Surface.without (map fst vars) free))
              "instance variables must occur in the instance head";
            checkPredicate ds infos scope (SPredicate (instanceClass inst) arguments);
            case arguments of {
              Cons (SCon _ _) Nil -> Right Unit;
              Cons _ Nil -> Left "instance head must start with a named type constructor";
              _ -> Right Unit
            };
            traverseEither (headType "") arguments;
            traverseEither
              (\predicate ->
                 case predicate of {
                   SPredicate _ args ->
                     do {
                       ensure (null (Surface.without (concatMap freeType args) free))
                         "instance context has a variable absent from the head";
                       checkPredicate ds infos scope predicate;
                       ensure
                         ((sumCounts (map typeSize args) < sumCounts (map typeSize arguments)) &&
                          all
                            (\a ->
                               (sumCounts (map (occurrences a) args) <=
                                sumCounts (map (occurrences a) arguments)))
                            free)
                         "instance context must be structurally smaller than its head"
                     }
                 })
              (instanceContext inst);
            Right
              (SInstanceDecl vars (instanceContext inst) (instanceClass inst) arguments
                 (instanceMethods inst))
          }
      }
    };
  headType :: String -> SType -> Either String InstanceHead;
  headType prefix ty =
    case ty of {
      STVar a -> Right (HVar (prefix ++ a));
      SCon c ts ->
        foldEither
          (\f a ->
             do {
               value <- headType prefix a;
               Right (HCon "@" (Cons f (Cons value Nil)))
             })
          (HCon c Nil)
          ts;
      STypeApp f a ->
        do {
          x <- headType prefix f;
          y <- headType prefix a;
          Right (HCon "@" (Cons x (Cons y Nil)))
        };
      SArrow a b ->
        do {
          x <- headType prefix a;
          y <- headType prefix b;
          Right (HCon "->" (Cons x (Cons y Nil)))
        };
      _ -> Left "instance heads must be monotypes"
    };
  checkOverlap :: List SInstanceDecl -> Either String Unit;
  checkOverlap instances =
    case instances of {
      Nil -> Right Unit;
      Cons a rest ->
        do {
          traverseEither
            (\b ->
               if not (eqString (instanceClass a) (instanceClass b))
               then Right Unit
               else do {
                      xs <- traverseEither (headType "left:") (instanceHead a);
                      ys <- traverseEither (headType "right:") (instanceHead b);
                      ensure (not (overlap M.empty (zip xs ys)))
                        ("overlapping instances for " ++ instanceClass a)
                    })
            rest;
          checkOverlap rest
        }
    };
  eqHead :: InstanceHead -> InstanceHead -> Bool;
  eqHead a b =
    case a of {
      HVar x ->
        case b of {
          HVar y -> eqString x y;
          _ -> False
        };
      HCon x xs ->
        case b of {
          HCon y ys -> (eqString x y && eqList eqHead xs ys);
          _ -> False
        }
    };
  walkHead :: Map String InstanceHead -> InstanceHead -> InstanceHead;
  walkHead substitution ty =
    case ty of {
      HVar a ->
        case M.lookup compareString a substitution of {
          Nothing -> ty;
          Just t -> walkHead substitution t
        };
      HCon c ts -> HCon c (map (walkHead substitution) ts)
    };
  occursHead :: String -> InstanceHead -> Bool;
  occursHead a ty =
    case ty of {
      HVar b -> eqString a b;
      HCon _ ts -> any (occursHead a) ts
    };
  overlap :: Map String InstanceHead -> List (Pair InstanceHead InstanceHead) -> Bool;
  overlap substitution equations =
    case equations of {
      Nil -> True;
      Cons (Pair x y) rest ->
        let {
          a = walkHead substitution x
        } in
        let {
          b = walkHead substitution y
        } in
        if eqHead a b
        then overlap substitution rest
        else case a of {
               HVar name ->
                 if occursHead name b
                 then False
                 else overlap (M.insert compareString name b substitution) rest;
               HCon c xs ->
                 case b of {
                   HVar name ->
                     if occursHead name a
                     then False
                     else overlap (M.insert compareString name a substitution) rest;
                   HCon d ys ->
                     (eqString c d &&
                      ((length xs == length ys) && overlap substitution (append (zip xs ys) rest)))
                 }
             }
    };
  -- Structural size and occurrence counts are total integer accumulations.
  -- Force each update so wide types do not leave a deferred arithmetic chain.
  sumCounts :: List Int -> Int;
  sumCounts counts = foldlStrict addInt 0 counts;
  typeSize :: SType -> Int;
  typeSize ty =
    case ty of {
      STVar _ -> 1;
      SCon _ xs -> (1 + sumCounts (map typeSize xs));
      STypeApp f a -> (typeSize f + typeSize a);
      SArrow a b -> ((1 + typeSize a) + typeSize b);
      _ -> 1
    };
  occurrences :: String -> SType -> Int;
  occurrences a ty =
    case ty of {
      STVar b -> if eqString a b then 1 else 0;
      SCon _ xs -> sumCounts (map (occurrences a) xs);
      STypeApp f x -> (occurrences a f + occurrences a x);
      SArrow x y -> (occurrences a x + occurrences a y);
      _ -> 0
    };
  lowerExpr :: Map String (List (Pair EvidenceRole String)) ->
               DataEnv ->
               Map String Info ->
               Map String (Pair String (List String)) ->
               List (Pair EvidenceRole String) ->
               SExpr -> Fresh (Pair SExpr (List (Pair String String)));
  lowerExpr valueScopes ds infos env candidates expression =
    case expression of {
      SVar x ->
        case M.lookup compareString x env of {
          Nothing -> freshPure (Pair expression Nil);
          Just (Pair name classes) ->
            do {
              wants <- wantedNames classes;
              freshPure (Pair (foldl SApp (SVar name) (map (\(Pair n _) -> SVar n) wants)) wants)
            }
        };
      SConstructor _ -> freshPure (Pair expression Nil);
      SIntLit _ -> freshPure (Pair expression Nil);
      SDoubleLit _ -> freshPure (Pair expression Nil);
      SBoolLit _ -> freshPure (Pair expression Nil);
      SStringLit _ -> freshPure (Pair expression Nil);
      SPrimitive _ -> freshPure (Pair expression Nil);
      SApp a b ->
        do {
          boundValueShared10 <-
            case a of {
              SAnn rhs (SAnnotation Nil ty) ->
                case scheme ty of {
                  Triple _ predicates _ ->
                    if null predicates
                    then lowerExpr valueScopes ds infos env candidates a
                    else do {
                           function <- signedIn valueScopes ds infos candidates env rhs ty;
                           wants <- wantedNames (map (\(SPredicate c _) -> c) predicates);
                           freshPure
                             (Pair (foldl SApp function (map (\(Pair n _) -> SVar n) wants)) wants)
                         }
                };
              _ -> lowerExpr valueScopes ds infos env candidates a
            };
          case boundValueShared10 of {
            Pair f as ->
              do {
                boundValueShared9 <- lowerExpr valueScopes ds infos env candidates b;
                case boundValueShared9 of {
                  Pair x bs ->
                    do {
                      freshPure (Pair (SApp f x) (append as bs))
                    }
                }
              }
          }
        };
      SLam x annotation body ->
        do {
          boundValueShared12 <-
            case annotation of {
              Nothing -> freshPure (Pair Nothing Nil);
              Just (SAnnotation existential ty) ->
                do {
                  translated <-
                    if null existential
                    then freshLift (translateScheme ds infos ty)
                    else freshPure ty;
                  let {
                    predicates =
                      case scheme ty of {
                        Triple _ ps _ -> ps
                      }
                  };
                  freshPure
                    (Pair (Just (SAnnotation existential translated))
                       (map (\(SPredicate c _) -> c) predicates))
                }
            };
          case boundValueShared12 of {
            Pair annotation2 classes ->
              do {
                boundValueShared11 <-
                  lowerExpr valueScopes ds infos (M.insert compareString x (Pair x classes) env)
                    candidates
                    body;
                case boundValueShared11 of {
                  Pair body2 wants ->
                    do {
                      freshPure (Pair (SLam x annotation2 body2) wants)
                    }
                }
              }
          }
        };
      SLet x (SAnn rhs (SAnnotation Nil ty)) body ->
        do {
          rhs2 <-
            signedIn valueScopes ds infos (M.findWithDefault compareString candidates x valueScopes)
              env
              rhs
              ty;
          let {
            predicates =
              case scheme ty of {
                Triple _ ps _ -> ps
              }
          };
          boundValueShared13 <-
            lowerExpr valueScopes ds infos
              (M.insert compareString x (Pair x (map (\(SPredicate c _) -> c) predicates)) env)
              candidates
              body;
          case boundValueShared13 of {
            Pair body2 wants ->
              do {
                freshPure (Pair (SLet x rhs2 body2) wants)
              }
          }
        };
      SLet x rhs body ->
        do {
          boundValueShared15 <-
            lowerExpr valueScopes ds infos env
              (M.findWithDefault compareString candidates x valueScopes)
              rhs;
          case boundValueShared15 of {
            Pair rhs2 wanted ->
              do {
                boundValueShared14 <-
                  lowerExpr valueScopes ds infos
                    (M.insert compareString x (Pair x (map snd wanted)) env)
                    candidates
                    body;
                case boundValueShared14 of {
                  Pair body2 wants ->
                    do {
                      freshPure
                        (Pair (SLet x (foldr (\(Pair n _) b -> SLam n Nothing b) rhs2 wanted) body2)
                           wants)
                    }
                }
              }
          }
        };
      SAnn a (SAnnotation existential ty) ->
        let {
          predicates =
            case scheme ty of {
              Triple _ ps _ -> ps
            }
        } in
        if not (null predicates)
        then do {
               freshLift
                 (ensure (null existential) "qualified annotations cannot bind existentials");
               result <- signedIn valueScopes ds infos candidates env a ty;
               freshPure (Pair result Nil)
             }
        else do {
               boundValueShared16 <- lowerExpr valueScopes ds infos env candidates a;
               case boundValueShared16 of {
                 Pair a2 wants ->
                   do {
                     translated <-
                       if null existential
                       then freshLift (translateScheme ds infos ty)
                       else freshPure ty;
                     freshPure (Pair (SAnn a2 (SAnnotation existential translated)) wants)
                   }
               }
             };
      SCase a branches ->
        do {
          boundValueShared18 <- lowerExpr valueScopes ds infos env candidates a;
          case boundValueShared18 of {
            Pair a2 as ->
              do {
                bs <-
                  mapM
                    (\(SAlternative pattern body) ->
                       do {
                         let {
                           names = Surface.patternVariables pattern
                         };
                         let {
                           scope = foldr (\n -> M.insert compareString n (Pair n Nil)) env names
                         };
                         boundValueShared17 <- lowerExpr valueScopes ds infos scope candidates body;
                         case boundValueShared17 of {
                           Pair body2 wants ->
                             do {
                               freshPure (Pair (SAlternative pattern body2) wants)
                             }
                         }
                       })
                    branches;
                freshPure (Pair (SCase a2 (map fst bs)) (append as (concatMap snd bs)))
              }
          }
        };
      SDo _ _ -> lowerExpr valueScopes ds infos env candidates (Desugar.desugarDo expression);
      SLetRec definitions body ->
        do {
          signatures <-
            freshLift
              (traverseEither
                 (\(Triple n annotation rhs) ->
                    case annotation of {
                      SAnnotation Nil ty -> Right (Triple n ty rhs);
                      _ ->
                        Left
                          ("recursive definition " ++
                           (n ++ " requires an explicit closed signature"))
                    })
                 definitions);
          let {
            entries =
              map
                (\(Triple n ty _) ->
                   case scheme ty of {
                     Triple _ predicates _ ->
                       Pair n (Pair n (map (\(SPredicate c _) -> c) predicates))
                   })
                signatures
          };
          let {
            scope = M.union compareString (M.fromList compareString entries) env
          };
          definitions2 <-
            mapM
              (\(Triple n ty rhs) ->
                 do {
                   translated <- freshLift (translateScheme ds infos ty);
                   rhs2 <-
                     signedIn valueScopes ds infos
                       (M.findWithDefault compareString candidates n valueScopes)
                       scope
                       rhs
                       ty;
                   freshPure (Triple n (SAnnotation Nil translated) rhs2)
                 })
              signatures;
          boundValueShared19 <- lowerExpr valueScopes ds infos scope candidates body;
          case boundValueShared19 of {
            Pair body2 wants ->
              do {
                freshPure (Pair (SLetRec definitions2 body2) wants)
              }
          }
        };
      SEquations _ -> freshFail "surface equations escaped lowering";
      SWanted _ _ -> freshFail "dictionary holes are reserved for dictionary translation";
      SChecked _ _ -> freshFail "checked source forms are reserved for dictionary translation"
    };
  wantedNames :: List String -> Fresh (List (Pair String String));
  wantedNames classes =
    mapM
      (\c ->
         do {
           name <- freshName "wantedDictionary";
           freshPure (Pair name c)
         })
      classes;
  signedIn :: Map String (List (Pair EvidenceRole String)) ->
              DataEnv ->
              Map String Info ->
              List (Pair EvidenceRole String) ->
              Map String (Pair String (List String)) -> SExpr -> SType -> Fresh SExpr;
  signedIn valueScopes ds infos available scope expression ty =
    do {
      translated <- freshLift (translateScheme ds infos ty);
      let {
        predicates =
          case scheme ty of {
            Triple _ ps _ -> ps
          }
      };
      names <- mapM (\p -> freshName "givenDictionary") predicates;
      let {
        local = append (map (\n -> Pair GivenEvidence n) names) available
      };
      boundValueShared20 <- lowerExpr valueScopes ds infos scope local expression;
      case boundValueShared20 of {
        Pair body wants ->
          do {
            let {
              closed = closeWants infos local wants body
            };
            freshPure (SChecked translated (foldr (\n b -> SLam n Nothing b) closed names))
          }
      }
    };
  closeWants :: Map String Info ->
                List (Pair EvidenceRole String) -> List (Pair String String) -> SExpr -> SExpr;
  closeWants infos candidates wants expression =
    let {
      replacements =
        M.fromList compareString
          (concatMap
             (\(Pair n c) ->
                case M.lookup compareString c infos of {
                  Nothing -> Nil;
                  Just (Info _ dict _ _ _) -> Cons (Pair n dict) Nil
                })
             wants)
    } in
    closeWanted replacements candidates expression;
  closeWanted :: Map String String -> List (Pair EvidenceRole String) -> SExpr -> SExpr;
  closeWanted replacements candidates expression =
    case expression of {
      SVar n ->
        case M.lookup compareString n replacements of {
          Nothing -> expression;
          Just d -> SWanted d candidates
        };
      SLam n a b -> SLam n a (closeWanted replacements candidates b);
      SApp a b ->
        SApp (closeWanted replacements candidates a) (closeWanted replacements candidates b);
      SLet n a b ->
        SLet n (closeWanted replacements candidates a) (closeWanted replacements candidates b);
      SAnn a ty -> SAnn (closeWanted replacements candidates a) ty;
      SCase a branches ->
        SCase (closeWanted replacements candidates a)
          (map (\(SAlternative p b) -> SAlternative p (closeWanted replacements candidates b))
             branches);
      SChecked ty a -> SChecked ty (closeWanted replacements candidates a);
      SLetRec definitions body ->
        SLetRec
          (map (\(Triple n t a) -> Triple n t (closeWanted replacements candidates a)) definitions)
          (closeWanted replacements candidates body);
      _ -> expression
    };
  instantiateMethod :: Map String SType -> SType -> Fresh SType;
  instantiateMethod arguments ty =
    case ty of {
      STVar n -> freshPure (M.findWithDefault compareString ty n arguments);
      SForall flag n bound body ->
        do {
          fresh <-
            freshAvoid "methodType"
              (append (concatMap typeNames (M.elems arguments)) (typeNames ty));
          bound2 <- instantiateMethod arguments bound;
          body2 <- instantiateMethod arguments (substitute n (STVar fresh) body);
          freshPure (SForall flag fresh bound2 body2)
        };
      SArrow a b ->
        do {
          x <- instantiateMethod arguments a;
          y <- instantiateMethod arguments b;
          freshPure (SArrow x y)
        };
      STypeApp f a ->
        do {
          x <- instantiateMethod arguments f;
          y <- instantiateMethod arguments a;
          freshPure (STypeApp x y)
        };
      SCon c types ->
        do {
          ts <- mapM (instantiateMethod arguments) types;
          freshPure (SCon c ts)
        };
      _ -> freshPure ty
    };
  freshAvoid :: String -> List String -> Fresh String;
  freshAvoid prefix forbidden =
    do {
      name <- freshName prefix;
      if elem eqString name forbidden then freshAvoid prefix forbidden else freshPure name
    };
  substitute :: String -> SType -> SType -> SType;
  substitute name replacement ty =
    case ty of {
      STVar a -> if eqString name a then replacement else ty;
      SForall flag a bound body ->
        SForall flag a (substitute name replacement bound)
          (if eqString a name then body else substitute name replacement body);
      SArrow a b -> SArrow (substitute name replacement a) (substitute name replacement b);
      STypeApp f a -> STypeApp (substitute name replacement f) (substitute name replacement a);
      SCon c types -> SCon c (map (substitute name replacement) types);
      _ -> ty
    };
  prettyQualified :: Map String String -> XType -> String;
  prettyQualified names ty =
    case ty of {
      XForall a bound body ->
        ("forall " ++ (prettyBinder a bound ++ (". " ++ prettyQualified names body)));
      _ ->
        case constraints names ty of {
          Pair Nil _ -> Pretty.prettyType ty;
          Pair predicates body ->
            ((if (length predicates == 1)
              then head predicates
              else ("(" ++ (intercalate ", " predicates ++ ")"))) ++
             (" => " ++ prettyQualified names body))
        }
    };
  prettyBinder :: XTyVar -> XType -> String;
  prettyBinder a bound =
    case bound of {
      XBot -> Pretty.prettyType (XVar a);
      XBotKind kind ->
        ("(" ++ (Pretty.prettyType (XVar a) ++ (" : " ++ (prettyKindLocal kind ++ ")"))));
      _ -> ("(" ++ (Pretty.prettyType (XVar a) ++ (" >= " ++ (Pretty.prettyType bound ++ ")"))))
    };
  prettyKindLocal :: Kind -> String;
  prettyKindLocal kind =
    case kind of {
      Star -> "*";
      KArrow a b ->
        ((case a of {
            Star -> "*";
            _ -> ("(" ++ (prettyKindLocal a ++ ")"))
          }) ++
         (" -> " ++ prettyKindLocal b))
    };
  constraints :: Map String String -> XType -> Pair (List String) XType;
  constraints names ty =
    case ty of {
      XArrow (XCon dictionary args) body ->
        case M.lookup compareString dictionary names of {
          Nothing -> Pair Nil ty;
          Just name ->
            case constraints names body of {
              Pair predicates result ->
                Pair (Cons (unwords (Cons name (map prettyArgument args))) predicates) result
            }
        };
      _ -> Pair Nil ty
    };
  prettyArgument :: XType -> String;
  prettyArgument ty =
    case ty of {
      XVar _ -> Pretty.prettyType ty;
      XCon _ Nil -> Pretty.prettyType ty;
      _ -> ("(" ++ (Pretty.prettyType ty ++ ")"))
    }
}
