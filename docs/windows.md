# Native Windows compiler and package manager

The Windows compiler is a Win64 PE executable. It uses Win32 process jobs,
file locks and UTF-16 filesystem APIs, with UTF-8 at the language boundary.
It runs without WSL, Cygwin or the MSYS runtime DLL.

Build the Haskell seed with native Windows GHC and Cabal:

```powershell
cabal update
cabal build exe:emlf -j2 --builddir=dist-windows
$seed = cabal list-bin exe:emlf --builddir=dist-windows
```

The initial Windows build used GHC 9.12.2, Cabal 3.14.2.0, its bundled MinGW
Clang 14.0.6, and MSYS2 UCRT64 GMP 6.3.0 and BDWGC 8.2.12 import libraries.
The native dependency prefix contains `include/gmp.h`, `include/gc/gc.h`,
`lib/libgmp.dll.a`, `lib/libgc.dll.a`, and the corresponding DLLs in `bin`.
BDWGC also needs `libwinpthread-1.dll`. The package manager additionally needs
native `pkgconf.exe` installed as `bin/pkg-config.exe`, its `libpkgconf-8.dll`,
and relocatable `gmp.pc` and `bdw-gc.pc` metadata under `lib/pkgconfig`.
MSYS2 is a source of native libraries; an MSYS shell is not needed to run either
MLF tool. Use MinGW-targeting Clang; MSVC-targeting Clang has not been qualified.

```powershell
python scripts/bootstrap-windows.py --seed $seed `
  --clang C:/path/to/mingw/bin/clang.exe `
  --native-prefix C:/path/to/ucrt64
```

This builds three native stages and requires byte-identical stage 2 and stage 3
LLVM. Logs, source identities, compiler hashes and the fixed-point result are
in `.mlf-build/windows/verification.json`. The script reserves a 256 MiB main
stack for compiler and interpreter recursion. On LLVM 14 it enables opaque
pointers explicitly. Keep the dependency DLLs beside the executables or on
`PATH`. After this first bootstrap, a native `emlf.exe` can replace the Haskell
seed for subsequent builds.

## Package manager

With a native compiler and the dependency prefix above, PowerShell 7 can build
the initial package manager and assemble a relocatable SDK:

```powershell
./scripts/bootstrap-package-windows.ps1 `
  -Compiler ./.mlf-build/windows/emlf-stage3.exe `
  -Clang C:/path/to/mingw/bin/clang.exe `
  -NativePrefix C:/path/to/native-dependencies
$sdk = (Resolve-Path .mlf-build/windows-package-tools).Path
$env:PATH = "$sdk/bin;" + $env:PATH
$env:MLF_NATIVE_PREFIX = $sdk
$env:MLF_CLANG = 'C:/path/to/mingw/bin/clang.exe'
$env:MLF_PACKAGE_MANAGER = "$sdk/bin/mlfpkg.exe"
./mlfpkg.ps1 --manifest examples/packages/mlf-package.json plan
./mlfpkg.ps1 --manifest examples/packages/mlf-package.json lock
./mlfpkg.ps1 --manifest examples/packages/mlf-package.json build
./mlfpkg.ps1 --manifest examples/packages/mlf-package.json test
./mlfpkg.ps1 --manifest examples/packages/mlf-package.json run hello
```

The example prints `Hello, local packages!`. The bootstrap script contains only
native compilation and SDK assembly; manifest parsing, resolution, lock files,
caching, build policy and testing run in the MLF manager. `mlfpkg.cmd` is also
available for Command Prompt. Both launchers honor `MLF_PACKAGE_MANAGER`.

Windows builds publish `.exe` files and copy the required runtime DLLs beside
them. The manager discovers its sibling `mlf-host.exe` and `pkg-config.exe`.
The small native host helper implements filesystem operations, directory
junctions and temporary directories without POSIX commands. Processes, locks,
hashes and deadlines use the Windows MLF runtime. Windows drive/UNC paths,
semicolon-separated `PATH`, spaces and Unicode are supported. The SDK prefix
defaults to the parent of the manager's `bin` directory; set `MLF_NATIVE_PREFIX`
when selecting a manager from another build directory. `MLF_CLANG` or `--clang`
selects the external MinGW Clang.

To rebuild both tools through the native manager, keep the input SDK separate
from the new build directory:

```powershell
./mlfpkg.ps1 --compiler "$sdk/bin/emlf.exe" --timeout 21600 `
  --build-dir .mlf-build/windows-native build
./.mlf-build/windows-native/bin/emlf.exe --type --expr '\x -> x'
```

This path requires no Haskell, Cabal, Python, WSL or MSYS shell. `plan`, `lock`,
`build`, ordinary package `test` (interpreter and LLVM), and `run` are supported.
The compiler repository's six internal `compiler-test` groups and release and
benchmark harnesses still contain POSIX transports; those groups have not been
qualified on Windows. Compiler parity is checked separately below.

## Independent compiler validation

The fixed-point result is separate from parity. Export the unchanged independent
corpus and checker through Cabal's dependency environment:

```powershell
New-Item -ItemType Directory -Force .mlf-build/windows/ghc-check,.mlf-build/windows/ghc-export
cabal exec --builddir=dist-windows -- ghc -O1 -package mlf `
  -outputdir .mlf-build/windows/ghc-check bootstrap/CheckTarget.hs `
  -o .mlf-build/windows/check-target.exe
cabal exec --builddir=dist-windows -- ghc -O1 -package mlf -itest `
  -outputdir .mlf-build/windows/ghc-export bootstrap/ExportCorpus.hs `
  -o .mlf-build/windows/export-corpus.exe
.mlf-build/windows/export-corpus.exe .mlf-build/windows/corpus
python scripts/check-windows-parity.py `
  --compiler .mlf-build/windows/emlf-stage3.exe `
  --checker .mlf-build/windows/check-target.exe `
  --manifest .mlf-build/windows/corpus/manifest.jsonl `
  --clang C:/path/to/mingw/bin/clang.exe --native-prefix C:/path/to/ucrt64
```

The parity adapter uses the existing acceptance, independent xMLF type checker,
diagnostic and interpreter/native IO comparisons, changing only native linking.
Its separate `parity/verification.json` records whether all cases passed.
`test/windows_runtime.c` additionally exercises Win64 integer conversion,
Unicode files and environment values, process argument quoting, redirects,
missing executables, deadlines, descendant cleanup, and contended file locks.
Build and run it against both standard and compact-BDWGC runtime layouts.

The retained Windows package validation additionally runs the 15 resolver tests
and 19 integration cases in `test/test_packages.py` and
`test/package_integration.py` against the native manager and compiler. These
cover local dependencies, source boundaries, Unicode paths, both backends,
cache invalidation and repair, failed builds, stale lock files, argument/stdin
forwarding, and explicit or discovered tool selection.
