# Initial installed comparison at c98cae57

This is the first measurement window. A subsequent byte comparison found two
existing module bindings had been renumbered in the emitted xMLF for the module
diamond. The new primitive had advanced the standalone namespace allocator.
The implementation was corrected and measured again. This receipt is retained
for the original candidate only.

The public `emlf SOURCE -o OUTPUT` installations at #29 (`8c455641`) and
the IndexVec implementation (`c98cae57`) compiled the same programs as
GHC. All 90 compilation commands succeeded. Every executable returned the
expected stdout, empty stderr and successful exit for three inputs (270 checks).

The machine was an Apple M1 Max with 32 GiB RAM running macOS 26.6.2, arm64.
Both compiler installations reported `MLF/shared-haskell-v1 GHC` and used
GHC 9.14.1 `-O2` to build the compiler, with the registered native Foundation
and runtime objects. GHC compiled user code with `--make -j1 -O2` against
one prebuilt host `MLF.Primitive` package. The MLF driver checked user code,
emitted LLVM, ran one Clang `-O2` compile and linked the installed objects.
The Clang version was Apple clang version 21.0.0 (clang-2100.1.1.101). Configuration, source hashes and exact
commands are in the [plan](plan.json).

Each cell has three rounds. Before/after order alternated, GHC occupied
rotating positions, and each round reversed order for its warm legs. Builds
ran serially. Fresh legs used empty target directories. A warm leg ran the
same command on unchanged inputs and its preceding outputs. GHC reused its
compiled user modules. The installed MLF driver rebuilt user code. Filesystem
caches were left warm. The [receipt](receipt.json) records every sample,
including user/system CPU time, wait4 peak RSS and sampled process-group RSS, executable checks and MLF commands.

## Median wall time

Times are seconds. MLF/GHC uses the candidate MLF median. A change below 1.0
means the candidate median was lower than the #29 median for that cell.

| Workload | Target | #29 | Candidate | GHC | Candidate / #29 | Candidate / GHC |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Declaration chain | fresh | 0.3770 | 0.3770 | 0.5354 | 1.000 | 0.70 |
| Declaration chain | warm | 0.3699 | 0.3773 | 0.0894 | 1.020 | 4.22 |
| Wide fan-out | fresh | 0.3739 | 0.3945 | 0.5343 | 1.055 | 0.74 |
| Wide fan-out | warm | 0.3787 | 0.4039 | 0.0898 | 1.067 | 4.50 |
| Recursive ring | fresh | 0.3829 | 0.3921 | 0.5841 | 1.024 | 0.67 |
| Recursive ring | warm | 0.3827 | 0.3946 | 0.0885 | 1.031 | 4.46 |
| Module diamond | fresh | 0.3683 | 0.3640 | 0.6709 | 0.988 | 0.54 |
| Module diamond | warm | 0.3475 | 0.3582 | 0.0882 | 1.031 | 4.06 |
| Compiler Unicode | fresh | 0.4510 | 0.4654 | 0.6338 | 1.032 | 0.73 |
| Compiler Unicode | warm | 0.4426 | 0.4673 | 0.1005 | 1.056 | 4.65 |

The chain median was essentially unchanged. The fresh module diamond was
1.2% lower, and the other three fresh candidate medians were 2.4–5.5% higher.
All five warm candidate medians were higher. This cohort does not establish a
compilation speedup from the graph migration. The public driver compiled these
five small targets faster than GHC on a fresh build, and took longer on a
no-edit repeat. The difference in user-object reuse matters to that comparison.

## MLF stage observations

These candidate fresh medians use filesystem completion times for emitted IR,
object and linked executable. The first interval includes driver startup and
frontend work. The last omits final validation and publication. Medians of the
three intervals are separate from whole-command wall time.

| Workload | Start to IR (s) | IR to object (s) | Object to linked program (s) |
| --- | ---: | ---: | ---: |
| Declaration chain | 0.258 | 0.038 | 0.055 |
| Wide fan-out | 0.264 | 0.042 | 0.055 |
| Recursive ring | 0.271 | 0.040 | 0.052 |
| Module diamond | 0.240 | 0.036 | 0.053 |
| Compiler Unicode | 0.329 | 0.051 | 0.056 |

## Reproduction

Check out the two commits in separate worktrees. Run the public build in each
and preserve its installation directory at the original path. From the candidate
checkout run the paired command below. The plan and receipt bind the binaries
and sources by SHA-256. All stage and oracle logs remain in the selected output
directory.

```sh
# In each worktree
python3 -B tools/shared/build.py --build-dir "$PWD/.mlf-build/install"

# In the candidate worktree
python3 -B tools/performance/compiler-shapes/bench.py installed \
  --before /absolute/before/.mlf-build/install --after "$PWD/.mlf-build/install" \
  --size 16 --repeats 3 --output "$PWD/.mlf-build/installed-pairs"
```
