# P2 writer wire transition

The historical 2503 P2 controls remain unchanged on disk. The active Patricia
adapter records every generated change and verifies exact inverse diffs.
Their pure encoders, fingerprints, laziness and independent frozen oracle still
run. Their text-writer comparisons run against the two prior writer definitions
reconstructed from the complete authenticated pre-binary CrateArtifact source
through delta008. They do not claim that current public writers emit old bytes.
The new envelope-only constructor is explicitly refused by that legacy projection.

The coordinator runs all retained controls, then requires the separate current
binary writer suite to finish before returning. Current writers must produce
actual MLFBIN bytes. A host-only implementation independently checks the fixed
header, contiguous sections, reference widths, total length and CRC32 (including
the standard known CRC vector). This is not an independent full typed decoder.
Production graph/typed decoding is separately compared with complete semantic
bytes from the frozen old encoders, not candidate-derived expected bytes.

All eight old raw fixture shapes plus the legacy object constructor are covered
by raw typed wire checks. The three unequal header/body-context fixtures remain
raw controls, not successful semantic-admission claims. Six explicitly listed
valid cases exercise current public readers on both writer methods and files
written by the original legacy writer. Five corruptions check version, checksum,
schema and semantic metadata/body pairing rejection. Each writer method also
checks first-write failure, preservation of the complete first file after a
second-write failure, temporary-file absence, and NUL validation before object
or payload demand. The paired text argument is deliberately bottom in current
binary writes, proving it stays unused.

Counts and result labels are separate: 2503 retained/projection controls and
184 actual binary writer controls. Original P1, supplemental native compatibility,
P3, production sources, frozen history and the fixed integrated runner are not
changed by this adaptation. No performance result is inferred from these checks.
