-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.LLVM.Codegen where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.LLVM.Build;
  import qualified Bootstrap.Std as L;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Set as S;
  import qualified Bootstrap.Primitive as P;
  import qualified Bootstrap.LLVM.Analysis as A;
  import qualified Bootstrap.LLVM.StrictFields as F;
  import qualified Bootstrap.LLVM.Kernel as K;
  import qualified Bootstrap.LLVM.Optimize as O;
  import qualified Bootstrap.LLVM.Native as N;
  generate :: Map String (Pair Int Int) -> XErased -> Either String (Pair String (List String));
  generate cs term =
    let {
      fs = A.analyze term
    } in
    let {
      ks = K.kernels fs
    } in
    let {
      output =
        Output 0 Nil "entry" Nil Nil cs fs S.empty M.empty ks S.empty (K.collecting fs ks) M.empty
          True
          M.empty
          M.empty
          M.empty
          M.empty
          (F.infer (M.map L.snd cs) fs term)
          S.empty
    } in
    case runBuild (callback Nil Nothing term) output of {
      Left error -> Left error;
      Right (Pair entry out) ->
        Right
          (Pair entry
             (L.concat
                (Cons (Cons "declare ptr @mlf_thunk_new(ptr, i64)" runtimeDeclarations)
                   (args4
                      (L.append allocationDefinition
                         (L.append thunkAllocationDefinition forceDefinition))
                      aliasMetadata
                      (L.reverse (constants out))
                      (L.reverse (definitions out))))))
    };
  lookupName :: Map XName CGBinding -> XName -> Build CGBinding;
  lookupName scope name =
    case M.lookup O.compareName name scope of {
      Just value -> cgPure value;
      Nothing ->
        do {
          fs <- gets functions;
          case M.lookup O.compareName name fs of {
            Nothing -> failure ("LLVM unbound identity: " ++ showInt (O.nameId name));
            Just f ->
              do {
                code <- wrapper name f;
                env <- environment scope (A.captures f);
                value <- call "@mlf_closure" (args2 (pointer code) (pointer env));
                cgPure (CGBinding value True)
              }
          }
        }
    };
  environment :: Map XName CGBinding -> List XName -> Build String;
  environment scope names =
    if L.null names
    then cgPure "null"
    else do {
           env <- call "@mlf_env_new" (args1 (number (L.length names)));
           L.mapM_
             (\entry ->
                case entry of {
                  Pair index name ->
                    do {
                      binding <- lookupName scope name;
                      value <- bindingOperand binding;
                      storeEnvironment env index value
                    }
                })
             (L.zip (L.range 0 (L.length names - 1)) names);
           cgPure env
         };
  readEnvironment :: List XName -> Build (Map XName CGBinding);
  readEnvironment names =
    do {
      entries <-
        L.mapM
          (\entry ->
             case entry of {
               Pair index name ->
                 do {
                   value <- loadEnvironment "%env" index;
                   cgPure (Pair name (CGBinding value False))
                 }
             })
          (L.zip (L.range 0 (L.length names - 1)) names);
      cgPure (M.fromList O.compareName entries)
    };
  callback :: List XName -> Maybe XName -> XErased -> Build String;
  callback captures argument body = callbackWithClear False captures argument body;
  -- A compiled suspended expression owns its capture environment and runs once.
  -- Drop those slots after loading them, before entering its possibly long body.
  -- Reusable function and IO environments must keep their captures intact.
  callbackWithClear :: Bool -> List XName -> Maybe XName -> XErased -> Build String;
  callbackWithClear private captures argument body =
    do {
      name <- fresh "@mlf.code.";
      definition name (args2 "ptr %env" "ptr %arg")
        (do {
           scope <- readEnvironment captures;
           if private
           then L.mapM_ (\index -> storeEnvironment "%env" index "null")
                  (L.range 0 (L.length captures - 1))
           else cgPure Unit;
           let {
             local =
               case argument of {
                 Nothing -> scope;
                 Just n -> M.insert O.compareName n (CGBinding "%arg" False) scope
               }
           };
           evaluate local body
         });
      cgPure name
    };
  worker :: XName -> A.WorkerFunction -> Build String;
  worker name f =
    do {
      let {
        symbol = ("@mlf.worker." ++ showInt (O.nameId name))
      };
      let {
        names = L.append (A.captures f) (A.parameters f)
      };
      let {
        registers = L.map (\i -> ("%a" ++ showInt i)) (L.range 0 (L.length names - 1))
      };
      seen <- gets (\state -> S.member O.compareName name (workers state));
      if seen
      then cgPure Unit
      else do {
             modify (\state -> withWorkers (S.insert O.compareName name (workers state)) state);
             inline <- gets inlinePrimitives;
             native <- gets (\state -> S.member O.compareName name (numericKernels state));
             if native then modify (withInlinePrimitives False) else cgPure Unit;
             let {
               scope =
                 M.fromList O.compareName
                   (L.zipWith
                      (\n register ->
                         Pair n (CGBinding register (S.member O.compareName n (A.strict f))))
                      names
                      registers)
             };
             definition symbol (L.map pointer registers) (evaluate scope (A.functionBody f));
             modify (withInlinePrimitives inline)
           };
      cgPure symbol
    };
  wrapper :: XName -> A.WorkerFunction -> Build String;
  wrapper name f =
    do {
      previous <- gets (\state -> M.lookup O.compareName name (wrappers state));
      case previous of {
        Just symbol -> cgPure symbol;
        Nothing ->
          do {
            symbol <- fresh "@mlf.curry.";
            modify
              (\state -> withWrappers (M.insert O.compareName name symbol (wrappers state)) state);
            buildWrapper name f symbol (A.captures f) (A.parameters f);
            cgPure symbol
          }
      }
    };
  buildWrapper :: XName -> A.WorkerFunction -> String -> List XName -> List XName -> Build Unit;
  buildWrapper name f symbol captured remaining =
    case remaining of {
      Nil -> failure "LLVM empty function wrapper";
      Cons arg rest ->
        definition symbol (args2 "ptr %env" "ptr %arg")
          (do {
             saved <- readEnvironment captured;
             let {
               scope = M.insert O.compareName arg (CGBinding "%arg" False) saved
             };
             if L.null rest
             then invoke scope name f (L.map XEVar (A.parameters f))
             else do {
                    next <- fresh "@mlf.curry.";
                    buildWrapper name f next (L.snoc captured arg) rest;
                    env <- environment scope (L.snoc captured arg);
                    call "@mlf_closure" (args2 (pointer next) (pointer env))
                  }
           })
    };
  invoke :: Map XName CGBinding -> XName -> A.WorkerFunction -> List XErased -> Build String;
  invoke scope name f args =
    do {
      native <- gets (\state -> S.member O.compareName name (numericKernels state));
      if native then kernelAction scope name f args else invokeOrdinary scope name f args
    };
  capturedArguments :: Map XName CGBinding -> A.WorkerFunction -> Build (List String);
  capturedArguments scope f =
    L.mapM
      (\name ->
         do {
           binding <- lookupName scope name;
           if S.member O.compareName name (A.strict f)
           then forceBinding binding
           else bindingOperand binding
         })
      (A.captures f);
  ordinaryArguments :: Map XName CGBinding ->
                       A.WorkerFunction -> List XErased -> Build (List String);
  ordinaryArguments scope f args =
    L.mapM
      (\entry ->
         case entry of {
           Pair name arg ->
             if S.member O.compareName name (A.strict f)
             then evaluate scope arg
             else thunk scope arg
         })
      (L.zip (A.parameters f) args);
  invokeOrdinary :: Map XName CGBinding ->
                    XName -> A.WorkerFunction -> List XErased -> Build String;
  invokeOrdinary scope name f args =
    do {
      symbol <- worker name f;
      captured <- capturedArguments scope f;
      values <- ordinaryArguments scope f args;
      call symbol (L.map pointer (L.append captured values))
    };
  kernelAction :: Map XName CGBinding -> XName -> A.WorkerFunction -> List XErased -> Build String;
  kernelAction scope name f args =
    do {
      old <- gets (\state -> M.lookup O.compareName name (kernelEntries state));
      entry <-
        case old of {
          Just symbol -> cgPure symbol;
          Nothing ->
            do {
              symbol <- fresh "@mlf.numeric.entry.";
              modify
                (\state ->
                   withKernelEntries (M.insert O.compareName name symbol (kernelEntries state))
                     state);
              let {
                names = L.append (A.captures f) (A.parameters f)
              };
              definition symbol (args2 "ptr %env" "ptr %arg")
                (do {
                   saved <- readEnvironment names;
                   values <-
                     L.mapM
                       (\n ->
                          case M.lookup O.compareName n saved of {
                            Nothing -> failure "LLVM native entry capture missing";
                            Just binding -> call "@mlf_peek" (args1 (pointer (operand binding)))
                          })
                       names;
                   checks <- L.mapM (\v -> result ("icmp ne ptr " ++ (v ++ ", null"))) values;
                   ready <-
                     L.foldM (\a b -> result ("and i1 " ++ (a ++ (", " ++ b)))) "true" checks;
                   choose "ptr" ready
                     (do {
                        value <- N.invokeKernel name f (L.map Boxed values);
                        call "@mlf_prim1" (args2 (number 0) (pointer value))
                      })
                     (invokeOrdinary saved name f (L.map XEVar (A.parameters f)))
                 });
              cgPure symbol
            }
        };
      captured <- capturedArguments scope f;
      values <- ordinaryArguments scope f args;
      let {
        all = L.append captured values
      };
      env <- call "@mlf_env_new" (args1 (number (L.length all)));
      L.mapM_
        (\entry ->
           case entry of {
             Pair i value -> storeEnvironment env i value
           })
        (L.zip (L.range 0 (L.length all - 1)) all);
      call "@mlf_native_io" (args2 (pointer entry) (pointer env))
    };
  suspended :: Map XName CGBinding -> XErased -> Build String;
  suspended scope expression =
    do {
      fs <- gets functions;
      let {
        captures = S.toList (A.needed fs expression)
      };
      code <- callbackWithClear True captures Nothing expression;
      if L.null captures
      then do {
             env <- environment scope captures;
             call "@mlf_thunk" (args2 (pointer code) (pointer env))
           }
      else do {
             value <-
               call (if (L.length captures <= 28) then "@mlf.allocate.thunk" else "@mlf_thunk_new")
                 (args2 (pointer code) (number (L.length captures)));
             env <- loadAt "ptr" value 16;
             L.mapM_
               (\entry ->
                  case entry of {
                    Pair index name ->
                      do {
                        binding <- lookupName scope name;
                        captured <- bindingOperand binding;
                        storeEnvironment env index captured
                      }
                  })
               (L.zip (L.range 0 (L.length captures - 1)) captures);
             cgPure value
           }
    };
  thunk :: Map XName CGBinding -> XErased -> Build String;
  thunk scope expression =
    case expression of {
      XEVar n ->
        do {
          binding <- lookupName scope n;
          bindingOperand binding
        };
      XEInt n -> evaluate scope expression;
      XEDouble n -> evaluate scope expression;
      XEBool b -> evaluate scope expression;
      XEString s -> evaluate scope expression;
      XEPrimitive p -> evaluate scope expression;
      XEConstructor c -> evaluate scope expression;
      XEAbs n b -> evaluate scope expression;
      XEEvidenceHole hole -> failure "LLVM unresolved dictionary evidence";
      _ ->
        case O.applications expression of {
          Pair (XEConstructor c) args ->
            do {
              constructor <- lookupConstructor c;
              if (L.length args == L.snd constructor)
              then evaluate scope expression
              else suspended scope expression
            };
          _ -> suspended scope expression
        }
    };
  evaluate :: Map XName CGBinding -> XErased -> Build String;
  -- Compact strings have immutable bytes and a lazily initialized Unicode
  -- index. A writable global value is itself a BDWGC root for that index;
  -- repeated evaluation needs no allocation or byte copying.
  evaluate scope expression =
    case expression of {
      XEVar n ->
        do {
          value <- lookupName scope n;
          forceBinding value
        };
      XEInt n -> literalInteger n;
      XEDouble n -> call "@mlf_double" (args1 ("double " ++ doubleLiteral n));
      XEBool b -> cgPure (immediate (if b then 6 else 2));
      XEString text ->
        do {
          literal <- stringConstant text;
          let {
            name = (L.fst literal ++ ".value")
          };
          let {
            value =
              (name ++
               (" = private global { i32, i32, i64, ptr, ptr } { i32 8, i32 0, i64 " ++
                (showInt (L.snd literal) ++
                 (", ptr " ++ (L.fst literal ++ ", ptr null }, align 8")))))
          };
          modify (\state -> withConstants (Cons value (constants state)) state);
          cgPure name
        };
      XEPrimitive p -> call "@mlf_primitive" (args1 (number (P.primitiveCode p)));
      XEConstructor c ->
        do {
          constructor <- lookupConstructor c;
          case constructor of {
            Pair tag arity ->
              if (arity == 0)
              then cgPure (immediate ((tag * 8) + 4))
              else call "@mlf_constructor" (args2 (number tag) (number arity))
          }
        };
      XEAbs n body ->
        do {
          fs <- gets functions;
          let {
            captures = S.toList (S.delete O.compareName n (A.needed fs body))
          };
          code <- callback captures (Just n) body;
          env <- environment scope captures;
          call "@mlf_closure" (args2 (pointer code) (pointer env))
        };
      XELet n rhs body ->
        do {
          fs <- gets functions;
          if M.member O.compareName n fs
          then evaluate scope body
          else do {
                 let {
                   strict = S.member O.compareName n (A.demanded fs body)
                 };
                 value <- if strict then evaluate scope rhs else thunk scope rhs;
                 evaluate (M.insert O.compareName n (CGBinding value strict) scope) body
               }
        };
      XELetRec bindings body ->
        do {
          fs <- gets functions;
          let {
            values =
              L.filter
                (\entry ->
                   case entry of {
                     Pair n a -> L.not (M.member O.compareName n fs)
                   })
                bindings
          };
          holes <-
            L.mapM
              (\entry ->
                 case entry of {
                   Pair n ignored ->
                     do {
                       hole <- call "@mlf_hole" Nil;
                       cgPure (Pair n (CGBinding hole False))
                     }
                 })
              values;
          let {
            recursive = M.union O.compareName (M.fromList O.compareName holes) scope
          };
          L.mapM_
            (\entry ->
               case entry of {
                 Pair n rhs ->
                   do {
                     value <- thunk recursive rhs;
                     hole <- lookupName recursive n;
                     emit
                       ("  call void @mlf_fill(ptr " ++
                        (operand hole ++ (", ptr " ++ (value ++ ")"))))
                   }
               })
            values;
          evaluate recursive body
        };
      XECase scrutinee alternatives -> evaluateCase evaluate scope scrutinee alternatives;
      XEApp f a -> application scope expression;
      XEEvidenceHole hole -> failure "LLVM unresolved dictionary evidence"
    };
  evaluateCase :: (Map XName CGBinding -> XErased -> Build String) ->
                  Map XName CGBinding -> XErased -> List XErasedAlternative -> Build String;
  evaluateCase finish scope scrutinee alternatives =
    case alternatives of {
      Cons (XErasedAlternative (XDefaultPattern optional) body) Nil ->
        do {
          value <- thunk scope scrutinee;
          finish (bindOptional optional (CGBinding value False) scope) body
        };
      _ ->
        do {
          value <- evaluate scope scrutinee;
          tag <- constructorTag value;
          labelled <-
            L.mapM
              (\alternative ->
                 do {
                   name <- fresh "case.";
                   cgPure (Pair name alternative)
                 })
              alternatives;
          missing <- fresh "case.missing.";
          join <- fresh "case.join.";
          let {
            fallback = L.fromMaybe missing (caseFallback labelled)
          };
          entries <- L.mapM caseSwitchEntry labelled;
          emit ("  switch i64 " ++ (tag ++ (", label %" ++ (fallback ++ " ["))));
          L.mapM_ emit (L.concat entries);
          emit "  ]";
          forcedBefore <- gets forcedValues;
          incoming <-
            L.mapM
              (\alternative ->
                 do {
                   modify (withForcedValues forcedBefore);
                   evaluateAlternative finish scope value join alternative
                 })
              labelled;
          if eqString fallback missing
          then do {
                 label missing;
                 emit "  call void @mlf_match_failure()";
                 emit "  unreachable"
               }
          else cgPure Unit;
          label join;
          modify (withForcedValues forcedBefore);
          phi "ptr" incoming
        }
    };
  bindOptional :: Maybe XName -> CGBinding -> Map XName CGBinding -> Map XName CGBinding;
  bindOptional optional value scope =
    case optional of {
      Nothing -> scope;
      Just name -> M.insert O.compareName name value scope
    };
  caseFallback :: List (Pair String XErasedAlternative) -> Maybe String;
  caseFallback entries =
    case entries of {
      Nil -> Nothing;
      Cons (Pair label (XErasedAlternative pattern body)) rest ->
        case pattern of {
          XDefaultPattern optional -> Just label;
          _ -> caseFallback rest
        }
    };
  caseSwitchEntry :: Pair String XErasedAlternative -> Build (List String);
  caseSwitchEntry (Pair label (XErasedAlternative pattern body)) =
    case pattern of {
      XDefaultPattern optional -> cgPure Nil;
      XConstructorPattern c fields ->
        do {
          constructor <- lookupConstructor c;
          cgPure (args1 ("    i64 " ++ (showInt (L.fst constructor) ++ (", label %" ++ label))))
        }
    };
  evaluateAlternative :: (Map XName CGBinding -> XErased -> Build String) ->
                         Map XName CGBinding ->
                         String ->
                         String -> Pair String XErasedAlternative -> Build (Pair String String);
  evaluateAlternative finish scope value join (Pair entry (XErasedAlternative pattern body)) =
    do {
      label entry;
      local <- caseScope scope value pattern body;
      result <- finish local body;
      from <- gets block;
      emit ("  br label %" ++ join);
      cgPure (Pair result from)
    };
  caseScope :: Map XName CGBinding -> String -> XPattern -> XErased -> Build (Map XName CGBinding);
  -- The selected checked constructor is already a saturated WHNF.
  -- One environment lookup suffices; field values remain lazy.
  caseScope scope value pattern body =
    case pattern of {
      XDefaultPattern optional -> cgPure (bindOptional optional (CGBinding value True) scope);
      XConstructorPattern c names ->
        do {
          constructor <- lookupConstructor c;
          fs <- gets functions;
          facts <- gets constructorFacts;
          let {
            flags = M.findWithDefault compareString Nil c facts
          };
          let {
            needed = A.needed fs body
          };
          let {
            fields = L.filter (fieldNeeded needed) (L.zip (L.range 0 (L.length names - 1)) names)
          };
          case constructor of {
            Pair tag arity ->
              if L.null fields
              then cgPure scope
              else do {
                     L.foldM (bindField flags value (if (arity <= 2) then 16 else 24)) scope fields
                   }
          }
        }
    };
  fieldNeeded :: Set XName -> Pair Int (Maybe XName) -> Bool;
  fieldNeeded needed (Pair index optional) =
    case optional of {
      Nothing -> False;
      Just name -> S.member O.compareName name needed
    };
  bindField :: List Bool ->
               String ->
               Int -> Map XName CGBinding -> Pair Int (Maybe XName) -> Build (Map XName CGBinding);
  bindField flags base offset env (Pair index optional) =
    case optional of {
      Nothing -> cgPure env;
      Just name ->
        do {
          field <- loadAt "ptr" base (offset + (8 * index));
          cgPure
            (M.insert O.compareName name (CGBinding field (L.fromMaybe False (L.at index flags)))
               env)
        }
    };
  -- Entered only where checked runST/STBind requires an ST action. Results
  -- remain lazy; the enclosing runST is the boundary that demands WHNF.
  -- Ordinary worker and let demands still produce the action description before
  -- execution. Bind results stay lazy, including results returned by helpers.
  executeST :: String -> Map XName CGBinding -> XErased -> Build String;
  executeST fuel scope expression =
    case expression of {
      XELet n rhs body ->
        case body of {
          XEApp (XEApp (XEPrimitive PSTBind) (XEVar use)) next ->
            if (O.eqName n use && L.not (S.member O.compareName n (O.free next)))
            then executeST fuel scope (XEApp (XEApp (XEPrimitive PSTBind) rhs) next)
            else executeSTLet fuel scope n rhs body;
          XEVar use ->
            if O.eqName n use then executeST fuel scope rhs else executeSTLet fuel scope n rhs body;
          _ -> executeSTLet fuel scope n rhs body
        };
      XELetRec bindings body ->
        do {
          fs <- gets functions;
          let {
            values =
              L.filter
                (\entry ->
                   case entry of {
                     Pair n a -> L.not (M.member O.compareName n fs)
                   })
                bindings
          };
          holes <-
            L.mapM
              (\entry ->
                 case entry of {
                   Pair n ignored ->
                     do {
                       hole <- call "@mlf_hole" Nil;
                       cgPure (Pair n (CGBinding hole False))
                     }
                 })
              values;
          let {
            recursive = M.union O.compareName (M.fromList O.compareName holes) scope
          };
          L.mapM_
            (\entry ->
               case entry of {
                 Pair n rhs ->
                   do {
                     value <- thunk recursive rhs;
                     hole <- lookupName recursive n;
                     emit
                       ("  call void @mlf_fill(ptr " ++
                        (operand hole ++ (", ptr " ++ (value ++ ")"))))
                   }
               })
            values;
          executeST fuel recursive body
        };
      XECase scrutinee alternatives -> evaluateCase (executeST fuel) scope scrutinee alternatives;
      _ ->
        do {
          fs <- gets functions;
          case O.applications expression of {
            Pair (XEPrimitive PSTReturn) (Cons value Nil) -> thunk scope value;
            Pair (XEPrimitive PSTBind) (Cons action (Cons next Nil)) ->
              do {
                value <- executeST fuel scope action;
                case next of {
                  XEAbs n body ->
                    executeST fuel (M.insert O.compareName n (CGBinding value False) scope) body;
                  _ ->
                    do {
                      continuation <- thunk scope next;
                      following <-
                        call "@mlf_application" (args2 (pointer continuation) (pointer value));
                      call "@mlf_execute_st_lazy" (args1 (pointer following))
                    }
                }
              };
            Pair (XEPrimitive PIfThenElse) (Cons condition (Cons yes (Cons no Nil))) ->
              do {
                value <- evaluate scope condition;
                test <- result ("icmp eq ptr " ++ (value ++ (", " ++ immediate 6)));
                choose "ptr" test (executeST fuel scope yes) (executeST fuel scope no)
              };
            Pair (XEPrimitive PSeq) (Cons first (Cons next Nil)) ->
              do {
                evaluate scope first;
                executeST fuel scope next
              };
            Pair (XEVar n) args ->
              case M.lookup O.compareName n fs of {
                Just f ->
                  if (L.length args == L.length (A.parameters f))
                  then do {
                         symbol <- stateWorker n f;
                         captured <- capturedArguments scope f;
                         values <- ordinaryArguments scope f args;
                         call symbol
                           (Cons ("i64 " ++ fuel) (L.map pointer (L.append captured values)))
                       }
                  else executeSTFallback scope expression;
                Nothing -> executeSTFallback scope expression
              };
            Pair (XEPrimitive p) args ->
              case stateHelper p of {
                Just (Pair symbol strict) ->
                  if (L.length args == L.length strict)
                  then do {
                         values <-
                           L.mapM
                             (\entry ->
                                case entry of {
                                  Pair demanded argument ->
                                    if demanded
                                    then evaluate scope argument
                                    else thunk scope argument
                                })
                             (L.zip strict args);
                         case p of {
                           PReadSTArray -> stateArray p values;
                           PWriteSTArray -> stateArray p values;
                           PLengthSTArray -> stateArray p values;
                           _ -> call symbol (L.map pointer values)
                         }
                       }
                  else executeSTFallback scope expression;
                Nothing -> executeSTFallback scope expression
              };
            _ -> executeSTFallback scope expression
          }
        }
    };
  executeSTFallback :: Map XName CGBinding -> XErased -> Build String;
  executeSTFallback scope expression =
    do {
      action <- evaluate scope expression;
      call "@mlf_execute_st_lazy" (args1 (pointer action))
    };
  stateHelper :: Primitive -> Maybe (Pair String (List Bool));
  stateHelper primitive =
    case primitive of {
      PNewSTArray -> Just (Pair "@mlf_st_new_array" (args2 True False));
      PReadSTArray -> Just (Pair "@mlf_st_read_array" (args2 True True));
      PWriteSTArray -> Just (Pair "@mlf_st_write_array" (args3 True True False));
      PLengthSTArray -> Just (Pair "@mlf_st_length_array" (args1 True));
      _ -> Nothing
    };
  -- Execute checked state-array access directly, preserving bounds failures and
  -- lazy cell values. The runtime still allocates arrays and handles opaque ST.
  stateArray :: Primitive -> List String -> Build String;
  stateArray p values =
    case values of {
      Nil -> failure "LLVM missing state array";
      Cons array rest ->
        do {
          boundValueShared1 <- arrayView array;
          case boundValueShared1 of {
            Pair len cells ->
              do {
                let {
                  lengthOnly =
                    case p of {
                      PLengthSTArray -> True;
                      _ -> False
                    }
                };
                if lengthOnly
                then do {
                       shifted <- result ("shl i64 " ++ (len ++ ", 1"));
                       bits <- result ("or i64 " ++ (shifted ++ ", 1"));
                       result ("inttoptr i64 " ++ (bits ++ " to ptr"))
                     }
                else case rest of {
                       Nil -> failure "LLVM missing state array index";
                       Cons index entries ->
                         do {
                           bits <- result ("ptrtoint ptr " ++ (index ++ " to i64"));
                           i <- result ("ashr i64 " ++ (bits ++ ", 1"));
                           low <- result ("and i64 " ++ (bits ++ ", 1"));
                           tag <- result ("icmp ne i64 " ++ (low ++ ", 0"));
                           bounds <- result ("icmp ult i64 " ++ (i ++ (", " ++ len)));
                           ok <- result ("and i1 " ++ (tag ++ (", " ++ bounds)));
                           valid <- fresh "state.valid.";
                           invalid <- fresh "state.invalid.";
                           emit
                             ("  br i1 " ++
                              (ok ++ (", label %" ++ (valid ++ (", label %" ++ invalid)))));
                           label invalid;
                           emit "  call void @mlf_bounds_failure()";
                           emit "  unreachable";
                           label valid;
                           address <-
                             result ("getelementptr ptr, ptr " ++ (cells ++ (", i64 " ++ i)));
                           let {
                             readOnly =
                               case p of {
                                 PReadSTArray -> True;
                                 _ -> False
                               }
                           };
                           if readOnly
                           then result ("load ptr, ptr " ++ (address ++ ", align 8, !tbaa !4"))
                           else case entries of {
                                  Cons entry Nil ->
                                    do {
                                      emit
                                        ("  store ptr " ++
                                         (entry ++
                                          (", ptr " ++ (address ++ ", align 8, !tbaa !4"))));
                                      cgPure (immediate 4)
                                    };
                                  _ -> failure "LLVM missing state array value"
                                }
                         }
                     }
              }
          }
        }
    };
  -- Single-use action aliases remain in the execution context above; ordinary
  -- values retain the same demand and sharing rules as ordinary code generation.
  executeSTLet :: String -> Map XName CGBinding -> XName -> XErased -> XErased -> Build String;
  executeSTLet fuel scope n rhs body =
    do {
      fs <- gets functions;
      if M.member O.compareName n fs
      then executeST fuel scope body
      else do {
             let {
               strict = S.member O.compareName n (A.demanded fs body)
             };
             value <- if strict then evaluate scope rhs else thunk scope rhs;
             executeST fuel (M.insert O.compareName n (CGBinding value strict) scope) body
           }
    };
  -- Tail transfers preserve the current frame's budget. Only equal worker
  -- signatures use musttail; non-tail calls still consume bounded fuel.
  executeSTTail :: Int -> String -> String -> Map XName CGBinding -> XErased -> Build Unit;
  executeSTTail arity tailFuel fuel scope expression =
    case expression of {
      XELet n rhs body ->
        case body of {
          XEApp (XEApp (XEPrimitive PSTBind) (XEVar use)) next ->
            if (O.eqName n use && L.not (S.member O.compareName n (O.free next)))
            then executeSTTail arity tailFuel fuel scope
                   (XEApp (XEApp (XEPrimitive PSTBind) rhs) next)
            else executeSTTailLet arity tailFuel fuel scope n rhs body;
          XEVar use ->
            if O.eqName n use
            then executeSTTail arity tailFuel fuel scope rhs
            else executeSTTailLet arity tailFuel fuel scope n rhs body;
          _ -> executeSTTailLet arity tailFuel fuel scope n rhs body
        };
      XELetRec bindings body ->
        do {
          fs <- gets functions;
          let {
            values =
              L.filter
                (\entry ->
                   case entry of {
                     Pair n a -> L.not (M.member O.compareName n fs)
                   })
                bindings
          };
          holes <-
            L.mapM
              (\entry ->
                 case entry of {
                   Pair n ignored ->
                     do {
                       hole <- call "@mlf_hole" Nil;
                       cgPure (Pair n (CGBinding hole False))
                     }
                 })
              values;
          let {
            recursive = M.union O.compareName (M.fromList O.compareName holes) scope
          };
          L.mapM_
            (\entry ->
               case entry of {
                 Pair n rhs ->
                   do {
                     value <- thunk recursive rhs;
                     hole <- lookupName recursive n;
                     emit
                       ("  call void @mlf_fill(ptr " ++
                        (operand hole ++ (", ptr " ++ (value ++ ")"))))
                   }
               })
            values;
          executeSTTail arity tailFuel fuel recursive body
        };
      XECase scrutinee alternatives ->
        finishCase (executeSTTail arity tailFuel fuel) scope scrutinee alternatives;
      _ ->
        do {
          fs <- gets functions;
          case O.applications expression of {
            Pair (XEPrimitive PSTBind) (Cons action (Cons (XEAbs n body) Nil)) ->
              do {
                value <- executeST fuel scope action;
                executeSTTail arity tailFuel fuel
                  (M.insert O.compareName n (CGBinding value False) scope)
                  body
              };
            Pair (XEPrimitive PIfThenElse) (Cons condition (Cons yes (Cons no Nil))) ->
              do {
                value <- evaluate scope condition;
                test <- result ("icmp eq ptr " ++ (value ++ (", " ++ immediate 6)));
                finishChoice test (executeSTTail arity tailFuel fuel scope yes)
                  (executeSTTail arity tailFuel fuel scope no)
              };
            Pair (XEPrimitive PSeq) (Cons first (Cons next Nil)) ->
              do {
                evaluate scope first;
                executeSTTail arity tailFuel fuel scope next
              };
            Pair (XEVar n) args ->
              case M.lookup O.compareName n fs of {
                Just f ->
                  if ((L.length args == L.length (A.parameters f)) &&
                      ((L.length (A.captures f) + L.length args) == arity))
                  then do {
                         symbol <- stateWorker n f;
                         captured <- capturedArguments scope f;
                         values <- ordinaryArguments scope f args;
                         value <-
                           result
                             ("musttail call ptr " ++
                              (symbol ++
                               ("(" ++
                                (L.intercalate ", "
                                   (Cons ("i64 " ++ tailFuel)
                                      (L.map pointer (L.append captured values))) ++
                                 ")"))));
                         emit ("  ret ptr " ++ value)
                       }
                  else finishST fuel scope expression;
                Nothing -> finishST fuel scope expression
              };
            _ -> finishST fuel scope expression
          }
        }
    };
  executeSTTailLet :: Int ->
                      String ->
                      String -> Map XName CGBinding -> XName -> XErased -> XErased -> Build Unit;
  executeSTTailLet arity tailFuel fuel scope n rhs body =
    do {
      fs <- gets functions;
      if M.member O.compareName n fs
      then executeSTTail arity tailFuel fuel scope body
      else do {
             let {
               strict = S.member O.compareName n (A.demanded fs body)
             };
             value <- if strict then evaluate scope rhs else thunk scope rhs;
             executeSTTail arity tailFuel fuel
               (M.insert O.compareName n (CGBinding value strict) scope)
               body
           }
    };
  finishST :: String -> Map XName CGBinding -> XErased -> Build Unit;
  finishST fuel scope expression =
    do {
      value <- executeST fuel scope expression;
      emit ("  ret ptr " ++ value)
    };
  restoreBranchCaches :: Output -> Output -> Output;
  restoreBranchCaches saved state =
    withScalarRanges (scalarRanges saved)
      (withArrayViews (arrayViews saved)
         (withUnboxedDoubles (unboxedDoubles saved) (withForcedValues (forcedValues saved) state)));
  finishChoice :: String -> Build Unit -> Build Unit -> Build Unit;
  finishChoice condition yes no =
    do {
      saved <- get;
      yesLabel <- fresh "yes.";
      noLabel <- fresh "no.";
      emit ("  br i1 " ++ (condition ++ (", label %" ++ (yesLabel ++ (", label %" ++ noLabel)))));
      label yesLabel;
      yes;
      modify (restoreBranchCaches saved);
      label noLabel;
      no
    };
  finishCase :: (Map XName CGBinding -> XErased -> Build Unit) ->
                Map XName CGBinding -> XErased -> List XErasedAlternative -> Build Unit;
  finishCase finish scope scrutinee alternatives =
    case alternatives of {
      Cons (XErasedAlternative (XDefaultPattern name) body) Nil ->
        do {
          value <- thunk scope scrutinee;
          finish (bindOptional name (CGBinding value False) scope) body
        };
      _ ->
        do {
          value <- evaluate scope scrutinee;
          tag <- constructorTag value;
          labelled <-
            L.mapM
              (\a ->
                 do {
                   entry <- fresh "case.";
                   cgPure (Pair entry a)
                 })
              alternatives;
          missing <- fresh "case.missing.";
          let {
            fallback = L.fromMaybe missing (caseFallback labelled)
          };
          entries <- L.mapM caseSwitchEntry labelled;
          emit ("  switch i64 " ++ (tag ++ (", label %" ++ (fallback ++ " ["))));
          L.mapM_ emit (L.concat entries);
          emit "  ]";
          saved <- get;
          L.mapM_
            (\entry ->
               case entry of {
                 Pair name (XErasedAlternative pattern body) ->
                   do {
                     modify (restoreBranchCaches saved);
                     label name;
                     local <- caseScope scope value pattern body;
                     finish local body
                   }
               })
            labelled;
          if eqString fallback missing
          then do {
                 label missing;
                 emit "  call void @mlf_match_failure()";
                 emit "  unreachable"
               }
          else cgPure Unit
        }
    };
  stateWorker :: XName -> A.WorkerFunction -> Build String;
  -- Preserve the explicit runtime stack for arbitrarily deep state binds.
  stateWorker name f =
    do {
      let {
        symbol = ("@mlf.st.worker." ++ showInt (O.nameId name))
      };
      let {
        names = L.append (A.captures f) (A.parameters f)
      };
      let {
        registers = L.map (\i -> ("%a" ++ showInt i)) (L.range 0 (L.length names - 1))
      };
      seen <- gets (\state -> S.member O.compareName name (stateWorkers state));
      if seen
      then cgPure Unit
      else do {
             modify
               (\state ->
                  withStateWorkers (S.insert O.compareName name (stateWorkers state)) state);
             let {
               scope =
                 M.fromList O.compareName
                   (L.zipWith
                      (\n register ->
                         Pair n (CGBinding register (S.member O.compareName n (A.strict f))))
                      names
                      registers)
             };
             definitionBody symbol (Cons "i64 %st.fuel" (L.map pointer registers))
               (do {
                  exhausted <- result "icmp eq i64 %st.fuel, 0";
                  finishChoice exhausted
                    (do {
                       value <- executeSTFallback scope (A.functionBody f);
                       emit ("  ret ptr " ++ value)
                     })
                    (do {
                       fuel <- result "sub i64 %st.fuel, 1";
                       executeSTTail (L.length names) "%st.fuel" fuel scope (A.functionBody f)
                     })
                })
           };
      cgPure symbol
    };
  application :: Map XName CGBinding -> XErased -> Build String;
  -- Checked Bool values in WHNF use the canonical immediates 2 and 6.
  application scope expression =
    do {
      fs <- gets functions;
      case O.applications expression of {
        Pair (XEVar n) args ->
          case M.lookup O.compareName n fs of {
            Just f ->
              if (L.length args == L.length (A.parameters f))
              then invoke scope n f args
              else genericApplication scope expression;
            Nothing -> genericApplication scope expression
          };
        Pair (XEPrimitive PIfThenElse) (Cons c (Cons a (Cons b Nil))) ->
          do {
            condition <- evaluate scope c;
            test <- result ("icmp eq ptr " ++ (condition ++ (", " ++ immediate 6)));
            choose "ptr" test (evaluate scope a) (evaluate scope b)
          };
        Pair (XEPrimitive PRunST) (Cons action Nil) ->
          do {
            value <- executeST "512" scope action;
            forceBinding (CGBinding value False)
          };
        Pair (XEPrimitive PSeq) (Cons a (Cons b Nil)) ->
          do {
            evaluate scope a;
            evaluate scope b
          };
        Pair (XEPrimitive p) args ->
          if (L.length args == P.primitiveArity p)
          then primitiveApplication scope p args
          else genericApplication scope expression;
        Pair (XEConstructor c) args ->
          do {
            constructor <- lookupConstructor c;
            case constructor of {
              Pair tag arity ->
                if (L.length args == arity)
                then do {
                       fields <- L.mapM (thunk scope) args;
                       constructorValue tag fields
                     }
                else genericApplication scope expression
            }
          };
        _ -> genericApplication scope expression
      }
    };
  primitiveApplication :: Map XName CGBinding -> Primitive -> List XErased -> Build String;
  primitiveApplication scope p args =
    do {
      values <- L.mapM (if P.primitiveStrict p then evaluate scope else thunk scope) args;
      inline <- gets inlinePrimitives;
      if L.not inline
      then primitiveCall p values
      else case values of {
             Cons a (Cons b Nil) ->
               case p of {
                 PAddInt -> integerOperation p a b;
                 PSubInt -> integerOperation p a b;
                 PMulInt -> N.numericProduct p a b;
                 PQuotInt -> N.numericProduct p a b;
                 PRemInt -> N.numericProduct p a b;
                 PEqInt -> integerOperation p a b;
                 PLtInt -> integerOperation p a b;
                 PAddDouble -> doubleOperation p a b;
                 PSubDouble -> doubleOperation p a b;
                 PMulDouble -> doubleOperation p a b;
                 PDivDouble -> doubleOperation p a b;
                 PEqDouble -> doubleOperation p a b;
                 PLtDouble -> doubleOperation p a b;
                 _ -> primitiveCall p values
               };
             Cons a Nil ->
               case p of {
                 PSqrtDouble ->
                   do {
                     x <- loadAt "double" a 8;
                     n <- result ("call double @llvm.sqrt.f64(double " ++ (x ++ ")"));
                     call "@mlf_double" (args1 ("double " ++ n))
                   };
                 _ -> primitiveCall p values
               };
             _ -> primitiveCall p values
           }
    };
  primitiveCall :: Primitive -> List String -> Build String;
  primitiveCall p values =
    call ("@mlf_prim" ++ showInt (L.length values))
      (Cons (number (P.primitiveCode p)) (L.map pointer values));
  genericApplication :: Map XName CGBinding -> XErased -> Build String;
  genericApplication scope expression =
    case expression of {
      XEApp f a ->
        do {
          function <- thunk scope f;
          argument <- thunk scope a;
          app <- call "@mlf_application" (args2 (pointer function) (pointer argument));
          forceValue app
        };
      _ -> failure "LLVM expected application"
    };
  -- Mirror the runtime's non-evaluating WHNF test for the compact layout.
  -- A single thunk can use its own update root directly. Mark it busy before
  -- calling, clear captures through its callback, then force and memoize its
  -- result. Runtime fallback preserves null/cycle errors and longer spines.
  forceDefinition :: List String;
  forceDefinition =
    Cons "define private ptr @mlf.force(ptr %value) alwaysinline {"
      (Cons "entry:"
         (Cons "  %null = icmp eq ptr %value, null"
            (Cons "  br i1 %null, label %slow, label %test"
               (Cons "test:"
                  (Cons "  %bits = ptrtoint ptr %value to i64"
                     (Cons "  %kind = and i64 %bits, 7"
                        (Cons "  %immediate = icmp ne i64 %kind, 0"
                           (Cons "  br i1 %immediate, label %done, label %tagged"
                              (Cons "tagged:"
                                 (Cons "  %tag = load i32, ptr %value, align 4"
                                    (Cons "  %ready = icmp uge i32 %tag, 5"
                                       (Cons "  br i1 %ready, label %done, label %deferred"
                                          (Cons "deferred:"
                                             (Cons "  %isthunk = icmp eq i32 %tag, 3"
                                                (Cons
                                                   "  br i1 %isthunk, label %enter, label %indirect"
                                                   (Cons "indirect:"
                                                      (Cons "  %forwarded = icmp eq i32 %tag, 2"
                                                         (Cons
                                                            "  br i1 %forwarded, label %next, label %slow"
                                                            (Cons "next:"
                                                               (Cons
                                                                  "  %slot = getelementptr i8, ptr %value, i64 8"
                                                                  (Cons
                                                                     "  %p = load ptr, ptr %slot, align 8"
                                                                     (Cons
                                                                        "  %missing = icmp eq ptr %p, null"
                                                                        (Cons
                                                                           "  br i1 %missing, label %slow, label %nexttest"
                                                                           (Cons "nexttest:"
                                                                              (Cons
                                                                                 "  %pbits = ptrtoint ptr %p to i64"
                                                                                 (Cons
                                                                                    "  %pkind = and i64 %pbits, 7"
                                                                                    (Cons
                                                                                       "  %pimm = icmp ne i64 %pkind, 0"
                                                                                       (Cons
                                                                                          "  br i1 %pimm, label %forward, label %ptagged"
                                                                                          (Cons
                                                                                             "ptagged:"
                                                                                             (Cons
                                                                                                "  %ptag = load i32, ptr %p, align 4"
                                                                                                (Cons
                                                                                                   "  %pready = icmp uge i32 %ptag, 5"
                                                                                                   (Cons
                                                                                                      "  br i1 %pready, label %forward, label %slow"
                                                                                                      (Cons
                                                                                                         "forward:"
                                                                                                         (Cons
                                                                                                            "  ret ptr %p"
                                                                                                            (Cons
                                                                                                               "done:"
                                                                                                               (Cons
                                                                                                                  "  ret ptr %value"
                                                                                                                  (Cons
                                                                                                                     "enter:"
                                                                                                                     (Cons
                                                                                                                        "  %code.slot = getelementptr i8, ptr %value, i64 8"
                                                                                                                        (Cons
                                                                                                                           "  %env.slot = getelementptr i8, ptr %value, i64 16"
                                                                                                                           (Cons
                                                                                                                              "  %code = load ptr, ptr %code.slot, align 8"
                                                                                                                              (Cons
                                                                                                                                 "  %env = load ptr, ptr %env.slot, align 8"
                                                                                                                                 (Cons
                                                                                                                                    "  store i32 1, ptr %value, align 4"
                                                                                                                                    (Cons
                                                                                                                                       "  store ptr null, ptr %code.slot, align 8"
                                                                                                                                       (Cons
                                                                                                                                          "  store ptr null, ptr %env.slot, align 8"
                                                                                                                                          (Cons
                                                                                                                                             "  %returned = call ptr %code(ptr %env, ptr null)"
                                                                                                                                             (Cons
                                                                                                                                                "  %canonical = call ptr @mlf_force(ptr %returned)"
                                                                                                                                                (Cons
                                                                                                                                                   "  store i32 2, ptr %value, align 4"
                                                                                                                                                   (Cons
                                                                                                                                                      "  store ptr %canonical, ptr %code.slot, align 8"
                                                                                                                                                      (Cons
                                                                                                                                                         "  ret ptr %canonical"
                                                                                                                                                         (Cons
                                                                                                                                                            "slow:"
                                                                                                                                                            (Cons
                                                                                                                                                               "  %result = tail call ptr @mlf_force(ptr %value)"
                                                                                                                                                               (Cons
                                                                                                                                                                  "  ret ptr %result"
                                                                                                                                                                  (Cons
                                                                                                                                                                     "}"
                                                                                                                                                                     Nil)))))))))))))))))))))))))))))))))))))))))))))))))))));
  aliasMetadata :: List String;
  aliasMetadata =
    Cons "!0 = !{!\"MLF storage\"}"
      (Cons "!1 = !{!\"managed object\", !0}"
         (Cons "!2 = !{!\"array cells\", !0}"
            (Cons "!3 = !{!1, !1, i64 0}" (Cons "!4 = !{!2, !2, i64 0}" Nil))));
  runtimeDeclarations :: List String;
  runtimeDeclarations =
    Cons "declare ptr @mlf_execute_st_lazy(ptr)"
      (Cons "declare ptr @mlf_st_new_array(ptr, ptr)"
         (Cons "declare ptr @mlf_st_read_array(ptr, ptr)"
            (Cons "declare ptr @mlf_st_write_array(ptr, ptr, ptr)"
               (Cons "declare ptr @mlf_st_length_array(ptr)"
                  (Cons "declare void @mlf_set_args(i32, ptr)"
                     (Cons "declare ptr @mlf_env_new(i64)"
                        (Cons "declare void @mlf_env_set(ptr, i64, ptr)"
                           (Cons "declare ptr @mlf_env_get(ptr, i64)"
                              (Cons "declare ptr @mlf_thunk(ptr, ptr)"
                                 (Cons "declare ptr @mlf_closure(ptr, ptr)"
                                    (Cons "declare ptr @mlf_application(ptr, ptr)"
                                       (Cons "declare ptr @mlf_hole()"
                                          (Cons "declare void @mlf_fill(ptr, ptr)"
                                             (Cons "declare ptr @mlf_integer(ptr)"
                                                (Cons "declare ptr @mlf_string(ptr, i64)"
                                                   (Cons "declare ptr @mlf_double(double)"
                                                      (Cons "declare double @llvm.sqrt.f64(double)"
                                                         (Cons
                                                            "declare double @mlf_int_to_double(ptr)"
                                                            (Cons
                                                               "declare ptr @mlf_read_int_table(ptr, ptr)"
                                                               (Cons
                                                                  "declare ptr @mlf_write_int_table(ptr, ptr, ptr)"
                                                                  (Cons
                                                                     "declare ptr @mlf_add_int_table(ptr, ptr, ptr)"
                                                                     (Cons
                                                                        "declare void @mlf_roots_enter(ptr, i64, ptr)"
                                                                        (Cons
                                                                           "declare void @mlf_roots_leave(ptr)"
                                                                           (Cons
                                                                              "declare void @mlf_gc_check(i64, ptr)"
                                                                              (Cons
                                                                                 "declare ptr @mlf_get_byte_line()"
                                                                                 (Cons
                                                                                    "declare ptr @mlf_new_array(i64, ptr, ptr)"
                                                                                    (Cons
                                                                                       "declare ptr @mlf_bytes_from_string(ptr)"
                                                                                       (Cons
                                                                                          "declare ptr @mlf_put_bytes(ptr, ptr, ptr)"
                                                                                          (Cons
                                                                                             "declare ptr @mlf_new_int_table()"
                                                                                             (Cons
                                                                                                "declare void @llvm.memmove.p0.p0.i64(ptr, ptr, i64, i1)"
                                                                                                (Cons
                                                                                                   "declare i8 @mlf_byte(ptr)"
                                                                                                   (Cons
                                                                                                      "declare ptr @mlf_peek(ptr)"
                                                                                                      (Cons
                                                                                                         "declare ptr @mlf_native_io(ptr, ptr)"
                                                                                                         (Cons
                                                                                                            "declare void @mlf_bounds_failure() noreturn"
                                                                                                            (Cons
                                                                                                               "declare ptr @mlf_primitive(i64)"
                                                                                                               (Cons
                                                                                                                  "declare ptr @mlf_prim1(i64, ptr)"
                                                                                                                  (Cons
                                                                                                                     "declare ptr @mlf_prim2(i64, ptr, ptr)"
                                                                                                                     (Cons
                                                                                                                        "declare i64 @mlf_truth(ptr)"
                                                                                                                        (Cons
                                                                                                                           "declare ptr @mlf_prim3(i64, ptr, ptr, ptr)"
                                                                                                                           (Cons
                                                                                                                              "declare ptr @mlf_force(ptr)"
                                                                                                                              (Cons
                                                                                                                                 "declare ptr @mlf_add_int(ptr, ptr)"
                                                                                                                                 (Cons
                                                                                                                                    "declare ptr @mlf_sub_int(ptr, ptr)"
                                                                                                                                    (Cons
                                                                                                                                       "declare ptr @mlf_eq_int(ptr, ptr)"
                                                                                                                                       (Cons
                                                                                                                                          "declare ptr @mlf_lt_int(ptr, ptr)"
                                                                                                                                          (Cons
                                                                                                                                             "declare ptr @mlf_constructor(i64, i64)"
                                                                                                                                             (Cons
                                                                                                                                                "declare ptr @mlf_constructor1(i64, ptr)"
                                                                                                                                                (Cons
                                                                                                                                                   "declare ptr @mlf_constructor2(i64, ptr, ptr)"
                                                                                                                                                   (Cons
                                                                                                                                                      "declare ptr @mlf_constructor_fields(i64, ptr)"
                                                                                                                                                      (Cons
                                                                                                                                                         "declare ptr @mlf_constructor_new(i64, i64)"
                                                                                                                                                         (Cons
                                                                                                                                                            "declare ptr @mlf_field(ptr, i64)"
                                                                                                                                                            (Cons
                                                                                                                                                               "declare void @mlf_match_failure() noreturn"
                                                                                                                                                               (Cons
                                                                                                                                                                  "declare { i64, i1 } @llvm.sadd.with.overflow.i64(i64, i64)"
                                                                                                                                                                  (Cons
                                                                                                                                                                     "declare { i64, i1 } @llvm.smul.with.overflow.i64(i64, i64)"
                                                                                                                                                                     (Cons
                                                                                                                                                                        "declare { i64, i1 } @llvm.ssub.with.overflow.i64(i64, i64)"
                                                                                                                                                                        (Cons
                                                                                                                                                                           "declare i32 @mlf_run(ptr, i64)"
                                                                                                                                                                           (Cons
                                                                                                                                                                              ""
                                                                                                                                                                              Nil))))))))))))))))))))))))))))))))))))))))))))))))))))))));
  -- Shared helpers keep emitted modules small; LLVM inlines their fast paths.
  allocationDefinition :: List String;
  allocationDefinition =
    Cons "@mlf_constructor_pending = external global [33 x ptr]"
      (Cons "declare ptr @mlf_constructor_allocate(i64, i64)"
         (Cons
            "define private ptr @mlf.allocate.constructor(i64 %identity, i64 %count, i64 %size) alwaysinline {"
            (Cons "entry:"
               (Cons "  %small = icmp ule i64 %size, 256"
                  (Cons "  br i1 %small, label %batch, label %slow"
                     (Cons "batch:"
                        (Cons "  %index = lshr i64 %size, 3"
                           (Cons
                              "  %slot = getelementptr [33 x ptr], ptr @mlf_constructor_pending, i64 0, i64 %index"
                              (Cons "  %value = load ptr, ptr %slot, align 8"
                                 (Cons "  %empty = icmp eq ptr %value, null"
                                    (Cons "  br i1 %empty, label %slow, label %ready"
                                       (Cons "ready:"
                                          (Cons "  %next = load ptr, ptr %value, align 8"
                                             (Cons "  store ptr %next, ptr %slot, align 8"
                                                (Cons "  store i64 0, ptr %value, align 8"
                                                   (Cons "  ret ptr %value"
                                                      (Cons "slow:"
                                                         (Cons
                                                            "  %allocated = call ptr @mlf_constructor_allocate(i64 %identity, i64 %count)"
                                                            (Cons "  ret ptr %allocated"
                                                               (Cons "}"
                                                                  (Cons
                                                                     "define private ptr @mlf.construct.1(i64 %identity, ptr %a) alwaysinline {"
                                                                     (Cons "entry:"
                                                                        (Cons
                                                                           "  %value = call ptr @mlf.allocate.constructor(i64 %identity, i64 1, i64 24)"
                                                                           (Cons
                                                                              "  store i32 12, ptr %value, align 4"
                                                                              (Cons
                                                                                 "  %id = getelementptr i8, ptr %value, i64 8"
                                                                                 (Cons
                                                                                    "  store i64 %identity, ptr %id, align 8"
                                                                                    (Cons
                                                                                       "  %first = getelementptr i8, ptr %value, i64 16"
                                                                                       (Cons
                                                                                          "  store ptr %a, ptr %first, align 8"
                                                                                          (Cons
                                                                                             "  ret ptr %value"
                                                                                             (Cons
                                                                                                "}"
                                                                                                (Cons
                                                                                                   "define private ptr @mlf.construct.2(i64 %identity, ptr %a, ptr %b) alwaysinline {"
                                                                                                   (Cons
                                                                                                      "entry:"
                                                                                                      (Cons
                                                                                                         "  %value = call ptr @mlf.allocate.constructor(i64 %identity, i64 2, i64 32)"
                                                                                                         (Cons
                                                                                                            "  store i32 13, ptr %value, align 4"
                                                                                                            (Cons
                                                                                                               "  %id = getelementptr i8, ptr %value, i64 8"
                                                                                                               (Cons
                                                                                                                  "  store i64 %identity, ptr %id, align 8"
                                                                                                                  (Cons
                                                                                                                     "  %first = getelementptr i8, ptr %value, i64 16"
                                                                                                                     (Cons
                                                                                                                        "  store ptr %a, ptr %first, align 8"
                                                                                                                        (Cons
                                                                                                                           "  %second = getelementptr i8, ptr %value, i64 24"
                                                                                                                           (Cons
                                                                                                                              "  store ptr %b, ptr %second, align 8"
                                                                                                                              (Cons
                                                                                                                                 "  ret ptr %value"
                                                                                                                                 (Cons
                                                                                                                                    "}"
                                                                                                                                    (Cons
                                                                                                                                       "define private ptr @mlf.construct.wide(i64 %identity, i64 %count) alwaysinline {"
                                                                                                                                       (Cons
                                                                                                                                          "entry:"
                                                                                                                                          (Cons
                                                                                                                                             "  %fields = mul i64 %count, 8"
                                                                                                                                             (Cons
                                                                                                                                                "  %size = add i64 %fields, 24"
                                                                                                                                                (Cons
                                                                                                                                                   "  %value = call ptr @mlf.allocate.constructor(i64 %identity, i64 %count, i64 %size)"
                                                                                                                                                   (Cons
                                                                                                                                                      "  store i32 28, ptr %value, align 4"
                                                                                                                                                      (Cons
                                                                                                                                                         "  %id = getelementptr i8, ptr %value, i64 8"
                                                                                                                                                         (Cons
                                                                                                                                                            "  store i64 %identity, ptr %id, align 8"
                                                                                                                                                            (Cons
                                                                                                                                                               "  %arity = getelementptr i8, ptr %value, i64 16"
                                                                                                                                                               (Cons
                                                                                                                                                                  "  store i64 %count, ptr %arity, align 8"
                                                                                                                                                                  (Cons
                                                                                                                                                                     "  ret ptr %value"
                                                                                                                                                                     (Cons
                                                                                                                                                                        "}"
                                                                                                                                                                        Nil))))))))))))))))))))))))))))))))))))))))))))))))))))));
  -- Only positive capture counts up to 28 reach this helper. They use the
  -- same rounded, traced allocation class as gc_malloc; captures start clear.
  -- The slow path handles initialization, refill and debug allocations.
  thunkAllocationDefinition :: List String;
  thunkAllocationDefinition =
    Cons "@mlf_compact_pending = external global [17 x ptr]"
      (Cons "define private ptr @mlf.allocate.thunk(ptr %code, i64 %count) alwaysinline {"
         (Cons "entry:"
            (Cons "  %words = add i64 %count, 4"
               (Cons "  %index = lshr i64 %words, 1"
                  (Cons
                     "  %slot = getelementptr [17 x ptr], ptr @mlf_compact_pending, i64 0, i64 %index"
                     (Cons "  %value = load ptr, ptr %slot, align 8"
                        (Cons "  %empty = icmp eq ptr %value, null"
                           (Cons "  br i1 %empty, label %slow, label %ready"
                              (Cons "ready:"
                                 (Cons "  %next = load ptr, ptr %value, align 8"
                                    (Cons "  store ptr %next, ptr %slot, align 8"
                                       (Cons "  store i64 3, ptr %value, align 8"
                                          (Cons "  %function = getelementptr i8, ptr %value, i64 8"
                                             (Cons "  store ptr %code, ptr %function, align 8"
                                                (Cons
                                                   "  %environment = getelementptr i8, ptr %value, i64 24"
                                                   (Cons
                                                      "  %capture = getelementptr i8, ptr %value, i64 16"
                                                      (Cons
                                                         "  store ptr %environment, ptr %capture, align 8"
                                                         (Cons
                                                            "  store i64 %count, ptr %environment, align 8"
                                                            (Cons "  ret ptr %value"
                                                               (Cons "slow:"
                                                                  (Cons
                                                                     "  %allocated = call ptr @mlf_thunk_new(ptr %code, i64 %count)"
                                                                     (Cons "  ret ptr %allocated"
                                                                        (Cons "}"
                                                                           Nil)))))))))))))))))))))))
}
