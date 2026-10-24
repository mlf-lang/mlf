# Primitive/host implementation review

Reviewed the shared design/core, translator audit, GHC qualification addendum, the
production facade/adapters, and native C contracts. Starting adapters were copied
from paused PR20 `767a5b6`; that PR was not modified. Findings were reproduced before
fixing them, and the final production bytes are covered by the saved receipt.

During this review, the user explicitly approved ordinary Haskell standard
Functor/Applicative/Monad and IsString, removing RebindableSyntax. That direction
supersedes the earlier design’s custom Monad and IO-only pure. The migration owner
implemented that interface change; the final identity fixtures test ordinary
classes, while earlier receipts retain their historical expectations.

## Defects found and corrected in this cutover

1. **Cold async action construction.** `asyncResolveCompletion`,
   `asyncReadCompletion`, `asyncSubscribeCompletion`, and `asyncSubscriptionStatus`
   matched their cell/subscription argument before returning an IO action. Evaluating
   the action with a poisoned operand threw immediately at both optimization levels.
   The migration owner moved each match behind an explicit IO `evaluate` barrier.
   The independent tests changed from four failures to zero.
2. **Regular-file identity.** `Directory.doesFileExist` accepted `/dev/null` and FIFO
   paths. Native `file_exists` accepts only regular files on POSIX. The byte-only
   transport now uses the same `stat`/`S_ISREG` test.
3. **Filesystem-result validation and timing.** A valid symlink to a raw-byte-invalid
   filename let discarded `canonicalPath` succeed; demanding its result later gave
   `invalid Unicode scalar`. Native rejects the invalid UTF-8 during the action.
   Canonical and executable paths now use native byte-oriented helpers and eager
   UTF-8 validation, with owned returned buffers.
4. **stdin ownership.** `ByteString.getContents` closed stdin. A subsequent
   `getByteLine` errored rather than returning an empty array at EOF. Chunked strict
   reads now leave the caller-owned handle open, matching the native runtime.
5. **Cancellation buffer leak.** An asynchronous exception pending when a safe FFI
   call returned could be delivered before Haskell acquired the returned buffer.
   The deterministic PR20 probe observed the buffer was never freed. Ownership
   transfer/copy/free is now masked; cancellation still propagates after cleanup.
6. **Transport-string OOM leak.** Failure of the second allocation in `mlf_string`
   stranded its wrapper. Fault injection counted one outstanding allocation before
   the fix and zero after. The failed allocation now frees that wrapper first.
7. **Locale-sensitive argv and file paths.** `System.Environment.getArgs` rejected
   valid UTF-8 emoji under `LC_ALL=C`, and malformed bytes produced the wrong error.
   The adapter now obtains the same RTS `getProgArgv` bytes used by bundled GHC
   9.14.1, checks the requested index, and performs MLF's explicit UTF-8 decoding.
   Read/write paths now cross the byte-only C boundary rather than GHC's
   locale-selected FilePath encoding. Filename-before-content demand and
   content-before-truncation order are explicitly tested.

8. **Array nominal identity.** IntArray and ByteArray were the same Haskell type
   synonym. An IntArray containing 300 could be passed to readByteArray, violating
   the native type distinction and byte invariant. Distinct newtypes now wrap all
   three scalar array families. Cross-array programs are compile-negative, and
   coldness/payload validation remain covered at both optimization levels.
9. **runProcess operand validation.** An embedded-NUL cwd was validated only after
   the adapter forced the specification. A poisoned specification therefore hid the
   native cwd error. An action-time filename barrier restores the required order.
10. **Nested panic demand.** Panic threw an exception containing a deferred message.
    At O0, panic (panic "inner") let the entry handler write a partial prefix and
    then fail while printing it. An explicit message WHNF barrier ensures the inner
    panic wins consistently at O0/O2.
11. **Exit bounds diagnostic.** The adapter’s exitWith error now matches native
    `exit status must be between 0 and 255` exactly.
12. **Diagnostic encoding.** The entry handler used locale-selected text IO, so a
    Unicode panic under LC_ALL=C failed while printing. It now writes UTF-8 bytes.

## Intentional contract clarification

POSIX os_setEnv called both file_path operations in a single C argument list.
GCC and Clang chose opposite error precedence. The shared runtime helper now
explicitly evaluates the name before the content, and the Haskell adapter validates
the name before marshaling its second operand. This is a deliberate clarification
of previously unspecified behavior, not a claim that the old runtime guaranteed
left-to-right order. Native GCC and Clang oracle subprocesses verify the result.
The migration owner additionally pins executable links to -rtsopts=ignoreAll so
literal +RTS arguments reach the same user argv interface; the suite checks this.

## Adapter provenance changes

- `MLF.Host.Async`: IO evaluation barriers for four cold operations (migration owner).
- `MLF.Host.IO`: masked C-result ownership transfer, eager result decoding, raw RTS
  argv, byte-oriented filesystem operations, non-closing stdin consumption, distinct
  array newtypes, explicit path-validation order and UTF-8 diagnostics.
- `cbits/host.c`: checked string allocation cleanup; native-compatible regular-file,
  canonical-path, executable-path, binary file read and binary file write helpers.
  Private transport operation numbers 10–14 were added. Public MLF primitive IDs
  and signatures were not changed; no GHC closure or MLF heap object crosses FFI.
- `MLF.Host.Base`: this reviewer added the panic-message demand barrier. The
  migration owner separately installed the user-approved standard class/IsString
  interface in Base/Primitive; this reviewer did not edit that interface.
- `runtime/mlf_system.h`: explicit POSIX setEnv name/content sequencing.

## Remaining qualification obligations

No unchecked narrowing defect was found through the public primitive facade in this
bounded review. Huge indices, lengths, handles, waits and bit patterns are rejected.
The private generic transport still relies on its callers' range invariants for its
Int64 lane; it is not a public shared API.

The broad `setjmp`/`longjmp` transport still needs systematic allocation-failure
injection for every native helper; fixing `mlf_string` does not establish that every
resource is released on every OOM path. Likewise the safe-FFI test establishes buffer
ownership when a call returns with cancellation pending, not immediate interruption
of an indefinitely blocked syscall or complete process-child cleanup. Keep those
separate from this suite's passing claims.

The GHC async representation remains typed and single-coordinator. No erased payload
table, unsafe cast, copied primitive IDs, or strict ST payload storage was
introduced. The standard Prelude class hierarchy is the explicitly approved
interface update described above, separate from the runtime repairs.
