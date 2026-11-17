# Independent header/candidate O0 qualification plan

This workflow is confined to the exact preparation push branch
`codex/pr51-header-candidate-o0-qualification-20261117-run02`. It never modifies or cancels PR #51 or main,
and it is not part of the planned PR promotion.

## Source and compiler boundary

The qualification commit must be one direct child of
`8d80e0fb1dbf4e6d40c53de35b727674b5c74817`. The complete tracked checkout is
verified before and after admission and each target. The allowlist contains
only the explicit test/oracle and qualification-tool/workflow/document changes;
all production and build-driver inputs remain byte/mode-identical. The fresh
O0 producer belongs to the actual qualification commit. It is not claimed to
be the literal binary from the baseline commit.

Official GHC 9.14.1 deb12 bindist: 306812040 bytes,
SHA256 `60f7ab75f28df892729fbaff3a54f58ee3ad7e731929f1b2f3eb0208f73de841`.
Installation is serial, with no restored build cache. The original known-good
installation/owned-child ledger contract is retained, including permitted
successful adopted children only for the root installer.

## Budgets and independent results

One Ubuntu 24.04 job has a 60-minute ceiling. Work allowances:
pure/synthetic 120 seconds, official installation 900, fresh build 1200,
header-only 120, candidate-only 625. Each phase retains the existing 30-second
root-notification grace and 10-second cleanup plus its final hard-stop margin.
Sampled owned-tree RSS 5GiB, per-process address space 6GiB, disk floor 4GiB,
combined stage capture cap 128MiB are unchanged. Sampling is not a continuous
or machine-wide isolation claim. Artifact upload has a separate 5-minute step
bound within the job ceiling.

Candidate retains its 600 work/10 cleanup/625 outer/25 cancellation-grace
contract and original 120-second vector limits. Header's complete preparation,
authentication and narrow compile/run fit within its separate 120-second
phase or fail; the budget is not a promise it will finish.

Header runs the two actual generated fixtures against current authenticated
GHC objects and the pinned historical formatter component. It is not the full
native-library suite or a complete historical compiler. Candidate runs all
its original host/native coverage and four real batch captures with 96 byte
projections, not 24 isolated interpreter processes or the full direct suite.

Once the producer succeeds, each target runs even if the other fails, unless
the job is cancelled. Original errors, outputs, actual build artifacts,
source mappings and owned-tree cleanup receipts are retained with always()
upload. No success is inferred from a printed banner, host-only test or pure
admission. All actual result claims require the relevant external exit status,
raw captures, complete source/artifact chain and final cleanup evidence.

The work and per-vector limits have not been relaxed to disguise the original
O0 candidate timeout. PR promotion and its exact-head full CI remain separate
from this narrow qualification.

## Retained first attempt and exact second-attempt delta

Run 44122608963 at 8bf86d65e1997d792fa262dbd90a971ba02069ce failed while compiling the new HeaderNamingOracle action bindings: GHC-39999 reported ambiguous Monad/Applicative constraints. Neither complete Header lane ran. This attempt adds only `controls :: IO ()` and `historicalControls :: IO ()` to that oracle, retaining every expected value and historical formatter byte. A pure regression reverses precisely those two signatures to the failed oracle's original Git blob and SHA256, with malformed-signature and unrelated-mutation negatives. The Header adapter inventory increases from 15 to 16 tests, making 82 tests per Python mode. Fresh compilation and actual two-lane execution remain required on this exact second-attempt head.

The first attempt's candidate-only target independently passed with 263 physical commands, 272 logical observations, all 248 native cases, both complete original host banners and seven demand checks, and four batches with 96 raw-byte projections. Its managed target took 272.669 seconds under the unchanged 600-second work limit. This does not prove 24 fresh interpreter processes equivalent and does not qualify any later producer. Original failure evidence remains local-only pending destination approval; this document does not contain raw logs or binaries. The second attempt retains the same budgets and reruns the whole isolated qualification without cancelling or changing PR #51 or main.
