#!/usr/bin/env python3
"""Historical parallel MPLC generator is stopped after a literal registry duplicate.

The historical implementation remains available in Git history. This entry point
must not emit a new candidate after STOP. Inspect existing bytes via
``scripts/audit_existing_candidates.py --restore``; that audit runs no experiment.
"""
raise SystemExit("STOP: MPLC overlaps the registered lattice by 99.95% (>70%); no new raster or slot is authorized.")
