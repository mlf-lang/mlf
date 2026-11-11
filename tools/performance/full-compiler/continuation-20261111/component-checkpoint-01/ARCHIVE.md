# Tested component snapshot, not complete controller

This exact source-only checkpoint passed83 lightweight tests:13mirror,27profile,19runtime and24guard. Raw test logs and file hashes are included. The27 sparse SCC insertions cover8 source files and an invertible95module/twoMain diagnostic mirror. No GHC compilation or target execution occurred. These tests do not qualify JSON units against the actual RTS, profile linking, compiler semantics or artifacts.

The separate stage controller was still being integrated when this snapshot was taken. Later epoch-wide active-lease/crash-quarantine hardening is not implied by these earlier component test results. Do not run this archive as a production stage launcher; use the latest reviewed controller and new explicit coordinator admissions.
