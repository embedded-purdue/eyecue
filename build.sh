#!/usr/bin/env bash
# build.sh — build the self-contained EyeCue desktop app
# Usage: ./build.sh
# Run from the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$REPO_ROOT/app/frontend"

echo "==> Building backend binary..."
bash "$REPO_ROOT/build_backend.sh"

echo "==> Building Electron app with electron-forge..."
cd "$FRONTEND_DIR" && npm run make

echo ""
echo "Done! Distributable is in app/frontend/out/make/"
