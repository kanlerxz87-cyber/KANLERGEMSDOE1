#!/usr/bin/env bash
# Autonomous Competition Data Placement & SHA-256 Verification Script
# Restores competition rasters, external USGS/DOE layers, and historical scored rasters
# into GEMS_DATA_DIR (defaulting to .cache/gems_data if present, or data/) and writes
# data/restore_receipt.json.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${GEMS_DATA_DIR:-$ROOT/.cache/gems_data}"
mkdir -p "$TARGET_DIR" "$ROOT/data"

echo "[GEMSDOE32] Restoring SHA-256-pinned public owner mirrors into: $TARGET_DIR"
echo "[GEMSDOE32] Provenance warning: matching hashes identify mirror bytes, not organizer-authenticated competition files."
python3 "$ROOT/scripts/restore_data.py" --group all --target-dir "$TARGET_DIR"

echo "[GEMSDOE32] Owner-mirror placement and manifest SHA-256 checks succeeded; organizer origin remains unverified."
