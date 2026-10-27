# History cleanup: 2026-10-27

The branch history was rewritten from `fda35b1a5a736062f97b8d6102ad0b47a255c7c5` to remove `tools/profile/results/` and PDF files under `papers/`. Empty commits and merge parent ordering were retained. Commit messages were preserved as historical text; IDs in old messages are not automatically rewritten. The compiler and tests outside these removal paths were not changed by the filtering step.

`commit-map.txt` records all 165 original-to-rewritten commit identities from the isolated single-branch filter. For each pair, the non-target file trees and ordered parents were compared. Sixteen original signed commits lost their signatures because the underlying commit objects changed. This map is a provenance record, not a replacement for the original signatures.

Original raw profiling archives are not bundled in this branch. Summaries and historical records remain, but reports that cite the removed raw files no longer provide independent access to that data. The corresponding objects can remain in other local refs or remote repositories; branch cleanup does not itself remove them from a shared Git object store.

The historical PDF originals and text transcriptions were copied to [mlf-lang/mlf-papers](https://github.com/mlf-lang/mlf-papers). The repository retains text versions; `impredicativity.txt` is a `pdftotext -layout` extraction whose figures and mathematical layout are not fully preserved. The original paper URL and PDF hash are recorded in `docs/figure12-results.txt`.

Existing audit ledgers retain their original historical identities. `tools/testing/history_refs.py` maps a limited reviewed set of those identities to rewritten commits and trees, pins the associated whole-tree identities, and refuses removed paths. Its mapping controls and the existing migration checks are part of `tools/release/check.sh`. This mapping must be requalified if history is rewritten again.
