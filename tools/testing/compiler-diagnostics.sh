# Native release gates run with Python disabled. Keep the raw captured bytes
# and omit only complete dependency decisions when checking program diagnostics.
mlf_compiler_diagnostics() {
  perl -MJSON::PP=decode_json -ne '
    if (/\Adependency ([^\r\n]+): (?:native|ir|source|unused) \(([^\r\n]+)\)\n\z/) {
      my ($name, $reason) = ($1, $2);
      next if eval { decode_json(qq{"$name"}); decode_json(qq{"$reason"}); 1 };
    }
    print;
  '
}

# Source fixture runners share the same run, fail and capture directory contract.
mlf_source_success() {
  local label=$1
  run "$@" || fail "$label failed; see $work/$label.stderr"
  mlf_compiler_diagnostics < "$work/$label.stderr" | cmp /dev/null - ||
    fail "$label wrote unexpected diagnostics; see $work/$label.stderr"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  mlf_compiler_diagnostics
fi
