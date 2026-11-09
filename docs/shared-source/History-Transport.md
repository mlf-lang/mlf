# Frozen history after the PR #25 squash

The reviewed history-cleanup mappings in `tools/testing/history_refs.py` remain
unchanged. They still identify exact original and rewritten objects, their
whole-tree hashes, and their object kinds. Historical reads still reject the
removed generated results and paper PDFs, unsafe paths, and unknown identities.
An unavailable rewrite may still resolve to its exact original object; the
published-mapping gate separately requires the reviewed rewritten object.

PR #25 was squash-merged into the PR #22 branch on 2026-11-05. Its integration
commit is not a descendant of every historical commit on the source branch.
In particular, the mapping from `2ea93adf6d8c76857e0d202a033e9bfee191e444` to
`bbed4764fdf6f0280b60299ebee67301e813a669` retains exact object/tree identity,
but the rewritten commit is not an ancestor of the squash integration.

The publication gate keeps direct ancestry as its normal rule. Only that one
rewritten historical commit has a reviewed squash-transport exception:

- Source tip: `90319e3b8c3a7758cd68b3b6474ba0dff6a61923`.
- Squash integration: `d52fb5a7c931fbd8d5262bbaf77f5babe0089baa`.
- Integration's exact, sole parent: `0b738335a62b6f23a5b945da793c939b2b116b88`.
- Both source and integration whole trees: `44c4aadf0e6799c9ef16bc2899fe14557f6cd802`.

The verifier checks these actual object kinds, trees, and parent list. It also
requires the rewritten historical commit and prior target to be ancestors of
the source, and the integration to be an ancestor of the current `HEAD`.
All proof operations ignore Git replacement objects. Reachability is not
cached, so changing `HEAD` cannot reuse an earlier success. Missing objects,
unrelated same-tree commits, and unreviewed transports fail closed. This proves
the reviewed exact-tree integration, not preservation of source ancestry or
that later commits have left the integrated files untouched. Future squashes
require new explicit review; they are not accepted by a generic same-tree rule.

## Reproducing the checks

Use a full-history checkout. Before the offline checks, run:

```sh
python3 -B tools/testing/prepare_history_refs.py
python3 -B tools/testing/test_history_refs.py
python3 -O -B tools/testing/test_history_refs.py
tools/release/check.sh
```

Preparation materializes all pinned squash evidence, even when direct
ancestry already suffices for the current checkout. It fetches only a missing reviewed source from `origin` at
`refs/pull/25/head`, and requires `FETCH_HEAD` to equal the exact pinned source
SHA before accepting it. The PR ref is only a locator; its name is not proof.
The source branch may be deleted, and no sibling PR branch is required.
With the source object already present, preparation is offline. It never
updates a branch, fetches an arbitrary fallback identity, or skips failed
proofs. Normal historical reads and the verifier never perform a network fetch.

The aggregate release check invokes preparation explicitly, as do shared-host
CI jobs before building. Unit controls cover missing and wrong objects,
mapping/tree/type mismatches, wrong or extra parents, all required ancestry edges,
changed `HEAD`, replacement objects, unrelated same-tree commits, and an
isolated checkout fetching the exact source or rejecting a moved ref.
