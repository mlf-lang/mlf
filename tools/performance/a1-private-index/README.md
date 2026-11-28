# A1 private-index controls

The Patricia graph suite compiles the four private-export rejection fixtures in
`controls/negative/`. Its builtin suite uses `current/CurrentBuiltinControls.hs`
to check the decoded builtin against the canonical prelude. See the
[Patricia runner instructions](../patricia/README.md).

Performance runners share `helper.py` for process supervision, resource limits
and producer authentication. Run its platform tests and the shared builder's
toolchain discovery tests from the repository root.

```sh
python3 -B tools/testing/run.py release-performance-a1-platform
```

## Historical A1 experiment

The fixed P3/A1 comparison, frozen compiler inputs, positive controls and
preparation tests are available in the [archived experiment](https://github.com/mlf-lang/mlf/tree/0704d216b8cf6d887d3737efa30a2eae3c152f0a/tools/performance/a1-private-index).
Use that revision's [reproduction instructions](https://github.com/mlf-lang/mlf/blob/0704d216b8cf6d887d3737efa30a2eae3c152f0a/tools/performance/a1-private-index/README.md)
with the recorded base and candidate. The [measurement report](../../../docs/performance/a1-private-index/README.md)
gives the results and their limits.
