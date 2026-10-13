module StateRuntime (stateRuntimeTests) where

import Control.Monad (unless)
import Data.List (isInfixOf)
import Backends (Backends, Entry (..), Input (..))
import qualified Backends as B
import qualified MLF.Compiler as C
import MLF.LLVM (emitLLVM)
import StateCases (stateRuntimeCases)
import StateTypes (checkedStateSource)

stateRuntimeTests :: Backends -> [(String,IO ())]
stateRuntimeTests backends =
  [("ST runtime: " ++ label, do
      result <- checkedStateSource source
      -- This fixture crosses the bounded direct-worker path into the explicit
      -- runtime stack. Guard activation separately from the output oracle.
      if label == "bounded-non-tail-state-worker" then do
        llvm <- either fail pure (emitLLVM (C.compiledTerm result))
        unless (all (`isInfixOf` llvm)
          ["define private ptr @mlf.st.worker.", "icmp eq i64 %st.fuel, 0",
           "call ptr @mlf_execute_st_lazy(", "call ptr @mlf_st_new_array(",
           "call ptr @mlf_st_read_array(", "call ptr @mlf_st_write_array("])
          (fail "bounded direct state execution was not exercised")
      else pure ()
      if label `elem` ["bounded-tail-state-worker", "bounded-mixed-tail-state-worker"] then do
        llvm <- either fail pure (emitLLVM (C.compiledTerm result))
        unless ("musttail call ptr @mlf.st.worker." `isInfixOf` llvm &&
                "(i64 %st.fuel," `isInfixOf` llvm)
          (fail "state tail transfer did not preserve its continuation budget")
      else pure ()
      if label == "single-use-action-alias" then do
        llvm <- either fail pure (emitLLVM (C.compiledTerm result))
        unless ("call ptr @mlf_st_read_array(" `isInfixOf` llvm &&
                not ("call ptr @mlf_execute_st_lazy(" `isInfixOf` llvm))
          (fail "single-use action alias fell back to generic execution")
      else pure ()
      observed <- B.execute backends ProgramEntry (Input "" False) (C.compiledTerm result)
      let outcomeMatches = case (failure,B.outcome observed) of
            (Nothing,Right ()) -> True
            (Just expectedError,Left actual) -> show actual == expectedError
            _ -> False
      unless (outcomeMatches && B.output observed == expected && null (B.stderrOutput observed) &&
              null (B.remaining observed)) (fail (show observed)))
    | (label,source,expected,failure) <- stateRuntimeCases]
