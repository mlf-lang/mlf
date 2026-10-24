-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Tests.SharedFrontend where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Parser as P;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.CrateQuery as Query;
  import qualified Bootstrap.InferenceUnit as Inference;
  import qualified Bootstrap.Lexer as L;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Compiler as C;
  import qualified Bootstrap.Constraint as Constraint;
  import qualified Bootstrap.Elaborate as Elaborate;
  import qualified Bootstrap.Graph as Graph;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.Data as Data;
  import qualified Bootstrap.X.Parser as XP;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Type as XT;
  import qualified Bootstrap.Runtime as Runtime;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Tests.IndependentCheck as Independent;
  import qualified Tests.IndependentType as IndependentType;
  import qualified MLF.Tests.ClassDemand as ClassDemandTests;
  prologue :: String;
  prologue =
    "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\n";
  source body = (prologue ++ ("module Example where\nimport MLF.Primitive\n" ++ (body ++ "\n")));
  parse body = P.parseModule "Example.hs" (source body);
  accept body = isRight (parse body);
  reject body = isLeft (parse body);
  linked text =
    case parse text of {
      Left _ -> False;
      Right m -> isRight (Modules.linkModules ImplicitPrelude ((:) m []))
    };
  forwardScope =
    case parse "main = let { x = y; y = 3 } in x" of {
      Right (SourceModule _ _ _ _ _ _ _ ((:) ((,,) _ _ (SLet y (SIntLit 3)
        (SLet x (SCallSite yLabel (SourceSpan yPackage yModule yFile 5 18 5 19) (SVar reference))
          (SCallSite xLabel (SourceSpan xPackage xModule xFile 5 32 5 33) (SVar result))))) []) _ SharedHaskellV1) ->
        eqString y "y" && eqString x "x" && eqString reference "y" && eqString result "x" &&
        eqString yLabel "y" && eqString xLabel "x" &&
        eqString yPackage "main" && eqString xPackage "main" &&
        eqString yModule "Example" && eqString xModule "Example" &&
        eqString yFile "Example.hs" && eqString xFile "Example.hs";
      _ -> False
    };
  refutableDo =
    case parse "data Maybe a = Nothing | Just a\nmain = do { Just x <- ioReturn (Just 3); ioReturn x }" of {
      Right (SourceModule _ _ _ _ _ _ _ ((:) ((,,) _ _
        (SSharedBind (SConstructorPattern constructor ((:) (Just binder) []))
          (SApp (SCallSite actionLabel _ (SVar action)) (SApp (SConstructor valueConstructor) (SIntLit 3)))
          (SApp (SCallSite continuationLabel _ (SVar continuation)) (SCallSite resultLabel _ (SVar result)))
          (SVar bindMethod)
          (SApp (SCallSite failureLabel _ (SVar failureMethod))
            (SApp (SPrimitive PTextToChars) (SStringLit message))))) []) _ SharedHaskellV1) ->
        eqString constructor "Just" && eqString valueConstructor "Just" &&
        eqString binder "x" && eqString result "x" && eqString resultLabel "x" &&
        eqString action "ioReturn" && eqString actionLabel "ioReturn" &&
        eqString continuation "ioReturn" && eqString continuationLabel "ioReturn" &&
        eqString bindMethod "$MLF.Primitive.>>=" &&
        eqString failureMethod "$MLF.Primitive.fail" && eqString failureLabel "a do statement" &&
        eqString message "Pattern match failure in do expression";
      _ -> False
    };
  fixedDo =
    case parse "main = let { bind = 7 } in do { value <- ioReturn 3; ioReturn value }" of {
      Right (SourceModule _ _ _ _ _ _ _ ((:) ((,,) _ _ expression) []) _ _) ->
        elem eqString "$MLF.Primitive.>>=" (Surface.freeNames expression);
      _ -> False
    };
  legacyScope =
    case P.parseExpr "legacy.hs" "let x = 1 in let x = x + 1 in x" of {
      Right (SLet _ (SIntLit 1) (SLet _ _ _)) -> True;
      _ -> False
    };
  mixedGraph =
    case parse "main = Support.answer" of {
      Left _ -> False;
      Right (SourceModule path name exports _ ds cs instances values body syntax) ->
        let {
          root =
            SourceModule path name exports
              ((:) (Import "MLF.Primitive" False Nothing Everything)
                 ((:) (Import "Support" False Nothing Everything) []))
              ds
              cs
              instances
              values
              body
              syntax
        } in
        case Modules.loadModuleMap
               (M.singleton "Support"
                  ((,) "Support.emlf"
                     "module Support where\nanswer = let x = 1 in let x = x + 1 in x\n"))
               root of {
          Left _ -> False;
          Right graph ->
            ((length graph == 2) && isRight (Modules.linkModules ImplicitPrelude graph))
        }
    };
  importedHook =
    case parse "main = 1" of {
      Left _ -> False;
      Right (SourceModule path name exports _ ds cs instances values body syntax) ->
        let {
          root =
            SourceModule path name exports
              ((:) (Import "MLF.Primitive" False Nothing Everything)
                 ((:) (Import "Bad" False Nothing Everything) []))
              ds
              cs
              instances
              values
              body
              syntax
        } in
        case P.parseModule "Bad.emlf" "module Bad where\nfromInteger x = x\n" of {
          Left _ -> False;
          Right bad -> isRight (Modules.linkModules ImplicitPrelude ((:) bad ((:) root [])))
        }
    };
  linkRaw text = case P.parseModule "Example.hs" (prologue ++ text) of { Left _ -> False; Right m -> isRight (Modules.linkModules ImplicitPrelude ((:) m [])) };

  evaluated :: String -> Either String Runtime.RValue;
  evaluated body = do {
    result <- mapLeft C.prettyError (C.compile "Example.hs" (source body));
    let { term = C.compiledTerm result };
    state <- Runtime.prepare False term;
    Runtime.evaluate (fst state) (Runtime.REnv M.empty) (X.erase term)
  };
  evaluatesInt :: String -> Int -> Bool;
  evaluatesInt body expected = case evaluated body of {
    Right (Runtime.RInteger actual) -> actual == expected;
    _ -> False
  };
  failsWith :: String -> String -> Bool;
  failsWith body expected = case evaluated body of { Left actual -> eqString actual expected; Right _ -> False };
  boxFunctor :: String;
  boxFunctor = "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\nunBox (Box x) = x\n";
  boxApplicative :: String;
  boxApplicative = boxFunctor ++ "instance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\n";
  boxMonad :: String;
  boxMonad = boxApplicative ++ "instance Monad Box where { (>>=) (Box x) f = f x }\n";
  check :: String -> Bool -> IO ();
  check name okay =
    if okay
    then ioReturn ()
    else do {
           putErr ("shared frontend failure: " ++ (name ++ "\n"));
           exitWith 1
         };
  -- Unsigned groups now pass parsing. The negative operator case belongs to
  -- module resolution: shadowed infix uses must still select the canonical
  -- primitive binding, independently of recursive signature availability.
  recursiveInfixRejected body =
    case C.compile "Example.hs" (source body) of {
      Left error ->
        (case C.phase error of { ModuleResolution -> True; _ -> False }) &&
        eqString (C.diagnostic error)
          "Example.hs: shared infix use requires a canonical MLF.Primitive binding; use the symbolic binding in prefix form";
      Right _ -> False
    };
  captureDefaults :: String;
  captureDefaults = "data Box a = Box a\ndefaultX f (Box x) = Box (f x)\ninstance Functor Box where { fmap = defaultX }\nunBox (Box x) = x\nmain = let { mlfInternal_36_102 = 40 } in unBox (mlfInternal_36_102 <$ Box 2)\n";
  targetRoundTrip term =
    case XP.parseTerm "<target roundtrip>" (Pretty.prettyTerm term) of {
      Left _ -> False;
      Right decoded ->
        case Check.checkClosed term of {
          Left _ -> False;
          Right before -> case Check.checkClosed decoded of {
            Left _ -> False;
            Right after -> XT.alphaEq before after && X.equalErased (X.erase term) (X.erase decoded)
          }
        }
    };
  hintRoundTrip hint =
    let { n = XName 17 (Constraint.targetNameHint hint) } in
    targetRoundTrip (XAbs n (XCon "Int" []) (XVarTerm n));
  sourceRoundTrip body =
    case C.compile "Example.hs" (source body) of {
      Left _ -> False;
      Right compiled -> targetRoundTrip (C.compiledTerm compiled)
    };
  builtinRoundTrip =
    case Artifact.builtinPrelude of {
      Left _ -> False;
      Right object ->
        let { encodedInterface = Artifact.encodeInterface (Artifact.objectInterface object);
              encodedObject = Artifact.encodeObject object } in
        case Artifact.decodeInterface encodedInterface of {
          Left _ -> False;
          Right iface ->
            case Artifact.decodeObject iface encodedObject of {
              Left _ -> False;
              Right decoded ->
                eqString encodedInterface (Artifact.encodeInterface (Artifact.objectInterface decoded)) &&
                eqString encodedObject (Artifact.encodeObject decoded)
            }
        }
    };
  -- These are direct host calls into the current source compiler, not guest
  -- tests interpreted by a prebuilt compiler. Expected types are authored here;
  -- neither the current checker nor inferred output supplies the oracle.
  recursiveInt :: XType;
  recursiveInt = XCon "Int" [];
  recursiveBool :: XType;
  recursiveBool = XCon "Bool" [];
  recursiveIdentity :: XType;
  recursiveIdentity =
    XForall (XTyVar 0) XBot (XArrow (XVar (XTyVar 0)) (XVar (XTyVar 0)));
  recursiveRight :: forall a. String -> Either String a -> IO a;
  recursiveRight label result =
    case result of {
      Right value -> ioReturn value;
      Left message -> do {
        putErr ("shared frontend failure: " ++ (label ++ (": " ++ (message ++ "\n"))));
        exitWith 1
      }
    };
  recursiveCheckedType :: String -> XType -> Either String XType -> IO ();
  recursiveCheckedType label expected result = do {
    actual <- recursiveRight label result;
    check label (IndependentType.alphaEq actual expected)
  };
  recursiveAccepted :: String -> String -> XType -> IO XTerm;
  recursiveAccepted label program expected = do {
    result <- recursiveRight (label ++ " source compilation")
      (mapLeft C.prettyError (C.compile "RecursiveInference.emlf" program));
    recursiveCompilation label result expected
  };
  recursiveCompilation :: String -> C.Compilation -> XType -> IO XTerm;
  recursiveCompilation label result expected = do {
    let { term = C.compiledTerm result };
    check (label ++ " inferred type") (IndependentType.alphaEq (C.inferredType result) expected);
    recursiveCheckedType (label ++ " current target") expected (Check.checkClosed term);
    recursiveCheckedType (label ++ " independent target") expected (Independent.checkClosed term);
    decoded <- recursiveRight (label ++ " target parse")
      (XP.parseTerm "RecursiveInference.xmlf" (Pretty.prettyTerm term));
    recursiveCheckedType (label ++ " current roundtrip") expected (Check.checkClosed decoded);
    recursiveCheckedType (label ++ " independent roundtrip") expected (Independent.checkClosed decoded);
    check (label ++ " roundtrip erasure") (X.equalErased (X.erase term) (X.erase decoded));
    -- C.compile also checks source-skeleton erasure against this same target.
    ioReturn term
  };
  recursiveModulesAccepted :: String -> Map String ((,) String String) -> String -> XType -> IO XTerm;
  recursiveModulesAccepted label modules program expected = do {
    result <- recursiveRight (label ++ " module compilation")
      (mapLeft C.prettyError (C.compileModules modules "Main.emlf" program));
    recursiveCompilation label result expected
  };
  recursiveStartsWith :: String -> String -> Bool;
  recursiveStartsWith prefix text =
    if stringLength text < stringLength prefix then False
    else eqString (stringSlice text 0 (stringLength prefix)) prefix;
  recursiveEndsWith :: String -> String -> Bool;
  recursiveEndsWith suffix text =
    if stringLength text < stringLength suffix then False
    else eqString (stringSlice text (stringLength text - stringLength suffix)
                   (stringLength suffix)) suffix;
  recursiveRejected :: String -> String -> String -> IO ();
  recursiveRejected label program diagnostic =
    case C.compile "RecursiveInference.emlf" program of {
      Left error -> do {
        check (label ++ " inference phase")
          (case C.phase error of { Inference -> True; _ -> False });
        check (label ++ " diagnostic")
          (recursiveStartsWith diagnostic (C.diagnostic error))
      };
      Right _ -> check (label ++ " unexpectedly accepted") False
    };
  recursiveGroups :: XErased -> [] ([] String);
  recursiveGroups term =
    case term of {
      XEAbs _ body -> recursiveGroups body;
      XEApp function argument -> append (recursiveGroups function) (recursiveGroups argument);
      XELet _ value body -> append (recursiveGroups value) (recursiveGroups body);
      XELetRec definitions body ->
        (:) (map (\((,) name _) -> X.nameHint name) definitions)
          (append (concatMap (\((,) _ rhs) -> recursiveGroups rhs) definitions) (recursiveGroups body));
      XECase scrutinee alternatives -> append (recursiveGroups scrutinee)
        (concatMap (\(XErasedAlternative _ body) -> recursiveGroups body) alternatives);
      _ -> []
    };
  recursiveOrder :: String -> [] String -> XTerm -> IO ();
  recursiveOrder label names term =
    check label
      (length (filter (X.equalList eqString names) (recursiveGroups (X.erase term))) == 1);
  recursiveProjection :: String -> Elaborate.TypeContext -> IntMap Int ->
                         [] ((,) XTyVar XType) -> XType -> XType -> IO ();
  recursiveProjection label context copies bounds source expected = do {
    proof <- recursiveRight (label ++ " evidence")
      (Elaborate.proveInstanceUsing Data.emptyDataEnv
        (Elaborate.recursiveReplacementIn context copies bounds) M.empty source expected);
    recursiveCheckedType (label ++ " current computation") expected
      (Check.checkComputation M.empty proof source);
    recursiveCheckedType (label ++ " independent computation") expected
      (Independent.checkComputation M.empty proof source)
  };
  recursiveProjectionChecks :: IO ();
  recursiveProjectionChecks = do {
    let {
      a = XTyVar 1;
      b = XTyVar 2;
      c = XTyVar 3;
      dependent = XForall c XBot (XArrow (XVar c) (XVar a));
      bounds = (:) ((,) a XBot) ((:) ((,) b dependent) []);
      source = XForall a XBot (XForall b dependent recursiveInt);
      empty = Elaborate.prepareTypes Graph.emptyGraph;
      copied = Elaborate.prepareTypes
        (Graph.mkGraph (IM.singleton 100 (Node GBot Nothing Flexible)) IM.empty 101)
    };
    recursiveProjection "recursive projection drops dependent peer bound"
      empty IM.empty bounds source recursiveInt;
    recursiveProjection "recursive projection retains renamed dependency"
      copied (IM.singleton 1 100) bounds source
      (XForall (XTyVar 100) XBot recursiveInt);
    recursiveProjection "recursive projection drops higher kind bottom"
      empty IM.empty ((:) ((,) a (XBotKind (KArrow Star Star))) [])
      (XForall a (XBotKind (KArrow Star Star)) recursiveInt) recursiveInt
  };
  -- Remove only a generated Inspect dictionary abstraction; its uses and the
  -- declared recursive scheme remain, so both checkers must detect bad scope.
  generatedInspectDictionary :: XType -> Bool;
  generatedInspectDictionary ty = case ty of {
    XCon name _ -> recursiveStartsWith "DictInspect" name;
    XApply function _ -> generatedInspectDictionary function;
    _ -> False
  };
  generatedDictionaryParameters :: XTerm -> [] XName;
  generatedDictionaryParameters term = case term of {
    XAbs name ty body ->
      let { nested = generatedDictionaryParameters body } in
      if recursiveStartsWith "wantedDictionary" (X.nameHint name) &&
         generatedInspectDictionary ty
      then (:) name nested else nested;
    XApp function argument -> append (generatedDictionaryParameters function)
      (generatedDictionaryParameters argument);
    XTypeAbs _ _ body -> generatedDictionaryParameters body;
    XTypeApp body _ -> generatedDictionaryParameters body;
    XLet _ rhs body -> append (generatedDictionaryParameters rhs)
      (generatedDictionaryParameters body);
    XLetRec definitions body -> append
      (concatMap (\((,,) _ _ rhs) -> generatedDictionaryParameters rhs) definitions)
      (generatedDictionaryParameters body);
    XCase scrutinee _ alternatives -> append (generatedDictionaryParameters scrutinee)
      (concatMap (\(XAlternative _ body) -> generatedDictionaryParameters body) alternatives);
    XWithData _ body -> generatedDictionaryParameters body;
    _ -> []
  };
  removeDictionaryAbstractions :: [] XName -> XTerm -> XTerm;
  removeDictionaryAbstractions names term = case term of {
    XAbs name ty body ->
      if elem X.equalName name names
      then body
      else XAbs name ty (removeDictionaryAbstractions names body);
    XApp function argument -> XApp (removeDictionaryAbstractions names function)
      (removeDictionaryAbstractions names argument);
    XTypeAbs variable bound body -> XTypeAbs variable bound
      (removeDictionaryAbstractions names body);
    XTypeApp body proof -> XTypeApp (removeDictionaryAbstractions names body) proof;
    XLet name rhs body -> XLet name (removeDictionaryAbstractions names rhs)
      (removeDictionaryAbstractions names body);
    XLetRec definitions body -> XLetRec
      (map (\((,,) name ty rhs) -> (,,) name ty (removeDictionaryAbstractions names rhs)) definitions)
      (removeDictionaryAbstractions names body);
    XCase scrutinee ty alternatives -> XCase (removeDictionaryAbstractions names scrutinee) ty
      (map (\(XAlternative pattern body) -> XAlternative pattern (removeDictionaryAbstractions names body)) alternatives);
    XWithData declarations body -> XWithData declarations (removeDictionaryAbstractions names body);
    _ -> term
  };
  recursiveDictionaryScopeControl :: IO ();
  recursiveDictionaryScopeControl = do {
    original <- recursiveAccepted "generated recursive dictionary target"
      ("class Inspect a where { inspect : a -> Bool }; " ++
       "instance Inspect Int where { inspect = \\x -> true }; " ++
       "let rec { f x = if inspect x then true else f x } in f 0") recursiveBool;
    let { parameters = generatedDictionaryParameters original };
    check "dictionary scope mutation has a generated parameter" (not (null parameters));
    let { malformed = removeDictionaryAbstractions parameters original };
    check "current checker rejects escaped recursive dictionary"
      (isLeft (Check.checkClosed malformed));
    check "independent checker rejects escaped recursive dictionary"
      (isLeft (Independent.checkClosed malformed))
  };
  recursiveResolutionRejected :: String -> String -> IO ();
  recursiveResolutionRejected label program =
    case C.compile "RecursiveInference.emlf" program of {
      Left error -> do {
        check (label ++ " resolution phase")
          (case C.phase error of { Resolution -> True; _ -> False });
        let {
          message = C.diagnostic error;
          prefix = "no instance or given constraint for ";
          suffix = "ambiguous uses need a type annotation"
        };
        check (label ++ " missing or ambiguous evidence")
          (recursiveStartsWith prefix message && recursiveEndsWith suffix message)
      };
      Right _ -> check (label ++ " unexpectedly accepted") False
    };
  qualifiedRecursiveChecks :: IO ();
  qualifiedRecursiveChecks = do {
    let {
      inspectClass = "class Inspect a where { inspect : a -> Bool }; ";
      inspectInt = "instance Inspect Int where { inspect = \\x -> true }; ";
      inspectBool = "instance Inspect Bool where { inspect = \\x -> x }; ";
      inspectInstances = inspectClass ++ inspectInt ++ inspectBool;
      strongClass = "class Inspect a => Strong a where { strong : a -> Bool }; ";
      strongInstances = inspectInstances ++ strongClass ++
        "instance Strong Int where { strong = \\x -> true }; " ++
        "instance Strong Bool where { strong = \\x -> x }; "
    };
    recursiveAccepted "unsigned recursive class interface generalized"
      (inspectInstances ++
       "let rec { f x = if true then inspect x else f x } in let b = f 0 in f true")
      recursiveBool;
    recursiveAccepted "mutual unsigned class interfaces generalized"
      (inspectInstances ++
       "let rec { f x = if inspect x then true else g x; g y = f y } in let b = f 0 in g true")
      recursiveBool;
    recursiveAccepted "recursive qualified function passed as first class argument"
      (inspectInstances ++
       "let rec { f x = if inspect x then true else (\\h -> h x) f } in let b = f 0 in f true")
      recursiveBool;
    recursiveAccepted "recursive multiparameter demands retain argument order"
      ("class C a b where { compareC : a -> b -> Bool }; " ++
       "instance C Int Bool where { compareC = \\x y -> y }; " ++
       "instance C Bool Int where { compareC = \\x y -> x }; " ++
       "let rec { f x y = if compareC x y then compareC y x else f x y } in let b = f 0 true in f false 1")
      recursiveBool;
    recursiveAccepted "recursive higher kind dictionary slot varies constructor"
      ("data Box a = Box a; data Wrap a = Wrap a; " ++
       "class InspectF (f : * -> *) where { inspectF : forall a. f a -> Bool }; " ++
       "instance InspectF Box where { inspectF = \\x -> true }; " ++
       "instance InspectF Wrap where { inspectF = \\x -> false }; " ++
       "let rec { visit x = if inspectF x then true else visit x } in let b = visit (Box 0) in visit (Wrap true)")
      recursiveBool;
    recursiveAccepted "recursive same class demands keep distinct arguments"
      (inspectInstances ++
       "let rec { f x y = if inspect x then inspect y else f x y } in let b = f 0 true in f false 1")
      recursiveBool;
    recursiveAccepted "recursive class planner retains no leaf demand cycle"
      (inspectClass ++ "let rec { f x = g x; g x = f x } in true")
      recursiveBool;
    recursiveAccepted "recursive unused lexical let does not export peer demand"
      (inspectClass ++
       "let rec { f x = if inspect x then true else g x; g y = let k = f in true } in g 0")
      recursiveBool;
    recursiveAccepted "recursive captured predicate preserves independent argument generalization"
      (inspectInstances ++
       "let choose = \\y -> let rec { f x = if inspect y then true else f x } in let b = f 0 in f true in let b = choose 0 in choose true")
      recursiveBool;
    recursiveAccepted "nested recursive class demand feeds outer recursion"
      (inspectInstances ++
       "let rec { f n = let rec { h x = if inspect x then f 0 else h x } in if h true then h 0 else f n } in f 1")
      recursiveBool;
    let {
      genericBox = inspectClass ++ "data Box a = Box a; " ++
        "instance Inspect (Box a) where { inspect = \\x -> true }; ";
      boxRecursion =
        "let rec { f (Box x) = if inspect (Box x) then true else f (Box x) } in "
    };
    recursiveAccepted "recursive generic instance retains polymorphic Box export"
      (genericBox ++ boxRecursion ++ "f")
      (XForall (XTyVar 0) XBot
        (XArrow (XCon "Box" ((:) (XVar (XTyVar 0)) [])) recursiveBool));
    recursiveAccepted "recursive generic instance accepts Box Int and Box Bool"
      (genericBox ++ boxRecursion ++ "let b = f (Box 0) in f (Box true)")
      recursiveBool;
    recursiveAccepted "mixed signed unsigned qualified recursion"
      (inspectInstances ++
       "let rec { f : forall a. Inspect a => a -> Bool; f x = if inspect x then true else g x; g y = f y } in let b = f 0 in g true")
      recursiveBool;
    recursiveAccepted "mixed qualified recursion uses superclass given"
      (strongInstances ++
       "let rec { f : forall a. Strong a => a -> Bool; f x = if inspect x then g x else strong x; g y = f y } in let b = f 0 in g true")
      recursiveBool;
    recursiveAccepted "unsigned recursion preserves captured superclass given"
      (inspectClass ++ strongClass ++
       "let outer : forall a. Strong a => a -> Bool = \\y -> let rec { f x = if inspect y then true else f x } in f 0 in true")
      recursiveBool;
    recursiveAccepted "mutual recursive demands preserve superclass and subclass"
      (strongInstances ++
       "let rec { f x = if strong x then true else g x; g y = if inspect y then true else f y } in let b = f 0 in g true")
      recursiveBool;
    recursiveResolutionRejected "recursive ambiguity never defaults to sole instance"
      (inspectClass ++ inspectInt ++
       "let rec { f x = if inspect x then true else f x } in f");
    recursiveResolutionRejected "recursive class demand rejects missing concrete instance"
      (inspectClass ++ inspectInt ++
       "let rec { f x = if inspect x then true else f x } in f true");
    recursiveResolutionRejected "unsigned peer cannot invent a signed given"
      (inspectClass ++
       "let rec { f : forall a. a -> Bool; f x = g x; g y = if inspect y then true else f y } in true");
    recursiveResolutionRejected "recursive output ambiguity never picks sole instance"
      ("class Convert a b where { convert : a -> b }; " ++
       "instance Convert Int Bool where { convert = \\x -> true }; " ++
       "let rec { f x = if true then convert x else f x } in f 0");
    putStrLn "shared frontend: qualified recursive inference checks passed"
  };
  -- Declaration provenance and declared-field schemes are independent repairs.
  -- Keep expression annotations and ordinary datatype parameters as controls;
  -- neither is permission to invent a higher-rank checking boundary.
  frontendRepairTarget :: String -> XType -> XTerm -> IO ();
  frontendRepairTarget label expected term = do {
    recursiveCheckedType (label ++ " current target") expected (Check.checkClosed term);
    recursiveCheckedType (label ++ " independent target") expected (Independent.checkClosed term);
    decoded <- recursiveRight (label ++ " target parse")
      (XP.parseTerm "FrontendRepair.xmlf" (Pretty.prettyTerm term));
    recursiveCheckedType (label ++ " current roundtrip") expected (Check.checkClosed decoded);
    recursiveCheckedType (label ++ " independent roundtrip") expected (Independent.checkClosed decoded);
    check (label ++ " roundtrip erasure") (X.equalErased (X.erase term) (X.erase decoded))
  };
  frontendRepairProvenanceChecks :: IO ();
  frontendRepairProvenanceChecks = do {
    declaration <- recursiveRight "parse declaration provenance"
      (P.parseExpr "FrontendRepair.emlf" "let id : forall a. a -> a = \\x -> x in id");
    annotation <- recursiveRight "parse expression annotation provenance"
      (P.parseExpr "FrontendRepair.emlf" "let id = ((\\x -> x) : forall a. a -> a) in id");
    check "declaration parser retains SSignature"
      (case declaration of { SLet _ (SSignature _ _) _ -> True; _ -> False });
    check "expression parser retains SAnn"
      (case annotation of { SLet _ (SAnn _ _) _ -> True; _ -> False });
    hygienicDeclaration <- recursiveRight "hygiene declaration provenance" (Separate.hygiene declaration);
    hygienicAnnotation <- recursiveRight "hygiene expression annotation provenance" (Separate.hygiene annotation);
    check "separate hygiene retains SSignature"
      (case hygienicDeclaration of { SLet _ (SSignature _ _) _ -> True; _ -> False });
    check "separate hygiene retains SAnn"
      (case hygienicAnnotation of { SLet _ (SAnn _ _) _ -> True; _ -> False });
    let {
      identityType = SForall Flexible "a" SBottom (SArrow (STVar "a") (STVar "a"));
      signature = SAnnotation [] (SArrow identityType (SCon "Bool" []));
      expected = XArrow recursiveIdentity recursiveBool;
      unit = XCon "()" [];
      scopedMember = \variable -> (,,) "id"
        (Just (SAnnotation [] (SForall Flexible variable SBottom
          (SArrow (STVar variable) (STVar variable)))))
        (SLam "x" (Just (SAnnotation [] (STVar variable)))
          (SAnn (SVar "x") (SAnnotation [] (STVar variable))))
    };
    rhs <- recursiveRight "parse separate rank two body"
      (P.parseExpr "FrontendRepair.emlf" "\\g -> let n = g 1 in g true");
    declared <- recursiveRight "extract declaration signature"
      (Inference.extractLoweredDeclarations
        (SLet "use" (SSignature rhs signature) (SConstructor "()")));
    annotated <- recursiveRight "extract expression annotation"
      (Inference.extractLoweredDeclarations
        (SLet "use" (SAnn rhs signature) (SConstructor "()")));
    checked <- recursiveRight "extract generated checking boundary"
      (Inference.extractLoweredDeclarations
        (SLet "use" (SChecked (SArrow identityType (SCon "Bool" [])) rhs)
          (SConstructor "()")));
    check "separate extraction recognizes declaration signatures only"
      (case declared of { (:) ((,,) _ (Just _) _) [] -> True; _ -> False });
    check "separate extraction does not promote SAnn"
      (case annotated of { (:) ((,,) _ Nothing (SAnn _ _)) [] -> True; _ -> False });
    check "separate extraction does not promote SChecked"
      (case checked of { (:) ((,,) _ Nothing (SChecked _ _)) [] -> True; _ -> False });
    check "query keys distinguish declaration and expression provenance"
      (not (eqString
        (Query.encodeMember (Query.canonicalMember
          ((,,) "use" Nothing (SSignature rhs signature))))
        (Query.encodeMember (Query.canonicalMember
          ((,,) "use" Nothing (SAnn rhs signature))))));
    check "query keys alpha rename declaration scoped type variables"
      (eqString (Query.encodeMember (Query.canonicalMember (scopedMember "a")))
        (Query.encodeMember (Query.canonicalMember (scopedMember "b"))));
    object <- recursiveRight "separate rank two declaration inference"
      (Inference.compileLoweredGroup "FrontendRepair" [] [] declared);
    check "separate declaration preserves prescribed rank two interface"
      (case lookup eqString "use" (Separate.unitBindings (Separate.objectInterface object)) of {
        Just actual -> IndependentType.alphaEq actual expected;
        Nothing -> False
      });
    frontendRepairTarget "separate rank two declaration" unit (Separate.objectTerm object);
    check "separate expression annotation still rejects rank two inference"
      (case Inference.compileLoweredGroup "FrontendRepair" [] [] annotated of {
        Left message -> recursiveStartsWith "Inference: type constructor mismatch" message;
        Right _ -> False
      });
    consumer <- recursiveRight "separate rank two imported use"
      (Inference.compileLoweredGroup "FrontendRepairConsumer"
        ((:) (Separate.objectInterface object) []) []
        ((:) ((,,) "answer" Nothing
          (SApp (SVar "use") (SLam "x" Nothing (SVar "x")))) []));
    check "separate imported rank two use preserves prescribed Bool interface"
      (case lookup eqString "answer" (Separate.unitBindings (Separate.objectInterface consumer)) of {
        Just actual -> IndependentType.alphaEq actual recursiveBool;
        Nothing -> False
      });
    frontendRepairTarget "separate imported rank two use"
      (XArrow expected unit) (Separate.objectTerm consumer)
  };
  frontendRepairSignatureChecks :: IO ();
  frontendRepairSignatureChecks = do {
    let {
      dummy = "class Dummy a where { dummy : a -> Bool }; ";
      declaration = "let use : (forall a. a -> a) -> Bool = \\g -> let n = g 1 in g true in use (\\x -> x)";
      annotation = "let use = ((\\g -> let n = g 1 in g true) : (forall a. a -> a) -> Bool) in use (\\x -> x)";
      invalid = "let id : forall a. a -> a = \\x -> 1 in id true";
      sharedDeclaration = "use :: (forall a. a -> a) -> Bool\nuse g = let { n = g 1 } in g True\nmain = use (\\x -> x)";
      sharedLocal = "main = let { use :: (forall a. a -> a) -> Bool; use g = let { n = g 1 } in g True } in use (\\x -> x)";
      sharedAnnotation = "main = let { use = ((\\g -> let { n = g 1 } in g True) :: (forall a. a -> a) -> Bool) } in use (\\x -> x)"
    };
    recursiveAccepted "rank two declaration without classes" declaration recursiveBool;
    recursiveAccepted "rank two declaration with unused class" (dummy ++ declaration) recursiveBool;
    recursiveRejected "rank two expression annotation without classes" annotation "type constructor mismatch";
    recursiveRejected "rank two expression annotation with unused class" (dummy ++ annotation) "type constructor mismatch";
    recursiveRejected "invalid universal declaration without classes" invalid "type constructor mismatch";
    recursiveRejected "invalid universal declaration with unused class" (dummy ++ invalid) "type constructor mismatch";
    recursiveAccepted "declaration signature scopes parameter type variable"
      "let f : forall a. a -> a = \\(x :: a) -> x in f" recursiveIdentity;
    recursiveAccepted "declaration signature scopes parameter type variable with unused class"
      (dummy ++ "let f : forall a. a -> a = \\(x :: a) -> x in f") recursiveIdentity;
    recursiveAccepted "recursive declaration signature scopes parameter type variable"
      "let rec { f : forall a. a -> a; f = \\(x :: a) -> x } in f" recursiveIdentity;
    recursiveAccepted "recursive declaration signature scopes parameter type variable with unused class"
      (dummy ++ "let rec { f : forall a. a -> a; f = \\(x :: a) -> x } in f") recursiveIdentity;
    recursiveAccepted "qualified expression annotation retains dictionary arity"
      "class C a where { method : a -> Int }; instance C Int where { method x = x }; let f = ((\\x -> method x) : forall a. C a => a -> Int) in f 1"
      recursiveInt;
    recursiveAccepted "raw do declaration preserves rank two checking"
      "do { let use : (forall a. a -> a) -> Bool = \\g -> let n = g 1 in g true; use (\\x -> x) }"
      recursiveBool;
    recursiveRejected "raw do expression annotation preserves inference"
      "do { let use = ((\\g -> let n = g 1 in g true) : (forall a. a -> a) -> Bool); use (\\x -> x) }"
      "type constructor mismatch";
    recursiveAccepted "shared top declaration preserves rank two checking"
      (source sharedDeclaration) recursiveBool;
    recursiveAccepted "shared local declaration preserves rank two checking"
      (source sharedLocal) recursiveBool;
    recursiveRejected "shared expression annotation preserves inference"
      (source sharedAnnotation) "type constructor mismatch";
    recursiveModulesAccepted "cross module declaration preserves rank two checking"
      (M.singleton "Use" ((,) "Use.emlf"
        "module Use where\nuse : (forall a. a -> a) -> Bool\nuse g = let n = g 1 in g true\n"))
      "module Main where\nimport Use\nmain = use (\\x -> x)\n" recursiveBool;
    recursiveModulesAccepted "shared cross module declaration preserves rank two checking"
      (M.singleton "Use" ((,) "Use.hs" (prologue ++
        "module Use where\nimport MLF.Primitive\nuse :: (forall a. a -> a) -> Bool\nuse g = let { n = g 1 } in g True\n")))
      (prologue ++ "module Main where\nimport MLF.Primitive\nimport Use\nmain = use (\\x -> x)\n")
      recursiveBool;
    frontendRepairProvenanceChecks
  };
  frontendRepairFieldChecks :: IO ();
  frontendRepairFieldChecks = do {
    let {
      poly = "data Poly = Poly (forall a. a -> a); ";
      polyType = XCon "Poly" [];
      maybe = "data Maybe a = Nothing | Just a; ";
      list = "data List a = Nil | Cons a (List a); ";
      maybeBool = XCon "Maybe" ((:) recursiveBool [])
    };
    recursiveAccepted "declared forall field automatic integer instance"
      (poly ++ "\\p -> case p of { Poly g -> g 1 }")
      (XArrow polyType recursiveInt);
    recursiveAccepted "declared forall field independent Int and Bool instances"
      (poly ++ "\\p -> case p of { Poly g -> let n = g 1 in g true }")
      (XArrow polyType recursiveBool);
    recursiveAccepted "declared forall field captured by mutual recursion"
      (poly ++ "\\p -> case p of { Poly g -> let rec { f n = if eqInt n 0 then g true else h (g n); h n = f n } in f 1 }")
      (XArrow polyType recursiveBool);
    recursiveAccepted "declared forall field preserves captured result parameter"
      "data H a = H (forall b. b -> a); \\x -> case H (\\z -> x) of { H f -> let n = f 1 in f true }"
      recursiveIdentity;
    recursiveRejected "declared forall field cannot generalize captured result parameter"
      "data H a = H (forall b. b -> a); \\x -> case H (\\z -> x) of { H f -> let n : Int = f 1 in (f true :: Bool) }"
      "type constructor mismatch";
    recursiveAccepted "declared forall field shadows datatype parameter"
      "data Shadow a = Shadow (forall a. a -> a); \\p -> case p of { Shadow f -> let n = f 1 in f true }"
      (XForall (XTyVar 0) XBot
        (XArrow (XCon "Shadow" ((:) (XVar (XTyVar 0)) [])) recursiveBool));
    recursiveAccepted "declared forall fields retain independent schemes"
      "data P = P (forall a. a -> a) (forall a. a -> a); \\p -> case p of { P f g -> let n = f 1 in let b = g true in let m = g 2 in f false }"
      (XArrow (XCon "P" []) recursiveBool);
    recursiveAccepted "declared forall field nested pattern extraction"
      "data P = P (forall a. a -> a); data Outer = Outer P; \\o -> case o of { Outer (P f) -> let n = f 1 in f true }"
      (XArrow (XCon "Outer" []) recursiveBool);
    recursiveAccepted "declared forall field term shadowing retains lexical scope"
      "data P = P (forall a. a -> a); \\p -> case p of { P f -> let f = \\x -> 1 in f true }"
      (XArrow (XCon "P" []) recursiveInt);
    recursiveAccepted "declared forall field preserves nested rank"
      "data P = P (forall t. (forall a. a -> a) -> t -> t); \\p -> case p of { P f -> let n = f (\\x -> x) 1 in f (\\x -> x) true }"
      (XArrow (XCon "P" []) recursiveBool);
    recursiveAccepted "ordinary field preserves existing nested rank"
      "data Use = Use ((forall a. a -> a) -> Bool); \\v -> case v of { Use k -> k (\\x -> x) }"
      (XArrow (XCon "Use" []) recursiveBool);
    recursiveAccepted "declared forall field independently instantiates higher kinds"
      (maybe ++ list ++
       "data HK = HK (forall (f : * -> *) a. f a -> f a); \\v -> case v of { HK k -> let n = k (Just 1) in k (Cons true Nil) }")
      (XArrow (XCon "HK" []) (XCon "List" ((:) recursiveBool [])));
    recursiveAccepted "declared forall field preserves captured higher kind"
      (maybe ++
       "data Wrap (f : * -> *) = Wrap (forall a. f a -> f a); \\v -> case v of { Wrap k -> let n = k (Just 1) in k (Just true) }")
      (XArrow (XCon "Wrap" ((:) (XCon "Maybe" []) [])) maybeBool);
    recursiveRejected "declared forall field cannot generalize captured higher kind"
      (maybe ++ list ++
       "data Wrap (f : * -> *) = Wrap (forall a. f a -> f a); \\v -> case v of { Wrap k -> let n = k (Just 1) in k (Cons true Nil) }")
      "type constructor mismatch";
    recursiveRejected "ordinary unknown field remains monomorphic"
      "data Box a = Box a; case Box (\\x -> x) of { Box f -> let n = f 1 in f true }"
      "type constructor mismatch";
    -- A forall supplied through a datatype argument is not a syntactically
    -- declared forall field. This separate limitation remains unchanged.
    recursiveRejected "scrutinee annotated polymorphic datatype argument remains explicit residual"
      "data Box a = Box a; case (Box (\\x -> x) :: Box (forall a. a -> a)) of { Box f -> let n = f 1 in f true }"
      "cannot raise a protected type variable";
    recursiveRejected "declared universal field still checks constructor argument"
      "data P = P (forall a. a -> a); P (\\x -> 1)"
      "cannot instantiate a rigid or protected type variable";
    recursiveAccepted "declared vacuous forall field extracts normalized instance"
      "data V = V (forall a. Int); \\v -> case v of { V x -> x }"
      (XArrow (XCon "V" []) recursiveInt);
    recursiveAccepted "declared vacuous forall field preserves captured parameter"
      "data V p = V (forall a. p); \\v -> case v of { V x -> x }"
      (XForall (XTyVar 0) XBot
        (XArrow (XCon "V" ((:) (XVar (XTyVar 0)) [])) (XVar (XTyVar 0))));
    -- This is a known constructor-side residual, not a field-extraction fix.
    -- Keep the original source and verification diagnostic as an explicit
    -- control rather than silently claiming that V 1 has been repaired.
    check "vacuous forall constructor mismatch remains explicit residual"
      (case C.compile "FrontendRepair.emlf" "data V = V (forall a. Int); V 1" of {
        Left error -> (case C.phase error of { Verification -> True; _ -> False }) &&
          recursiveStartsWith "application type mismatch" (C.diagnostic error);
        Right _ -> False
      })
  };
  frontendRepairChecks :: IO ();
  frontendRepairChecks = do {
    frontendRepairSignatureChecks;
    frontendRepairFieldChecks;
    putStrLn "shared frontend: declaration provenance and declared forall field checks passed"
  };
  recursiveInferenceChecks :: IO ();
  recursiveInferenceChecks = do {
    recursiveRight "recursive class demand planner" ClassDemandTests.checkAll;
    recursiveAccepted "ordinary unsigned factorial"
      "let rec { fact n = if eqInt n 0 then 1 else mulInt n (fact (subInt n 1)) } in fact"
      (XArrow recursiveInt recursiveInt);
    let {
      evenDefinition = "even n = if eqInt n 0 then true else odd (subInt n 1)";
      oddDefinition = "odd n = if eqInt n 0 then false else even (subInt n 1)"
    };
    mutual <- recursiveAccepted "mutual unsigned even odd"
      ("let rec { " ++ (evenDefinition ++ ("; " ++ (oddDefinition ++ " } in even"))))
      (XArrow recursiveInt recursiveBool);
    recursiveOrder "mutual source order retains one runtime knot"
      ((:) "even" ((:) "odd" [])) mutual;
    reordered <- recursiveAccepted "mutual declaration reordering"
      ("let rec { " ++ (oddDefinition ++ ("; " ++ (evenDefinition ++ " } in even"))))
      (XArrow recursiveInt recursiveBool);
    recursiveOrder "reordered source retains one runtime knot"
      ((:) "odd" ((:) "even" [])) reordered;
    recursiveAccepted "recursive identity generalized export"
      "let rec { f x = if true then x else f x } in f" recursiveIdentity;
    recursiveAccepted "recursive higher rank parameter annotation"
      "let rec { f = \\(g : forall a. a -> a) -> \\n -> if eqInt n 0 then let x : Int = g 1 in (g true :: Bool) else f g (subInt n 1) } in f"
      (XArrow recursiveIdentity (XArrow recursiveInt recursiveBool));
    recursiveRejected "recursive unannotated parameter stays monomorphic"
      "let rec { f = \\g -> \\n -> if eqInt n 0 then let x : Int = g 1 in (g true :: Bool) else f g (subInt n 1) } in f"
      "type constructor mismatch";
    recursiveAccepted "recursive export used at Int and Bool"
      "let rec { f x = if true then x else f x } in let n : Int = f 1 in (f true :: Bool)"
      recursiveBool;
    recursiveAccepted "mutual SCC generalized only after solving"
      "let rec { f x = if true then x else g x; g y = f y } in let n : Int = f 1 in (g true :: Bool)"
      recursiveBool;
    recursiveAccepted "mutual SCC exports independent instances"
      "let rec { f x = if true then x else g x; g y = f y } in let n : Int = g 1 in (f true :: Bool)"
      recursiveBool;
    mixed <- recursiveAccepted "mixed signed polymorphic cycle"
      "let rec { f : forall a. a -> a; f x = g x; g x = f x } in let n : Int = f 1 in (g true :: Bool)"
      recursiveBool;
    recursiveOrder "mixed signed source order retains one runtime knot"
      ((:) "f" ((:) "g" [])) mixed;
    recursiveAccepted "mixed signed cycle exports unsigned polymorphism"
      "let rec { g x = f x; f : forall a. a -> a; f x = g x } in g"
      recursiveIdentity;
    let {
      nest = "data Nest a = Tip a | Step (Nest (Nest a)); ";
      depth = "depth n = case n of { Tip x -> 0; Step ns -> addInt 1 (depth ns) }"
    };
    recursiveAccepted "signed Nest polymorphic recursion preserved"
      (nest ++ ("let rec { depth : forall a. Nest a -> Int; " ++ (depth ++ " } in depth")))
      (XForall (XTyVar 0) XBot
        (XArrow (XCon "Nest" ((:) (XVar (XTyVar 0)) [])) recursiveInt));
    recursiveRejected "unsigned Nest polymorphic recursion rejected"
      (nest ++ ("let rec { " ++ (depth ++ " } in depth"))) "cyclic structure/binding dependencies";
    recursiveAccepted "nonrecursive capture still generalizes independent argument"
      "\\z -> let f = \\n -> z in let i = f 0 in f true" recursiveIdentity;
    recursiveRejected "nonrecursive capture cannot generalize environment"
      "\\z -> let f = \\n -> z in let i : Int = f 0 in (f true :: Bool)"
      "type constructor mismatch";
    recursiveAccepted "recursive entire root remains environment owned"
      "\\z -> let rec { f = if true then z else f } in f" recursiveIdentity;
    recursiveRejected "recursive entire root cannot generalize environment"
      "\\z -> let rec { f = if true then z else f } in let i : Int = f in (f :: Bool)"
      "type constructor mismatch";
    recursiveAccepted "recursive capture generalizes independent argument"
      "\\z -> let rec { f n y = if eqInt n 0 then z else f (subInt n 1) y } in let i = f 0 true in f 1 0"
      recursiveIdentity;
    recursiveRejected "recursive capture cannot generalize environment"
      "\\z -> let rec { f n = if eqInt n 0 then z else f (subInt n 1) } in let i : Int = f 0 in (f 1 :: Bool)"
      "type constructor mismatch";
    recursiveAccepted "mutual capture preserves environment sharing"
      "\\z -> let rec { f n = if eqInt n 0 then g n else f (subInt n 1); g n = if eqInt n 0 then z else f (subInt n 1) } in f 1"
      recursiveIdentity;
    recursiveRejected "indirect recursive capture cannot generalize environment"
      "\\z -> let rec { f n = if eqInt n 0 then g n else f (subInt n 1); g n = if eqInt n 0 then z else f (subInt n 1) } in let i : Int = f 0 in (g 1 :: Bool)"
      "type constructor mismatch";
    recursiveRejected "recursive self application occurs check"
      "let rec { f x = f f } in f" "cyclic structure/binding dependencies";
    recursiveRejected "recursive shared uses conflict at Int and Bool"
      "let rec { f x = if true then x else let n : Int = f 1 in (f true :: Bool) } in f"
      "type constructor mismatch";
    recursiveRejected "mutual SCC cannot generalize early"
      "let rec { f x = if true then x else g x; g y = let n : Int = f 1 in (f true :: Bool) } in f"
      "type constructor mismatch";
    recursiveRejected "mixed signed universal contract still checked"
      "let rec { f : forall a. a -> a; f x = g x; g y = if true then 1 else f y } in f"
      "type constructor mismatch: Skolem";
    recursiveAccepted "nested group captures outer recursive binder"
      "let rec { f n = let rec { g m = if eqInt m 0 then f 0 else g (subInt m 1) } in if eqInt n 0 then 0 else g (subInt n 1) } in f"
      (XArrow recursiveInt recursiveInt);
    recursiveAccepted "peer only variables retain recursive evidence scope"
      "let rec { f x y = if g x then y else f x y; g x = let k = f x in true } in let b : Bool = f 0 true in let n : Int = f true 0 in g 0"
      recursiveBool;
    -- Both wants are concrete, but belong to distinct instances of one class.
    -- This does not ask the unsigned SCC to invent a generalized dictionary API.
    recursiveAccepted "recursive concrete class wants retain distinct instances"
      ("class Inspect a where { inspect : a -> Bool }; " ++
       "instance Inspect Int where { inspect = \\x -> true }; " ++
       "instance Inspect Bool where { inspect = \\x -> x }; " ++
       "let rec { f n = if eqInt n 0 then inspect n else if inspect true then f (subInt n 1) else false } in f")
      (XArrow recursiveInt recursiveBool);
    let {
      divergentModules = M.fromList compareString
        ((:) ((,) "A" ((,) "A.emlf" "module A where\nimport qualified B\nf x = B.g x\n"))
        ((:) ((,) "B" ((,) "B.emlf" "module B where\nimport qualified A\ng x = A.f x\n")) []));
      identityModules = M.fromList compareString
        ((:) ((,) "A" ((,) "A.emlf" "module A where\nimport qualified B\nf x = if true then x else B.g x\n"))
        ((:) ((,) "B" ((,) "B.emlf" "module B where\nimport qualified A\ng x = A.f x\n")) []))
    };
    -- This original source diverges. Compile and check it, never evaluate it.
    recursiveModulesAccepted "cross module unsigned divergent cycle type only"
      divergentModules "module Main where\nimport A\nmain = f 0\n" XBot;
    recursiveModulesAccepted "cross module unsigned identity generalized export"
      identityModules "module Main where\nimport A\nmain = f\n" recursiveIdentity;
    recursiveModulesAccepted "cross module unsigned exports used at Int and Bool"
      identityModules
      "module Main where\nimport A\nmain = let n : Int = f 1 in (f true :: Bool)\n" recursiveBool;
    let {
      transitiveInstances = M.fromList compareString
        ((:) ((,) "Inspect" ((,) "Inspect.emlf" "module Inspect where\nclass Inspect a where { inspect : a -> Bool }\n"))
        ((:) ((,) "Instances" ((,) "Instances.emlf" "module Instances () where\nimport Inspect\ninstance Inspect Int where { inspect = \\x -> true }\n"))
        ((:) ((,) "Bridge" ((,) "Bridge.emlf" "module Bridge () where\nimport Instances ()\n"))
        ((:) ((,) "A" ((,) "A.emlf" "module A (f) where\nimport Inspect\nimport Bridge ()\nimport qualified B\nf n = if eqInt n 0 then inspect n else B.g (subInt n 1)\n"))
        ((:) ((,) "B" ((,) "B.emlf" "module B (g) where\nimport qualified A\ng n = A.f n\n")) [])))))
    };
    recursiveModulesAccepted "cross module unsigned recursion sees transitive defining instance"
      transitiveInstances "module Main where\nimport A\nmain = f 1\n" recursiveBool;
    recursiveDictionaryScopeControl;
    qualifiedRecursiveChecks;
    recursiveProjectionChecks;
    frontendRepairChecks;
    let {
      f = XName 1 "f";
      x = XName 2 "x";
      malformed = XLetRec
        ((:) ((,,) f (XArrow recursiveInt recursiveInt)
          (XAbs x recursiveInt (XBoolTerm True))) []) (XVarTerm f)
    };
    check "current checker rejects recursive RHS type mismatch" (isLeft (Check.checkClosed malformed));
    check "independent checker rejects recursive RHS type mismatch" (isLeft (Independent.checkClosed malformed));
    putStrLn "shared frontend: recursive inference checks passed"
  };
  frontendChecks :: IO ();
  frontendChecks =
    do {
      check "legacy malformed pragma comment"
        (isRight
           (P.parseModule "Legacy.emlf" "{-# LANGUAGE X, #-}\nmodule Legacy where\nmain = 1\n"));
      check "legacy pragma-shaped ordinary comment"
        (isRight
           (P.parseModule "Legacy.emlf"
              "{-# arbitrary legacy comment -}\nmodule Legacy where\nmain = 1\n"));
      check "shared malformed pragma rejected"
        (isLeft
           (P.parseModule "Example.hs"
              (prologue ++
               "{-# LANGUAGE X, #-}\nmodule Example where\nimport MLF.Primitive\nmain = 1\n")));
      check "module metadata" (accept "main = 42");
      check "forward group scope" forwardScope;
      check "legacy sequential scope" legacyScope;
      check "fixed do identity" fixedDo;
      check "mixed per-file profiles" mixedGraph;
      check "imported hook identity" importedHook;
      check "primitive facade link" (linked "main = do { printInt 42; ioReturn () }");
      check "facade implementation host" (linked "main = implementationHost");
      check "ordinary bind binding"
        (case P.parseModule "Example.hs"
                (prologue ++
                 "module Example where\nimport MLF.Primitive hiding (bind)\nbind = 42\nmain = do { ioReturn bind; ioReturn bind }\n") of {
           Left _ -> False;
           Right m -> isRight (Modules.linkModules ImplicitPrelude ((:) m []))
         });
      check "closed recursive group"
        (accept "main = let { f :: Int -> Int; f x = g x; g :: Int -> Int; g x = f x } in 1");
      check "unsigned recursive group" (accept "main = let { f x = f x } in 1");
      check "mixed signed cycle"
        (accept "main = let { f :: Int -> Int; f x = g x; g x = f x } in 1");
      check "do let forward scope" (accept "main = do { let { x = y; y = 3 }; ioReturn x }");
      check "constructor do patterns accepted"
        (accept "main = do { Pair x y <- ioReturn (Pair 1 2); ioReturn x }");
      check "refutable do preserves pattern and canonical failure hooks" refutableDo;
      check "wildcard do bind" (accept "main = do { _ <- ioReturn 1; ioReturn 2 }");
      check "same-indent operator continuation rejected" (reject "main = 1 +\n2");
      check "same-indent RHS rejected" (reject "main =\n1");
      check "indented RHS accepted" (accept "main =\n  1");
      check "explicit separator layout accepted" (accept "a = 1;\nmain = a");
      check "implicit block closed by explicit brace rejected"
        (reject "main = do { ioReturn 1; do\n  ioReturn 2 }");
      check "explicit local braces" (reject "main = let x = 1 in x");
      check "implicit inline do" (reject "main = do ioReturn 1");
      check "implicit inline case" (reject "main = case True of True -> 1; False -> 2");
      check "recursive spelling rejected" (reject "main = let rec { x :: Int; x = x } in 1");
      check "single-colon signature" (reject "main : Int\nmain = 1");
      check "inline signature" (reject "main :: Int = 1");
      check "double-colon kinds" (accept "f :: forall (m :: * -> *) a. m a -> m a\nf x = x");
      check "legacy kind colon rejected" (reject "f :: forall (m : * -> *) a. m a -> m a\nf x = x");
      check "free signature variable" (reject "f :: a -> a\nf x = x");
      check "higher rank arrow" (accept "f :: (forall a. a -> a) -> Int\nf g = g 1");
      check "impredicative argument" (reject "f :: Box (forall a. a -> a)\nf = Box (\\x -> x)");
      check "bounded forall rejected" (reject "f :: forall (a >= Int). a -> a\nf x = x");
      check "rigid forall rejected" (reject "f :: forall (a = Int). a -> a\nf x = x");
      check "existential annotation rejected" (reject "f :: exists a. a -> a\nf x = x");
      check "nested context rejected" (reject "f :: forall a. (Monad IO => IO a) -> IO a\nf x = x");
      check "string patterns accepted" (accept "f \"x\" = 1\nf _ = 2");
      check "typed patterns rejected" (reject "f (x :: Int) = x");
      check "tuple expressions accepted" (accept "main = (1,2)");
      check "unit sugar accepted" (accept "main = ()");
      check "list sugar accepted" (accept "main = [1]");
      check "canonical list-tail accepted" (accept "main = 1 : []");
      check "tuple types accepted" (accept "main :: (Int, Int)\nmain = (1,2)");
      check "tuple patterns accepted" (accept "f (x,y) = x");
      check "typed negative literal" (accept "main :: Int\nmain = (-1)");
      check "bare negative rejected" (reject "main = -1");
      check "unary plus rejected" (reject "main = +1");
      check "nonfinite floating rejected" (reject "main = 1e999");
      check "malformed numeric adjacency" (reject "main = 1abc");
      check "unicode identifiers rejected" (reject "é = 1");
      check "unicode strings accepted" (accept "main = \"λ\"");
      check "lambda-dot rejected" (reject "main = \\x.x");
      check "compact delimiter-prefix rejected" (reject "main = \\x->-1");
      check "Haskell reserved identifiers" (reject "type = 1");
      check "ordinary contextual identifiers" (accept "pattern x = x\nmain = pattern 1");
      check "ordinary fromInteger binding" (accept "main = let { fromInteger = 1 } in fromInteger");
      check "ordinary negate binding" (accept "main = \\negate -> negate");
      check "ordinary otherwise binding"
        (accept "main = case Unit of { Unit -> \\otherwise -> otherwise }");
      check "ordinary fromString spelling" (accept "main = fromString \"x\"");
      check "qualified ordinary spelling" (accept "main = MLF.Primitive.fromInteger 1");
      check "ordinary ifThenElse use" (linked "main = ifThenElse True 1 2");
      check "otherwise value" (linked "main = otherwise");
      check "guarded equations explicitly excluded" (reject "f x | x == 0 = 1 | otherwise = 2");
      check "partial guard rejected" (reject "f x | x == 0 = 1");
      check "tab rejected" (reject "main =\n\t1");
      check "comment operator ambiguity rejected" (reject "main = 1 --oops");
      check "embedded marker is data" (accept "main = \"-- mlf:syntax unknown\"");
      check "missing marker rejected"
        (isLeft (P.parseModule "Example.hs" "module Example where\nmain = 1\n"));
      check "unknown marker rejected"
        (isLeft
           (P.parseModule "Example.emlf"
              "-- mlf:syntax future-v2\nmodule Example where\nmain = 1\n"));
      check "duplicate marker rejected"
        (isLeft
           (P.parseModule "Example.hs"
              (prologue ++
               "-- mlf:syntax shared-haskell-v1\nmodule Example where\nimport MLF.Primitive\nmain = 1\n")));
      check "missing extensions rejected"
        (isLeft
           (P.parseModule "Example.hs"
              "-- mlf:syntax shared-haskell-v1\nmodule Example where\nimport MLF.Primitive\nmain = 1\n"));
      check "unsupported pragma rejected"
        (isLeft
           (P.parseModule "Example.hs"
              (prologue ++
               "{-# LANGUAGE Strict #-}\nmodule Example where\nimport MLF.Primitive\nmain = 1\n")));
      check "profile mismatch rejected"
        (isLeft (P.parseModuleWithProfile LegacyEmlfV1 "Example.hs" (source "main = 1")));
      check "facade import optional"
        (isRight (P.parseModule "Example.hs" (prologue ++ "module Example where\nmain = 1\n")));
      check "selective facade accepted"
        (isRight
           (P.parseModule "Example.hs"
              (prologue ++ "module Example where\nimport MLF.Primitive (Int)\nmain = 1\n")));
      check "qualified facade accepted"
        (isRight
           (P.parseModule "Example.hs"
              (prologue ++ "module Example where\nimport qualified MLF.Primitive\nmain = 1\n")));
      check "ordinary hook hiding accepted"
        (isRight
           (P.parseModule "Example.hs"
              (prologue ++
               "module Example where\nimport MLF.Primitive hiding (ifThenElse)\nmain = 1\n")));
      check "facade reexport accepted"
        (isRight
           (P.parseModule "Example.hs"
              (prologue ++
               "module Example (module MLF.Primitive) where\nimport MLF.Primitive\nmain = 1\n")));
    check "RebindableSyntax excluded" (isLeft (P.parseModule "Example.hs" (prologue ++ "{-# LANGUAGE RebindableSyntax #-}\nmodule Example where\nmain = 1\n")));
    check "ordinary source True needs scope" (not (linkRaw "module Example where\nmain = True\n"));
    check "ordinary source Unit needs scope" (not (linkRaw "module Example where\nmain = Unit\n"));
    check "ordinary Unit type needs scope" (not (linkRaw "module Example where\nmain :: Unit\nmain = 1\n"));
    check "hidden Bool constructor" (not (linkRaw "module Example where\nimport MLF.Primitive hiding (True)\nmain = True\n"));
    check "qualified canonical operator" (linked "main = 1 MLF.Primitive.+ 2");
    check "operator prefix" (linked "main = (+) 1 2");
    check "ordinary symbolic local prefix" (linked "main = let { (++) x y = subInt x y } in (++) 10 3");
    check "noncanonical infix explicit rejection" (not (linked "main = let { (++) x y = subInt x y } in 10 ++ 3 ++ 1"));
    check "method selective import" (linkRaw "module Example where\nimport MLF.Primitive (IO, Monad((>>=)), ioReturn)\nmain = ioReturn 1 >>= ioReturn\n");
    check "qualified methods visible" (linkRaw "module Example where\nimport qualified MLF.Primitive as P\ndata Box a = Box a\ninstance P.Functor Box where { fmap f (Box x) = Box (f x) }\nmain = Box 1\n");
    check "hidden instance method rejected" (not (linkRaw "module Example where\nimport MLF.Primitive (Functor)\ndata Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\nmain = Box 1\n"));
    check "standard hierarchy defaults" (linked "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nmain = do { Box 1; return 2 }");
    check "standard liftA2 minimum" (linked "data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; liftA2 f (Box x) (Box y) = Box (f x y) }\nmain = pure 1");
    check "standard missing minimum rejected" (not (linked "data Box a = Box a\ninstance Functor Box where { (<$) x y = Box x }\nmain = Box 1"));
      check "recursive local infix rejected" (recursiveInfixRejected "main = let { (+) x y = x + y } in (+) 1 2");
      check "signed recursive local infix rejected" (recursiveInfixRejected "main = let { (+) :: Int -> Int -> Int; (+) x y = x + y } in (+) 1 2");
      check "qualified operator whitespace rejected" (reject "main = 1 MLF.Primitive . + 2");
      check "legacy Prelude excluded" (isLeft (P.parseModule "Example.hs" (prologue ++ "module Example where\nimport Prelude\nmain = 1\n")));
      check "legacy Prelude identity excluded" (isLeft (P.parseModule "Prelude.hs" (prologue ++ "module Prelude where\nmain = 1\n")));
      check "legacy-only words are ordinary identifiers" (accept "rec = 1\nexists = 2\ntrue = 3\nfalse = 4\nbot = 5\nmain = rec + exists + true + false + bot");
      check "metadata accepts MLF.Primitive" (isRight (Separate.validModuleName "MLF.Primitive"));
      check "metadata accepts Prelude" (isRight (Separate.validModuleName "Prelude"));
      check "metadata accepts Example.Nested" (isRight (Separate.validModuleName "Example.Nested"));
      check "metadata rejects malformed identity 0" (isLeft (Separate.validModuleName ""));
      check "metadata rejects malformed identity 1" (isLeft (Separate.validModuleName "lowercase"));
      check "metadata rejects malformed identity 2" (isLeft (Separate.validModuleName "Example..Nested"));
      check "metadata rejects malformed identity 3" (isLeft (Separate.validModuleName "Example where {}"));
      check "metadata rejects malformed identity 4" (isLeft (Separate.validModuleName " Example"));
      check "metadata rejects malformed identity 5" (isLeft (Separate.validModuleName "Example "));
      check "metadata rejects malformed identity 6" (isLeft (Separate.validModuleName "Example {- comment -}"));
      check "shared builtin source ownership reserved" (isLeft (P.parseModule "Primitive.hs" (prologue ++ "module MLF.Primitive where\nmain = 1\n")));
      check "legacy builtin source ownership reserved" (isLeft (P.parseModule "Primitive.emlf" "module MLF.Primitive where\nmain = 1\n"));
      check "builtin checked artifact round trip" builtinRoundTrip;
      check "unsafe hint roundtrip 0" (hintRoundTrip "$f");
      check "unsafe hint roundtrip 1" (hintRoundTrip "$defaultA");
      check "unsafe hint roundtrip 2" (hintRoundTrip ">>=");
      check "unsafe hint roundtrip 3" (hintRoundTrip "");
      check "unsafe hint roundtrip 4" (hintRoundTrip "_x");
      check "valid hint preserved alpha_2" (eqString (Constraint.targetNameHint "alpha_2") "alpha_2");
      check "valid hint preserved beta'" (eqString (Constraint.targetNameHint "beta'") "beta'");
      check "valid hint preserved λ" (eqString (Constraint.targetNameHint "λ") "λ");
      check "valid hint preserved let" (eqString (Constraint.targetNameHint "let") "let");
      check "valid hint preserved mlfInternal_36_102" (eqString (Constraint.targetNameHint "mlfInternal_36_102") "mlfInternal_36_102");
      check "default and generated-name capture roundtrip" (sourceRoundTrip captureDefaults);

      recursiveInferenceChecks;
      putStrLn "shared frontend: parser and namespace checks passed"
    };
  nativeFirst :: IO ();
  nativeFirst = do {
    check "default and generated-name capture execution" (evaluatesInt captureDefaults 40);
    check "native standard hierarchy inference" (evaluatesInt (boxMonad ++ "main = unBox (do { x <- pure 40; return (x + 2) })") 42);
    check "native Applicative defaults" (evaluatesInt (boxApplicative ++ "main = unBox (liftA2 addInt (Box 30) (Box 12))") 42);
    check "native Applicative liftA2 minimum" (evaluatesInt (boxFunctor ++ "instance Applicative Box where { pure = Box; liftA2 f (Box x) (Box y) = Box (f x y) }\nmain = unBox (Box (addInt 30) <*> Box 12)") 42);
    check "native do preserves overridden sequencing" (failsWith (boxApplicative ++ "instance Monad Box where { (>>=) (Box x) f = f x; (>>) a b = panic \"overridden sequence\" }\nmain = unBox (do { Box 1; Box 2 })") "overridden sequence");
    check "native fmap default partial demand" (failsWith "data Box a = Box a\ninstance Functor Box where { fmap = panic \"fmap bottom\" }\nmain = seq (((<$) 1) :: Box Int -> Box Int) 7" "fmap bottom");
      putStrLn "shared frontend: first native semantics checks passed"
    };
  nativeSecond :: IO ();
  nativeSecond = do {
    check "native ap default function demand" (failsWith (boxFunctor ++ "instance Applicative Box where { pure = Box; liftA2 = panic \"liftA2 bottom\" }\nmain = seq ((<*>) :: Box (Int -> Int) -> Box Int -> Box Int) 7") "liftA2 bottom");
    check "native left default function demand" (failsWith (boxFunctor ++ "instance Applicative Box where { pure = Box; liftA2 = panic \"liftA2 bottom\" }\nmain = seq ((<*) :: Box Int -> Box Int -> Box Int) 7") "liftA2 bottom");
    check "native liftA2 default partial demand" (failsWith (boxFunctor ++ "instance Applicative Box where { pure = Box; (<*>) = panic \"ap bottom\" }\nmain = seq (liftA2 addInt (Box 1) :: Box Int -> Box Int) 7") "ap bottom");
    check "native return default function demand" (failsWith (boxFunctor ++ "instance Applicative Box where { pure = panic \"pure bottom\"; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\nmain = seq (return :: Int -> Box Int) 7") "pure bottom");
    check "native sequencing default partial WHNF" (evaluatesInt (boxApplicative ++ "instance Monad Box where { (>>=) = panic \"bind bottom\" }\nmain = seq (((>>) (Box 1)) :: Box Int -> Box Int) 7") 7);
      putStrLn "shared frontend: checks passed"
    };

  checkFiles :: Int -> Int -> IO ();
  checkFiles i count = if i >= count then putStrLn "shared source files: grammar checks passed" else do {
    file <- getArg i;
    text <- readFile file;
    case P.parseModule file text of {
      Left error -> do { putErr (file ++ (": " ++ (error ++ "\n"))); exitWith 1 };
      Right _ -> checkFiles (i + 1) count
    }
  };
  main :: IO ();
  main = do {
    count <- getArgCount;
    if count == 0 then do { frontendChecks; nativeFirst; nativeSecond }
    else do {
      mode <- getArg 0;
      if eqString mode "--recursive-inference" then recursiveInferenceChecks
      else if eqString mode "--frontend" then frontendChecks
      else if eqString mode "--native-first" then nativeFirst
      else if eqString mode "--native-second" then nativeSecond
      else checkFiles 0 count
    }
  }
}
