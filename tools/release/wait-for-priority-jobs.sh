#!/usr/bin/env bash
# GitHub matrix ordering is not runner priority. Admit the other macOS groups
# only after both long groups have obtained runners (or finished independently).
set -euo pipefail
run=${GITHUB_RUN_ID:?}
repository=${GITHUB_REPOSITORY:?}
workflow_source=${GITHUB_SHA:?}
[[ "$run" =~ ^[0-9]+$ && "$workflow_source" =~ ^[0-9a-f]{40}$ ]]
mkdir -p .mlf-build
while :; do
  if gh api --paginate --slurp "repos/$repository/actions/runs/$run/jobs?per_page=100" > .mlf-build/priority-jobs.json; then
    if jq -e --arg source "$workflow_source" '
      [.[].jobs[] | (.name | split(" / ") | last) as $group |
        select($group == "macos-arm64 port" or $group == "macos-arm64 unit") | . + {group:$group}] |
      length == 2 and (map(.group) | unique | length == 2) and
      all(.[]; .head_sha == $source and
        (.status == "completed" or (.status == "in_progress" and .runner_id > 0)))
    ' .mlf-build/priority-jobs.json >/dev/null; then
      printf 'Both priority macOS groups obtained runners; releasing the other four groups.\n'
      exit 0
    fi
  fi
  sleep 10
done
