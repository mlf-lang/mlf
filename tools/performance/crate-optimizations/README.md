# Crate optimization controls

CI runs the selector (P1), fingerprint (P2) and prefix-encoding (P3)
controls against the current GHC-hosted compiler. With an existing GHC 9.14.1
O2 producer, run the same suite from the repository root.

```sh
python3 -B tools/testing/run.py patricia-integrated -- --suite p123 \
  --producer .mlf-build/shared-ghc --output .mlf-build/crate-optimization-controls
```

The [Patricia controls](../patricia/README.md) compile the independent
Haskell reference implementations and exercise the current selectors,
fingerprint and artifact writers, and prefix encoders. The [selector differential](p1/README.md) also runs P1 on its own.

The [former standalone runners](https://github.com/mlf-lang/mlf/tree/0704d216b8cf6d887d3737efa30a2eae3c152f0a/tools/performance/crate-optimizations) and their
[native-library compatibility audit](https://github.com/mlf-lang/mlf/blob/0704d216b8cf6d887d3737efa30a2eae3c152f0a/tools/performance/crate-optimizations/p2/NATIVE-COMPATIBILITY-AUDIT.md) are archived with the source
projections and manifests used for those experiments.
