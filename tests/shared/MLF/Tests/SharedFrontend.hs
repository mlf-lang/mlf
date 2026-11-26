-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Tests.SharedFrontend where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Parser as P;
  import qualified Bootstrap.Parsec as Parsing;
  import qualified Bootstrap.Lexer as Lexer;
  import qualified Bootstrap.Separate as Separate;
  import qualified Bootstrap.CrateArtifact as Artifact;
  import qualified Bootstrap.CrateQuery as Query;
  import qualified Bootstrap.CrateGraph as CrateGraph;
  import qualified Bootstrap.QueryGraph as QueryGraph;
  import qualified Bootstrap.Bitstream as Wire;
  import qualified Bootstrap.ArtifactStructure as Structure;
  import qualified Bootstrap.InferenceUnit as Inference;
  import qualified Bootstrap.SourceInference as Source;
  import qualified Bootstrap.IntSet as IntSet;
  import qualified Bootstrap.OpenFragment as Open;
  import qualified Bootstrap.IndexVec as Index;
  import qualified Bootstrap.Lexer as L;
  import qualified Bootstrap.Module as Modules;
  import qualified Bootstrap.Surface as Surface;
  import qualified Bootstrap.Dependency as Dependency;
  import qualified Bootstrap.SourceEquality as SourceEquality;
  import qualified Bootstrap.Map as M;
  import qualified Bootstrap.Compiler as C;
  import qualified Bootstrap.Constraint as Constraint;
  import qualified Bootstrap.Elaborate as Elaborate;
  import qualified Bootstrap.Graph as Graph;
  import qualified Bootstrap.IntMap as IM;
  import qualified Bootstrap.Data as Data;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Set as Set;
  import qualified Bootstrap.X.Parser as XP;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Type as XT;
  import qualified Bootstrap.Runtime as Runtime;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Tests.IndependentCheck as Independent;
  import qualified Tests.IndependentType as IndependentType;
  import qualified MLF.Tests.ClassDemand as ClassDemandTests;
  import qualified Test.Assert as A;
  import qualified Test.Case as Case;
  import qualified Test.Runner as Runner;
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
  atomNameCase = case (,) (parse "main = true") (parse "main = True") of {
    (,) (Right (SourceModule _ _ _ _ _ _ _ [((,,) _ _
          (SCallSite label (SourceSpan _ _ _ 5 8 5 12) (SVar variable)))] _ _))
        (Right (SourceModule _ _ _ _ _ _ _ [((,,) _ _ (SConstructor constructor))] _ _)) ->
      eqString variable "true" && eqString label variable && eqString constructor "$MLF.Source.True";
    _ -> False
  };
  openSymbolOrder = let {
    iface names = Artifact.CrateInterface "crate" [] [] [] [] [] [] [] []
      (map (\n -> (,) n (XCon "Int" [])) names) "" "" []
  } in case (,) (Artifact.openIndex [iface ["z","a"]] [])
                (Artifact.openIndex [iface ["x"],iface ["x"]] []) of {
    (,) (Right (Artifact.OpenIndex ids _ _ _)) (Left message) ->
      eqString message "duplicate crate crate symbol" &&
      case (,) (M.lookup compareString "z" ids) (M.lookup compareString "a" ids) of {
        (,) (Just first) (Just second) -> Index.toInt first == 0 && Index.toInt second == 1;
        _ -> False
      };
    _ -> False
  };
  boundedDeclarationReads = let {
    readId i = XVarTerm (XName i "same hint");
    source = XLetRec [((,,) (XName 1 "binder") (XCon "Int" []) (readId (0 - 3)))]
      (XApp (readId 5) (XApp (readId 4) (readId 90)));
    before name = if X.nameId name < 5 then Set.singleton name else Set.empty;
    ids names = map X.nameId (Set.toList names)
  } in eqList eqInt (ids (Artifact.variableReadsWith before source)) [0 - 3,4] &&
    eqList eqInt (ids (Artifact.declarationVariableReads source)) [0 - 3,4,5,90];
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
  saturatedPrimitiveRouting = let {
    predicate = SApp (SApp (SPrimitive PEqInt) (SIntLit 1)) (SIntLit 1);
    program = SProgram [] (SApp (SApp (SApp (SPrimitive PIfThenElse) predicate) (SIntLit 7)) (SIntLit 9));
    form = mapEither (compose Constraint.form Constraint.skeleton)
  } in case (,) (form (Constraint.generateFileProgram program)) (form (Constraint.generateProgram program)) of {
    (,) (Right (FApplyPrimitive PIfThenElse [_]
      [PrimitiveUse (Typed _ (FApplyPrimitive PEqInt [] [_,_])) _,_,_])) (Right (FApply _ _ _ _)) -> True;
    _ -> False
  };
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
    else ioError (userError (textToChars ("shared frontend failure: " ++ name)));
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
  frontendTransparentLetChecks :: IO ();
  frontendTransparentLetChecks = do {
    let {
      declared = "let use : (forall a. a -> a) -> Bool = let marker = true in \\g -> let n = g 1 in g true in use (\\x -> x)";
      dummy = "class Dummy a where { dummy : a -> Bool }; "
    };
    recursiveAccepted "checked signature crosses transparent let" declared recursiveBool;
    recursiveAccepted "checked signature crosses transparent let with unused class"
      (dummy ++ declared) recursiveBool;
    recursiveAccepted "checked transparent let retains ordinary rhs generalization"
      "let use : (forall a. a -> a) -> Bool = let id = \\x -> x in let n = id 1 in \\g -> let b = id true in let m = g 1 in g true in use (\\x -> x)"
      recursiveBool;
    recursiveRejected "checked transparent let does not generalize captured environment"
      "\\y -> let use : (forall a. a -> a) -> Bool = let n : Int = y in \\g -> (y :: Bool) in use (\\x -> x)"
      "type constructor mismatch";
    recursiveRejected "checked transparent let preserves expected skolem"
      "let use : forall p. (forall a. a -> a) -> p = let marker = true in \\g -> true in use"
      "type constructor mismatch";
    recursiveRejected "checked transparent let preserves explicit lambda annotation"
      "let use : (forall a. a -> a) -> Bool = let marker = true in \\(g :: Int -> Int) -> g true in use"
      "type constructor mismatch";
    recursiveRejected "transparent let expression annotation remains a coercion"
      "let use = ((let marker = true in \\g -> let n = g 1 in g true) :: (forall a. a -> a) -> Bool) in use (\\x -> x)"
      "type constructor mismatch"
  };
  frontendRepairSignatureChecks :: IO ();
  frontendRepairSignatureChecks = do {
    frontendTransparentLetChecks;
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
    recursiveAccepted "scrutinee annotated polymorphic datatype argument"
      "data Box a = Box a; case (Box (\\x -> x) :: Box (forall a. a -> a)) of { Box f -> let n = f 1 in f true }"
      recursiveBool;
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
    frontendRepairParameterFieldChecks;
    frontendRepairSourceFieldChecks
  };
  frontendRepairParameterFieldChecks :: IO ();
  frontendRepairParameterFieldChecks = do {
    let {
      box = "data Box a = Box a; ";
      boxType = \field -> XCon "Box" ((:) field []);
      boxIdentity = boxType recursiveIdentity;
      boxToBool = XArrow boxIdentity recursiveBool;
      useIdentity = "case box of { Box f -> let n = f 1 in f true }";
      choice = "data Choice a = L a | R a; ";
      chosen = "case (L (\\x -> x) :: Choice (forall a. a -> a)) of { ";
      recursivePrefix = "let rec { loop x = loop x } in ";
      maybe = "data Maybe a = Nothing | Just a; ";
      list = "data List a = Nil | Cons a (List a); ";
      maybeBool = XCon "Maybe" ((:) recursiveBool []);
      listBool = XCon "List" ((:) recursiveBool []);
      parameter = XVar (XTyVar 0);
      argument = XVar (XTyVar 1);
      capturedResult = XForall (XTyVar 1) XBot (XArrow argument parameter);
      capturedOuter = box ++ "data Outer p = Outer (Box (forall b. b -> p)); ";
      capturedHigher = box ++ maybe ++ list ++
        "data Higher (f : * -> *) = Higher (Box (forall a. f a -> f a)); ";
      applied = XApply parameter argument;
      higherIdentity = XForall (XTyVar 0) (XBotKind (KArrow Star Star))
        (XForall (XTyVar 1) XBot (XArrow applied applied));
      appliedInt = XApply parameter recursiveInt;
      appliedBool = XApply parameter recursiveBool;
      capturedHigherIdentity = XForall (XTyVar 1) XBot (XArrow applied applied)
    };
    recursiveAccepted "known parameter field from annotated lambda"
      (box ++ "\\(box : Box (forall a. a -> a)) -> " ++ useIdentity) boxToBool;
    recursiveAccepted "known parameter field from directly checked signed lambda"
      (box ++ "let use : Box (forall a. a -> a) -> Bool = \\box -> " ++
       useIdentity ++ " in use") boxToBool;
    recursiveAccepted "checked signature reaches known parameter field through ordinary let"
      (box ++ "let use : Box (forall a. a -> a) -> Bool = let marker = true in \\box -> " ++
       useIdentity ++ " in use") boxToBool;
    recursiveAccepted "known parameter field passed first class"
      (box ++ "let use : (forall a. a -> a) -> Bool = \\g -> let n = g 1 in g true in " ++
       "\\(box : Box (forall a. a -> a)) -> case box of { Box f -> use f }") boxToBool;
    recursiveAccepted "known parameter fields share interface not instantiations"
      "data Pair a = Pair a a; \\(pair : Pair (forall a. a -> a)) -> case pair of { Pair f g -> let n = f 1 in let b = g true in let m = g 2 in f false }"
      (XArrow (XCon "Pair" ((:) recursiveIdentity [])) recursiveBool);
    recursiveAccepted "known parameter field nested constructor pattern"
      (box ++ "\\(outer : Box (Box (forall a. a -> a))) -> case outer of { Box (Box f) -> let n = f 1 in f true }")
      (XArrow (boxType boxIdentity) recursiveBool);
    recursiveAccepted "known parameter field nested case preserves local barrier"
      (box ++ "\\(outer : Box (Box (forall a. a -> a))) -> case outer of { Box inner -> case inner of { Box f -> let n = f 1 in f true } }")
      (XArrow (boxType boxIdentity) recursiveBool);
    recursiveAccepted "known parameter field term shadowing retains lexical scope"
      (box ++ "\\(box : Box (forall a. a -> a)) -> case box of { Box f -> let n = f 1 in let f = \\x -> 1 in f true }")
      (XArrow boxIdentity recursiveInt);
    recursiveAccepted "known parameter field preserves captured outer variable"
      (capturedOuter ++ "\\outer -> case outer of { Outer box -> case box of { Box f -> let n = f 1 in f true } }")
      (XForall (XTyVar 0) XBot
        (XArrow (XCon "Outer" ((:) parameter [])) parameter));
    recursiveRejected "known parameter field cannot generalize captured outer variable"
      (capturedOuter ++ "\\outer -> case outer of { Outer box -> case box of { Box f -> let n : Int = f 1 in (f true :: Bool) } }")
      "type constructor mismatch";
    recursiveAccepted "known parameter field preserves captured skolem identity"
      (box ++ "let use : forall p. Box (forall b. b -> p) -> p = \\box -> " ++
       useIdentity ++ " in use")
      (XForall (XTyVar 0) XBot (XArrow (boxType capturedResult) parameter));
    recursiveRejected "known parameter field cannot instantiate captured skolem"
      (box ++ "let use : forall p. Box (forall b. b -> p) -> Bool = \\box -> case box of { Box f -> let n : Int = f 1 in (f true :: Bool) } in use")
      "type constructor mismatch: Skolem";
    recursiveRejected "abstract parameter is not its polymorphic lower bound"
      (box ++ "let use : forall p. Box p -> Bool = \\box -> case box of { Box f -> let n = f 1 in f true } in use")
      "type constructor mismatch: Skolem";
    recursiveAccepted "known parameter field independently instantiates higher kinds"
      (box ++ maybe ++ list ++
       "\\(box : Box (forall (f : * -> *) a. f a -> f a)) -> case box of { Box k -> let n = k (Just 1) in k (Cons true Nil) }")
      (XArrow (boxType higherIdentity) listBool);
    recursiveAccepted "known parameter field preserves captured higher kind skolem"
      (box ++ "let use : forall (f : * -> *). Box (forall a. f a -> f a) -> f Int -> f Bool -> f Bool = " ++
       "\\box x y -> case box of { Box k -> let n = k x in k y } in use")
      (XForall (XTyVar 0) (XBotKind (KArrow Star Star))
        (XArrow (boxType capturedHigherIdentity)
          (XArrow appliedInt (XArrow appliedBool appliedBool))));
    recursiveAccepted "known parameter field preserves captured higher kind constructor"
      (capturedHigher ++ "\\outer -> case outer of { Higher box -> case box of { Box k -> let n = k (Just 1) in k (Just true) } }")
      (XArrow (XCon "Higher" ((:) (XCon "Maybe" []) [])) maybeBool);
    recursiveRejected "known parameter field cannot generalize captured higher kind"
      (capturedHigher ++ "\\outer -> case outer of { Higher box -> case box of { Box k -> let n = k (Just 1) in k (Cons true Nil) } }")
      "type constructor mismatch";
    recursiveAccepted "known parameter field exact rigid bottom"
      (box ++ "\\(box : Box (forall a. a)) -> case box of { Box f -> let n = addInt f 1 in if f then true else false }")
      (XArrow (boxType XBot) recursiveBool);
    recursiveRejected "unknown parameter field is not exact bottom"
      (box ++ "\\box -> case box of { Box f -> let n = addInt f 1 in if f then true else false }")
      "type constructor mismatch";
    recursiveAccepted "parameter field nested rank alone does not require projection"
      (box ++ "\\(box : Box ((forall a. a -> a) -> Bool)) -> case box of { Box f -> f (\\x -> x) }")
      (XArrow (boxType (XArrow recursiveIdentity recursiveBool)) recursiveBool);
    recursiveAccepted "unknown parameter field ordinary extraction"
      (box ++ "\\box -> case box of { Box value -> value }")
      (XForall (XTyVar 0) XBot (XArrow (boxType parameter) parameter));
    recursiveAccepted "unknown parameter field let alias preserves shared type"
      (box ++ "\\box -> case box of { Box value -> let alias = value in alias }")
      (XForall (XTyVar 0) XBot (XArrow (boxType parameter) parameter));
    recursiveAccepted "unknown parameter field single application"
      (box ++ "case Box (\\x -> x) of { Box f -> f 1 }") recursiveInt;
    recursiveRejected "unknown lambda parameter field remains monomorphic"
      (box ++ "\\box -> " ++ useIdentity) "type constructor mismatch";
    -- Projection is a one-shot local decision. Later application information
    -- must not reopen an unknown field at the earlier case barrier.
    recursiveRejected "later annotated argument cannot reopen parameter projection"
      (box ++ "(\\box -> " ++ useIdentity ++ ") (Box (\\x -> x) :: Box (forall a. a -> a))")
      "type constructor mismatch";
    -- Every alternative must be prepared before the first branch body can
    -- flush generation through an unsigned recursive group, even before use.
    recursiveAccepted "known parameter fields prepared before first branch recursive flush"
      (choice ++ chosen ++ "L f -> " ++ recursivePrefix ++
       "let n = f 1 in f true; R g -> let n = g 2 in g false }") recursiveBool;
    recursiveAccepted "known parameter fields prepared before reversed branch recursive flush"
      (choice ++ chosen ++ "R g -> " ++ recursivePrefix ++
       "let n = g 2 in g false; L f -> let n = f 1 in f true }") recursiveBool;
    recursiveAccepted "known parameter fields prepared before nested case recursive flush"
      (choice ++ "data Unit = Unit; " ++ chosen ++
       "L f -> case Unit of { Unit -> " ++ recursivePrefix ++
       "let n = f 1 in f true }; R g -> let n = g 2 in g false }") recursiveBool;
    recursiveAccepted "known parameter fields prepared before nested recursive group flush"
      (choice ++ chosen ++ "L f -> let rec { outer x = let rec { inner y = inner y } in outer x } in " ++
       "let n = f 1 in f true; R g -> let n = g 2 in g false }") recursiveBool;
    ioReturn ()
  };
  frontendCanonicalField :: String -> Field -> Field -> IO ();
  frontendCanonicalField label original expected = do {
    let { actual = Data.canonicalSourceField original };
    check label (eqString (Query.encodeField actual) (Query.encodeField expected));
    check (label ++ " idempotent")
      (eqString (Query.encodeField (Data.canonicalSourceField actual))
        (Query.encodeField actual))
  };
  frontendRepairSourceFieldPureChecks :: IO ();
  frontendRepairSourceFieldPureChecks = do {
    let {
      int = Applied "Int" [];
      bool = Applied "Bool" [];
      dead = Quantified "a" Star int;
      live = Quantified "a" Star (Parameter "a");
      identity = Quantified "a" Star (Function (Parameter "a") (Parameter "a"));
      higherKind = KArrow Star Star;
      declare = \name field -> DataDecl name []
        ((:) (ConstructorDecl name ((:) field [])) []);
      checked = declare "Checked" dead;
      local = declare "Local" (Function dead (Applied "Checked" []));
      normalized = declare "Local" (Function int (Applied "Checked" []));
      unbound = declare "Unbound" (Quantified "unused" Star (Parameter "missing"));
      unknown = declare "Unknown" (Quantified "unused" Star (Applied "Missing" []));
      illKinded = DataDeclK "IllKinded" ((:) ((,) "f" higherKind) [])
        ((:) (ConstructorDecl "IllKinded"
          ((:) (Quantified "unused" Star (Parameter "f")) [])) [])
    };
    frontendCanonicalField "source field drops nested binders inner to outer"
      (Quantified "a" Star (Quantified "b" Star int)) int;
    frontendCanonicalField "source field preserves live alias forall" live live;
    frontendCanonicalField "source field drops only shadowed outer binder"
      (Quantified "a" Star identity) identity;
    frontendCanonicalField "source field preserves outer occurrence beside shadow"
      (Quantified "a" Star (Function (Parameter "a") identity))
      (Quantified "a" Star (Function (Parameter "a") identity));
    frontendCanonicalField "source field retains captured datatype parameter"
      (Quantified "unused" Star (Parameter "p")) (Parameter "p");
    frontendCanonicalField "source field normalizes arrow domain and codomain"
      (Function dead (Quantified "b" Star bool)) (Function int bool);
    frontendCanonicalField "source field normalizes constructor arguments"
      (Applied "Pair" ((:) dead ((:) (Quantified "b" Star bool) [])))
      (Applied "Pair" ((:) int ((:) bool [])));
    frontendCanonicalField "source field normalizes application function and argument"
      (Application (Quantified "unused" Star (Parameter "f")) dead)
      (Application (Parameter "f") int);
    frontendCanonicalField "source field drops higher kind dead binder"
      (Quantified "f" higherKind dead) int;
    frontendCanonicalField "source field preserves higher kind live binder"
      (Quantified "f" higherKind (Application (Parameter "f") dead))
      (Quantified "f" higherKind (Application (Parameter "f") int));
    actual <- recursiveRight "source declarations validate against checked context"
      (Data.canonicalSourceDeclarations ((:) checked []) ((:) local []));
    check "source declarations return only normalized local layouts"
      (case actual of {
        (:) declaration [] -> eqString (Query.encodeDatatype declaration)
          (Query.encodeDatatype normalized);
        _ -> False
      });
    repeated <- recursiveRight "source declaration normalization repeats"
      (Data.canonicalSourceDeclarations ((:) checked []) actual);
    check "source declarations are idempotent"
      (eqString (Query.list Query.encodeDatatype repeated)
        (Query.list Query.encodeDatatype actual));
    empty <- recursiveRight "source declarations accept empty source batch"
      (Data.canonicalSourceDeclarations ((:) checked []) []);
    check "checked context is not returned as source" (null empty);
    -- Revalidate the combined contract and inspect the checked layout. The
    -- source operation must not rewrite the imported nominal field scheme.
    environment <- recursiveRight "normalized source and unchanged checked context validate"
      (Data.validateDeclarations (append ((:) checked []) actual));
    preserved <- recursiveRight "checked context layout remains available"
      (Data.lookupDatatype environment "Checked");
    check "checked context retains its vacuous quantified field"
      (case Data.datatypeConstructors preserved of {
        (:) (ConstructorDecl _ ((:) field [])) [] ->
          eqString (Query.encodeField field) (Query.encodeField dead);
        _ -> False
      });
    check "source normalization rejects original unbound field"
      (case Data.canonicalSourceDeclarations [] ((:) unbound []) of {
        Left message -> eqString message "unbound data type parameter: missing";
        Right _ -> False
      });
    check "source normalization rejects original ill kinded field"
      (case Data.canonicalSourceDeclarations [] ((:) illKinded []) of {
        Left message -> eqString message "constructor field must have kind *";
        Right _ -> False
      });
    check "source normalization rejects original unknown field constructor"
      (case Data.canonicalSourceDeclarations [] ((:) unknown []) of {
        Left message -> eqString message "unknown field type: Missing";
        Right _ -> False
      });
    check "source normalization validates checked context too"
      (case Data.canonicalSourceDeclarations ((:) unbound [])
          ((:) (declare "Valid" int) []) of {
        Left message -> eqString message "unbound data type parameter: missing";
        Right _ -> False
      });
    check "source normalization validates combined declaration identities"
      (case Data.canonicalSourceDeclarations ((:) checked []) ((:) checked []) of {
        Left message -> eqString message "duplicate data type";
        Right _ -> False
      })
  };
  frontendRepairSourceFieldChecks :: IO ();
  frontendRepairSourceFieldChecks = do {
    let {
      vacuous = "data V = V (forall a. Int); ";
      v = XCon "V" [];
      captured = XForall (XTyVar 0) XBot
        (XArrow (XVar (XTyVar 0)) (XCon "Captured" ((:) (XVar (XTyVar 0)) [])))
    };
    recursiveAccepted "vacuous forall constructor as value"
      (vacuous ++ "V") (XArrow recursiveInt v);
    recursiveAccepted "vacuous forall constructor application"
      (vacuous ++ "V 1") v;
    recursiveAccepted "vacuous forall constructor typed payload"
      (vacuous ++ "V (1 :: Int)") v;
    recursiveAccepted "vacuous forall constructor explicitly quantified payload"
      (vacuous ++ "V (1 :: forall a. Int)") v;
    recursiveAccepted "vacuous forall constructor signed local payload"
      (vacuous ++ "let n : forall a. Int = 1 in V n") v;
    recursiveAccepted "vacuous forall constructor let alias"
      (vacuous ++ "let make = V in make 1") v;
    recursiveAccepted "vacuous forall constructor partial application"
      "data Partial = Partial (forall a. Int) Bool; Partial 1"
      (XArrow recursiveBool (XCon "Partial" []));
    recursiveAccepted "vacuous forall nested in arrow domain"
      "data Domain = Domain ((forall a. Int) -> Bool); Domain (\\n -> eqInt n 1)"
      (XCon "Domain" []);
    recursiveAccepted "vacuous forall nested in arrow codomain"
      "data Codomain = Codomain (Int -> (forall a. Bool)); Codomain (\\n -> eqInt n 1)"
      (XCon "Codomain" []);
    recursiveAccepted "vacuous forall nested in constructor argument"
      "data Maybe a = Nothing | Just a; data Nested = Nested (Maybe (forall a. Int)); Nested (Just 1)"
      (XCon "Nested" []);
    recursiveAccepted "vacuous forall constructor captures datatype parameter"
      "data Captured p = Captured (forall a. p); \\x -> Captured x" captured;
    recursiveAccepted "vacuous forall constructor shadows datatype parameter"
      "data Shadow a = Shadow (forall a. Int); Shadow"
      (XForall (XTyVar 0) XBot
        (XArrow recursiveInt (XCon "Shadow" ((:) (XVar (XTyVar 0)) []))));
    recursiveAccepted "vacuous forall constructor retains live inner shadow"
      "data Shadow = Shadow (forall a. forall a. a -> a); Shadow"
      (XArrow recursiveIdentity (XCon "Shadow" []));
    recursiveAccepted "vacuous forall constructor drops higher kind dead binder"
      "data Higher = Higher (forall (f : * -> *) a. Int); Higher 1"
      (XCon "Higher" []);
    recursiveAccepted "vacuous forall constructor preserves live higher rank field"
      "data Mixed = Mixed (forall a b. a -> a); Mixed"
      (XArrow recursiveIdentity (XCon "Mixed" []));
    recursiveRejected "vacuous forall constructor rejects wrong payload"
      (vacuous ++ "V true") "type constructor mismatch";
    recursiveRejected "vacuous forall captured parameter is not generalized"
      "data Captured p = Captured (forall a. p); \\v -> case v of { Captured x -> let n : Int = x in (x :: Bool) }"
      "type constructor mismatch";
    recursiveRejected "source normalization rejects raw unbound field"
      "data Unbound = Unbound (forall a. missing); true"
      "unbound data type parameter: missing";
    recursiveRejected "source normalization rejects raw ill kinded field"
      "data IllKinded (f : * -> *) = IllKinded (forall a. f); true"
      "constructor field must have kind *";
    recursiveRejected "source normalization rejects raw unknown field constructor"
      "data Unknown = Unknown (forall a. Missing); true"
      "unknown field type: Missing";
    -- A live alias forall is not empty. Its graph/target agreement limitation
    -- remains unresolved and must not be hidden by dropping the binder.
    check "live alias forall constructor remains explicit residual"
      (case C.compile "FrontendRepair.emlf" "data Abs = Abs (forall a. a); Abs" of {
        Left error -> (case C.phase error of { Verification -> True; _ -> False }) &&
          eqString "elaboration changed the inferred type" (C.diagnostic error);
        Right _ -> False
      });
    frontendRepairSourceFieldPureChecks
  };
  frontendCanonicalClassType :: String -> SType -> SType -> IO ();
  frontendCanonicalClassType label original expected = do {
    let { actual = Classes.canonicalSourceType original };
    check label (eqString (Query.encodeType actual) (Query.encodeType expected));
    check (label ++ " idempotent")
      (eqString (Query.encodeType (Classes.canonicalSourceType actual))
        (Query.encodeType actual))
  };
  frontendEqualClass :: SClassDecl -> SClassDecl -> Bool;
  frontendEqualClass (SClassDecl name parameters supers methods)
                     (SClassDecl other otherParameters otherSupers otherMethods) =
    eqString name other &&
    eqList (\((,) a k) ((,) b l) -> eqString a b && eqKind k l)
      parameters otherParameters &&
    eqString (Query.list Query.encodePredicate supers)
      (Query.list Query.encodePredicate otherSupers) &&
    eqList (\((,) a ty) ((,) b otherType) -> eqString a b &&
      eqString (Query.encodeType ty) (Query.encodeType otherType)) methods otherMethods;
  frontendRepairSourceClassTypeChecks :: IO ();
  frontendRepairSourceClassTypeChecks = do {
    let {
      int = SCon "Int" [];
      bool = SCon "Bool" [];
      dead = SForall Flexible "unused" SBottom int;
      live = SForall Flexible "a" SBottom (STVar "a");
      identity = SForall Flexible "a" SBottom (SArrow (STVar "a") (STVar "a"));
      higherKind = KArrow Star Star;
      predicate = \ty -> SQualified ((:) (SPredicate "Parent" ((:) ty [])) []) int;
      dependent = SForall Flexible "a" SBottom
        (SForall Flexible "b" (STVar "a") (SArrow (STVar "b") (STVar "b")));
      ownBound = SForall Flexible "a" SBottom
        (SForall Flexible "a" (STVar "a") int)
    };
    frontendCanonicalClassType "source class type drops nested dead binders"
      (SForall Flexible "a" SBottom (SForall Flexible "b" SBottom int)) int;
    frontendCanonicalClassType "source class type preserves live alias forall" live live;
    frontendCanonicalClassType "source class type drops only shadowed outer binder"
      (SForall Flexible "a" SBottom identity) identity;
    frontendCanonicalClassType "source class type keeps outer occurrence beside shadow"
      (SForall Flexible "a" SBottom (SArrow (STVar "a") identity))
      (SForall Flexible "a" SBottom (SArrow (STVar "a") identity));
    frontendCanonicalClassType "source class type keeps predicate-only variable"
      (SForall Flexible "a" SBottom (predicate (STVar "a")))
      (SForall Flexible "a" SBottom (predicate (STVar "a")));
    frontendCanonicalClassType "source class type normalizes predicate arguments"
      (SForall Flexible "a" SBottom
        (predicate (SForall Flexible "unused" SBottom (STVar "a"))))
      (SForall Flexible "a" SBottom (predicate (STVar "a")));
    frontendCanonicalClassType "source class type drops predicate shadow outer binder"
      (SForall Flexible "a" SBottom (predicate identity)) (predicate identity);
    frontendCanonicalClassType "source class type retains later bound dependency"
      dependent dependent;
    frontendCanonicalClassType "source class binder does not scope its own bound"
      ownBound ownBound;
    frontendCanonicalClassType "source class type normalizes retained quantifier bound"
      (SForall Flexible "a" dead (STVar "a"))
      (SForall Flexible "a" int (STVar "a"));
    frontendCanonicalClassType "source class type never erases bounded syntax"
      (SForall Flexible "unused" int bool) (SForall Flexible "unused" int bool);
    frontendCanonicalClassType "source class type never erases rigid syntax"
      (SForall Rigid "unused" SBottom int) (SForall Rigid "unused" SBottom int);
    frontendCanonicalClassType "source class type normalizes arrow domain and codomain"
      (SArrow dead (SForall Flexible "unused" SBottom bool)) (SArrow int bool);
    frontendCanonicalClassType "source class type normalizes constructor arguments"
      (SCon "Pair" ((:) dead ((:) (SForall Flexible "unused" SBottom bool) [])))
      (SCon "Pair" ((:) int ((:) bool [])));
    frontendCanonicalClassType "source class type normalizes both application branches"
      (STypeApp (SForall Flexible "unused" SBottom (STVar "f")) dead)
      (STypeApp (STVar "f") int);
    frontendCanonicalClassType "source class type drops higher kind dead binder"
      (SForall Flexible "f" (SBottomKind higherKind) dead) int;
    frontendCanonicalClassType "source class type retains higher kind live binder"
      (SForall Flexible "f" (SBottomKind higherKind) (STypeApp (STVar "f") dead))
      (SForall Flexible "f" (SBottomKind higherKind) (STypeApp (STVar "f") int))
  };
  frontendRepairSourceClassHeaderChecks :: IO ();
  frontendRepairSourceClassHeaderChecks = do {
    let {
      int = SCon "Int" [];
      a = STVar "a";
      parameters = (:) ((,) "a" Star) [];
      rawMethod = SForall Flexible "unused" SBottom (SArrow a int);
      checked = SClassDecl "Checked" parameters [] ((:) ((,) "checkedMethod" rawMethod) []);
      local = SClassDecl "Local" parameters
        ((:) (SPredicate "Checked" ((:) (SForall Flexible "unused" SBottom a) [])) [])
        ((:) ((,) "localMethod" (SArrow a (SForall Flexible "unused" SBottom int))) []);
      normalized = SClassDecl "Local" parameters
        ((:) (SPredicate "Checked" ((:) a [])) [])
        ((:) ((,) "localMethod" (SArrow a int)) []);
      importedNames = Set.singleton "Checked";
      checkedInfo = Classes.Info checked "Dict_Checked" "Make_Checked" [] [];
      declared = \name method ty -> SClassDecl name parameters [] ((:) ((,) method ty) []);
      importedDuplicate = declared "Imported" "sharedMethod" rawMethod;
      sourceDuplicate = declared "Source" "sharedMethod" rawMethod;
      secondDuplicate = declared "Second" "sharedMethod" rawMethod;
      implicit = declared "Implicit" "implicitMethod"
        (SForall Flexible "unused" SBottom (SArrow a (SArrow (STVar "b") (STVar "b"))));
      implicitExpected = declared "Implicit" "implicitMethod"
        (SArrow a (SArrow (STVar "b") (STVar "b")))
    };
    check "source class maps method and superclass types without changing identities"
      (frontendEqualClass (Classes.canonicalSourceClass local) normalized);
    actual <- recursiveRight "source class headers validate checked context"
      (Classes.canonicalSourceClasses importedNames [] ((:) checked []) ((:) local []));
    check "source class headers return only normalized local headers"
      (eqList frontendEqualClass actual ((:) normalized []));
    repeated <- recursiveRight "source class headers normalize repeatedly"
      (Classes.canonicalSourceClasses importedNames [] ((:) checked []) actual);
    check "source class header normalization is idempotent"
      (eqList frontendEqualClass repeated actual);
    empty <- recursiveRight "source class headers accept empty source batch"
      (Classes.canonicalSourceClasses importedNames [] ((:) checked []) []);
    check "checked class headers are not returned as source" (null empty);
    let { infos = M.fromList compareString
      ((:) ((,) "Checked" checkedInfo)
        ((:) ((,) "Local" (Classes.Info normalized "Dict_Local" "Make_Local" [] [])) [])) };
    checkedDictionary <- recursiveRight "checked class dictionary remains reconstructible"
      (Classes.dictionaryDecl infos checkedInfo);
    check "checked class dictionary preserves its raw quantified method layout"
      (case Data.datatypeConstructors checkedDictionary of {
        (:) (ConstructorDecl _ ((:) field [])) [] ->
          eqString (Query.encodeField field)
            (Query.encodeField (Quantified "unused" Star
              (Function (Parameter "a") (Applied "Int" []))));
        _ -> False
      });
    original <- recursiveRight "source headers retain implicit quantification provenance"
      (Classes.canonicalSourceClasses Set.empty [] [] ((:) implicit []));
    check "source headers return original syntax not inserted implicit quantifiers"
      (eqList frontendEqualClass original ((:) implicitExpected []));
    grouped <- recursiveRight "source class method names preserve imported namespace grouping"
      (Classes.canonicalSourceClasses (Set.singleton "Imported") []
        ((:) importedDuplicate []) ((:) sourceDuplicate []));
    check "source class duplicate grouping still normalizes own header"
      (eqList frontendEqualClass grouped
        ((:) (declared "Source" "sharedMethod" (SArrow a int)) []));
    check "source class same namespace duplicate methods remain invalid"
      (case Classes.canonicalSourceClasses Set.empty []
          ((:) importedDuplicate []) ((:) sourceDuplicate []) of {
        Left message -> eqString message "duplicate class method";
        Right _ -> False
      });
    check "source class imported grouping never masks duplicate own methods"
      (case Classes.canonicalSourceClasses (Set.singleton "Imported") []
          ((:) importedDuplicate []) ((:) sourceDuplicate ((:) secondDuplicate [])) of {
        Left message -> eqString message "duplicate class method";
        Right _ -> False
      });
    -- This wrapper owns every source header. Its imported-name set separates
    -- method namespaces; unlike checkedHeaders, it is not artifact provenance.
    program <- recursiveRight "source class program normalizes all fresh headers"
      (Classes.canonicalSourceProgram importedNames
        (SClassProgram [] ((:) checked ((:) local [])) [] (SIntLit 1)));
    check "source class program does not mistake imported names for checked headers"
      (case program of {
        SClassProgram [] headers [] (SIntLit 1) ->
          eqList frontendEqualClass headers
            ((:) (declared "Checked" "checkedMethod" (SArrow a int)) ((:) normalized []));
        _ -> False
      });
    check "source class normalization validates raw checked header context"
      (case Classes.canonicalSourceClasses importedNames []
          ((:) (declared "Checked" "checkedMethod"
            (SForall Flexible "unused" int (SArrow a int))) []) ((:) local []) of {
        Left message -> eqString message
          "class methods require ordinary forall signatures without bounded or nested class constraints";
        Right _ -> False
      })
  };
  frontendRepairSourceClassChecks :: IO ();
  frontendRepairSourceClassChecks = do {
    let {
      instanceInt = "instance Ignore Int where { ignore = \\x -> x }; ignore 1";
      parent = "class Parent a where { parent : a -> Int }; ";
      boundedDiagnostic =
        "class methods require ordinary forall signatures without bounded or nested class constraints"
    };
    recursiveAccepted "ordinary class method normalization control"
      ("class Ignore a where { ignore : a -> Int }; " ++ instanceInt) recursiveInt;
    recursiveAccepted "source class drops leading dead method forall"
      ("class Ignore a where { ignore : forall b. a -> Int }; " ++ instanceInt) recursiveInt;
    recursiveAccepted "source class drops dead method result forall"
      ("class Ignore a where { ignore : a -> (forall b. Int) }; " ++ instanceInt) recursiveInt;
    recursiveAccepted "source class drops dead method argument forall"
      ("class Ignore a where { ignore : a -> (forall b. Int) -> Int }; " ++
       "instance Ignore Int where { ignore = \\x n -> n }; ignore 0 1") recursiveInt;
    recursiveAccepted "source class drops dead forall inside nominal method result"
      ("data Maybe a = Nothing | Just a; " ++
       "class Build a where { build : a -> Maybe (forall b. Int) }; " ++
       "instance Build Int where { build x = Just x }; build 1")
      (XCon "Maybe" ((:) recursiveInt []));
    recursiveAccepted "source class drops higher kind dead method forall"
      ("class Ignore a where { ignore : forall (f : * -> *) b. a -> Int }; " ++ instanceInt)
      recursiveInt;
    recursiveAccepted "source class retains captured higher kind parameter"
      ("data Box a = Box a; " ++
       "class IgnoreF (f : * -> *) where { ignoreF : forall b. f Int -> Int }; " ++
       "instance IgnoreF Box where { ignoreF = \\x -> 1 }; ignoreF (Box 0)") recursiveInt;
    recursiveAccepted "source class retains live method forall beside dead binder"
      ("class Keep a where { keep : forall b c. a -> b -> b }; " ++
       "instance Keep Int where { keep = \\x y -> y }; keep 0 true") recursiveBool;
    recursiveAccepted "source class normalizes superclass argument and preserves given projection"
      (parent ++ "class Parent (forall b. a) => Child a where { child : a -> Int }; " ++
       "instance Parent Int where { parent = \\x -> x }; " ++
       "instance Child Int where { child = \\x -> x }; " ++
       "let use : forall a. Child a => a -> Int = \\x -> parent x in use (child 1)") recursiveInt;
    recursiveRejected "source class rejects raw dead bounded method forall"
      "class Invalid a where { invalid : forall (b >= Int). a -> Int }; true"
      boundedDiagnostic;
    recursiveRejected "source class rejects raw dead rigid method forall"
      "class Invalid a where { invalid : forall (b = Int). a -> Int }; true"
      boundedDiagnostic;
    recursiveRejected "source class rejects raw higher kind method result"
      "class Invalid (f : * -> *) where { invalid : forall b. f }; true"
      "term annotation must have kind *";
    recursiveRejected "source class rejects raw dead bounded superclass forall"
      (parent ++ "class Parent (forall (b >= Int). a) => Invalid a where { invalid : a -> Int }; true")
      boundedDiagnostic;
    recursiveRejected "source class rejects free variable in dead superclass bound"
      (parent ++ "class Parent (forall (b >= missing). a) => Invalid a where { invalid : a -> Int }; true")
      "unbound annotation type variable: missing";
    recursiveRejected "source class rejects kind error in dead superclass bound"
      (parent ++ "class Parent (forall (b >= Int Bool). a) => Invalid a where { invalid : a -> Int }; true")
      "invalid type constructor arity: a type of kind * cannot be applied";
    recursiveRejected "source class captured parameter cannot become another result type"
      ("class Keep a where { keep : forall b. a -> a }; " ++
       "instance Keep Int where { keep = \\x -> true }; keep 1")
      "type constructor mismatch";
    -- Qualified predicate liveness above is a pure normalization contract,
    -- not support for ordinary constrained methods in the source language.
    recursiveRejected "source class ordinary constrained methods remain unsupported"
      (parent ++ "class Invalid a where { invalid : forall b. Parent b => a -> Int }; true")
      "only managed HasCallStack constraints are supported in class methods";
    frontendRepairSourceClassTypeChecks;
    frontendRepairSourceClassHeaderChecks
  };
  frontendRepairChecks :: IO ();
  frontendRepairChecks = do {
    frontendRepairSignatureChecks;
    frontendRepairFieldChecks;
    frontendRepairSourceClassChecks;
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
  -- Compare maintained parser trees, using explicit braces as the layout
  -- oracle. Only call-site positions are erased for these value-only cases;
  -- signatures, binding order, shadowing and recursive groups stay exact.
  layoutValueModule (SourceModule file name exports imports ds cs instances values body syntax) =
    SourceModule file name exports imports ds cs instances
      (map (\((,,) n a e) -> (,,) n a (Classes.eraseCallSites e)) values)
      body syntax;
  sameLayout left right = case (,) (parse left) (parse right) of {
    (,) (Right a) (Right b) -> SourceEquality.eqSourceModule (layoutValueModule a) (layoutValueModule b);
    _ -> False
  };
  formatterChecks :: IO ();
  formatterChecks = do {
      check "inline shared let" (accept "main = let x = 1 in x");
      check "inline shared let forward scope" (sameLayout "main = let x = y; y = 3 in x" "main = let { x = y; y = 3 } in x");
      check "multiline shared let forward scope"
        (sameLayout "main =\n  let x = y\n      y = 3\n   in x" "main = let { x = y; y = 3 } in x");
      check "inline nested let shadowing"
        (sameLayout "main = let x = 1 in let x = 2; y = x in y" "main = let { x = 1 } in let { x = 2; y = x } in y");
      check "implicit inline do" (accept "main = do ioReturn 1");
      check "implicit inline case" (sameLayout "main = case True of True -> 1; False -> 2" "main = case True of { True -> 1; False -> 2 }");
      check "inline case before next declaration"
        (sameLayout "f b = case b of True -> 1; False -> 2\nmain = f False" "f b = case b of { True -> 1; False -> 2 }\nmain = f False");
      check "case scrutinee closes implicit nested case"
        (sameLayout "main = case case True of True -> False; False -> True of True -> 1; False -> 2" "main = case case True of { True -> False; False -> True } of { True -> 1; False -> 2 }");
      check "case scrutinee closes implicit do"
        (accept "main = case do ioReturn 1 of value -> value");
      check "inline case closes at parenthesis"
        (sameLayout "f a b = a + b\nmain = f (case True of True -> 1; False -> 2) 3" "f a b = a + b\nmain = f (case True of { True -> 1; False -> 2 }) 3");
      check "inline case closes at collection comma"
        (sameLayout "main = [case True of True -> 1; False -> 2, 3]" "main = [case True of { True -> 1; False -> 2 }, 3]");
      check "inline do closes at else"
        (accept "main = if True then do ioReturn 1; ioReturn 2 else do ioReturn 3; ioReturn 4");
      check "inline do explicit let group"
        (accept "main = do let { x = y; y = 3 }; ioReturn x");
      check "multiline do implicit let group"
        (accept "main = do\n  let x = y\n      y = 3\n  ioReturn x");
      check "formatter split prologue and relocated marker"
        (isRight (P.parseModule "Example.hs"
          ("{-# LANGUAGE FlexibleContexts #-}\n{-# LANGUAGE FlexibleInstances #-}\n{-# LANGUAGE KindSignatures #-}\n{-# LANGUAGE MultiParamTypeClasses #-}\n{-# LANGUAGE OverloadedStrings #-}\n{-# LANGUAGE RankNTypes #-}\n-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude #-}\n{-# LANGUAGE NoMonomorphismRestriction #-}\nmodule Example where\nmain = 1\n")));
      check "same-indent of after do rejected"
        (reject "main = case do ioReturn 1; ioReturn 2\nof x -> x");
      check "same-indent of after case rejected"
        (reject "main = case case True of True -> 1; False -> 2\nof x -> x");
      check "same-indent in after case rejected"
        (reject "main = let x = case True of True -> 1; False -> 2\nin x");
      check "formatter retains legacy sequential scope" legacyScope;
      check "formatter same-indent RHS rejected" (reject "main =\n1");
      check "formatter same-indent operator rejected" (reject "main = 1 +\n2");
      check "formatter retains explicit boundary rejection" (reject "main = do { ioReturn 1; do\n  ioReturn 2 }")
  };
  -- Compare the new partial checker with the retained general solver, then
  -- ask the frozen target checker independently. Binder IDs may differ, so
  -- erasure equality follows lexical binding rather than printed hints.
  -- The general elaborator emits identity coercions and aliases. Compare
  -- erasures modulo only those two administrative laws, not arbitrary beta
  -- reduction or an optimizer supplied by the candidate.
  monomorphicAdministrative names term = case term of {
    XEVar name -> XEVar (M.findWithDefault X.compareName name name names);
    XEAbs name body -> XEAbs name (monomorphicAdministrative (M.delete X.compareName name names) body);
    XEApp function argument -> let { f = monomorphicAdministrative names function;
      a = monomorphicAdministrative names argument } in case f of {
        XEAbs x (XEVar y) -> if X.equalName x y then a else XEApp f a;
        _ -> XEApp f a
      };
    XELet name rhs body -> case monomorphicAdministrative names rhs of {
      XEVar original -> monomorphicAdministrative (M.insert X.compareName name original names) body;
      value -> XELet name value (monomorphicAdministrative (M.delete X.compareName name names) body)
    };
    XELetRec bindings body -> let {
      scope = foldl (\env binding -> M.delete X.compareName (fst binding) env) names bindings
    } in XELetRec (map (\((,) name rhs) -> (,) name (monomorphicAdministrative scope rhs)) bindings)
      (monomorphicAdministrative scope body);
    XECase subject alternatives -> XECase (monomorphicAdministrative names subject)
      (map (\(XErasedAlternative pattern body) -> let {
        scope = foldl (\env name -> M.delete X.compareName name env) names (X.patternNames pattern)
      } in XErasedAlternative pattern (monomorphicAdministrative scope body)) alternatives);
    _ -> term
  };
  monomorphicErasure names left right = case (,) left right of {
    (,) (XEVar a) (XEVar b) -> case M.lookup X.compareName a names of {
      Just actual -> X.equalName actual b; Nothing -> False
    };
    (,) (XEAbs a body) (XEAbs b other) ->
      monomorphicErasure (M.insert X.compareName a b names) body other;
    (,) (XEApp f a) (XEApp g b) -> monomorphicErasure names f g && monomorphicErasure names a b;
    (,) (XELet a value body) (XELet b other rest) -> monomorphicErasure names value other &&
      monomorphicErasure (M.insert X.compareName a b names) body rest;
    (,) (XELetRec xs body) (XELetRec ys rest) ->
      length xs == length ys && let {
        scope = foldl (\env ((,) a b) -> M.insert X.compareName (fst a) (fst b) env) names (zip xs ys)
      } in all (\((,) a b) -> monomorphicErasure scope (snd a) (snd b)) (zip xs ys) &&
        monomorphicErasure scope body rest;
    (,) (XECase subject alternatives) (XECase other branches) ->
      monomorphicErasure names subject other &&
      eqList (\(XErasedAlternative pattern body) (XErasedAlternative target result) ->
        case erasurePatternScope names pattern target of {
          Just scope -> monomorphicErasure scope body result;
          Nothing -> False
        }) alternatives branches;
    _ -> X.equalErased left right
  };
  erasurePatternScope names left right = let {
    binder env pair = case pair of {
      (,) Nothing Nothing -> Just env;
      (,) (Just a) (Just b) -> Just (M.insert X.compareName a b env);
      _ -> Nothing
    };
    fields env a b = case (,) a b of {
      (,) [] [] -> Just env;
      (,) ((:) x xs) ((:) y ys) -> case binder env ((,) x y) of {
        Just scope -> fields scope xs ys;
        Nothing -> Nothing
      };
      _ -> Nothing
    }
  } in case (,) left right of {
    (,) (XConstructorPattern a xs) (XConstructorPattern b ys) ->
      if eqString a b then fields names xs ys else Nothing;
    (,) (XDefaultPattern a) (XDefaultPattern b) -> binder names ((,) a b);
    _ -> Nothing
  };
  monomorphicGroupCase = inferenceGroupCase Inference.monomorphicIndexed;
  groundGroupCase = inferenceGroupCase Inference.groundIndexed;
  inferenceGroupCase route label expectedFast parameters members =
    inferenceGroupCaseWithData route label expectedFast [] parameters members;
  inferenceGroupCaseWithData route label expectedFast datatypes parameters members = do {
    prepared <- recursiveRight label (Inference.prepareIndexedGroup parameters datatypes members);
    let { candidate = route parameters members (snd prepared) };
    check (label ++ " route") (isRight candidate == expectedFast);
    ordinary <- recursiveRight (label ++ " ordinary")
      (Inference.finishOpenGroup (fst prepared) (map snd members) (snd prepared));
    actual <- recursiveRight (label ++ " indexed")
      (Inference.compileOpenGroupIndexed "control" parameters datatypes members);
    let { a = Open.closedTerm actual; b = Open.closedTerm ordinary };
    check (label ++ " erasure") (monomorphicErasure M.empty (monomorphicAdministrative M.empty (X.erase a))
      (monomorphicAdministrative M.empty (X.erase b)));
    check (label ++ " exported type")
      (eqList (\((,) n ty) ((,) m other) -> eqString (X.nameHint n) (X.nameHint m) && XT.alphaEq ty other)
        (Open.bindings actual) (Open.bindings ordinary));
    actualType <- recursiveRight (label ++ " frozen target") (Independent.checkClosed a);
    ordinaryType <- recursiveRight (label ++ " ordinary frozen target") (Independent.checkClosed b);
    check (label ++ " independent type") (XT.alphaEq actualType ordinaryType)
  };
  templateGroupChecks = do {
    let { a = XTyVar 100; ty = XForall a XBot
          (XArrow (XArrow (XVar a) (XVar a)) (XArrow (XVar a) (XVar a)));
      parameters = \identity name scheme -> [(,,) (Index.fromInt identity) name scheme];
      member = \foreignId owner stepId argId name -> [(,) (Index.fromInt owner) ((,,) name Nothing
        (SDeclScope [Index.fromInt stepId] (SLam "step" Nothing
          (SDeclScope [Index.fromInt argId] (SLam "value" Nothing
            (SApp (SGlobal (Index.fromInt stepId) "step")
              (SApp (SApp (SGlobal (Index.fromInt foreignId) "wrong hint")
                (SGlobal (Index.fromInt stepId) "step")) (SGlobal (Index.fromInt argId) "value"))))))))];
      ps = parameters 3 "previous" ty;
      first = member 3 10 11 12 "first";
      second = member 23 30 31 32 "second" };
    installed <- recursiveRight "template initial inference"
      (CrateGraph.compileIndexedMemo "context" M.empty "first" ps [] first);
    check "checked polymorphic template is retained" (M.size (snd installed) == 1);
    repeated <- recursiveRight "template renamed inference"
      (CrateGraph.compileIndexedMemo "context" (snd installed) "second"
        (parameters 23 "otherPrevious" ty) [] second);
    check "alpha-equivalent dependency and owner use one template" (M.size (snd repeated) == 1);
    inferenceGroupCase (\inputs members _ -> mapEither fst
        (CrateGraph.compileIndexedMemo "context" (snd installed) "second" inputs [] members))
      "reused polymorphic template" True (parameters 23 "otherPrevious" ty) second;
    key <- recursiveRight "template source key" (CrateGraph.inferenceTemplateKey "context" ps first);
    let { b = XTyVar 200;
      alpha = XForall b XBot (XArrow (XArrow (XVar b) (XVar b)) (XArrow (XVar b) (XVar b)));
      bounded = XForall a (XCon "Int" [])
        (XArrow (XArrow (XVar a) (XVar a)) (XArrow (XVar a) (XVar a)));
      application = XForall a XBot (XForall b XBot
        (XArrow (XArrow (XVar a) (XVar b)) (XArrow (XVar a) (XVar b))));
      different label context inputs members = do {
        other <- recursiveRight label (CrateGraph.inferenceTemplateKey context inputs members);
        check label (not (eqString key other))
      } };
    renamedKey <- recursiveRight "template alpha-renamed key"
      (CrateGraph.inferenceTemplateKey "context" (parameters 23 "otherPrevious" alpha) second);
    check "template alpha-renaming preserves the key" (eqString key renamedKey);
    different "template includes datatype context" "other-context" ps first;
    different "template includes quantified bounds" "context" (parameters 3 "previous" bounded) first;
    check "unsupported bounded dependency is not accepted through an older template"
      (isLeft (Inference.compileOpenGroupIndexed "bounded" (parameters 3 "previous" bounded) [] first) &&
       isLeft (CrateGraph.compileIndexedMemo "context" (snd installed) "bounded"
         (parameters 3 "previous" bounded) [] first));
    inferenceGroupCase (\inputs members _ -> mapEither fst
        (CrateGraph.compileIndexedMemo "context" (snd installed) "application" inputs [] members))
      "changed dependency scheme is inferred again" True (parameters 3 "previous" application) first;
    let { two = append ps (parameters 4 "spare" ty) };
    leftKey <- recursiveRight "first dependency position" (CrateGraph.inferenceTemplateKey "context" two first);
    rightKey <- recursiveRight "second dependency position"
      (CrateGraph.inferenceTemplateKey "context" two (member 4 10 11 12 "first"));
    check "template distinguishes equally typed dependencies" (not (eqString leftKey rightKey));
    check "template rejects unresolved identities"
      (isLeft (CrateGraph.inferenceTemplateKey "context" ps (member 99 10 11 12 "first")));
    check "template rejects binder identity capture"
      (isLeft (CrateGraph.inferenceTemplateKey "context" ps (member 3 10 3 12 "first")));
    check "template rejects recursive ownership"
      (isLeft (CrateGraph.inferenceTemplateKey "context" ps (member 10 10 11 12 "first")));
    let { full = M.fromList compareString (map (\i -> (,) (showInt i) (fst installed)) (range 1 64)) };
    limited <- recursiveRight "bounded template inventory"
      (CrateGraph.compileIndexedMemo "context" full "second" (parameters 23 "otherPrevious" ty) [] second);
    check "template inventory stays bounded" (M.size (snd limited) == 64)
  };
  checkedGroundUses = do {
    let { a = XTyVar 41; x = XName 10 "poly"; t = XVar a;
      use target = XTypeApp (XVarTerm x) (XThen (XInner (XBottom target)) XElim);
      scope signature = XEnv M.empty (M.singleton x signature);
      same = XForall a XBot (XArrow t t); alwaysBool = XForall a XBot (XArrow t recursiveBool);
      repeated = XApp (use recursiveInt) (XApp (use recursiveInt) (XIntTerm 7));
      compare label signature term expected = do {
        recursiveCheckedType label expected (Check.inferIn Data.emptyDataEnv (scope signature) term);
        recursiveCheckedType (label ++ " independent") expected (Independent.inferIn Data.emptyDataEnv (scope signature) term)
      }
    };
    compare "repeated ground instantiation" same repeated recursiveInt;
    compare "same binder identity with a different scheme" alwaysBool (use recursiveInt) (XArrow recursiveInt recursiveBool);
    compare "same binder with another type argument" same (use recursiveBool) (XArrow recursiveBool recursiveBool);
    let { b = XTyVar 42; outer = XForall a XBot; inner = XForall b XBot };
    compare "ground substitution through a dependent inner bound"
      (outer (inner (XForall a t (XArrow t (XVar b))))) (use recursiveInt)
      (inner (XForall a recursiveInt (XArrow t (XVar b))));
    compare "a shadowing bottom binder retains its occurrences"
      (outer (inner (outer (XArrow t (XVar b))))) (use recursiveInt)
      (inner (outer (XArrow t (XVar b))));
    let { raw = XApply (XCon "Wrap" []) recursiveInt;
      ds = Data.withKinds [(,) "Wrap" (KArrow Star Star)] };
    check "an unused quantifier preserves the original application in its body"
      (case Check.checkComputationIn ds M.empty XElim (XForall a recursiveInt (inner raw)) of {
        Right (XForall _ XBot (XApply (XCon name []) _)) -> eqString name "Wrap"; _ -> False
      });
    let { open = XEnv (M.singleton b XBot) (M.singleton x (outer (inner (XArrow t (XVar b)))));
      expected = XForall a XBot (XArrow (XVar b) t) };
    recursiveCheckedType "open type argument avoids capture" expected
      (Check.inferIn Data.emptyDataEnv open (use (XVar b)));
    check "ground instantiation on a monomorphic variable still fails"
      (case Check.inferIn Data.emptyDataEnv (scope recursiveInt) (use recursiveInt) of {
        Left reason -> eqString reason "Inst-Inner requires a forall source"; Right _ -> False
      })
  };
  groundGroupChecks = do {
    checkedGroundUses;
    groundAliasChecks;
    groundRecursiveChecks;
    groundRecursiveSourceRoutes;
    groundCaseEvidenceCheck;
    let { a = XTyVar 100; b = XTyVar 101; c = XTyVar 102;
      xa = XVar a; xb = XVar b; xc = XVar c;
      int = SCon "Int" []; arrow = SArrow int int;
      identity = XForall a XBot (XArrow xa xa);
      constant = XForall a XBot (XForall b (XForall c XBot (XArrow xc xa)) (XArrow xa xb));
      apply = XForall a XBot (XForall b XBot (XArrow (XArrow xa xb) (XArrow xa xb)));
      composeTy = XForall a XBot (XForall b XBot
        (XForall c (XForall (XTyVar 103) XBot
          (XArrow (XArrow (XVar (XTyVar 103)) xa) (XArrow (XVar (XTyVar 103)) xb)))
          (XArrow (XArrow xa xb) xc)));
      parameter = \ty -> [(,,) (Index.fromInt 3) "poly" ty];
      use = SGlobal (Index.fromInt 3) "wrong-hint";
      localIdentity = SLam "v" Nothing (SVar "v");
      row = \ty body -> [(,) (Index.fromInt 10) ((,,) "function" (Just (SAnnotation [] ty)) body)];
      conditional = \p yes no -> SApp (SApp (SApp (SPrimitive PIfThenElse) p) yes) no };
    let { ps = parameter identity; typed = row arrow (SLam "x" Nothing (SApp use (SVar "x"))) };
    direct <- recursiveRight "direct unary import" (Inference.signedApplicationGroup ps [] typed);
    elaborated <- recursiveRight "elaborated unary import" (Inference.compileElaboratedGroup ps [] typed);
    check "direct unary import preserves the checked term"
      (eqString (Open.fingerprint direct) (Open.fingerprint elaborated));
    recursiveRight "frozen unary import" (Independent.checkClosed (Open.closedTerm direct));
    check "bounded import requires full elaboration"
      (isLeft (Inference.signedApplicationGroup (parameter constant) [] typed));
    groundGroupCase "ground imported identity" True (parameter identity)
      (row arrow (SLam "x" Nothing (SApp use (SVar "x"))));
    groundGroupCase "ground independent Bool and Int instantiations" True (parameter identity)
      (row int (conditional (SApp use (SBoolLit True)) (SApp use (SIntLit 7)) (SApp use (SIntLit 8))));
    groundGroupCase "ground bounded constant scheme" True (parameter constant)
      (row int (SApp (SApp use (SIntLit 7)) (SBoolLit True)));
    groundGroupCase "ground function application" True (parameter apply)
      (row int (SApp (SApp use localIdentity) (SIntLit 7)));
    groundGroupCase "ground bounded composition scheme" True (parameter composeTy)
      (row int (SApp (SApp (SApp use localIdentity) localIdentity) (SIntLit 7)));
    groundGroupCase "ground resolved local identity" True (parameter identity)
      (row arrow (SDeclScope [Index.fromInt 12]
        (SLam "poly" Nothing (SApp use (SGlobal (Index.fromInt 12) "wrong-local")))));
    groundGroupCase "ground specialization leaves polymorphic argument to solver" False (parameter constant)
      (row int (SApp (SApp use (SIntLit 7)) localIdentity));
    groundGroupCase "ground specialization leaves local generalization to solver" False []
      (row int (SLet "id" localIdentity (SApp (SVar "id") (SIntLit 7))));
    groundLocalLetChecks;
    groundGroupCase "ground specialization never generalizes unsigned exports" False []
      [(,) (Index.fromInt 10) ((,,) "function" Nothing localIdentity)];
    groundGroupCase "ground specialization leaves higher-rank argument to solver" False
      (parameter (XArrow identity (XCon "Int" [])))
      (row int (SApp use (SAnn localIdentity
        (SAnnotation [] (SForall Flexible "a" SBottom (SArrow (STVar "a") (STVar "a")))))));
    let { bounded = parameter (XForall a (XCon "Int" []) (XArrow xa xa));
      invalid = row (SCon "Bool" []) (SApp use (SBoolLit True)) };
    boundedPrepared <- recursiveRight "bounded rejection preparation" (Inference.prepareIndexedGroup bounded [] invalid);
    check "ground specialization respects non-bottom bound"
      (isLeft (Inference.groundIndexed bounded invalid (snd boundedPrepared)));
    check "ordinary solver rejects the same non-bottom bound"
      (isLeft (Inference.finishOpenGroup (fst boundedPrepared) (map snd invalid) (snd boundedPrepared)));
    check "combined route rejects the same non-bottom bound"
      (isLeft (Inference.compileOpenGroupIndexed "control" bounded [] invalid));
    let { bad = [row int (SApp (SApp use (SIntLit 7)) (SBoolLit True)),
          row arrow (SLam "x" Nothing (SApp (SVar "x") (SVar "x"))),
          row int (SGlobal (Index.fromInt 99) "poly")] };
    mapM_ (\members -> do {
      prepared <- recursiveRight "ground bad preparation" (Inference.prepareIndexedGroup (parameter identity) [] members);
      check "ground invalid use rejects fast route"
        (isLeft (Inference.groundIndexed (parameter identity) members (snd prepared)));
      check "ground invalid use rejects ordinary route"
        (isLeft (Inference.finishOpenGroup (fst prepared) (map snd members) (snd prepared)));
      check "ground invalid use rejects combined route"
        (isLeft (Inference.compileOpenGroupIndexed "control" (parameter identity) [] members))
    }) bad
  };
  groundLocalLetChecks = do {
    let { int = recursiveInt; a = Index.fromInt 33; b = Index.fromInt 34;
      sig = Just (SAnnotation [] (SCon "Int" []));
      identity = SLam "value" Nothing (SVar "value");
      app f x = SApp f (SIntLit x);
      add x y = SApp (SApp (SPrimitive PAddInt) x) y;
      conditional b yes no = SApp (SApp (SApp (SPrimitive PIfThenElse) b) yes) no;
      lexical = SVar "id"; owned = SGlobal a "misleading"; shadow = SGlobal b "id";
      local body = SLet "id" identity body;
      indexed body = SDeclScope [a] (local body);
      selected route = case route of { Inference.IndexedSignedGround -> True; _ -> False };
      ordinary route = case route of { Inference.IndexedOrdinary -> True; _ -> False };
      run label strict route rhs answer = groundLocalLetCase label sig strict route rhs int
        (\term -> groundLocalInt label term answer);
      candidate ref = SWantedScope "CaseDictionary" (CandidateEnvironment 0 [(,) GivenEvidence ref]);
      lexicalWanted = candidate (LexicalRef "id");
      ownedWanted = candidate (DeclRef a "other hint") };
    run "signed lexical one-use specialization" False selected (local (app lexical 7)) 7;
    run "signed resolved one-use with an identically named shadow" False selected
      (indexed (add (app owned 7) (app (SDeclScope [b] (SLam "id" Nothing shadow)) 2))) 9;
    run "repeated polymorphic local at different types" False ordinary
      (local (conditional (SApp lexical (SBoolLit True)) (app lexical 7) (SIntLit 0))) 7;
    run "repeated polymorphic local at the same type" False ordinary
      (indexed (add (app owned 7) (app (SGlobal a "id") 8))) 15;
    run "repeated closed local stays specialized" True selected
      (SLet "f" (SLam "x" Nothing (add (SVar "x") (SIntLit 1)))
        (add (app (SVar "f") 7) (app (SVar "f") 9))) 18;
    check "one potential implicit use is not one explicit use"
      (not (Inference.groundSingleUse Nothing "id" lexicalWanted));
    check "an explicit use plus a lexical wanted candidate cannot specialize"
      (not (Inference.groundSingleUse Nothing "id" (SApp lexical lexicalWanted)));
    check "an explicit use plus a resolved wanted candidate cannot specialize"
      (not (Inference.groundSingleUse (Just a) "id" (SApp owned ownedWanted)));
    check "two implicit sites cannot specialize"
      (not (Inference.groundSingleUse (Just a) "id" (SApp ownedWanted ownedWanted)));
    check "an unrelated same-spelled resolved candidate is not a use"
      (Inference.groundSingleUse (Just a) "owner" (SApp owned (candidate (DeclRef b "owner"))));
    groundLocalLetCase "escaped local identity retains its principal export"
      Nothing False ordinary (local lexical) recursiveIdentity groundLocalPrincipalUse;
    let { collision =
      "class LocalRouteValue a where { localRouteValue :: a -> Int }\n" ++
      ("instance LocalRouteValue Int where { localRouteValue x = addInt x 3 }\n" ++
        ("useLocalRoute :: forall a. LocalRouteValue a => a -> Int\n" ++
          ("useLocalRoute givenDictionary0 = let once = \\v -> v in if once True then (\\givenDictionary1 -> addInt (localRouteValue givenDictionary0) givenDictionary1) 4 else 0\n" ++
            "main = useLocalRoute 7"))) };
    result <- recursiveRight "qualified source permits user givenDictionary names"
      (mapLeft C.prettyError (C.compile "Example.hs" (source collision)));
    check "qualified source collision result type"
      (IndependentType.alphaEq recursiveInt (C.inferredType result));
    groundLocalInt "qualified source given names do not capture evidence" (C.compiledTerm result) 14
  };
  groundLocalLetCase label annotation strict route rhs expected use = do {
    let { members = [(,) (Index.fromInt 10) ((,,) "answer" annotation rhs)];
      bind = Surface.bindIndexedMembers };
    env <- recursiveRight (label ++ " environment") (Open.environment []);
    (,) external lowered <- recursiveRight (label ++ " prepare")
      (Inference.prepareIndexedGroupIn (Just env) bind [] [] members);
    check (label ++ " conservative admission")
      (isRight (Inference.groundIndexed [] members lowered) == strict);
    (,) selected actual <- recursiveRight (label ++ " file compiler")
      (Inference.compileFileGroupRoutingIn (,) env bind "local-let-control" [] [] members);
    check (label ++ " selected route") (route selected);
    ordinary <- recursiveRight (label ++ " ordinary solver") (Inference.finishOpenGroup external (map snd members) lowered);
    let { target fragment = case (,) (Open.bindings fragment) (Open.body fragment) of {
      (,) [(,) binder ty] (XLet owner value (XConstructor "()" [])) ->
        if eqString (X.nameHint binder) "answer" && X.equalName owner binder && XT.alphaEq ty expected
        then Right (XWithData (Open.declarations (Open.context fragment)) (XLet owner value (XVarTerm binder)))
        else Left "wrong export";
      _ -> Left "expected one exported let"
    } };
    actualTerm <- recursiveRight (label ++ " select actual export") (target actual);
    ordinaryTerm <- recursiveRight (label ++ " select ordinary export") (target ordinary);
    recursiveCheckedType (label ++ " actual independent export") expected (Independent.checkClosed actualTerm);
    recursiveCheckedType (label ++ " ordinary independent export") expected (Independent.checkClosed ordinaryTerm);
    check (label ++ " erasure agrees with ordinary")
      (monomorphicErasure M.empty (monomorphicAdministrative M.empty (X.erase actualTerm))
        (monomorphicAdministrative M.empty (X.erase ordinaryTerm)));
    use actualTerm;
    use ordinaryTerm
  };
  groundLocalInt label term expected = do {
    state <- recursiveRight (label ++ " runtime data") (Runtime.prepare False term);
    actual <- recursiveRight label (Runtime.evaluate (fst state) (Runtime.REnv M.empty) (X.erase term));
    check label (case actual of { Runtime.RInteger n -> n == expected; _ -> False })
  };
  groundLocalPrincipalUse term = case term of {
    XWithData datatypes (XLet owner rhs variable) -> do {
      let { applied ty arg =
        XWithData datatypes (XLet owner rhs (XApp (X.instantiate variable (X.typeApplication ty)) arg));
        int = applied recursiveInt (XIntTerm 7);
        bool = applied recursiveBool (XBoolTerm True) };
      recursiveCheckedType "escaped identity instantiated at Int" recursiveInt (Independent.checkClosed int);
      recursiveCheckedType "escaped identity instantiated at Bool" recursiveBool (Independent.checkClosed bool);
      groundLocalInt "escaped identity runtime at Int" int 7;
      state <- recursiveRight "escaped identity Bool runtime data" (Runtime.prepare False bool);
      value <- recursiveRight "escaped identity Bool evaluation"
        (Runtime.evaluate (fst state) (Runtime.REnv M.empty) (X.erase bool));
      check "escaped identity runtime at Bool" (case value of { Runtime.RBoolean actual -> actual; _ -> False })
    };
    _ -> check "escaped identity target has one let" False
  };
  groundCaseEvidenceCheck = let {
    datatypes = [DataDecl "CaseDictionary" ["a"]
      [ConstructorDecl "CaseDictionary" [Function (Parameter "a") (Parameter "a")]]];
    variable = STVar "a";
    annotation = SAnnotation [] (SForall Flexible "a" SBottom
      (SArrow (SCon "CaseDictionary" [variable]) (SArrow variable variable)));
    wanted = SWantedScope "CaseDictionary" (CandidateEnvironment 0 []);
    rhs = SLam "dictionary" Nothing (SLam "input" Nothing (SGivenScope ["dictionary"]
      (SCase wanted [SAlternative (SConstructorPattern "CaseDictionary" [Just "method"])
        (SApp (SVar "method") (SVar "input"))])));
    members = [(,) (Index.fromInt 10) ((,,) "applyDictionary" (Just annotation) rhs)]
  } in inferenceGroupCaseWithData Inference.groundIndexed
    "signed polymorphic case with lexical evidence" True datatypes [] members;
  groundRecursiveChecks = do {
    let { int = SCon "Int" []; bool = SCon "Bool" [];
      sig = \ty -> Just (SAnnotation [] (SArrow int ty));
      peer = \i -> SGlobal (Index.fromInt i) "non-authoritative hint";
      member = \i name annotation rhs -> (,) (Index.fromInt i) ((,,) name annotation
        (SDeclScope [Index.fromInt (i + 100)] (SLam "x" Nothing (rhs (peer (i + 100))))));
      choose = \yes no -> SApp (SApp (SApp (SPrimitive PIfThenElse) (SBoolLit True)) yes) no;
      left = member 20 "left" (sig int) (\x -> choose (SIntLit 7) (SApp (peer 10) x));
      right = member 10 "right" (sig int) (\x -> SApp (peer 20) x);
      self = member 40 "self" (sig int) (\x -> choose x (SApp (peer 40) x));
      a = XTyVar 50; poly = [(,,) (Index.fromInt 3) "identity" (XForall a XBot (XArrow (XVar a) (XVar a)))];
      imported = member 10 "right" (sig int) (\x -> SApp (peer 3) (SApp (peer 20) x));
      wrong = member 10 "right" (sig bool) (\x -> SApp (peer 20) x);
      mixed = member 10 "right" Nothing (\x -> SApp (peer 20) x);
      route = inferenceGroupCase Inference.groundRecursiveIndexed };
    route "recursive ground mutual by declaration identity" True [] [right,left];
    route "recursive ground use of polymorphic import" True poly [imported,left];
    route "recursive ground self edge" True [] [self];
    prepared <- recursiveRight "recursive ground mixed preparation"
      (Inference.prepareIndexedGroup [] [] [mixed,left]);
    check "recursive ground requires every signature"
      (isLeft (Inference.groundRecursiveIndexed [] [mixed,left] (snd prepared)));
    invalid <- recursiveRight "recursive ground mismatched peer preparation"
      (Inference.prepareIndexedGroup [] [] [wrong,left]);
    check "recursive ground rejects a mismatched peer"
      (isLeft (Inference.groundRecursiveIndexed [] [wrong,left] (snd invalid)));
    check "recursive ground keeps ordinary error" (case (,)
      (Inference.finishOpenGroup (fst invalid) (map snd [wrong,left]) (snd invalid))
      (Inference.compileOpenGroupIndexed "control" [] [] [wrong,left]) of {
        (,) (Left expected) (Left actual) -> eqString expected actual;
        _ -> False
      })
  };
  groundRecursiveSourceRoutes = do {
    let { sourceRows = "goSigned :: Int -> Int\ngoSigned x = if eqInt x 0 then 7 else goForward x\n";
      forwarder = "goForward x = goSigned x";
      mixed route = case route of { Inference.IndexedMixedForwarder -> True; _ -> False };
      signed route = case route of { Inference.IndexedSignedRecursion -> True; _ -> False };
      ordinary route = case route of { Inference.IndexedOrdinary -> True; _ -> False } };
    groundRecursiveSourceCase "one unsigned forwarder selects mixed recursion" mixed (sourceRows ++ forwarder);
    groundRecursiveSourceCase "two signed peers select signed recursion" signed
      (sourceRows ++ ("goForward :: Int -> Int\n" ++ forwarder));
    groundRecursiveSourceCase "unsigned computation falls back to ordinary recursion" ordinary
      (sourceRows ++ "goForward x = addInt (goSigned x) 1")
  };
  groundRecursiveSourceCase label expectedRoute text = do {
    parsed <- recursiveRight (label ++ " parse") (parse text);
    resolved <- recursiveRight (label ++ " resolve")
      (Modules.resolveCrate NoImplicitPrelude M.empty Modules.spelling [parsed]);
    -- Resolution installs the primitive facade as a real module. Its own
    -- declarations are not members of the test's source compilation unit.
    let { modules = filter (\entry -> eqString (Modules.moduleIdentity parsed)
          (Modules.moduleIdentity (Modules.resolvedSource entry))) (Modules.resolvedCrateModules resolved);
      values = Modules.boundIn resolved modules;
      scopes = Modules.resolvedValueScopesIn resolved modules;
      reads = Dependency.fileLastDeclarationOccurrences;
      bind = Surface.bindIndexedMembersWith (Dependency.occurrenceGlobalIds reads) };
    (,) planned _ <- recursiveRight (label ++ " plan")
      (Source.prepareResolvedSourcePlan values M.empty [] [] [] [] scopes []);
    original <- case planned of { Just plan -> ioReturn plan; Nothing -> panic (label ++ " lacks a resolved plan") };
    (,) plan open <- recursiveRight (label ++ " query plan")
      (Source.protectedQueryPlanReading Dependency.fileDeclarationOccurrences original M.empty);
    contracts <- recursiveRight (label ++ " initial contracts") (Source.initialContracts plan M.empty M.empty);
    (,) checked steps <- recursiveRight (label ++ " open contracts") (open contracts);
    (,) owners prepare <- case steps of {
      [step] -> ioReturn step; _ -> panic (label ++ " must be one source SCC")
    };
    (,) slots prepared <- recursiveRight (label ++ " prepared slots") (do {
      group <- prepare checked;
      Source.slotPreparedWith (Dependency.fileLastValueOccurrences False) checked owners group
    });
    members <- recursiveRight (label ++ " indexed members") (Source.indexedMembers slots prepared);
    inventory <- recursiveRight (label ++ " datatype inventory") (Query.prepareData (Source.planData plan));
    let { parameters = Source.expectedParameters slots prepared;
      datatypes = Query.requiredFileDataIn inventory (Source.groupMembers prepared)
        (append (Source.groupBindings prepared) (Source.groupCandidateBindings prepared));
      int = XCon "Int" []; expectedType = XArrow int int;
      types fragment = let { bindings = Open.bindings fragment } in
        eqList eqString (sortBy compareString (map (compose X.nameHint fst) bindings)) ["goForward","goSigned"] &&
        all (\entry -> XT.alphaEq expectedType (snd entry)) bindings;
      knot fragment = case Open.body fragment of {
        XLetRec [_,_] (XConstructor "()" []) -> True;
        _ -> False
      } };
    check (label ++ " closed inputs") (null parameters);
    env <- recursiveRight (label ++ " environment") (Open.environment datatypes);
    (,) route actual <- recursiveRight (label ++ " file compile")
      (Inference.compileFileGroupRoutingIn (,) env bind "mixed-source-control" parameters datatypes members);
    check (label ++ " selected route") (expectedRoute route);
    _ <- recursiveRight (label ++ " validate prepared fragment") (Source.validatePreparedOpen slots prepared actual);
    (,) external lowered <- recursiveRight (label ++ " prepare ordinary")
      (Inference.prepareIndexedGroupIn (Just env) bind parameters datatypes members);
    ordinary <- recursiveRight (label ++ " ordinary") (Inference.finishOpenGroup external (map snd members) lowered);
    check (label ++ " exact exports and recursive knot") (types actual && types ordinary && knot actual && knot ordinary);
    let { a = Open.closedTerm actual; b = Open.closedTerm ordinary };
    check (label ++ " erasure") (monomorphicErasure M.empty (monomorphicAdministrative M.empty (X.erase a))
      (monomorphicAdministrative M.empty (X.erase b)));
    actualType <- recursiveRight (label ++ " frozen target") (Independent.checkClosed a);
    ordinaryType <- recursiveRight (label ++ " ordinary frozen target") (Independent.checkClosed b);
    check (label ++ " independent type") (XT.alphaEq actualType ordinaryType)
  };
  groundAliasDepth known identity = case IM.lookup identity known of {
    Just (Inference.GroundVar next) -> 1 + groundAliasDepth known next;
    _ -> 0
  };
  groundAliasChecks = do {
    let { a = XTyVar 100; ty = XForall a XBot (XArrow (XVar a) (XVar a));
      globals = M.singleton 3 (Inference.GroundImport (XName 0 "poly") ty);
      call = \body -> SApp (SGlobal (Index.fromInt 3) "wrong") body;
      body = SLam "x" Nothing (foldl (\body _ -> call body) (SVar "x") (range 0 255)) };
    (,,) template actual inferred <- recursiveRight "nested ground uses"
      (Inference.groundInfer globals M.empty (Inference.GroundState 0 IM.empty IM.empty 1) body);
    wanted <- recursiveRight "nested ground target"
      (Inference.groundType M.empty (XArrow (XCon "Int" []) (XCon "Int" [])));
    solved <- recursiveRight "nested ground solve" (Inference.groundUnify inferred actual wanted);
    case solved of { Inference.GroundState _ known _ _ ->
      check "nested polymorphic uses do not build a linear type-alias chain"
        (all (\identity -> groundAliasDepth known identity <= 16) (IM.keys known))
    };
    sealed <- recursiveRight "nested ground seal" (Inference.groundSeal solved template);
    checked <- recursiveRight "nested ground independent check" (Independent.checkClosed (XAbs (XName 0 "poly") ty sealed));
    check "nested polymorphic uses preserve their closed type"
      (XT.alphaEq checked (XArrow ty (XArrow (XCon "Int" []) (XCon "Int" []))))
  };
  monomorphicGroupChecks = do {
    let { int = SCon "Int" []; bool = SCon "Bool" []; arrow = SArrow int int;
      row = \ty body -> [(,) (Index.fromInt 10) ((,,) "function" (Just (SAnnotation [] ty)) body)];
      unsigned = \body -> [(,) (Index.fromInt 10) ((,,) "function" Nothing body)];
      add = \a b -> SApp (SApp (SPrimitive PAddInt) a) b;
      identity = SLam "x" Nothing (SVar "x") };
    monomorphicGroupCase "signed primitive lambda" True []
      (row arrow (SChecked arrow (SLam "x" Nothing (add (SVar "x") (SIntLit 7)))));
    monomorphicGroupCase "signed boolean" True [] (row bool (SBoolLit True));
    monomorphicGroupCase "signed Unicode text" True [] (row (SCon "String" []) (SStringLit "lambda λ"));
    monomorphicGroupCase "signed floating value" True [] (row (SCon "Double" []) (SDoubleLit (doubleFromBits (-9223372036854775808))));
    monomorphicGroupCase "signed higher order lambda" True []
      (row (SArrow arrow arrow) (SLam "f" Nothing (SLam "x" Nothing (SApp (SVar "f") (SVar "x")))));
    monomorphicGroupCase "signed application checks lambda argument" True []
      (row int (SApp (SAnn (SLam "f" Nothing (SApp (SVar "f") (SIntLit 8)))
        (SAnnotation [] (SArrow arrow int))) identity));
    monomorphicGroupCase "signed local shadowing" True []
      (row arrow (SLam "x" Nothing (SLet "x" (SIntLit 4) (SVar "x"))));
    monomorphicGroupCase "signed resolved import ignores hint" True
      [(,,) (Index.fromInt 3) "outside" (XCon "Int" [])]
      (row arrow (SLam "x" Nothing (add (SVar "x") (SGlobal (Index.fromInt 3) "wrong-hint"))));
    monomorphicGroupCase "signed named import is shadowed locally" True
      [(,,) (Index.fromInt 3) "x" (XCon "Int" [])]
      (row arrow identity);
    monomorphicGroupCase "polymorphic annotation uses solver" False []
      (row (SForall Flexible "a" SBottom (SArrow (STVar "a") (STVar "a"))) identity);
    monomorphicGroupCase "unsigned declaration uses solver" False []
      [(,) (Index.fromInt 10) ((,,) "function" Nothing identity)];
    monomorphicGroupCase "inferred primitive lambda" True []
      (unsigned (SLam "x" Nothing (add (SVar "x") (SIntLit 7))));
    monomorphicGroupCase "inferred two arguments" True []
      (unsigned (SLam "x" Nothing (SLam "y" Nothing (add (SVar "x") (SVar "y")))));
    monomorphicGroupCase "inferred resolved parameter" True []
      (unsigned (SDeclScope [Index.fromInt 12]
        (SLam "x" Nothing (add (SGlobal (Index.fromInt 12) "wrong") (SIntLit 1)))));
    monomorphicGroupCase "inferred closed global" True
      [(,,) (Index.fromInt 3) "outside" (XArrow (XCon "Int" []) (XCon "Int" []))]
      (unsigned (SLam "x" Nothing (SApp (SGlobal (Index.fromInt 3) "wrong") (SVar "x"))));
    monomorphicGroupCase "inferred literal" True [] (unsigned (SIntLit 7));
    monomorphicGroupCase "inferred boolean" True [] (unsigned (SBoolLit True));
    monomorphicGroupCase "inferred Unicode" True [] (unsigned (SStringLit "λ"));
    monomorphicGroupCase "inferred negative zero" True []
      (unsigned (SDoubleLit (doubleFromBits (-9223372036854775808))));
    monomorphicGroupCase "inferred inline lambda application uses solver" False []
      (unsigned (SLam "x" Nothing (SApp (SLam "y" Nothing (add (SVar "y") (SIntLit 1))) (SVar "x"))));
    monomorphicGroupCase "inferred unused parameter remains polymorphic" False []
      (unsigned (SLam "x" Nothing (SIntLit 1)));
    monomorphicGroupCase "inferred unknown function uses solver" False []
      (unsigned (SLam "f" Nothing (SApp (SVar "f") (SIntLit 1))));
    monomorphicGroupCase "inferred let generalization uses solver" False []
      (unsigned (SLet "id" identity (SApp (SVar "id") (SIntLit 1))));
    monomorphicGroupCase "inferred shadowing leaves outer parameter polymorphic" False []
      (unsigned (SLam "x" Nothing (SLam "x" Nothing (add (SVar "x") (SIntLit 1)))));
    monomorphicGroupCase "recursive declaration uses solver" False []
      (row arrow (SLam "x" Nothing (SApp (SGlobal (Index.fromInt 10) "function") (SVar "x"))));
    let { bad = [row int (SBoolLit True), row arrow (SLam "x" (Just (SAnnotation [] bool)) (SIntLit 1)),
          row int (SGlobal (Index.fromInt 99) "outside"), row int (SVar "missing"),
          row arrow (SChecked (SArrow bool bool) identity),
          unsigned (SLam "x" Nothing (add (SVar "x") (SBoolLit True))),
          unsigned (SLam "x" Nothing (add (SVar "x")
            (SApp (SAnn (SLam "b" Nothing (SIntLit 1)) (SAnnotation [] (SArrow bool int))) (SVar "x"))))] };
    mapM_ (\members -> do {
      check "bad monomorphic declaration rejects"
        (isLeft (Inference.compileOpenGroupIndexed "control" [] [] members));
      case Inference.prepareIndexedGroup [] [] members of {
        Left _ -> ioReturn ();
        Right prepared -> check "bad monomorphic declaration ordinary rejects"
          (isLeft (Inference.finishOpenGroup (fst prepared) (map snd members) (snd prepared)))
      }
    }) bad;
    let { entry = Artifact.definitionName "entry-control" (Modules.Entity "Main" "<crate-entry>" Modules.Value);
      plain = XCon "Int" []; legacy = XForall (XTyVar 1) XBot plain;
      iface = \bindings -> Artifact.CrateInterface "entry-control" [] ["Main"] [(,) "Main" []]
        [(,) "Main" []] [] [] [] [] bindings entry "checked" (map (\binding -> (,) (fst binding) False) bindings);
      bindings = [(,) entry plain, (,) "select_legacy" legacy];
      available = M.fromList compareString [(,) entry ((,) (XName 0 "main") plain),
        (,) "select_legacy" ((,) (XName 2 "legacy") legacy)];
      root = iface bindings };
    check "direct entry preserves legacy import adaptation rejection"
      (isLeft (Artifact.linkEntry 3 [root] root available entry));
    let { ordinary = iface [(,) entry plain]; value = M.fromList compareString [(,) entry ((,) (XName 0 "main") plain)] };
    check "direct entry accepts checked closed monotype"
      (case Artifact.linkEntry 3 [ordinary] ordinary value entry of { Right (XVarTerm n) -> X.nameId n == 0; _ -> False });
    check "direct entry rejects import type mismatch"
      (isLeft (Artifact.linkEntry 3 [ordinary] ordinary (M.fromList compareString [(,) entry ((,) (XName 0 "main") (XCon "Bool" []))]) entry))
  };
  sourceCandidateChecks = do {
    let { int = SCon "Int" [];
      klass = SClassDecl "Probe" [(,) "a" Star] [] [(,) "probe" (SArrow (STVar "a") int)];
      instanceValue = SInstanceDecl [] [] "Probe" [int] [(,) "probe" (SLam "x" Nothing (SVar "x"))];
      members = [(,,) "plain" Nothing (SLam "x" Nothing (SApp (SApp (SPrimitive PAddInt) (SVar "x")) (SIntLit 1))),
        (,,) "overloaded" Nothing (SLam "x" Nothing (SApp (SVar "probe") (SVar "x")))];
      scope = IntSet.fromList [0] };
    planned <- recursiveRight "candidate-demand source plan"
      (Source.prepareSourcePlan M.empty [] [klass] [(,) "probeInt" instanceValue]
        (M.fromList compareString [(,) "plain" scope,(,) "overloaded" scope]) [scope] members);
    plan <- case planned of { Just value -> ioReturn value; Nothing -> panic "candidate-demand source plan fallback" };
    dictionary <- case M.lookup compareString "Probe" (Classes.inventoryOrdinaryRegistry (Source.planInventory plan)) of {
      Just value -> ioReturn value; Nothing -> panic "candidate-demand dictionary missing"
    };
    let { contracts = M.singleton "probeInt" (Source.SourceContract (XCon dictionary [XCon "Int" []]) [] False) };
    plain <- recursiveRight "plain prepared source" (Source.prepareGroup plan contracts ["plain"]);
    overloaded <- recursiveRight "overloaded prepared source" (Source.prepareGroup plan contracts ["overloaded"]);
    check "unsigned root without evidence slots has no candidate dependencies" (null (Source.groupCandidateBindings plain));
    check "unsigned overloaded root retains its exact candidate dependency"
      (eqList eqString (map fst (Source.groupCandidateBindings overloaded)) ["probeInt"]);
    check "unsigned overloaded root retains evidence slots" (case Source.groupAuthority overloaded of {
      Just (Source.RootAuthority _ labels _ _ _) -> not (null labels); _ -> False
    })
  };
  rebuiltHashChecks = do {
    check "open group owner uses exact framing"
      (eqString (Separate.openGroupName "c" ["a","b"])
        "16:MLF-OPEN-GROUP-11:c6:1:a1:b");
    let { owners = map (\((,) crate members) -> Separate.openGroupName crate members)
          [(,) "c" ["a","b"],(,) "c" ["a","c"],(,) "c" ["a1:b"],
           (,) "c" ["ab"],(,) "c1:a" ["b"],(,) "d" ["a","b"],(,) "λ" ["a",""]] };
    check "open group owner retains crate, full membership, boundaries and Unicode"
      (length (nubBy eqString owners) == length owners);
    check "open group owner canonicalizes member order"
      (eqString (Separate.openGroupName "c" ["a","b"]) (Separate.openGroupName "c" ["b","a"]));
    check "open owner reader retains legacy admission"
      (Artifact.openGroupOwnerMatches "c" ["a","b"] (Separate.queryGroupName "c" ["a","b"]));
    check "open owner reader admits exact new ownership"
      (Artifact.openGroupOwnerMatches "c" ["a","b"] (Separate.openGroupName "c" ["a","b"]));
    check "open owner reader rejects empty ownership"
      (not (Artifact.openGroupOwnerMatches "c" [] (Separate.openGroupName "c" [])));
    check "open owner reader rejects changed ownership"
      (all (\owner -> not (Artifact.openGroupOwnerMatches "c" ["a","b"] owner))
        [Separate.openGroupName "d" ["a","b"],Separate.openGroupName "c" ["a"],
         Separate.openGroupName "c" ["a","c"],Separate.openGroupName "c" ["a","b","c"]]);
    let { prepared names original lowered metadata = Wire.VNode 421
            [Wire.VText "v",Structure.toList Structure.toText names,Wire.VText original,
             Wire.VText lowered,Structure.toList Structure.toText metadata];
      finished group fragment bindings = Wire.VNode 427 [Wire.VText group,Wire.VText fragment,
        Structure.toList (Structure.toPair Structure.toText Structure.toText) bindings];
      preparedBase = prepared ["a"] "body" "lowered" ["metadata"];
      finishBase = finished "g" "h" [(,) "a" "d"];
      inventory fields = Wire.VNode 422 (map Wire.VText fields);
      scope fields edges = Wire.VNode 423 [inventory fields,
        Structure.toList (Structure.toPair Structure.toText Structure.toText) edges];
      literal label value text = do {
        bytes <- byteArrayFromString text;
        expected <- byteArrayDigest bytes;
        result <- CrateGraph.hashRebuiltValue value;
        actual <- recursiveRight label result;
        check label (eqString expected actual)
      } };
    literal "prepared input fixed framing" preparedBase
      "25:MLF-PREPARED-INPUT-TEXT-11:v1:11:a4:body7:lowered1:18:metadata";
    literal "finish receipt fixed framing" finishBase
      "25:MLF-FINISH-RECEIPT-TEXT-11:g1:h1:11:a1:d";
    literal "scope inventory fixed framing" (inventory ["a","bc"])
      "26:MLF-SCOPE-INVENTORY-TEXT-11:21:a2:bc";
    literal "scope dependencies fixed framing" (scope ["a"] [(,) "k" "h"])
      "22:MLF-SCOPE-READS-TEXT-11:11:a1:11:k1:h";
    let { variants = [preparedBase,prepared [] "body" "lowered" ["metadata"],
          prepared [""] "body" "lowered" ["metadata"],
          prepared ["a","b"] "body" "lowered" ["metadata"],
          prepared ["a1:b"] "body" "lowered" ["metadata"],
          prepared ["a"] "lowered" "body" ["metadata"],
          prepared ["a"] "body" "lowered" ["meta","data"],
          prepared ["a"] "body" "lowered" ["meta4:data"],
          prepared ["a"] ("λ" ++ stringFromCode 0 ++ stringFromCode 128512) "lowered" ["metadata"],
          finishBase,finished "h" "g" [(,) "a" "d"],finished "g" "h" [(,) "d" "a"],
          inventory [],inventory [""],inventory ["a","bc"],inventory ["ab","c"],
          inventory ["bc","a"],inventory ["λ" ++ stringFromCode 0 ++ stringFromCode 128512],
          scope [] [],scope ["a"] [],scope ["a"] [(,) "k" "h"],
          scope ["a"] [(,) "k" "changed"],scope ["b"] [(,) "k" "h"],
          scope ["a"] [(,) "k" "h",(,) "j" "i"],scope ["a"] [(,) "j" "i",(,) "k" "h"]] };
    hashes <- mapM (\value -> CrateGraph.hashRebuiltValue value >>= recursiveRight "rebuilt hash") variants;
    check "rebuilt hashes retain domains, list boundaries, order and Unicode"
      (length (nubBy eqString hashes) == length variants);
    check "framed allocation bound accepts exact size"
      (eqMaybe (\a b -> a == b) (CrateGraph.framedSize 6 0 ["a","b"]) (Just 6));
    check "framed allocation bound rejects one byte short"
      (isNothing (CrateGraph.framedSize 5 0 ["a","b"]));
    let { ordinary = Wire.VNode 999 [Wire.VBits (-1)] };
    expected <- QueryGraph.hashValue ordinary >>= recursiveRight "ordinary hash";
    actual <- CrateGraph.hashRebuiltValue ordinary >>= recursiveRight "fallback hash";
    check "unknown rebuilt shape retains ordinary encoding" (eqString expected actual);
    let { unknownScope = Wire.VNode 422 [Wire.VBits 1] };
    scopeExpected <- QueryGraph.hashValue unknownScope >>= recursiveRight "ordinary scope shape";
    scopeActual <- CrateGraph.hashRebuiltValue unknownScope >>= recursiveRight "fallback scope shape";
    check "non-text scope shape retains ordinary encoding" (eqString scopeExpected scopeActual);
    first <- CrateGraph.hashRebuiltCached Nothing (scope ["a"] [(,) "k" "h"])
      >>= recursiveRight "initial scope hash";
    repeated <- CrateGraph.hashRebuiltCached (snd first) (scope ["a"] [(,) "k" "h"])
      >>= recursiveRight "repeated scope hash";
    check "exact scope reuses validated digest" (eqString (fst first) (fst repeated));
    mapM_ (\value -> do {
      fresh <- CrateGraph.hashRebuiltValue value >>= recursiveRight "changed scope fresh hash";
      changed <- CrateGraph.hashRebuiltCached (snd repeated) value >>= recursiveRight "changed scope cached hash";
      check "scope memo preserves changed metadata and dependency hashes"
        (eqString fresh (fst changed) && not (eqString (fst repeated) (fst changed)))
    }) [scope ["b"] [(,) "k" "h"],scope ["a"] [(,) "k" "new"],
        scope ["a"] [],inventory ["a"],unknownScope];
    invalidCached <- CrateGraph.hashRebuiltCached (snd repeated)
      (Wire.VNode 423 [inventory ["a"],Wire.VNode 1 [Wire.VNode (-1) []]]);
    check "scope memo still rejects invalid new wire value" (isLeft invalidCached);
    invalid <- CrateGraph.hashRebuiltValue (Wire.VNode (-1) []);
    check "rebuilt hash preserves wire admission rejection" (isLeft invalid)
  };
  declarationInventoryChecks :: IO ();
  declarationInventoryChecks = do {
    let { names = ["z", "alpha", "a", "last"];
      equation name = P.Equation name [] Nothing (SIntLit 1);
      declarations ns = map (\name -> (,,) name Nothing (SIntLit 1)) ns;
      moduleFor ns ds cs = SourceModule "Inventory.hs" (Just "Inventory") Nothing
        [] ds cs [] (declarations ns) Nothing SharedHaskellV1;
      duplicate result = case result of {
        Left message -> eqString message "Inventory: duplicate declaration";
        Right _ -> False
      } };
    grouped <- recursiveRight "distinct declaration inventory" (P.groupValues (map equation names));
    check "group inventory preserves source order"
      (eqList eqString (map (\((,,) name _ _) -> name) grouped) names);
    check "separated equations retain their duplicate diagnostic"
      (case P.groupValues (map equation ["z", "a", "z"]) of {
        Left message -> eqString message "function equations must be contiguous; duplicate value declaration";
        Right _ -> False
      });
    check "preconstructed shared module rejects duplicate values"
      (case P.validateSharedModule (moduleFor ["f", "f"] [] []) of {
        Left message -> eqString message "duplicate value declaration"; Right _ -> False
      });
    let { open = Just (SAnnotation ["a"] (STVar "a"));
          raw rhs = SourceModule "Inventory.hs" (Just "Inventory") Nothing [] [] [] []
            [(,,) "f" open rhs] Nothing SharedHaskellV1 };
    check "preconstructed recursive group requires a closed signature"
      (case P.validateSharedModule (raw (SVar "f")) of {
        Left message -> eqString message "recursive definition f requires an explicit closed signature";
        Right _ -> False
      });
    check "preconstructed nonrecursive annotation keeps its scope"
      (isRight (P.validateSharedModule (raw (SIntLit 1))));
    let { slot = Index.fromInt 3; span = SourceSpan "pkg" "Inventory" "Inventory.hs" 1 1 1 2;
          scoped rhs = SDeclScope [slot] (SLet "x" rhs (SCallSite "f" span (SGlobal slot "f")));
          core = scoped (SIntLit 1) };
    check "surface lowering preserves declaration IDs, hints and spans"
      (case Surface.lowerExpression core of {
        Right result -> SourceEquality.eqSExprBits result core; Left _ -> False
      });
    check "surface lowering finds equations inside a scope"
      (case Surface.lowerExpression (scoped (SEquations [])) of {
        Left message -> eqString message "function has no equations"; Right _ -> False
      });
    check "adjacent equations still form one declaration"
      (accept "choose True = 1\nchoose False = 2");
    let { large = map (\n -> "value" ++ showInt n) (range 0 1023) };
    check "large distinct module inventory" (isRight (Modules.locals (moduleFor large [] [])));
    check "identical duplicate entity cannot disappear in a set"
      (duplicate (Modules.locals (moduleFor (append large ["value0"]) [] [])));
    check "duplicate final key is rejected"
      (duplicate (Modules.locals (moduleFor (append large ["value1023"]) [] [])));
    let { thing = DataDecl "Thing" [] [ConstructorDecl "Thing" []] };
    check "type and constructor may share their spelling"
      (isRight (Modules.locals (moduleFor [] [thing] [])));
    check "constructor and value share the term namespace"
      (duplicate (Modules.locals (moduleFor ["Thing"] [thing] [])));
    check "class and datatype share the type namespace"
      (duplicate (Modules.locals (moduleFor [] [thing] [SClassDecl "Thing" [] [] []])));
    check "method and value share the term namespace"
      (duplicate (Modules.locals (moduleFor ["method"] []
        [SClassDecl "Class" [] [] [(,) "method" (STVar "a")]])))
  };
  -- Reference precedence grammar before the delimiter shortcut. The operators,
  -- associativity and non-associative comparison diagnostic are tested together.
  precedenceParserChecks :: IO ();
  precedenceParserChecks = let {
    at choices = Parsing.pMap (\((,) location operator) a b ->
      SApp (SApp (SCallSite (P.referenceLeaf operator) location
        (SVar (P.sourceOperatorName operator))) a) b)
      (Parsing.pWithSpan (P.sharedInfix choices));
    product = Parsing.pChainl P.operand (at ["*","/","%"]);
    sum = Parsing.pChainl product (at ["+","-"]);
    concatOp = Parsing.pChoice (Parsing.pMap (\_ -> P.sourceConsExpression) (Parsing.pToken ":")) (at ["++"]);
    joined = Parsing.pChainr sum concatOp;
    level4 = do {
      first <- joined;
      rest <- Parsing.pMany (do { op <- P.sharedInfix P.sharedLevel4Operators; value <- joined; Parsing.pPure ((,) op value) });
      when (length rest > 1 && any (\entry -> elem eqString (P.referenceLeaf (fst entry)) P.sharedComparisons) rest)
        (Parsing.pFail "ambiguous use of a non-associative comparison operator");
      Parsing.pPure (foldl (\left entry -> P.namedOperator (fst entry) left (snd entry)) first rest)
    };
    conjunction = Parsing.pChainr level4 (at ["&&"]);
    disjunction = Parsing.pChainr conjunction (at ["||"]);
    reference = Parsing.pChainl disjunction (at [">>=",">>"]);
    remaining = \(Parsing.ParseState _ tokens _ _ _ _) -> map Lexer.tokenText tokens;
    sameState = \a b -> Parsing.stateOffset a == Parsing.stateOffset b && eqList eqString (remaining a) (remaining b);
    agrees = \spellings -> let {
      tokens = zipWith (\index word -> Lexer.Token word 3 (index * 5) 3 (index * 5 + stringLength word))
        (range 1 (length spellings)) spellings;
      start = Parsing.ParseState "Prec.hs" tokens (Lexer.Token "" 4 1 4 1) SharedHaskellV1 "Prec" "pkg"
    } in case (,) (Parsing.pRun reference start) (Parsing.pRun P.sharedBindExpr start) of {
      (,) (Parsing.PSuccess a end used) (Parsing.PSuccess b next more) -> used == more && sameState end next && SourceEquality.eqSExpr a b;
      (,) (Parsing.PFailure a end used) (Parsing.PFailure b next more) -> used == more && sameState end next && eqString a b;
      _ -> False
    };
    operators = append [":"] Lexer.sharedValueOperators;
    combinations = concatMap (\a -> map (\b -> ["x",a,"y",b,"z",")"]) operators) operators;
    examples = [[],["x"],["x","M",".","+","y"],["x","M",".+","y"],["x","M",".","N",".++","y"],["x","M","."],["M",".","x","+","y"],["x","+"],
      ["x","<","y","==","z"],["(","x","+","y",")","*","z"],["(",")"],["(","-","1",")"],
      ["(","+",")","x"],["(",",",")"],["1.5",";"],["f","[","x",",","y","]"],["(","let"],["1","(","x"]]
  } in check "shared infix precedence, associativity, spans, residual tokens and errors"
         (all agrees (append examples combinations));
  applicationParserChecks :: IO ();
  applicationParserChecks = let {
    reference = Parsing.pBind P.atom (\first -> Parsing.pMap (foldl SApp first) (Parsing.pMany P.atom));
    remaining = \(Parsing.ParseState _ tokens _ _ _ _) -> map Lexer.tokenText tokens;
    sameState = \a b -> Parsing.stateOffset a == Parsing.stateOffset b &&
      eqList eqString (remaining a) (remaining b);
    agrees expected actual syntax spellings = let {
      tokens = zipWith (\col spelling -> Lexer.Token spelling 3 col 3 (col + stringLength spelling))
        (range 1 (length spellings)) spellings;
      state = Parsing.ParseState "App.hs" tokens (Lexer.Token "" 4 1 4 1) syntax "App" "pkg"
    } in case (,) (Parsing.pRun expected state) (Parsing.pRun actual state) of {
      (,) (Parsing.PSuccess a end used) (Parsing.PSuccess b next more) ->
        used == more && sameState end next && SourceEquality.eqSExpr a b;
      (,) (Parsing.PFailure a end used) (Parsing.PFailure b next more) ->
        used == more && sameState end next && eqString a b;
      _ -> False
    };
    examples = append (map (\stop -> ["f","x",stop,"y"]) [")",",",";","}","]"])
      [[],[")"],["f"],["f","(","g","x",")","y"],["f","(",")"],
       ["f","("],["f","[","x",","],["f","then"],["f","M",".","g"]];
    equations = append examples [
      ["Fork","(","Tip","x",")","(","Tip","x",")",";","next"],
      ["Z9'","(","A_","(","B1","x",")",")","}"],["True","(","A","x",")",";"],
      ["Node","M",".","Leaf",";"],["Node","(","x",",","Leaf",")"],["Node","(","Leaf"],
      ["f","(","g","(","x",")",")","x",";","next"],["if","x","then","y","else","z"],
      ["f","(","x",",","y",")"],["x","::","Int"],["x","+",")"],["x","}"],
      ["f","0xff","3.25","9e-2"],["x","(","let","{","x","=","1","}","in","x",")"],
      ["M",".","f","x"],["x",":::", "y"],["f","(","(","g","x",")",")","x",")"]];
    profiles = [SharedHaskellV1,LegacyEmlfV1,MetadataSyntax]
  } in do {
    check "application tree, residual tokens and committed failures"
      (all (\syntax -> all (agrees reference P.application syntax) examples) profiles);
    check "equation RHS tree, coordinates, remaining tokens and committed failures"
      (all (\syntax -> all (agrees P.expr P.equationExpression syntax) equations) profiles);
    check "scanned source equation constructors, coordinates and general grammar fallback"
      (all (\syntax -> all (agrees P.expr (P.equationExpressionWith True) syntax) equations) profiles)
  };
  finalGeometryChecks :: IO ();
  finalGeometryChecks = do {
    let { texts = \glyph -> Wire.VNode 8 (replicate 40 (Wire.VText
              (concatStringList (replicate 65536 glyph))));
      ascii = texts "a"; multibyte = texts (stringFromCode 128512) };
    check "source geometry charges UTF-8 bytes independently of node count" (case
      (,) (Source.smallFinalValue ascii) (Source.smallFinalValue multibyte) of {
        (,) (Just False) Nothing -> True; _ -> False });
    check "full graph admits the shared ASCII and multibyte trees"
      (all (\raw -> isRight (Wire.planGraph Wire.defaultLimits [raw])) [ascii,multibyte]);
    check "legacy task-list geometry preserves its four-unit scalar budget"
      (case (,) (Source.smallFinalTasks [(,,) 1 False [Wire.VText "x"]] 5 1 False)
                (Source.smallFinalTasks [(,,) 1 False [Wire.VText "x"]] 4 1 False) of {
        (,) (Just False) Nothing -> True; _ -> False })
  };
  frontendChecks :: IO ();
  frontendChecks =
    do {
      declarationInventoryChecks;
      applicationParserChecks;
      precedenceParserChecks;
      finalGeometryChecks;
      formatterChecks;
      monomorphicGroupChecks;
      groundGroupChecks;
      templateGroupChecks;
      sourceCandidateChecks;
      rebuiltHashChecks;
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
      let { plain = concatStringList (map (\_ -> "a") (range 1 257));
            invalid = "x\n" ++ plain ++ "\t" } in
        check "plain source run keeps the next error at its scalar column"
          (case L.validateSharedSource "Run.hs" invalid (stringLength invalid) (L.Cursor 0 1 1) 0 of {
            Left message -> eqString message "Run.hs:2:258: shared source requires LF and spaces-only whitespace";
            Right _ -> False
          });
      check "module metadata" (accept "main = 42");
      check "forward group scope" forwardScope;
      check "ordinary true and constructor True" atomNameCase;
      check "open symbol slot order and repeated names" openSymbolOrder;
      check "bounded Prelude variable reads" boundedDeclarationReads;
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
      check "list comprehension with a missing source rejected"
        (reject "main = [x | x <- ]");
      check "list comprehension with a trailing comma rejected"
        (reject "main = [x | x <- [1], ]");
      check "open-ended range without a start rejected" (reject "main = [..]");
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
    check "qualified application operator" (linked "main = addInt 40 MLF.Primitive.$ 2");
    check "application operator selective import"
      (linkRaw "module Example where\nimport MLF.Primitive (($), addInt)\nmain = ($) (addInt 40) 2\n");
    check "application operator honors hiding"
      (not (linkRaw "module Example where\nimport MLF.Primitive hiding (($))\nmain = addInt 40 $ 2\n"));
    check "shadowed application operator is accepted in prefix form"
      (linked "main = let { ($) x y = subInt x y } in ($) 10 3");
    check "shadowed application operator is rejected in infix form"
      (recursiveInfixRejected "main = let { ($) x y = subInt x y } in 10 $ 3");
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
  listExpressionChecks :: IO ();
  listExpressionChecks =
    let {
      cases =
        [("comprehension skips a refutable generator and preserves nested generator order",
          "case [10 * x + y | Symbol x <- [Symbol 1, Missing, Symbol 2], (_,y) <- [(0,x),(0,x + 1)]] of { [11,12,22,23] -> 42; _ -> 0 }"),
         ("comprehension lets and guards use the preceding qualifier scope",
          "case [y | x <- [19,20,21], let { y = x * 2 }, y > 40] of { [42] -> 42; _ -> 0 }"),
         ("implicit comprehension let ends before the next qualifier",
          "case [y | x <- [40], let y = x + 2, y > 0] of { [y] -> y; _ -> 0 }"),
         ("final implicit comprehension let ends at the closing bracket",
          "case [y | x <- [40], let y = x + 2] of { [y] -> y; _ -> 0 }"),
         ("comprehension does not force an ignored element or unused tail",
          "case [42 | _ <- (panic \"unused element\" :: Int) : panic \"unused tail\"] of { x : _ -> x; [] -> 0 }"),
         ("typed open-ended range supplies a finite prefix lazily",
          "case [40 :: Int ..] of { x : y : z : _ -> z; _ -> 0 }"),
         ("compact open-ended range stops at Int's upper bound",
          "case ([9223372036854775807..] :: [Int]) of { [_] -> 42; _ -> 0 }"),
         ("stepped open-ended range descends",
          "case [46,44..] of { x : y : z : _ -> z; _ -> 0 }"),
         ("zero-step open-ended range repeats",
          "case [42,42..] of { x : y : z : _ -> z; _ -> 0 }"),
         ("stepped open-ended range handles a step wider than Int",
          "let { low = 0 - 9223372036854775807 - 1; high = 9223372036854775807 } in case ([low,high..] :: [Int]) of { [a,b] -> if a == low && b == high then 42 else 0; _ -> 0 }"),
         ("application operator is right-associative", "addInt 2 $ mulInt 2 $ 20"),
         ("application operator binds below arithmetic", "mulInt 2 $ 20 + 1"),
         ("application operator binds below monadic bind", "unBox $ Box 20 >>= (\\x -> Box (x + 22))"),
         ("application operator accepts a lambda and preserves laziness",
          "(\\f -> f (panic \"unused argument\" :: Int)) $ \\_ -> 42")];
      -- Compile the controls together to share the compiler's builtin setup.
      numbered = zip (range 1 (length cases)) cases;
      requireExpression (ordinal, (_, expression)) rest =
        "require " ++ showInt ordinal ++ " (" ++ expression ++ ") (" ++ rest ++ ")";
      fixture = boxMonad ++
        "data Symbol = Missing | Symbol Int\nrequire :: Int -> Int -> Int -> Int\n" ++
        "require ordinal actual rest = if actual == 42 then rest else ordinal\nmain = " ++
        foldr requireExpression "0" numbered
    } in
    case evaluated fixture of {
      Right (Runtime.RInteger 0) -> ioReturn ();
      Right (Runtime.RInteger ordinal) -> check (fst (index cases (ordinal - 1))) False;
      Right _ -> check "list-expression controls returned an unexpected value" False;
      Left error -> check ("list-expression controls: " ++ error) False
    };
  nativeFirst :: IO ();
  nativeFirst = do {
    listExpressionChecks;
    check "file-owned constraints specialize saturated primitives" saturatedPrimitiveRouting;
    check "wildcard columns stay lazy and a binder in a later row shadows the outer name"
      (evaluatesInt
        ("outer = 40\npick _ _ _ True = outer\npick _ _ outer False = outer\n" ++
         "unused :: Int\nunused = panic \"unused pattern column\"\n" ++
         "main = addInt (pick unused unused unused True) (pick unused unused 2 False)")
        42);
    check "saturated conditional preserves rank and lazy integer alternatives"
      (evaluatesInt
        ("choose :: Bool -> (forall a. a -> a) -> (forall a. a -> a) -> Int\n" ++
         "choose test f g = (if test then f else g) 13\n" ++
         "pick n = case n of { 1 -> choose True (\\x -> x) (\\x -> panic \"unselected function\"); 0 -> panic \"unselected alternative\"; _ -> 16 }\n" ++
         "main = addInt (pick 1) (pick 8)")
        29);
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
  -- The old flags and frozen driver use these same case actions. The
  -- grouped actions keep their existing source-sharing and exact banners.
  recoverFrontend :: IO () -> A.Test ();
  recoverFrontend action =
    A.Test (catchIOError (do { action; ioReturn (Right ()) }) (\error ->
      let { message = textFromChars (ioeGetErrorString error) } in
      if recursiveStartsWith "shared frontend failure: " message
      then ioReturn (Left (A.Failure message Nothing))
      else ioError error));
  frontendCase name label action =
    Case.test ("shared-frontend/" ++ name) label ["family:shared-frontend"] (recoverFrontend action);
  standard = [
    frontendCase "frontend" "parser, declarations and recursive inference" frontendChecks,
    frontendCase "native-first" "first native semantics group" nativeFirst,
    frontendCase "native-second" "second native semantics group" nativeSecond
  ];
  frontendRegistry = append standard [
    frontendCase "recursive-inference" "focused recursive inference" recursiveInferenceChecks,
    frontendCase "formatter" "formatter grammar"
      (do { formatterChecks; putStrLn "shared frontend: formatter checks passed" })
  ];
  argumentsFrom index count =
    if index >= count then ioReturn []
    else do {
      arg <- getArg index;
      rest <- argumentsFrom (index + 1) count;
      ioReturn ((:) arg rest)
    };
  main :: IO ();
  main = do {
    count <- getArgCount;
    args <- argumentsFrom 0 count;
    case args of {
      [] -> mapM_ (\entry -> A.orExit (Case.action entry)) standard;
      (:) mode _ ->
        let {
          selects = startsRegistry mode;
          legacy = if recursiveStartsWith "--" mode then find (\entry -> eqString (Case.id entry)
            ("shared-frontend/" ++ (stringSlice mode 2 (stringLength mode - 2)))) frontendRegistry else Nothing
        } in
        if selects then do {
          code <- Runner.run args frontendRegistry;
          if code == 0 then ioReturn () else exitWith code
        } else
          case legacy of {
            Just entry -> A.orExit (Case.action entry);
            Nothing -> checkFiles 0 count
          }
    }
  };
  startsRegistry mode =
    elem eqString mode ["--list", "--exact", "--filter", "--tag", "--group", "--format", "--report"]
}
