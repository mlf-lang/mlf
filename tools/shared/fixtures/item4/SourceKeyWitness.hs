{-# LANGUAGE OverloadedStrings #-}
-- Test oracle: replay the canonical input from the parsed plan and actual
-- predecessor interfaces. Fingerprint records cannot supply their own key.
module SourceKeyWitness (sourceKeys, fullKey, fingerprint) where

import Prelude
import Control.Monad (foldM)
import qualified Bootstrap.CrateQuery as Q
import qualified Bootstrap.InferenceUnit as I
import qualified Bootstrap.Map as M
import qualified Bootstrap.SourceInference as S
import qualified Bootstrap.Separate as U
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as B
import qualified MLF.Primitive as P

expect x = case x of T.Left msg -> fail (B.unpack msg); T.Right value -> pure value
fingerprint text = P.byteArrayFromString text >>= P.byteArrayDigest
fullKey keys digest = case lookup digest keys of
  Just key -> pure key
  Nothing -> fail ("no canonical source input for " ++ B.unpack digest)

sourceKeys crate original imports protected final = do
  compiler <- P.getExecutablePath >>= P.fileDigest
  plan <- expect (S.initializeProtection original protected)
  types <- expect (foldM I.mergeExternal M.empty (concatMap U.unitBindings imports))
  initial <- expect (S.initialContracts plan types protected)
  inventory <- expect (Q.prepareData (S.planData plan))
  let step (previous, keys) names = do
        group <- expect (S.prepareGroup plan previous names)
        let ds = Q.requiredDataIn inventory (S.groupMembers group)
                   (S.groupBindings group ++ S.groupCandidateBindings group)
            input = Q.sourceQueryKey crate compiler group previous ds
            added = M.filterWithKey (\n _ -> n `elem` names) final
        digest <- fingerprint input
        pure (M.union P.compareString added previous, (digest,input):keys)
  snd <$> foldM step (initial, []) (S.planGroups plan)
