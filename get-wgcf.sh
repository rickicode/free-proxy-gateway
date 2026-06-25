#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$ROOT/bin"
VERSION="${1:-2.4.1}"

ARCH_RAW="$(uname -m)"
case "$ARCH_RAW" in
  x86_64) ARCH="amd64" ;;
  aarch64) ARCH="arm64" ;;
  *)
    echo "unsupported arch: $ARCH_RAW" >&2
    exit 1
    ;;
esac

URL="https://github.com/ViRb3/wgcf/releases/download/v${VERSION}/wgcf_${ARCH}"
DEST="$BIN_DIR/wgcf"

mkdir -p "$BIN_DIR"
echo "Downloading wgcf v${VERSION} ($ARCH)..."
curl -L "$URL" -o "$DEST"
chmod +x "$DEST"
printf '%s\n' "$VERSION" > "$BIN_DIR/wgcf.version"

echo "installed $DEST (version $VERSION)"
