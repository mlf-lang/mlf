-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Tests.PRQuickMain where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Compiler as C;
  import qualified Bootstrap.Std as S;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Parser as Parser;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Tests.IndependentCheck as Independent;
  import qualified Tests.IndependentType as IndependentType;
  import qualified Test.Assert as A;
  import qualified Test.Case as Case;
  import qualified Test.Runner as Runner;
  -- Direct shared-source smoke entry. The legacy guest fixture is retained.
  -- Its dependency closure stays independent of the native campaign and drivers.
  fatal :: forall a. String -> IO a;
  fatal message =
    ioBind (putErr ("PR current-source smoke: " ++ (message ++ "\n"))) (\_ -> exitWith 1);
  right :: forall a. Either String a -> A.Test a;
  right = A.right (\message -> message);
  accepted :: String -> String -> String -> A.Test ();
  accepted fixtures output name =
    do {
      let {
        file = fixtures ++ ("/" ++ (name ++ ".emlf"))
      };
      source <- A.liftIO (readFile file);
      result <- A.andThen (A.liftIO (C.compile file source)) (A.right C.prettyError);
      let {
        expected = XCon "Int" [];
        serialized = Pretty.prettyTerm (C.compiledTerm result)
      };
      A.assert (IndependentType.alphaEq (C.inferredType result) expected) "wrong inferred type";
      target <- right (Parser.parseTerm (name ++ ".xmlf") serialized);
      currentType <- right (Check.checkClosed target);
      independentType <- right (Independent.checkClosed target);
      A.assert (IndependentType.alphaEq currentType expected) "wrong checked target type";
      A.assert (IndependentType.alphaEq independentType expected) "wrong independently checked target type";
      A.assert (X.equalErased (X.erase target) (X.erase (C.compiledTerm result)))
        "serialized target changed erasure";
      A.liftIO (writeFile (output ++ ("/" ++ (name ++ ".xmlf"))) (serialized ++ "\n"))
    };
  rejected :: String -> String -> A.Test ();
  rejected fixtures name =
    do {
      let {
        file = fixtures ++ ("/" ++ (name ++ ".emlf"))
      };
      source <- A.liftIO (readFile file);
      expected <- A.liftIO (readFile (fixtures ++ ("/" ++ (name ++ ".stderr"))));
      compilation <- A.liftIO (C.compile file source);
      case compilation of {
        Left error -> do {
          A.assert (case C.phase error of { Inference -> True; _ -> False }) "wrong rejection phase";
          A.equal eqString (\message -> message) "wrong rejection diagnostic" expected (C.prettyError error ++ "\n")
        };
        Right _ -> A.fail "rejected source was accepted"
      }
    };
  rejectTarget :: String -> Either String XType -> A.Test ();
  rejectTarget label result =
    case result of {
      Left message -> A.equal eqString (\text -> text) (label ++ ": wrong target rejection")
        "application type mismatch" message;
      Right _ -> A.fail (label ++ ": malformed target was accepted")
    };
  malformed fixtures =
    do {
      source <- A.liftIO (readFile (fixtures ++ "/malformed-before-effects.xmlf"));
      target <- right (Parser.parseTerm "malformed-before-effects.xmlf" source);
      rejectTarget "current checker" (Check.checkClosed target);
      rejectTarget "independent checker" (Independent.checkClosed target)
    };
  progress :: String -> String -> IO ();
  progress output stage = writeFile (output ++ "/progress.log") (stage ++ "\n");
  registry fixtures output =
    let {
      entry id label body = Case.test ("source-smoke/" ++ id) label ["family:source-smoke"]
        (A.andThen (A.liftIO (progress output ("Checking " ++ label))) (\_ -> body))
    } in
    [ entry "polymorphic-let" "accepted polymorphic-let" (accepted fixtures output "polymorphic-let")
    , entry "impredicative-self-application" "accepted impredicative-self-application"
        (accepted fixtures output "impredicative-self-application")
    , entry "monomorphic-mismatch" "rejected monomorphic-mismatch" (rejected fixtures "monomorphic-mismatch")
    , entry "invalid-universal-annotation" "rejected invalid-universal-annotation"
        (rejected fixtures "invalid-universal-annotation")
    , entry "malformed-before-effects" "malformed target" (malformed fixtures)
    ];
  observe result = do {
    path <- getEnv "MLF_SOURCE_SMOKE_CASE_REPORT";
    if eqString path "" then ioReturn () else do {
      prior <- readFile path;
      writeFile path (prior ++ (Runner.resultJson result ++ "\n"))
    };
    case result of {
      Runner.Result entry (Right ()) -> putStrLn ("PASS current-source " ++ Case.name entry);
      Runner.Result entry (Left failure) -> putErr
        ("PR current-source smoke: " ++ (Case.name entry ++ (": " ++ (A.describe failure ++ "\n"))))
    }
  };
  moreArgs :: Int -> Int -> IO ([] String);
  moreArgs index count =
    if index >= count then ioReturn []
    else do {
      arg <- getArg index;
      rest <- moreArgs (index + 1) count;
      ioReturn ((:) arg rest)
    };
  main :: IO ();
  main =
    do {
      count <- getArgCount;
      if count < 2 then fatal "expected FIXTURE-DIRECTORY OUTPUT-DIRECTORY" else ioReturn ();
      fixtures <- getArg 0;
      output <- getArg 1;
      args <- moreArgs 2 count;
      let {
        cases = registry fixtures output
      };
      if S.null args
      then do {
        outcomes <- Runner.executeWith observe cases;
        if S.all Runner.passed outcomes then do {
          progress output "Completed all five current-source cases";
          putStrLn "PR current-source smoke passed: 2 accepted, 2 rejected, 1 malformed target."
        } else exitWith 1
      }
      else do {
        code <- Runner.run args cases;
        if code == 0 then ioReturn () else exitWith code
      }
    }
}
