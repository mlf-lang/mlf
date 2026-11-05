# Explicit async parity on pull requests

Pull requests do not run the expensive async interpreter/native parity campaign
by default. A maintainer can add the **`ci:async-parity`** label to request it;
adding or removing that label triggers CI again. An explicit opt-in runs parity
even for documentation-only changes. Alternatively, manually run the CI workflow
on the desired branch (without `windows_runtime_only`).

Main pushes, manual runs and merge-queue events retain async coverage. Fast native
completion/runtime, Windows runtime, build-runner, source-smoke and metadata jobs
are unchanged.

The async job still runs its cheap policy selector and retains `decision.json`.
A default PR receipt says `parity_execution: not-executed`, not that parity passed.
Only that explicit decision skips the expensive steps. Malformed/missing PR metadata
fails the cheap selector without executing parity. The aggregate PR gate still requires all six
jobs to succeed: failed, cancelled or skipped jobs cannot satisfy it. The
full-native qualification and its supplemental tuple/list checks are unchanged.
