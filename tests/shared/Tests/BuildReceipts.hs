-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Tests.BuildReceipts where {
  import MLF.Primitive;
  import Bootstrap.Types;
  import qualified Bootstrap.Std as S;
  import qualified Package.Json as J;
  -- These are the actual production operations, not copied source fragments.
  appendSuiteBuildReceipt :: J.Json -> J.Json -> J.Json;
  appendSuiteBuildReceipt saved receipt =
    J.Array (S.snoc (J.values (J.getOr "suite_builds" (J.Array []) saved)) receipt);
  preparedSuiteTargets :: J.Json -> [] String -> Bool;
  preparedSuiteTargets saved targets =
    S.all (\target -> J.has target (J.getObject "prepared_suite_targets" saved)) targets
}
