# Selector differential controls

`run_selector_differential.py` compiles `SelectorDifferential.hs` against an
existing authenticated GHC producer. It checks 154,072 selector, interface,
identity, error-order and demand cases, plus 6,162 collection cases.

`FrozenSelectors.hs`, `FrozenSelectorMap.hs` and `FrozenSelectorSet.hs` are ordinary
independent reference fixtures. Their algorithm bodies are retained from the
fixtures present at `496dcae024cae1a93096d9bdb9d6b93e57359dc0`; selector imports
explicitly use the reference Map and Set. They share representation types and
primitive operations with the current compiler, but call no current selector or
collection implementation. The executable also checks current collections
against independent list expectations.

The runner records the exact files used in each invocation, verifies those files
and the producer after execution, and checks observed result counts and failure
propagation. Current source edits do not need new historical hash allowlists or
inverse source transformations. Old migration manifests and audit prose remain
available in the cited Git commit.

```sh
python3 -B tools/performance/crate-optimizations/p1/run_selector_differential.py \
  --source-root . --build-receipt .mlf-build/shared-ghc/receipt.json \
  --output .mlf-build/selector-differential
```
