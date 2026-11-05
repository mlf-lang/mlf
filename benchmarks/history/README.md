# Artifact-binary benchmark source transition

These two fixtures preserve the exact benchmark manifest and Bootstrap.Types
source used before the artifact-binary source transition. The manifest is from
commit 80a8bf4407d159eab8e7735b4b5a65581d172426, where its historical Types pin
no longer matched the newly published live compiler source.

The live manifest now identifies the current source for future benchmark runs.
The existing artifact-binary source contract authenticates the complete current
source inventory and reconstructs the old Types bytes with its pinned delta015.
The release provenance check requires exact archived evidence and permits only
this Types pin change plus the two evidence pins in the live manifest.

Existing benchmark measurements and receipts are unchanged. These checks prove
source identity and reconstruction, not unchanged runtime performance, benchmark
correctness, or a new measurement on the current compiler.
