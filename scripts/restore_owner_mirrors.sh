#!/usr/bin/env bash
# Reuse the reviewed upstream restore tool. These are OWNER MIRRORS, not authenticated official bytes.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
command -v gh >/dev/null || { echo 'GitHub CLI (gh) is required for the permitted GitHub host.' >&2; exit 1; }
TEMPLATE="$(bash "$ROOT/scripts/bootstrap_template.sh")"
printf '%s\n' 'Restoring SHA-pinned owner mirrors; matches do not establish organizer provenance.' >&2
"${PYTHON:-python3}" "$TEMPLATE/scripts/restore_data.py" --group core --target-dir "$ROOT/data"
