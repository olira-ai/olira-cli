#!/usr/bin/env sh
# Olira CLI installer
# Usage: curl -fsSL https://install.olira.ai | sh
#
# Installs the latest olira binary to /usr/local/bin (or ~/bin if not writable).

set -e

REPO="raiahealth/olira-platform"
BINARY="olira"
INSTALL_DIR="/usr/local/bin"

# ── Detect platform ──────────────────────────────────────────────────────────

OS=$(uname -s)
ARCH=$(uname -m)

case "$OS" in
  Darwin)
    case "$ARCH" in
      arm64)  ASSET="olira-macos-arm64" ;;
      x86_64) ASSET="olira-macos-x86_64" ;;
      *)      echo "Unsupported macOS architecture: $ARCH" && exit 1 ;;
    esac
    ;;
  Linux)
    case "$ARCH" in
      x86_64) ASSET="olira-linux-x86_64" ;;
      *)      echo "Unsupported Linux architecture: $ARCH" && exit 1 ;;
    esac
    ;;
  *)
    echo "Unsupported OS: $OS"
    echo "Please download a binary manually from https://github.com/${REPO}/releases"
    exit 1
    ;;
esac

# ── Resolve latest release ───────────────────────────────────────────────────

if command -v curl >/dev/null 2>&1; then
  DOWNLOADER="curl -fsSL"
elif command -v wget >/dev/null 2>&1; then
  DOWNLOADER="wget -qO-"
else
  echo "Error: curl or wget is required." && exit 1
fi

echo "Fetching latest olira-cli release..."
LATEST_TAG=$($DOWNLOADER "https://api.github.com/repos/${REPO}/releases/latest" \
  | grep '"tag_name"' \
  | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')

if [ -z "$LATEST_TAG" ]; then
  echo "Error: could not determine latest release." && exit 1
fi

VERSION="${LATEST_TAG#olira-cli-v}"
DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${LATEST_TAG}/${ASSET}"

echo "Installing olira v${VERSION} (${ASSET})..."

# ── Download ─────────────────────────────────────────────────────────────────

TMP_FILE=$(mktemp)
trap 'rm -f "$TMP_FILE"' EXIT

if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$DOWNLOAD_URL" -o "$TMP_FILE"
else
  wget -qO "$TMP_FILE" "$DOWNLOAD_URL"
fi

chmod +x "$TMP_FILE"

# ── Install ──────────────────────────────────────────────────────────────────

if [ -w "$INSTALL_DIR" ]; then
  mv "$TMP_FILE" "${INSTALL_DIR}/${BINARY}"
  echo "Installed to ${INSTALL_DIR}/${BINARY}"
else
  # Fall back to ~/bin
  INSTALL_DIR="$HOME/bin"
  mkdir -p "$INSTALL_DIR"
  mv "$TMP_FILE" "${INSTALL_DIR}/${BINARY}"
  echo "Installed to ${INSTALL_DIR}/${BINARY}"

  # Warn if ~/bin is not in PATH
  case ":$PATH:" in
    *":$INSTALL_DIR:"*) ;;
    *)
      echo ""
      echo "NOTE: Add the following to your shell profile (~/.zshrc or ~/.bashrc):"
      echo "  export PATH=\"\$HOME/bin:\$PATH\""
      ;;
  esac
fi

echo ""
echo "olira $(${INSTALL_DIR}/${BINARY} --version 2>/dev/null || echo v${VERSION}) installed successfully."
echo "Run 'olira login' to get started."
