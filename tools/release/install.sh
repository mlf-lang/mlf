#!/bin/sh
set -eu
package=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
prefix=${1:-"$HOME/.local"}
case "$prefix" in /*) ;; *) printf '%s\n' 'Use an absolute install prefix.' >&2; exit 1 ;; esac
(cd "$package" && shasum -a 256 -c CHECKSUMS >/dev/null)
version=$(cat "$package/VERSION")
commit=$(cat "$package/COMMIT")
mkdir -p "$prefix/lib/mlf" "$prefix/bin"
destination="$prefix/lib/mlf/$version-$commit"
if [ -e "$destination" ]; then
  cmp "$package/CHECKSUMS" "$destination/CHECKSUMS"
  (cd "$destination" && shasum -a 256 -c CHECKSUMS >/dev/null)
else
  staged=$(mktemp -d "$prefix/lib/mlf/.install.XXXXXX")
  trap 'rm -rf "$staged"' EXIT HUP INT TERM
  cp -R "$package/." "$staged/"
  (cd "$staged" && shasum -a 256 -c CHECKSUMS >/dev/null)
  mv "$staged" "$destination"
  trap - EXIT HUP INT TERM
fi
# Real launcher files preserve relative package discovery even through PATH.
# Do not replace unrelated commands or symlinks in the user's bin directory.
for command_name in emlf mlfpkg; do
  launcher="$prefix/bin/$command_name"
  if [ -e "$launcher" ] || [ -L "$launcher" ]; then
    if [ -L "$launcher" ] || ! grep -q '^# MLF installed command$' "$launcher"; then
      printf 'Refusing to replace unrelated command: %s\n' "$launcher" >&2
      exit 1
    fi
  fi
done
for command_name in emlf mlfpkg; do
  launcher="$prefix/bin/$command_name"
  temporary=$(mktemp "$prefix/bin/.mlf-launcher.XXXXXX")
  # Pass the package path through a quoted shell literal, including apostrophes.
  quoted=$(printf '%s' "$destination/bin/$command_name" | sed "s/'/'\\\\''/g")
  printf '#!/bin/sh\n# MLF installed command\nexec '\''%s'\'' "$@"\n' "$quoted" > "$temporary"
  chmod 755 "$temporary"
  mv "$temporary" "$launcher"
done
printf 'Installed MLF %s in %s\nAdd %s/bin to PATH.\n' "$version" "$destination" "$prefix"
