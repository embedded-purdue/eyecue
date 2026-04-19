#!/usr/bin/env bash
# build_backend.sh — build only the self-contained backend binary
# Usage: bash build_backend.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST_BINARY="$REPO_ROOT/dist/eyecue-backend"

if [[ ! -f "$REPO_ROOT/env/bin/python" ]]; then
  echo "ERROR: Missing venv python at $REPO_ROOT/env/bin/python" >&2
  echo "Create it first: python3 -m venv env && source env/bin/activate && pip install -r requirements.txt" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$REPO_ROOT/env/bin/activate"

echo "==> Installing PyInstaller if missing..."
pip install pyinstaller --quiet

echo "==> Building backend binary with PyInstaller..."
cd "$REPO_ROOT"
pyinstaller backend.spec --distpath dist --workpath build/pyinstaller --noconfirm

if [[ ! -f "$DIST_BINARY" ]]; then
  echo "ERROR: PyInstaller did not produce $DIST_BINARY" >&2
  exit 1
fi

echo "==> Backend binary ready: $DIST_BINARY"
