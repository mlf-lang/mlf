# Actual builtin identity regeneration

The QueryGraph change belongs to the existing 56-module builtin source-identity
closure. The old literal's identity was therefore stale. This evidence is not a
hand-written identity edit or a waiver of the ordinary verification gate.

A separate clean clone at ec41739d1e6a50f4feee7c8131c28c6b162c4298 ran the
unchanged ordinary GHC O0 builder. All 18 preceding commands succeeded. Only
check-candidate failed, exit 1, with exactly `prepared Prelude build source
identity is stale\n` and empty stdout. The original build remains incomplete.
It took 150.672 seconds and peaked at 1,187,954,688 bytes of process-tree RSS.

The maintained generate_builtin_evidence.py collector authenticated that exact
failure and the current commands, inputs, tools and outputs. It ran the actual
built generator, captured 2,220,407 bytes with empty stderr, and re-authenticated
all 2,165 input pins. Its resource guard completed in 85.135 seconds with peak
RSS 186,523,648 bytes. The generation receipt is complete but explicitly does
not verify a repaired candidate or qualify any toolchain.

Both the collector and separate review confirmed that replacing the sole
64-hex identity at byte offset 776 makes the old literal byte-for-byte equal to
the actual stdout. Nothing else changes. The generated stdout was copied
unchanged into bootstrap/MLF/BuiltinPreludeData.hs. The ordinary offline manager
then generated mlf.lock and successfully ran --locked plan; the semantic lock
delta is exactly that literal's source SHA-256.

Old literal SHA-256: 01b68240e93b397ac73874636edc69311ffb7aa89e2fa61dd346ad0416ffcbb8
New literal SHA-256: d2512a3daf981164c3ae49f3e17473942803092d08a95c325da416afd2a8d89c

The frozen failed producer remains at its original absolute prefix, unchanged:
/workspace/scratch/3f83e2ebe290/declid-issue37-generator-source-ec41739d
The copied evidence index records original paths and byte hashes. These are
local provenance checks, not a third-party signature. No native compiler or
native performance gate has been qualified by this generation step.
