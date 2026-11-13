# Candidate: reuse childless nodes during canonicalization

Experimental, not merged. Against fixed source `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`.
The source and demand review is complete. The first ordinary producer completed
GHC compilation/linking but was correctly rejected by the final builtin freshness
gate: `prepared Prelude build source identity is stale`. Graph is in the builtin
generator source closure, so its change requires exact canonical regeneration.
The 201.662-second failed run was cleaned up with both locks and lease cleared.
See [the failure record](results/first-build-failure.json). Its source and outputs
remain unchanged; a new isolated regenerated-builtin producer is being prepared.
No gate is skipped or failure retroactively marked successful. Candidate Haskell
correctness and performance are not yet established.

The qualified r17 experiment identifies canonicalize/rebind as 8,830,980,432
profiled allocation bytes, 52.46% of local unify and 14.48% of the total.
That interval includes more than canonicalize and is not a prediction of
available savings or ordinary CPU share. The result is at commit
`84fe794c35693b5a7f854dca5d3a5cd1a61eb3a2`.

This single production hunk reuses GBot, GBotK, GTyCon and GSkolem nodes, while
keeping the existing strict map traversal and tag/binder/flag demand. No child
comparison, graph validation, endpoint admission, rebind permission, public API
or hash-only equality is added or removed. Structural tags use the old action.
See DESIGN.md for the bounded argument and rejection criteria.

A separate 23-case public Graph.unify fixture has passed on the original
ordinary producer, checkpoint `954f5a63e56bc34ef95d6a39b09a63eab0154707`.
That is a baseline result, not evidence that this candidate passes. Direct
canonicalize partial-value/forged-map controls and candidate comparison are
being prepared. Later ordinary measurements retain the fixed ABBA x3 plan,
full artifact equality and fresh query controls. Neutral or regressive outcomes
will be reported, not resampled until favorable.

Native-generation A/B and fixed-point work remain paused. No latest-main
integration, full compiler90 regression, reliable speedup or GHC parity claim.
The local candidate source commit is `768227fd023b3231eb7d8ce8cde43661b7bfef28`;
its production Graph bytes match this publication, but the public commit also
contains this documentation and is a distinct identity.
