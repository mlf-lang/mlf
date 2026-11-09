# Focused shared frontend evidence

All four focused checks passed against the same direct-source GHC O0 executable.

Binary SHA-256: 50728040aba323149be1f592847f73e9d7b7febdf90fdfe05465319d801fb211

| Check | Seconds | Peak group RSS | Result |
| --- | ---: | ---: | --- |
| final-o0-frontend | 3.75 | 10.2 MiB | PASS |
| final-o0-native-first | 47.56 | 29.1 MiB | PASS |
| final-o0-native-second | 47.44 | 28.1 MiB | PASS |
| final-o0-grammar94 | 24.65 | 30.3 MiB | PASS |

Every shard records exact argv, stdout, stderr, source hashes before/after, binary hashes before/after, and a bounded-resource receipt. The 94 shared source and 31 host/runtime input hashes match the recorded producer build inputs for every shard.

The first three shards exercise native parser/name resolution and MLF inference/interpreter behavior, including standard class defaults and exact bottom-demand regressions. The fourth shard is grammar-only over all 94 canonical files.

## Qualification limits

- Overall producer receipt is incomplete: its combined 94-file grammar/name-resolution gate exhausted the aggregate 120-second build watchdog after successful code generation and linking.
- The standalone 94-file shard checks grammar only. It does not establish whole-corpus name resolution or native MLF typechecking.
- The native bridge parser audit passed, but its native --type attempt hit the separate 1 GiB address-space ceiling; full bridge typechecking and native bootstrap remain pending.
- No O2 demand campaign, native code generation campaign, or complete bootstrap qualification is claimed.
