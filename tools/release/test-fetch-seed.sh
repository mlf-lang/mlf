#!/usr/bin/env bash
# Synthetic archives exercise platform selection and every existing pin gate.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
root=$PWD
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/bin" "$scratch/fixtures"
cat > "$scratch/bin/gh" <<'GH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$TEST_SEED_SCRATCH/download.log"
patterns=()
destination=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --pattern) patterns+=("$2"); shift 2 ;;
    --dir) destination=$2; shift 2 ;;
    *) shift ;;
  esac
done
for pattern in "${patterns[@]}"; do cp "$TEST_SEED_FIXTURES/$pattern" "$destination/"; done
GH
chmod +x "$scratch/bin/gh"
export PATH="$scratch/bin:$PATH" TEST_SEED_SCRATCH="$scratch"
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
checks=0
for platform in macos-arm64 linux-x64; do
  fixture="$scratch/fixtures/$platform"
  package="mlf-0.0.1-$platform"
  mkdir -p "$fixture/$package/libexec"
  printf 'compiler %s\n' "$platform" > "$fixture/$package/libexec/emlf"
  printf 'manager %s\n' "$platform" > "$fixture/$package/libexec/mlfpkg"
  printf '%s\n' abcdef > "$fixture/$package/COMMIT"
  tar -czf "$fixture/$package.tar.gz" -C "$fixture" "$package"
  (cd "$fixture"; shasum -a 256 "$package.tar.gz" > SHA256SUMS)
  pin="$scratch/$platform.env"
  {
    if [ "$platform" = linux-x64 ]; then printf 'MLF_SEED_PLATFORM=linux-x64\n'; fi
    printf 'MLF_SEED_VERSION=0.0.1\nMLF_SEED_SOURCE_COMMIT=abcdef\n'
    printf 'MLF_SEED_ARCHIVE_SHA256=%s\n' "$(sha256 "$fixture/$package.tar.gz")"
    printf 'MLF_SEED_COMPILER_SHA256=%s\n' "$(sha256 "$fixture/$package/libexec/emlf")"
    printf 'MLF_SEED_MANAGER_SHA256=%s\n' "$(sha256 "$fixture/$package/libexec/mlfpkg")"
  } > "$pin"
  export TEST_SEED_FIXTURES="$fixture"
  env -u MLF_SEED_PLATFORM GITHUB_ENV="$scratch/environment" tools/release/fetch-seed.sh "$scratch/success-$platform" "$pin" > "$scratch/result"
  grep -Fxq "MLF_COMPILER=$scratch/success-$platform/$package/libexec/emlf" "$scratch/environment"
  grep -Fq -- "--pattern $package.tar.gz --pattern SHA256SUMS" "$scratch/download.log"
  checks=$((checks + 1))
  for field in ARCHIVE_SHA256 SOURCE_COMMIT COMPILER_SHA256 MANAGER_SHA256; do
    sed "s/^MLF_SEED_$field=.*/MLF_SEED_$field=wrong/" "$pin" > "$scratch/wrong.env"
    if env -u MLF_SEED_PLATFORM tools/release/fetch-seed.sh "$scratch/failure-$platform-$field" "$scratch/wrong.env" > "$scratch/failure.log" 2>&1; then
      printf 'Seed verification accepted wrong %s for %s\n' "$field" "$platform" >&2; exit 1
    fi
    checks=$((checks + 1))
  done
  printf 'PASS seed fetch: %s archive selection and four independent pin rejections\n' "$platform"
done
cp "$scratch/linux-x64.env" "$scratch/unsupported.env"
printf 'MLF_SEED_PLATFORM=unsupported\n' >> "$scratch/unsupported.env"
before=$(wc -l < "$scratch/download.log")
if tools/release/fetch-seed.sh "$scratch/unsupported" "$scratch/unsupported.env" > "$scratch/failure.log" 2>&1; then exit 1; fi
test "$(wc -l < "$scratch/download.log")" = "$before"
grep -Fq 'Unsupported seed platform: unsupported' "$scratch/failure.log"
checks=$((checks + 1))
printf '%s seed fetch platform/pin checks passed.\n' "$checks"
