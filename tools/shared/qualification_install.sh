#!/usr/bin/env bash
# Runs only inside the root-owned install stage, not as an unbounded job.
set -euo pipefail
test "$(id -u)" = 0
original_temp="$RUNNER_TEMP"
install_root="$original_temp/header-candidate-qualification-toolchain"
test ! -e "$install_root"
mkdir -m 0755 "$install_root"
export RUNNER_TEMP="$install_root"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential clang libgc-dev libgmp-dev libnuma-dev libncurses-dev pkg-config xz-utils
archive="$RUNNER_TEMP/ghc-9.14.1.tar.xz"
curl --fail --show-error --location --max-time 300 https://downloads.haskell.org/~ghc/9.14.1/ghc-9.14.1-x86_64-deb12-linux.tar.xz -o "$archive"
test "$(stat -c %s "$archive")" = 306812040
printf '%s  %s\n' 60f7ab75f28df892729fbaff3a54f58ee3ad7e731929f1b2f3eb0208f73de841 "$archive" | sha256sum -c -
tar --no-same-owner -xJf "$archive" -C "$RUNNER_TEMP"
(cd "$RUNNER_TEMP/ghc-9.14.1-x86_64-unknown-linux" && ./configure --prefix="$RUNNER_TEMP/ghc" && make -j1 install)
test "$("$RUNNER_TEMP/ghc/bin/ghc" --numeric-version)" = 9.14.1
python3 -B tools/release/cleanup-ghc-install.py --receipt .mlf-build/header-candidate-qualification/install-input-cleanup.json
printf '%s\n' "$RUNNER_TEMP/ghc/bin" >> "$GITHUB_PATH"
