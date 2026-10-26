#!/usr/bin/env bash
# Restore the public, checksum-pinned shared template without modifying it.
# The extracted tree is refreshed from the verified archive on every invocation.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REV=07806249f4ed3efe70b4fbf866183c32392b7853
ARCHIVE_SHA=74421783a733593d61893de323c3dfd6f4a2cf4a2af2d07bdd872e17bc3df12d
CACHE="$ROOT/.cache/upstream"
ARCHIVE="$CACHE/GEMSDOE32-$REV.tar.gz"
mkdir -p "$CACHE"
if [[ ! -f "$ARCHIVE" ]] || [[ "$(sha256sum "$ARCHIVE" | cut -d' ' -f1)" != "$ARCHIVE_SHA" ]]; then
  command -v gh >/dev/null || { echo 'GitHub CLI (gh) is required to restore the pinned template.' >&2; exit 1; }
  tmp="$(mktemp "$CACHE/.template.XXXXXX")"
  trap 'rm -f "$tmp"' EXIT
  gh api "repos/buffedlizard55-lab/GEMSDOE32/tarball/$REV" > "$tmp"
  [[ "$(sha256sum "$tmp" | cut -d' ' -f1)" == "$ARCHIVE_SHA" ]] || { echo 'Template archive hash mismatch; refusing extraction.' >&2; exit 1; }
  mv -f "$tmp" "$ARCHIVE"
  trap - EXIT
fi
"${PYTHON:-python3}" "$ROOT/scripts/restore_template.py" "$ARCHIVE" "$CACHE" "$REV" "$ARCHIVE_SHA"
printf '%s\n' "$CACHE/GEMSDOE32-$REV"
