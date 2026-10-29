# W1 validation record

The repository-adapted finite suite was executed successfully after the original
private study, against the authentic ordinary baseline and W1 producers. The
adaptation did **not** inherit a PASS from the private harness. Its complete
three-stage run passed under the original resource limits in 47.956031 seconds,
with exit zero and no owned descendants left in the guard's visible namespace.
This duration is a test-suite duration, **not a compiler performance sample**.

- 20 independent transport cases on both sides: 40 executions.
- 20 exact mocked fault/call-order cases, without changing expected results.
- Four actual supervised/unsupervised child and grandchild cleanup cases.
- Actual GHC eligibility: 33 owned opens and closes, CLOEXEC observations,
  positive poll count and unchanged open-FD count after warmup.
- Unsupported-header fallback and the unchanged versioned syscall ABI check.
- Both rebuilt C objects match their respective official producer objects;
  copied Haskell dependency objects remain unchanged, with only the two intended
  fixture Main compilations. All input and object inventories were rechecked.

Portable suite receipt SHA-256: `6b48ab0978d4b7fc622f01cfcdf0b6c7bd0c4ff022843920cb5c56a79d117337`.
The machine-specific receipt and logs are preserved privately rather than
published as repository inputs. The full source/test scripts and literal
fixtures are in this directory. This record is documentation added after that
run; all previously tested package files and all compiler inputs remain exactly
unchanged. The static inventory/syntax check is also rerun on this final package.

The official W1 producer, independent seven dependency-object checks plus
corrupt-object rejection, P1-P3/A1/F1 gates, direct host/source smoke, host IO,
host arrays and six identical regenerated locks/locked plans were checked.
Two earlier outer exact-gate sessions were interrupted. Their incomplete guards
remain incomplete in the private evidence. Successfully finished component
receipts, exit codes, input and log hashes were independently reauthenticated;
only missing final plans and end authentication were completed under a new
terminal guard. This is composite recovery, not an uninterrupted full campaign.

The separate [nine-leg measurement](MEASUREMENTS.md) retained every prescribed
sample: wall median improved 3.060352%, but reaped-child CPU increased 1.061419%.
The predeclared gates were met narrowly. W1 remains 9.719279x plain GHC on this
explicit frozen slice, not the requested <=3x. No stronger statistical,
cross-host, macOS, Windows or native-bootstrap performance claim is made.
