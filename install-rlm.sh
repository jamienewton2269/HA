#!/bin/sh
set -eu

REPO_BASE="https://raw.githubusercontent.com/jamienewton2269/HA/main/custom_components/rlm"
DEST="${1:-/config/custom_components/rlm}"

mkdir -p "$DEST"

for file in __init__.py const.py manager.py manifest.json services.yaml; do
  echo "Installing RLM: $file"
  curl -fsSL "$REPO_BASE/$file" -o "$DEST/$file"
done

echo
echo "RLM files installed to $DEST"
echo "Add 'rlm:' to configuration.yaml if it is not already present, then restart Home Assistant."
