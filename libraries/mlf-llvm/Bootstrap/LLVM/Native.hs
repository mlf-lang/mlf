-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.Native where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.LLVM.Build;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Primitive as P;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.LLVM.Analysis as A;
  import qualified Bootstrap.LLVM.Kernel as K;
  import qualified Bootstrap.LLVM.Optimize as O;
  data TableUpdate = TableUpdate XName XErased XErased XErased XName XErased;
  boxed :: Scalar -> Build String;
  boxed value =
    case value of {
      Boxed v -> cgPure v;
      Floating v -> call "@mlf_double" (args1 ("double " ++ v))
    };
  floating :: Scalar -> Build String;
  floating value =
    case value of {
      Floating v -> cgPure v;
      Boxed v ->
        do {
          old <- gets (\state -> M.lookup compareString v (unboxedDoubles state));
          case old of {
            Just x -> cgPure x;
            Nothing ->
              do {
                x <- loadAt "double" v 8;
                modify
                  (\state ->
                     withUnboxedDoubles (M.insert compareString v x (unboxedDoubles state)) state);
                cgPure x
              }
          }
        }
    };
  scalarArgument :: Scalar -> String;
  scalarArgument value =
    case value of {
      Floating v -> ("double " ++ v);
      Boxed v -> pointer v
    };
  isFloating :: Scalar -> Bool;
  isFloating value =
    case value of {
      Floating v -> True;
      Boxed v -> False
    };
  invokeKernel :: XName -> A.WorkerFunction -> List Scalar -> Build String;
  invokeKernel name f arguments =
    do {
      invocation <- kernelCall name f arguments;
      case invocation of {
        Pair code values -> call code (L.map scalarArgument values)
      }
    };
  promoteDouble :: Map String String -> Scalar -> Scalar;
  promoteDouble doubles value =
    case value of {
      Floating x -> value;
      Boxed x ->
        case M.lookup compareString x doubles of {
          Just number -> Floating number;
          Nothing -> value
        }
    };
  boundedScalar :: Map String (Pair Int Int) -> Int -> Scalar -> Bool;
  boundedScalar facts limit value =
    case value of {
      Floating x -> False;
      Boxed x ->
        case M.lookup compareString x facts of {
          Nothing -> False;
          Just (Pair lo hi) -> ((lo >= 0) && (hi < limit))
        }
    };
  requestedMode :: Map String (Pair Int Int) ->
                   Set XName -> Set XName -> Bool -> XName -> Scalar -> NativeMode;
  requestedMode facts counters indices narrow name value =
    case value of {
      Floating v -> UnboxedDouble;
      Boxed v ->
        if (narrow && S.member O.compareName name indices)
        then SmallIndex
        else if (S.member O.compareName name counters &&
                 boundedScalar facts 4611686018427387904 value)
             then NonnegativeInt
             else General
    };
  specialized :: List NativeMode -> Bool;
  specialized modes = L.any (\mode -> (modeCode mode /= 0)) modes;
  variantCount :: XName -> Set (Pair XName (List NativeMode)) -> Int;
  variantCount name variants =
    L.length
      (L.filter
         (\entry ->
            case entry of {
              Pair n modes -> (O.eqName n name && specialized modes)
            })
         (S.toList variants));
  kernelCall :: XName -> A.WorkerFunction -> List Scalar -> Build (Pair String (List Scalar));
  kernelCall name f arguments =
    do {
      facts <- gets scalarRanges;
      doubles <- gets unboxedDoubles;
      let {
        values = L.map (promoteDouble doubles) arguments
      };
      let {
        counters = zeroTested (A.functionBody f)
      };
      let {
        indices = integerParameters (A.functionBody f)
      };
      collects <- gets (\state -> S.member O.compareName name (collectingKernels state));
      let {
        narrow =
          (L.not collects &&
           (indexLoop (A.functionBody f) &&
            L.all
              (\entry ->
                 case entry of {
                   Pair n v ->
                     if S.member O.compareName n indices
                     then boundedScalar facts 2147483648 v
                     else True
                 })
              (L.zip (L.append (A.captures f) (A.parameters f)) values)))
      };
      let {
        requested =
          L.zipWith (requestedMode facts counters indices narrow)
            (L.append (A.captures f) (A.parameters f))
            values
      };
      variants <- gets kernelWorkers;
      let {
        overflow =
          (specialized requested &&
           (L.not (S.member compareKernel (Pair name requested) variants) &&
            (variantCount name variants >= 8)))
      };
      actual <-
        if overflow
        then L.mapM
               (\value ->
                  do {
                    pointer <- boxed value;
                    cgPure (Boxed pointer)
                  })
               values
        else cgPure values;
      code <-
        kernelWorker name f (if overflow then L.replicate (L.length values) General else requested);
      cgPure (Pair code actual)
    };
  zeroTested :: XErased -> Set XName;
  zeroTested expression =
    case O.applications expression of {
      Pair (XEPrimitive PEqInt) (Cons (XEVar n) (Cons (XEInt zero) Nil)) ->
        if (zero == 0) then S.singleton n else zeroTestedChildren expression;
      Pair (XEPrimitive PEqInt) (Cons (XEInt zero) (Cons (XEVar n) Nil)) ->
        if (zero == 0) then S.singleton n else zeroTestedChildren expression;
      _ -> zeroTestedChildren expression
    };
  zeroTestedChildren :: XErased -> Set XName;
  zeroTestedChildren expression =
    case expression of {
      XEAbs n b -> zeroTested b;
      XEApp a b -> S.union O.compareName (zeroTested a) (zeroTested b);
      XELet n a b -> S.union O.compareName (zeroTested a) (zeroTested b);
      XELetRec ds b -> zeroTested b;
      _ -> S.empty
    };
  integerPositions :: Primitive -> List Int;
  integerPositions p =
    case p of {
      PAddInt -> args2 0 1;
      PSubInt -> args2 0 1;
      PMulInt -> args2 0 1;
      PQuotInt -> args2 0 1;
      PRemInt -> args2 0 1;
      PAndInt -> args2 0 1;
      PEqInt -> args2 0 1;
      PLtInt -> args2 0 1;
      PNewIntArray -> args2 0 1;
      PNewByteArray -> args2 0 1;
      PIntToDouble -> args1 0;
      PNewDoubleArray -> args1 0;
      PReadIntArray -> args1 1;
      PReadDoubleArray -> args1 1;
      PReadByteArray -> args1 1;
      PReadIntTable -> args1 1;
      PWriteDoubleArray -> args1 1;
      PWriteIntArray -> args2 1 2;
      PWriteByteArray -> args2 1 2;
      PWriteIntTable -> args2 1 2;
      PPutBytes -> args2 1 2;
      _ -> Nil
    };
  integerParameters :: XErased -> Set XName;
  integerParameters expression =
    let {
      direct =
        case O.applications expression of {
          Pair (XEPrimitive p) args ->
            S.fromList O.compareName
              (L.concatMap
                 (\entry ->
                    case entry of {
                      Pair index value ->
                        case value of {
                          XEVar name ->
                            if L.elem eqInt index (integerPositions p) then args1 name else Nil;
                          _ -> Nil
                        }
                    })
                 (L.zip (L.range 0 (L.length args - 1)) args));
          _ -> S.empty
        }
    } in
    S.union O.compareName direct
      (case expression of {
         XEAbs n b -> integerParameters b;
         XEApp a b -> S.union O.compareName (integerParameters a) (integerParameters b);
         XELet n a b -> S.union O.compareName (integerParameters a) (integerParameters b);
         XELetRec ds b -> integerParameters b;
         _ -> S.empty
       });
  primitives :: XErased -> List Primitive;
  primitives expression =
    case expression of {
      XEPrimitive p -> args1 p;
      XEAbs n b -> primitives b;
      XEApp a b -> L.append (primitives a) (primitives b);
      XELet n a b -> L.append (primitives a) (primitives b);
      XELetRec ds b -> primitives b;
      _ -> Nil
    };
  indexOperation :: Primitive -> Bool;
  indexOperation p =
    case p of {
      PReadByteArray -> True;
      PWriteByteArray -> True;
      PReadIntArray -> True;
      PWriteIntArray -> True;
      _ -> False
    };
  nonIndexOperation :: Primitive -> Bool;
  nonIndexOperation p =
    case p of {
      PReadIntTable -> True;
      PWriteIntTable -> True;
      PAddDouble -> True;
      PSubDouble -> True;
      PMulDouble -> True;
      PDivDouble -> True;
      PSqrtDouble -> True;
      PIntToDouble -> True;
      PReadDoubleArray -> True;
      PWriteDoubleArray -> True;
      _ -> False
    };
  indexLoop :: XErased -> Bool;
  indexLoop expression =
    let {
      operations = primitives expression
    } in
    (L.any indexOperation operations && L.not (L.any nonIndexOperation operations));
  modeSuffix :: NativeMode -> String;
  modeSuffix mode =
    case mode of {
      General -> "p";
      UnboxedDouble -> "d";
      NonnegativeInt -> "n";
      SmallIndex -> "i"
    };
  registerScalar :: NativeMode -> String -> Scalar;
  registerScalar mode register = if (modeCode mode == 1) then Floating register else Boxed register;
  kernelWorker :: XName -> A.WorkerFunction -> List NativeMode -> Build String;
  kernelWorker name f modes =
    do {
      let {
        symbol =
          ("@mlf.numeric." ++
           (showInt (O.nameId name) ++
            (if specialized modes then ("." ++ L.concatStrings (L.map modeSuffix modes)) else "")))
      };
      let {
        names = L.append (A.captures f) (A.parameters f)
      };
      let {
        registers = L.map (\i -> ("%a" ++ showInt i)) (L.range 0 (L.length names - 1))
      };
      let {
        key = Pair name modes
      };
      seen <- gets (\state -> S.member compareKernel key (kernelWorkers state));
      if seen
      then cgPure Unit
      else do {
             modify
               (\state ->
                  withKernelWorkers (S.insert compareKernel key (kernelWorkers state)) state);
             let {
               values = L.zipWith registerScalar modes registers
             };
             definitionBody symbol (L.map scalarArgument values)
               (kernelWorkerBody name f modes names registers values)
           };
      cgPure symbol
    };
  kernelWorkerBody :: XName ->
                      A.WorkerFunction ->
                      List NativeMode -> List XName -> List String -> List Scalar -> Build Unit;
  kernelWorkerBody name f modes names registers values =
    do {
      collects <- gets (\state -> S.member O.compareName name (collectingKernels state));
      if collects
      then do {
             let {
               roots =
                 L.concatMap
                   (\entry ->
                      case entry of {
                        Pair mode register -> if (modeCode mode == 1) then Nil else args1 register
                      })
                   (L.zip modes registers)
             };
             slots <- rootSlots roots;
             emit
               ("  call void @mlf_gc_check(" ++
                (number (L.length roots) ++ (", ptr " ++ (slots ++ ")"))))
           }
      else cgPure Unit;
      L.mapM_
        (\entry ->
           case entry of {
             Pair mode register ->
               case mode of {
                 NonnegativeInt -> recordRange register (Pair 0 4611686018427387903);
                 SmallIndex -> recordRange register (Pair 0 2147483647);
                 _ -> cgPure Unit
               }
           })
        (L.zip modes registers);
      let {
        scope = M.fromList O.compareName (L.zip names values)
      };
      let {
        integers = integerParameters (A.functionBody f)
      };
      let {
        narrow =
          L.concatMap
            (\entry ->
               case entry of {
                 Pair index (Pair name mode) ->
                   if (S.member O.compareName name integers &&
                       ((modeCode mode == 0) || (modeCode mode == 2)))
                   then args1 index
                   else Nil
               })
            (L.zip (L.range 0 (L.length names - 1)) (L.zip names modes))
      };
      let {
        narrowed =
          L.map
            (\entry ->
               case entry of {
                 Pair index mode -> if L.elem eqInt index narrow then SmallIndex else mode
               })
            (L.zip (L.range 0 (L.length modes - 1)) modes)
      };
      let {
        ordinary = executeNumericReturn modes scope (A.functionBody f)
      };
      let {
        copy = K.byteCopy name f
      };
      let {
        body =
          case copy of {
            Just ns -> copyBytesReturn scope ns ordinary;
            Nothing -> ordinary
          }
      };
      variants <- gets kernelWorkers;
      let {
        allowed =
          (S.member compareKernel (Pair name narrowed) variants || (variantCount name variants < 8))
      };
      if (L.isJust copy ||
          (collects || (L.not (indexLoop (A.functionBody f)) || (L.null narrow || L.not allowed))))
      then body
      else do {
             tests <-
               L.mapM
                 (\index ->
                    do {
                      bits <- result ("ptrtoint ptr " ++ (L.index registers index ++ " to i64"));
                      low <- result ("and i64 " ++ (bits ++ ", 1"));
                      tag <- result ("icmp ne i64 " ++ (low ++ ", 0"));
                      range <- result ("icmp ult i64 " ++ (bits ++ ", 4294967296"));
                      result ("and i1 " ++ (tag ++ (", " ++ range)))
                    })
                 narrow;
             ready <- L.foldM (\a b -> result ("and i1 " ++ (a ++ (", " ++ b)))) "true" tests;
             fast <- fresh "range.fast.";
             slow <- fresh "range.general.";
             emit ("  br i1 " ++ (ready ++ (", label %" ++ (fast ++ (", label %" ++ slow)))));
             label fast;
             code <- kernelWorker name f narrowed;
             value <-
               result
                 ("musttail call ptr " ++
                  (code ++ ("(" ++ (L.intercalate ", " (L.map scalarArgument values) ++ ")"))));
             emit ("  ret ptr " ++ value);
             label slow;
             body
           }
    };
  numericValue :: Map XName Scalar -> XName -> Build Scalar;
  numericValue scope name =
    case M.lookup O.compareName name scope of {
      Just value -> cgPure value;
      Nothing -> failure ("LLVM numeric region unbound identity: " ++ showInt (O.nameId name))
    };
  numericBoxed :: Map XName Scalar -> XName -> Build String;
  numericBoxed scope name =
    do {
      value <- numericValue scope name;
      boxed value
    };
  rootSlots :: List String -> Build String;
  rootSlots roots =
    if L.null roots
    then cgPure "null"
    else do {
           slots <- result ("alloca [" ++ (showInt (L.length roots) ++ " x ptr], align 8"));
           L.mapM_
             (\entry ->
                case entry of {
                  Pair i value ->
                    do {
                      slot <-
                        result ("getelementptr ptr, ptr " ++ (slots ++ (", i64 " ++ showInt i)));
                      emit ("  store ptr " ++ (value ++ (", ptr " ++ (slot ++ ", align 8"))))
                    }
                })
             (L.zip (L.range 0 (L.length roots - 1)) roots);
           cgPure slots
         };
  withNumericRoots :: forall a. XName -> Map XName Scalar -> Build a -> Build a;
  withNumericRoots name scope action =
    do {
      collects <- gets (\state -> S.member O.compareName name (collectingKernels state));
      if L.not collects
      then action
      else do {
             let {
               roots =
                 S.toList
                   (S.fromList compareString
                      (L.concatMap
                         (\scalar ->
                            case scalar of {
                              Boxed v -> args1 v;
                              Floating v -> Nil
                            })
                         (M.elems scope)))
             };
             slots <- rootSlots roots;
             frame <- result "alloca [3 x ptr], align 8";
             emit
               ("  call void @mlf_roots_enter(ptr " ++
                (frame ++ (", " ++ (number (L.length roots) ++ (", ptr " ++ (slots ++ ")"))))));
             value <- action;
             emit ("  call void @mlf_roots_leave(ptr " ++ (frame ++ ")"));
             cgPure value
           }
    };
  numericCondition :: Scalar -> Build String;
  numericCondition value =
    do {
      pointer <- boxed value;
      result ("icmp eq ptr " ++ (pointer ++ (", " ++ immediate 6)))
    };
  numericChoose :: String -> Build Scalar -> Build Scalar -> Build Scalar;
  numericChoose condition yes no =
    do {
      value <-
        choose "ptr" condition
          (do {
             value <- yes;
             boxed value
           })
          (do {
             value <- no;
             boxed value
           });
      cgPure (Boxed value)
    };
  numericBranch :: Map XName Scalar -> XErased -> Build Scalar -> Build Scalar -> Build Scalar;
  numericBranch scope expression yes no =
    do {
      value <- scalarValue scope expression;
      condition <- numericCondition value;
      numericChoose condition
        (do {
           refineNumeric scope expression True;
           yes
         })
        (do {
           refineNumeric scope expression False;
           no
         })
    };
  numericReference :: Map XName Scalar -> XErased -> Maybe String;
  numericReference scope expression =
    case expression of {
      XEVar n ->
        case M.lookup O.compareName n scope of {
          Just (Boxed v) -> Just v;
          _ -> Nothing
        };
      XEInt n ->
        if ((n >= (0 - 4611686018427387904)) && (n < 4611686018427387904))
        then Just (immediate ((n * 2) + 1))
        else Nothing;
      _ -> Nothing
    };
  validRange :: Pair Int Int -> Bool;
  validRange (Pair lo hi) = (lo <= hi);
  refineEndpoint :: Map XName Scalar -> Bool -> XName -> Int -> Build Unit;
  refineEndpoint scope truth name k =
    case M.lookup O.compareName name scope of {
      Just (Boxed v) ->
        do {
          bounds <- gets (\state -> M.lookup compareString v (scalarRanges state));
          case bounds of {
            Just (Pair lo hi) ->
              do {
                let {
                  next =
                    if truth
                    then Pair (L.max lo k) (L.min hi k)
                    else if (k == lo)
                         then Pair (lo + 1) hi
                         else if (k == hi) then Pair lo (hi - 1) else Pair lo hi
                };
                if validRange next then recordRange v next else cgPure Unit
              };
            Nothing -> cgPure Unit
          }
        };
      _ -> cgPure Unit
    };
  refineNumeric :: Map XName Scalar -> XErased -> Bool -> Build Unit;
  refineNumeric scope expression truth =
    case O.applications expression of {
      Pair (XEPrimitive PEqInt) (Cons (XEVar n) (Cons (XEInt k) Nil)) ->
        refineEndpoint scope truth n k;
      Pair (XEPrimitive PEqInt) (Cons (XEInt k) (Cons (XEVar n) Nil)) ->
        refineEndpoint scope truth n k;
      Pair (XEPrimitive PLtInt) (Cons a (Cons b Nil)) ->
        case numericReference scope a of {
          Nothing -> cgPure Unit;
          Just x ->
            case numericReference scope b of {
              Nothing -> cgPure Unit;
              Just y ->
                do {
                  facts <- gets scalarRanges;
                  case M.lookup compareString x facts of {
                    Nothing -> cgPure Unit;
                    Just (Pair lo hi) ->
                      case M.lookup compareString y facts of {
                        Nothing -> cgPure Unit;
                        Just (Pair lo2 hi2) ->
                          do {
                            let {
                              xs =
                                if truth
                                then Pair lo (L.min hi (hi2 - 1))
                                else Pair (L.max lo lo2) hi
                            };
                            let {
                              ys =
                                if truth
                                then Pair (L.max lo2 (lo + 1)) hi2
                                else Pair lo2 (L.min hi2 hi)
                            };
                            if validRange xs then recordRange x xs else cgPure Unit;
                            if validRange ys then recordRange y ys else cgPure Unit
                          }
                      }
                  }
                }
            }
        };
      _ -> cgPure Unit
    };
  executeNumericReturn :: List NativeMode -> Map XName Scalar -> XErased -> Build Unit;
  executeNumericReturn modes scope expression =
    case tableUpdate expression of {
      Just update ->
        do {
          next <- executeTableUpdate scope update;
          case next of {
            Pair local rest -> executeNumericReturn modes local rest
          }
        };
      Nothing ->
        case expression of {
          XELet n a b ->
            do {
              value <- scalarValue scope a;
              executeNumericReturn modes (M.insert O.compareName n value scope) b
            };
          XELetRec ds b -> executeNumericReturn modes scope b;
          _ -> executeNumericReturnApplication modes scope expression
        }
    };
  executeNumericReturnApplication :: List NativeMode -> Map XName Scalar -> XErased -> Build Unit;
  executeNumericReturnApplication modes scope expression =
    case O.applications expression of {
      Pair (XEPrimitive PIOBind) (Cons a (Cons (XEAbs n b) Nil)) ->
        do {
          value <- executeNumeric scope a;
          executeNumericReturn modes (M.insert O.compareName n value scope) b
        };
      Pair (XEPrimitive PIfThenElse) (Cons c (Cons a (Cons b Nil))) ->
        do {
          value <- scalarValue scope c;
          condition <- numericCondition value;
          before <- get;
          yes <- fresh "tail.yes.";
          no <- fresh "tail.no.";
          emit ("  br i1 " ++ (condition ++ (", label %" ++ (yes ++ (", label %" ++ no)))));
          label yes;
          refineNumeric scope c True;
          executeNumericReturn modes scope a;
          modify
            (\state ->
               withScalarRanges (scalarRanges before)
                 (withArrayViews (arrayViews before)
                    (withUnboxedDoubles (unboxedDoubles before)
                       (withForcedValues (forcedValues before) state))));
          label no;
          refineNumeric scope c False;
          executeNumericReturn modes scope b
        };
      Pair (XEVar name) args ->
        do {
          fs <- gets functions;
          case M.lookup O.compareName name fs of {
            Nothing -> failure "LLVM missing numeric tail function";
            Just f ->
              do {
                captured <- L.mapM (numericValue scope) (A.captures f);
                values <- L.mapM (scalarValue scope) args;
                invocation <- kernelCall name f (L.append captured values);
                case invocation of {
                  Pair code actual ->
                    do {
                      let {
                        marker =
                          if L.eqList equalBool (L.map (\mode -> (modeCode mode == 1)) modes)
                               (L.map isFloating actual)
                          then "musttail "
                          else ""
                      };
                      value <-
                        result
                          (marker ++
                           ("call ptr " ++
                            (code ++
                             ("(" ++ (L.intercalate ", " (L.map scalarArgument actual) ++ ")")))));
                      emit ("  ret ptr " ++ value)
                    }
                }
              }
          }
        };
      _ ->
        do {
          value <- executeNumeric scope expression;
          pointer <- boxed value;
          emit ("  ret ptr " ++ pointer)
        }
    };
  equalBool :: Bool -> Bool -> Bool;
  equalBool a b = if a then b else L.not b;
  scalarValue :: Map XName Scalar -> XErased -> Build Scalar;
  scalarValue scope expression =
    case expression of {
      XEVar n -> numericValue scope n;
      XEInt n ->
        do {
          value <- literalInteger n;
          if ((n >= (0 - 4611686018427387904)) && (n < 4611686018427387904))
          then recordRange value (Pair n n)
          else cgPure Unit;
          cgPure (Boxed value)
        };
      XEDouble n -> cgPure (Floating (doubleLiteral n));
      XELet n a b ->
        do {
          value <- scalarValue scope a;
          scalarValue (M.insert O.compareName n value scope) b
        };
      _ -> scalarApplication scope expression
    };
  scalarApplication :: Map XName Scalar -> XErased -> Build Scalar;
  scalarApplication scope expression =
    case O.applications expression of {
      Pair (XEPrimitive PAddInt) (Cons a (Cons b Nil)) ->
        if isZero b
        then scalarValue scope a
        else if isZero a then scalarValue scope b else scalarGeneralApplication scope expression;
      Pair (XEPrimitive PSubInt) (Cons a (Cons (XEInt zero) Nil)) ->
        if (zero == 0) then scalarValue scope a else scalarGeneralApplication scope expression;
      Pair (XEPrimitive PEqInt) (Cons (XEVar a) (Cons (XEVar b) Nil)) ->
        if O.eqName a b
        then cgPure (Boxed (immediate 6))
        else scalarGeneralApplication scope expression;
      _ -> scalarGeneralApplication scope expression
    };
  isZero :: XErased -> Bool;
  isZero expression =
    case expression of {
      XEInt n -> (n == 0);
      _ -> False
    };
  scalarGeneralApplication :: Map XName Scalar -> XErased -> Build Scalar;
  scalarGeneralApplication scope expression =
    case O.applications expression of {
      Pair (XEPrimitive PIfThenElse) (Cons c (Cons a (Cons b Nil))) ->
        numericBranch scope c (scalarValue scope a) (scalarValue scope b);
      Pair (XEPrimitive p) args ->
        do {
          values <- L.mapM (scalarValue scope) args;
          scalarPrimitive p values
        };
      Pair (XEVar n) args ->
        do {
          fs <- gets functions;
          case M.lookup O.compareName n fs of {
            Nothing -> failure "LLVM missing numeric function";
            Just f ->
              do {
                values <- L.mapM (scalarValue scope) args;
                scalarValue
                  (M.union O.compareName (M.fromList O.compareName (L.zip (A.parameters f) values))
                     scope)
                  (A.functionBody f)
              }
          }
        };
      Pair (XEConstructor c) args ->
        if L.null args
        then scalarAtom expression
        else do {
               values <- L.mapM (scalarBoxed scope) args;
               constructor <- lookupConstructor c;
               case constructor of {
                 Pair tag arity ->
                   do {
                     value <-
                       if (arity == L.length args)
                       then constructorValue tag values
                       else do {
                              initial <-
                                call "@mlf_constructor" (args2 (number tag) (number arity));
                              L.foldM
                                (\f a ->
                                   do {
                                     app <- call "@mlf_application" (args2 (pointer f) (pointer a));
                                     forceValue app
                                   })
                                initial
                                values
                            };
                     cgPure (Boxed value)
                   }
               }
             };
      _ -> scalarAtom expression
    };
  scalarBoxed :: Map XName Scalar -> XErased -> Build String;
  scalarBoxed scope expression =
    do {
      value <- scalarValue scope expression;
      boxed value
    };
  scalarAtom :: XErased -> Build Scalar;
  scalarAtom expression =
    case expression of {
      XEBool b -> cgPure (Boxed (immediate (if b then 6 else 2)));
      XEString text ->
        do {
          literal <- stringConstant text;
          value <- call "@mlf_string" (args2 (pointer (L.fst literal)) (number (L.snd literal)));
          cgPure (Boxed value)
        };
      XEConstructor c ->
        do {
          constructor <- lookupConstructor c;
          case constructor of {
            Pair tag arity ->
              if (arity == 0)
              then cgPure (Boxed (immediate ((tag * 8) + 4)))
              else do {
                     value <- call "@mlf_constructor" (args2 (number tag) (number arity));
                     cgPure (Boxed value)
                   }
          }
        };
      XEInt n ->
        do {
          value <- literalInteger n;
          cgPure (Boxed value)
        };
      XEDouble n -> cgPure (Floating (doubleLiteral n));
      _ -> failure "LLVM unsupported scalar in numeric region"
    };
  scalarPrimitive :: Primitive -> List Scalar -> Build Scalar;
  scalarPrimitive p values =
    case values of {
      Cons a Nil ->
        case p of {
          PIntToDouble ->
            do {
              value <- boxed a;
              bits <- result ("ptrtoint ptr " ++ (value ++ " to i64"));
              low <- result ("and i64 " ++ (bits ++ ", 1"));
              tag <- result ("icmp ne i64 " ++ (low ++ ", 0"));
              answer <-
                choose "double" tag
                  (do {
                     untagged <- result ("ashr i64 " ++ (bits ++ ", 1"));
                     result ("sitofp i64 " ++ (untagged ++ " to double"))
                   })
                  (result ("call double @mlf_int_to_double(ptr " ++ (value ++ ")")));
              cgPure (Floating answer)
            };
          PSqrtDouble ->
            do {
              x <- floating a;
              value <- result ("call double @llvm.sqrt.f64(double " ++ (x ++ ")"));
              cgPure (Floating value)
            };
          _ -> scalarPrimitiveFallback p values
        };
      Cons a (Cons b Nil) ->
        if doubleBinary p then scalarDoubleBinary p a b else scalarPrimitiveFallback p values;
      _ -> scalarPrimitiveFallback p values
    };
  doubleBinary :: Primitive -> Bool;
  doubleBinary p =
    case p of {
      PAddDouble -> True;
      PSubDouble -> True;
      PMulDouble -> True;
      PDivDouble -> True;
      PEqDouble -> True;
      PLtDouble -> True;
      _ -> False
    };
  scalarDoubleBinary :: Primitive -> Scalar -> Scalar -> Build Scalar;
  scalarDoubleBinary p a b =
    do {
      x <- floating a;
      y <- floating b;
      if ((P.primitiveCode p == 23) || (P.primitiveCode p == 24))
      then do {
             test <-
               result
                 ("fcmp " ++
                  ((if (P.primitiveCode p == 23) then "oeq" else "olt") ++
                   (" double " ++ (x ++ (", " ++ y)))));
             value <-
               result
                 ("select i1 " ++
                  (test ++ (", ptr " ++ (immediate 6 ++ (", ptr " ++ immediate 2)))));
             cgPure (Boxed value)
           }
      else do {
             let {
               op =
                 case p of {
                   PAddDouble -> "fadd";
                   PSubDouble -> "fsub";
                   PMulDouble -> "fmul";
                   _ -> "fdiv"
                 }
             };
             value <- result (op ++ (" double " ++ (x ++ (", " ++ y))));
             cgPure (Floating value)
           }
    };
  scalarPrimitiveFallback :: Primitive -> List Scalar -> Build Scalar;
  scalarPrimitiveFallback p values =
    do {
      pointers <- L.mapM boxed values;
      result <-
        case pointers of {
          Cons a (Cons b Nil) ->
            case p of {
              PAddInt -> numericInteger p a b;
              PSubInt -> numericInteger p a b;
              PEqInt -> numericInteger p a b;
              PLtInt -> numericInteger p a b;
              PMulInt -> numericProduct p a b;
              PQuotInt -> numericProduct p a b;
              PRemInt -> numericProduct p a b;
              PAndInt -> numericAnd a b;
              _ -> numericPrimitiveCall p pointers
            };
          _ -> numericPrimitiveCall p pointers
        };
      cgPure (Boxed result)
    };
  numericPrimitiveCall :: Primitive -> List String -> Build String;
  numericPrimitiveCall p pointers =
    call ("@mlf_prim" ++ showInt (L.length pointers))
      (Cons (number (P.primitiveCode p)) (L.map pointer pointers));
  executeNumeric :: Map XName Scalar -> XErased -> Build Scalar;
  executeNumeric scope expression =
    case tableUpdate expression of {
      Just update ->
        do {
          next <- executeTableUpdate scope update;
          case next of {
            Pair local rest -> executeNumeric local rest
          }
        };
      Nothing ->
        case expression of {
          XELet n a b ->
            do {
              value <- scalarValue scope a;
              executeNumeric (M.insert O.compareName n value scope) b
            };
          XELetRec ds b -> executeNumeric scope b;
          _ -> executeNumericApplication scope expression
        }
    };
  executeNumericApplication :: Map XName Scalar -> XErased -> Build Scalar;
  executeNumericApplication scope expression =
    case O.applications expression of {
      Pair (XEPrimitive PIOBind) (Cons a (Cons (XEAbs n b) Nil)) ->
        do {
          value <- executeNumeric scope a;
          executeNumeric (M.insert O.compareName n value scope) b
        };
      Pair (XEPrimitive PIOReturn) (Cons a Nil) -> scalarValue scope a;
      Pair (XEPrimitive PIfThenElse) (Cons c (Cons a (Cons b Nil))) ->
        numericBranch scope c (executeNumeric scope a) (executeNumeric scope b);
      Pair (XEVar name) args ->
        do {
          fs <- gets functions;
          case M.lookup O.compareName name fs of {
            Nothing -> failure "LLVM missing numeric function";
            Just f ->
              do {
                captured <- L.mapM (numericValue scope) (A.captures f);
                values <- L.mapM (scalarValue scope) args;
                value <-
                  withNumericRoots name scope (invokeKernel name f (L.append captured values));
                cgPure (Boxed value)
              }
          }
        };
      Pair (XEPrimitive p) args ->
        if arrayOperation p
        then executeArray scope p args
        else case p of {
               PReadIntTable -> executeTable scope p args;
               PWriteIntTable -> executeTable scope p args;
               PGetByteLine -> executeAllocation scope p args;
               PNewByteArray -> executeAllocation scope p args;
               PNewIntArray -> executeAllocation scope p args;
               PNewDoubleArray -> executeAllocation scope p args;
               PByteArrayFromString -> executeAllocation scope p args;
               PPutBytes -> executeAllocation scope p args;
               PNewIntTable -> executeAllocation scope p args;
               _ -> failure "LLVM unsupported numeric IO region"
             };
      _ -> failure "LLVM unsupported numeric IO region"
    };
  arrayOperation :: Primitive -> Bool;
  arrayOperation p =
    case p of {
      PReadIntArray -> True;
      PReadDoubleArray -> True;
      PWriteIntArray -> True;
      PWriteDoubleArray -> True;
      PLengthIntArray -> True;
      PLengthDoubleArray -> True;
      PReadByteArray -> True;
      PWriteByteArray -> True;
      PLengthByteArray -> True;
      _ -> False
    };
  lengthOperation :: Primitive -> Bool;
  lengthOperation p =
    case p of {
      PLengthIntArray -> True;
      PLengthDoubleArray -> True;
      PLengthByteArray -> True;
      _ -> False
    };
  executeArray :: Map XName Scalar -> Primitive -> List XErased -> Build Scalar;
  executeArray scope p args =
    do {
      values <- L.mapM (scalarValue scope) args;
      array <-
        case values of {
          Nil -> failure "LLVM missing array operand";
          Cons a rest -> boxed a
        };
      view <- arrayView array;
      case view of {
        Pair len cells ->
          if lengthOperation p
          then do {
                 shift <- result ("shl i64 " ++ (len ++ ", 1"));
                 bits <- result ("or i64 " ++ (shift ++ ", 1"));
                 value <- result ("inttoptr i64 " ++ (bits ++ " to ptr"));
                 cgPure (Boxed value)
               }
          else do {
                 index <- boxed (L.index values 1);
                 bits <- result ("ptrtoint ptr " ++ (index ++ " to i64"));
                 i <- result ("ashr i64 " ++ (bits ++ ", 1"));
                 low <- result ("and i64 " ++ (bits ++ ", 1"));
                 tag <- result ("icmp ne i64 " ++ (low ++ ", 0"));
                 bounds <- result ("icmp ult i64 " ++ (i ++ (", " ++ len)));
                 ok <- result ("and i1 " ++ (tag ++ (", " ++ bounds)));
                 valid <- fresh "array.valid.";
                 invalid <- fresh "array.invalid.";
                 emit ("  br i1 " ++ (ok ++ (", label %" ++ (valid ++ (", label %" ++ invalid)))));
                 label invalid;
                 emit "  call void @mlf_bounds_failure()";
                 emit "  unreachable";
                 label valid;
                 recordRange index (Pair 0 1152921504606846974);
                 let {
                   byteArray = ((P.primitiveCode p == 36) || (P.primitiveCode p == 37))
                 };
                 address <-
                   result
                     ("getelementptr " ++
                      ((if byteArray then "i8" else "i64") ++
                       (", ptr " ++ (cells ++ (", i64 " ++ i)))));
                 executeArrayCell p values address
               }
      }
    };
  executeArrayCell :: Primitive -> List Scalar -> String -> Build Scalar;
  executeArrayCell p values address =
    case p of {
      PReadByteArray ->
        do {
          x <- result ("load i8, ptr " ++ (address ++ ", align 1, !tbaa !4"));
          wide <- result ("zext i8 " ++ (x ++ " to i64"));
          shifted <- result ("shl i64 " ++ (wide ++ ", 1"));
          tagged <- result ("or i64 " ++ (shifted ++ ", 1"));
          value <- result ("inttoptr i64 " ++ (tagged ++ " to ptr"));
          recordRange value (Pair 0 255);
          cgPure (Boxed value)
        };
      PWriteByteArray ->
        do {
          value <- boxed (L.index values 2);
          x <- numericByte value;
          emit ("  store i8 " ++ (x ++ (", ptr " ++ (address ++ ", align 1, !tbaa !4"))));
          cgPure (Boxed (immediate 4))
        };
      PReadDoubleArray ->
        do {
          value <- result ("load double, ptr " ++ (address ++ ", align 8, !tbaa !4"));
          cgPure (Floating value)
        };
      PReadIntArray ->
        do {
          value <- result ("load ptr, ptr " ++ (address ++ ", align 8, !tbaa !4"));
          cgPure (Boxed value)
        };
      PWriteDoubleArray ->
        do {
          value <- floating (L.index values 2);
          emit ("  store double " ++ (value ++ (", ptr " ++ (address ++ ", align 8, !tbaa !4"))));
          cgPure (Boxed (immediate 4))
        };
      _ ->
        do {
          value <- boxed (L.index values 2);
          emit ("  store ptr " ++ (value ++ (", ptr " ++ (address ++ ", align 8, !tbaa !4"))));
          cgPure (Boxed (immediate 4))
        }
    };
  executeTable :: Map XName Scalar -> Primitive -> List XErased -> Build Scalar;
  executeTable scope p args =
    do {
      values <- L.mapM (scalarBoxed scope) args;
      value <-
        call (if (P.primitiveCode p == 43) then "@mlf_read_int_table" else "@mlf_write_int_table")
          (L.map pointer values);
      cgPure (Boxed value)
    };
  executeAllocation :: Map XName Scalar -> Primitive -> List XErased -> Build Scalar;
  executeAllocation scope p args =
    do {
      values <- L.mapM (scalarBoxed scope) args;
      let {
        target =
          case p of {
            PGetByteLine -> Pair "@mlf_get_byte_line" Nil;
            PNewIntTable -> Pair "@mlf_new_int_table" Nil;
            PByteArrayFromString -> Pair "@mlf_bytes_from_string" Nil;
            PPutBytes -> Pair "@mlf_put_bytes" Nil;
            _ -> Pair "@mlf_new_array" (args1 (number (P.primitiveCode p)))
          }
      };
      value <-
        case target of {
          Pair symbol prefix -> call symbol (L.append prefix (L.map pointer values))
        };
      cgPure (Boxed value)
    };
  bindParts :: XErased -> Maybe (Triple XErased XName XErased);
  bindParts expression =
    case O.applications expression of {
      Pair (XEPrimitive PIOBind) (Cons action (Cons (XEAbs name body) Nil)) ->
        Just (Triple action name body);
      _ -> Nothing
    };
  tableUpdate :: XErased -> Maybe TableUpdate;
  tableUpdate expression =
    case bindParts expression of {
      Nothing -> Nothing;
      Just (Triple readAction old body) ->
        case O.applications readAction of {
          Pair (XEPrimitive PReadIntTable) (Cons table (Cons key Nil)) ->
            case bindParts body of {
              Nothing -> Nothing;
              Just (Triple writeAction done rest) ->
                case O.applications writeAction of {
                  Pair (XEPrimitive PWriteIntTable) (Cons table2 (Cons key2 (Cons value Nil))) ->
                    if (X.equalErased table table2 && X.equalErased key key2)
                    then case O.applications value of {
                           Pair (XEPrimitive PAddInt) (Cons a (Cons b Nil)) ->
                             let {
                               delta =
                                 if X.equalErased a (XEVar old)
                                 then Just b
                                 else if X.equalErased b (XEVar old) then Just a else Nothing
                             } in
                             case delta of {
                               Nothing -> Nothing;
                               Just amount ->
                                 if S.member O.compareName old (O.free amount)
                                 then Nothing
                                 else Just (TableUpdate old table key amount done rest)
                             };
                           _ -> Nothing
                         }
                    else Nothing;
                  _ -> Nothing
                }
            };
          _ -> Nothing
        }
    };
  executeTableUpdate :: Map XName Scalar -> TableUpdate -> Build (Pair (Map XName Scalar) XErased);
  executeTableUpdate scope (TableUpdate old table key delta done rest) =
    do {
      values <- L.mapM (scalarBoxed scope) (args3 table key delta);
      previous <- call "@mlf_add_int_table" (L.map pointer values);
      cgPure
        (Pair
           (M.insert O.compareName done (Boxed (immediate 4))
              (M.insert O.compareName old (Boxed previous) scope))
           rest)
    };
  numericAnd :: String -> String -> Build String;
  numericAnd a b =
    do {
      x <- result ("ptrtoint ptr " ++ (a ++ " to i64"));
      y <- result ("ptrtoint ptr " ++ (b ++ " to i64"));
      bits <- result ("and i64 " ++ (x ++ (", " ++ y)));
      low <- result ("and i64 " ++ (bits ++ ", 1"));
      tag <- result ("icmp ne i64 " ++ (low ++ ", 0"));
      value <-
        choose "ptr" tag (result ("inttoptr i64 " ++ (bits ++ " to ptr")))
          (numericPrimitiveCall PAndInt (args2 a b));
      facts <- gets scalarRanges;
      let {
        bounds =
          L.concatMap
            (\v ->
               case M.lookup compareString v facts of {
                 Just (Pair lo hi) -> if (lo >= 0) then args1 hi else Nil;
                 Nothing -> Nil
               })
            (args2 a b)
      };
      case bounds of {
        Nil -> cgPure Unit;
        Cons first rest -> recordRange value (Pair 0 (L.foldl L.min first rest))
      };
      cgPure value
    };
  numericByte :: String -> Build String;
  numericByte value =
    do {
      facts <- gets scalarRanges;
      bits <- result ("ptrtoint ptr " ++ (value ++ " to i64"));
      n <- result ("ashr i64 " ++ (bits ++ ", 1"));
      let {
        narrow = result ("trunc i64 " ++ (n ++ " to i8"))
      };
      let {
        proven =
          case M.lookup compareString value facts of {
            Just (Pair lo hi) -> ((lo >= 0) && (hi <= 255));
            Nothing -> False
          }
      };
      if proven
      then narrow
      else do {
             low <- result ("and i64 " ++ (bits ++ ", 1"));
             small <- result ("icmp ne i64 " ++ (low ++ ", 0"));
             bounds <- result ("icmp ult i64 " ++ (n ++ ", 256"));
             valid <- result ("and i1 " ++ (small ++ (", " ++ bounds)));
             choose "i8" valid narrow (result ("call i8 @mlf_byte(ptr " ++ (value ++ ")")))
           }
    };
  tagInteger :: String -> Build String;
  tagInteger value =
    do {
      shifted <- result ("shl i64 " ++ (value ++ ", 1"));
      bits <- result ("or i64 " ++ (shifted ++ ", 1"));
      result ("inttoptr i64 " ++ (bits ++ " to ptr"))
    };
  checkedProduct :: String -> String -> Build String -> Build String -> Build String;
  checkedProduct x y fast slow =
    do {
      both <- result ("and i64 " ++ (x ++ (", " ++ y)));
      low <- result ("and i64 " ++ (both ++ ", 1"));
      tag <- result ("icmp ne i64 " ++ (low ++ ", 0"));
      choose "ptr" tag fast slow
    };
  productFast :: Primitive -> String -> String -> Build String -> Build String;
  productFast p x y slow =
    do {
      i <- result ("ashr i64 " ++ (x ++ ", 1"));
      j <- result ("ashr i64 " ++ (y ++ ", 1"));
      if (P.primitiveCode p == 14)
      then do {
             pair <-
               result
                 ("call { i64, i1 } @llvm.smul.with.overflow.i64(i64 " ++
                  (i ++ (", i64 " ++ (j ++ ")"))));
             n <- result ("extractvalue { i64, i1 } " ++ (pair ++ ", 0"));
             overflow <- result ("extractvalue { i64, i1 } " ++ (pair ++ ", 1"));
             noOverflow <- result ("xor i1 " ++ (overflow ++ ", true"));
             lower <- result ("icmp sge i64 " ++ (n ++ ", -4611686018427387904"));
             upper <- result ("icmp sle i64 " ++ (n ++ ", 4611686018427387903"));
             bounds <- result ("and i1 " ++ (lower ++ (", " ++ upper)));
             fits <- result ("and i1 " ++ (bounds ++ (", " ++ noOverflow)));
             choose "ptr" fits (tagInteger n) slow
           }
      else do {
             nonzero <- result ("icmp ne i64 " ++ (j ++ ", 0"));
             smallest <- result ("icmp eq i64 " ++ (i ++ ", -4611686018427387904"));
             negativeOne <- result ("icmp eq i64 " ++ (j ++ ", -1"));
             promotion <- result ("and i1 " ++ (smallest ++ (", " ++ negativeOne)));
             noPromotion <- result ("xor i1 " ++ (promotion ++ ", true"));
             fits <- result ("and i1 " ++ (nonzero ++ (", " ++ noPromotion)));
             choose "ptr" fits
               (do {
                  value <-
                    result
                      ((if (P.primitiveCode p == 15) then "sdiv" else "srem") ++
                       (" i64 " ++ (i ++ (", " ++ j))));
                  tagInteger value
                })
               slow
           }
    };
  productBounds :: Pair Int Int -> Pair Int Int -> Pair Int Int;
  productBounds (Pair lo hi) (Pair lo2 hi2) =
    let {
      products = args4 (lo * lo2) (lo * hi2) (hi * lo2) (hi * hi2)
    } in
    Pair (L.foldl L.min (lo * lo2) products) (L.foldl L.max (lo * lo2) products);
  smallBounds :: Pair Int Int -> Bool;
  smallBounds (Pair lo hi) = ((lo >= (0 - 4611686018427387904)) && (hi < 4611686018427387904));
  numericProduct :: Primitive -> String -> String -> Build String;
  numericProduct p a b =
    do {
      facts <- gets scalarRanges;
      x <- result ("ptrtoint ptr " ++ (a ++ " to i64"));
      y <- result ("ptrtoint ptr " ++ (b ++ " to i64"));
      let {
        slow = numericPrimitiveCall p (args2 a b)
      };
      let {
        fast = productFast p x y slow
      };
      let {
        bound =
          if (P.primitiveCode p == 14)
          then case M.lookup compareString a facts of {
                 Nothing -> Nothing;
                 Just range1 ->
                   case M.lookup compareString b facts of {
                     Nothing -> Nothing;
                     Just range2 -> Just (productBounds range1 range2)
                   }
               }
          else Nothing
      };
      case bound of {
        Just bounds ->
          if smallBounds bounds
          then do {
                 i <- result ("ashr i64 " ++ (x ++ ", 1"));
                 j <- result ("ashr i64 " ++ (y ++ ", 1"));
                 multiplied <- result ("mul nsw i64 " ++ (i ++ (", " ++ j)));
                 value <- tagInteger multiplied;
                 recordRange value bounds;
                 cgPure value
               }
          else checkedProduct x y fast slow;
        Nothing -> checkedProduct x y fast slow
      }
    };
  integerBounds :: Primitive -> Pair Int Int -> Pair Int Int -> Pair Int Int;
  integerBounds p (Pair lo hi) (Pair lo2 hi2) =
    if (P.primitiveCode p == 8) then Pair (lo + lo2) (hi + hi2) else Pair (lo - hi2) (hi - lo2);
  numericInteger :: Primitive -> String -> String -> Build String;
  numericInteger p a b =
    do {
      facts <- gets scalarRanges;
      let {
        range =
          case M.lookup compareString a facts of {
            Nothing -> Nothing;
            Just range1 ->
              case M.lookup compareString b facts of {
                Nothing -> Nothing;
                Just range2 -> Just (integerBounds p range1 range2)
              }
          }
      };
      case range of {
        Nothing -> integerOperation p a b;
        Just bounds ->
          if ((P.primitiveCode p == 10) || ((P.primitiveCode p == 11) || smallBounds bounds))
          then do {
                 x <- result ("ptrtoint ptr " ++ (a ++ " to i64"));
                 y <- result ("ptrtoint ptr " ++ (b ++ " to i64"));
                 if ((P.primitiveCode p == 10) || (P.primitiveCode p == 11))
                 then do {
                        test <-
                          result
                            ("icmp " ++
                             ((if (P.primitiveCode p == 10) then "eq" else "slt") ++
                              (" i64 " ++ (x ++ (", " ++ y)))));
                        result
                          ("select i1 " ++
                           (test ++ (", ptr " ++ (immediate 6 ++ (", ptr " ++ immediate 2)))))
                      }
                 else do {
                        offset <- result ("sub i64 " ++ (y ++ ", 1"));
                        bits <-
                          result
                            ((if (P.primitiveCode p == 8) then "add" else "sub") ++
                             (" nsw i64 " ++ (x ++ (", " ++ offset))));
                        value <- result ("inttoptr i64 " ++ (bits ++ " to ptr"));
                        recordRange value bounds;
                        cgPure value
                      }
               }
          else integerOperation p a b
      }
    };
  copyBytesReturn :: Map XName Scalar -> List XName -> Build Unit -> Build Unit;
  copyBytesReturn scope names fallback =
    do {
      values <- L.mapM (numericBoxed scope) names;
      case values of {
        Cons source (Cons dest (Cons end (Cons offset (Cons index Nil)))) ->
          do {
            sourceView <- arrayView source;
            destView <- arrayView dest;
            bits <-
              L.mapM (\value -> result ("ptrtoint ptr " ++ (value ++ " to i64")))
                (args3 end offset index);
            tests <-
              L.mapM
                (\value ->
                   do {
                     low <- result ("and i64 " ++ (value ++ ", 1"));
                     result ("icmp ne i64 " ++ (low ++ ", 0"))
                   })
                bits;
            numbers <- L.mapM (\value -> result ("ashr i64 " ++ (value ++ ", 1"))) bits;
            case numbers of {
              Cons n (Cons o (Cons i Nil)) ->
                copyBytesChecks sourceView destView tests n o i fallback;
              _ -> failure "LLVM invalid copy indices"
            }
          };
        _ -> failure "LLVM invalid copy operands"
      }
    };
  copyBytesChecks :: Pair String String ->
                     Pair String String ->
                     List String -> String -> String -> String -> Build Unit -> Build Unit;
  copyBytesChecks (Pair sourceLength sourceCells) (Pair destLength destCells) tests n o i fallback =
    do {
      validStart <- result ("icmp sge i64 " ++ (i ++ ", 0"));
      validEnd <- result ("icmp sge i64 " ++ (n ++ (", " ++ i)));
      validSource <- result ("icmp ule i64 " ++ (n ++ (", " ++ sourceLength)));
      validOffset <- result ("icmp ule i64 " ++ (o ++ (", " ++ destLength)));
      available <- result ("sub i64 " ++ (destLength ++ (", " ++ o)));
      validDest <- result ("icmp ule i64 " ++ (n ++ (", " ++ available)));
      count <- result ("sub i64 " ++ (n ++ (", " ++ i)));
      separate <- result ("icmp ne ptr " ++ (sourceCells ++ (", " ++ destCells)));
      samePosition <- result ("icmp eq i64 " ++ (o ++ ", 0"));
      disjoint <- result ("icmp uge i64 " ++ (o ++ (", " ++ count)));
      separateOrSame <- result ("or i1 " ++ (separate ++ (", " ++ samePosition)));
      safeAlias <- result ("or i1 " ++ (separateOrSame ++ (", " ++ disjoint)));
      let {
        validity =
          L.append tests
            (L.append (args3 validStart validEnd validSource)
               (args3 validOffset validDest safeAlias))
      };
      ready <- L.foldM (\a b -> result ("and i1 " ++ (a ++ (", " ++ b)))) "true" validity;
      fast <- fresh "copy.bulk.";
      slow <- fresh "copy.scalar.";
      emit ("  br i1 " ++ (ready ++ (", label %" ++ (fast ++ (", label %" ++ slow)))));
      label fast;
      from <- result ("getelementptr i8, ptr " ++ (sourceCells ++ (", i64 " ++ i)));
      start <- result ("add i64 " ++ (o ++ (", " ++ i)));
      to <- result ("getelementptr i8, ptr " ++ (destCells ++ (", i64 " ++ start)));
      emit
        ("  call void @llvm.memmove.p0.p0.i64(ptr " ++
         (to ++ (", ptr " ++ (from ++ (", i64 " ++ (count ++ ", i1 false)"))))));
      emit ("  ret ptr " ++ immediate 4);
      label slow;
      fallback
    }
}
