# Native v0.1.1 validation

The release contains the exact compiler and package manager built from immutable
[`v0.1.1`](https://github.com/mlf-lang/mlf/tree/v0.1.1), commit
`c6033e67601c197cc91d19a0c3a3db4fbdaa1435`.

- Compiler SHA-256: `36816b701ad373d28e16f4dbeba0d3548921cbf36e4b4ca0816b1b53d558e9b6`.
- Package manager SHA-256: `3ad5f14b10258a54ab144e73cbcb40d4c286d9eae5dcc6278adab6c5e8ff4f68`.

All six complete native reports identify that compiler and the same 426 source
inputs. The unchanged release packager verified every source and primary-log
hash, coverage, both layouts, and a fresh self-build with identical LLVM and
binary hashes. Relocated installation, modules, interpreter/LLVM agreement,
native package tests, safe reinstall, and unrelated-command preservation passed.

| Group | Acceptance execution | Coverage |
| --- | --- | --- |
| unit | GitHub | 654 checks, 6,712 independent oracle terms, Figure 12, 57 harness tests |
| packages | GitHub | 18 resolver tests and 19 integration cases |
| self-host | GitHub | Fresh build; LLVM and binary fixed point; no reused candidate build |
| parity | GitHub | 7,086 cases and 160 runtime executions |
| backends | GitHub | 552 rows × 2 backends in each layout |
| port | Local macOS ARM64, 32 GiB RAM | 26 rows × 2 backends in each layout |

The [GitHub run](https://github.com/mlf-lang/mlf/actions/runs/39111436031) failed
its hosted port job after `StateRuntime`, with `StateTypes` next. Its original
workflow omitted the failure stderr, so the cause remains unconfirmed. Its
publisher was skipped. The complete port group was independently rerun locally
through the native MLF package manager, using the exact downloaded compiler,
Clang 23.1.3 and Homebrew BDWGC 8.2.12. Every fixture, independent type check,
source-erasure check, output oracle and execution limit was retained. Both full
layouts passed. This does not claim that the hosted port failure was fixed.

All 52 local port LLVM files and 52 serialized targets also match the earlier
verified PGO run byte for byte. The release is assembled with the five complete
GitHub group reports and the complete local port report; the failed hosted report
is retained separately. No packaging guard was changed. Main now retains outer
test logs and stderr in future workflow artifacts. Its README also uses two
native generations, with input tools kept outside the candidate output directory.

The [machine-readable record](native-release-v0.1.1.json) binds the source,
compiler, native manager, Clang, GMP, BDWGC, test-driver and supervisor hashes.
The supplementary `mlf-0.1.1-validation.tar.gz` release asset retains successful
reports, local process samples, LLVM, serialized targets, logs, tool context,
the failed hosted attempt and rejected heap-cap probes. The 3 GiB cap emitted
allocator warnings and was rejected; it was not used for acceptance. `assemble.sh`
records the strict assembly command. The main archive contains all six complete
reports and primary logs under `evidence/`. Published `SHA256SUMS` covers both
archives; the main archive also has per-file `CHECKSUMS`.

To rerun the port group from a clean `v0.1.1` source checkout with native tools:

```sh
export PATH="$(brew --prefix llvm)/bin:$PATH"
export MLF_GC_PREFIX="$(brew --prefix bdw-gc)"
/path/to/native/mlfpkg compiler-test port \
  --compiler /path/to/release/libexec/emlf \
  --build-dir "$PWD/.mlf-build/port-rerun"
```

Use a fresh output directory. The raw acceptance log records the actual native
manager path and arguments; its executable hash is in the JSON context. Local
packaging uses `tools/release/package.sh VERIFIED_INPUTS FRESH_OUTPUT
 tools/release/licenses/BDWGC.txt` from the clean tagged checkout.

The separate [seven-sample performance gate](../tools/profile/RESULTS.md) passed
3× C compilation and 2× C runtime for every workload using its identified PGO
compiler and LLVM/linker configuration. It was not rerun for this stock release
binary; those performance measurements retain their original hashes and scope.
