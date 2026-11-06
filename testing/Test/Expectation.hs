-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Test.Expectation where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Test.Outcome as O;
  -- Reason is a stable diagnostic/oracle code, not a substring of stderr.
  -- Verified means an independent adapter oracle accepted the raw observation.
  -- Neither a nonzero exit nor a matching diagnostic alone is enough.
  data Expectation = Accept O.Phase | Reject O.Phase String Int | ExpectSignal O.Phase String Int;
  data Termination =
    Exit Int |
    Signal Int |
    Deadline |
    Interrupted |
    BadProtocol String |
    Infrastructure String |
    Unavailable String |
    Skip String;
  data Observation = Observation O.Phase Termination String Bool;
  validate :: Expectation -> Either String ();
  validate expected =
    case expected of {
      Accept _ -> Right ();
      Reject _ reason code ->
        if ((stringLength reason > 0) && ((code > 0) && (code <= 255)))
        then Right ()
        else Left "rejection requires a diagnostic code and a specific nonzero exit";
      ExpectSignal _ reason signal ->
        if ((stringLength reason > 0) && ((signal > 0) && (signal < 128)))
        then Right ()
        else Left "expected signal requires a diagnostic code and a specific signal"
    };
  phase expected =
    case expected of {
      Accept value -> value;
      Reject value _ _ -> value;
      ExpectSignal value _ _ -> value
    };
  match :: Expectation -> Observation -> O.Outcome;
  match expected (Observation actualPhase termination reason verified) =
    case validate expected of {
      Left error -> O.ProtocolError error;
      Right () ->
        case validObservation termination of {
          Left error -> O.ProtocolError error;
          Right () -> matchValid expected actualPhase termination reason verified
        }
    };
  matchValid expected actualPhase termination reason verified =
    case termination of {
      Deadline -> O.Timeout "observation exceeded its deadline";
      Interrupted -> O.Cancelled "observation was cancelled";
      BadProtocol error -> O.ProtocolError error;
      Infrastructure error -> O.InfrastructureError error;
      Unavailable error -> O.Unsupported error;
      Skip error -> O.Skipped error;
      _ ->
        if not (O.equalPhase (phase expected) actualPhase)
        then O.AssertionFailure "observation ended in the wrong phase"
        else if not verified
             then O.AssertionFailure "independent observation verifier failed"
             else case expected of {
                    Accept _ ->
                      case termination of {
                        Exit 0 -> O.Pass;
                        Signal signal -> O.Crash signal reason;
                        _ -> O.AssertionFailure "expected successful exit"
                      };
                    Reject wantedPhase wantedReason wantedCode ->
                      case termination of {
                        Exit code ->
                          if ((code == wantedCode) && eqString reason wantedReason)
                          then O.ExpectedRejection wantedPhase reason code
                          else O.AssertionFailure "rejection exit or diagnostic did not match";
                        Signal signal -> O.Crash signal reason;
                        _ -> O.AssertionFailure "expected a phase-specific rejection"
                      };
                    ExpectSignal _ wantedReason wantedSignal ->
                      case termination of {
                        Signal signal ->
                          if ((signal == wantedSignal) && eqString reason wantedReason)
                          then O.Pass
                          else O.Crash signal reason;
                        _ -> O.AssertionFailure "expected a specific verified signal"
                      }
                  }
    };
  -- Keep Boolean operations explicit for the foundation-only import closure.
  not value = if value then False else True;
  validObservation :: Termination -> Either String ();
  validObservation termination =
    case termination of {
      Exit code ->
        if ((code >= 0) && (code <= 255)) then Right () else Left "invalid observed exit code";
      Signal signal ->
        if ((signal > 0) && (signal < 128)) then Right () else Left "invalid observed signal";
      Unavailable reason -> nonemptyReason reason;
      Skip reason -> nonemptyReason reason;
      _ -> Right ()
    };
  nonemptyReason :: String -> Either String ();
  nonemptyReason reason =
    if (stringLength reason > 0)
    then Right ()
    else Left "skip/unsupported requires an auditable reason"
}
