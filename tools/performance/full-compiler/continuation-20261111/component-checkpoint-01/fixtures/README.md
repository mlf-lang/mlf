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
