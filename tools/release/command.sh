#!/bin/sh
# Installed commands resolve their own package; no checkout paths are embedded.
set -eu
command_name=${0##*/}
package=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
if [ "${1:-}" = --version ] && [ "$#" -eq 1 ]; then
  printf '%s %s (%s)\n' "$command_name" "$(cat "$package/VERSION")" "$(cat "$package/COMMIT")"
  exit 0
fi
exec "$package/libexec/$command_name" "$@"
