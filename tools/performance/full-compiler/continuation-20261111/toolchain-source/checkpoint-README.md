# Current-main endpoint qualification and recovery checkpoint

## Outcome

Frozen compiler sources: `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`.
The complete recursive `MLF.Entry.Emlf` closure is **90 shared modules,
5,233,364 bytes**. Both lanes include all of it freshly. GHC additionally uses
the original five-line Main wrapper. Installed GHC packages, fixed primitive/
host adapters, builtin artifacts and runtime objects are reusable dependencies.
The MLF lane compiles this closure as **one crate**, not as an `mlfpkg`
package-by-package build. This is a declared endpoint, not a claim that it is
the fastest available complete-build route.

On the recorded cloud Linux x86_64 machine (Intel Xeon Platinum 8573C, nine
visible CPUs, approximately 9.7 GiB RAM):

| Qualification | Outcome | Exact outer wall | Sampled process-tree peak RSS |
| --- | --- | ---: | ---: |
| GHC-built ordinary O2 MLF, source to runnable compiler | Stopped by unchanged 600-second guard during source-to-checked; no completed stage or checked output | 600.098992210 s | 1,745,485,824 bytes |
| GHC 9.14.1, source to runnable compiler including link | Complete; exactly 90 shared modules plus Main fresh, version/identity checks passed | 155.931809537 s | 1,216,823,296 bytes |

The GHC compiler stage was 155.815914475 seconds, with 148.415633 user and
7.440147 system seconds. MLF's killed parent worker did not reap the compiler
child, so its retained `wait4` CPU fields **are not compiler CPU measurements**.
There is no MLF CPU/GC breakdown or successful complete-task time here.

**No complete MLF/GHC ratio or performance win was established.** No formal
MGGM samples, candidate timing, native self-host A/B, or fixed-point test ran.
The MLF qualification may have overlapped approximately three seconds of a
small frontend control at its beginning; it is not a formal performance sample.
There were no retries, replacement samples, limit increases or omitted target
modules. The originally proposed MGGM window was not started after this failure.

The failed MLF query directory had a zero-byte `.lock` file and empty
`query-graph-v2/{generations,results,staging}` directories. Current query payloads
are published after successful computation. Their absence does not prove that
inference had not run, and does not localize the internal timeout phase.

This checkpoint records exact GHC source provenance and authored CLI checks.
The MLF fresh-group inventory, complete checked-byte oracle and comparison of
both generated compilers' behavior remain **unavailable**, not passed. Historical
81-module results, including 7.157×, must not be substituted for this run.

## What is preserved

- `frozen-workload.json`: portable relative paths, source bytes and SHA256 for
  every target module, original Main identity, and the original workload hash.
- `environment.json` and `toolchains.json`: machine boundary, versions, official
  download URLs and verified archive/package hashes.
- `mlf-command.json`, `mlf-qualification.json`, `ghc-command.json`,
  `ghc-qualification.json`, `ghc-stages.json`: original small receipts, including
  the failed observation. Their absolute paths describe the original invocation.
- `qualification-plan.json`: the pre-execution plan; its conditional formal
  comparison never became eligible and must not be resumed blindly.
- `summary.json`: result, limitations, receipt hashes and identities of large
  local inputs. This directory is a completed **failure/qualification record**,
  not an open timing cohort.

Toolchains, producer objects/executables, fixed builtin/runtime dependencies and
large logs are not committed. Receipt hashes identify them but cannot restore
their bytes. A new machine or lost workspace requires rebuilding and authenticating
them. A reboot/environment change creates a new cohort; never append its timings
to these receipts or relabel an interrupted command as successful.

## Restore the cloud tools

Use a fresh cloud Linux x86_64 Debian-compatible workspace. Do not attach a user
computer for this checkpoint. The original base supplied GCC 14.2.0, GNU ld 2.44,
glibc 2.41, GMP 6.3.0, make, ar, pkg-config, curl, xz and dpkg-deb. Install missing
prerequisites from the distribution's trusted package sources with the required
authorization. A materially different base must be recorded as a new environment.

The following installs only into a fresh workspace-local directory. It uses the
pinned official downloads; a missing/changed archive must fail rather than be
silently replaced with another version.

```sh
ROOT="$PWD"
TC="$(dirname "$ROOT")/compiler-toolchain-recovery-$(date -u +%Y%m%dT%H%M%SZ)"
export ROOT TC
mkdir "$TC"
python3 - <<'PY'
import hashlib, json, os, pathlib, subprocess
root, tc = pathlib.Path(os.environ['ROOT']), pathlib.Path(os.environ['TC'])
m = json.loads((root / 'tools/performance/full-compiler/baseline-20261110/toolchains.json').read_text())
for item in [m['ghc'], *m['debian_packages']]:
    path = tc / item['url'].rsplit('/', 1)[1]
    subprocess.run(['curl', '-fL', '--retry', '2', item['url'], '-o', str(path)], check=True)
    if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
        raise SystemExit('archive SHA256 mismatch: ' + str(path))
    if path.suffix == '.deb':
        subprocess.run(['dpkg-deb', '-x', str(path), str(tc / 'debian')], check=True)
PY
tar -xJf "$TC/ghc-9.14.1-x86_64-deb12-linux.tar.xz" -C "$TC"
(cd "$TC/ghc-9.14.1-x86_64-unknown-linux" && ./configure --prefix="$TC/ghc" && make install)
mkdir "$TC/bin" "$TC/pkgconfig"
ln -s ../debian/usr/lib/llvm-19/bin/clang "$TC/bin/clang"
sed "s|^prefix=/usr$|prefix=$TC/debian/usr|" \
  "$TC/debian/usr/lib/x86_64-linux-gnu/pkgconfig/bdw-gc.pc" > "$TC/pkgconfig/bdw-gc.pc"
export PATH="$TC/ghc/bin:$TC/bin:$PATH"
export LD_LIBRARY_PATH="$TC/debian/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export LIBRARY_PATH="$TC/debian/usr/lib/x86_64-linux-gnu${LIBRARY_PATH:+:$LIBRARY_PATH}"
export PKG_CONFIG_PATH="$TC/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
test "$(ghc --numeric-version)" = 9.14.1
clang --version
pkg-config --cflags --libs bdw-gc gmp
```

Record these environment variables in the new run's recovery notes. In particular,
the isolated Clang, GC library and pkg-config paths must reach all child commands.
Do not copy, rewrite or rebase the old producer's authentication receipt.

## Reconstruct inputs and fixed dependencies

First check out the checkpoint branch/commit whose shared sources match the frozen
inventory. Only one worker may build or measure at a time. Use a new output name:

```sh
RUN="$ROOT/.mlf-build/baseline-recovery-$(date -u +%Y%m%dT%H%M%SZ)"
export RUN
mkdir "$RUN"
python3 -B tools/performance/full-compiler/prepare_workload.py \
  --source "$ROOT" --label f9bdb40a659bfdff4cbb782d438afbb0417dd2e1 \
  --output "$RUN/workload.json"
python3 - <<'PY'
import json, os, pathlib
root, run = pathlib.Path(os.environ['ROOT']), pathlib.Path(os.environ['RUN'])
frozen = json.loads((root / 'tools/performance/full-compiler/baseline-20261110/frozen-workload.json').read_text())
actual = json.loads((run / 'workload.json').read_text())
rows = [{k: r[k] for k in ['module', 'relative', 'sha256', 'bytes']} for r in actual['modules']]
if rows != frozen['modules'] or actual['module_count'] != frozen['module_count']:
    raise SystemExit('frozen compiler source inventory mismatch')
PY
python3 -B tools/shared/resource_watchdog.py --seconds 900 \
  --address-space-mib 6144 --rss-mib 5120 --max-output-mib 2048 \
  --disk-free-mib 5120 "$RUN/build" \
  python3 -B tools/shared/build.py --bootstrap-only --optimization 2 \
  --build-dir "$RUN/build/producer"
python3 -B tools/performance/compiler-shapes/prepare.py \
  --producer "$RUN/build/producer" --source "$ROOT" --build-builtin \
  --expose-entry-host --output "$RUN/setup" \
  --ghc "$(command -v ghc)" --clang "$(command -v clang)"
```

These are setup steps, not performance measurements. Keep the 5 GiB process-tree
RSS, 6 GiB per-process address-space, 5 GiB free-disk and 3 GiB available-host
memory guards. The 900-second setup budget is not the 600-second endpoint budget.

After setup, **stop and consult the current experiment plan**. Do not automatically
repeat the timed-out MLF endpoint or run MGGM. This checkpoint's next step was
bounded diagnostic localization, not another unchanged ten-minute run. If a later
approved protocol calls for endpoint qualification, the exact invocation shape is:

```sh
# LANE is explicitly chosen by that new protocol, not a retry of this record.
python3 -B tools/performance/full-compiler/qualify.py \
  --workload "$RUN/workload.json" --setup "$RUN/setup/setup.json" \
  --producer "$RUN/build/producer" --producer-source "$ROOT" \
  --lane "$LANE" --output "$RUN/qualification-$LANE"
```

Before accepting an existing result after an interruption, check its completion
flag, exit/guard reason, source and tool hashes and output artifacts. An absent or
incomplete receipt is pending/failed, never evidence of completion. Keep old
receipts unchanged and allocate new identities for newly authorized work.
