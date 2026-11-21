# Daily repository housekeeping

Ask an agent to **“do today's repository housekeeping.”** Aim for **120
minutes of recorded work per day**. Each job delivers one verifiable
improvement through one merged PR. A larger reorganization can span several
jobs when each step is useful on its own.

## Plan the day

Sum today's entries in the [housekeeping log](housekeeping-log.md). Use the
average duration of recent recorded jobs to estimate how many more will fit
in the remaining minutes. When the log is empty, start with one bounded job.
Recalculate after each job. Once a job starts, finish it even if it takes the
day over 120 minutes. Record the actual time and stop starting jobs once the
daily target is reached.

## Pick one job

Check the working tree, recent changes, and unfinished migrations. When
those yield no candidate, trace a routine task from its instructions through
its entry point to its result. Prefer the change that removes the most
recurring effort or risk of error. State who benefits and how to verify it.
For example, “adding a backend fixture will require one registration” gives
the job a testable goal.

Implement behavior-preserving cleanup autonomously. Ask the maintainer to
decide changes to supported behavior, such as retiring a launcher, dropping a
campaign, or choosing between conflicting command semantics. Preserve
unrelated working-tree changes.

| If you find | What to do | What to verify |
| --- | --- | --- |
| Local and CI tools repeat an operation | Follow both callers to the implementation. Share the common step and keep platform setup with its launcher. | Exercise each affected entry point. Check arguments, exit status on failure, and where output is written. |
| Two test runners repeat setup or registration | Trace one family from fixture to campaign. Put reusable runner behavior in `testing/` and keep compiler-specific expectations with the suite in `tests/`. Consult the [coverage analysis](../tests/coverage-overlap.md) and [migration ledger](../tests/testing-migration-ledger.json). | Compare case IDs, expectations, and campaign membership before and after. Use a known failing case or harness probe to check failure reporting. Preserve independent oracles and backend coverage. |
| A file or directory is hard to place | Identify its producer and consumers, including package manifests, CI workflows, and scripts that discover files by convention. Move the smallest group with a common purpose and update its callers together. | Run the consumer through its usual entry point and check references to the old path. |
| Generated files accumulate beside sources | Identify which command writes them and whether Git tracks them. Direct reproducible scratch output to the relevant build directory. Check provenance before treating a tracked file as disposable, especially under `tmp/a8-reference/`. | Rerun the producer and consumer. Check that the output is usable and review the resulting working-tree status. |
| Two documents describe the same procedure | Verify the command against the current entry point, keep the procedure beside its owner, and link to it from the other location. | Follow the links and check the command from the documented working directory. |

## Record the work and merge

1. Track active work on the job, including investigation, edits, and hands-on
   validation. Pause the clock during idle waits and interruptions. Run the
   checks for the affected entry points and follow the
   [contribution guide](../CONTRIBUTING.md) for compiler and package changes.
2. Immediately before the first push for the PR, add one log row with the
   date, job, active work intervals, total minutes, and verified outcome.
   Include the row in that push. This fixes the recorded duration for the job.
3. Open one PR for the job. Follow CI and review through merge, addressing
   failures and feedback under the repository's merge requirements. All work
   after the first push, including CI fixes, is outside the daily time total.
4. Report the merged PR, validation, and updated daily total. If a larger
   effort continues, leave the next independently useful step in its existing
   issue or migration ledger, or in the run summary.

If investigation yields no worthwhile edit, report what you examined and
why you kept it. Skip the log entry and PR, and exclude the investigation
from the daily total. If no worthwhile candidate remains, finish the day
early and report the actual total.
