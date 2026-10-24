-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Bootstrap.Runtime where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Data as D;
  import qualified Bootstrap.Primitive as P;
  import qualified Bootstrap.ProcessHost as ProcessHost;
  import qualified Bootstrap.X.Check as C;
  import qualified Bootstrap.X.Syntax as X;
  -- The host's lazy fields supply call-by-need for interpreted closures and
  -- recursive environments. Effects stay in explicit action values until run.
  data REnv =
    REnv (Map XName (Either String RValue)) |
    RLocal XName (Either String RValue) REnv |
    RRecursive (Map XName (Either String RValue)) REnv;
  data RValue =
    RInteger Int |
    RDouble Double |
    RBoolean Bool |
    RString String |
    RChar Int |
    RIOError (Either String RValue) |
    RIntArray IntArray |
    RDoubleArray DoubleArray |
    RByteArray ByteArray |
    RIntTable IntTable |
    RClosure REnv XName XErased |
    RConstructor String (List (Either String RValue)) |
    RConstructorFunction String Int (List (Either String RValue)) |
    RPrimitive Primitive (List (Either String RValue)) |
    RAction Primitive (List (Either String RValue)) |
    RSTAction Primitive (List (Either String RValue)) |
    RSTArrayHandle Int |
    RAsyncScopeHandle Int |
    RCompletionHandle Int Int |
    RAsyncSubscriptionHandle Int Int Int;
  -- Catchable IO failure is distinct from fatal evaluator errors and from a
  -- successfully returned value whose demand may fail later. Messages retain
  -- their canonical lazy [Char] representation, including surrogate codepoints.
  data RIOOutcome =
    RIOSuccess (Either String RValue) |
    RIOFailure (Either String RValue);
  -- Primitive payloads represent the language value itself. Forcing only the
  -- interpreter's wrapper would leave strict numeric accumulators suspended.
  -- Algebraic fields, closures and actions retain their ordinary lazy behavior.
  forceValue :: RValue -> RValue;
  forceValue value =
    case value of {
      RInteger n -> seq n value;
      RDouble n -> seq n value;
      RBoolean b -> seq b value;
      RString text -> seq text value;
      RChar n -> seq n value;
      RIntArray array -> seq array value;
      RDoubleArray array -> seq array value;
      RByteArray array -> seq array value;
      RIntTable table -> seq table value;
      RSTArrayHandle handle -> seq handle value;
      RAsyncScopeHandle handle -> seq handle value;
      RCompletionHandle owner handle -> seq owner (seq handle value);
      RAsyncSubscriptionHandle owner handle status -> seq owner (seq handle (seq status value));
      _ -> value
    };
  runTerm :: XTerm -> IO (Either String Unit);
  runTerm term = runTermWithArguments Nil term;
  runProgram :: XTerm -> IO (Either String Unit);
  runProgram term = runProgramWithArguments Nil term;
  runTermWithArguments :: List String -> XTerm -> IO (Either String Unit);
  runTermWithArguments args term = runEntry True args term;
  runProgramWithArguments :: List String -> XTerm -> IO (Either String Unit);
  runProgramWithArguments args term = runEntry False args term;
  isIO :: XType -> Bool;
  isIO ty =
    case ty of {
      XForall a lower body -> isIO body;
      XCon name (Cons arg Nil) -> eqString name "IO";
      _ -> False
    };
  declarations term =
    case term of {
      XWithData ds body -> ds;
      _ -> Nil
    };
  prepare :: Bool -> XTerm -> Either String (Pair DataEnv Bool);
  prepare requireIO term =
    do {
      ty <- mapLeft (\message -> ("target verification failed: " ++ message)) (C.checkClosed term);
      ensure (not requireIO || isIO ty) "program must have type IO a to run";
      ds <- D.validateDeclarations (declarations term);
      Right (Pair ds (isIO ty))
    };
  runEntry requireIO args term =
    case prepare requireIO term of {
      Left message -> ioReturn (Left message);
      Right (Pair ds action) ->
        let {
          value = evaluate ds (REnv M.empty) (X.erase term)
        } in
        if action
        then ioBind ProcessHost.begin
               (\checkpoint ->
                  ioBind (runAction args ds value)
                    (\result ->
                       ioBind (ProcessHost.finish checkpoint result)
                         (\cleaned -> ioReturn (mapEither (\ignored -> Unit) cleaned))))
        else ioReturn (mapEither (\v -> seq (forceValue v) Unit) value)
    };
  envLookup :: XName -> REnv -> Maybe (Either String RValue);
  envLookup n env =
    case env of {
      REnv values -> M.lookup compareName n values;
      RLocal key value parent ->
        if (nameId n == nameId key) then Just value else envLookup n parent;
      RRecursive values parent ->
        case M.lookup compareName n values of {
          Just value -> Just value;
          Nothing -> envLookup n parent
        }
    };
  envInsert n value env = RLocal n value env;
  envExtend entries env =
    foldlStrict
      (\scope entry ->
         case entry of {
           Pair name value -> envInsert name value scope
         })
      env
      entries;
  recursiveEnv :: DataEnv -> REnv -> List (Pair XName XErased) -> REnv;
  recursiveEnv ds env bindings =
    let {
      result :: REnv;
      result =
        RRecursive
          (M.fromList compareName
             (map
                (\entry ->
                   case entry of {
                     Pair name rhs -> Pair name (evaluate ds result rhs)
                   })
                bindings))
          env
    } in
    result;
  evaluate :: DataEnv -> REnv -> XErased -> Either String RValue;
  evaluate ds env expression =
    case expression of {
      XEVar n ->
        case envLookup n env of {
          Nothing -> Left ("unbound runtime variable: " ++ nameHint n);
          Just value -> value
        };
      XEAbs name body -> Right (RClosure env name body);
      XEApp f a -> evaluateApplication ds env f a;
      XELet name rhs body -> evaluate ds (envInsert name (evaluate ds env rhs) env) body;
      XELetRec bindings body -> evaluate ds (recursiveEnv ds env bindings) body;
      XEInt n -> Right (RInteger n);
      XEDouble n -> Right (RDouble n);
      XEBool b -> Right (RBoolean b);
      XEString s -> Right (RString s);
      XEPrimitive primitive -> runtimePrimitive ds primitive Nil;
      XEConstructor name ->
        bindEither (D.lookupConstructor ds name)
          (\entry ->
             case entry of {
               Pair _ constructor ->
                 let {
                   remaining = length (D.constructorFields constructor)
                 } in
                 Right
                   (if (remaining == 0)
                    then RConstructor name Nil
                    else RConstructorFunction name remaining Nil)
             });
      XECase scrutinee alternatives -> choose ds env (evaluate ds env scrutinee) alternatives;
      XEEvidenceHole ignored -> Left "unresolved runtime dictionary evidence"
    };
  -- A syntactically known primitive has no effects or failure before saturation.
  -- Build its lazy argument list once instead of allocating partial RPrimitive
  -- values and Either wrappers at each application. Overapplication still takes
  -- the ordinary path, preserving the result's function/error behavior.
  evaluateApplication :: DataEnv -> REnv -> XErased -> XErased -> Either String RValue;
  evaluateApplication ds env function argument =
    case function of {
      XEPrimitive primitive ->
        if (P.primitiveArity primitive >= 1)
        then runtimePrimitive ds primitive (Cons (evaluate ds env argument) Nil)
        else evaluateOrdinaryApplication ds env function argument;
      XEApp first second ->
        case first of {
          XEPrimitive primitive ->
            if (P.primitiveArity primitive >= 2)
            then runtimePrimitive ds primitive
                   (Cons (evaluate ds env second) (Cons (evaluate ds env argument) Nil))
            else evaluateOrdinaryApplication ds env function argument;
          XEApp (XEPrimitive primitive) initial ->
            if (P.primitiveArity primitive >= 3)
            then runtimePrimitive ds primitive
                   (Cons (evaluate ds env initial)
                      (Cons (evaluate ds env second) (Cons (evaluate ds env argument) Nil)))
            else evaluateOrdinaryApplication ds env function argument;
          _ -> evaluateOrdinaryApplication ds env function argument
        };
      _ -> evaluateOrdinaryApplication ds env function argument
    };
  evaluateOrdinaryApplication :: DataEnv -> REnv -> XErased -> XErased -> Either String RValue;
  evaluateOrdinaryApplication ds env function argument =
    bindEither (evaluate ds env function) (\value -> apply ds value (evaluate ds env argument));
  choose :: DataEnv ->
            REnv -> Either String RValue -> List XErasedAlternative -> Either String RValue;
  choose ds env value alternatives =
    case alternatives of {
      Nil -> Left "non-exhaustive runtime case";
      Cons (XErasedAlternative pattern body) rest ->
        case pattern of {
          XDefaultPattern name -> evaluate ds (maybe env (\n -> envInsert n value env) name) body;
          XConstructorPattern constructor names ->
            bindEither value
              (\v ->
                 case constructorView v of {
                   RConstructor tag fields ->
                     if eqString constructor tag
                     then if (length names == length fields)
                          then evaluate ds
                                 (envExtend
                                    (catMaybes
                                       (zipWith
                                          (\name field -> mapOptional (\n -> Pair n field) name)
                                          names
                                          fields))
                                    env)
                                 body
                          else Left "runtime constructor pattern arity mismatch"
                     else choose ds env value rest;
                   _ -> Left "constructor pattern matched a non-data value"
                 })
        }
    };
  constructorView :: RValue -> RValue;
  constructorView value =
    case value of {
      RConstructorFunction name _ fields -> RConstructor name fields;
      _ -> value
    };
  apply :: DataEnv -> RValue -> Either String RValue -> Either String RValue;
  apply ds function argument =
    case function of {
      RClosure env name body -> evaluate ds (envInsert name argument env) body;
      RConstructorFunction name remaining fields ->
        let {
          next = snoc fields argument
        } in
        if (remaining <= 0)
        then Left "runtime constructor overapplication"
        else Right
               (if (remaining == 1)
                then RConstructor name next
                else RConstructorFunction name (remaining - 1) next);
      RConstructor name fields ->
        bindEither (D.lookupConstructor ds name)
          (\entry ->
             case entry of {
               Pair declaration constructor ->
                 if (length fields < length (D.constructorFields constructor))
                 then Right (RConstructor name (snoc fields argument))
                 else Left "runtime constructor overapplication"
             });
      RPrimitive primitive arguments -> runtimePrimitive ds primitive (snoc arguments argument);
      _ -> Left "runtime application of a non-function"
    };
  integer :: Either String RValue -> Either String Int;
  integer thunk =
    bindEither thunk
      (\value ->
         case value of {
           RInteger n -> Right n;
           _ -> Left "runtime primitive expected Int"
         });
  floating :: Either String RValue -> Either String Double;
  floating thunk =
    bindEither thunk
      (\value ->
         case value of {
           RDouble n -> Right n;
           _ -> Left "runtime primitive expected Double"
         });
  string :: Either String RValue -> Either String String;
  string thunk =
    bindEither thunk
      (\value ->
         case value of {
           RString s -> Right s;
           _ -> Left "runtime primitive expected String"
         });
  boolean :: Either String RValue -> Either String Bool;
  boolean thunk =
    bindEither thunk
      (\value ->
         case value of {
           RBoolean b -> Right b;
           _ -> Left "runtime primitive expected Bool"
         });
  intArray :: Either String RValue -> Either String IntArray;
  intArray thunk =
    bindEither thunk
      (\value ->
         case value of {
           RIntArray a -> Right a;
           _ -> Left "runtime primitive expected IntArray"
         });
  doubleArray :: Either String RValue -> Either String DoubleArray;
  doubleArray thunk =
    bindEither thunk
      (\value ->
         case value of {
           RDoubleArray a -> Right a;
           _ -> Left "runtime primitive expected DoubleArray"
         });
  byteArray :: Either String RValue -> Either String ByteArray;
  byteArray thunk =
    bindEither thunk
      (\value ->
         case value of {
           RByteArray a -> Right a;
           _ -> Left "runtime primitive expected ByteArray"
         });
  intTable :: Either String RValue -> Either String IntTable;
  intTable thunk =
    bindEither thunk
      (\value ->
         case value of {
           RIntTable a -> Right a;
           _ -> Left "runtime primitive expected IntTable"
         });
  character :: Either String RValue -> Either String Int;
  character thunk =
    bindEither thunk
      (\value -> case value of {
         RChar n -> Right n;
         _ -> Left "runtime primitive expected Char"
       });
  runtimeIOError :: Either String RValue -> Either String (Either String RValue);
  runtimeIOError thunk =
    bindEither thunk
      (\value -> case value of {
         RIOError message -> Right message;
         _ -> Left "runtime primitive expected IOError"
       });
  runtimeTextChars :: String -> Int -> RValue;
  runtimeTextChars text index =
    if index == stringLength text
    then RConstructor "[]" Nil
    else RConstructor ":"
           (Cons (Right (RChar (stringCodeAt text index)))
              (Cons (Right (runtimeTextChars text (index + 1))) Nil));
  runtimeCharsText :: Either String RValue -> Either String String;
  runtimeCharsText thunk =
    bindEither (runtimeCharsChunks False thunk) (\chunks -> Right (concatStrings chunks));
  runtimeCharsChunks :: Bool -> Either String RValue -> Either String (List String);
  runtimeCharsChunks diagnostic thunk =
    bindEither thunk
      (\value -> case value of {
         RConstructor name fields ->
           case fields of {
             Nil -> if eqString name "[]" then Right Nil
                    else Left "runtime primitive expected [Char]";
             Cons first (Cons rest Nil) ->
               if eqString name ":"
               then do {
                 code <- character first;
                 let { scalar = ((code < 55296) || (code > 57343)) };
                 ensure (diagnostic || scalar) "invalid Unicode scalar";
                 chunks <- runtimeCharsChunks diagnostic rest;
                 Right (Cons (if scalar then stringFromCode code else ("\\" ++ showInt code)) chunks)
               }
               else Left "runtime primitive expected [Char]";
             _ -> Left "runtime primitive expected [Char]"
           };
         _ -> Left "runtime primitive expected [Char]"
       });
  integer2 f a b =
    do {
      x <- integer a;
      y <- integer b;
      Right (RInteger (f x y))
    };
  double2 f a b =
    do {
      x <- floating a;
      y <- floating b;
      Right (RDouble (f x y))
    };
  intCompare f a b =
    do {
      x <- integer a;
      y <- integer b;
      Right (RBoolean (f x y))
    };
  doubleCompare f a b =
    do {
      x <- floating a;
      y <- floating b;
      Right (RBoolean (f x y))
    };
  divide f a b =
    do {
      x <- integer a;
      y <- integer b;
      ensure (y /= 0) "integer division by zero";
      Right (RInteger (f x y))
    };
  isAction primitive =
    let {
      n = P.primitiveCode primitive
    } in
    ((n == 100) || ((n == 101) || ((n <= 5) ||
     (((n >= 27) && (n <= 44)) || (((n >= 56) && (n <= 65)) || ((n >= 73) && (n <= 94)))))));
  isSTAction primitive =
    case primitive of {
      PSTReturn -> True;
      PSTBind -> True;
      PNewSTArray -> True;
      PReadSTArray -> True;
      PWriteSTArray -> True;
      PLengthSTArray -> True;
      _ -> False
    };
  runtimePrimitive :: DataEnv -> Primitive -> List (Either String RValue) -> Either String RValue;
  runtimePrimitive ds primitive arguments =
    let {
      arity = P.primitiveArity primitive
    } in
    if (length arguments < arity)
    then Right (RPrimitive primitive arguments)
    else if not (length arguments == arity)
         then Left ("runtime primitive arity mismatch: " ++ P.primitiveName primitive)
         else if isAction primitive
              then Right (RAction primitive arguments)
              else if isSTAction primitive
                   then Right (RSTAction primitive arguments)
                   else primitiveResult ds primitive arguments;
  primitiveResult :: DataEnv -> Primitive -> List (Either String RValue) -> Either String RValue;
  primitiveResult ds primitive arguments =
    let {
      a = head arguments
    } in
    let {
      b = head (tail arguments)
    } in
    let {
      c = head (tail (tail arguments))
    } in
    case primitive of {
      PTextToChars -> mapEither (\text -> runtimeTextChars text 0) (string a);
      PTextFromChars -> mapEither RString (runtimeCharsText a);
      PCharCode -> mapEither RInteger (character a);
      PCharFromCode -> do {
        code <- integer a;
        ensure ((code >= 0) && (code <= 1114111)) "invalid Char codepoint";
        Right (RChar code)
      };
      PUserError -> Right (RIOError a);
      PIOErrorString -> bindEither (runtimeIOError a) (\message -> message);
      PRunST -> runStateRegion ds a;
      PConcatString ->
        do {
          x <- string a;
          y <- string b;
          Right (RString (x ++ y))
        };
      PShowInt -> mapEither (\n -> RString (showInt n)) (integer a);
      PAddInt -> integer2 addInt a b;
      PSubInt -> integer2 subInt a b;
      PMulInt -> integer2 mulInt a b;
      PAndInt -> integer2 andInt a b;
      PQuotInt -> divide quotInt a b;
      PRemInt -> divide remInt a b;
      PReadInt ->
        bindEither (string a)
          (\s ->
             if validInteger s then Right (RInteger (readInt s)) else Left "invalid integer input");
      PEqInt -> intCompare eqInt a b;
      PLtInt -> intCompare ltInt a b;
      PAddDouble -> double2 addDouble a b;
      PSubDouble -> double2 subDouble a b;
      PMulDouble -> double2 mulDouble a b;
      PDivDouble -> double2 divDouble a b;
      PSqrtDouble -> mapEither (\n -> RDouble (sqrtDouble n)) (floating a);
      PEqDouble -> doubleCompare eqDouble a b;
      PLtDouble -> doubleCompare ltDouble a b;
      PIntToDouble -> mapEither (\n -> RDouble (intToDouble n)) (integer a);
      PFormatDouble ->
        do {
          places <- integer a;
          n <- floating b;
          ensure ((places >= 0) && (places <= 17)) "Double precision must be between 0 and 17";
          Right (RString (formatDouble places n))
        };
      PEqString ->
        do {
          x <- string a;
          y <- string b;
          Right (RBoolean (eqString x y))
        };
      PIfThenElse -> bindEither (boolean a) (\choice -> if choice then b else c);
      PStringLength -> mapEither (\s -> RInteger (stringLength s)) (string a);
      PStringCodeAt ->
        do {
          s <- string a;
          i <- integer b;
          ensure ((i >= 0) && (i < stringLength s)) "string index out of bounds";
          Right (RInteger (stringCodeAt s i))
        };
      PStringSlice ->
        do {
          s <- string a;
          i <- integer b;
          n <- integer c;
          ensure ((i >= 0) && ((i <= stringLength s) && ((n >= 0) && (n <= (stringLength s - i)))))
            "string slice out of bounds";
          Right (RString (stringSlice s i n))
        };
      PStringFromCode ->
        do {
          n <- integer a;
          ensure ((n >= 0) && ((n <= 1114111) && ((n < 55296) || (n > 57343))))
            "invalid Unicode scalar";
          Right (RString (stringFromCode n))
        };
      PCompareString ->
        do {
          x <- string a;
          y <- string b;
          Right (RInteger (compareString x y))
        };
      PReadDouble ->
        bindEither (string a)
          (\s ->
             if validDecimal s
             then Right (RDouble (readDouble s))
             else Left "invalid Double input");
      PDoubleToBits -> mapEither (\n -> RInteger (doubleToBits n)) (floating a);
      PDoubleFromBits ->
        do {
          n <- integer a;
          ensure ((n >= 0) && (n <= 18446744073709551615)) "Double bit pattern out of bounds";
          Right (RDouble (doubleFromBits n))
        };
      PSeq -> bindEither a (\value -> seq (forceValue value) b);
      PPanic -> bindEither (string a) Left;
      _ -> Left ("runtime primitive arity mismatch: " ++ P.primitiveName primitive)
    };
  isDigit c = ((c >= 48) && (c <= 57));
  skipSign s i =
    if ((i < stringLength s) && ((stringCodeAt s i == 43) || (stringCodeAt s i == 45)))
    then (i + 1)
    else i;
  skipDigits :: String -> Int -> Int;
  skipDigits s i =
    if ((i < stringLength s) && isDigit (stringCodeAt s i)) then skipDigits s (i + 1) else i;
  validInteger s =
    let {
      start = skipSign s 0
    } in
    ((start < stringLength s) && (skipDigits s start == stringLength s));
  validExponent s i =
    if (i == stringLength s)
    then True
    else if ((stringCodeAt s i == 101) || (stringCodeAt s i == 69))
         then let {
                start = skipSign s (i + 1)
              } in
              ((start < stringLength s) && (skipDigits s start == stringLength s))
         else False;
  validDecimal s =
    let {
      start = skipSign s 0
    } in
    let {
      end = skipDigits s start
    } in
    if (start == end)
    then False
    else if ((end < stringLength s) && (stringCodeAt s end == 46))
         then let {
                fraction = skipDigits s (end + 1)
              } in
              ((fraction > (end + 1)) && validExponent s fraction)
         else validExponent s end;
  unit = Right (RConstructor "Unit" Nil);
  -- Each runST starts a fresh persistent store. The checked region type keeps
  -- handles local to this store; no host mutation or IO operation is involved.
  -- Keeping the default cell separate avoids allocating or forcing every slot.
  data RSTArrayState = RSTArrayState Int (Either String RValue) (Map Int (Either String RValue));
  data RSTStore = RSTStore Int (Map Int RSTArrayState);
  stateArray n initial cells = seq n (seq cells (RSTArrayState n initial cells));
  stateStore next arrays = seq next (seq arrays (RSTStore next arrays));
  stateArrayHandle :: Either String RValue -> Either String Int;
  stateArrayHandle thunk =
    bindEither thunk
      (\value ->
         case value of {
           RSTArrayHandle handle -> Right handle;
           _ -> Left "runtime primitive expected STArray"
         });
  stateArrayLookup :: Int -> Map Int RSTArrayState -> Either String RSTArrayState;
  stateArrayLookup handle arrays =
    case M.lookup compareInt handle arrays of {
      Nothing -> Left "STArray does not belong to this region";
      Just array -> Right array
    };
  runStateRegion :: DataEnv -> Either String RValue -> Either String RValue;
  runStateRegion ds action =
    bindEither (runStateAction ds (stateStore 0 M.empty) action Nil)
      (\result ->
         case result of {
           Pair finalStore value ->
             bindEither value (\ready -> seq (forceValue ready) (Right ready))
         });
  -- Continuations contain unevaluated callback values. Results are thunks:
  -- a read returns the cell from this immutable store version, so a later
  -- write cannot change an earlier read even if its value is forced later.
  runStateAction :: DataEnv ->
                    RSTStore ->
                    Either String RValue ->
                    List (Either String RValue) ->
                    Either String (Pair RSTStore (Either String RValue));
  runStateAction ds store thunk continuations =
    bindEither thunk
      (\value ->
         case value of {
           RSTAction primitive arguments -> performState ds store primitive arguments continuations;
           _ -> Left "runtime expected an ST action"
         });
  resumeState :: DataEnv ->
                 RSTStore ->
                 Either String RValue ->
                 List (Either String RValue) ->
                 Either String (Pair RSTStore (Either String RValue));
  resumeState ds store value continuations =
    seq store
      (case continuations of {
         Nil -> Right (Pair store value);
         Cons next rest ->
           bindEither next (\function -> runStateAction ds store (apply ds function value) rest)
       });
  performState :: DataEnv ->
                  RSTStore ->
                  Primitive ->
                  List (Either String RValue) ->
                  List (Either String RValue) ->
                  Either String (Pair RSTStore (Either String RValue));
  performState ds store primitive arguments continuations =
    let {
      a = head arguments
    } in
    let {
      b = head (tail arguments)
    } in
    let {
      c = head (tail (tail arguments))
    } in
    case primitive of {
      PSTReturn -> resumeState ds store a continuations;
      PSTBind -> runStateAction ds store a (Cons b continuations);
      PNewSTArray ->
        do {
          n <- arraySize a;
          case store of {
            RSTStore next arrays ->
              let {
                array = stateArray n b M.empty
              } in
              let {
                updated = stateStore (next + 1) (M.insert compareInt next array arrays)
              } in
              resumeState ds updated (Right (RSTArrayHandle next)) continuations
          }
        };
      PReadSTArray ->
        do {
          handle <- stateArrayHandle a;
          case store of {
            RSTStore next arrays ->
              do {
                array <- stateArrayLookup handle arrays;
                case array of {
                  RSTArrayState n initial cells ->
                    do {
                      index <- arrayIndex n b;
                      resumeState ds store (M.findWithDefault compareInt initial index cells)
                        continuations
                    }
                }
              }
          }
        };
      PWriteSTArray ->
        do {
          handle <- stateArrayHandle a;
          case store of {
            RSTStore next arrays ->
              do {
                array <- stateArrayLookup handle arrays;
                case array of {
                  RSTArrayState n initial cells ->
                    do {
                      index <- arrayIndex n b;
                      let {
                        updatedArray = stateArray n initial (M.insert compareInt index c cells)
                      };
                      let {
                        updated = stateStore next (M.insert compareInt handle updatedArray arrays)
                      };
                      seq updatedArray (resumeState ds updated unit continuations)
                    }
                }
              }
          }
        };
      PLengthSTArray ->
        do {
          handle <- stateArrayHandle a;
          case store of {
            RSTStore next arrays ->
              do {
                array <- stateArrayLookup handle arrays;
                case array of {
                  RSTArrayState n initial cells ->
                    resumeState ds store (Right (RInteger n)) continuations
                }
              }
          }
        };
      _ -> Left "runtime ST action primitive arity mismatch"
    };
  wrapIO :: forall a. IO a -> (a -> RValue) -> IO (Either String (Either String RValue));
  wrapIO action wrap = ioBind action (\value -> ioReturn (Right (Right (wrap value))));
  finishIO action = ioBind action (\ignored -> ioReturn (Right unit));
  checkedIO :: forall a b. Either String a -> (a -> IO (Either String b)) -> IO (Either String b);
  checkedIO result next =
    case result of {
      Left message -> ioReturn (Left message);
      Right value -> next value
    };
  runAction :: List String ->
               DataEnv -> Either String RValue -> IO (Either String (Either String RValue));
  runAction args ds thunk =
    ioBind (runActionState args ds rAsyncEmpty thunk)
      (\result -> ioReturn
         (bindEither result
            (\(Pair _ outcome) -> case outcome of {
               RIOSuccess value -> Right value;
               RIOFailure message ->
                 bindEither (runtimeCharsChunks True message)
                   (\chunks -> Left ("user error (" ++ concatStrings chunks ++ ")"))
             })));
  perform :: List String ->
             DataEnv ->
             Primitive -> List (Either String RValue) -> IO (Either String (Either String RValue));
  perform args ds primitive arguments =
    if ((P.primitiveCode primitive == 1) ||
        ((P.primitiveCode primitive == 100) || (P.primitiveCode primitive == 101)))
    then runAction args ds (Right (RAction primitive arguments))
    else let {
      a = head arguments
    } in
    let {
      b = head (tail arguments)
    } in
    let {
      c = head (tail (tail arguments))
    } in
    case primitive of {
      PIOReturn -> ioReturn (Right a);
      PIOBind ->
        ioBind (runAction args ds a)
          (\result ->
             case result of {
               Left message -> ioReturn (Left message);
               Right value ->
                 runAction args ds (bindEither b (\function -> apply ds function value))
             });
      PGetLine -> wrapIO getLine RString;
      PPutStr -> checkedIO (string a) (\s -> finishIO (putStr s));
      PPutStrLn -> checkedIO (string a) (\s -> finishIO (putStrLn s));
      PPrintInt -> checkedIO (integer a) (\n -> finishIO (printInt n));
      PNewIntArray ->
        checkedIO
          (do {
             n <- arraySize a;
             x <- integer b;
             Right (Pair n x)
           })
          (\entry ->
             case entry of {
               Pair n x -> wrapIO (newIntArray n x) RIntArray
             });
      PNewDoubleArray ->
        checkedIO
          (do {
             n <- arraySize a;
             x <- floating b;
             Right (Pair n x)
           })
          (\entry ->
             case entry of {
               Pair n x -> wrapIO (newDoubleArray n x) RDoubleArray
             });
      PNewByteArray ->
        checkedIO
          (do {
             n <- arraySize a;
             x <- byte b;
             Right (Pair n x)
           })
          (\entry ->
             case entry of {
               Pair n x -> wrapIO (newByteArray n x) RByteArray
             });
      PReadIntArray ->
        checkedIO (intArray a)
          (\array ->
             ioBind (lengthIntArray array)
               (\n -> checkedIO (arrayIndex n b) (\i -> wrapIO (readIntArray array i) RInteger)));
      PReadDoubleArray ->
        checkedIO (doubleArray a)
          (\array ->
             ioBind (lengthDoubleArray array)
               (\n -> checkedIO (arrayIndex n b) (\i -> wrapIO (readDoubleArray array i) RDouble)));
      PReadByteArray ->
        checkedIO (byteArray a)
          (\array ->
             ioBind (lengthByteArray array)
               (\n -> checkedIO (arrayIndex n b) (\i -> wrapIO (readByteArray array i) RInteger)));
      PWriteIntArray ->
        checkedIO (intArray a)
          (\array ->
             ioBind (lengthIntArray array)
               (\n ->
                  checkedIO
                    (do {
                       i <- arrayIndex n b;
                       x <- integer c;
                       Right (Pair i x)
                     })
                    (\entry ->
                       case entry of {
                         Pair i x -> finishIO (writeIntArray array i x)
                       })));
      PWriteDoubleArray ->
        checkedIO (doubleArray a)
          (\array ->
             ioBind (lengthDoubleArray array)
               (\n ->
                  checkedIO
                    (do {
                       i <- arrayIndex n b;
                       x <- floating c;
                       Right (Pair i x)
                     })
                    (\entry ->
                       case entry of {
                         Pair i x -> finishIO (writeDoubleArray array i x)
                       })));
      PWriteByteArray ->
        checkedIO (byteArray a)
          (\array ->
             ioBind (lengthByteArray array)
               (\n ->
                  checkedIO
                    (do {
                       i <- arrayIndex n b;
                       x <- byte c;
                       Right (Pair i x)
                     })
                    (\entry ->
                       case entry of {
                         Pair i x -> finishIO (writeByteArray array i x)
                       })));
      PLengthIntArray -> checkedIO (intArray a) (\array -> wrapIO (lengthIntArray array) RInteger);
      PLengthDoubleArray ->
        checkedIO (doubleArray a) (\array -> wrapIO (lengthDoubleArray array) RInteger);
      PLengthByteArray ->
        checkedIO (byteArray a) (\array -> wrapIO (lengthByteArray array) RInteger);
      PByteArrayFromString ->
        checkedIO (string a) (\s -> wrapIO (byteArrayFromString s) RByteArray);
      PPutBytes ->
        checkedIO (byteArray a)
          (\array ->
             ioBind (lengthByteArray array)
               (\n ->
                  checkedIO (byteSlice n b c)
                    (\slice ->
                       case slice of {
                         Pair offset count -> finishIO (putBytes array offset count)
                       })));
      PGetByteLine -> wrapIO getByteLine RByteArray;
      PNewIntTable -> wrapIO newIntTable RIntTable;
      PReadIntTable ->
        checkedIO
          (do {
             table <- intTable a;
             key <- integer b;
             Right (Pair table key)
           })
          (\entry ->
             case entry of {
               Pair table key -> wrapIO (readIntTable table key) RInteger
             });
      PWriteIntTable ->
        checkedIO
          (do {
             table <- intTable a;
             key <- integer b;
             value <- integer c;
             Right (Triple table key value)
           })
          (\entry ->
             case entry of {
               Triple table key value -> finishIO (writeIntTable table key value)
             });
      PReadFile -> checkedIO (path a) (\file -> wrapIO (readFile file) RString);
      PWriteFile ->
        checkedIO
          (do {
             file <- path a;
             text <- string b;
             Right (Pair file text)
           })
          (\entry ->
             case entry of {
               Pair file text -> finishIO (writeFile file text)
             });
      PFileExists -> checkedIO (path a) (\file -> wrapIO (fileExists file) RBoolean);
      PCanonicalPath -> checkedIO (path a) (\file -> wrapIO (canonicalPath file) RString);
      PGetArgCount -> ioReturn (Right (Right (RInteger (length args))));
      PGetArg ->
        checkedIO (integer a)
          (\i ->
             case at i args of {
               Nothing -> ioReturn (Left "argument index out of bounds");
               Just argument -> ioReturn (Right (Right (RString argument)))
             });
      PPutErr -> checkedIO (string a) (\s -> finishIO (putErr s));
      PExitWith ->
        checkedIO (integer a)
          (\status ->
             if ((status < 0) || (status > 255))
             then ioReturn (Left "exit status must be between 0 and 255")
             else exitWith status);
      PGetExecutablePath -> wrapIO getExecutablePath RString;
      PGetContents -> wrapIO getContents RString;
      PGetEnv -> checkedIO (path a) (\x -> wrapIO (getEnv x) RString);
      PSetEnv ->
        checkedIO
          (do {
             x <- path a;
             y <- string b;
             Right (Pair x y)
           })
          (\pair ->
             case pair of {
               Pair x y -> finishIO (setEnv x y)
             });
      PUnsetEnv -> checkedIO (path a) (\x -> finishIO (unsetEnv x));
      PRunProcess ->
        checkedIO
          (do {
             x <- path a;
             y <- string b;
             Right (Pair x y)
           })
          (\pair ->
             case pair of {
               Pair x y -> wrapIO (runProcess x y) RInteger
             });
      PListDirectory -> checkedIO (path a) (\x -> wrapIO (listDirectory x) RString);
      PDirectoryExists -> checkedIO (path a) (\x -> wrapIO (directoryExists x) RBoolean);
      PFileDigest -> checkedIO (path a) (\x -> wrapIO (fileDigest x) RString);
      PAcquireFileLock -> checkedIO (path a) (\x -> wrapIO (acquireFileLock x) RInteger);
      PReleaseFileLock -> checkedIO (integer a) (\x -> finishIO (releaseFileLock x));
      PProcessSupervisor ->
        checkedIO (string a) (\request -> wrapIO (ProcessHost.request request) RString);
      _ -> ioReturn (Left "runtime action primitive arity mismatch")
    };
  arraySize a =
    do {
      n <- integer a;
      ensure ((n >= 0) && (n <= 1152921504606846975)) "invalid array length";
      Right n
    };
  byte a =
    do {
      n <- integer a;
      ensure ((n >= 0) && (n <= 255)) "byte value must be between 0 and 255";
      Right n
    };
  arrayIndex size a =
    do {
      n <- integer a;
      ensure ((n >= 0) && (n < size)) "array index out of bounds";
      Right n
    };
  byteSlice size offset count =
    do {
      i <- integer offset;
      ensure ((i >= 0) && (i <= size)) "byte slice out of bounds";
      n <- integer count;
      ensure ((n >= 0) && (n <= (size - i))) "byte slice out of bounds";
      Right (Pair i n)
    };
  path a =
    do {
      name <- string a;
      ensure (not (hasNul name 0)) "file path contains NUL";
      Right name
    };
  hasNul :: String -> Int -> Bool;
  hasNul s i =
    if (i >= stringLength s) then False else ((stringCodeAt s i == 0) || hasNul s (i + 1));
  -- Completion state belongs to one interpreted IO execution. Handles remain
  -- opaque RValue variants; no source operation turns an Int into a typed cell.
  -- Callback/result thunks remain lazy fields in this persistent, traced store.
  data RAsyncScopeState =
    RAsyncScopeState Bool Bool Int Int (List Int) (List Int) (List Int) (List (Pair Int Int));
  data RAsyncCellState = RAsyncCellState Int (Maybe (Either String RValue)) (List Int);
  data RAsyncSubscriptionState =
    RAsyncSubscriptionState Int (Maybe Int) (Either String RValue) (Maybe (Either String RValue));
  data RAsyncStore =
    RAsyncStore Int Int Int (Map Int RAsyncScopeState) (Map Int RAsyncCellState) (Map Int
                                                                                  RAsyncSubscriptionState);
  rAsyncStore ns nc nt scopes cells tickets =
    seq ns
      (seq nc
         (seq nt
            (seq scopes (seq cells (seq tickets (RAsyncStore ns nc nt scopes cells tickets))))));
  rAsyncEmpty = rAsyncStore 0 0 0 M.empty M.empty M.empty;
  rAsyncLookupScope :: RAsyncStore -> Int -> Either String RAsyncScopeState;
  rAsyncLookupScope (RAsyncStore ns _ _ scopes _ _) identity =
    case M.lookup compareInt identity scopes of {
      Nothing ->
        if ((identity >= 0) && (identity < ns))
        then Right (RAsyncScopeState True False 0 0 Nil Nil Nil Nil)
        else Left "unknown async scope";
      Just scope -> Right scope
    };
  rAsyncLookupCell :: RAsyncStore -> Int -> Either String RAsyncCellState;
  rAsyncLookupCell (RAsyncStore _ _ _ _ cells _) identity =
    case M.lookup compareInt identity cells of {
      Nothing -> Left "unknown completion cell";
      Just cell -> Right cell
    };
  rAsyncLookupTicket (RAsyncStore _ _ _ _ _ tickets) identity =
    M.lookup compareInt identity tickets;
  rAsyncSetScope (RAsyncStore ns nc nt scopes cells tickets) identity scope =
    rAsyncStore ns nc nt (M.insert compareInt identity scope scopes) cells tickets;
  rAsyncSetCell (RAsyncStore ns nc nt scopes cells tickets) identity cell =
    rAsyncStore ns nc nt scopes (M.insert compareInt identity cell cells) tickets;
  rAsyncSetTicket (RAsyncStore ns nc nt scopes cells tickets) identity ticket =
    rAsyncStore ns nc nt scopes cells (M.insert compareInt identity ticket tickets);
  rAsyncRemoveIdentity identity values = filter (\value -> (value /= identity)) values;
  rAsyncClosed (RAsyncScopeState closed _ _ _ _ _ _ _) = closed;
  rAsyncBusy (RAsyncScopeState _ busy _ _ _ _ _ _) = busy;
  rAsyncSetBusy :: RAsyncStore -> Int -> Bool -> Either String RAsyncStore;
  rAsyncSetBusy store identity busy =
    do {
      boundValueShared1 <- rAsyncLookupScope store identity;
      case boundValueShared1 of {
        RAsyncScopeState closed _ cellLimit callbackLimit cells tickets ready timers ->
          do {
            Right
              (if closed
               then store
               else rAsyncSetScope store identity
                      (RAsyncScopeState closed busy cellLimit callbackLimit cells tickets ready
                         timers))
          }
      }
    };
  rAsyncScopeHandle :: Either String RValue -> Either String Int;
  rAsyncScopeHandle value =
    bindEither value
      (\entry ->
         case entry of {
           RAsyncScopeHandle identity -> Right identity;
           _ -> Left "runtime primitive expected AsyncScope"
         });
  rAsyncCellHandle :: Either String RValue -> Either String (Pair Int Int);
  rAsyncCellHandle value =
    bindEither value
      (\entry ->
         case entry of {
           RCompletionHandle owner identity -> Right (Pair owner identity);
           _ -> Left "runtime primitive expected Completion"
         });
  rAsyncTicketHandle :: Either String RValue -> Either String (Triple Int Int Int);
  rAsyncTicketHandle value =
    bindEither value
      (\entry ->
         case entry of {
           RAsyncSubscriptionHandle owner identity status -> Right (Triple owner identity status);
           _ -> Left "runtime primitive expected AsyncSubscription"
         });
  rAsyncFinished store value = ioReturn (Right (Pair store (RIOSuccess (Right value))));
  rAsyncNewScope (RAsyncStore ns nc nt scopes cells tickets) cellLimit callbackLimit =
    let {
      scope = RAsyncScopeState False False cellLimit callbackLimit Nil Nil Nil Nil
    } in
    Pair (rAsyncStore (ns + 1) nc nt (M.insert compareInt ns scope scopes) cells tickets)
      (RAsyncScopeHandle ns);
  rAsyncClose :: RAsyncStore -> Int -> Either String RAsyncStore;
  rAsyncClose store identity =
    do {
      boundValueShared2 <- rAsyncLookupScope store identity;
      case boundValueShared2 of {
        RAsyncScopeState closed busy cellLimit callbackLimit ownedCells ownedTickets ready timers ->
          do {
            if closed
            then Right store
            else case store of {
                   RAsyncStore ns nc nt scopes cells tickets ->
                     let {
                       remainingCells =
                         foldlStrict (\table key -> M.delete compareInt key table) cells ownedCells
                     } in
                     let {
                       remainingTickets =
                         foldlStrict (\table key -> M.delete compareInt key table) tickets
                           ownedTickets
                     } in
                     Right
                       (rAsyncStore ns nc nt (M.delete compareInt identity scopes) remainingCells
                          remainingTickets)
                 }
          }
      }
    };
  rAsyncNewCell :: RAsyncStore -> Int -> Either String (Pair RAsyncStore (Maybe RValue));
  rAsyncNewCell store owner =
    do {
      boundValueShared3 <- rAsyncLookupScope store owner;
      case boundValueShared3 of {
        RAsyncScopeState closed busy cellLimit callbackLimit ownedCells ownedTickets ready timers ->
          do {
            if (closed || (length ownedCells >= cellLimit))
            then Right (Pair store Nothing)
            else case store of {
                   RAsyncStore ns nc nt scopes cells tickets ->
                     let {
                       scope =
                         RAsyncScopeState closed busy cellLimit callbackLimit (Cons nc ownedCells)
                           ownedTickets
                           ready
                           timers
                     } in
                     let {
                       updated =
                         rAsyncStore ns (nc + 1) nt (M.insert compareInt owner scope scopes)
                           (M.insert compareInt nc (RAsyncCellState owner Nothing Nil) cells)
                           tickets
                     } in
                     Right (Pair updated (Just (RCompletionHandle owner nc)))
                 }
          }
      }
    };
  rAsyncResolve :: RAsyncStore -> Int -> Int -> Either String RValue -> Either String (Pair RAsyncStore Int);
  rAsyncResolve store owner identity payload =
    do {
      scope <- rAsyncLookupScope store owner;
      if rAsyncClosed scope
      then Right (Pair store 3)
      else do {
             boundValueShared4 <- rAsyncLookupCell store identity;
             case boundValueShared4 of {
               RAsyncCellState cellOwner result waiters ->
                 do {
                   ensure (cellOwner == owner) "completion owner mismatch";
                   case result of {
                     Just _ -> Right (Pair store 2);
                     Nothing ->
                       do {
                         updated <-
                           foldM
                             (\current ticketId ->
                                case rAsyncLookupTicket current ticketId of {
                                  Nothing -> Left "missing completion waiter";
                                  Just (RAsyncSubscriptionState ticketOwner cell callback _) ->
                                    Right
                                      (rAsyncSetTicket current ticketId
                                         (RAsyncSubscriptionState ticketOwner cell callback
                                            (Just payload)))
                                })
                             store
                             waiters;
                         case scope of {
                           RAsyncScopeState closed busy cellLimit callbackLimit ownedCells ownedTickets ready timers ->
                             let {
                               readyScope =
                                 RAsyncScopeState closed busy cellLimit callbackLimit ownedCells
                                   ownedTickets
                                   (append ready waiters)
                                   timers
                             } in
                             Right
                               (Pair
                                  (rAsyncSetCell (rAsyncSetScope updated owner readyScope) identity
                                     (RAsyncCellState owner (Just payload) Nil))
                                  0)
                         }
                       }
                   }
                 }
             }
           }
    };
  rAsyncRead store owner identity =
    do {
      scope <- rAsyncLookupScope store owner;
      if rAsyncClosed scope
      then Right Nothing
      else do {
             boundValueShared5 <- rAsyncLookupCell store identity;
             case boundValueShared5 of {
               RAsyncCellState cellOwner result _ ->
                 do {
                   ensure (cellOwner == owner) "completion owner mismatch";
                   Right result
                 }
             }
           }
    };
  rAsyncInsertTimer :: Int -> Int -> List (Pair Int Int) -> List (Pair Int Int);
  rAsyncInsertTimer deadline identity timers =
    case timers of {
      Nil -> Cons (Pair deadline identity) Nil;
      Cons (Pair first entry) rest ->
        if (deadline < first)
        then Cons (Pair deadline identity) timers
        else Cons (Pair first entry) (rAsyncInsertTimer deadline identity rest)
    };
  rAsyncSubscribe store owner cellId callback =
    rAsyncSubscribeTimer store owner cellId callback Nothing;
  rAsyncSubscribeTimer store owner cellId callback deadline =
    do {
      boundValueShared8 <- rAsyncLookupScope store owner;
      case boundValueShared8 of {
        RAsyncScopeState closed busy cellLimit callbackLimit ownedCells ownedTickets ready timers ->
          do {
            if closed
            then Right (Pair store (RAsyncSubscriptionHandle owner (-1) 3))
            else if (length ownedTickets >= callbackLimit)
                 then Right (Pair store (RAsyncSubscriptionHandle owner (-1) 4))
                 else do {
                        payload <-
                          case cellId of {
                            Nothing -> Right Nothing;
                            Just identity ->
                              do {
                                boundValueShared6 <- rAsyncLookupCell store identity;
                                case boundValueShared6 of {
                                  RAsyncCellState cellOwner result _ ->
                                    do {
                                      ensure (cellOwner == owner) "completion owner mismatch";
                                      Right result
                                    }
                                }
                              }
                          };
                        case store of {
                          RAsyncStore ns nc nt scopes cells tickets ->
                            let {
                              immediatelyReady =
                                case deadline of {
                                  Just _ -> False;
                                  Nothing ->
                                    case cellId of {
                                      Nothing -> True;
                                      Just _ ->
                                        case payload of {
                                          Nothing -> False;
                                          Just _ -> True
                                        }
                                    }
                                }
                            } in
                            let {
                              queue = if immediatelyReady then append ready (Cons nt Nil) else ready
                            } in
                            let {
                              timerQueue =
                                case deadline of {
                                  Nothing -> timers;
                                  Just time -> rAsyncInsertTimer time nt timers
                                }
                            } in
                            let {
                              scope =
                                RAsyncScopeState closed busy cellLimit callbackLimit ownedCells
                                  (Cons nt ownedTickets)
                                  queue
                                  timerQueue
                            } in
                            let {
                              updated =
                                rAsyncStore ns nc (nt + 1) (M.insert compareInt owner scope scopes)
                                  cells
                                  (M.insert compareInt nt
                                     (RAsyncSubscriptionState owner cellId callback payload)
                                     tickets)
                            } in
                            if (immediatelyReady ||
                                (case deadline of {
                                   Just _ -> True;
                                   Nothing -> False
                                 }))
                            then Right (Pair updated (RAsyncSubscriptionHandle owner nt 0))
                            else case cellId of {
                                   Nothing -> Left "invalid pending async action";
                                   Just identity ->
                                     do {
                                       boundValueShared7 <- rAsyncLookupCell updated identity;
                                       case boundValueShared7 of {
                                         RAsyncCellState cellOwner result waiters ->
                                           do {
                                             Right
                                               (Pair
                                                  (rAsyncSetCell updated identity
                                                     (RAsyncCellState cellOwner result
                                                        (append waiters (Cons nt Nil))))
                                                  (RAsyncSubscriptionHandle owner nt 0))
                                           }
                                       }
                                     }
                                 }
                        }
                      }
          }
      }
    };
  rAsyncTicketStatus :: RAsyncStore -> Int -> Int -> Int -> Either String Int;
  rAsyncTicketStatus store owner identity rejected =
    if (rejected /= 0)
    then Right rejected
    else do {
           scope <- rAsyncLookupScope store owner;
           if rAsyncClosed scope
           then Right 3
           else Right
                  (case rAsyncLookupTicket store identity of {
                     Nothing -> 6;
                     Just _ -> 0
                   })
         };
  rAsyncRemoveTicket store owner identity =
    do {
      boundValueShared10 <- rAsyncLookupScope store owner;
      case boundValueShared10 of {
        RAsyncScopeState closed busy cellLimit callbackLimit ownedCells ownedTickets ready timers ->
          do {
            case rAsyncLookupTicket store identity of {
              Nothing -> Right store;
              Just (RAsyncSubscriptionState ticketOwner cellId callback payload) ->
                do {
                  ensure (owner == ticketOwner) "subscription owner mismatch";
                  updated <-
                    case cellId of {
                      Nothing -> Right store;
                      Just key ->
                        do {
                          boundValueShared9 <- rAsyncLookupCell store key;
                          case boundValueShared9 of {
                            RAsyncCellState cellOwner result waiters ->
                              do {
                                Right
                                  (rAsyncSetCell store key
                                     (RAsyncCellState cellOwner result
                                        (rAsyncRemoveIdentity identity waiters)))
                              }
                          }
                        }
                    };
                  case updated of {
                    RAsyncStore ns nc nt scopes cells tickets ->
                      let {
                        scope =
                          RAsyncScopeState closed busy cellLimit callbackLimit ownedCells
                            (rAsyncRemoveIdentity identity ownedTickets)
                            (rAsyncRemoveIdentity identity ready)
                            (filter (\(Pair _ entry) -> (entry /= identity)) timers)
                      } in
                      Right
                        (rAsyncStore ns nc nt (M.insert compareInt owner scope scopes) cells
                           (M.delete compareInt identity tickets))
                  }
                }
            }
          }
      }
    };
  rAsyncCancel store owner identity rejected =
    do {
      status <- rAsyncTicketStatus store owner identity rejected;
      if (status /= 0)
      then Right (Pair store status)
      else do {
             updated <- rAsyncRemoveTicket store owner identity;
             Right (Pair updated 0)
           }
    };
  rAsyncDue :: Int -> List (Pair Int Int) -> Pair (List Int) (List (Pair Int Int));
  rAsyncDue now timers =
    case timers of {
      Nil -> Pair Nil Nil;
      Cons (Pair deadline identity) rest ->
        if (deadline > now)
        then Pair Nil timers
        else case rAsyncDue now rest of {
               Pair due later -> Pair (Cons identity due) later
             }
    };
  rAsyncMature :: RAsyncStore -> Int -> Int -> Either String RAsyncStore;
  rAsyncMature store owner now =
    do {
      boundValueShared11 <- rAsyncLookupScope store owner;
      case boundValueShared11 of {
        RAsyncScopeState closed busy cellLimit callbackLimit cells tickets ready timers ->
          do {
            if closed
            then Right store
            else case rAsyncDue now timers of {
                   Pair due later ->
                     Right
                       (rAsyncSetScope store owner
                          (RAsyncScopeState closed busy cellLimit callbackLimit cells tickets
                             (append ready due)
                             later))
                 }
          }
      }
    };
  rAsyncWait :: RAsyncStore ->
                Int -> Int -> Int -> IO (Either String (Pair RAsyncStore RIOOutcome));
  rAsyncWait store owner limit start =
    checkedIO (rAsyncLookupScope store owner)
      (\initial ->
         if rAsyncClosed initial
         then rAsyncFinished store (RInteger 3)
         else if rAsyncBusy initial
              then rAsyncFinished store (RInteger 8)
              else ioBind ProcessHost.clock
                     (\now ->
                        checkedIO
                          (do {
                             updated <- rAsyncMature store owner now;
                             scope <- rAsyncLookupScope updated owner;
                             Right (Pair updated scope)
                           })
                          (\(Pair updated scope) ->
                             case scope of {
                               RAsyncScopeState closed busy _ _ _ _ ready timers ->
                                 if closed
                                 then rAsyncFinished updated (RInteger 3)
                                 else if busy
                                      then rAsyncFinished updated (RInteger 8)
                                      else case ready of {
                                             Cons _ _ -> rAsyncFinished updated (RInteger 0);
                                             Nil ->
                                               case timers of {
                                                 Nil -> rAsyncFinished updated (RInteger 1);
                                                 Cons (Pair deadline _) _ ->
                                                   if ((limit >= 0) && ((now - start) >= limit))
                                                   then rAsyncFinished updated (RInteger 1)
                                                   else let {
                                                          remaining =
                                                            if (limit < 0)
                                                            then (deadline - now)
                                                            else min (deadline - now)
                                                                   (limit - (now - start))
                                                        } in
                                                        ioBind
                                                          (ProcessHost.pause (min 1000 remaining))
                                                          (\_ ->
                                                             rAsyncWait updated owner limit start)
                                               }
                                           }
                             })));
  -- This loop threads updates through *all* IO binds. Legacy host effects do not
  -- get a fresh store, and nested stepping of another scope preserves both queues.
  runActionState :: List String ->
                    DataEnv ->
                    RAsyncStore ->
                    Either String RValue ->
                    IO (Either String (Pair RAsyncStore RIOOutcome));
  runActionState args ds store thunk =
    case thunk of {
      Left message -> ioReturn (Left message);
      Right value ->
        case value of {
          RAction primitive arguments ->
            case primitive of {
              PIOBind ->
                ioBind (runActionState args ds store (head arguments))
                  (\result ->
                     case result of {
                       Left message -> ioReturn (Left message);
                       Right (Pair updated outcome) ->
                         case outcome of {
                           RIOFailure message -> ioReturn (Right (Pair updated (RIOFailure message)));
                           RIOSuccess value ->
                             runActionState args ds updated
                               (bindEither (head (tail arguments))
                                  (\function -> apply ds function value))
                         }
                     });
              PIOError ->
                checkedIO (runtimeIOError (head arguments))
                  (\message -> ioReturn (Right (Pair store (RIOFailure message))));
              PCatchIOError ->
                ioBind (runActionState args ds store (head arguments))
                  (\result -> case result of {
                     Left message -> ioReturn (Left message);
                     Right (Pair updated outcome) ->
                       case outcome of {
                         RIOSuccess value -> ioReturn (Right (Pair updated (RIOSuccess value)));
                         RIOFailure message ->
                           runActionState args ds updated
                             (bindEither (head (tail arguments))
                                (\handler -> apply ds handler (Right (RIOError message))))
                       }
                   });
              _ ->
                if ((P.primitiveCode primitive >= 83) && (P.primitiveCode primitive <= 94))
                then performAsync args ds store primitive arguments
                else ioBind (perform args ds primitive arguments)
                       (\result -> ioReturn (mapEither (\value -> Pair store (RIOSuccess value)) result))
            };
          _ -> ioReturn (Left "runtime expected an IO action")
        }
    };
  performAsync :: List String ->
                  DataEnv ->
                  RAsyncStore ->
                  Primitive ->
                  List (Either String RValue) ->
                  IO (Either String (Pair RAsyncStore RIOOutcome));
  performAsync args ds store primitive arguments =
    let {
      a = head arguments
    } in
    let {
      b = head (tail arguments)
    } in
    let {
      c = head (tail (tail arguments))
    } in
    case primitive of {
      PAsyncScopeNew ->
        checkedIO
          (do {
             cells <- arraySize a;
             callbacks <- arraySize b;
             Right (Pair cells callbacks)
           })
          (\(Pair cells callbacks) ->
             case rAsyncNewScope store cells callbacks of {
               Pair updated result -> rAsyncFinished updated result
             });
      PAsyncScopeClose ->
        checkedIO
          (do {
             identity <- rAsyncScopeHandle a;
             rAsyncClose store identity
           })
          (\updated -> rAsyncFinished updated (RConstructor "Unit" Nil));
      PAsyncNewCompletion ->
        checkedIO
          (do {
             owner <- rAsyncScopeHandle a;
             rAsyncNewCell store owner
           })
          (\(Pair updated result) ->
             case result of {
               Nothing -> runActionState args ds updated c;
               Just cell ->
                 runActionState args ds updated
                   (bindEither b (\callback -> apply ds callback (Right cell)))
             });
      PAsyncResolveCompletion ->
        checkedIO
          (do {
             boundValueShared12 <- rAsyncCellHandle a;
             case boundValueShared12 of {
               Pair owner identity ->
                 do {
                   rAsyncResolve store owner identity b
                 }
             }
           })
          (\(Pair updated status) -> rAsyncFinished updated (RInteger status));
      PAsyncReadCompletion ->
        checkedIO
          (do {
             boundValueShared13 <- rAsyncCellHandle a;
             case boundValueShared13 of {
               Pair owner identity ->
                 do {
                   rAsyncRead store owner identity
                 }
             }
           })
          (\result ->
             case result of {
               Nothing -> runActionState args ds store c;
               Just payload ->
                 runActionState args ds store
                   (bindEither b (\callback -> apply ds callback payload))
             });
      PAsyncSubscribeCompletion ->
        checkedIO
          (do {
             boundValueShared14 <- rAsyncCellHandle a;
             case boundValueShared14 of {
               Pair owner identity ->
                 do {
                   rAsyncSubscribe store owner (Just identity) b
                 }
             }
           })
          (\(Pair updated result) -> rAsyncFinished updated result);
      PAsyncSubscriptionStatus ->
        checkedIO
          (do {
             boundValueShared15 <- rAsyncTicketHandle a;
             case boundValueShared15 of {
               Triple owner identity rejected ->
                 do {
                   rAsyncTicketStatus store owner identity rejected
                 }
             }
           })
          (\status -> rAsyncFinished store (RInteger status));
      PAsyncCancelSubscription ->
        checkedIO
          (do {
             boundValueShared16 <- rAsyncTicketHandle a;
             case boundValueShared16 of {
               Triple owner identity rejected ->
                 do {
                   rAsyncCancel store owner identity rejected
                 }
             }
           })
          (\(Pair updated status) -> rAsyncFinished updated (RInteger status));
      PAsyncEnqueue ->
        checkedIO
          (do {
             owner <- rAsyncScopeHandle a;
             rAsyncSubscribe store owner Nothing b
           })
          (\(Pair updated result) -> rAsyncFinished updated result);
      PAsyncDelay ->
        checkedIO
          (do {
             owner <- rAsyncScopeHandle a;
             milliseconds <- integer b;
             ensure ((milliseconds >= 0) && (milliseconds <= 4294967295)) "invalid async delay";
             Right (Pair owner milliseconds)
           })
          (\(Pair owner milliseconds) ->
             ioBind ProcessHost.clock
               (\now ->
                  checkedIO (rAsyncSubscribeTimer store owner Nothing c (Just (now + milliseconds)))
                    (\(Pair updated result) -> rAsyncFinished updated result)));
      PAsyncWait ->
        checkedIO
          (do {
             owner <- rAsyncScopeHandle a;
             limit <- integer b;
             ensure ((limit >= (-1)) && (limit <= 4294967295)) "invalid async wait";
             Right (Pair owner limit)
           })
          (\(Pair owner limit) ->
             ioBind ProcessHost.clock (\start -> rAsyncWait store owner limit start));
      PAsyncStep ->
        checkedIO (rAsyncScopeHandle a)
          (\owner ->
             checkedIO (rAsyncLookupScope store owner)
               (\initial ->
                  if rAsyncClosed initial
                  then rAsyncFinished store (RInteger 3)
                  else if rAsyncBusy initial
                       then rAsyncFinished store (RInteger 8)
                       else ioBind ProcessHost.clock
                              (\now ->
                                 checkedIO (rAsyncMature store owner now)
                                   (\store ->
                                      checkedIO (rAsyncLookupScope store owner)
                                        (\scope ->
                                           if rAsyncClosed scope
                                           then rAsyncFinished store (RInteger 3)
                                           else if rAsyncBusy scope
                                                then rAsyncFinished store (RInteger 8)
                                                else case scope of {
                                                       RAsyncScopeState _ _ _ _ _ _ Nil _ ->
                                                         rAsyncFinished store (RInteger 1);
                                                       RAsyncScopeState _ _ _ _ _ _ (Cons identity _) _ ->
                                                         case rAsyncLookupTicket store identity of {
                                                           Nothing ->
                                                             ioReturn
                                                               (Left "missing ready subscription");
                                                           Just (RAsyncSubscriptionState _ cell callback payload) ->
                                                             checkedIO
                                                               (do {
                                                                  removed <-
                                                                    rAsyncRemoveTicket store owner
                                                                      identity;
                                                                  rAsyncSetBusy removed owner True
                                                                })
                                                               (\updated ->
                                                                  let {
                                                                    action =
                                                                      case cell of {
                                                                        Nothing -> callback;
                                                                        Just _ ->
                                                                          case payload of {
                                                                            Nothing ->
                                                                              Left
                                                                                "unresolved ready completion";
                                                                            Just result ->
                                                                              bindEither callback
                                                                                (\function ->
                                                                                   apply ds function
                                                                                     result)
                                                                          }
                                                                      }
                                                                  } in
                                                                  ioBind
                                                                    (runActionState args ds updated
                                                                       action)
                                                                    (\result ->
                                                                       case result of {
                                                                         Left message ->
                                                                           ioReturn (Left message);
                                                                         Right (Pair after outcome) ->
                                                                           checkedIO
                                                                             (rAsyncSetBusy after
                                                                                owner
                                                                                False)
                                                                             (\finished ->
                                                                                case outcome of {
                                                                                  RIOSuccess _ ->
                                                                                    rAsyncFinished finished (RInteger 0);
                                                                                  RIOFailure message ->
                                                                                    ioReturn (Right (Pair finished (RIOFailure message)))
                                                                                })
                                                                       }))
                                                         }
                                                     })))));
      _ -> ioReturn (Left "invalid async primitive")
    }
}
