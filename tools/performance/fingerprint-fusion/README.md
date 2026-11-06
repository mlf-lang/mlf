# F1: guarded GHC-host fingerprint arithmetic fusion

F1 adds two literal GHC rewrite rules to the host `Integer` facade, with six
public alias INLINE pragmas. It does not change shared/native MLF source, the
primitive ABI, serialized fingerprints, or source locks. It is integrated with
P1–P3 and A0/A1; F2 and F3 are not included.

For the exact `(state * 65599 + code) rem 2147483647` and
`(state * 131 + code) rem 2147483629` forms, a nonnegative state below its modulus
and integer code in `0..0x10ffff` permit an `Int64` calculation: the complete sum
is below `2^48`. Narrowing occurs only after these checks. Other values use the
original unbounded, ordered `Integer` operations, including negative `rem` and
arbitrarily large signed operands. This is arithmetic, not Unicode validation;
surrogate code values are not rejected. State is demanded before multiplication,
then code, as before; partial application stays lazy. The fallback has no rule
heads and cannot recursively rewrite itself. Production retains
`-fpedantic-bottoms -fno-state-hack`.

## Maintained current-source correctness gate

First produce a fresh complete current GHC 9.14.1 O2 build with
`tools/shared/build.py`. Then run serially under the maintained resource guard:

```sh
python3 -B tools/shared/resource_watchdog.py --seconds 1800 \
  --address-space-mib 6144 --rss-mib 5120 --disk-free-mib 4096 \
  .mlf-build/f1-guard python3 -B tools/performance/fingerprint-fusion/run_controls.py \
  --producer .mlf-build/shared-ghc --output .mlf-build/f1-controls
```

The runner authenticates the full current producer and builtin before/after. It
compiles exact frozen `Oracle.hs`, `Tests.hs` and `Probe.hs` in fresh isolated O0
and O2 directories with current host source. Oracle and driver stay O0; the oracle
uses literal Prelude `Integer` arithmetic, not candidate arithmetic or private
helpers. Exact expected stdout is authored, never captured from the candidate:

* 19,050 value comparisons over six public named/operator/mismatched-constant routes;
* 270 checksum streams, comparing every prefix, plus host character boundaries;
* 60 exact error-priority probes and 18 lazy partial applications;
* 224 ordinary signed divisions and 40 zero-divisor/error-order probes;
* 36 bounded divergent observations and 12 exact panic-before-divergence checks.

Timeout observations are finite controls, not a theorem of universal divergence.
Exact module resolution, immutable snapshots, exit zero and empty execution stderr
are required. Core lint runs at both optimization levels. The public O0 probe
must fire neither rule; O2 must fire each twice. Unmatched O2 expressions must
retain ordinary `Integer` operations in their Core, without narrow operations.

A separate diagnostic copies the complete authenticated O2 objects, removes only
`Bootstrap.Separate.{hi,o}` from that **copy**, and recompiles the actual unchanged
current `Separate` with its real producer flags plus Core lint and dump flags.
Only `Separate` may compile; each rule must fire at least four times. All other
copied objects and all original producer outputs must remain unchanged. No dump
flags are added to the production build or a timing leg.

The existing P1–P3 and A1 gates are preserved. P1/P2 host pins were independently
re-audited for this addition-only host delta. In particular, P2's literal oracle
is compiled with rewrite rules disabled and interface unfoldings omitted so F1
cannot contaminate both sides of its differential, including later harness
inlining. Its source bytes and all original expected checks stay fixed.
The separate F1 oracle supplies independent coverage of host arithmetic.

CI adds this bounded gate only to O2/all; it itself checks both O0 and O2 host
semantics. All original four source-smoke matrix legs and their coverage/caps
remain. No expensive opt-in native async bootstrap is enabled. Receipts/logs/Core
dumps are run artifacts, never committed machine-specific metadata.

## Historical observations and limits

The exact production patch was first studied on P3
`875e483de49655030c4ffba1995b60610a50273a` (patch SHA256
`db1bfb786002d68aac92d4932a4583ddf21e23c5b1c0886e9d96763ee88a0a7a`).
One fixed real slice pair measured F1 **90.319474082 s** versus P3
**93.747313464 s**: **3.6565%** lower wall time, with both reporting 544 fresh /
0 reused groups and identical checked artifact bytes. This was one pair, not
three rounds/medians, a GHC comparison, or proof of stable compiler-wide benefit.
The separate synthetic rolling-loop improvement is not compiler performance.

The original experiment's 5% screen did not accept F1. The subsequent explicit
integration decision does not use that screen as a mandatory merge threshold;
it does not turn the single pair into performance qualification. No new timing
campaign is performed for the combined A1 + F1 tree, and historical A1/F1 gains
must not be added or attributed to this final combination. Native execution and
other host/platform speedups are not established by these GHC controls. Private
raw historical evidence remains separate; it is not included in this repository.
