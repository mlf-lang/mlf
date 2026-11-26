# Independent index-design references

These files preserve the exact prepared output of `run_design_controls.py`
at `496dcae024cae1a93096d9bdb9d6b93e57359dc0`:

- `FrozenDesignMap.hs`: Map at `fc300bc9fdc389b585cbef0630fc8915d53e89c5`,
  original SHA-256 `1ef3465e36c4fddcb2b2e60fafd27b642a79e956fe8357355b798d1c7ab199b0`.
- `FrozenDesignSet.hs`: Set at the same commit, original SHA-256
  `c2222cc52e2ee750a92d563f8f513ecf4eb60b1afd534b91a37b7c5d5ba6e60f`.
- `FrozenDesignIdentityInventory.hs`: the established identity collector
  fixture, originally SHA-256
  `e124701116aba2826e4f34fdd1fce4809bb488ecbc41d99f5f2d3d07a8ba4035`.

The existing preparation's only changes were module names and the imports
linking Set to the frozen Map and the collector to the frozen Set. Those changes
and the original collector body were verified once before saving these files.
No algorithm body changed. Normal tests compile these files directly and check
their fixture integrity; they do not fetch commits or invert source rewrites.
The original provenance is also recorded in `../../design-controls/oracle.json`.
