# Header naming reference and controls

These are ordinary, directly compiled Haskell fixtures. The native-library gate
copies them together with `../HeaderNamingOracle.hs`, records their actual input
bytes and verifies the snapshots before and after execution. It does not read
old Git objects, extract function bodies or reverse source transformations.

`HistoricalHeaderNames.hs` preserves the four naming functions previously read
from Git blob `dd5b4630a80803c19afdb219dba2dc4bffc3ea1b`. It uses current shared
foundational modules and is not a complete historical compiler.

`HeaderValidationHistorical.hs` and `HeaderValidationCurrent.hs` are the final
prepared control sources from `header_validation_adapter.py` at commit
`496dcae024cae1a93096d9bdb9d6b93e57359dc0`. They retain the original duplicate
error, datatype/constructor table, complete entity identity, Unicode naming,
encoded-prefix and forged-primitive checks. The historical lane invokes the
reference functions and historical oracle controls. The current lane invokes
production naming and the independent current oracle.

All three materialized modules were verified byte-for-byte against that
preparation before removing it. The old commit retains the original extraction
procedure for historical reproduction; current qualification uses the checked-in
sources and real compiler execution.
