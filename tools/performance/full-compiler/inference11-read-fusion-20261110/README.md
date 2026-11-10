# Ordinary inference11 read-fusion qualification and cohort

Status: correctness passed; the fixed real-compilation cohort does **not**
support a speedup. All four observations are retained. There was no automatic
retry, extra warm-up, removed observation, full90 continuation or native
fixed-point experiment.

## Frozen question

Source revision: `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`.
Compile the original inference library, including its original Graph:
11 modules, 515309 source bytes, 780 fresh inference groups. Five dependency
interfaces and objects are fixed: builtin, foundation, frontend, language-core,
xmlf. Their preparation is excluded. The measured boundary is the ordinary CLI
source-to-checked command, including startup, reads, checks, artifact encoding,
file writes and fresh query publication. It excludes LLVM and native linking.
This is not the full90 compiler-to-runnable endpoint or a GHC comparison.

A uses the original complete O2 producer. B uses a new complete ordinary O2
producer, with all 137 shared modules, four host modules and 13 executables built
normally. Its only production source changes are Graph's 54 saturated read
expansions and the officially derived single RawPrelude identity field in the
canonical builtin literal. The original check-candidate and fresh-literal gates
both passed; the actual 2220407-byte generated literal equals the canonical
source in full, and inverse identity replacement recovers the original literal.

- Candidate Graph SHA256:
  `fdb9e899392ac0068f9f11432d512d1168934455a6da733a10e7cabb52d19df3`.
- Candidate canonical SHA256:
  `c0d4205ebfe8fde9fddf7ab63442558ada389056916fa2fe41dfc94b90297be8`.
- Original executable SHA256:
  `6120355c75ea590cf37777f38b3f58a7df7ce6dbd6d0857788f4049124dc2642`.
- Candidate executable SHA256:
  `7b89000b35b6a086af14efc896eab414851e37e4e447d6c6679e10292941d943`.

The earlier synthetic Graph microbenchmark and ordinary code-shape evidence do
not substitute for this actual compilation result.

## Results, including the failed launch

Q01 failed after4.425634s before the controller or any compiler started. Its
launcher passed bare `python3` to `os.execv`, which does not search PATH. The
failed receipt/log remain local. The minimal absolute-Python correction was
independently reviewed, and a new Q02 was separately admitted.

Q02 is qualification only, excluded from the formal cohort. Once A then B:
107.052748211s and101.709313582s. Both produced raw-byte-identical mlfci, mlfco
and queries to the historical B2 reference, each with780 fresh groups and0
reuse. The phase completed in212.283030025s. This establishes actual compatibility
with the original f9 dependency artifacts; it is not a speed estimate.

C01 was independently admitted with a fixed ABBA order, no additional warm-up.
All four observations passed the same strict oracles:

| Position | Side | Wall seconds | wait4 user seconds | wait4 system seconds | Maximum individual RSS bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | A | 96.666402158 | 93.387880 | 3.584719 | 380092416 |
| 2 | B | 151.642281213 | 153.728915 | 4.775379 | 361897984 |
| 3 | B | 104.524868001 | 101.349673 | 3.233474 | 361631744 |
| 4 | A | 104.961783279 | 101.551000 | 3.548310 | 380182528 |

Predeclared descriptive statistics, using all observations:
- Candidate/base median ratio:1.27049275704582.
- Candidate/base geometric-mean ratio:1.2498750267268373.
- Two observations per side only. The large first-B variation prevents a robust
  general performance inference, but it cannot be removed to claim a win.
- The high-B observation also has higher recorded user CPU. No throttle,
  CPU-frequency, host-competition, ordinary GC or allocation measurements were
  collected. Its cause is unknown. Profile-build GC percentages cannot establish
  what happened in this ordinary observation.

C01 completed in462.612743171s under its600s phase cap; each compile was capped
at180s and the remaining phase time. Peak whole-scope RSS404623360 bytes, lowest
available host memory9194201088 bytes, lowest free disk48334249984 bytes, peak
output114877167 bytes. No guard was approached. All423 input pins,16 output pins
and finite runtime mappings were verified;22 commands completed with no terminal
live descendants, final outer sampled RSS was0, and both orchestration locks
were independently reacquired. Detailed safe values and receipt hashes are in
C01-summary.json. Q01 and Q02 have their own separate summaries.

## Protocol and correctness

- Q: once A then B, total420s. C: separately admitted ABBA, total600s.
- Original cross-session watchdog, per-command exact-child wait4 Runner, scope
  wrapper and two serial locks are reused. All authentication and oracles count
  against the phase budget, but are outside each target wall measurement.
- Original spec has eight length-prefixed fields. Only the cache directory is
  replaced per leg; inverse packing must exactly recover the original spec.
- Every target/query directory is new, with no previous target outputs.
- All three public artifacts must equal the historical B2 bytes in full.
  Complete query JSON must match, with780 fresh groups, no cached groups, no reuse
  and unique identities. An independent ordinary baseline show-crate checks all
  eleven module owners and five dependency identities/paths.
- No query-key normalization exists. A withdrawn early idea based on legacy
  Q.queryKey was incorrect for this route: current reports use G.nodeHash(rawNode),
  while executable identity belongs to session configuration. Cache generation
  indexes are not a cross-producer equality oracle.
- The new allowlisted runtime environment is explicit, not claimed identical to
  an unknown historical inherited LD tail. Both compilers, Python and the known
  mkdir/mv/rm/rmdir host commands have trusted-loader resolution and real-file
  hashes checked before/after. System preload is rejected if nonempty.
- GHC/package/build-object identities are retained as build provenance. Unused
  toolchain trees are not repeatedly scanned or claimed currently authenticated.
- Kernel caches are not cleared. Nothing here proves whole-OS immutability.

## Recovery and exact tested-source boundary

`run.py` is byte-for-byte the tested private controller
363067f5d136250bd382d9bfd77234882123e22acc2d8482dedcdc0aafcfd68e.
Its original working layout was a sibling directory to the frozen source and
candidate checkouts. Copy this tool directory into an equivalent experimental
workspace layout before adapting it; do not run it in this nested repository
location and assume paths will resolve.

The published `run-phase.sh` has exactly one portability change from tested
0f7aafbc...: the machine-specific shared-lock path becomes required environment
variable MLF_SPRINT_LOCK. **That published wrapper has not been executed.**
Do not call it the original tested file. The failed launcher's original digest,
private reviewed manifest digest and original documentation digest are recorded
in tested-source-hashes.json.

`workload.template.json` replaces the private workspace prefix with
`${WORKSPACE}` in paths and pin keys. It is a disclosure-safe inventory and
reconstruction aid, **not** the authenticated runtime workload. The tested
controller intentionally rejects a different workload hash. Do not remove its
checks merely to make the template run. When paths or rebuilt dependency bytes
change, regenerate a clearly identified workload/reference cohort, freeze all
new identities, review that adaptation, and rerun qualification before timing.
Preserve module ownership, dependency order, fresh target and all strict oracles.

The required candidate handoff contains exact source/producer/runtime directory
paths, outer/work/producer receipt hashes, approved canonical old/new identity
and file hash, and the executable path/hash. The controller rejects missing or
incomplete proof, arbitrary generated changes, mixed old objects and an unverified
builtin literal. C additionally binds exact successful Q receipts, controller
and launcher identities, input environment and runtime mappings.

Raw machine-path receipts, logs, query caches, object dumps, binaries and generated
artifacts are **only retained locally**, not in this public checkpoint. If those
files are lost, reconstruct both normal producers, the fixed dependencies and
reference artifacts from source, then perform a new qualification. The public
summaries are evidence indexes, not substitutes for absent raw data.

The full90 baseline remains unsuccessful on the MLF side under its original
600s guard. This slice does not revise that result. No successful compiler/GHC
speed ratio or full-compiler improvement is claimed.
