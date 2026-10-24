-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Test.Outcome where {
  import MLF.Primitive;
  import Bootstrap.Types hiding (Phase);
  -- A rejection is meaningful only at the phase named by its independent oracle.
  data Phase = Setup | Source | TypeCheck | Target | Emission | Runtime | Validation | Cleanup;
  phaseName :: Phase -> String;
  phaseName phase =
    case phase of {
      Setup -> "setup";
      Source -> "source";
      TypeCheck -> "type";
      Target -> "target";
      Emission -> "emission";
      Runtime -> "runtime";
      Validation -> "validation";
      Cleanup -> "cleanup"
    };
  equalPhase left right = eqString (phaseName left) (phaseName right);
  data Outcome =
    Pass |
    AssertionFailure String |
    ExpectedRejection Phase String Int |
    Crash Int String |
    Timeout String |
    Cancelled String |
    ProtocolError String |
    InfrastructureError String |
    Unsupported String |
    Skipped String;
  successful :: Outcome -> Bool;
  successful outcome =
    case outcome of {
      Pass -> True;
      ExpectedRejection _ _ _ -> True;
      _ -> False
    };
  status :: Outcome -> String;
  status outcome =
    case outcome of {
      Pass -> "passed";
      AssertionFailure _ -> "assertion_failure";
      ExpectedRejection _ _ _ -> "expected_rejection";
      Crash _ _ -> "crash";
      Timeout _ -> "timeout";
      Cancelled _ -> "cancelled";
      ProtocolError _ -> "protocol_error";
      InfrastructureError _ -> "infrastructure_error";
      Unsupported _ -> "unsupported";
      Skipped _ -> "skipped"
    };
  message outcome =
    case outcome of {
      Pass -> "";
      ExpectedRejection _ reason _ -> reason;
      AssertionFailure reason -> reason;
      Crash _ reason -> reason;
      Timeout reason -> reason;
      Cancelled reason -> reason;
      ProtocolError reason -> reason;
      InfrastructureError reason -> reason;
      Unsupported reason -> reason;
      Skipped reason -> reason
    }
}
