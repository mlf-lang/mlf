# Archived source-query storage experiment

This offline prototype packed and restored `MLF-QUERY-CACHE-1` records from the
source-query-v6 compiler. Its reader required a complete query record as the
root of each bundle. The codec, CLI, overlay and their controls are available
in the [archived experiment](https://github.com/mlf-lang/mlf/tree/0704d216b8cf6d887d3737efa30a2eae3c152f0a/tools/experimental/artifact-representation).

The historical [storage measurements](RESULTS.json), [read and update measurements](READ-UPDATE-RESULTS.json),
[codec and CLI results](VALIDATION.json), and [overlay results](OVERLAY-VALIDATION.json)
remain available here. The current checked crate artifact format is documented
in the [crate compilation guide](../../../docs/crate-compilation.md).
