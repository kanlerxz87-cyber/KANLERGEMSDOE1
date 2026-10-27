#!/usr/bin/env bash
# Autonomous Competition Data Placement & SHA-256 Verification Script
# Restores competition rasters, external USGS/DOE layers, and historical scored rasters
# into GEMS_DATA_DIR (defaulting to data/) and writes data/restore_receipt.json.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${GEMS_DATA_DIR:-$ROOT/data}"
PYTHON_BIN="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi
mkdir -p "$TARGET_DIR" "$ROOT/data"

echo "[GEMSDOE32] Verifying and restoring competition data into: $TARGET_DIR"
"$PYTHON_BIN" "$ROOT/scripts/restore_data.py" --group all --target-dir "$TARGET_DIR"

echo "[GEMSDOE32] Competition data placement and SHA-256 verification succeeded."
