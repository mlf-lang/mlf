#!/usr/bin/env bash
# Exercise publishing decisions without credentials or writes to GitHub.
set -euo pipefail
scripts=$(cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
mkdir "$scratch/bin" "$scratch/bundle with spaces"
export TEST_PUBLISH_LOG="$scratch/gh.log"
export TEST_SOURCE=0123456789012345678901234567890123456789
export TEST_GH_MODE=success
export PATH="$scratch/bin:$PATH"
export MLF_PACKAGE_MANAGER="$scratch/bin/mlfpkg"
cat > "$MLF_PACKAGE_MANAGER" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
test "$#" -eq 3 && test "$1" = pack
test ! -e "$3"
jq -n --rawfile manifest "$2/release.json" '{format:1,manifest:$manifest,crates:[]}' > "$3"
manifest=$(shasum -a 256 "$2/release.json" | awk '{print $1}')
asset=$(shasum -a 256 "$3" | awk '{print $1}')
jq -n --arg manifest "$manifest" --arg asset "$asset" '{sha256:$manifest,asset_sha256:$asset}'
SH
cat > "$scratch/bin/gh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$TEST_PUBLISH_LOG"
case "$1 $2" in
  'api '*)
    if [ "$TEST_GH_MODE" = moved ] || { [ "$TEST_GH_MODE" = moved-during-upload ] && grep -q 'release create' "$TEST_PUBLISH_LOG"; }; then
      echo 1111111111111111111111111111111111111
    else
      echo "$TEST_SOURCE"
    fi ;;
  'release view') test "$TEST_GH_MODE" = existing ;;
  'release create')
    [[ "$*" == *'--verify-tag --draft --latest=false'* ]]
    test "$TEST_GH_MODE" != upload-failed ;;
  'release edit') [[ "$*" == *'--draft=false --latest=false'* ]] ;;
  *) exit 99 ;;
esac
SH
chmod +x "$scratch/bin/"*
jq -n '{name:"example",version:"1.2.3",compiler_sha256:("a" * 64)}' > "$scratch/bundle with spaces/release.json"
"$scripts/prepare-package-release.sh" "$scratch/bundle with spaces" owner/repo packages/example/1.2.3 "$scratch/output with spaces" >/dev/null
jq -e '.dependencies.example.github.repository == "owner/repo" and .dependencies.example.github.tag == "packages/example/1.2.3"' "$scratch/output with spaces/dependency.json" >/dev/null
test ! -e "$TEST_PUBLISH_LOG"
echo 'PASS publishing: preparation is local and emits pinned dependency'
expect_failure() { if "$@" >"$scratch/failure.log" 2>&1; then echo 'Expected failure' >&2; exit 1; fi; }
expect_failure "$scripts/prepare-package-release.sh" "$scratch/bundle with spaces" owner/repo packages/example/1.2.3 "$scratch/output with spaces"
expect_failure "$scripts/prepare-package-release.sh" "$scratch/bundle with spaces" owner/repo --latest "$scratch/invalid"
expect_failure "$scripts/prepare-package-release.sh" "$scratch/bundle with spaces" owner/repo latest "$scratch/invalid"
echo 'PASS publishing: existing output and invalid locator are rejected'
publish() { "$scripts/publish-package-release.sh" "$scratch/output with spaces" owner/repo packages/example/1.2.3 "$TEST_SOURCE"; }
publish
test "$(wc -l < "$TEST_PUBLISH_LOG" | tr -d ' ')" = 5
tail -n 1 "$TEST_PUBLISH_LOG" | grep -q 'release edit.*--draft=false'
echo 'PASS publishing: exact tag is checked and assets precede publication'
for mode in existing moved upload-failed moved-during-upload; do
  export TEST_GH_MODE=$mode
  : > "$TEST_PUBLISH_LOG"
  expect_failure publish
  if grep -q 'release edit' "$TEST_PUBLISH_LOG"; then exit 1; fi
  if { [ "$mode" = existing ] || [ "$mode" = moved ]; } && grep -q 'release create' "$TEST_PUBLISH_LOG"; then exit 1; fi
  echo "PASS publishing: $mode cannot publish"
done
export TEST_GH_MODE=success
: > "$TEST_PUBLISH_LOG"
asset=$(jq -r '.dependencies.example.github.asset' "$scratch/output with spaces/dependency.json")
printf '\nchanged\n' >> "$scratch/output with spaces/$asset"
expect_failure publish
test ! -s "$TEST_PUBLISH_LOG"
echo 'PASS publishing: damaged asset is rejected before GitHub access'
echo '8 package publishing checks passed'
