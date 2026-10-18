#!/usr/bin/env bash
# Transparent command timing for the immutable native seed and Clang on macOS.
set -euo pipefail
directory=${1:?timing directory required}
kind=${2:?command kind required}
shift 2
test "$#" -gt 0
sample=$(mktemp -d "$directory/commands/$kind.XXXXXX")
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
jq -n --arg kind "$kind" --arg cwd "$PWD" --arg started "$started" \
  --args '{kind:$kind,cwd:$cwd,started_utc:$started,argv:$ARGS.positional,
    phase:(if $kind=="clang" then
      if any($ARGS.positional[];endswith(".ll")) then "llvm-and-link"
      elif any($ARGS.positional[];endswith(".c")) then "runtime-c"
      else "clang-query" end else $kind end)}' -- "$@" > "$sample/command.json"
printf 'START %s %s %s\n' "$started" "$kind" "$(jq -c .argv "$sample/command.json")" >> "$directory/events.log"
if /usr/bin/time -lp -o "$sample/time.txt" "$@"; then code=0; else code=$?; fi
jq -n --slurpfile command "$sample/command.json" --rawfile raw "$sample/time.txt" \
  --arg finished "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --argjson code "$code" '
  def seconds($label): capture("(?m)^"+$label+" +(?<value>[0-9.]+)").value | tonumber;
  def counter($label): capture("(?m)^ *(?<value>[0-9]+) +"+$label+" *$").value | tonumber;
  $command[0] + {complete:true,finished_utc:$finished,exit_code:$code,
    wall_seconds:($raw|seconds("real")),user_seconds:($raw|seconds("user")),
    system_seconds:($raw|seconds("sys")),peak_rss_bytes:($raw|counter("maximum resident set size")),
    page_reclaims:($raw|counter("page reclaims")),page_faults:($raw|counter("page faults")),
    swaps:($raw|counter("swaps"))}' > "$sample/result.json"
printf 'END %s %s %s\n' "$kind" "$code" "$(jq -c '{wall_seconds,user_seconds,system_seconds,peak_rss_bytes,argv}' "$sample/result.json")" >> "$directory/events.log"
exit "$code"
