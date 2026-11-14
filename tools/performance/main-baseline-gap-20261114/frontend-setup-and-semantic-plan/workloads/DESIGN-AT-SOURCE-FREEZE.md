# Fixed same-input frontend workloads: source preparation only

This package freezes inputs and templates, not a runner, admission, timing sample
or successful semantic qualification. Main is the authenticated commit
`fc300bc9fdc389b585cbef0630fc8915d53e89c5`. No source or result from the F25
optimization chain is substituted for this main baseline.

## Exact fixed inventory

Cell order is baseline-0; flat_functions at 16/32/64/128/256;
higher_order_chain at 16/32/64/128/256; Foundation14. Each cell has the fixed
ordinary order M,G,G,M: exactly 48 future legs, not 48 completed measurements.

* Eleven shape Main.hs files: 41,439 UTF-8 source bytes in total.
* Foundation14: 14 exact copied main files, 173,594 source bytes. This is the
  existing selected anchor, not all 15 modules in the package manifest; Regex
  is outside this anchor. No extra GHC Main or wrapper is added.
* Combined: 25 files, 215,033 bytes. Both endpoints use each cell's same ordered
  source paths and identical bytes. Foundation adds only its common source root
  to GHC's lookup path; fixed MLF.Primitive comes from the qualified private unit.

`CELLS.json` records every byte/hash, mapping and known static source quantity.
For generated shapes, binding declarations/signatures are exact: baseline 2,
flat n+2, higher-order 5. Textual composition count is n for higher-order.
These are source counts, **not** graph visits, constraints or query groups.
Foundation declaration counts remain unknown because no Haskell parser ran.

## Pure generator provenance

`generator-source.py` is the full byte-exact main generator source.
`generator-functions.py` contains its exact HEADER/MAIN literals and
balanced/program/expected definitions. The source preparation script verified
an AST allowlist and executed only those definitions in a restricted namespace.
It did not import the repository module, call generate(), run its filesystem
entry, or use any repository helper/loader/guard/lock/compiler.

The 11 programs are exact outputs of main's program(family,n), generated with
explicit families/sizes rather than the default matrix. Foundation copies were
checked against both main's complete 3,876-file source inventory and the frozen
14-module closure. `GENERATOR-PROVENANCE.json` records originals and extraction.

Independent closed-form oracles use inputs [-1,0,7]: baseline x; flat
n*x+n*(n-1)//2; higher-order x+n. The output is decimal integer plus LF.
Values stay far within the host Int64 range. These mathematical/source oracles
are not observed target results or universal partial-value equivalence proofs.
Foundation is a library with no program entry or numeric runtime formula.

## Future qualification, before any timed legs

The original genuinely qualified main emlf is the independent ordinary semantic
reference. Its exact binary/producer and BUILD/CONTROLS review pins are recorded
in COMMAND-TEMPLATES.json. It is not the stats-copy candidate, and the existence
of those main baseline reviews does not qualify a workload cell.

For every cell, a separately bounded, reviewed qualification must first run the
reference compile-crate route on these inputs, retain the complete checked pair,
ordered query report and query publication outputs, and establish their actual
freshness/ownership. For the 11 executable shapes, template --run-crate checks
on the reference checked product must match the independent three-input formula.
This uses the interpreter, not native program generation. Nothing ran here.

The later qualified stats-copy is the candidate, not its own oracle. Its fresh
compile uses the same source list/spec/dependencies and must compare complete
raw checked/query artifacts against the reference at the **same concrete
output paths**, with full archive/clean-path reconstruction and no normalization.
The separate runner must implement and authenticate that file flow; this input
package does not implement it. Semantic controls are outside the 48 timed legs
and need their own future bounded protocol, not hidden extra samples.

GHC must genuinely accept the same input bytes through the frozen typed-only
flags (-fno-code -fwrite-interface -no-link), with fresh exact interfaces and
verified private-package/tool provenance. Declared module-to-.hi path templates
are expectations, not generated outputs. GHC typed acceptance is not a GHC
runtime formula test or end-to-end equivalence with MLF's extra checking,
serialization and publication work. There is no cross-compiler raw-byte oracle.

All current-main actual query counts, typed interface inventories, reference
artifacts and candidate artifacts are null. In particular, **475 is not reused
as a main oracle**. Future qualification must determine real counts without
post-hoc sample selection; every measured leg must then meet its frozen fresh/
zero-reuse and full query/order/product contract.

## Templates and remaining boundaries

COMMAND-TEMPLATES.json lists each exact source/spec field mapping, reference and
stats-copy argv, typed GHC argv and formula controls. Setup and per-leg output
paths deliberately remain placeholders. Resolve them only from independently
qualified actual setup and a new reviewed stage; recursively pack the final
fields after binding paths. Placeholder JSON is not a runnable crate spec.

SETUP actual execution/qualification is still pending when these inputs freeze.
No counter implementation, performance runner, native path, lock, epoch, active
copy or admission exists here. Counters, CPU/GC sampling, output parsing,
resource caps and the fixed 48-leg single-attempt schedule still need an explicit
future execution source/actual gate. Existing published timing data were not
recomputed. The 62 input checks are only AST/file/contract checks.
