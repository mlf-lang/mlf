# Ordinary checked-receipt reuse

**HOLD: no merge and no additional timing samples.** The strict focused fixture
and Foundation raw-output checks passed, but the two timing pairs do not
establish an overall speed improvement. This is an experimental archive, not a
production recommendation.

Baseline: [`fc300bc9`](https://github.com/mlf-lang/mlf/tree/fc300bc9fdc389b585cbef0630fc8915d53e89c5).
Only `libraries/mlf-crates/Bootstrap/InferenceUnit.hs` changes.

## Candidate and safety boundary

The ordinary compiler already produces a checked term. This patch retains that
receipt and reuses it only when the external environment is empty and the actual
implementation root is `XLet` or `XLetRec`. Imported contexts and other roots keep
the original `Open.environment` then `Open.check` path.

The original `Compiler.finishCompilation` still performs constraint solving,
evidence elaboration, checked-term validation, type agreement and source-erasure
agreement. `Open.fromChecked` still constructs the datatype environment and
forces the deferred declaration inventory before the unchanged ownership check.
No raw canonicalization or mismatch waiver is introduced. The original public
`compileGroupBody` projects the same triple. The new helper is also exported
because the module has no explicit export list; the reasoning concerns receipts
obtained internally, not arbitrary forged compiler values.

## Actual evidence

- **Focused O0 and O2:** 55 home modules per lane; 13 cases each, comprising six
  Right, six Left and one exact synchronous demand exception. Each saved 63
  sidecars and the exact 71-byte marker. Complete original raw/typed values,
  ordered parameters/owned bindings, audits and full error messages satisfy the
  frozen gates. The declaration-tail negative requires its precise deferred
  inventory error. All corresponding O0/O2 sidecars also matched.
- **Two ordinary producers:** fresh O2 builds of the real `emlf` entry point,
  each with 95 home modules. Only C's InferenceUnit source differs; entry point,
  other sources, demand flags, packages and two C inputs are shared.
- **Foundation15:** A reproduction and C qualification, then four fixed calls
  in **A1/C1/C2/A2** order. All six match complete CI/CO bytes and ordered
  532-group/539-member/14-owner checks. Complete queries also matched as an
  observation, not a replacement oracle. Only the four later calls are samples.

| C relative to paired A | Pair 1 | Pair 2 | Geometric point |
|---|---:|---:|---:|
| Wall time | -0.82464% | +0.48213% | -0.17340% |
| Total CPU | -0.77932% | +0.52209% | -0.13074% |
| OS peak RSS | -4.99758% | -4.87053% | -4.93407% |

Wall and CPU directions are mixed; their near-zero summary is **not an
established overall gain**. Peak RSS is lower in both observed pairs, about 5%,
but is not allocated bytes, retained heap, GC behavior or a demonstrated cause.
All samples are retained, with user/system components in `results/foundation.json`.
Two pairs do not establish stability or significance. There is no pooling with
other workloads and no native, whole-PR or general semantic conclusion.

## Preserved failure and reproducibility

The earlier historical-reference qualification stopped on baseline A, before C
ran: CI bytes include the builtin dependency's absolute location, which had
changed after restoration. An independent byte/wire audit accounted for that
path and framing difference. The original **INCONCLUSIVE** record remains.
The later experiment used a separately admitted current-path reference and
required fresh A reproduction and full C raw equality before sampling. There was
no runtime normalizer or silent relaxation of the old gate.

`candidate.patch`, the two fixture source files and `expected.stdout` are the
exact tested bytes. `TEST-CONTRACT.json` defines the 13 cases and 63 files.
`REPRODUCE.md` is a portable focused recipe, **syntax-checked only**, not another
executed experiment or the private supervisor. The actual producer and workload
results are separately identified in `results/summary.json` and
`results/foundation.json`, including source/producer/output hashes and all four
raw timing values. Absolute input locations affect serialized CI bytes, so a
portable rebuild is not promised to reproduce the archived CI or ELF hashes.

This package contains no binaries, private execution paths or private
controllers. Publication of this archive does not imply adoption. No new
compiler or target was run while assembling it.
