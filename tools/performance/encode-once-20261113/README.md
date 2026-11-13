# One fresh encoding for initial input and derived query nodes

Status (2026-11-13): **real GHC 9.14.1 build, focused semantic validation, and 12 ordinary cold-build samples completed** against frozen `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`. See [ordinary results](results/ordinary-summary.json). No native-generation A/B or fixed-point run was started. This experimental candidate is not merged and has not passed latest-main integration or CI.

The one-encoding helper passed the same real fixture on both producers (18 in-memory cases and 4 real publication/reopen cases each), 3 maintained codec/query modes each, 2 candidate first-error controls, and 5 CLI controls per relink. Across 12 fresh foundation14 samples (ABBA × 3, 6 per side), all 475 queries were fresh and all 3 artifacts plus ordered queries matched exactly. Ordinary allocation was stable at 60,564,698,920 baseline versus 60,385,303,368 candidate bytes, **179,395,552 bytes / 0.2962% less**. Wall medians were 21.229 versus 20.870 seconds (observed -1.69%), but the candidate was slower in 2 of 6 adjacent pairs: **no reliable runtime speedup established**. This narrow reuse does not remove the whole ENCODE bucket.

The source and demand review below predates execution; its semantic limits still apply. Original recorded code/fixture/runner inputs remain immutable.

## Patch scope and demand review

`candidate-encode-source.patch` changes only `libraries/mlf-crates/Bootstrap/CrateGraph.hs`. A local `recordInputAndDerived` helper calls unchanged `QueryGraph.encodeHashed` once, then unchanged `recordDigest` twice. Only `recordInitialBindings` and `recordDatatypes` use it; `input`, all other query recording, verification/audit rehashes, the codec, and publication are unchanged.

The input update still precedes the derived update. The first call uses `inputKey wanted`, empty reads, no location, and no pending payload. Its returned pair is pattern matched before the derived call. The second uses the original `wanted`, exactly `[edge leaf]`, and the fresh digest/bytes with a persistent location. Neither call trusts an old digest; `recordDigest` retains its existing full `sameNode` comparison. Both updates use a digest freshly computed from the exact value by the unchanged schema-6 encoding. No checking or value field is dropped.

The original `record` returns a lazy `mapEither` result. The helper retains that outer shape. `mapEither` propagates the first encoding's `Left` before touching the session. On success, matching the digest/bytes pair and the first `recordDigest` pair retains the first session constructor demand. The caller still forces the second returned pair before recursing over remaining inputs. Wanted keys remain lazy; no extra `seq`, eager traversal, or early hash comparison was introduced. Sharing is intentionally local to one value in one pair of records.

This is not a claim that two IO computations and one IO computation have identical behavior under every external failure. A second allocation/hash execution can no longer fail transiently after the first succeeds. The intended production domain is deterministic successful encoding of finite, admitted metadata, with the first operation's existing error propagation retained. The fixture checks several partial host failure priorities explicitly; it does not prove all partial-value, asynchronous-exception, OOM, or arbitrary forged-session cases equivalent. Byte arrays must remain immutable after hashing, as required by the existing query protocol.

## Real-API regression source

`fixtures/EncodeInputReuse.hs` uses the actual `CrateGraph.recordInitialBindings` and `recordDatatypes` entry points. It is the same source for baseline and candidate builds. Its reference functions freeze the original two-`QueryGraph.record` protocol, using unchanged production value encoders. It never calls the new helper directly, injects an opaque checker receipt, substitutes digest equality for byte equality, or fabricates a successful run.

Mode `pure` performs real encoder/hash IO in memory but does not publish files. Expected output is 18 `PASS<TAB>case-id` lines followed by `SUMMARY<TAB>pure<TAB>18`. It covers:

- Empty, singleton and mixed batches; quantified/higher-kinded contracts, class ordering, protection, Unicode and equal values with distinct identities.
- Same-key sequential replacement, matching and changed old nodes, already-active nodes, and an old node with the **correct content hash but wrong reads/location**.
- Exact session metadata, every node's ordered reads and payload location, and all pending payload bytes. Session directory paths are deliberately excluded so isolated publication roots can be compared.
- Unchanged, changed and deleted authoritative input propagation to an old dependent with a repeated dependency edge.
- Five partial-host failure priorities: bad type before classes/list tail, bad declaration before tail, bad value before bad session, good value before bad session, and empty input not forcing the scope. The successful result is fully rendered inside the exception catcher, not inspected only to `Either` WHNF.

Mode `publication FRESH_ROOT` requires an absent root and no inherited `MLF_QUERY_FAILPOINT`. It creates separate `frozen` and `production` stores, invokes the real publisher, reopens from disk, and exercises cold, warm, changed and deleted inputs. Expected output is four `PASS` lines then `SUMMARY<TAB>publication<TAB>4`. It compares exact file inventories and bytes after each phase, including generation/current files and retained payloads. It never deletes or reuses an existing root. The parent directory must already exist.

## Validation gate owned by the runner

Build this fixture separately against the frozen and candidate module products with the project's original package/language/C dependencies. Do not mix `CrateGraph` interfaces or objects between builds. Preserve the authorized process/resource controls and record source, patch, compiler, flags, binary and log hashes. Run both modes in each build; compare complete expected case coverage and exit status. Missing cases, a truncated summary or any exception fail the gate.

The fixture does not introduce a runner or automatic compilation entry point. Existing query-generation/index/codec tests and semantic controls remain necessary, including publisher failpoints, checksum/corruption rejection and codec bounds. A representative large real artifact must retain its existing resource-limit behavior; the fixture intentionally does not create multi-million-element values just to trigger default limits. Repeated IO failure injection and arbitrary partial sessions remain separate work, not reported passes.

After semantic gates, run the same fresh foundation14 target and exact `.mlfci`/`.mlfco`/`.queries` plus ordered-query oracles. Measure the paired-site encoding contribution rather than assigning the whole ENCODE bucket to this change. Any speed claim requires ordinary measurement under explicit authorization; native A/B and fixed-point remain paused.
