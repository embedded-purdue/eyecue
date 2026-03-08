#!/usr/bin/env bash
# build.sh — build the self-contained EyeCue desktop app
# Usage: ./build.sh
# Run from the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$REPO_ROOT/app/frontend"
DIST_BINARY="$REPO_ROOT/dist/eyecue-backend"

echo "==> Activating Python venv..."
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

echo "==> Building Electron app with electron-forge..."
cd "$FRONTEND_DIR" && npx electron-forge make

echo ""
echo "Done! Distributable is in app/frontend/out/make/"
