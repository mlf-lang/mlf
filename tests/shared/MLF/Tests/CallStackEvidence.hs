-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Tests.CallStackEvidence where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import Bootstrap.Std;
  import qualified Bootstrap.Compiler as Compiler;
  import qualified Bootstrap.Classes as Classes;
  import qualified Bootstrap.Fresh as Fresh;
  import qualified Bootstrap.Data as Data;
  import qualified Bootstrap.Map as Map;
  import qualified Bootstrap.Runtime as Runtime;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Type as TargetType;
  prologue :: String;
  prologue = "-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule CallStackCase where\nimport MLF.Primitive\n";
  evaluated :: String -> Either String String;
  evaluated body = do {
    compiled <- mapLeft Compiler.prettyError (Compiler.compile "CallStackCase.hs" (prologue ++ body));
    let { term = Compiler.compiledTerm compiled };
    Check.checkClosed term;
    state <- Runtime.prepare False term;
    result <- Runtime.evaluate (fst state) (Runtime.REnv Map.empty) (X.erase term);
    case result of { Runtime.RString text -> Right text; _ -> Left "expected opaque text result" }
  };
  containsFrom :: String -> String -> Int -> Bool;
  containsFrom needle haystack offset =
    if offset + stringLength needle > stringLength haystack then False
    else if eqString needle (stringSlice haystack offset (stringLength needle)) then True
    else containsFrom needle haystack (offset + 1);
  contains :: String -> String -> Bool;
  contains needle haystack = containsFrom needle haystack 0;
  checkStack :: String -> String -> [] String -> [] String -> IO ();
  checkStack label body present absent = case evaluated body of {
    Left error -> do { putErr (label ++ (": " ++ (error ++ "\n"))); exitWith 1 };
    Right text ->
      if all (\part -> contains part text) present && all (\part -> not (contains part text)) absent
      then putStrLn ("PASS " ++ label)
      else do { putErr (label ++ (": unexpected stack\n" ++ (text ++ "\n"))); exitWith 1 }
  };
  leaf :: String;
  leaf = "leaf :: HasCallStack => Int -> CallStack\nleaf x = callStack\n";
  probe :: String;
  probe = "data Probe a = Pure a | Failed CallStack\ninstance Functor Probe where { fmap f (Pure x) = Pure (f x); fmap f (Failed s) = Failed s }\ninstance Applicative Probe where { pure = Pure; (<*>) (Pure f) (Pure x) = Pure (f x); (<*>) (Failed s) x = Failed s; (<*>) x (Failed s) = Failed s }\ninstance Monad Probe where { (>>=) (Pure x) f = f x; (>>=) (Failed s) f = Failed s }\ninstance MonadFail Probe where { fail message = Failed callStack }\nresult (Pure x) = \"success\"\nresult (Failed s) = textFromChars (prettyCallStack s)\n";
  checkRejected :: String -> String -> IO ();
  checkRejected label body = case Compiler.compile "CallStackCase.hs" (prologue ++ body) of {
    Left _ -> putStrLn ("PASS " ++ label);
    Right _ -> do { putErr (label ++ ": unexpectedly accepted\n"); exitWith 1 }
  };
  checkStructural :: String -> Bool -> IO ();
  checkStructural label result =
    if result then putStrLn ("PASS " ++ label)
    else do { putErr (label ++ ": failed\n"); exitWith 1 };
  qualifier :: SType -> SType;
  qualifier body = SQualified ((:) (SPredicate "MLFHasCallStack" []) []) body;
  structuralChecks :: IO ();
  structuralChecks = do {
    checkStructural "method field keeps evidence"
      (case Classes.field (SForall Flexible "a" SBottom
              (qualifier (STypeApp (STVar "m") (STVar "a")))) of {
         Right (Quantified _ Star (Function (Applied name []) (Application (Parameter _) (Parameter _)))) ->
           eqString name "MLFStackEvidence";
         _ -> False
       });
    checkStructural "substitution traverses method qualification"
      (case Classes.substitute "m" (SCon "Box" [])
              (qualifier (STypeApp (STVar "m") (STVar "a"))) of {
         SQualified _ (STypeApp (SCon name []) _) -> eqString name "Box";
         _ -> False
       });
    checkStructural "nested qualifiers stay rejected"
      (isLeft (Classes.methodEvidenceType
        (SArrow (qualifier (SCon "Int" [])) (SCon "Int" []))));
    checkStructural "method field rejects nested managed qualification"
      (isLeft (Classes.field
        (SArrow (qualifier (SCon "Int" [])) (SCon "Int" []))));
    checkStructural "method field rejects ordinary class qualification"
      (isLeft (Classes.field
        (SQualified ((:) (SPredicate "Eq" ((:) (STVar "a") [])) [])
          (SArrow (STVar "a") (STVar "a")))));
    checkStructural "method field rejects qualified forall bounds"
      (isLeft (Classes.field
        (SForall Flexible "a" (qualifier (SCon "Int" [])) (STVar "a"))));
    checkStructural "managed evidence is never generalized"
      (case Fresh.runFresh []
              (Classes.applyEvidence
                (Just ((,) "leaf" (SourceSpan "main" "Example" "Example.hs" 4 5 4 9)))
                "leaf" Map.empty (SVar "selector")
                ((:) "MonadFail" ((:) "MLFHasCallStack" []))) of {
         Right ((,) (SApp (SApp (SVar _) (SVar _)) (SApp (SConstructor wrapper) _))
                     ((:) ((,) _ wanted) [])) ->
           eqString wrapper "MLFStackEvidence" && eqString wanted "MonadFail";
         _ -> False
       });
    checkStructural "method given reaches callStack without pushing"
      (case Fresh.runFresh []
              (Classes.lowerSignedBody Map.empty Data.emptyDataEnv Map.empty [] Map.empty
                (SVar "$MLF.Stack.callStack") (qualifier (SCon "MLFCallStack" []))
                (SArrow Classes.callStackEvidenceType (SCon "MLFCallStack" []))) of {
         Right (SChecked _ (SLam given _ (SCase (SVar used)
                   ((:) (SAlternative (SConstructorPattern wrapper _) (SVar _)) [])))) ->
           eqString given used && eqString wrapper "MLFStackEvidence";
         _ -> False
       });
    checkStructural "location erasure preserves ordinary annotations"
      (case Classes.eraseCallSites
              (SAnn (SCallSite "id" (SourceSpan "main" "Example" "Example.hs" 4 5 4 7) (SVar "id"))
                (SAnnotation [] (SArrow (STVar "a") (STVar "a")))) of {
         SAnn (SVar name) (SAnnotation [] (SArrow (STVar _) (STVar _))) -> eqString name "id";
         _ -> False
       });
    checkStructural "ordinary local accessor spelling is not intrinsic"
      (case Fresh.runFresh [] (Classes.lowerExpr Map.empty Data.emptyDataEnv Map.empty
              (Map.insert compareString "mlfCallStack" ((,) "mlfCallStack" []) Map.empty)
              [] (SVar "mlfCallStack")) of {
         Right ((,) (SVar name) []) -> eqString name "mlfCallStack";
         _ -> False
       });
    checkStructural "ordinary code keeps class-free path"
      (not (Classes.managedExpression
        (SAnn (SVar "id") (SAnnotation [] (SArrow (STVar "a") (STVar "a"))))))
  };
  managedTargetCompilation =
    let {
      capture = DataDecl "Capture" ((:) "b" [])
        ((:) (ConstructorDecl "Capture" ((:) (Applied "MLFCallStack" []) [])) []);
      declaration = SClassDecl "Observe" ((:) ((,) "a" Star) []) []
        ((:) ((,) "observe" (SForall Flexible "b" SBottom
          (qualifier (SArrow (STVar "a") (SCon "Capture" ((:) (STVar "b") [])))))) []);
      inst = SInstanceDecl [] [] "Observe" ((:) (SCon "Int" []) [])
        ((:) ((,) "observe" (SLam "x" Nothing (SApp (SConstructor "Capture") (SVar "$MLF.Stack.callStack")))) []);
      application = SApp
        (SCallSite "observe" (SourceSpan "main" "Example" "Example.hs" 1 1 1 8) (SVar "observe"))
        (SIntLit 42);
      body = SCase
        (SAnn application (SAnnotation [] (SCon "Capture" ((:) (SCon "Bool" []) []))))
        ((:) (SAlternative (SConstructorPattern "Capture" ((:) (Just "stack") [])) (SVar "stack")) [])
    } in Compiler.compileProgramWithPrelude NoImplicitPrelude
                (SClassProgram ((:) capture []) ((:) declaration []) ((:) inst []) body);
  managedTargetCheck :: Bool;
  managedTargetCheck = case managedTargetCompilation of {
      Left _ -> False;
      Right compiled ->
        isRight (Check.checkClosed (Compiler.compiledTerm compiled)) &&
        TargetType.alphaEq (Compiler.inferredType compiled) (XCon "MLFCallStack" [])
    };
  checkManagedTarget :: IO ();
  checkManagedTarget = case managedTargetCompilation of {
    Left error -> do { putErr (Compiler.prettyError error ++ "\n"); exitWith 1 };
    Right _ -> checkStructural "managed method evidence passes target checker" managedTargetCheck
  };
  locatedIdentityInference :: Bool;
  locatedIdentityInference =
    let {
      identityType = SForall Flexible "a" SBottom (SArrow (STVar "a") (STVar "a"));
      plain = SAnn (SLam "x" Nothing (SVar "x")) (SAnnotation [] identityType);
      located = SAnn
        (SLam "x" Nothing (SCallSite "x" (SourceSpan "main" "Example" "Example.hs" 1 7 1 8) (SVar "x")))
        (SAnnotation [] identityType)
    } in case Compiler.compileExprWithPrelude NoImplicitPrelude plain of {
      Left _ -> False;
      Right before -> case Compiler.compileExprWithPrelude NoImplicitPrelude located of {
        Left _ -> False;
        Right after -> TargetType.alphaEq (Compiler.inferredType before) (Compiler.inferredType after)
      }
    };
  basicSourceChecks :: IO ();
  basicSourceChecks = do {
    checkStructural "location preserves ordinary inferred MLF type" locatedIdentityInference;
    checkManagedTarget;
    checkStack "local accessor spelling is not captured"
      "main = let { mlfCallStack = 42 } in showInt mlfCallStack\n"
      ((:) "42" []) ((:) "CallStack" []);
    checkStack "unsigned does not infer stack" (leaf ++ "unsigned x = leaf x\nmain = textFromChars (prettyCallStack (unsigned 0))\n")
      ((:) "leaf," ((:) "CallStackCase.hs:7:14" [])) ((:) "unsigned," ((:) "callStack," []));
    checkStack "explicit no-stack boundary" (leaf ++ "signed :: Int -> CallStack\nsigned x = leaf x\nmain = textFromChars (prettyCallStack (signed 0))\n")
      ((:) "leaf," []) ((:) "signed," []);
    checkStack "explicit qualified forwarding" (leaf ++ "forward :: HasCallStack => Int -> CallStack\nforward x = leaf x\nmain = textFromChars (prettyCallStack (forward 0))\n")
      ((:) "leaf," ((:) "forward," [])) ((:) "callStack," []);
    ioReturn ()
  };
  customSourceChecks :: IO ();
  customSourceChecks = do {
    checkStack "custom fail sees method given" (probe ++ "custom :: HasCallStack => Probe Int\ncustom = fail \"failed\"\nmain = result custom\n")
      ((:) "fail," ((:) "custom," [])) ((:) "callStack," []);
    checkStack "patterned do carries its own origin" (probe ++ "data Optional a = Missing | Present a\npatterned :: HasCallStack => Probe Int\npatterned = do { Present x <- pure Missing; pure x }\nmain = result patterned\n")
      ((:) "a do statement," ((:) "patterned," [])) ((:) "fail," []);
    checkStack "qualified reference uses occurrence name"
      ("import qualified MLF.Primitive as P\n" ++ (probe ++ "main = result (P.fail \"failed\" :: Probe Int)\n"))
      ((:) "fail," []) ((:) "P.fail," []);
    checkStack "qualified expression annotation has its own frame"
      (probe ++ "main = result ((fail :: HasCallStack => [Char] -> Probe Int) \"failed\")\n")
      ((:) "fail," ((:) "an expression type signature," [])) ((:) "<generated>" []);
    checkStack "annotated expression does not propagate through unsigned binding"
      (probe ++ "main = let { unsigned = (fail :: HasCallStack => [Char] -> Probe Int) } in result (unsigned \"failed\")\n")
      ((:) "fail," ((:) "an expression type signature," [])) ((:) "unsigned," []);
    ioReturn ()
  };
  negativeSourceChecks :: IO ();
  negativeSourceChecks = do {
    checkRejected "managed constraint has zero arguments" "bad :: HasCallStack Int => Int\nbad = 0\nmain = bad\n";
    checkRejected "managed constraint cannot be superclass" "class HasCallStack => C a where { c :: a -> Int }\nmain = 0\n";
    checkRejected "managed constraint cannot be instance context" "class C a where { c :: a -> Int }\ninstance HasCallStack => C Int where { c x = x }\nmain = 0\n";
    checkRejected "method result remains type checked" ("data Box a = Box a\ninstance Functor Box where { fmap f (Box x) = Box (f x) }\ninstance Applicative Box where { pure = Box; (<*>) (Box f) (Box x) = Box (f x) }\ninstance Monad Box where { (>>=) (Box x) f = f x }\ninstance MonadFail Box where { fail message = Box 42 }\nmain = 0\n");
    ioReturn ()
  };
  sourceChecks :: IO ();
  sourceChecks = do {
    basicSourceChecks;
    customSourceChecks;
    negativeSourceChecks;
    putStrLn "call-stack evidence: focused checks passed"
  };
  main :: IO ();
  main = do {
    structuralChecks;
    count <- getArgCount;
    if count == 0 then sourceChecks
    else do {
      mode <- getArg 0;
      if eqString mode "--structure" then ioReturn ()
      else if eqString mode "--basic" then basicSourceChecks
      else if eqString mode "--custom" then customSourceChecks
      else if eqString mode "--negative" then negativeSourceChecks
      else if eqString mode "--target" then checkManagedTarget
      else sourceChecks
    }
  }

}
