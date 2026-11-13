# Source-only control contract

These controls have not been compiled or executed. Python mirror tests do not
qualify Haskell semantics or profiling attribution. Both files need independent
review and a separately admitted PROBE-CONTROLS run under the full supervisor.

* `DeferredDemand.hs 100000`: exact stdout `PASS deferred-demand\n`, empty stderr.
  Compile profiling options into fixed one-use report destinations. The runtime
  argument prevents a fixed CAF workload. Confirm positive raw allocation under
  TOY_PRODUCER, including when demanded by TOY_CONSUMER; do not infer conversion
  from RTS totals. Inspect installed RTS allocation units and retain the raw JSON.
  The independent pair is a toy no-demand-bottom check, not a substitute for
  actual compiler-inventory controls.
* `InventoryDemand.hs`: no argv; exact stdout `PASS inventory-demand\n`, empty
  stderr. Actual Checked.check succeeds for Int 42; type projection succeeds;
  separately demanding declarationBindings returns the exact invalid-fragment
  error. A pair retains an independent bottom inventory producer without demand.
  Actual Open.check rejects nonfragment ownership and unbound export type. This
  is not an injected bottom inside the opaque CheckedTerm constructor.

Maintained frozen fixtures to retain (not run in source preparation):

* `tools/shared/fixtures/CheckedBindings.hs`: 32 prescribed accepted/rejected
  syntax cases, inventory parity against independent collector, 6 freshening
  serials each, metadata/link controls; final line is
  `Checked binding inventory audit: 33 checks passed` with preceding PASS lines.
  Includes `valid-nonfragment`, `bad-recursive-signature`, `unbound-rhs`,
  `open-import-type` and checked metadata signature/checksum rejections.
* `tools/shared/fixtures/item4/SourceValueScope.hs`: original full main checks
  source-definition marker preservation of type and erasure. Keep its complete
  maintained expected stdout, not just one matched PASS substring.
* `tests/shared/MLF/Tests/SharedFrontend.hs`: maintained shared frontend assertions
  include roundtrip type/erasure and Compiler.compile's real skeleton-erasure gate.
  It is a library test module, not a standalone Main. Run through its original
  harness; do not replace it with a fabricated standalone command.

The coordinator must pin and retain original fixture harnesses, outputs, and
negative expectations before admitting controls. No claim of complete maintained
semantic-fixture execution is made by this preparation package.

## Implemented PROBE-CONTROLS runner

`controls.run(stage)` compiles and runs these controls only when called by the
separately admitted stage. It never launches on import. The outer 120-second
budget includes all compilation, linking, negative probes, and harness runs.
No automatic extension or retry occurs if seven fixture links cannot fit.

`DeferredDemand` now returns its lazy list from an IO producer action before
calling the consumer. Neither the runner nor the producer forces that list.
The profile oracle requires positive producer self-allocation without a consumer
ancestor. A profile that does not demonstrate that fails the control.

`IgnoredRTS` receives literal `+RTS -M1m -RTS`; with compiled `ignoreAll`, stdout
must be `["+RTS","-M1m","-RTS"]\n`. Compile-in report destinations remain active.

`UnitAllocation` parses/forces its integer argument outside UNIT_ALLOCATION,
then allocates one mutable byte array and returns its size without retaining it.
Two invocations of the same binary request 1048576 and 1114112 bytes. Their SCC
self-allocation difference must be exactly 65536 raw JSON units. Equal-sized
object/profiling headers cancel, discriminating bytes from words. Both raw JSON
reports remain archived; no equality to whole-process RTS allocation is imposed.

Admission must additionally pin the installed `ProfilerReportJson.c` writer
source and the full exact expected stdout for both maintained harnesses under
`controls.maintained`. The source pins must resolve to the frozen original
CheckedBindings.hs and SourceValueScope.hs paths, not a substituted shortened
fixture. Independent review must verify the writer's JSON allocation expression.

The actual profiled compiler cancellation control compiles one fresh tiny module
in a separate cache. It observes a POSIX write lock in `/proc/locks`, binds its
owner to the guard's tracked compiler descendants, cancels, requires cleanup,
and independently reacquires the same inode. If compilation ends before the
lock/cancellation observation, the control fails rather than accepting a race.
This canceled tiny control is never a target timing or attribution observation.
