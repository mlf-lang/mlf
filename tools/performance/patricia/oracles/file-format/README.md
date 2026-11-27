# Independent file-format oracle

These fixtures were extracted from `tools/shared/` at
`8c4556416023ac727e3fb2294070358a3dae8d9e`. Before extraction, all three original
SHA-256 identities were checked:

| File | Original SHA-256 |
| --- | --- |
| `artifact_binary_reference.py` | `de312e3415eba178b649d30b6fa2b113fc864455de16603a5902af034d036422` |
| `artifact_binary_typed.py` | `b703af43e334733c9ccb49f2a4e5a63a615f6bd065c8c464bdd3841ed54e369d` |
| `artifact_structure_contract.json` | `20f1df71bc2fc1ebe01247dc986b01029b3e8e0c4a89f7dcc8cc517f756cf5a1` |

The reference codec and schema JSON are byte-identical to those inputs. The
typed reader retains the type validator, value accessors and builtin declarations
used for closed/open comparison. The unused query cache inspector and schema
sample generator were removed. The validator `validate_type` accepts the
keyword-only `primitive_max` (default 131), checks that it is one of 131 or 136,
and uses that value for the existing primitive-code bound. All schema traversal,
framing, arity and validation algorithms are retained. This replaces runtime
source substitutions through bounds 131, 133 and 136 with a direct function
call. No current production algorithm was copied into the oracle.

`open_file_comparison.current_dependency_decoded` alone requests 136 and then
checks the literal forward/reverse identities and uniqueness of the five added
primitive declarations. Own artifacts and linked terms use the unchanged 131
default. Tests exercise these distinct domains and malformed inputs directly.

`frozen_file_oracles.py` loads these checked files without Git, temporary source
rewriting, PR fetching or release-marker authentication. Current compiler inputs
are validated by their own build receipt. The fixed fixture digests in
`open_file_comparison.py` must not be updated as a way to admit compiler output;
a deliberate oracle change needs its own independently justified behavior.
