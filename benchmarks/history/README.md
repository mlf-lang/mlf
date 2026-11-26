# Historical benchmark source transitions

The former artifact-binary parent manifest and Types source, and the release
scripts that repeatedly reconstructed them, are archived at commit
`496dcae024cae1a93096d9bdb9d6b93e57359dc0`. They are no longer inputs to the
current benchmark gate.

Current workload sources, upstream provenance, explicit adaptations and input
hashes remain in `benchmarks/manifest.json`. The native benchmark campaign
still checks execution results and the retained timing-report contract.

See [historical infrastructure retirement](../../docs/testing-history-retirement.md)
for archival checkout instructions and the distinction between current input
identity and a historical source-transition proof.
