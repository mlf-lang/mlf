-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Tests.PRQuickMain where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Compiler as C;
  import qualified Bootstrap.X.Check as Check;
  import qualified Bootstrap.X.Parser as Parser;
  import qualified Bootstrap.X.Pretty as Pretty;
  import qualified Bootstrap.X.Syntax as X;
  import qualified Tests.IndependentCheck as Independent;
  import qualified Tests.IndependentType as IndependentType;
  -- Direct shared-source smoke entry. The legacy guest fixture is retained.
  -- Its dependency closure stays independent of the native campaign and drivers.
  fatal :: forall a. String -> IO a;
  fatal message =
    ioBind (putErr ("PR current-source smoke: " ++ (message ++ "\n"))) (\_ -> exitWith 1);
  require :: Bool -> String -> IO ();
  require condition message = if condition then ioReturn () else fatal message;
  right :: forall a. Either String a -> IO a;
  right value =
    case value of {
      Left message -> fatal message;
      Right result -> ioReturn result
    };
  accepted :: String -> String -> String -> IO ();
  accepted fixtures output name =
    do {
      let {
        file = (fixtures ++ ("/" ++ (name ++ ".emlf")))
      };
      source <- readFile file;
      result <-
        case C.compile file source of {
          Left error -> fatal (C.prettyError error);
          Right compiled -> ioReturn compiled
        };
      let {
        expected = XCon "Int" []
      };
      require (IndependentType.alphaEq (C.inferredType result) expected)
        (name ++ ": wrong inferred type");
      let {
        serialized = Pretty.prettyTerm (C.compiledTerm result)
      };
      target <- right (Parser.parseTerm (name ++ ".xmlf") serialized);
      currentType <- right (Check.checkClosed target);
      independentType <- right (Independent.checkClosed target);
      require (IndependentType.alphaEq currentType expected)
        (name ++ ": wrong checked target type");
      require (IndependentType.alphaEq independentType expected)
        (name ++ ": wrong independently checked target type");
      require (X.equalErased (X.erase target) (X.erase (C.compiledTerm result)))
        (name ++ ": serialized target changed erasure");
      writeFile (output ++ ("/" ++ (name ++ ".xmlf"))) (serialized ++ "\n");
      putStrLn ("PASS current-source accepted " ++ name)
    };
  rejected :: String -> String -> IO ();
  rejected fixtures name =
    do {
      let {
        file = (fixtures ++ ("/" ++ (name ++ ".emlf")))
      };
      source <- readFile file;
      expected <- readFile (fixtures ++ ("/" ++ (name ++ ".stderr")));
      case C.compile file source of {
        Left error ->
          do {
            require
              (case C.phase error of {
                 Inference -> True;
                 _ -> False
               })
              (name ++ ": wrong rejection phase");
            require (eqString (C.prettyError error ++ "\n") expected)
              (name ++ (": wrong rejection diagnostic: " ++ C.prettyError error))
          };
        Right _ -> fatal (name ++ ": rejected source was accepted")
      };
      putStrLn ("PASS current-source rejected " ++ name)
    };
  rejectTarget :: String -> Either String XType -> IO ();
  rejectTarget label result =
    case result of {
      Left message ->
        require (eqString message "application type mismatch")
          (label ++ (": wrong target rejection: " ++ message));
      Right _ -> fatal (label ++ ": malformed target was accepted")
    };
  progress :: String -> String -> IO ();
  progress output stage = writeFile (output ++ "/progress.log") (stage ++ "\n");
  main :: IO ();
  main =
    do {
      count <- getArgCount;
      require (count == 2) "expected FIXTURE-DIRECTORY OUTPUT-DIRECTORY";
      fixtures <- getArg 0;
      output <- getArg 1;
      progress output "Checking accepted polymorphic-let";
      accepted fixtures output "polymorphic-let";
      progress output "Checking accepted impredicative-self-application";
      accepted fixtures output "impredicative-self-application";
      progress output "Checking rejected monomorphic-mismatch";
      rejected fixtures "monomorphic-mismatch";
      progress output "Checking rejected invalid-universal-annotation";
      rejected fixtures "invalid-universal-annotation";
      progress output "Checking malformed target";
      source <- readFile (fixtures ++ "/malformed-before-effects.xmlf");
      target <- right (Parser.parseTerm "malformed-before-effects.xmlf" source);
      rejectTarget "current checker" (Check.checkClosed target);
      rejectTarget "independent checker" (Independent.checkClosed target);
      progress output "Completed all five current-source cases";
      putStrLn "PASS current-source malformed target";
      putStrLn "PR current-source smoke passed: 2 accepted, 2 rejected, 1 malformed target."
    }
}
