# Foundation source key measurement protocol

Use the actual PR head for the v6 source driver. Build the old and new
CrateSession/CrateQuery modules in one GHC 9.14.1 -O2 executable. Only rename
modules/imports to select the plain arms. Both call the normal compileSpecFile
entry and hash the same executable. The probe copies add clock boundaries.
Use one absolute source tree, fixed dependency/prelude prefix, the same 14
modules, crate identity and Version edit for all arms of a run. Prepare the
builtin before timing. Each stage is a new process. Cold means empty query
directory, with normal OS page caching.

Before editing production, run old plain then old probe, each cold/warm/edit.
Require identical reports, keys, full cache file contents and final artifact
bytes for corresponding source states. For the comparison, repeat this check
in the final combined executable for both versions. Time the plain order
old/new/new/old. Each sequence gets an empty directory, then a warm run, then
one edit (0.3.0 to 0.3.1). Finally run old probe and new probe once in that
order on fresh caches. Keep all samples, errors and logs. Report both plain
samples per version or their mean, with no outlier selection. Require 504/0,
0/504 and 1/503 inferred/reused, unchanged keys for the other groups, 83
shared contexts and matching complete final interface/object bytes across arms.

Use monotonic process launch-to-wait4 wall time and per-child peak RSS.
Report on-disk logical bytes across the entire cache. Probe key forcing ends
at the strict host Text with its scalar count. The following write includes
UTF-8/FFI, system calls and buffered file writes. The SHA primitive reads the
staged file. Record-read timing forces the decoded Either through raw object
admission, including context reads and validation. PreparedRaw timing forces
source-specific admission separately. Finalization, final output and inference
stay in the total. No filesystem flush, simulated pure-I/O cost, isolated
pure SHA cost, or timing proportional to saved bytes is assumed.
