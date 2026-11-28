-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Package.DependencyMode (Mode(..), Decision(..), name, json, line, emit) where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Package.Json as J;

  data Mode = Native | CheckedIR | Source | Unused;
  data Decision = Decision String Mode String;
  name :: Mode -> String;
  name Native = "native";
  name CheckedIR = "ir";
  name Source = "source";
  name Unused = "unused";
  json :: Decision -> J.Json;
  json (Decision dependency mode reason) = J.object
    [(,) "dependency" (J.str dependency), (,) "mode" (J.str (name mode)), (,) "reason" (J.str reason)];
  -- Keep each decision on one line, including paths with embedded control characters.
  line :: Decision -> String;
  line (Decision dependency mode reason) =
    "dependency " ++ J.quoteAt dependency 0 ++ ": " ++ name mode ++ " (" ++ J.quoteAt reason 0 ++ ")";
  emit :: Decision -> IO ();
  emit decision = putErr (line decision ++ "\n")
}
