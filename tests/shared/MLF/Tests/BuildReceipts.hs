-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module MLF.Tests.BuildReceipts where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Package.Json as J;
  import qualified Tests.BuildReceipts as R;
  rejectValue :: J.Json -> IO ();
  rejectValue value = putStrLn (J.render (R.appendSuiteBuildReceipt (J.set "suite_builds" value J.empty) (J.num 7)));
  good :: IO ();
  good = do {
    let { first = R.appendSuiteBuildReceipt J.empty (J.num 0) };
    let { second = R.appendSuiteBuildReceipt (J.set "suite_builds" first J.empty) (J.num 7) };
    putStrLn (J.render first);
    putStrLn (J.render second);
    if R.preparedSuiteTargets J.empty ((:) "core-crates" [])
      then panic "missing prepared map accepted" else putStrLn "missing map builds";
    let { one = J.set "prepared_suite_targets" (J.set "core-crates" (J.str "retained") J.empty) J.empty };
    if R.preparedSuiteTargets one ((:) "core-crates" [])
      then putStrLn "existing map reused" else panic "existing prepared map ignored";
    if R.preparedSuiteTargets one ((:) "core-crates" ((:) "core-solver" []))
      then panic "missing target accepted" else putStrLn "partial map builds"
  };
  main :: IO ();
  main = do {
    which <- getArg 0;
    if eqString which "first-and-second" then good
    else if eqString which "reject-null" then rejectValue J.Null
    else if eqString which "reject-object" then rejectValue J.empty
    else if eqString which "reject-string" then rejectValue (J.str "malformed")
    else if eqString which "reject-prepared-null"
      then if R.preparedSuiteTargets (J.set "prepared_suite_targets" J.Null J.empty) ((:) "core-crates" [])
        then putStrLn "bad" else putStrLn "bad"
      else panic "unknown receipt test case"
  }
}
