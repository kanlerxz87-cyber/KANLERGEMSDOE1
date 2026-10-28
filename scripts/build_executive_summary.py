#!/usr/bin/env python3
"""Publish a fail-closed, reproducible nine-site historical audit summary.

This is an evidence renderer, NOT a selector, experiment, score estimator or
live-site scraper. It never enables a contest download. Run the raster audit
first to update measurements; --check detects stale/tampered published output.
Only the standard library is required, including on Pages/CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FOCUS_SITES = tuple(f"GEMSDOE{i}" for i in (24, 25, 27, 28, 30, 31, 32, 33, 36))
BEGIN = "<!-- BEGIN GENERATED FOCUS SUMMARY -->"
END = "<!-- END GENERATED FOCUS SUMMARY -->"
INPUTS = {
    "focus_manifest": "registry/focus_sites.json",
    "raster_audit": "docs/evidence/protocol_audit_20261026.json",
    "current_run_card": "docs/evidence/current_run_card.json",
    "head_source_review": "docs/evidence/focus_head_review_20261027.json",
}


def read_json(path):
    # Python's default accepts NaN/Infinity, which is inappropriate evidence.
    def reject(value):
        raise ValueError(f"Nonfinite JSON literal: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)


def fraction(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"Invalid fraction: {value!r}")
    return float(value)


def indexed(rows):
    if not isinstance(rows, list) or len(rows) != len(FOCUS_SITES):
        raise ValueError("Exactly nine audited focus entries are required")
    by_site = {row["site"]: row for row in rows}
    if len(by_site) != len(rows) or set(by_site) != set(FOCUS_SITES):
        raise ValueError("Missing, duplicate or unexpected focus site")
    return by_site


def build(root=ROOT):
    sources = {name: read_json(root / path) for name, path in INPUTS.items()}
    manifest = indexed(sources["focus_manifest"]["files"])
    audit = sources["raster_audit"]
    measured = indexed(audit["focus_sites"])
    card = sources["current_run_card"]
    current_sources = indexed(sources["head_source_review"]["sources"])
    if card.get("ok_to_submit") is not False or card.get("verdict") != "negative":
        raise ValueError("This historical-audit renderer cannot publish an approved candidate; use a separate selector")
    if card["holdout_dti"].get("valid_value") is not None:
        raise ValueError("Unexpected holdout evidence: review the release before publishing")
    rows = []
    for site in FOCUS_SITES:
        m, a = manifest[site], measured[site]
        for key in ("sha256", "ref", "repo", "path", "dest", "reported_score", "score_evidence"):
            if a[key] != m[key]:
                raise ValueError(f"Audit/manifest mismatch for {site}: {key}")
        current = current_sources[site]
        if (current["reference_path"] != m["path"] or current["reference_sha256_at_head"] != m["sha256"]
                or current["reference_matches_pinned_bytes"] is not True):
            raise ValueError(f"Pinned artifact differs from latest reviewed HEAD bytes for {site}; review required")
        source_url = current.get("redirect_target_source", {}).get("url", current["homepage_source_url"])
        source_parts = urlsplit(source_url)
        source_commit = current["head_commit"]
        if (not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit)
                or source_parts.scheme != "https" or source_parts.netloc != "github.com"
                or not source_parts.path.startswith(f"/{m['repo']}/blob/{source_commit}/")
                or ".." in source_parts.path.split("/")):
            raise ValueError(f"Unpinned current homepage source URL for {site}")
        score = fraction(m["reported_score"])
        pairs = audit["focus_matrix"][site]
        if set(pairs) != set(FOCUS_SITES):
            raise ValueError(f"Incomplete comparison matrix for {site}")
        overlaps = {}
        duplicate = False
        for peer, pair in pairs.items():
            overlap = fraction(pair["within_3px_fraction"])
            rho = pair["spearman_final_dots"]
            if isinstance(rho, bool) or not isinstance(rho, (float, int)) or not math.isfinite(rho) or not -1 <= rho <= 1:
                raise ValueError(f"Undefined rank correlation for {site}/{peer}")
            if peer != site:
                overlaps[peer] = overlap
                duplicate |= overlap > .70 or rho > .90 or pair["identical_support"] is True
        worst = max(overlaps.values())
        if a["worst_peer"] not in overlaps or overlaps[a["worst_peer"]] != worst or a["worst_peer_3px_overlap"] != worst:
            raise ValueError(f"Stale worst-peer statistic for {site}")
        if a["literal_unique_vs_other_focus_champions"] is not (not duplicate):
            raise ValueError(f"Inconsistent uniqueness verdict for {site}")
        parsed = urlsplit(m["reference_url"])
        if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.path != f"/{m['repo']}/blob/{m['ref']}/{m['path']}":
            raise ValueError(f"Unpinned or unexpected source URL for {site}")
        if not isinstance(a["support_pixels"], int) or isinstance(a["support_pixels"], bool) or a["support_pixels"] <= 0:
            raise ValueError(f"Invalid support count for {site}")
        rows.append({
            "site": site, "reference_filename": Path(m["path"]).name,
            "owner_homepage_review": {"excerpt": current["owner_status_excerpt"],
                "source_url": source_url,
                "source_commit": current["head_commit"],
                "reference_bytes_unchanged_at_reviewed_head": True,
                "interpretation": current["review_interpretation"], "organizer_confirmed": False},
            "reference_url": m["reference_url"], "raster_sha256": m["sha256"],
            "positive_pixels": a["support_pixels"],
            "reported_score": score, "score_evidence": "USER/OWNER-REPORT; no submission-page receipt",
            "estimated_leaderboard_score": None,
            "holdout_dti": {"value": None, "ci95": None, "evaluator_version": None,
                            "n_withheld_positives": None, "status": "UNAVAILABLE: no admissible fold-local replay"},
            "worst_other_focus_overlap_3px": worst, "worst_other_focus_peer": a["worst_peer"],
            "identical_support_peers": a["identical_support_peers"],
            "unique_in_nine_champion_subset": not duplicate,
            "full_registry_checked": False, "surface_gate": "NOT REPLAYED",
            "ok_to_download_and_submit": False, "contest_download": None,
            "verdict": "DO NOT SUBMIT: duplicate" if duplicate else "DO NOT SUBMIT: incomplete scientific evidence",
        })
    best = max(rows, key=lambda r: r["reported_score"])
    return {
        "schema_version": 1, "scope": "Nine pinned historical champions, not an exhaustive current inventory of any site",
        "raster_audit_reviewed_utc": audit["reviewed_utc"],
        "source_sha256": {name: hashlib.sha256((root / path).read_bytes()).hexdigest() for name, path in INPUTS.items()},
        "banner": "STOP — NO RASTER IS CLEARED FOR SUBMISSION",
        "highest_user_report": {"site": best["site"], "value": best["reported_score"],
                                "evidence_class": "USER/OWNER-REPORT; not organizer-confirmed; not a recommendation"},
        "rows": rows, "new_experiments": 0, "slots_used": 0,
        "selector_required": True, "ok_to_submit": False,
    }


def render(report):
    parts = [BEGIN,
             '<h2>Latest requested-site scorecard (2026-10-28)</h2>',
             '<p><strong>Best reported history: GEMSDOE32, 0.2778 (user/owner report, not an organizer receipt). No file is cleared to submit.</strong> The requested-site scorecard includes every requested site\'s reported maximum, additional scores supplied for that site, provenance limits, and prior champion-raster overlap warnings. <a href="focus-sites-review-20261028.html">Open the nine-site focus review ↗</a>.</p>',
             '<h2>Which file should I download and submit?</h2>',
             '<p><strong>None is cleared.</strong> This table is generated from the pinned nine-site manifest and raster audit, not inferred from filenames or site marketing. “Estimated score” is unavailable in every row; a reported leaderboard value is not a forecast. No eligible new TIFF was generated after the mandatory lane STOP.</p>',
             '<div class="table-wrap"><table><caption>Submission decision · nine historical references</caption><thead><tr><th>Site</th><th>Reference file (research evidence only)</th><th>Reported score · evidence</th><th>Estimated score / valid HOLDOUT-DTI</th><th>Unique vs other eight champions?</th><th>Download and submit?</th></tr></thead><tbody>']
    for row in report["rows"]:
        parts.append('<tr><td>' + escape(row["site"]) + '</td><td class="file"><a href="' + escape(row["reference_url"], quote=True) + '">'
                     + escape(row["reference_filename"]) + '</a><br><small>SHA-256 ' + escape(row["raster_sha256"][:12])
                     + '… · ' + f'{row["positive_pixels"]:,}' + ' positive pixels</small></td><td>'
                     + f'{row["reported_score"]:.4f}' + '<br><small>USER/OWNER-REPORT<br>No organizer receipt</small></td>'
                     + '<td>Unavailable<br><small>No admissible fold-local replay or calibrated forecast</small></td><td class="bad">'
                     + ('FAIL' if not row["unique_in_nine_champion_subset"] else 'Incomplete') + '<br><small>'
                     + f'{row["worst_other_focus_overlap_3px"]:.2%}' + ' within 3 px of '
                     + escape(row["worst_other_focus_peer"]) + '</small></td><td class="bad">NO<br><small>No contest download authorized</small></td></tr>')
    parts += ['</tbody></table></div>',
              '<p>Audit replay: ' + escape(report["raster_audit_reviewed_utc"]) + '. These measurements do not certify a complete registry or a pre-placement surface check. See the <a href="evidence/site_summary.json">machine-readable table and input hashes</a> and <a href="evidence/protocol_audit_20261026.json">all 81 directional comparisons</a>. Different TIFF hashes do not prove different predictions: GEMSDOE25 and GEMSDOE30 have identical decoded support.</p>', END]
    # Publish source declarations separately: they are not our scientific results.
    source_table = ['<h2>What the current reviewed source pages say</h2>',
                    '<p>Owner declarations observed at immutable GitHub HEADs on 27 October; not organizer receipts or independently replayed current experiments. The nine historical reference TIFFs were also fetched at those HEADs and all nine SHA-256 hashes still match the pinned audited bytes.</p>',
                    '<div class="table-wrap"><table><thead><tr><th>Site</th><th>Owner homepage declaration (source text)</th><th>Our interpretation</th></tr></thead><tbody>']
    for row in report["rows"]:
        source = row['owner_homepage_review']
        source_table.append('<tr><td>' + escape(row['site']) + '</td><td><a href="'
                            + escape(source['source_url'], quote=True) + '">'
                            + escape(source['excerpt']) + '</a></td><td>' + escape(source['interpretation']) + '</td></tr>')
    source_table += ['</tbody></table></div>', '<p><a href="evidence/focus_head_review_20261027.json">Source byte hashes and flagged irregularities</a>. A peer site’s upload permission is not inherited by this project.</p>']
    parts[-1:-1] = source_table
    return '\n'.join(parts)


def outputs(root=ROOT):
    report = build(root)
    page_path = root / "docs/executive-summary.html"
    page = page_path.read_text(encoding="utf-8")
    if page.count(BEGIN) != 1 or page.count(END) != 1 or page.index(BEGIN) >= page.index(END):
        raise ValueError("Executive page must contain exactly one ordered generated-summary marker pair")
    start, end = page.index(BEGIN), page.index(END) + len(END)
    return {root / "docs/evidence/site_summary.json": json.dumps(report, indent=2, allow_nan=False) + '\n',
            page_path: page[:start] + render(report) + page[end:]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="Fail on stale/missing generated output without changing files")
    args = ap.parse_args()
    files = outputs()
    if args.check:
        stale = [str(p.relative_to(ROOT)) for p, text in files.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            raise SystemExit("Stale generated evidence; run scripts/build_executive_summary.py: " + ", ".join(stale))
        print("Executive summary and source hashes match; no submission is authorized.")
    else:
        for path, text in files.items():
            path.write_text(text, encoding="utf-8")
        print("Published nine historical audit rows; contest download remains blocked.")


if __name__ == "__main__":
    main()
