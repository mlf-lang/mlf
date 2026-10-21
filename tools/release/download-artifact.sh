#!/usr/bin/env bash
# Extract one authenticated, digest-checked artifact sequentially, including
# large parity archives on hosts with limited file descriptors.
set -euo pipefail
run=${1:?run ID required}
name=${2:?exact artifact name required}
output=${3:?new output directory required}
source=${4:?workflow source SHA required}
[[ "$run" =~ ^[0-9]+$ && "$name" =~ ^[A-Za-z0-9._-]+$ && "$source" =~ ^[0-9a-f]{40}$ ]]
test ! -e "$output"
repository=${GITHUB_REPOSITORY:-mlf-lang/mlf}
work=$(mktemp -d "${TMPDIR:-/tmp}/mlf-artifact.XXXXXX")
trap 'rm -rf "$work"' EXIT
gh api --paginate --slurp "repos/$repository/actions/runs/$run/artifacts?per_page=100" > "$work/list.json"
jq -e --arg name "$name" --arg source "$source" --argjson run "$run" '
  [.[].artifacts[] | select(.name == $name)] |
  if length == 1 then .[0] else error("missing or ambiguous artifact") end |
  select(.expired == false and .workflow_run.id == $run and .workflow_run.head_sha == $source) |
  select(.digest | test("^sha256:[0-9a-f]{64}$"))
' "$work/list.json" > "$work/artifact.json"
id=$(jq -er .id "$work/artifact.json")
expected=$(jq -er '.digest | sub("^sha256:"; "")' "$work/artifact.json")
gh api "repos/$repository/actions/artifacts/$id/zip" --allow-escape-sequences > "$work/artifact.zip"
if command -v sha256sum >/dev/null 2>&1; then
  actual=$(sha256sum "$work/artifact.zip" | awk '{print $1}')
else
  actual=$(shasum -a 256 "$work/artifact.zip" | awk '{print $1}')
fi
test "$actual" = "$expected"
unzip -Z -1 "$work/artifact.zip" > "$work/entries"
while IFS= read -r entry; do
  case "/$entry/" in
    *'/../'*|*'/./'*|//*|*'\'*) printf 'Unsafe artifact path: %s\n' "$entry" >&2; exit 1 ;;
  esac
done < "$work/entries"
mkdir -p "$output"
unzip -q "$work/artifact.zip" -d "$output"
printf 'Verified artifact %s from run %s: sha256:%s\n' "$name" "$run" "$actual"
