# Independent runtime-adapter review

Review date: 2026-10-23. Scope: the production `MLF.Primitive`,
`MLF.Host.Base`, `MLF.Host.IO`, `MLF.Host.Async` and `cbits/host.c` under
`host/ghc`, compared with `runtime/mlf_runtime.c`, its included native helpers,
and the shared-source design plus GHC qualification addendum. No compiler build,
PR20 modification or user-computer work was performed for this review.

## Conclusion

The previous focused receipt (`20261023T210203Z`, 73 contract checks per
optimization level) did not cover several observable contract violations.
Independent bounded probes reproduced five adapter defects, an argv build
configuration gap, and compiler-dependent demand in a native helper. **All seven
findings have now been corrected and checked within this review's Linux scope.**
The final focused receipt is `20261023T211159Z`: all 84 command expectations pass,
including 87 direct contract checks and 590 numeric comparisons at each of
`-O0` and `-O2`. Independently recomputing every recorded source hash found no
mismatches. No additional blocking adapter defect remains from this bounded
review; this is not a full dual-host or release qualification.

The inspected representation boundary uses actual Prelude Bool,
arbitrary-precision Integer, opaque scalar Strings, typed completion payloads,
and a byte-only C transport. During this review the user approved an updated
ordinary-Haskell syntax design: the former custom Monad and IO-only pure
requirements are intentionally superseded by actual Prelude
Functor/Applicative/Monad and standard polymorphic pure. The unchanged demand,
typed-payload and primitive-ID requirements continue to apply. These conclusions
do not imply whole-compiler or bootstrap qualification.

## Findings

### 1. Primitive array identities collapsed (high)

Originally `IntArray` and `ByteArray` were identical type synonyms for
`Data.Array.IO.IOArray Prelude.Int Integer`. This accepted the following through
only the public facade:

```haskell
asByte :: F.IntArray -> F.ByteArray
asByte a = a
```

A GHC program allocating `newIntArray 1 300`, converting with `asByte`, and
calling `readByteArray` returned **300**. This violates both distinct native
primitive type identity and the byte-value invariant. Native runtime operations
expect separate `INT_ARRAY` and `BYTE_ARRAY` tags; the native type interface also
uses separate type constructors.

Required fix: abstract distinct wrappers, with a negative public-facade fixture.
Keep action construction cold when introducing wrappers. The host maintainer has
introduced distinct newtypes and is qualifying the updated action wrappers.

### 2. runProcess forces specification before validating cwd (medium)

The generic host transport encodes both String arguments before entering C.
Originally `v_runProcess` called it without first validating the cwd. Thus:

```haskell
F.runProcess (B.literal "bad\0cwd") (B.failure "specification")
```

produced `HostError "specification"` at both `-O0` and `-O2`. The unchanged
native `os_runProcess` first calls `file_path(directory)`, producing
`Runtime: file path contains NUL` before demanding the specification. This is
an action-time ordering violation, analogous to the earlier writeFile defect.

Required fix: an action-time cwd validation barrier before encoding the second
argument. This barrier has been added by the host maintainer.

### 3. panic fails to demand its String operand before throwing (medium)

Originally `v_panic s = failure (unpack s)` let a lazy exception message escape.
At `-O0`, running `panic (panic "inner")` through `runEntry` printed a partial
`Runtime: ` prefix and then a GHC uncaught HostError with a backtrace. The
unchanged native runtime demands the String before printing and produces
exactly `Runtime: inner\n`, exit status 1.

The same GHC source happened to produce the correct text at `-O2`; this is an
optimization-dependent defect, not evidence that no barrier is required.
Required fix: demand the String before constructing/throwing the outer error.
The host maintainer has added `s pseq ...`.

### 4. Entry-wrapper diagnostics depended on the locale (medium)

Originally `runEntry` rendered HostError with `System.IO.hPutStrLn`. Under
`LC_ALL=C`, `panic "😀"` printed a partial prefix and an IOException saying the
character could not be encoded, at both optimization levels. Native panic
writes the String's UTF-8 bytes and prints `Runtime: 😀\n` successfully.

Required fix: emit the diagnostic as explicit UTF-8 bytes, including the prefix
and newline, and flush stderr. The host maintainer has implemented this and is
adding exact-output subprocess checks in both C and C.UTF-8 locales.

### 5. exitWith range-error text differs (low)

`exitWith 256` originally reported `invalid exit code`. Native runtime reports
`exit status must be between 0 and 255`. The host maintainer has aligned this
specified runtime diagnostic. The range check already happened at action time
and rejected huge integers; no unchecked narrowing was found here.

### 6. RTS command-line parsing changes application argv (medium; build boundary)

Raw `getProgArgv` fixes locale decoding but returns argv after RTS processing.
The existing public ArgumentProbe invoked with `+RTS -RTS` reports an argument
bounds error, whereas native runtime preserves both arguments. Invoking it with
`+RTS --info -RTS` prints RTS information without running the program.

The inspected `tools/shared/build.py` and `mlf-shared.cabal` linker settings did
not disable that interception. Relinking the same ArgumentProbe with supported
GHC 9.14.1 flag `-rtsopts=ignoreAll` made `+RTS --info -RTS` ordinary application
arguments: reading the first String returned scalar length 4. This flag is
listed in the installed GHC 9.14.1 user's guide, `phases.html`, RTS options.

Required decision/fix: retain literal argument semantics in every authoritative
GHC executable link, normally using `-rtsopts=ignoreAll`, and cover special RTS
spellings. This flag is now present in every Cabal executable and in the Python
builder's actual link commands. The final focused suite preserves literal RTS
argument spellings. The receipt must bind the link setting; changing only getArg
cannot prevent RTS startup from intercepting input. Installed GHC documents that
ignoreAll also ignores GHCRTS; a separate environment-variable regression was not
part of this independent probe.

### 7. setEnv has a native demand-order ambiguity (medium; common contract)

`runtime/mlf_system.h` calls
`setenv(file_path(name), file_path(contents), 1)` in one C argument list. C does
not specify which file_path runs first. A direct unchanged native oracle with
poisoned name and contents gave:

- `/usr/bin/cc -O0`: `Runtime: contents`
- `/workspace/shared/mlf-toolchain/bin/clang -O0`: `Runtime: name`
- GHC host at both optimization levels: `HostError "name"`

Do not fix the adapter to an assumed portable right-first rule. Additionally,
the host encodes contents before C validates a NUL-containing name, so
`setEnv "bad\0name" (panic "contents")` differs from the Clang native path just
like runProcess did.

Required fix: make common native validation order explicit with sequential
temporaries, preserve the chosen native/guest contract across both C compilers,
and add the matching action-time barrier in the GHC adapter. The maintainer has
now specified name-before-contents in the POSIX native helper and added the
matching host barrier. This common-helper clarification must be included in
fresh native qualification, not attributed solely to the GHC adapter.

## Post-fix independent checks and revised syntax boundary

Fresh bounded GHC builds at both `-O0` and `-O2` reproduced the intended results
for runProcess cwd validation, setEnv name validation/demand, exact nested panic,
UTF-8 panic under `LC_ALL=C`, and exitWith range diagnostics. Recompiling the
original `asByte` counterexample now fails with distinct IntArray/ByteArray types.

The revised facade directly imports and reexports the actual Prelude
`Functor(..)`, `Applicative(..)` and `Monad(..)` entities. It contains no replacement
class declarations, custom do hooks or literal-hook exports. `bind` remains an
ordinary compatibility function delegating to Prelude `(>>=)`. The opaque String
has an instance of the actual `Data.String.IsString` class. No unsafe cast,
wrapper class hierarchy or representation-erasing transport was introduced.

An independent `NoImplicitPrelude, OverloadedStrings` fixture deliberately
shadows `fromInteger`, `fromRational`, `fromString`, `negate`, `ifThenElse`,
`(>>=)` and `(>>)` with definitions that panic. With **no RebindableSyntax**, an
ordinary do/if expression plus negative Int and Double literals and a Unicode/NUL
String literal evaluates to `(42,-7,-1.25,2)` at both optimization levels. This
establishes that GHC's ordinary syntax, rather than those lexical lookalikes,
performs desugaring. It does not establish the new native frontend's handling of
the same fixture; that remains a separate dual-host acceptance gate.

The eight owned implementation-class instances and removal of RebindableSyntax
from the entire shared manifest were being coordinated separately while these
adapter checks ran. No completed whole-manifest claim is made here.

## Independently checked non-findings and limits

- The four repaired async pattern matches are now behind IO evaluate barriers.
  Typed cells retain lazy payloads; a rejected second resolution does not demand
  its payload. Scope closure/status, callback retirement before invocation,
  FIFO readiness and timer insertion agree with the inspected native algorithm
  under the documented single-coordinator model.
- ST arrays retain lazy elements, read snapshots and rank-2 region typing.
  Ordinary IO scalar arrays validate initializers even when length is zero.
- Public huge sizes, indices, bit patterns, file-lock numbers and async limits
  use explicit checks before narrowing. The generic private transport still
  assumes its integer callers maintain that invariant.
- Unicode Strings use scalar counts and explicit UTF-8 transport. Independent
  getLine probes succeeded with emoji under both C and C.UTF-8; malformed bytes
  produced the MLF UTF-8 error. No locale problem was reproduced there.
- Native-compatible regular-file tests and owned canonical/executable-path
  buffers are implemented; results are decoded during the action even when the
  caller discards them. The raw read/write path avoids FilePath locale encoding.
- The C-result copy/free region is masked against a pending asynchronous
  exception. This does not establish prompt cancellation of a blocked syscall.
- Both Cabal and the authoritative Python builder contain the required
  `-fpedantic-bottoms -fno-state-hack` flags. Their presence does not prove all
  optimizer demand equivalences; the nested-panic counterexample illustrates
  why direct tests remain necessary.
- The host still shares native helpers whose setjmp/longjmp error exits can
  bypass cleanup on allocation failure. The earlier review correctly limits
  its allocation-failure and process-cleanup claims. No exhaustive OOM or
  cancellation campaign was performed here.

## Probe method and evidence

Independent fixtures and build logs were created outside the checkout under
`/tmp/mlf-adapter-independent-review`. GHC builds used 9.14.1, `-O0` and `-O2`,
`-XHaskell2010 -fpedantic-bottoms -fno-state-hack -dcore-lint`, disabled package
environments, production host sources, and the real C process adapter. Each
compile had a 60-second bound; executable probes had a 5-second bound. Native
oracles included the unchanged `runtime/mlf_runtime.c` directly and linked the
already installed BDWGC/GMP dependencies, without compiling the language
implementation. The original reviewed source identities were recorded by receipt
`20261023T210203Z` (the original `tests/shared-host/evidence/latest` checkpoint).
The original five hashes were:

- Base.hs: `71be4d20a9d73fb040b9b6e9e1e9914e3c4c26a84bbb818e793dc90d86e0ff08`
- IO.hs: `948c4be5d8a8796451925b1af5007d655f2c62c893dc6bb738e2c3da69153987`
- Async.hs: `f96128f3494d7525178205d58fcf4870a41fdef92874342af44318453c261c35`
- Primitive.hs: `d6275901d9816a8654725f90a6e7883376c56c8f927d6618ee48359e8af390fe`
- host.c: `bfcf4b400902afaa89e0d6cbe0de5901a4e1e89c6100d203e50c3099ba7fc694`

The complete original checkpoint is preserved in
`tests/shared-host/evidence/before-independent-review/`. The fresh passing
post-fix receipt is `tests/shared-host/evidence/latest/receipt.json`, timestamp
`20261023T211159Z`; every source listed by that receipt matched the checkout at
the independent final verification. Its principal final hashes are:

- host/ghc/MLF/Host/Base.hs: `6d60cb8f2349293f2a797348b202577267df5f69d334cc936df6be455e547a4d`
- host/ghc/MLF/Host/IO.hs: `6779594885592e3661f0070c0a1f2244d7563d5e3b19bcb1a0b47c6af934adf8`
- host/ghc/MLF/Host/Async.hs: `d576fb9829c9d7eed49c728bc67a05266f74850f5a38bde346783d269013d0c3`
- host/ghc/MLF/Primitive.hs: `ffe9fd2106149e664e5ca22e1e1eae51cf4b0a1541cee090f1e7bc9185efa031`
- host/ghc/cbits/host.c: `bfcf4b400902afaa89e0d6cbe0de5901a4e1e89c6100d203e50c3099ba7fc694`
- runtime/mlf_system.h: `eb1f0f97ece2bd95a60a75e4c7445b5c2cbd2ff75c75545e2ac673f2f3157cff`

The focused test receipt identifies compiler paths and version observations;
the eventual authoritative migration receipt must additionally bind complete
compiler/tool hashes, dependency identities and the full final implementation
snapshot. These focused results cannot substitute for that final build record.

This review document is the only checkout file edited by this reviewer.
