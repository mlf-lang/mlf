#!/usr/bin/env bash
# Source before qualification builds. Parallelism is explicit and bounded;
# memory evidence, rather than processor count, decides its CI default.
export MLF_TEST_BUILD_JOBS=${MLF_TEST_BUILD_JOBS:-1}
case "$MLF_TEST_BUILD_JOBS" in 1|2) ;; *) printf '%s\n' 'Qualification build jobs must be 1 or 2.' >&2; return 2 ;; esac
if [ "$MLF_TEST_BUILD_JOBS" = 2 ]; then
  test "$(uname -s)" = Linux || { printf '%s\n' 'Parallel qualification is not yet validated on this platform.' >&2; return 2; }
  # This is a resource admission check, not proof that two arbitrary workloads
  # fit. The workflow may select two only after the measured budget is reviewed.
  memory=$(awk '/^MemTotal:/ {printf "%.0f\n", $2 * 1024}' /proc/meminfo)
  test "$memory" -ge 15032385536 || { printf '%s\n' 'Two qualification build jobs require at least 14 GiB host RAM.' >&2; return 2; }
fi
printf 'Qualification build jobs: %s\n' "$MLF_TEST_BUILD_JOBS"
