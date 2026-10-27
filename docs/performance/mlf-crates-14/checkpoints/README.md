# External historical checkpoint

The complete `mlf-crates-profile-20261026-v3.zip` remains in the separately
delivered user artifact and in the original local restoration commit
`a3e543fbace8c780937335ce9de1519a8101a0e1`. It is intentionally not stored in
this published Git tree. No private download link or credential is included.

- Size: 21,941,703 bytes; 945 ZIP members.
- SHA256: `7ba5f352557178a3d384627965759eda197c7d25e0e7db7b11faa59458cbaf27`.
- `SHA256SUMS` is the checksum for that **external** file, not a claim that the
  file is present in this directory. After obtaining the unchanged archive,
  run `sha256sum -c SHA256SUMS` from a directory containing both files.
- `archive-inventory.json` records the complete member inventory from the
  authenticated ZIP directory. CRC32 fields are integrity metadata, not
  cryptographic authenticity proofs.

The archive contains the broader historical profiles, phase accounting, source
and test snapshots, recipes, validation and timing receipts, and manifests.
Query bodies, toolchains, and compiler binaries were intentionally excluded.
The accepted implementation, independent control tests, reproducibility recipes,
summaries, and qualification receipts remain in this repository. Retaining the
archive externally does not change compiler code, checks, locks, or measured
results. Historical recipes retain their original provenance and may require
the recorded paths, authenticated producers, and toolchain; they are not
advertised as turnkey runs in an arbitrary checkout.
