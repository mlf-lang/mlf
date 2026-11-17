# First prefix-rejection reasons: diagnostic archive

This is an isolated GHC-only diagnostic on baseline fc300bc9fdc389b585cbef0630fc8915d53e89c5, not an optimization or a production patch. It classifies the first rejection witness of fallbackPrefixRejected, not every congruentExpansionMap failure or every internal hole.

The existing guard retains its ordered checks and short circuits. Reason 0 is the original False result; reason 1 is a repeated fresh-source mapping conflict; reason 2 is the first old-bottom / non-bottom-copy mismatch. Four strict scalar counters record completed demanded observations, with an explicit 1,000,000-call diagnostic cap. There is no graph encoding, size weighting, per-event log or timing instrumentation.

## Finite evidence

The single O2 finite gate passed independent bounded checks: 14 cases, 59 exact sidecars and a 52-byte stdout marker. Thirteen observations completed: 10 original-False, 1 conflict, 2 old-bottom-hole; the typed pending-spine exception did not increment counters. O0 was not run. Direct helper tests do not certify all real instantiate routes or arbitrary raw inputs.

The patch, helper, test Main and expected files here are byte-exact copies of tested source. The patch changes only Solver; add the separately supplied helper to a private source search root. The finite Main is distinct from the diagnostic CLI entry. These files require the pinned baseline's normal GHC host/facade modules and C support, not shape stubs or altered Prelude identities. No new public build recipe has been executed.

The diagnostic CLI entry used this small wrapper, not the finite Main:

    module Main where
    import MLF.Host.IO (runEntry)
    import qualified MLF.Entry.Emlf as Entry
    import qualified Prototype.PrefixReasons as Capture
    main :: IO ()
    main = do
      runEntry Entry.main
      Capture.writeCapture "prefix-reasons.tsv"

## One independently checked real diagnostic

One fresh 96-home ordinary GHC producer executed the original CommonFoundationRoot + Foundation15 --type workload. The raw record is 17,801 completed observations: 3,270 original-False, 4,045 mapping-conflict and 10,486 internal-hole first witnesses. Independent recomputation passed bounded actual-output and numerical checks. This is not a formal-isolation benchmark.

The original CLI stdout was required to be Bool plus LF, with empty target stderr. The 37 compiler warnings were retained separately; target stderr was empty. The controller budget was 240 seconds aggregate compilation including two C steps, 90 seconds for the single target, 400 seconds whole stage and 4 GiB address space. Elapsed budget values are not performance samples.

Counts do not establish cost shares, removable work, speedup or eligibility of a new graft algorithm. NOINLINE and compiler options limit common transformations but do not prove one event per arbitrary source invocation. Exceptions before/during reason evaluation do not count; interruption after the atomic increment is not rolled back, so an interrupted run cannot support complete-count conclusions. Cooperative locks do not establish formal physical-resource isolation. No native, A/B, production or optimization qualification follows.
