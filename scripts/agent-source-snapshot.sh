set -euo pipefail

usage() {
  printf 'Usage: %s SOURCE_GIT_DIR COMMIT_SHA DESTINATION [BASE_REF]\n' "$0" >&2
  exit 2
}

(( $# == 3 || $# == 4 )) || usage
source_dir="$1"
commit="$2"
destination="$3"
base_ref="${4:-}"

if ! [[ "$commit" =~ ^[[:xdigit:]]{40}$ ]]; then
  echo '❌ expected a full 40-character commit SHA' >&2
  exit 2
fi
if [[ -e "$destination" || -L "$destination" ]]; then
  echo '❌ destination already exists; refusing to overwrite' >&2
  exit 2
fi
if ! git -C "$source_dir" rev-parse --git-dir >/dev/null 2>&1; then
  echo '❌ source is not a readable local Git repository' >&2
  exit 1
fi
actual="$(git -C "$source_dir" rev-parse --verify "${commit}^{commit}" 2>/dev/null)" || {
  echo '❌ requested commit is not cached locally' >&2
  exit 1
}
if [[ "${actual,,}" != "${commit,,}" ]]; then
  echo '❌ cached Git commit does not match requested SHA' >&2
  exit 1
fi

base_actual=""
if [[ -n "$base_ref" ]]; then
  base_actual="$(git -C "$source_dir" rev-parse --verify "${base_ref}^{commit}" 2>/dev/null)" || {
    echo '❌ requested comparison base is not cached locally' >&2
    exit 1
  }
  if ! git -C "$source_dir" merge-base --is-ancestor "$base_actual" "$actual"; then
    echo '❌ requested comparison base is not an ancestor of requested HEAD' >&2
    exit 1
  fi
fi

mkdir -p "$(dirname "$destination")"
staging="$(mktemp -d "$(dirname "$destination")/.source-snapshot.XXXXXXXX")"
trap 'rm -rf -- "$staging"' EXIT
# Preserve Git metadata for comparison-base and exact-HEAD quality gates.
# A no-hardlinks clone is independent of later writes to the local cache.
rmdir -- "$staging"
git clone --local --no-hardlinks --no-checkout --quiet -- "$source_dir" "$staging"
git -C "$staging" checkout --detach --force --quiet "$actual"
[[ "$(git -C "$staging" rev-parse HEAD)" == "$actual" ]]
if [[ -n "$base_actual" ]]; then
  git -C "$staging" cat-file -e "${base_actual}^{commit}" || {
    echo '❌ comparison base object missing from materialized snapshot' >&2
    exit 1
  }
  git -C "$staging" merge-base --is-ancestor "$base_actual" HEAD || {
    echo '❌ comparison base ancestry changed during snapshot creation' >&2
    exit 1
  }
fi
if [[ -e "$destination" || -L "$destination" ]]; then
  echo '❌ destination appeared during snapshot creation; refusing to overwrite' >&2
  exit 2
fi
mv -T -- "$staging" "$destination"
trap - EXIT
if [[ -n "$base_actual" ]]; then
  printf '✅ offline snapshot from verified Git commit %s with base %s: %s\n' \
    "$actual" "$base_actual" "$destination"
else
  printf '✅ offline snapshot from verified Git commit %s: %s\n' "$actual" "$destination"
fi
