# Fixed 48-leg main sampling, disabled source

Actual combined qualification is now frozen at report `9293db94…`: original failed SEMANTIC remains failed; unchanged 84 commands plus the separately completed suffix cover all 12 cells, 24 qualification RTS records and original A/stats B/GHC typed artifacts. This source consumes those exact records, never reruns reference/show/formulas or builds/relinks anything.

## Executed plan, if separately admitted

One controller and worker serve two sequential scopes, `E/sampling-01` and `E/sampling-02`, where E is the accepted `main-gap-setup-run04`. Each block runs exactly four runtime-before, 24 measured legs, four runtime-after commands: 32 children and 24 mandatory RTS reports. Total 64 children, 48 measured legs, 48 RTS. The original fixed per-cell order is M,G,G,M. First block: baseline0 and five flat-functions cells. Second: five higher-order cells and Foundation14. The two endpoints use the same ordered source files and the exact actually qualified argv. No extra GHC Main, extra source, stdlib install, native generations or counter instrumentation.

Runtime roles are python, shell, ghc and stats-emlf. The original MLF reference binary is not executed again but remains fully pinned in historical provenance. This explicitly resolves the plan's support-command choice; no role is silently treated as a measured sample.

Each guard cap is 600s; each common launch-bound worker deadline is 595s. All child/precheck/hash/oracle time is charged to it; nominal child caps do not enlarge the deadline. The full next 600s cap must fit both the 1,200s sampling ceiling and the unchanged 1,800s post-SETUP total before any admission. Actual already charged qualification is 717,873,335,365ns = failed stage 596,647,140,326ns + completion 121,226,195,039ns. These are lifecycle costs, NOT performance samples. Actual returned guard-call durations including cleanup are added after each block. Block2 is forbidden unless block1 independently passed and its real duration leaves room for a full600s. Failure, insufficient budget, missing RTS, changed raw bytes or any uncertain cleanup stops without retry/substitution/partial-success claim.

## Same-path, same-binary raw oracle

Before each measured leg, require the original logical `E/active/cells/<cell>` absent, with real non-symlink existing active/cells parents. M receives the exact original archived crate.spec bytes and an empty query directory. G receives a fresh empty objects directory. Actual target argv, source spelling, private unit, builtin, report sink and paths affecting published bytes remain the same as qualification. The completed raw tree is compared against that cell's actual B or G artifact names and bytes with NO compiler-SHA/CRC/CURRENT/path exception. The earlier cross-producer relation is not reused to relax same-B comparison. Full query report must equal accepted fresh0-reuse data; GHC must report exactly its actual home module/source inventory and fresh nonempty .hi set, no hidden home rebuild/object.

After each leg, the original guard archives its fixed RTS sink into new scope command evidence and clears it; the entire cell is archived into new scope legs and the active cell is empty again. No old qualification/reference/completion evidence is overwritten or moved. There is no global path/metadata normalization.

The complete old E inventory (7,868 files/490 directories at qualification) is immutable. Block2 additionally consumes the entire independently accepted block1 scope. Only the current scope and the sole current active cell are mutable, never blanket E. Do NOT create both sampling scopes in advance: an unadmitted sibling is an unexpected old-E addition. New worker outputs are only commands/legs; live controller/watchdog/worker-receipt files are not self-referential worker outputs.

## Authentication and timing boundaries

Reuse the original immutable guard, runtime helper, external stats parser, full wire oracle, actual guard ancestry, original double locks, held73/free0 probes, fresh current-boot epoch and one-use claim. Claim input is the original fullpin in immutable launch binding, never a re-pin of changed current content. Completed historical results may cross a reboot with original evidence preserved, but each new scope uses real current resources/locks/runtime.

Retain the reviewed completion policy: full SHA on the complete unique source/tool/runtime/old-output/coordinator-input union at entry and exit; in between, exact inode/device/mode/link-count/size/mtime_ns/ctime_ns, symlink-chain, complete name/type inventory, critical pins and real guard lease/lock ownership. New artifacts get full pins as created and again at exit. This is cooperative exclusion plus boundary attestation, NOT protection against privileged hostile write-and-restore races. Each actual raw oracle remains full-byte. Worker precheck intervals/counts are recorded separately, not compilation CPU.

Fresh application/query caches are not OS page-cache cold: no cache dropping. RTS gives allocation, copied bytes, residency and rounded MUT/GC/Total CPU/elapsed. Child guard elapsed includes monitoring overhead and is not exact target wall_ns; user/system process split is unavailable. Two observations per endpoint/cell are exploratory scale/CPU-GC comparisons, not stable speedup, significance, asymptotic proof or GHC parity. GHC typed-only and MLF frontend emit different artifact sets. Runtime graph visits/copies/constraint counters are not implemented; query publication rows are not substitutes.

## Review/activation/sole safe launch

Required source report schema: `main-gap-sampling-source-review-v1`; complete/source_gate_passed true, blockers empty, exact source_package_manifest fullpin. Source PASS is not actual sampling acceptance.

After that review, exclusively materialize only sampling-01: save exact controller.disabled.py and a controller.py differing solely in unique READY=False→True. Independent activation review follows. The package's source controller is never run directly. The same enabled bytes later work in sampling-02 solely because its exact basename/parent choose BLOCK2; no other path/phase is accepted.

For block1:
`/usr/bin/python3.13 -B <E>/sampling-01/controller.py prepare SAMPLE1 --source-review <source-report> --source-review-sha256 <actual-SHA> --prior-review <combined-report> --prior-review-sha256 9293db948fe9393f28f6153ee514eb16e1c1ee3c8b1ec0fe15ffa9d762232a41`

Then only:
`/usr/bin/python3.13 -B <E>/sampling-01/controller.py run SAMPLE1 --admission <E>/sampling-01/coordination/SAMPLE1-admission.json --sha256 <actual-admission-SHA>`

Never directly execute the inner watchdog argv. After actual block1 independent acceptance, materialize/admit block2 analogously with SAMPLE2 and the genuine `main-gap-sampling-01-actual-review/report.json` + actual SHA. No future block1 PASS, ns or scope inventory is prefilled here. `NEXT-REVIEW-CONTRACT.json` freezes that prospective interface. Actual reports always bind original raw logs separately from semantic artifact byte oracles.
