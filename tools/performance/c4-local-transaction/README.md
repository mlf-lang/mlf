# Current graph control output checks

`contracts.py` parses the complete public, transaction and nonmonotone-layout
control output used by `../patricia/run_integrated.py`. It checks typed summary
values, ordered case boundaries, independently authored outcome flags and
nonempty success/rejection coverage. `test_controls.py` exercises truncated,
duplicate, reordered, malformed and vacuous output using the current graph
fixture matrix in `../patricia/controls/graph/expectations.json`.

The C4 source-migration ledger, historical runner, duplicate Haskell controls
and fixed-14 qualification CLI were retired with the history support subsystem.
The directly compiled reference algorithms and behavior controls now live in
`../patricia/oracles` and `../patricia/controls`. The nine authored file cases
are in `../patricia/fixtures/file-cases.json` and run through
`../patricia/file_cases.py`.

For the original C4 experiment and its exact migration proofs, inspect this
folder at commit `496dcae024cae1a93096d9bdb9d6b93e57359dc0` in Git history.
Ordinary builds and tests do not fetch or certify that historical state.
