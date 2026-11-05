# Root-bounded open packages

This change adds open-package wire schema 8. It addresses a valid multi-fragment
package exceeding the old single-root expansion limit even though every final
fragment is individually small.

## Wire representation

The existing canonical bitstream framing, UTF-8 symbol table, bottom-up node
table, bit-width encoding, checksum, and reference validation are retained.
Schema 8 has one tag-432 header root followed by the ordered tag-401 final
fragment roots. The header contains the wire marker
`MLF-OPEN-CRATE-2/checker-1`, compiler compatibility identity, metadata digest,
binding references, declaration references, and final count. Its count must
match the remaining roots exactly.

All roots use one physical symbol/node table. Sharing therefore remains global,
including sharing between different fragments. Each final retains its complete
group name, checked receipt, declaration names, parameter names, body, owned
names, and used-name inventory. The existing dependency-interface association,
type/ownership validation, and retained semantic audit still apply.

## Compatibility

The schema-7 reader and its original limits remain available. Raw transfer,
relocation, and release handling preserve an existing schema-7 package's object bytes.
A checked rebuild uses the current schema-8 writer: its full interface and
fragment meaning must match the old package, but its wire checksum changes.
With unchanged metadata and dependency paths, a schema-8 checked rebuild must
preserve the complete pair's bytes.

Closed binary families and legacy text readers are unchanged. This is backward
reading compatibility, not forward compatibility: older binaries that only
recognize schema 7 cannot read new schema-8 packages. Upgrade producers and
consumers together.

The semantic compatibility marker remains `MLF-OPEN-CRATE-1/checker-1`.
It is distinct from the new wire-format marker.

## Resource accounting

The original 64 Mi-unit expanded-work bound still applies to each root and
physical subtree. Schema 8 additionally bounds the entire package at
256 Mi-units, matching the artifact storage byte-limit class. This is an
explicit package-format bound, not a claim that every valid source program fits.

Combined work includes the complete wire roots plus the actual schema-6 syntax
plans used to hash binding types and datatype declarations. Repeated edges,
repeated roots, and UTF-8 text occurrences are charged every time, even when
their physical nodes or symbols are shared. Hash encoding consumes the same
plan used for charging. Work left after the wire must also cover those hashes.

Schema 7 retains its historical wire and individual-hash limits; it does not
acquire the schema-8 combined package-work budget.

These logical counters do not establish a hard RSS or CPU bound. Physical
input limits and the existing process, memory, time, and disk guards remain
necessary; downstream passes are not claimed to have precise per-artifact
allocation accounting.

## Validation and provenance

The codec controls cover root and combined boundaries, repeated-DAG
amplification, Unicode accounting, malformed input, and shape-sensitive,
graph-local typed decoding. Public-reader controls cover old and new packages,
complete checked migration meaning, current byte identity, and binding /
declaration hash work exhausting the remaining package budget.

The source provenance successor is a reversible five-file edge. Historical
contracts, generation records, and reference tests are preserved and replayed
on their authenticated physical predecessor sources. The new generation record
distinguishes successful compile/link/generator commands from an original
wrapper-cleanup failure and a separate successful verification of its outputs.

Focused GHC checks are not a native-backend or full-CI qualification. The
exact-head CI gate must still compile the complete reviewed 49-module native
fixture, lower and link it, and execute the full public-reader and distribution
controls. Previous monolithic frontend timeout/OOM observations are not resolved
merely by changing this package representation.
