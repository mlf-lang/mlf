# Bash adapters use the same event sink as the native fixture adapters.
# Enable it only for the outer suite named by the dispatcher.
release_begin() { :; }
release_pass() { :; }

if [ "${MLF_TEST_SUITE:-}" = "$1" ] && [ -n "${MLF_TEST_EVENTS:-}" ]; then
  . "$(dirname -- "${BASH_SOURCE[0]}")/../testing/native-events.sh"

  release_begin() { mlf_case_start "$1"; }
  release_pass() { mlf_case_result pass 0; }

  release_failed() {
    local code=$1
    if [ "${BASH_SUBSHELL:-0}" -eq 0 ]; then
      mlf_case_cleanup "$code" || true
    fi
    return "$code"
  }

  set -E
  trap 'release_failed "$?"' ERR
fi
