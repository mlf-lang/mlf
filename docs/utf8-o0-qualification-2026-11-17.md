# Independent UTF8 O0 qualification

## Status before the first run

UNTESTED CANDIDATE. Source review and pure controls are not actual interpreter
qualification. This branch is independent of PR #51 and main, and is not a
merge-ready result. Its push workflow does not cancel another workflow.

Fixed production baseline: 09e3fb20d7105da53639f6c8817a6a11d4f01ec1.
The fresh producer belongs to the qualification commit, not literally the
baseline commit. The full tracked source map is checked against the baseline;
only the explicit test, qualification tooling, document and workflow paths may
differ. Production modules, host/runtime inputs, build driver, configurations
and verifier helpers stay byte-identical.

## Failure being investigated

The previous db7edc O0 direct artifact showed the expanded forward interpreter
batch reaching its individual 120-second limit after the host batch passed.
This was not the aggregate 600-second deadline. The captured owned-tree guard
did reach successful cleanup. Empty output does not establish whether parsing,
typechecking, initialization, evaluation or buffering caused the delay.

Retain the expanded-v1 generator and all its tests. The loop-v2 successor changes
only the fixture main binder and appends a fixed monomorphic argument getter,
one recursive IO loop and an ordered data table. It has one syntactic runCase
call point. Full inverse reconstruction must recover the exact original
Length.hs bytes and blob pin. Forward and reverse tables contain all 25
interpreter vectors. A timeout is not addressed by enlarging its limit.

## Actual coverage required

The existing managed route must run the complete UTF8 target:
133 physical commands, 112 original logical vectors (29 host, 25 interpreter,
29 native O0, 29 native O2), 12 original demand cases, 12 direct runtime cases,
four actual batch executions (host/interpreter in two directions) and 100
byte-range projections. The three interpreter demand cases remain fresh
processes. Two interpreter batches are not 25 fresh-process-isolated vectors,
and forward/reverse agreement is not a universal cache, state or GC proof.
Neither this target nor its qualified receipt implies full direct CI passed.

## Fixed limits and process ownership

One Ubuntu 24.04 job, maximum 60 minutes; official deb12 GHC 9.14.1 archive
306812040 bytes and SHA256
60f7ab75f28df892729fbaff3a54f58ee3ad7e731929f1b2f3eb0208f73de841.
No producer cache or artifact from another source head is accepted.
The original full bootstrap build and producer authentication are used.

Work ceilings: pure/synthetic admission 120 seconds, install 900 seconds,
full O0 bootstrap 1200 seconds, UTF8 source/target qualification 625 seconds.
Each outer stage adds at most 30 seconds for its root to handle cancellation,
then 10 seconds of owned cleanup, and a final 5-second hard-failure margin.
The internal managed target keeps 600 work / 10 cleanup / 625 outer seconds.
Artifact upload has a separate 5-minute ceiling.

Each executed child receives a 6 GiB address-space limit. Owned RSS <=5 GiB,
free disk >=4 GiB and combined stage captures <=128 MiB are sampled checks,
not instantaneous hard guarantees. Privileged installer children may alter
their own inherited limits. No performance measurements or machine-wide
isolation are claimed. Only install runs as root so its root-owned apt/make
descendants can be safely reaped; build and target are unprivileged.

Signal only an unreaped, rechecked direct child through a pidfd. Subreaper
adoption includes descendants with new sessions and nested subreapers. Cleanup
must reach ECHILD. Exit zero with live descendants is failure even if they are
later cleaned up. On a resource/deadline/cancel trigger, first notify the root
and allow its managed shutdown, then enforce bounded cleanup. Any forced
cleanup prevents qualification. SIGKILL of the outer owner or GitHub's final
job kill cannot be certified as contained; missing receipts/artifacts mean
incomplete evidence, never success.

## Retained evidence

Upload all stage receipts/captures, installation hash and cleanup evidence,
the full fresh producer directory including binaries/objects/commands/logs,
source maps before/after, managed guard, worker/original/qualification
receipts, generated fixtures, all actual captures and synthetic cleanup
readiness/terminal records. Local synthetic budgets are explicitly reduced;
they do not claim the production limits or interpreter work executed.

## Run 01 evidence and run 02 maintenance

Run 44070388971 at 7c03e9ad7da52e40e685785f36ca529c252cfec9 is retained
as FAILED, not retroactively passed. Its pure stage passed 46 tests in each of
normal and optimized modes. Installation finished its root command with status
0 in 140.939 seconds, validated the official archive and GHC 9.14.1, and reached
ECHILD without signals. Its root and three naturally exited adopted children
all had status 0. The stage nevertheless failed its over-strict single-reap
predicate. No producer build or actual UTF8 target ran.

Run 02 uses a new independent branch, still one direct child of the fixed
09e3 baseline, preserving the failed run and its branch. Only root install may
accept extra naturally exited owned children. Every ledger PID must be unique
and positive, include the root exactly once, and have integer exit status 0;
any signal, cancellation, error, survivor or missing ownership/ECHILD proof
rejects success. Pure, build and UTF8 retain the single-root restriction.
No process selection, supervisor, resource limit or time budget is relaxed.

Ten actual synthetic owner cases include naturally exited adopted status 0,
status 7, non-install adopted 0, and a live TERM-ignoring install orphan.
Install-branch synthetic tests only stub the UID check inside an unprivileged
harness. They do not install packages or qualify real root operation. Separate
pure ledger negatives reject identity, duplicate/missing PID, status, phase
and incomplete cleanup errors. These new tests and the candidate loop remain
UNTESTED until this exact new branch's CI provides their actual results.
