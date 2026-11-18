# Edge observer v3 finite gate (pending execution)
Research only, not production optimization or reuse. Exact main fc300bc9 oracle,
v2 observer d9c14d39, offline ledger 326a6c06. Adds ordered parent/original child/
canonical child/ancestor/result tuple only after existing dominated Bool branch.
Earlier Gen and missing-child errors remain unkeyed. Global Euler token remains.
No cache, skipped validation, mutable graph changes, or native qualification.

Independent source review corrected the initial overbroad Gen-before-poison
assertion: a successful outer edge precedes the failing inner edge. Exact valid
and alias tuples are also checked. Source-review only is not semantic validation.
Five extra events per edge reach the existing 8192 cap sooner; claims must remain
finite-fixture only. New O0/O2 gate retains original 14 cases, poison/error
expectations, original validator oracle and bad-cache mutant negative control.
Requires all 71 sidecars equal between O0/O2. No performance claim, and no repeat
Foundation profiling. Results must be audited after actual runner completion.
