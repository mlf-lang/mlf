# Active async fixture compatibility

The native parity runners still execute the paths under `tests/async-task`,
`tests/async-process`, `tests/async-package`, and
`tests/fixtures/async-completion`. The GHC direct-host tests execute different
shared `.hs` entries. A passing direct-host suite does not establish that the
native runner's input sources still compile.

Four active entries (task Main/Processes and process Main/Panic) now select
`shared-haskell-v1` syntax. Their bodies match the maintained corresponding
`tests/shared/MLF/Tests/Async/*.hs` modules, with the entry module named Main.
This syntax change is necessary because the legacy parser's list patterns
produce nominal `Cons`/`Nil`, while the current libraries expose canonical
`[]`/`:`. Merely spelling a type `[Int]` does not repair those patterns.
The compiler, legacy parser, frozen evidence, and historical fixtures are not
changed. WaitGraph only needs `Unit` changed to `()` and retains its syntax.
The package consumer and Guards already used canonical unit.

Before replacing entries, the old and shared bodies were independently compared:
ordered identifiers, strings, numbers, and control arrows match exactly after
excluding module/import headers, comments, and the migrated constructor names.
The respective token counts are 907, 1185, 1658, and 145. This is a structural
migration check, not a semantic execution claim. The assertions, failure codes,
case ordering, helper calls, and literal expected stdout files remain unchanged.

Completion runtime and source-negative cases need canonical unit too. The latter
still deliberately contain their original type/kind/opacity violations; unrelated
unit errors must not make a negative case pass for the wrong reason. Their
rejection-phase checks remain active. Target-negative XMLF fixtures are untouched.
No user-defined nominal ADT elsewhere is renamed to a builtin.

`test_async_sources.py` runs in the unconditional release metadata gate, in both
normal and optimized Python. Mutation controls catch the original `IO Unit`
regression, stale list/tuple identities, duplicate nominal Monad declarations,
stale checked-type oracles, and a missing required entry. It is only a static
regression guard and explicitly does not claim source or runtime qualification.

`check_async_sources.py --producer BUILD --output NEW_DIRECTORY` additionally
uses the authenticated exact-source GHC-produced compiler to compile the 13
active positive parity entries and target-check their `IO ()` results, and check
all nine completion source negatives at their intended rejection phase. It
records commands, hashes, diagnostics and an initially incomplete result. The
producer is rechecked before success. The existing symlink-aware guest-state
inventory snapshots all library/test `.hs` and `.emlf` paths, additions, removals,
lexical aliases and resolved contents, and is compared before and after every
compiler command. Preexisting fixture-directory shadows of manifest modules are
rejected. Compiler commands use an empty controlled cwd, rather than allowing
ambient repository-root module lookup; non-Main entry module names are rejected
to keep hierarchy lookup roots explicit. CI runs this bounded source check on
O2 without requiring an expensive fresh native bootstrap. This is compiler-source
compatibility, not GHC-host execution of the test bodies and not native parity.
The existing completion/process/task/package native parity runners, literal output
oracles, source-pinning and ABI guards remain required.

## Reconstruction and validation status

This patch is reconstructed on the remotely fetched baseline
`98540496cd5e94d2de87894486acdc9bb945fdac` after the previous working directories
were lost. It reconstructs the final source changes previously developed as
`bb55966c`, `8cd14aff`, `a18a7203`, and `ea346b49`; it does not restore those Git
objects or claim byte-for-byte recovery of their complete trees. The migration
comparison above and all 16 cheap controls were rerun on the reconstructed code.

The recorded result of the earlier authenticated source campaign was: Task Main
compilation passed in 16.43s and target checking as `IO ()` passed in 0.46s;
Processes compilation reached the original 120s per-command cap with empty
stdout/stderr and completed cleanup. The entire campaign remained incomplete
(139.50s, peak process RSS 2,065,313,792 bytes, no outer-watchdog resource trip).
Those old receipt files are no longer available in the recovered workspace;
this description is historical context, not a substitute receipt or a fresh
validation claim. No campaign was run after the source timeout was raised.

The source-command cap matches the existing 600s completion/process/task parity
default. Target checks retain 120s. The aggregate budget remains 1800s, 4 GiB RSS,
6 GiB address space, 256 MiB evidence and an 8 GiB disk floor. All output evidence
is nested beneath the watched root. No case is dropped, and another timeout
requires diagnosis rather than an automatic limit increase. Fresh authenticated
source checks and native parity are still required for the final integrated code.
