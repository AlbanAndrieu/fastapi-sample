set -euo pipefail

usage() {
  printf 'Usage: %s SOURCE_GIT_DIR COMMIT_SHA DESTINATION\n' "$0" >&2
  exit 2
}

(($# == 3)) || usage
source_dir="$1"
commit="$2"
destination="$3"

if ! [[ "$commit" =~ ^[[:xdigit:]]{40}$ ]]; then
  echo '❌ expected a full 40-character commit SHA' >&2
  exit 2
fi
if [[ -e "$destination" ]]; then
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

mkdir -p "$(dirname "$destination")"
staging="$(mktemp -d "$(dirname "$destination")/.source-snapshot.XXXXXXXX")"
trap 'rm -rf -- "$staging"' EXIT
# Read the verified local Git object database, never the dirty worktree.
git -C "$source_dir" archive --format=tar "$actual" | tar -xf - -C "$staging"
printf '%s\n' "$actual" > "$staging/.source-commit-sha"
mv -- "$staging" "$destination"
trap - EXIT
printf '✅ offline snapshot from verified Git commit %s: %s\n' "$actual" "$destination"
