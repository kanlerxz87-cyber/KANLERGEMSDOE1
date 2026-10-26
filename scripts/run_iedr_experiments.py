#!/usr/bin/env python3
"""Stopped IEDR lane. Never generate or promote after a literal duplicate.

The historical runner was removed from the executable path: it excluded a lattice
from the registry, used a final full-catalogue mask as a holdout prediction, and
sampled canaries outside a verified withheld-only split (and did not fail closed). Reproduce the negative byte-level audit with
``python scripts/audit_existing_candidates.py --restore``. The historical runner
remains in Git history for analysis; its reported holdouts are not release evidence.
"""
import sys


def main() -> int:
    print("STOP: IEDR overlaps the registered lattice by more than 70% within 3 px. "
          "No new experiment, raster, promotion or competition slot is permitted in this lane. "
          "Run scripts/audit_existing_candidates.py --restore to reproduce the evidence.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
