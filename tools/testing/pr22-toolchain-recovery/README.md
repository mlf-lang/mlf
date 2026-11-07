# Provisional recovery source, not an installation receipt

These scripts extract/install only into a required NEW --output directory, never the source directory or a system prefix. Linux only. Example: python3 restore_debian.py --output /absolute/new/debian-task and python3 restore_ghc.py --output /absolute/new/ghc-task. The parent directory must already exist and be canonical. Existing outputs are rejected, including failed runs. New output descendants of any `.git` repository/worktree marker are also rejected before creation. Preserve failed outputs for review; choose another new directory only when authorized and within budget.

Official archive SHA256 and size checks are explicit exceptions, not Python assertions, and occur before extraction. Five unit controls pass both normal Python and -O, including rejecting wrong bytes without invoking extraction. The revised CLI scripts have NOT been rerun through a new full download/install; the earlier installation was separately validated, not evidence that these revised scripts were end-to-end executed.

Scripts require 3 GiB available Linux memory and an 8 GiB free-disk floor plus reserve (1 GiB Debian, 8 GiB GHC before staging, 4 GiB before install). The coordinator must separately enforce the global 16 GiB new-work budget and serial heavy jobs across all workers. Checks are preflight checks, not a continuous process monitor. Interrupt if aggregate limits are threatened. No package installation scripts, apt configuration or system settings are used.

They do not automatically clean anything, set a global PATH, or claim usable/qualified tools. Run scoped independent compiler/LLVM/GC/GMP/PGO probes and record versions. GHC cleanup responsibility is explicit: run the maintained tools/release/cleanup-ghc-install.py with RUNNER_TEMP set to that GHC output and a fresh receipt outside it. That script checks installed closure before deleting only its owned staging and archive.

No machine-local binaries, receipts, absolute runtime inventories, credentials or other secrets are included here. pins.tsv records official Debian archive hashes; restoration writes actual URLs/dependencies into its task-local manifest.
