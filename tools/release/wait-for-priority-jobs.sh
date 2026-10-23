#!/usr/bin/env bash
# GitHub matrix ordering is not runner priority. Admit the other macOS groups
# only after every requested priority job has obtained a runner or finished.
set -euo pipefail
run=${GITHUB_RUN_ID:?}
repository=${GITHUB_REPOSITORY:?}
workflow_source=${GITHUB_SHA:?}
priorities=${MLF_PRIORITY_JOBS:-'["macos-arm64 port","macos-arm64 unit"]'}
[[ "$run" =~ ^[0-9]+$ && "$workflow_source" =~ ^[0-9a-f]{40}$ ]]
jq -e 'type == "array" and length > 0 and all(.[]; type == "string") and (unique | length) == length' <<< "$priorities" >/dev/null
mkdir -p .mlf-build
while :; do
  if gh api --paginate --slurp "repos/$repository/actions/runs/$run/jobs?per_page=100" > .mlf-build/priority-jobs.json; then
    if jq -e --arg source "$workflow_source" --argjson priorities "$priorities" '
      [.[].jobs[] | (.name | split(" / ") | last) as $group |
        select($priorities | index($group) != null) | . + {group:$group}] |
      length == ($priorities | length) and (map(.group) | unique | length) == ($priorities | length) and
      all(.[]; .head_sha == $source and
        (.status == "completed" or (.status == "in_progress" and .runner_id > 0)))
    ' .mlf-build/priority-jobs.json >/dev/null; then
      printf 'All priority macOS jobs obtained runners; releasing the other four groups.\n'
      exit 0
    fi
  fi
  sleep 10
done
