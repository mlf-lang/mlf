# awk -f name-workers.awk workers.tsv profile.ll > named.ll
# Keep private function labels as internal symbols for native stack sampling.
# Numeric identities come from the production optimizer's worker analysis.
NR == FNR { names[$1] = $2; next }
{
  line = $0
  sub(/^define private /, "define internal ", line)
  if (line ~ / = .*constant .*c"/) { print line; next }
  prefix = ""
  while (match(line, /@mlf\.(st\.)?worker\.[0-9]+/)) {
    token = substr(line, RSTART, RLENGTH)
    identity = token
    sub(/^.*\./, "", identity)
    prefix = prefix substr(line, 1, RSTART - 1) token
    if (identity in names) prefix = prefix "_" names[identity]
    line = substr(line, RSTART + RLENGTH)
  }
  print prefix line
}
