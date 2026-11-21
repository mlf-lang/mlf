# Sourced by native fixture adapters. Registered IDs contain only ASCII
# identifier characters, so a case does not require an extra process to report.
mlf_case_id=

mlf_case_selected() {
  test -z "${MLF_TEST_EXACT:-}" || test "$MLF_TEST_EXACT" = "$1"
}

mlf_case_start() {
  case "$1" in ''|*[!a-zA-Z0-9_./-]*) return 2 ;; esac
  mlf_case_id=$1
  if [ -n "${MLF_TEST_EVENTS:-}" ]; then
    printf '{"start":"%s"}\n' "$mlf_case_id" >> "$MLF_TEST_EVENTS"
  fi
}

mlf_case_result() {
  test -n "$mlf_case_id" || return 0
  case "$1" in pass|fail|skip|timeout|crash|cancelled) ;; *) return 2 ;; esac
  case "$2" in ''|*[!0-9]*) return 2 ;; esac
  if [ -n "${MLF_TEST_EVENTS:-}" ]; then
    printf '{"id":"%s","status":"%s","observed_exit":%s}\n' "$mlf_case_id" "$1" "$2" >> "$MLF_TEST_EVENTS"
  fi
  mlf_case_id=
}

mlf_case_cleanup() {
  test "$1" -ne 0 || return 0
  case "$1" in
    130|143) mlf_case_result cancelled "$1" ;;
    *) mlf_case_result fail "$1" ;;
  esac
}

# Consume the actual process output in order. Only observed, literal oracle
# rows earn a result. The caller still checks whole stdout, stderr and exit.
mlf_report_labeled_output() {
  local prefix=$1 oracle=$2 output=$3 status=$4 expected actual
  while IFS= read -r expected; do
    IFS= read -r actual <&3 || actual=
    case "$expected" in
      'PASS '*)
        mlf_case_start "$prefix/${expected#PASS }"
        if [ "$actual" = "$expected" ]; then
          mlf_case_result pass 0
        else
          mlf_case_result fail "$status"
          return 1
        fi ;;
    esac
  done < "$oracle" 3< "$output"
  cmp "$oracle" "$output"
}
