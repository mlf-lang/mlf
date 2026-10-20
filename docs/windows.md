# Native Windows toolchain

The Windows x64 preview contains native `emlf.exe`, `mlfpkg.exe`, a small Win32
filesystem helper, runtime sources, GMP/BDWGC DLLs, headers and import libraries.
It does not require GHC, Cabal, Python, WSL or an MSYS shell.

Download the Windows zip and `SHA256SUMS` from the release, verify the archive,
and extract the complete SDK. In PowerShell 7:

```powershell
. .\mlf-0.2.0-windows-x64\Activate.ps1
emlf --version
mlfpkg --version
emlf --type --expr '\x -> x'
mlfpkg --manifest .\examples\packages\mlf-package.json test
```

Native compilation requires a MinGW-targeting Clang. Set `MLF_CLANG` to its
absolute path. The SDK includes `Build-Program.ps1` for standalone sources;
the native package manager handles crate metadata, inference/cache decisions,
LLVM compilation and linking. Published executables carry their required DLLs
in the package build's `bin` directory.

## Reproduce a release build

The cross-platform workflow exports checked `emlf.ll` and `mlfpkg.ll` from its
native macOS bootstrap with an exact two-file checksum manifest. Windows links
those LLVM files with its own runtime, then performs two fresh native builds:

```powershell
tools/release/setup-windows.ps1 -Output .mlf-build/windows-dependencies
tools/release/bootstrap-windows-release.ps1 `
  -Seed .mlf-build/portable-llvm `
  -NativePrefix $env:MLF_NATIVE_PREFIX -Clang $env:MLF_CLANG `
  -Output .mlf-build/windows-native
tools/release/qualify-windows.ps1 `
  -Stage1 .mlf-build/windows-native/stage1 `
  -Stage2 .mlf-build/windows-native/stage2 `
  -NativePrefix $env:MLF_NATIVE_PREFIX -Clang $env:MLF_CLANG `
  -Output .mlf-build/windows-evidence
tools/release/package-windows.ps1 `
  -Build .mlf-build/windows-native/stage2 `
  -NativePrefix $env:MLF_NATIVE_PREFIX -Clang $env:MLF_CLANG `
  -Evidence .mlf-build/windows-evidence -Output .mlf-build/windows-release
```

Setup downloads hash-pinned native dependencies and retains source archives,
provenance and licenses. Both LLVM inputs are verified before linking.
No type checking or inference is bypassed.

## Qualification

Qualification binds the exact source snapshot, native tools, Clang, helper
and dependency hashes. It requires:

- Fresh compiler and manager LLVM fixed points across the two native builds.
- The native MLF package harness: 18 resolver checks and 26 integration cases,
  including crate cache invalidation, source-free metadata, command failure
  propagation, compiler selection and native PGO isolation.
- The native MLF parity harness: 7,086 frozen cases, independently checked
  targets, prescribed rejection diagnostics and 160 interpreter/native runtime
  executions. The two reviewed crate import-cycle overlays are shared with
  POSIX; expected types are never regenerated from the candidate.
- `tests/native/windows_runtime.c` under standard and compact GC, checking Win64
  integer conversion, UTF-8 paths, process behavior and runtime operations.
  Deep cache paths exceeding MAX_PATH cover writes, atomic replacement, copies,
  directory enumeration, canonical link identity, redirects, locks and cleanup.
  `tools/release/test-windows-runtime.ps1` runs these checks independently of a
  compiler bootstrap and is also a required CI job.
  It also rebuilds C and LLVM objects and executables across a timestamp
  boundary, requiring byte-identical outputs with zero COFF/PE timestamps.
- PE import inspection, exact embedded versions, SDK relocation and standalone
  executable/DLL checks.

The internal POSIX unit/backend/port event transports are not claimed as Windows
qualification. Those full matrices run separately on Linux and macOS.
Performance claims remain scoped to the separately recorded benchmark host and
candidate. Packaging rejects incomplete or mismatched evidence.
