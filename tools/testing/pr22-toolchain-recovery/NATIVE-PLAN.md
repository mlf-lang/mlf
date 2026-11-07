# Qualification plan, not evidence

Use the restored task-local toolchain env.sh and pinned official seed archives retained in pr19-seed-recovery-20261106. Verify every actual seed binary plus bundle checksums, commit and archive hash against repository pins before executing. Seed-only success is not bootstrap success.

Run scripts/bootstrap-async.sh (delegates shared) with GC_FREE_SPACE_DIVISOR=8 and MLF_TEST_BUILD_JOBS=1, maintained measure-process-tree.py minimum available memory set to 3072 MiB, and outer timeout with TERM then KILL after 30 seconds. This host's agreed floor is 3 GiB available RAM, 8 GiB free disk and total new work at most 16 GiB. One compiler campaign at a time; stop and preserve diagnostics if a floor is crossed. Do not use Darwin-only timed-bootstrap.sh on Linux.

Real seed route must build frozen legacy bridge then both shared native compiler and package manager, validate native-MLF identities, process capability and typed completion, and emit complete before/after input receipts. A bootstrap receipt alone is explicitly not fixed-point qualification.

Build current tool pair with --locked plan followed by --locked build, --jobs 1 and explicit runtime/timeout. Require fresh distinct stages and cache directories for next-generation BOTH emlf and mlfpkg, cached:false, identical source/clang/PGO inputs, and exact LLVM plus native binary hashes for BOTH tools. POSIX existing self-host test checks emlf only and cannot establish manager fixed point.

Run async completion (source interpreter, target interpreter, LLVM), process/task (interpreter and LLVM) and package native replay; require all expected output fields, including opaque/type rejection counts. Run native unit/backends/parity/packages/self-host/port-preparation/port/tuple-list campaigns as maintained. Package-core reproduction and fresh independent fixed-point tests are separate required evidence.

Full platform acceptance still needs native-qualification CI: macOS bridge/portable LLVM, Linux and Windows consumption, macOS campaign groups and all-ten Benchmark Game, Windows oracle and both-tool fixed point. ci.yml manual full_validation:true or self_host:true triggers full qualification; a PR label does not. Avoid optional release archives, tags and publication.

Main Benchmark Game failure run42214537005 only established aggregate performance-limit failure from logs. Exact per-case ratios remain unknown; its 6.3 GB artifact was not downloaded. Do not attribute it to PR22 or claim a performance gate pass.
