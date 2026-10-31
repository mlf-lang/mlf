# Darwin process launch (S1)

This candidate reduces the cost of repeatedly launching cache-publication
commands from a GHC-hosted compiler. `CrateQuery.writeCache` still writes the
temporary file and runs the same `/bin/mv -f` command. No inference, validation,
query publication, or target work is removed.

The production change adds 24 lines to `runtime/mlf_system.h`. On Darwin, a
command with inherited cwd and all three inherited standard streams first uses
`posix_spawnp`. It inherits a valid runner-owned process group, or creates the
child-owned group required by the existing unsupervised path. Attribute/spawn
failure falls back to the existing `fork`/`execvp`, including executable text
without a shebang. The original wait, status, timeout, reaping, and readiness
code remains in place. The non-Darwin source path is unchanged.

The API distinction matters: a failed spawn leaves its PID unspecified. The
candidate uses a separate temporary PID and never treats a failed call's value
as a child. See Apple's [posix_spawn manual](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/posix_spawn.2.html).

## Discovery and confirmation

Performance baseline: `1d16f351` (its production compiler sources equal
`fffb66a3`). Both producers are authenticated ordinary GHC 9.14.1 `-O2` builds,
with the same `-fpedantic-bottoms -fno-state-hack` options. Native shape outputs
use serial, ordinary Clang `-O2`, with fixed primitive/runtime dependencies.

The shape discovery window contains one fixed ABBA/BAAB block per shape,
two fresh native compilations per side, and three independent executable
outputs per compilation. All twelve builds passed fresh/raw-byte comparisons;
all thirty-six executable checks passed. These are exploratory medians, with
no confidence claim.

| n = 512 shape | Fresh groups | Before, seconds | Spawn, seconds | Time reduction |
|---|---:|---:|---:|---:|
| Independent top-level functions | 515 | 7.581 | 4.836 | 36.21% |
| Inferred dependency chain | 515 | 8.682 | 5.701 | 34.33% |
| Local functions in one group | 3 | 4.967 | 4.957 | 0.20% |

The separate real-compiler discovery block had medians 75.771 / 69.826 seconds,
with system CPU 5.893 / 1.749 seconds. This supports the process-launch cost
explanation but is not the confirmation data.

The primary task is the retained **15-module, 711-fresh / 0-reused** compiler
workload, frozen at target source `d96f67726599fa4e21f236462886106434c8e417`.
Its endpoint is checked MLF/xMLF output. It is distinct from the shapes' full
source-to-native endpoint, and is not a new GHC-versus-MLF language ranking.
The older 14-module/544-group workload is not substituted for this one.

The independent confirmation protocol freezes six four-leg blocks before the
first sample, in order `BAAB BAAB ABBA BAAB ABBA ABBA` (seed 20261031). Every
leg starts with an empty target query directory and compares both checked
artifacts as raw bytes against the retained independent reference. The ordered
group sequence is also compared. Discovery timings are excluded.

For each block, average the two adjacent-pair log wall ratios B/A. The primary
ratio is the exponential of the mean of the six block effects. SciPy 1.18.1
provides the ordinary two-sided t interval; the gain interval reverses the
exponentiated endpoints. The frozen acceptance rule requires a point gain of
at least 2%, a positive nominal 95% gain lower bound, and positive point gains
in both execution directions. No samples are added for significance.

Confirmation result: **accepted**. The paired block estimate reduces wall time
by **7.040%**, with a nominal 95% interval of **6.087% to 7.984%**. ABBA and BAAB
point gains are 6.663% and 7.416%. All six blocks and 24 fresh/raw-qualified legs
completed, without exclusions or replacement samples. Descriptive wall
medians are 72.520 / 67.052 seconds; system CPU medians are 5.353 / 1.617 seconds.
The ratio of those medians is a different estimand from the paired primary
estimate. Full timing values and evidence identities are in [result.json](result.json).

These comparisons concern fixed binaries, inputs and one local Mac session.
Six blocks do not establish independence, and the nominal interval does not
cover the entire history of candidate selection. Of 131 ordinary GHC objects,
129 are byte-identical. The two host objects have identical `__text` sections;
their string differences show build-source paths. Linked layout can still
differ. No claim about other platforms or layouts follows from these results.

## Retained controls and measurement boundary

`run_controls.py --full` reuses the complete old Darwin readiness suite. Its
existing fault expectations are unchanged; an explicit test-only failing
spawn adapter exercises the old fallback traces. Added source admission in
the C4 gate accepts only the reviewed complete header hashes and verifies an
exact inverse to the previous header; other dependency checks remain intact.

The controls include 20 new and 27 retained syscall/fault/order cases, 12
additional real-command parity executions, 40 retained transport executions,
four timeout/descendant cases, and ten ordinary Clang native-ABI cases. Two
GHC diagnostic relinks use the ordinary non-Main objects: the retained
readiness test and the new spawn/environment/process-group/FD test. The latter
observes 28 successful spawns, two fork paths, and stable descriptor counts.
These diagnostics are not timing samples.

The final review also runs `run_inherited.py`: 22 real cases across the two
ordinary host objects cover closed standard streams, close-on-exec standard
streams, inherited and close-on-exec extra descriptors, ignored/caught/blocked
signals, and unset/empty PATH. All pass. This supplemental qualification adds
no performance samples and does not change the frozen production candidate.

The complete existing validation-reuse, P1/P2/P3, A1, fingerprint-fusion, Map,
query-encoding, and C4 nine-file gates are retained and run on the candidate.
Expectations come from their frozen controls and previous implementations.

`compare.py` uses the unchanged exact-child `Runner`, with its existing 5 GiB
disk-free floor, 3 GiB available-memory floor, 5 GiB sampled process-group RSS
guard, 512 MiB active-leg work bound, and 600-second real-target timeout.
On macOS, RSS is sampled and a hard address-space bound is not enforced.
`with_scope.py` keeps nested helpers in the runner-owned process group on both
sides; its common Python/exec startup is included in timing. This protocol
change is recorded, and timings from older protocols are not pooled.

Only one compiler runs at a time. Preparation, authentication and output
checks are outside timing. After each complete block, the controller records
query-cache byte/hash inventories and removes only those disposable caches.
It retains raw checked outputs, query reports and command receipts. The
retained-output bound between blocks is 2 GiB; a four-leg active block has the
separate existing per-leg bounds. All failures remain in their original
directories, with no replacement samples. A control output-name collision and
an obsolete historical generator pin were corrected before any measured
samples in their respective failed attempts.

## Reproduction entry points

Use separately authenticated baseline and candidate source/producer trees.
The comparison config names these trees, the existing workload manifest,
independent raw references, complete control receipts, limits and fixed block
schedule. Each run archives its exact config, controller and frozen plan.

```sh
python3 -B tools/performance/process-spawn/run_controls.py \
  --baseline-root /path/to/before-source \
  --baseline-producer /path/to/before-producer \
  --producer /path/to/candidate-producer --output /path/to/new-controls \
  --full --gc-prefix /path/to/bdw-gc --gmp-prefix /path/to/gmp

python3 -B tools/performance/process-spawn/compare.py \
  --config /path/to/frozen-config.json --output /path/to/new-window

uv run --no-build --python 3.12 --with scipy==1.18.1 \
  --with matplotlib==3.11.2 --with numpy==2.3.5 -- python -B \
  tools/performance/process-spawn/analyze.py \
  --shapes /path/to/shape-discovery --target /path/to/confirmation \
  --output /path/to/new-analysis --plot
```
