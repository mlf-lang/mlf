# New-batch ordinary producer adapter

Source prepared for the separately authorized November 13 rerun. This directory
does not contain a preapproved admission or fabricated execution receipt. The
author only statically inspected this adapter; it has not been invoked by its
author. Historical sources, admissions, markers, and receipts remain unchanged.

## Entry points

Use the same resolved `/usr/bin/python3` for preparation, original build,
qualification, and later r13 controller. Do not call `_qualify` directly.

```text
/usr/bin/python3 -B $ROOT/ordinary/controller.py run BUILD --admission $BUILD_ADMISSION --sha256 $BUILD_ADMISSION_SHA
/usr/bin/python3 -B $ROOT/ordinary/controller.py run CONTROLS --admission $CONTROL_ADMISSION --sha256 $CONTROL_ADMISSION_SHA
```

These are separate single-shot stages, not a shell script to chain or retry.
Each creates its own exclusive claim and fresh stage directory. Failure retains
the claim and all evidence. No native A/B, fixed point, or target compile occurs.

BUILD600 uses the exact original command tail:

```text
<resolved-python> -B <source>/tools/shared/build.py --bootstrap-only --optimization 2 --build-dir <ordinary>/build/producer
```

The unchanged r13 `guard.py` is the outer supervisor, with two current locks,
durable epoch lease, subreaper/pidfd cleanup, and a 600-second total window.
Inside it, unchanged original `resource_watchdog.py` retains 600 seconds,
AS6144MiB/RSS5120MiB/output2048MiB/free-disk5120MiB and original CPU limiting.
The outer bound is the whole ordinary directory, including `ordinary/tmp`;
the original watchdog's 2048MiB output accounting covers its stage directory.
The r13 outer supervisor's whole-directory bound remains its unchanged 4GiB.
This is a fresh reviewed adapter, not byte-identical replay of the older wrapper.

CONTROLS has the same supervision with 120-second bounds. Its qualifier verifies
the actual watchdog/guard ancestor chain, start identities, active lease, guard
configuration, and supervisor lock ownership before and after qualification.
It uses the unchanged original authenticator through r13 `oracles.authenticate`:
137 shared modules, four host modules, 13 outputs, 284 objects/interfaces,
original O2/demand/package flags, original builtin gates, exact C commands, and
five exact CLI stdout/stderr/exit controls. No old Main.o is reused.

## Admission JSON contract

Every `path`/`sha256` pin refers to a real current file. `bytes` is optional except
where explicitly generated; when present it is checked. The coordinator supplies
the actual approval and review, not this program.

```text
schema: "r14-ordinary-admission-v1"
approved: true only after current review
phase: "BUILD" or "CONTROLS"
budget_seconds: 600 or 120 respectively
source: absolute ROOT/source
r13: absolute exact-restored sparse-attribution-r13 directory
workspace: new epoch workspace
epoch: current lock-epoch.json pin
locks: [epoch.shared, epoch.reproduction]
environment: current coordination/environment.json pin
python: pin of resolved /usr/bin/python3 executable
adapter_code_pins: {absolute ordinary/controller.py: its current SHA256}
source_pins: {absolute original source input: actual current SHA256, ...}
toolchain_evidence: [pins of actual install/restoration evidence JSON, ...]
toolchain_files: {absolute canonical regular executable/library/evidence file: SHA256, ...}
review: {complete: true, receipt: pin of current adapter review}
prior: {} for BUILD
```

CONTROLS `prior` must have exactly:

```text
controller: pin of ordinary/build/controller.json
outer: pin of ordinary/build/outer/guard.json
producer: pin of ordinary/build/producer/receipt.json
```

`source_pins` must include `shared-sources.json` and these original files:

- `tools/shared/build.py`
- `tools/shared/test_direct.py`
- `tools/shared/resource_watchdog.py`
- `tools/performance/a1-private-index/helper.py`
- `tools/shared/verify_builtin_prelude.py`
- `tools/shared/builtin_prelude_identity.py`
- `tools/shared/verify_prepared_libraries.py`

Additional genuine source pins are allowed. The source must have exact f9 HEAD
and no tracked modifications. The original build/authenticator independently
checks its full source, configuration, toolchain, package, output and log inputs.
Toolchain evidence pins are integrity inputs, not a programmatic certification
of arbitrary evidence JSON semantics; the coordinator reviews their contents.

The explicit environment uses only the same allowlist as r13. For both ordinary
stages it must keep `TMPDIR=<ordinary>/tmp`, already created, and otherwise remain
byte-for-byte the same. Preserve this environment file for r13; only the profile
work's bounded TMPDIR may differ later. No semantic/query, preload, audit, or
extra package overrides are allowed. Package discovery/provenance remains the
real producer's responsibility, not values filled into a synthetic receipt.

## Actual outputs, if stages succeed

- BUILD: original `build/producer/receipt.json`, original logs/objects/binaries,
  `build/bounded-receipt.json`, true outer `build/outer/guard.json`, and the new
  `build/controller.json`. Both watchdog and outer cleanup must succeed.
- CONTROLS: exact five stdout/stderr files, `controls/focused-control-receipt.json`,
  both real supervision receipts, `controls/controller.json`, and
  `relink-inputs.json` using the frozen insertion map's 94 Emlf non-Main modules.
  It does not depend on the missing historical workload.json.
- Only after completed CONTROLS: `ordinary-handoff.json`, directly usable as the
  r13 admission's `ordinary` object. Its `build_outer` is the actual outer guard,
  not the inner watchdog or a copied historical summary. Its command still ends
  in the original build argv, as r13 provenance requires.

The adapter never generates `complete:true` before actual command success and
current evidence checks. No old setup SHA, boot ID, inode, receipt digest,
package path, process identity, or cleanup conclusion is hardcoded. Only source
revision and immutable r13 implementation hashes are fixed.
