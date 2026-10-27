"""Publish a fail-closed historical readiness table; never select a contest slot.

Uses committed audit evidence, not a new raster evaluation or live score forecast.
Run with --check in CI to detect stale published reports.
"""
import argparse
import csv
import html
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITES = tuple(f'GEMSDOE{x}' for x in (24, 25, 27, 28, 30, 31, 32, 33, 36))


def rows_from_evidence(registry, audit):
    references = registry['files']
    measurements = audit['focus_sites']
    if (len(references) != len(SITES) or len(measurements) != len(SITES)
            or {r['site'] for r in references} != set(SITES)
            or {r['site'] for r in measurements} != set(SITES)):
        raise ValueError('Expected exactly one reference and measurement per focus site')
    by_site = {r['site']: r for r in measurements}
    rows = []
    for reference in references:
        measured = by_site[reference['site']]
        for key in ('sha256', 'ref', 'path', 'reported_score', 'score_evidence'):
            if measured[key] != reference[key]:
                raise ValueError(f"Audit/registry mismatch: {reference['site']} {key}")
        overlap = measured['worst_peer_3px_overlap']
        if not isinstance(overlap, (int, float)) or not 0 <= overlap <= 1:
            raise ValueError('Invalid overlap measurement')
        # This report deliberately cannot promote historical references. It must
        # be redesigned with valid fold evidence before any future promotion.
        if overlap <= .70 or measured['literal_unique_vs_other_focus_champions'] is not False:
            raise ValueError('Historical negative evidence changed; review report policy')
        rows.append({
            'site': reference['site'],
            'historical_reference_file': Path(reference['path']).name,
            'sha256': reference['sha256'],
            'reported_score': f"{reference['reported_score']:.4f}",
            'score_evidence': reference['score_evidence'],
            'estimated_score': 'UNAVAILABLE; no admissible HOLDOUT-DTI',
            'uniqueness': 'FAIL under directional overlap rule',
            'worst_peer': measured['worst_peer'],
            'within_3px_fraction': str(overlap),
            'file_to_submit': 'NONE',
            'ok_to_submit': 'NO',
        })
    return sorted(rows, key=lambda row: SITES.index(row['site']))


def render(rows, reviewed_utc):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    esc = html.escape
    table_rows = ''.join(
        '<tr>' + ''.join(f'<td>{esc(str(value))}</td>' for value in (
            r['site'], r['historical_reference_file'],
            r['reported_score'] + ' (USER/OWNER-REPORT; no receipt)',
            r['estimated_score'], r['uniqueness'],
            f"{float(r['within_3px_fraction']):.2%} vs {r['worst_peer']}",
            r['file_to_submit'], r['ok_to_submit'])) + '</tr>' for r in rows)
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Submission readiness · KANLER GEMS</title><link rel="stylesheet" href="assets/style.css"></head>
<body><header><div class="wrap"><h1>Which file can I submit?</h1><nav class="nav"><a href="index.html">Status</a><a href="executive-summary.html">Executive summary</a><a href="how-to-submit.html">Submission instructions</a></nav></div></header>
<main class="wrap"><div class="banner" role="status"><strong>NONE — DO NOT SUBMIT THESE HISTORICAL FILES</strong>
<p>No unique, validated contest download or defensible score estimate is available. A local format pass is not a scientific promotion pass.</p></div>
<p>Evidence date: {esc(reviewed_utc)}. This table is generated from the committed, pinned nine-site audit, not a new evaluation or a live site crawl. Latest review does not refresh these measurements.</p>
<p>GEMSDOE32 has the highest <em>reported</em> historical score in this group; it is not a recommended submission. Overlap failure is not necessarily byte identity. A complete registry and pre-placement surface audit are still missing.</p>
<p><a href="evidence/submission_readiness.csv" download>Download the nine-site readiness table (CSV)</a> · <a href="evidence/protocol_audit_20261026.json">Underlying audit</a> · <a href="evidence/current_run_card.json">Negative run card</a></p>
<div class="table-wrap"><table><thead><tr><th>Site</th><th>Historical reference (NOT a download recommendation)</th><th>Historical score evidence</th><th>Estimated score</th><th>Unique?</th><th>Directional dot overlap</th><th>File to submit</th><th>OK to submit?</th></tr></thead><tbody>{table_rows}</tbody></table></div>
<h2>Unblocking sequence — no automatic slot use</h2><ol>
<li>Resolve the stopped lane and assign a specific method; the current request supplies no new single-method paragraph.</li>
<li>Complete the registry and verify data origin/licensing, including an organizer-authenticated template.</li>
<li>Before placement, pass surface and preregistered support checks; stop on any duplicate.</li>
<li>Pass withheld-segment feature canaries and replay fold-local features and placement with the shared evaluator. Beat the current admissible holdout best with paired evidence; no such baseline is established here.</li>
<li>Pass final dot uniqueness and strict TIFF validation, then obtain the separate selector decision within the authenticated weekly cap.</li></ol>
<p>Neither a renamed file nor a different TIFF compression proves uniqueness. Nothing on this page uploads to the competition.</p></main></body></html>\n'''
    return page, stream.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    registry = json.loads((ROOT / 'registry/focus_sites.json').read_text())
    audit = json.loads((ROOT / 'evidence/protocol_audit_20261026.json').read_text())
    rows = rows_from_evidence(registry, audit)
    page, csv_text = render(rows, audit['reviewed_utc'])
    for path, content in ((ROOT / 'docs/submission-readiness.html', page),
                          (ROOT / 'docs/evidence/submission_readiness.csv', csv_text)):
        if args.check:
            if not path.is_file() or path.read_text() != content:
                raise SystemExit(f'Stale report: {path.relative_to(ROOT)}')
        else:
            path.write_text(content, encoding='utf-8')
    print('Nine-site readiness report verified; cleared files: 0; no slot selected.')


if __name__ == '__main__':
    main()
