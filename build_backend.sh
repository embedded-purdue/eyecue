#!/usr/bin/env bash
# build_backend.sh — build only the self-contained backend binary
# Usage: bash build_backend.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST_BINARY="$REPO_ROOT/dist/eyecue-backend"

file_mtime() {
  local path="$1"
  if stat -f "%m" "$path" >/dev/null 2>&1; then
    stat -f "%m" "$path"
  else
    stat -c "%Y" "$path"
  fi
}

needs_rebuild() {
  if [[ ! -f "$DIST_BINARY" ]]; then
    return 0
  fi

  local binary_mtime
  binary_mtime="$(file_mtime "$DIST_BINARY")"

  local src_file src_mtime
  while IFS= read -r -d '' src_file; do
    src_mtime="$(file_mtime "$src_file")"
    if [[ "$src_mtime" -gt "$binary_mtime" ]]; then
      return 0
    fi
  done < <(
    find "$REPO_ROOT/app" -path "$REPO_ROOT/app/frontend" -prune -o -type f -name "*.py" -print0
    find "$REPO_ROOT" -maxdepth 1 -type f \( -name "backend.spec" -o -name "requirements.txt" \) -print0
  )

  return 1
}

if [[ ! -f "$REPO_ROOT/env/bin/python" ]]; then
  echo "ERROR: Missing venv python at $REPO_ROOT/env/bin/python" >&2
  echo "Create it first: python3 -m venv env && source env/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$REPO_ROOT/env/bin/activate"

echo "==> Installing PyInstaller if missing..."
pip install pyinstaller --quiet

if ! needs_rebuild; then
  echo "==> Backend binary is up to date: $DIST_BINARY"
  exit 0
fi

echo "==> Building backend binary with PyInstaller..."
cd "$REPO_ROOT"
pyinstaller backend.spec --distpath dist --workpath build/pyinstaller --noconfirm

if [[ ! -f "$DIST_BINARY" ]]; then
  echo "ERROR: PyInstaller did not produce $DIST_BINARY" >&2
  exit 1
fi

echo "==> Backend binary ready: $DIST_BINARY"
